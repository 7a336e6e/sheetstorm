"""Decision & response-action log service (W4-DEC; decision-log plan §3.4).

The only writer of ``incident_decisions``, ``response_actions`` and
``decision_log_revisions``. Every change of a head row appends one revision
in the same transaction: full snapshot, ``{field: {from, to}}`` diff
(``utils/audit_diff``), reason, actor. Revisions are chained per record with
``utils/hash_chain`` (domain ``decision-v1``) and HMAC-signed with the custody
signing key (same key + key-id scheme as the custody ledger), so altering,
removing or reordering a revision is detectable by :func:`verify_record`.

Concurrency: :func:`lock` takes ``pg_advisory_xact_lock('decision:<incident>')``
before the head row is loaded, which serialises numbering and revision
appends; the head rows also carry ``version`` (If-Match, C8).

Privileged decisions (``is_privileged``) are visible only with
``decisions:read_privileged``. Every read helper here filters them, sockets
send them only to scope ``decisions_privileged`` (C9), and nothing in this
module is ever passed to ``ai_service`` (§1 #22b).

Functions run inside the caller's transaction and flush; callers commit.
"""
from __future__ import annotations

import hmac
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app import db
from app.models import DecisionLogRevision, IncidentDecision, ResponseAction, User
from app.models.artifact import custody_key_id, custody_signing_key
from app.models.decision_log import (
    ACTION_STATUSES, ACTION_TYPES, DECISION_CATEGORIES, DECISION_STATUSES, TARGET_TYPES, VERIFICATION_RESULTS,
)
from app.utils.audit_diff import audit_changes
from app.utils.hash_chain import (
    advisory_xact_lock, canonical_json, genesis_hash, hmac_hex, link_hash, verify_linear_chain,
)
from app.utils.validation import parse_datetime

DOMAIN = 'decision-v1'
PAYLOAD_VERSION = 1
SIGNATURE_PREFIX = b'sheetstorm-decision-v1:'

PRIVILEGED_PERM = 'decisions:read_privileged'
MAX_ALTERNATIVES = 20
MAX_TEXT = 20000
MAX_NAME = 255
# Retroactive times may be in the past only (clock-skew slack).
_FUTURE_SLACK = timedelta(minutes=5)

SIG_VALID = 'valid'
SIG_INVALID = 'invalid'
SIG_KEY_MISMATCH = 'key_mismatch'

# Columns excluded from the revision diff (bookkeeping, always changes).
_DIFF_IGNORE = ('version', 'updated_at', 'updated_by')

__all__ = [
    'DecisionLogError', 'lock', 'can_read_privileged', 'decisions_query', 'get_decision', 'get_action',
    'create_decision', 'update_decision', 'approve_decision', 'reject_decision', 'reopen_decision',
    'supersede_decision', 'create_action', 'update_action', 'transition_action', 'revisions',
    'verify_record', 'export_payload', 'virtual_timeline',
]


