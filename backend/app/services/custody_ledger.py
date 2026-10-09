"""Tamper-evident custody ledger (v3): the only writer of ``chain_of_custody``.

Each entry is appended to two hash chains at once, its evidence item's chain
(``seq``/``prev_hash``) and its incident's chain (``incident_seq``/
``incident_prev_hash``); ``entry_hash`` commits to both and the row is
HMAC-signed (``models/artifact.py`` ``before_insert``). Payload and
verification rules live in ``app/utils/verify_custody.py`` (stdlib; shipped in
export bundles).

Concurrency: ``pg_advisory_xact_lock('custody:<incident_id>')`` + ``max(seq)``
per chain. One lock per incident serialises both chains (and evidence
numbering). Custody does not use ``ledger_heads`` (two chains per entry).

Every method runs inside the caller's transaction and flushes; callers commit.
Custody state machine (409 ``invalid_custody_transition`` on violation)::

    in_storage --check_out--> checked_out --check_in--> in_storage
    in_storage|checked_out --transfer--> transferred --check_in--> in_storage
    in_storage|checked_out|transferred --dispose--> disposed   (terminal; blocked under legal hold)

``void`` (tombstone) needs no legal hold and no live children. Every other
action leaves the state unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func

from app import db
from app.models import Artifact, ChainOfCustody, CustodyAnchor, CustodyParty, EvidenceItem, User
from app.models.evidence import EVIDENCE_TYPES, HASH_ALGORITHMS, HASH_SOURCES, TRANSFER_METHODS
from app.utils import verify_custody as vc
from app.utils.hash_chain import advisory_xact_lock

CHAIN_VERSION = vc.CHAIN_VERSION
CLIENTS = ('web', 'mcp-server', 'mcp-bridge')
DISPOSE_METHODS = ('returned_to_owner', 'destroyed', 'released', 'other')


class CustodyError(Exception):
    """A custody operation that would violate the ledger rules."""
    status = 409
    code = 'invalid_custody_transition'

    def __init__(self, message, *, code=None, status=None, details=None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status:
            self.status = status
        self.details = details or {}

    def to_dict(self):
        return {'error': self.code, 'message': self.message, **self.details}

    def to_response(self):
        from flask import jsonify
        return jsonify(self.to_dict()), self.status


def lock_key(incident_id) -> str:
    return f'custody:{vc.canon_uuid(incident_id)}'


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds') if value else None


def _uid(value):
    if value is None:
        return None
    return getattr(value, 'id', value)


def _request_meta():
    """(ip_address, user_agent, client) of the current request, if any."""
    try:
        from flask import has_request_context, request
    except ImportError:  # pragma: no cover
        return None, None, 'system'
    if not has_request_context():
        return None, None, 'system'
    client = (request.headers.get('X-SheetStorm-Client') or 'web').strip().lower()
    if client not in CLIENTS:
        client = 'other'
    return request.remote_addr, (request.headers.get('User-Agent') or '')[:500] or None, client


def _user_name(user_id):
    if user_id is None:
        return None
    user = db.session.get(User, user_id)
    return user.name if user is not None else None


class CustodyLedger:
    """Append-only custody ledger operations (see module docstring)."""

    # ── Locking / chain heads ──────────────────────────────────────────────

    @staticmethod
    def lock(incident_id) -> None:
        """Serialise custody writes for one incident (released at COMMIT/ROLLBACK)."""
        advisory_xact_lock(db.session, lock_key(incident_id))

    @staticmethod
    def _fresh(item: EvidenceItem) -> EvidenceItem:
        """Lock the item's incident and reload the item so state checks see
        the latest committed projection."""
        CustodyLedger.lock(item.incident_id)
        if item.id is not None and item in db.session and item not in db.session.new:
            db.session.flush()
            db.session.refresh(item)
        return item

    @staticmethod
    def _legacy_rows(**filters):
        return (db.session.query(ChainOfCustody.id, ChainOfCustody.signature, ChainOfCustody.created_at)
                .filter_by(**filters).filter(ChainOfCustody.chain_version.is_(None))
                .order_by(ChainOfCustody.created_at, ChainOfCustody.id).all())

    @staticmethod
    def _legacy_dicts(rows):
        return [{'id': r[0], 'signature': r[1], 'created_at': r[2]} for r in rows]

    @staticmethod
    def _head(seq_col, scope_name, scope_id, **filters):
        """(next_seq, prev_hash, legacy_seal_info_or_None) for one chain."""
        last = (db.session.query(seq_col, ChainOfCustody.entry_hash)
                .filter_by(**filters).filter(ChainOfCustody.chain_version == CHAIN_VERSION)
                .order_by(seq_col.desc()).first())
        if last is not None:
            return last[0] + 1, last[1], None
        legacy = CustodyLedger._legacy_dicts(CustodyLedger._legacy_rows(**filters))
        genesis, kind = vc.chain_genesis(scope_name, scope_id, legacy)
        seal = {'count': len(legacy), 'hash': genesis} if kind == 'legacy_seal' else None
        return 1, genesis, seal

    # ── State snapshot ─────────────────────────────────────────────────────

    @staticmethod
    def state_after(item: EvidenceItem) -> dict:
        if item.current_holder_party_id is not None:
            party = item.current_holder_party or db.session.get(CustodyParty, item.current_holder_party_id)
            holder = {'type': 'party', 'id': str(item.current_holder_party_id), 'name': party.name if party else None}
        elif item.current_holder_user_id is not None:
            holder = {'type': 'user', 'id': str(item.current_holder_user_id),
                      'name': _user_name(item.current_holder_user_id)}
        else:
            holder = {'type': 'storage', 'id': None, 'name': item.storage_location}
        return {'custody_state': item.custody_state, 'holder': holder, 'storage_location': item.storage_location}

    @staticmethod
    def item_snapshot(item: EvidenceItem) -> dict:
        """Full metadata snapshot (strict-JSON values) for ``register``."""
        fields = ('evidence_type', 'title', 'description', 'condition_notes', 'media_type', 'make', 'model',
                  'serial_number', 'seal_number', 'bag_number', 'storage_location', 'acquired_by_name',
                  'acquired_from', 'acquisition_method', 'acquisition_tool', 'acquisition_tool_version',
                  'source_host_label', 'derivation_note')
        snap = {f: getattr(item, f) for f in fields}
        snap['capacity_bytes'] = item.capacity_bytes
        snap['acquired_at'] = _iso(item.acquired_at)
        snap['acquired_by_user_id'] = vc.canon_uuid(item.acquired_by_user_id)
        snap['source_host_id'] = vc.canon_uuid(item.source_host_id)
        snap['parent_id'] = vc.canon_uuid(item.parent_id)
        snap['sequence_number'] = item.sequence_number
        snap['evidence_number'] = item.evidence_number
        snap['acquisition_hashes'] = list(item.acquisition_hashes or [])
        return snap

    # ── Core append ────────────────────────────────────────────────────────

    @staticmethod
    def append(item: EvidenceItem, action: str, *, performed_by, artifact: Optional[Artifact] = None,
               purpose=None, recipient_id=None, external_party: Optional[CustodyParty] = None,
               transfer_method=None, verification_result=None, extra: Optional[dict] = None) -> ChainOfCustody:
        """Append one ledger entry for ``item`` (no state transition; use the
        named methods for check_out/check_in/transfer/dispose/void).

        ``extra`` must be strict JSON (str/int/bool/null/list/dict; no floats).
        Server-written ``extra_data`` keys: performer_name, state_after,
        client, and legacy_seal/incident_legacy_seal on a chain's first entry.
        """
        if action not in ChainOfCustody.ACTIONS:
            raise ValueError(f'unknown custody action {action!r}')
        if transfer_method is not None and transfer_method not in TRANSFER_METHODS:
            raise CustodyError('Invalid transfer_method', code='bad_request', status=400)
        if item.id is None or item.incident_id is None:
            raise ValueError('evidence item must be flushed before appending custody entries')
        CustodyLedger.lock(item.incident_id)
        db.session.flush()

        seq, prev, item_seal = CustodyLedger._head(ChainOfCustody.seq, 'item', item.id,
                                                   evidence_item_id=item.id)
        iseq, iprev, inc_seal = CustodyLedger._head(ChainOfCustody.incident_seq, 'incident',
                                                    item.incident_id, incident_id=item.incident_id)
        performer_id = _uid(performed_by)
        ip, ua, client = _request_meta()
        ed = dict(extra or {})
        ed['performer_name'] = getattr(performed_by, 'name', None) or _user_name(performer_id)
        ed['state_after'] = CustodyLedger.state_after(item)
        ed['client'] = client
        ed['evidence_number'] = item.evidence_number
        if item_seal:
            ed['legacy_seal'] = item_seal
        if inc_seal:
            ed['incident_legacy_seal'] = inc_seal
        if external_party is not None:
            ed.setdefault('party', external_party.snapshot())

        entry = ChainOfCustody(
            artifact_id=artifact.id if artifact is not None else None,
            evidence_item_id=item.id,
            incident_id=item.incident_id,
            seq=seq, incident_seq=iseq, prev_hash=prev, incident_prev_hash=iprev,
            chain_version=CHAIN_VERSION,
            action=action,
            performed_by=performer_id,
            ip_address=ip, user_agent=ua,
            purpose=purpose,
            recipient_id=_uid(recipient_id),
            external_party_id=external_party.id if external_party is not None else None,
            transfer_method=transfer_method,
            verification_result=verification_result,
            extra_data=ed,
        )
        db.session.add(entry)
        db.session.flush()
        return entry

    # ── Registration ───────────────────────────────────────────────────────

    @staticmethod
    def register_item(item: EvidenceItem, *, actor, extra: Optional[dict] = None) -> ChainOfCustody:
        """Number, persist and register a new item (``register`` entry with a
        full metadata snapshot; plus ``derive`` on the parent when set)."""
        if item.evidence_type not in EVIDENCE_TYPES:
            raise CustodyError('Invalid evidence_type', code='bad_request', status=400)
        CustodyLedger.lock(item.incident_id)
        if item.organization_id is None:
            from app.models import Incident
            item.organization_id = db.session.get(Incident, item.incident_id).organization_id
        if item.parent_id is not None:
            parent = db.session.get(EvidenceItem, item.parent_id)
            if parent is None or parent.incident_id != item.incident_id:
                raise CustodyError('Parent evidence item not found', code='not_found', status=404)
            if parent.is_voided:
                raise CustodyError('Parent evidence item is voided')
        last = (db.session.query(func.max(EvidenceItem.sequence_number))
                .filter(EvidenceItem.incident_id == item.incident_id).scalar())
        item.sequence_number = (last or 0) + 1
        item.created_by = item.created_by or _uid(actor)
        if item.custody_state is None:
            item.custody_state = 'in_storage'
        if item.acquisition_hashes is None:
            item.acquisition_hashes = []
        db.session.add(item)
        db.session.flush()
        entry = CustodyLedger.append(item, 'register', performed_by=actor,
                                     extra={'item': CustodyLedger.item_snapshot(item), **(extra or {})})
        if item.parent_id is not None:
            parent = db.session.get(EvidenceItem, item.parent_id)
            CustodyLedger.append(parent, 'derive', performed_by=actor,
                                 extra={'child': {'id': str(item.id), 'evidence_number': item.evidence_number,
                                                  'title': item.title},
                                        'derivation_note': item.derivation_note})
        return entry

    # ── Transitions ────────────────────────────────────────────────────────

    @staticmethod
    def _require_active(item):
        if item.is_voided:
            raise CustodyError(f'{item.evidence_number} is voided')
        if item.custody_state == 'disposed':
            raise CustodyError(f'{item.evidence_number} has been disposed')

    @staticmethod
    def _require_text(value, name):
        if not isinstance(value, str) or not value.strip():
            raise CustodyError(f'{name} is required', code='bad_request', status=400)
        return value.strip()

    @staticmethod
    def _recipient(to_user, to_party):
        if (to_user is None) == (to_party is None):
            raise CustodyError('Exactly one of to_user / to_party is required', code='bad_request', status=400)
        if to_party is not None and not to_party.is_active:
            raise CustodyError('Custody party is inactive')

    @staticmethod
    def _set_holder(item, to_user=None, to_party=None):
        item.current_holder_user = to_user
        item.current_holder_party = to_party
        item.current_holder_user_id = to_user.id if to_user is not None else None
        item.current_holder_party_id = to_party.id if to_party is not None else None

    @staticmethod
    def check_out(item, *, actor, purpose, to_user=None, to_party=None, transfer_method=None,
                  expected_return_at=None, extra=None):
        item = CustodyLedger._fresh(item)
        CustodyLedger._require_active(item)
        purpose = CustodyLedger._require_text(purpose, 'purpose')
        CustodyLedger._recipient(to_user, to_party)
        if item.custody_state != 'in_storage':
            raise CustodyError(f'Cannot check out an item that is {item.custody_state}')
        item.custody_state = 'checked_out'
        CustodyLedger._set_holder(item, to_user, to_party)
        item.expected_return_at = expected_return_at
        ed = dict(extra or {})
        ed['expected_return_at'] = _iso(expected_return_at)
        if to_user is not None:
            ed['recipient'] = {'type': 'user', 'id': str(to_user.id), 'name': to_user.name}
        return CustodyLedger.append(item, 'check_out', performed_by=actor, purpose=purpose,
                                    recipient_id=to_user, external_party=to_party,
                                    transfer_method=transfer_method, extra=ed)

    @staticmethod
    def transfer(item, *, actor, reason, transfer_method, to_user=None, to_party=None, extra=None):
        item = CustodyLedger._fresh(item)
        CustodyLedger._require_active(item)
        reason = CustodyLedger._require_text(reason, 'reason')
        if transfer_method not in TRANSFER_METHODS:
            raise CustodyError('transfer_method is required', code='bad_request', status=400)
        CustodyLedger._recipient(to_user, to_party)
        if item.custody_state not in ('in_storage', 'checked_out'):
            raise CustodyError(f'Cannot transfer an item that is {item.custody_state}')
        item.custody_state = 'transferred'
        CustodyLedger._set_holder(item, to_user, to_party)
        item.expected_return_at = None
        ed = dict(extra or {})
        if to_user is not None:
            ed['recipient'] = {'type': 'user', 'id': str(to_user.id), 'name': to_user.name}
        return CustodyLedger.append(item, 'transfer', performed_by=actor, purpose=reason,
                                    recipient_id=to_user, external_party=to_party,
                                    transfer_method=transfer_method, extra=ed)

    @staticmethod
    def check_in(item, *, actor, storage_location, seal_intact, condition_notes=None, seal_number=None,
                 received_from_party=None, extra=None):
        item = CustodyLedger._fresh(item)
        CustodyLedger._require_active(item)
        storage_location = CustodyLedger._require_text(storage_location, 'storage_location')
        if not isinstance(seal_intact, bool):
            raise CustodyError('seal_intact (boolean) is required', code='bad_request', status=400)
        if item.custody_state not in ('checked_out', 'transferred'):
            raise CustodyError(f'Cannot check in an item that is {item.custody_state}')
        previous = CustodyLedger.state_after(item)
        item.custody_state = 'in_storage'
        CustodyLedger._set_holder(item)
        item.storage_location = storage_location
        item.expected_return_at = None
        if condition_notes is not None:
            item.condition_notes = condition_notes
        if seal_number:
            item.seal_number = seal_number
        ed = dict(extra or {})
        ed.update({'seal_intact': seal_intact, 'seal_number': seal_number, 'condition_notes': condition_notes,
                   'received_from': previous['holder']})
        return CustodyLedger.append(item, 'check_in', performed_by=actor, external_party=received_from_party,
                                    extra=ed)

    @staticmethod
    def dispose(item, *, actor, method, reason, witness_name=None, extra=None):
        item = CustodyLedger._fresh(item)
        CustodyLedger._require_active(item)
        reason = CustodyLedger._require_text(reason, 'reason')
        if method not in DISPOSE_METHODS:
            raise CustodyError('Invalid disposal method', code='bad_request', status=400)
        if item.under_legal_hold:
            raise CustodyError(f'{item.evidence_number} is under legal hold', code='legal_hold')
        item.custody_state = 'disposed'
        CustodyLedger._set_holder(item)
        item.expected_return_at = None
        ed = dict(extra or {})
        ed.update({'method': method, 'witness_name': witness_name})
        return CustodyLedger.append(item, 'dispose', performed_by=actor, purpose=reason, extra=ed)

    @staticmethod
    def void(item, *, actor, reason, extra=None):
        item = CustodyLedger._fresh(item)
        reason = CustodyLedger._require_text(reason, 'reason')
        if item.is_voided:
            raise CustodyError(f'{item.evidence_number} is already voided')
        if item.under_legal_hold:
            raise CustodyError(f'{item.evidence_number} is under legal hold', code='legal_hold')
        live_children = item.children.filter(EvidenceItem.voided_at.is_(None)).count()
        if live_children:
            raise CustodyError(f'{item.evidence_number} has {live_children} derived item(s) that are not voided')
        item.voided_at = _now()
        item.voided_by = _uid(actor)
        item.void_reason = reason
        return CustodyLedger.append(item, 'void', performed_by=actor, purpose=reason, extra=extra)

    @staticmethod
    def acknowledge(item, entry: ChainOfCustody, *, actor, typed_name, statement=None, stated_at=None,
                    receipt_artifact: Optional[Artifact] = None, extra=None):
        """Typed-name acknowledgment of a transfer/check_out (once per entry)."""
        item = CustodyLedger._fresh(item)
        typed_name = CustodyLedger._require_text(typed_name, 'typed_name')
        if (entry is None or entry.evidence_item_id != item.id or entry.action not in ('transfer', 'check_out')
                or not entry.is_chained):
            raise CustodyError('Only a transfer or check-out entry of this item can be acknowledged',
                               code='not_found', status=404)
        already = (ChainOfCustody.query.filter_by(evidence_item_id=item.id, action='acknowledge')
                   .filter(ChainOfCustody.extra_data['acknowledges'].astext == str(entry.id)).first())
        if already is not None:
            raise CustodyError('This entry has already been acknowledged')
        if receipt_artifact is not None and (receipt_artifact.incident_id != item.incident_id
                                             or receipt_artifact.purpose != 'custody_receipt'
                                             or receipt_artifact.is_deleted):
            raise CustodyError('receipt_artifact must be a custody receipt of this incident',
                               code='bad_request', status=400)
        ed = dict(extra or {})
        ed.update({'acknowledges': str(entry.id), 'acknowledges_seq': entry.seq, 'typed_name': typed_name,
                   'statement': statement, 'stated_at': _iso(stated_at)})
        if receipt_artifact is not None:
            ed['receipt'] = {'artifact_id': str(receipt_artifact.id), 'sha256': receipt_artifact.sha256,
                             'filename': receipt_artifact.original_filename}
        return CustodyLedger.append(item, 'acknowledge', performed_by=actor, artifact=receipt_artifact,
                                    extra=ed)

    # ── Non-transition helpers ─────────────────────────────────────────────

    @staticmethod
    def set_legal_hold(item, *, actor, hold: bool, until=None, reason=None):
        """Place (indefinite lock, or until ``until``) or release an item hold."""
        item = CustodyLedger._fresh(item)
        item.is_locked = bool(hold) and until is None
        item.legal_hold_until = until if hold else None
        return CustodyLedger.append(item, 'legal_hold', performed_by=actor, purpose=reason,
                                    extra={'hold': bool(hold), 'legal_hold_until': _iso(item.legal_hold_until)})

    @staticmethod
    def add_hash(item, *, actor, algorithm, value, source, supersedes=None, reason=None):
        """Add an acquisition hash (never edited; corrections supersede)."""
        item = CustodyLedger._fresh(item)
        algorithm = (algorithm or '').lower()
        value = (value or '').lower()
        if algorithm not in HASH_ALGORITHMS or source not in HASH_SOURCES:
            raise CustodyError('Invalid hash algorithm or source', code='bad_request', status=400)
        if len(value) != HASH_ALGORITHMS[algorithm] or any(c not in '0123456789abcdef' for c in value):
            raise CustodyError(f'{algorithm} value must be {HASH_ALGORITHMS[algorithm]} hex characters',
                               code='bad_request', status=400)
        hashes = [dict(h) for h in (item.acquisition_hashes or []) if isinstance(h, dict)]
        if supersedes is None and any(h.get('algorithm') == algorithm and not h.get('superseded')
                                      for h in hashes):
            raise CustodyError(f'A {algorithm} hash is already recorded; supersede it with a reason')
        if supersedes is not None:
            CustodyLedger._require_text(reason, 'reason')
        record = {'algorithm': algorithm, 'value': value, 'source': source, 'recorded_at': _iso(_now()),
                  'recorded_by': vc.canon_uuid(_uid(actor))}
        if supersedes is not None:
            record['supersedes'] = str(supersedes)
            for h in hashes:
                if h.get('algorithm') == algorithm and h.get('value') == str(supersedes).lower():
                    h['superseded'] = True
        hashes.append(record)
        item.acquisition_hashes = hashes
        return CustodyLedger.append(item, 'add_hash', performed_by=actor, purpose=reason, extra={'hash': record})

    @staticmethod
    def record_verification(item, *, actor, algorithm, expected, observed, method=None, tool=None,
                            notes=None, artifact=None, extra=None):
        """Append a ``verify`` entry and update the verification projection."""
        item = CustodyLedger._fresh(item)
        match = bool(expected) and (observed or '').lower() == (expected or '').lower()
        result = 'match' if match else 'mismatch'
        item.last_verified_at = _now()
        item.last_verification_result = result
        ed = dict(extra or {})
        ed.update({'algorithm': algorithm, 'expected_hash': expected, 'observed_hash': observed,
                   'match': match, 'method': method, 'tool': tool, 'notes': notes})
        return CustodyLedger.append(item, 'verify', performed_by=actor, artifact=artifact,
                                    verification_result=result, extra=ed)

    # ── Reads / verification ───────────────────────────────────────────────

    @staticmethod
    def entries(item=None, incident_id=None, artifact_id=None):
        q = ChainOfCustody.query
        if item is not None:
            q = q.filter(ChainOfCustody.evidence_item_id == item.id)
        if incident_id is not None:
            q = q.filter(ChainOfCustody.incident_id == incident_id)
        if artifact_id is not None:
            q = q.filter(ChainOfCustody.artifact_id == artifact_id)
        # Legacy rows first (they precede the chain), then chain order.
        return q.order_by(ChainOfCustody.chain_version.is_(None).desc(), ChainOfCustody.incident_seq,
                          ChainOfCustody.created_at, ChainOfCustody.id).all()

    @staticmethod
    def heads(incident_id) -> dict:
        """Incident head + per-item heads (for purge events / manifests)."""
        inc = (db.session.query(ChainOfCustody.incident_seq, ChainOfCustody.entry_hash)
               .filter(ChainOfCustody.incident_id == incident_id, ChainOfCustody.chain_version == CHAIN_VERSION)
               .order_by(ChainOfCustody.incident_seq.desc()).first())
        sub = (db.session.query(ChainOfCustody.evidence_item_id, func.max(ChainOfCustody.seq).label('seq'))
               .filter(ChainOfCustody.incident_id == incident_id, ChainOfCustody.chain_version == CHAIN_VERSION)
               .group_by(ChainOfCustody.evidence_item_id).subquery())
        rows = (db.session.query(ChainOfCustody.evidence_item_id, ChainOfCustody.seq, ChainOfCustody.entry_hash)
                .join(sub, (sub.c.evidence_item_id == ChainOfCustody.evidence_item_id)
                      & (sub.c.seq == ChainOfCustody.seq)).all())
        return {
            'incident': {'seq': inc[0], 'hash': inc[1]} if inc else None,
            'items': {str(r[0]): {'seq': r[1], 'hash': r[2]} for r in rows},
        }

    @staticmethod
    def _signature_statuses(rows):
        from flask import current_app
        from app.models.artifact import custody_signing_key
        secret = custody_signing_key()
        legacy_secret = current_app.config.get('SECRET_KEY', '')
        return {r.id: r.signature_status(secret, legacy_secret=legacy_secret) for r in rows}

    @staticmethod
    def _projection_drift(item, rows):
        chained = [r for r in rows if r.is_chained and r.evidence_item_id == item.id]
        if not chained:
            return []
        last = max(chained, key=lambda r: r.seq or 0)
        recorded = (last.extra_data or {}).get('state_after')
        if not isinstance(recorded, dict):
            return []
        current = CustodyLedger.state_after(item)
        drift = []
        if recorded.get('custody_state') != current['custody_state']:
            drift.append({'field': 'custody_state', 'item_value': current['custody_state'],
                          'ledger_value': recorded.get('custody_state')})
        rh, ch = recorded.get('holder') or {}, current['holder']
        if (rh.get('type'), rh.get('id')) != (ch.get('type'), ch.get('id')):
            drift.append({'field': 'holder', 'item_value': ch, 'ledger_value': rh})
        if recorded.get('storage_location') != current['storage_location']:
            drift.append({'field': 'storage_location', 'item_value': current['storage_location'],
                          'ledger_value': recorded.get('storage_location')})
        return drift

    @staticmethod
    def _chain_report(rows, scope, scope_id, *, seq_attr='seq', prev_attr='prev_hash'):
        chained = [r for r in rows if r.is_chained]
        legacy = [r for r in rows if not r.is_chained]
        res = vc.verify_chain(chained, scope, scope_id, legacy, seq_attr=seq_attr, prev_attr=prev_attr)
        first = min(chained, key=lambda r: getattr(r, seq_attr) or 0) if chained else None
        seal_key = 'legacy_seal' if scope == 'item' else 'incident_legacy_seal'
        sealed = bool(first is not None and (first.extra_data or {}).get(seal_key))
        return res, {'count': len(legacy), 'sealed': sealed}, chained

    @staticmethod
    def verify(item: Optional[EvidenceItem] = None, incident=None) -> dict:
        """Read-only verification of an item chain or a whole incident ledger.

        ``status``: intact | intact_with_unsigned_legacy | unverifiable
        (key_mismatch) | broken (link/hash/seq breaks) | compromised (an HMAC
        does not match). Callers that expose it should audit-log
        ``custody_chain_verified`` (no ledger row is written).
        """
        if (item is None) == (incident is None):
            raise ValueError('pass exactly one of item / incident')
        incident_id = item.incident_id if item is not None else incident.id
        result = {'scope': 'item' if item is not None else 'incident',
                  'incident_id': str(incident_id), 'breaks': [], 'warnings': [], 'projection_drift': [],
                  'notes': []}
        if item is not None:
            rows = CustodyLedger.entries(item=item)
            res, legacy, chained = CustodyLedger._chain_report(rows, 'item', item.id)
            result['evidence_item_id'] = str(item.id)
            result['item_chain'] = {k: res[k] for k in ('length', 'head_seq', 'head_hash', 'genesis')}
            result['breaks'] = [dict(b, chain='item', evidence_item_id=str(item.id)) for b in res['breaks']]
            result['warnings'] = [dict(w, chain='item') for w in res['warnings']]
            result['projection_drift'] = CustodyLedger._projection_drift(item, rows)
            result['legacy'] = legacy
        else:
            rows = CustodyLedger.entries(incident_id=incident_id)
            res, legacy, chained = CustodyLedger._chain_report(rows, 'incident', incident_id,
                                                               seq_attr='incident_seq',
                                                               prev_attr='incident_prev_hash')
            result['incident_chain'] = {k: res[k] for k in ('length', 'head_seq', 'head_hash', 'genesis')}
            result['breaks'] = [dict(b, chain='incident') for b in res['breaks']]
            result['warnings'] = [dict(w, chain='incident') for w in res['warnings']]
            result['legacy'] = legacy
            items = {}
            item_rows = {}
            for r in rows:
                item_rows.setdefault(r.evidence_item_id, []).append(r)
            all_items = EvidenceItem.query.filter_by(incident_id=incident_id).all()
            for it in all_items:
                its = item_rows.get(it.id, [])
                ires, ileg, _ = CustodyLedger._chain_report(its, 'item', it.id)
                items[str(it.id)] = {
                    'evidence_number': it.evidence_number,
                    **{k: ires[k] for k in ('length', 'head_seq', 'head_hash', 'genesis')},
                    'breaks': ires['breaks'], 'legacy': ileg,
                }
                result['breaks'] += [dict(b, chain='item', evidence_item_id=str(it.id)) for b in ires['breaks']]
                result['warnings'] += [dict(w, chain='item', evidence_item_id=str(it.id))
                                       for w in ires['warnings']]
                result['projection_drift'] += [dict(d, evidence_item_id=str(it.id))
                                               for d in CustodyLedger._projection_drift(it, its)]
            orphan_items = {k for k in item_rows if k not in {i.id for i in all_items}}
            for k in orphan_items:
                result['breaks'].append({'seq': None, 'id': None, 'reason': 'missing_item',
                                         'chain': 'item', 'evidence_item_id': str(k)})
            result['items'] = items

        statuses = CustodyLedger._signature_statuses(rows)
        sigs = {vc.SIG_VALID: 0, vc.SIG_INVALID: 0, vc.SIG_KEY_MISMATCH: 0, vc.SIG_UNSIGNED_LEGACY: 0}
        for st in statuses.values():
            sigs[st] = sigs.get(st, 0) + 1
        result['signatures'] = sigs
        result['signature_status_by_id'] = {str(k): v for k, v in statuses.items()}
        result['status'] = vc.overall_status(result['breaks'], sigs)

        anchors = CustodyAnchor.query.filter_by(incident_id=incident_id).order_by(CustodyAnchor.created_at).all()
        inc_head = CustodyLedger.heads(incident_id)['incident'] if anchors else None
        result['anchors'] = [dict(a.to_dict(), covers_current_head=bool(
            inc_head and a.status == 'granted' and a.incident_seq == inc_head['seq']
            and a.head_hash == inc_head['hash'])) for a in anchors]

        if legacy['count']:
            first_v3 = min((r.created_at for r in chained), default=None)
            when = _iso(first_v3) if first_v3 else 'now'
            result['notes'].append(
                f"{legacy['count']} legacy entr{'y' if legacy['count'] == 1 else 'ies'} recorded before {when} "
                'were not hash-chained; they are sealed by the first chained entry, but tampering before '
                'the upgrade cannot be detected.')
        return result

    @staticmethod
    def chain_summary(item) -> dict:
        v = CustodyLedger.verify(item=item)
        return {'status': v['status'], 'head_seq': v['item_chain']['head_seq'],
                'head_hash': v['item_chain']['head_hash']}


# ── Registrations (evidence_refs §1 #10, realtime §1 #14) ────────────────────

def _evidence_label(item):
    return f'{item.evidence_number} {item.title}'


def _serialize_evidence_item(item):
    data = item.to_dict()
    data.pop('extra_data', None)
    return data


_CUSTODY_PRIVATE_FIELDS = ('ip_address', 'user_agent', 'signature', 'signature_key_id')


def _serialize_custody_entry(entry):
    data = entry.to_dict()
    for key in _CUSTODY_PRIVATE_FIELDS:
        data.pop(key, None)
    return data


def _register():
    from app.services import realtime
    from app.services.evidence_refs import register_ref_type
    register_ref_type('evidence_item', EvidenceItem, label=_evidence_label, permission='artifacts:read')
    realtime.register_entity('evidence_item', 'artifacts', 'artifacts:read', _serialize_evidence_item)
    realtime.register_entity('custody_entry', 'artifacts', 'artifacts:read', _serialize_custody_entry)


_register()