class DecisionLogError(Exception):
    """A request the decision log refuses (status + machine-readable code)."""

    def __init__(self, message, *, code='bad_request', status=400, details=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.details = details or {}

    def to_dict(self):
        return {'error': self.code, 'message': self.message, **self.details}

    def to_response(self):
        from flask import jsonify
        return jsonify(self.to_dict()), self.status


def _bad(message, code='bad_request', **details):
    return DecisionLogError(message, code=code, status=400, details=details)


def _forbidden(message, permission=None):
    details = {'required': permission} if permission else {}
    return DecisionLogError(message, code='forbidden', status=403, details=details)


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


def _canon(value):
    """Strict-JSON-safe value (uuid/datetime -> str; floats are not stored)."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    return str(value)


def snapshot(record) -> dict:
    """Every column of a head row, canonical (what a revision stores)."""
    return {c.name: _canon(getattr(record, c.name)) for c in record.__table__.columns}


def record_type_of(record) -> str:
    return 'decision' if isinstance(record, IncidentDecision) else 'response_action'


def lock(incident_id) -> None:
    """Serialise decision-log writes of one incident (released at COMMIT/ROLLBACK)."""
    advisory_xact_lock(db.session, f'decision:{incident_id}')


def _single_flush(fn):
    """Run a mutation without autoflush: a lookup made half-way through
    (links, targets) would otherwise flush the head row early and bump its
    ``version`` twice for one change. ``append_revision`` flushes explicitly."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with db.session.no_autoflush:
            return fn(*args, **kwargs)
    return wrapper


def can_read_privileged(user) -> bool:
    return bool(user is not None and user.has_permission(PRIVILEGED_PERM))


# ── Revision chain ──────────────────────────────────────────────────────────

def _get(row, name):
    return row.get(name) if isinstance(row, dict) else getattr(row, name, None)


def revision_payload(rev) -> dict:
    """The hashed payload of one revision (every immutable field)."""
    return {
        'v': PAYLOAD_VERSION,
        'id': _canon(_get(rev, 'id')),
        'incident_id': _canon(_get(rev, 'incident_id')),
        'record_type': _get(rev, 'record_type'),
        'record_id': _canon(_get(rev, 'record_id')),
        'seq': _get(rev, 'seq'),
        'event': _get(rev, 'event'),
        'snapshot': _canon(_get(rev, 'snapshot')),
        'changes': _canon(_get(rev, 'changes') or {}),
        'reason': _get(rev, 'reason'),
        'actor_id': _canon(_get(rev, 'actor_id')),
        'actor_email': _get(rev, 'actor_email'),
        'is_privileged': bool(_get(rev, 'is_privileged')),
        'self_approved': bool(_get(rev, 'self_approved')),
        'created_at': _canon(_get(rev, 'created_at')),
    }


def payload_bytes(rev) -> bytes:
    return canonical_json(revision_payload(rev), strict=True)


def compute_entry_hash(rev) -> str:
    return link_hash(DOMAIN, _get(rev, 'prev_hash') or '', payload_bytes(rev))


def compute_signature(key, entry_hash) -> str:
    return hmac_hex(key, SIGNATURE_PREFIX + (entry_hash or '').encode('utf-8'))


def genesis(record_type, record_id) -> str:
    return genesis_hash(DOMAIN, record_type, str(record_id))


def signature_status(rev, secret) -> str:
    sig = _get(rev, 'signature')
    if not sig or not _get(rev, 'signature_key_id'):
        return SIG_INVALID
    if _get(rev, 'signature_key_id') != custody_key_id(secret):
        return SIG_KEY_MISMATCH
    try:
        expected = compute_signature(secret, compute_entry_hash(rev))
    except (TypeError, ValueError):
        return SIG_INVALID
    return SIG_VALID if hmac.compare_digest(str(sig), expected) else SIG_INVALID


def append_revision(record, event, *, actor, before, reason=None, self_approved=False):
    """Flush ``record`` and append its next revision (caller holds :func:`lock`)."""
    db.session.flush()
    rtype = record_type_of(record)
    after = snapshot(record)
    changes = audit_changes({k: v for k, v in (before or {}).items() if k not in _DIFF_IGNORE},
                            {k: v for k, v in after.items() if k not in _DIFF_IGNORE})
    last = (DecisionLogRevision.query.with_entities(DecisionLogRevision.seq, DecisionLogRevision.entry_hash)
            .filter_by(record_type=rtype, record_id=record.id)
            .order_by(DecisionLogRevision.seq.desc()).first())
    rev = DecisionLogRevision(
        id=uuid.uuid4(), created_at=_now(), incident_id=record.incident_id, record_type=rtype,
        record_id=record.id, seq=(last[0] + 1) if last else 1, event=event, snapshot=after,
        changes=_canon(changes), reason=reason,
        actor_id=getattr(actor, 'id', None), actor_email=getattr(actor, 'email', None),
        is_privileged=bool(getattr(record, 'is_privileged', False)), self_approved=bool(self_approved),
        prev_hash=last[1] if last else genesis(rtype, record.id),
    )
    rev.entry_hash = compute_entry_hash(rev)
    secret = custody_signing_key()
    rev.signature = compute_signature(secret, rev.entry_hash)
    rev.signature_key_id = custody_key_id(secret)
    db.session.add(rev)
    db.session.flush()
    return rev


def revisions(record):
    return (DecisionLogRevision.query.filter_by(record_type=record_type_of(record), record_id=record.id)
            .order_by(DecisionLogRevision.seq).all())


def verify_record(record, rows=None) -> dict:
    """Verify one record's revision chain, signatures and head projection.

    ``status``: intact | unverifiable (signed with another key) | broken
    (missing / reordered / altered links, or the head row no longer matches
    its last revision) | compromised (a signature does not match).
    """
    rtype = record_type_of(record)
    rows = revisions(record) if rows is None else rows
    failures = verify_linear_chain(rows, DOMAIN, genesis(rtype, record.id), 'prev_hash', payload_bytes,
                                   hash_attr='entry_hash', seq_attr='seq', ts_attr='created_at', start_seq=1)
    breaks = [f for f in failures if f['reason'] != 'timestamp_regression']
    warnings = [f for f in failures if f['reason'] == 'timestamp_regression']
    if not rows:
        breaks.append({'seq': None, 'id': None, 'reason': 'no_revisions'})
    elif _canon(rows[-1].snapshot) != snapshot(record):
        breaks.append({'seq': rows[-1].seq, 'id': str(rows[-1].id), 'reason': 'head_drift'})
    secret = custody_signing_key()
    by_id = {str(r.id): signature_status(r, secret) for r in rows}
    counts = {SIG_VALID: 0, SIG_INVALID: 0, SIG_KEY_MISMATCH: 0}
    for st in by_id.values():
        counts[st] += 1
    if counts[SIG_INVALID]:
        status = 'compromised'
    elif breaks:
        status = 'broken'
    elif counts[SIG_KEY_MISMATCH]:
        status = 'unverifiable'
    else:
        status = 'intact'
    return {'status': status, 'length': len(rows), 'breaks': breaks, 'warnings': warnings,
            'signatures': counts, 'signature_status_by_id': by_id,
            'head_hash': rows[-1].entry_hash if rows else None,
            'signing_key_id': custody_key_id(secret)}


# ── Reads (privileged filter in one place) ──────────────────────────────────

def decisions_query(incident_id, user):
    """Decisions of an incident the user may see (privileged filtered)."""
    q = IncidentDecision.query.filter(IncidentDecision.incident_id == incident_id)
    if not can_read_privileged(user):
        q = q.filter(IncidentDecision.is_privileged.is_(False))
    return q


def get_decision(incident_id, decision_id, user):
    """The decision, or None when absent or privileged-and-hidden (404, no leak)."""
    return decisions_query(incident_id, user).filter(IncidentDecision.id == decision_id).first()


def actions_query(incident_id):
    return ResponseAction.query.filter(ResponseAction.incident_id == incident_id)


def get_action(incident_id, action_id):
    return actions_query(incident_id).filter(ResponseAction.id == action_id).first()


def _hidden_decision_ids(incident_id, ids, user):
    """Ids among ``ids`` that are privileged decisions the user may not read."""
    ids = [i for i in ids if i]
    if not ids or can_read_privileged(user):
        return set()
    rows = (db.session.query(IncidentDecision.id)
            .filter(IncidentDecision.incident_id == incident_id, IncidentDecision.id.in_(ids),
                    IncidentDecision.is_privileged.is_(True)).all())
    return {r[0] for r in rows}


# ── Field validation ────────────────────────────────────────────────────────

def _text(data, key, *, max_len=MAX_TEXT, required=False, allow_empty=False):
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip() and not allow_empty):
        if required:
            raise _bad(f'{key} is required', 'validation_error', field=key)
        return None
    if not isinstance(value, str):
        raise _bad(f'{key} must be a string', 'validation_error', field=key)
    if '\x00' in value:
        raise _bad(f'{key} contains a NUL character', 'validation_error', field=key)
    value = value.strip()
    if len(value) > max_len:
        raise _bad(f'{key} must be at most {max_len} characters', 'validation_error', field=key)
    return value


def _choice(data, key, choices, *, required=False, default=None):
    value = data.get(key, default)
    if value is None:
        if required:
            raise _bad(f'{key} is required', 'validation_error', field=key)
        return None
    if value not in choices:
        raise _bad(f'Invalid {key}; allowed: {", ".join(choices)}', 'validation_error', field=key)
    return value


def _when(data, key, default=None):
    value = parse_datetime(data.get(key), key)
    if value is None:
        return default
    if value > _now() + _FUTURE_SLACK:
        raise _bad(f'{key} cannot be in the future', 'validation_error', field=key)
    return value


def _uuid(value, key):
    if value in (None, ''):
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise _bad(f'{key} must be a UUID', 'validation_error', field=key)


def _bool(data, key, default=False):
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise _bad(f'{key} must be true or false', 'validation_error', field=key)
    return value


def _reason(data, *, required=True):
    return _text(data, 'reason', max_len=2000, required=required)


def _alternatives(value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_ALTERNATIVES:
        raise _bad(f'alternatives must be a list of at most {MAX_ALTERNATIVES} items', 'validation_error',
                   field='alternatives')
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise _bad('each alternative must be {option, reason_not_chosen}', 'validation_error',
                       field='alternatives')
        option = _text(item, 'option', max_len=1000, required=True)
        reason = _text(item, 'reason_not_chosen', max_len=4000)
        out.append({'option': option, 'reason_not_chosen': reason})
    return out


def _links(incident_id, value, user):
    """Validated ``[{evidence_type, evidence_id}]`` (evidence_refs registry);
    a privileged decision the user cannot read is reported as not found."""
    from app.services.evidence_refs import EvidenceRefsError, validate_refs
    refs = validate_refs(incident_id, value if value is not None else [], max_refs=50)
    hidden = _hidden_decision_ids(incident_id, [uuid.UUID(r['evidence_id']) for r in refs
                                                if r['evidence_type'] == 'decision'], user)
    if hidden:
        raise EvidenceRefsError('Invalid evidence references', [
            {'index': i, 'evidence_type': 'decision', 'evidence_id': r['evidence_id'], 'reason': 'not_found'}
            for i, r in enumerate(refs) if r['evidence_type'] == 'decision'
            and uuid.UUID(r['evidence_id']) in hidden])
    return refs


def _actor_or_name(data, name_key, user):
    """Attestation rule: an in-app ``*_by_user_id`` is only ever the acting
    user; anyone else is recorded as ``*_by_name`` text."""
    name = _text(data, name_key, max_len=MAX_NAME)
    return (None, name) if name else (user.id, None)


def _next_number(model, incident_id):
    current = db.session.query(func.max(model.number)).filter(model.incident_id == incident_id).scalar()
    return (current or 0) + 1


def _invalid_transition(record, event):
    return DecisionLogError(f'Cannot {event} a {record.status} {record_type_of(record).replace("_", " ")}',
                            code='invalid_transition', status=409,
                            details={'from': record.status, 'event': event})


def _require(user, permission, what):
    if not user.has_permission(permission):
        raise _forbidden(f'{what} requires {permission}', permission)


# ── Decisions ───────────────────────────────────────────────────────────────

DECISION_EDITABLE = ('title', 'decision', 'rationale', 'alternatives', 'category', 'decided_at',
                     'decided_by_name', 'links', 'is_privileged')


@_single_flush
def create_decision(incident, user, data):
    """Record a decision. Retroactive logging: ``approved_by_name`` (+
    ``approved_at``) records an external approval; ``approve: true`` is an
    in-app approval by the actor and needs ``decisions:approve``."""
    lock(incident.id)
    is_priv = _bool(data, 'is_privileged')
    if is_priv and not can_read_privileged(user):
        raise _forbidden('Only users who can read privileged decisions can record one', PRIVILEGED_PERM)
    by_id, by_name = _actor_or_name(data, 'decided_by_name', user)
    d = IncidentDecision(
        id=uuid.uuid4(), incident_id=incident.id, number=_next_number(IncidentDecision, incident.id),
        title=_text(data, 'title', max_len=300, required=True),
        decision=_text(data, 'decision', required=True),
        rationale=_text(data, 'rationale'),
        alternatives=_alternatives(data.get('alternatives')),
        category=_choice(data, 'category', DECISION_CATEGORIES, default='other'),
        status='proposed', is_privileged=is_priv,
        decided_at=_when(data, 'decided_at', _now()), decided_by_user_id=by_id, decided_by_name=by_name,
        links=_links(incident.id, data.get('links'), user),
        created_by=user.id, updated_by=user.id,
    )
    self_approved = False
    approved_by_name = _text(data, 'approved_by_name', max_len=MAX_NAME)
    if approved_by_name:
        d.status, d.approved_by_name = 'approved', approved_by_name
        d.approved_at = _when(data, 'approved_at', d.decided_at)
    elif _bool(data, 'approve'):
        _require(user, 'decisions:approve', 'Approving a decision')
        d.status, d.approved_by_user_id, d.approved_at = 'approved', user.id, _now()
        self_approved = True
    d.self_approved = self_approved
    db.session.add(d)
    append_revision(d, 'create', actor=user, before={}, reason=_reason(data, required=False),
                    self_approved=self_approved)
    return d


@_single_flush
def update_decision(decision, user, data):
    """Edit descriptive fields (status only moves through transitions).
    ``reason`` is required; a no-op edit is 400 ``no_changes``."""
    reason = _reason(data)
    before = snapshot(decision)
    if 'title' in data:
        decision.title = _text(data, 'title', max_len=300, required=True)
    if 'decision' in data:
        decision.decision = _text(data, 'decision', required=True)
    if 'rationale' in data:
        decision.rationale = _text(data, 'rationale')
    if 'alternatives' in data:
        decision.alternatives = _alternatives(data.get('alternatives'))
    if 'category' in data:
        decision.category = _choice(data, 'category', DECISION_CATEGORIES, required=True)
    if 'decided_at' in data:
        decision.decided_at = _when(data, 'decided_at') or decision.decided_at
    if data.get('decided_by_name'):
        decision.decided_by_user_id, decision.decided_by_name = None, _text(data, 'decided_by_name',
                                                                            max_len=MAX_NAME)
    if 'links' in data:
        decision.links = _links(decision.incident_id, data.get('links'), user)
    if 'is_privileged' in data:
        flag = _bool(data, 'is_privileged')
        if flag != decision.is_privileged and not can_read_privileged(user):
            raise _forbidden('Changing the privileged flag requires decisions:read_privileged', PRIVILEGED_PERM)
        decision.is_privileged = flag
    if snapshot(decision) == before:
        raise _bad('Nothing to change', 'no_changes')
    decision.updated_by = user.id
    return append_revision(decision, 'update', actor=user, before=before, reason=reason)


@_single_flush
def approve_decision(decision, user, data):
    """proposed -> approved. In-app approval (the actor) needs
    ``decisions:approve``; an external ``approved_by_name`` attestation needs
    only ``decisions:update``."""
    if decision.status != 'proposed':
        raise _invalid_transition(decision, 'approve')
    before = snapshot(decision)
    name = _text(data, 'approved_by_name', max_len=MAX_NAME)
    self_approved = False
    if name:
        _require(user, 'decisions:update', 'Recording an external approval')
        decision.approved_by_user_id, decision.approved_by_name = None, name
        decision.approved_at = _when(data, 'approved_at', _now())
    else:
        _require(user, 'decisions:approve', 'Approving a decision')
        decision.approved_by_user_id, decision.approved_by_name, decision.approved_at = user.id, None, _now()
        self_approved = user.id in (decision.created_by, decision.decided_by_user_id)
    reason = _reason(data, required=False)
    decision.status, decision.status_reason, decision.self_approved = 'approved', reason, self_approved
    decision.updated_by = user.id
    return append_revision(decision, 'approve', actor=user, before=before, reason=reason,
                           self_approved=self_approved)


@_single_flush
def reject_decision(decision, user, data):
    """proposed -> rejected (``decisions:approve``; reason required)."""
    _require(user, 'decisions:approve', 'Rejecting a decision')
    if decision.status != 'proposed':
        raise _invalid_transition(decision, 'reject')
    reason = _reason(data)
    before = snapshot(decision)
    decision.status, decision.status_reason, decision.updated_by = 'rejected', reason, user.id
    return append_revision(decision, 'reject', actor=user, before=before, reason=reason)


@_single_flush
def reopen_decision(decision, user, data):
    """rejected -> proposed (``decisions:update``; reason required)."""
    if decision.status != 'rejected':
        raise _invalid_transition(decision, 'reopen')
    reason = _reason(data)
    before = snapshot(decision)
    decision.status, decision.status_reason, decision.updated_by = 'proposed', reason, user.id
    return append_revision(decision, 'reopen', actor=user, before=before, reason=reason)


@_single_flush
def supersede_decision(decision, user, data):
    """proposed|approved -> superseded by another decision of the incident."""
    if decision.status not in ('proposed', 'approved'):
        raise _invalid_transition(decision, 'supersede')
    target_id = _uuid(data.get('superseded_by_id'), 'superseded_by_id')
    if target_id is None:
        raise _bad('superseded_by_id is required', 'validation_error', field='superseded_by_id')
    if target_id == decision.id:
        raise _bad('A decision cannot supersede itself', 'validation_error', field='superseded_by_id')
    if get_decision(decision.incident_id, target_id, user) is None:
        raise _bad('superseded_by_id must be a decision of this incident', 'validation_error',
                   field='superseded_by_id')
    reason = _reason(data, required=False)
    before = snapshot(decision)
    decision.status, decision.superseded_by_id = 'superseded', target_id
    decision.status_reason, decision.updated_by = reason, user.id
    return append_revision(decision, 'supersede', actor=user, before=before, reason=reason)


# ── Response actions ────────────────────────────────────────────────────────

def _target_models():
    from app.models import CompromisedAccount, CompromisedHost, HostBasedIndicator, MalwareTool, NetworkIndicator
    return {'host': CompromisedHost, 'account': CompromisedAccount, 'network_ioc': NetworkIndicator,
            'host_ioc': HostBasedIndicator, 'malware': MalwareTool}


def _resolve_target(incident_id, target_type, target_id):
    """The target row (same incident) or None for external/none targets."""
    models = _target_models()
    if target_type not in models:
        if target_id is not None:
            raise _bad(f'target_id is not allowed for target_type {target_type}', 'validation_error',
                       field='target_id')
        return None
    if target_id is None:
        raise _bad(f'target_id is required for target_type {target_type}', 'validation_error', field='target_id')
    obj = models[target_type].query.filter_by(id=target_id, incident_id=incident_id).first()
    if obj is None:
        raise _bad('target_id must be a record of this incident', 'validation_error', field='target_id')
    return obj


def _target_label(target_type, obj):
    from app.services.evidence_refs import ref_types
    rt = ref_types().get(target_type)
    return rt.label_for(obj)[:500] if rt is not None else None


def _decision_ref(incident_id, value, user):
    did = _uuid(value, 'decision_id')
    if did is not None and get_decision(incident_id, did, user) is None:
        raise _bad('decision_id must be a decision of this incident', 'validation_error', field='decision_id')
    return did


# Target-state changes applied on execute (US-2): action_type -> (target_type, value).
TARGET_STATE_MAP = {
    'isolate_host': ('host', 'isolated'),
    'contain_host': ('host', 'contained'),
    'reimage_host': ('host', 'reimaged'),
    'decommission_host': ('host', 'decommissioned'),
    'release_host': ('host', None),          # target_state required
    'disable_account': ('account', 'disabled'),
    'reset_credentials': ('account', 'reset'),
    'delete_account': ('account', 'deleted'),
}
_STATE_FIELD = {'host': ('containment_status', 'hosts:update'), 'account': ('status', 'accounts:update')}


@_single_flush
def create_action(incident, user, data):
    """Record a response action. Retroactive logging: later-stage fields
    (``authorized_by_name``, ``executed_at``, ``verified_at`` + result) set
    the status to the furthest stage with complete data; one ``create``
    revision. Target-state changes are never applied on create."""
    lock(incident.id)
    action_type = _choice(data, 'action_type', ACTION_TYPES, required=True)
    target_type = _choice(data, 'target_type', TARGET_TYPES, default='none')
    target_id = _uuid(data.get('target_id'), 'target_id')
    target = _resolve_target(incident.id, target_type, target_id)
    label = _text(data, 'target_label', max_len=500)
    if target is not None:
        label = _target_label(target_type, target)
    a = ResponseAction(
        id=uuid.uuid4(), incident_id=incident.id, number=_next_number(ResponseAction, incident.id),
        action_type=action_type, title=_text(data, 'title', max_len=300, required=True),
        description=_text(data, 'description'), target_type=target_type, target_id=target_id,
        target_label=label, decision_id=_decision_ref(incident.id, data.get('decision_id'), user),
        status='requested', requested_by_user_id=user.id, requested_at=_when(data, 'requested_at', _now()),
        rollback_plan=_text(data, 'rollback_plan'), links=_links(incident.id, data.get('links'), user),
        created_by=user.id, updated_by=user.id,
    )
    auth_name = _text(data, 'authorized_by_name', max_len=MAX_NAME)
    if auth_name:
        a.status, a.authorized_by_name = 'authorized', auth_name
        a.authorized_at = _when(data, 'authorized_at', a.requested_at)
    executed_at = _when(data, 'executed_at')
    if executed_at is not None:
        a.status, a.executed_at = 'executed', executed_at
        a.executed_by_user_id, a.executed_by_name = _actor_or_name(data, 'executed_by_name', user)
        verified_at = _when(data, 'verified_at')
        if verified_at is not None:
            a.verification_result = _choice(data, 'verification_result', VERIFICATION_RESULTS, required=True)
            a.verification_method = _text(data, 'verification_method', max_len=255)
            a.verification_notes = _text(data, 'verification_notes')
            a.verified_at, a.status = verified_at, 'verified'
            a.verified_by_user_id, a.verified_by_name = _actor_or_name(data, 'verified_by_name', user)
            a.self_verified = bool(a.verified_by_user_id and a.verified_by_user_id == a.executed_by_user_id)
    db.session.add(a)
    append_revision(a, 'create', actor=user, before={}, reason=_reason(data, required=False))
    return a


@_single_flush
def update_action(action, user, data):
    """Edit descriptive fields (title, description, rollback_plan,
    target_label for external targets, decision_id, links); reason required."""
    reason = _reason(data)
    before = snapshot(action)
    if 'title' in data:
        action.title = _text(data, 'title', max_len=300, required=True)
    if 'description' in data:
        action.description = _text(data, 'description')
    if 'rollback_plan' in data:
        action.rollback_plan = _text(data, 'rollback_plan')
    if 'target_label' in data and action.target_type in ('external', 'none'):
        action.target_label = _text(data, 'target_label', max_len=500)
    if 'decision_id' in data:
        action.decision_id = _decision_ref(action.incident_id, data.get('decision_id'), user)
    if 'links' in data:
        action.links = _links(action.incident_id, data.get('links'), user)
    if snapshot(action) == before:
        raise _bad('Nothing to change', 'no_changes')
    action.updated_by = user.id
    return append_revision(action, 'update', actor=user, before=before, reason=reason)


# event -> (allowed from-states, to-state, reason required)
ACTION_TRANSITIONS = {
    'authorize': (('requested', 'failed'), 'authorized', False),
    'start': (('authorized',), 'in_progress', False),
    'execute': (('authorized', 'in_progress'), 'executed', False),
    'fail': (('in_progress', 'executed'), 'failed', True),
    'verify': (('executed',), 'verified', False),
    'rollback': (('executed', 'verified'), 'rolled_back', True),
    'cancel': (('requested', 'authorized', 'in_progress'), 'cancelled', True),
}


def _state_target(action, user):
    """(target row, field) for a target-state change; checks the permission."""
    mapped = TARGET_STATE_MAP.get(action.action_type)
    if mapped is None or action.target_type != mapped[0] or action.target_id is None:
        raise _bad(f'{action.action_type} on a {action.target_type} target cannot change a target state',
                   'target_state_not_applicable')
    field, perm = _STATE_FIELD[mapped[0]]
    _require(user, perm, 'Changing the target state')
    target = _target_models()[mapped[0]].query.filter_by(id=action.target_id,
                                                          incident_id=action.incident_id).first()
    if target is None:
        raise DecisionLogError('The target no longer exists', code='target_missing', status=409)
    return target, field


def _apply_target_state(action, user, data, side_effects):
    target, field = _state_target(action, user)
    model = type(target)
    allowed = getattr(model, 'CONTAINMENT_STATUSES', None) or getattr(model, 'STATUSES')
    value = data.get('target_state') or TARGET_STATE_MAP[action.action_type][1]
    if value is None:
        raise _bad('target_state is required for this action', 'validation_error', field='target_state')
    if value not in allowed:
        raise _bad(f'Invalid target_state; allowed: {", ".join(allowed)}', 'validation_error', field='target_state')
    old = getattr(target, field)
    setattr(target, field, value)
    action.target_state_before = {'field': field, 'value': old}
    action.target_state_after = {'field': field, 'value': value}
    side_effects.append({'target': target, 'target_type': action.target_type, 'field': field,
                         'old': old, 'new': value})


def _restore_target_state(action, user, side_effects):
    after, before = action.target_state_after or {}, action.target_state_before or {}
    if not after or not before:
        return
    target, field = _state_target(action, user)
    current = getattr(target, field)
    if current != after.get('value'):
        raise DecisionLogError('The target changed since this action was executed; roll back with '
                               'restore_target_state=false or update the target first',
                               code='target_state_changed', status=409,
                               details={'current': current, 'expected': after.get('value')})
    setattr(target, field, before.get('value'))
    side_effects.append({'target': target, 'target_type': action.target_type, 'field': field,
                         'old': current, 'new': before.get('value')})


@_single_flush
def transition_action(action, user, event, data):
    """Move an action through its state machine (409 ``invalid_transition``).

    Returns ``(revision, side_effects)``; side effects are target-state
    changes the caller audits and emits after commit. Permissions: in-app
    ``authorize`` needs ``response_actions:authorize`` (an external
    ``authorized_by_name`` needs ``response_actions:update``); every other
    event needs ``response_actions:update``; target-state changes also need
    ``hosts:update`` / ``accounts:update``.
    """
    if event not in ACTION_TRANSITIONS:
        raise _bad(f'Unknown action event {event}')
    sources, target_status, reason_required = ACTION_TRANSITIONS[event]
    if event != 'authorize':
        _require(user, 'response_actions:update', 'Updating a response action')
    if action.status not in sources:
        raise _invalid_transition(action, event)
    retry = event == 'authorize' and action.status == 'failed'
    reason = _reason(data, required=reason_required or retry)
    before = snapshot(action)
    side_effects = []
    self_approved = False

    if event == 'authorize':
        name = _text(data, 'authorized_by_name', max_len=MAX_NAME)
        if name:
            _require(user, 'response_actions:update', 'Recording an external authorization')
            action.authorized_by_user_id, action.authorized_by_name = None, name
            action.authorized_at = _when(data, 'authorized_at', _now())
        else:
            _require(user, 'response_actions:authorize', 'Authorizing a response action')
            action.authorized_by_user_id, action.authorized_by_name, action.authorized_at = user.id, None, _now()
            self_approved = user.id in (action.requested_by_user_id, action.created_by)
        action.self_approved = self_approved
    elif event == 'execute':
        action.executed_at = _when(data, 'executed_at', _now())
        action.executed_by_user_id, action.executed_by_name = _actor_or_name(data, 'executed_by_name', user)
        if _bool(data, 'apply_target_state'):
            _apply_target_state(action, user, data, side_effects)
    elif event == 'verify':
        action.verification_result = _choice(data, 'verification_result', VERIFICATION_RESULTS, required=True)
        action.verification_method = _text(data, 'verification_method', max_len=255, required=True)
        action.verification_notes = _text(data, 'verification_notes')
        action.verified_at = _when(data, 'verified_at', _now())
        action.verified_by_user_id, action.verified_by_name = _actor_or_name(data, 'verified_by_name', user)
        action.self_verified = bool(action.verified_by_user_id
                                    and action.verified_by_user_id == action.executed_by_user_id)
    elif event == 'rollback':
        if _bool(data, 'restore_target_state', default=bool(action.target_state_after)):
            _restore_target_state(action, user, side_effects)
        action.rolled_back_at, action.rolled_back_by_user_id = _now(), user.id
        action.rollback_reason = reason

    action.status, action.status_reason, action.updated_by = target_status, reason, user.id
    rev = append_revision(action, 'retry' if retry else event, actor=user, before=before, reason=reason,
                          self_approved=self_approved)
    return rev, side_effects


# ── Serialization ───────────────────────────────────────────────────────────

DECISION_USER_FIELDS = ('decided_by_user_id', 'approved_by_user_id', 'created_by', 'updated_by')
ACTION_USER_FIELDS = ('requested_by_user_id', 'authorized_by_user_id', 'executed_by_user_id',
                      'verified_by_user_id', 'rolled_back_by_user_id', 'created_by', 'updated_by')


def base_dict(record) -> dict:
    """Columns + display id (no names, no resolved labels): socket payloads."""
    data = snapshot(record)
    data['display_id'] = record.display_id
    data['record_type'] = record_type_of(record)
    return data


def _users_by_id(ids):
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: {'id': str(u.id), 'name': u.name}
            for u in User.query.with_entities(User.id, User.name).filter(User.id.in_(ids)).all()}


def _revision_counts(record_type, ids):
    if not ids:
        return {}
    rows = (db.session.query(DecisionLogRevision.record_id, func.count(DecisionLogRevision.id))
            .filter(DecisionLogRevision.record_type == record_type, DecisionLogRevision.record_id.in_(ids))
            .group_by(DecisionLogRevision.record_id).all())
    return dict(rows)


def _with_users(data, record, fields, users):
    data['users'] = {f: users.get(getattr(record, f)) for f in fields}
    return data


def serialize_decisions(rows, user, *, resolve_links=True) -> list:
    from app.services.evidence_refs import resolve_refs
    rows = list(rows)
    users = _users_by_id(getattr(d, f) for d in rows for f in DECISION_USER_FIELDS)
    counts = _revision_counts('decision', [d.id for d in rows])
    successors = {d.id: d for d in IncidentDecision.query.filter(
        IncidentDecision.id.in_([d.superseded_by_id for d in rows if d.superseded_by_id])).all()} \
        if any(d.superseded_by_id for d in rows) else {}
    out = []
    for d in rows:
        data = _with_users(base_dict(d), d, DECISION_USER_FIELDS, users)
        data['revision_count'] = counts.get(d.id, 0)
        nxt = successors.get(d.superseded_by_id)
        if nxt is not None and (not nxt.is_privileged or can_read_privileged(user)):
            data['superseded_by'] = {'id': str(nxt.id), 'display_id': nxt.display_id, 'title': nxt.title}
        else:
            data['superseded_by'] = None
            data['superseded_by_id'] = None if nxt is not None else data['superseded_by_id']
        if resolve_links:
            data['links'] = resolve_refs(d.incident_id, d.links or [], user=user)
        out.append(data)
    return out


def serialize_actions(rows, user, *, resolve_links=True) -> list:
    from app.services.evidence_refs import resolve_refs
    rows = list(rows)
    users = _users_by_id(getattr(a, f) for a in rows for f in ACTION_USER_FIELDS)
    counts = _revision_counts('response_action', [a.id for a in rows])
    dids = [a.decision_id for a in rows if a.decision_id]
    decisions = {d.id: d for d in IncidentDecision.query.filter(IncidentDecision.id.in_(dids)).all()} if dids else {}
    privileged_ok = can_read_privileged(user)
    out = []
    for a in rows:
        data = _with_users(base_dict(a), a, ACTION_USER_FIELDS, users)
        data['revision_count'] = counts.get(a.id, 0)
        dec = decisions.get(a.decision_id)
        if dec is not None and dec.is_privileged and not privileged_ok:
            data['decision_id'], data['decision'] = None, None
            data['decision_restricted'] = True
        else:
            data['decision'] = ({'id': str(dec.id), 'display_id': dec.display_id, 'title': dec.title,
                                 'status': dec.status} if dec is not None else None)
        if resolve_links:
            data['links'] = resolve_refs(a.incident_id, a.links or [], user=user)
        out.append(data)
    return out


def serialize_revisions(rows, record) -> list:
    status = verify_record(record, rows)
    out = []
    for r in rows:
        data = {c.name: _canon(getattr(r, c.name)) for c in r.__table__.columns}
        data['signature_status'] = status['signature_status_by_id'].get(str(r.id))
        out.append(data)
    return out


def _socket_action(action):
    """Socket payload of a response action: never the id of a privileged decision."""
    data = base_dict(action)
    if action.decision_id is not None:
        dec = db.session.get(IncidentDecision, action.decision_id)
        if dec is not None and dec.is_privileged:
            data['decision_id'] = None
            data['decision_restricted'] = True
    return data


# ── Exports / timeline / report appendix ────────────────────────────────────

EXPORT_KINDS = ('decisions', 'actions', 'all')
CSV_COLUMNS = (
    'record_type', 'display_id', 'title', 'status', 'category', 'action_type', 'target', 'decision',
    'rationale', 'decided_at', 'decided_by', 'approved_by', 'approved_at', 'requested_at', 'requested_by',
    'authorized_by', 'authorized_at', 'executed_by', 'executed_at', 'verified_by', 'verified_at',
    'verification_result', 'verification_method', 'rolled_back_at', 'rollback_reason', 'privileged',
    'self_approved', 'revisions', 'links',
)


def _who(data, user_field, name_field):
    user = (data.get('users') or {}).get(user_field)
    if user:
        return user['name']
    return data.get(name_field) or ''


def export_payload(incident, user, *, kind='all', include_privileged=False, include_revisions=False) -> dict:
    """Decisions + actions the user may read, for exports and the report
    appendix. Privileged decisions only with ``include_privileged`` AND
    ``decisions:read_privileged``. Never passed to ``ai_service``."""
    payload = {'incident': {'id': str(incident.id), 'incident_number': incident.incident_number,
                            'title': incident.title, 'tlp': incident.tlp},
               'generated_at': _iso(_now()),
               'generated_by': {'id': str(user.id), 'name': user.name} if user is not None else None,
               'decisions': [], 'response_actions': []}
    if kind in ('decisions', 'all') and user.has_permission('decisions:read'):
        q = IncidentDecision.query.filter(IncidentDecision.incident_id == incident.id)
        if not (include_privileged and can_read_privileged(user)):
            q = q.filter(IncidentDecision.is_privileged.is_(False))
        rows = q.order_by(IncidentDecision.number).all()
        payload['decisions'] = serialize_decisions(rows, user)
        if include_revisions:
            for data, row in zip(payload['decisions'], rows):
                data['revisions'] = serialize_revisions(revisions(row), row)
    if kind in ('actions', 'all') and user.has_permission('response_actions:read'):
        rows = actions_query(incident.id).order_by(ResponseAction.number).all()
        payload['response_actions'] = serialize_actions(rows, user)
        if include_revisions:
            for data, row in zip(payload['response_actions'], rows):
                data['revisions'] = serialize_revisions(revisions(row), row)
    return payload


def _link_text(links):
    return '; '.join(f"{l.get('evidence_type')}:{l.get('label') or l.get('evidence_id')}" for l in links or [])


def csv_rows(payload) -> list:
    rows = []
    for d in payload.get('decisions', []):
        rows.append({
            'record_type': 'decision', 'display_id': d['display_id'], 'title': d['title'], 'status': d['status'],
            'category': d['category'], 'decision': d['decision'], 'rationale': d.get('rationale') or '',
            'decided_at': d.get('decided_at'), 'decided_by': _who(d, 'decided_by_user_id', 'decided_by_name'),
            'approved_by': _who(d, 'approved_by_user_id', 'approved_by_name'), 'approved_at': d.get('approved_at'),
            'privileged': d.get('is_privileged'), 'self_approved': d.get('self_approved'),
            'revisions': d.get('revision_count'), 'links': _link_text(d.get('links')),
        })
    for a in payload.get('response_actions', []):
        rows.append({
            'record_type': 'response_action', 'display_id': a['display_id'], 'title': a['title'],
            'status': a['status'], 'action_type': a['action_type'],
            'target': f"{a['target_type']}: {a.get('target_label') or ''}".strip(),
            'decision': (a.get('decision') or {}).get('display_id') or '',
            'requested_at': a.get('requested_at'), 'requested_by': _who(a, 'requested_by_user_id', '-'),
            'authorized_by': _who(a, 'authorized_by_user_id', 'authorized_by_name'),
            'authorized_at': a.get('authorized_at'),
            'executed_by': _who(a, 'executed_by_user_id', 'executed_by_name'), 'executed_at': a.get('executed_at'),
            'verified_by': _who(a, 'verified_by_user_id', 'verified_by_name'), 'verified_at': a.get('verified_at'),
            'verification_result': a.get('verification_result'),
            'verification_method': a.get('verification_method'),
            'rolled_back_at': a.get('rolled_back_at'), 'rollback_reason': a.get('rollback_reason'),
            'self_approved': a.get('self_approved'), 'revisions': a.get('revision_count'),
            'links': _link_text(a.get('links')),
        })
    return rows


def to_csv(payload) -> str:
    """CSV of an export payload; every cell through ``csv_safe`` (CWE-1236)."""
    import csv
    import io
    from app.utils.csv_safe import csv_safe
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for row in csv_rows(payload):
        writer.writerow([csv_safe(row.get(c)) for c in CSV_COLUMNS])
    return buf.getvalue()


def virtual_timeline(incident, user) -> list:
    """Virtual timeline rows (``kind: response | decision``), never
    materialized as timeline events; privileged decisions filtered."""
    out = []
    if user.has_permission('response_actions:read'):
        for a in actions_query(incident.id).all():
            out.append({'kind': 'response', 'id': str(a.id), 'display_id': a.display_id,
                        'timestamp': _iso(a.executed_at or a.authorized_at or a.requested_at),
                        'activity': f'{a.action_type} {a.target_label or ""}'.strip(), 'title': a.title,
                        'status': a.status, 'target_type': a.target_type,
                        'host_id': str(a.target_id) if a.target_type == 'host' and a.target_id else None})
    if user.has_permission('decisions:read'):
        for d in decisions_query(incident.id, user).all():
            out.append({'kind': 'decision', 'id': str(d.id), 'display_id': d.display_id,
                        'timestamp': _iso(d.decided_at), 'activity': d.title, 'title': d.title,
                        'status': d.status, 'category': d.category, 'is_privileged': d.is_privileged})
    out.sort(key=lambda r: (r['timestamp'] or '', r['display_id']))
    return out


def links_contain_query(model, incident_id, refs):
    """Rows of ``model`` (decisions / actions) whose ``links`` cite any of
    ``refs`` (``[{evidence_type, evidence_id}]``); GIN ``jsonb_path_ops``."""
    from sqlalchemy import or_
    if not refs:
        return model.query.filter(False)
    return model.query.filter(model.incident_id == incident_id,
                              or_(*[model.links.contains([ref]) for ref in refs]))


# ── Realtime (C9) and registrations ─────────────────────────────────────────

def _entity(decision_privileged):
    return 'decision_privileged' if decision_privileged else 'decision'


def emit_decision(decision, op, *, was_privileged=None):
    """Emit after commit. A privileged decision goes ONLY to scope
    ``decisions_privileged`` (with data) and nothing reaches scope
    ``decisions``. When the flag flips, the old scope gets a ``deleted``
    first and the new scope a ``created``."""
    from app.services import realtime
    priv = bool(decision.is_privileged)
    if was_privileged is not None and bool(was_privileged) != priv:
        realtime.emit_change(decision.incident_id, _entity(bool(was_privileged)), 'deleted', id=decision.id)
        op = 'created'
    realtime.emit_change(decision.incident_id, _entity(priv), op, obj=decision)


def emit_action(action, op):
    from app.services import realtime
    realtime.emit_change(action.incident_id, 'response_action', op, obj=action)


def _decision_label(d):
    if d.is_privileged:
        return f'{d.display_id} [privileged]'
    return f'{d.display_id} {d.title}'


def _action_label(a):
    return f'{a.display_id} {a.title}'


def _register():
    from app.services import realtime
    from app.services.evidence_refs import register_ref_type
    register_ref_type('decision', IncidentDecision, label=_decision_label, permission='decisions:read')
    register_ref_type('response_action', ResponseAction, label=_action_label, permission='response_actions:read')
    realtime.register_entity('decision', 'decisions', 'decisions:read', base_dict)
    realtime.register_entity('decision_privileged', 'decisions_privileged', PRIVILEGED_PERM, base_dict)
    realtime.register_entity('response_action', 'response_actions', 'response_actions:read', _socket_action)


_register()
