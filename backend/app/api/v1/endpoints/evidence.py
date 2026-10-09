"""Evidence register API: items, custody workflow, verification, exports,
custody parties (evidence plan §3.6-3.7; integration §5 W2-EVD-API).

Base path ``/incidents/<incident_id>/evidence``; parties at ``/custody-parties``.
Every incident route goes through ``@require_incident_access`` (org-scoped
``g.incident`` + incident visibility); every lookup below it is scoped to that
incident or its organization, so a foreign id is a 404.

Permissions (one mapping, ``EVIDENCE_PERMS``; C29 reuses ``artifacts:*``):
    read    artifacts:read    list, detail, custody list, verify, single-item
                              custody export json/csv/pdf/form
    write   artifacts:upload  register, edit, add hash, verify hash, check out,
                              check in, transfer, acknowledge, create party
    manage  artifacts:delete  dispose, void, legal hold, edit/deactivate party
    export  incidents:export  ON TOP of read (C24): evidence register CSV/PDF/
                              bundle and the item custody bundle

Ledger writes go through ``CustodyLedger`` (one transaction per request);
realtime ``emit_change`` runs after the commit. Every chain verification
writes a ``custody_chain_verified`` audit row (``CustodyLedger.verify`` writes
nothing); a broken/compromised result is logged as a security event.
Optimistic concurrency: item mutations and party edits honour ``If-Match`` /
body ``expected_version`` (409 ``conflict``); responses carry ``ETag``.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import current_app, g, jsonify, request, send_file
from flask_jwt_extended import jwt_required
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from werkzeug.exceptions import BadRequest

from app import db, limiter
from app.api.v1 import api_bp
from app.middleware.audit import audit_log, log_audit_event, log_security_event
from app.middleware.rbac import (get_current_user, require_incident_access, require_permission,
                                 user_can_access_incident)
from app.models import (Artifact, ChainOfCustody, CompromisedHost, CustodyAnchor, CustodyParty, EvidenceItem,
                        User)
from app.models.evidence import (CUSTODY_STATES, EVIDENCE_TYPES, HASH_ALGORITHMS, HASH_SOURCES, PARTY_ROLES,
                                 TRANSFER_METHODS)
from app.services import evidence_export_service as exports
from app.services import realtime
from app.services.custody_ledger import DISPOSE_METHODS, CustodyError, CustodyLedger
from app.services.hash_service import HashService
from app.utils.audit_diff import record_changes, snapshot
from app.utils.concurrency import commit_or_conflict, precondition, set_etag
from app.utils.pagination import apply_filters, escape_like, paginate_response, parse_list_args
from app.utils.validation import parse_datetime

EVIDENCE_PERMS = {
    'read': 'artifacts:read',
    'write': 'artifacts:upload',
    'manage': 'artifacts:delete',
    'export': 'incidents:export',
}

BASE = '/incidents/<uuid:incident_id>/evidence'
ITEM = BASE + '/<uuid:evidence_item_id>'

TEXT_MAX = 20000
MAX_HASHES = 20
CLOCK_SLACK = timedelta(minutes=5)
FORM_BLANK_ROWS = (0, 20, 8)  # min, max, default
ITEM_EXPORT_FORMATS = ('json', 'csv', 'pdf', 'form', 'bundle')
REGISTER_EXPORT_FORMATS = ('csv', 'pdf', 'bundle')

# Descriptive string columns and their length caps (= column sizes).
ITEM_STR_FIELDS = {
    'title': 255, 'description': TEXT_MAX, 'condition_notes': TEXT_MAX, 'media_type': 120, 'make': 120,
    'model': 120, 'serial_number': 120, 'seal_number': 120, 'bag_number': 120, 'storage_location': 500,
    'acquired_by_name': 255, 'acquired_from': 500, 'acquisition_method': 100, 'acquisition_tool': 150,
    'acquisition_tool_version': 60, 'derivation_note': TEXT_MAX,
}
_REF_FIELDS = {'evidence_type', 'capacity_bytes', 'acquired_at', 'acquired_by_user_id', 'source_host_id'}
REGISTER_FIELDS = frozenset(ITEM_STR_FIELDS) | _REF_FIELDS | {'parent_id', 'acquisition_hashes'}
# Not patchable: acquisition_hashes (add_hash), parent_id (immutable), number,
# custody state / holder / storage_location (custody actions), hold, void.
PATCH_FIELDS = (frozenset(ITEM_STR_FIELDS) - {'storage_location'}) | _REF_FIELDS
PARTY_STR_FIELDS = {'name': 255, 'organization_name': 255, 'email': 255, 'phone': 60, 'address': TEXT_MAX,
                    'notes': TEXT_MAX}
PARTY_FIELDS = frozenset(PARTY_STR_FIELDS) | {'role'}
_IGNORED_KEYS = frozenset({'expected_version'})
_HEX = re.compile(r'^[0-9a-f]+$')
_EV_NUMBER = re.compile(r'^(?:ev-?)?0*(\d{1,9})$', re.IGNORECASE)

EVIDENCE_SORTABLE = {
    'sequence_number': EvidenceItem.sequence_number,
    'acquired_at': EvidenceItem.acquired_at,
    'updated_at': EvidenceItem.updated_at,
    'created_at': EvidenceItem.created_at,
    'title': EvidenceItem.title,
}
PARTY_SORTABLE = {'name': CustodyParty.name, 'created_at': CustodyParty.created_at, 'role': CustodyParty.role}


# ── Errors ──────────────────────────────────────────────────────────────────

class ApiError(Exception):
    def __init__(self, status, code, message, **details):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details

    def response(self):
        return jsonify({'error': self.code, 'message': self.message, **self.details}), self.status


def _bad(message, **details):
    return ApiError(400, 'bad_request', message, **details)


def _not_found(what):
    return ApiError(404, 'not_found', f'{what} not found')


def _forbidden(permission):
    return ApiError(403, 'forbidden', f'Permission denied. Required: {permission}')


def _api_errors(f):
    """Validation / custody errors -> JSON responses; the transaction (and
    the incident's advisory lock) is rolled back. Inside ``@audit_log`` so the
    audit row records the real status."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ApiError as exc:
            db.session.rollback()
            return exc.response()
        except CustodyError as exc:
            db.session.rollback()
            return exc.to_response()
        except BadRequest as exc:
            db.session.rollback()
            return jsonify({'error': getattr(exc, 'error_code', 'bad_request'), 'message': exc.description}), 400
    return wrapper


# ── Input validation (trust boundary) ───────────────────────────────────────

def _body():
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise _bad('Request body must be a JSON object')
    return data


def _check_keys(data, allowed):
    unknown = sorted(set(data) - set(allowed) - _IGNORED_KEYS)
    if unknown:
        raise _bad(f"Unknown or read-only field(s): {', '.join(unknown)}", fields=unknown)


def _str(data, name, max_len, *, required=False):
    value = data.get(name)
    if value is None:
        if required:
            raise _bad(f'{name} is required')
        return None
    if not isinstance(value, str):
        raise _bad(f'{name} must be a string')
    value = value.strip()
    if not value:
        if required:
            raise _bad(f'{name} is required')
        return None
    if len(value) > max_len:
        raise _bad(f'{name} must be at most {max_len} characters')
    return value


def _bool(data, name, *, default=None, required=False):
    value = data.get(name, default)
    if value is None and not required:
        return None
    if not isinstance(value, bool):
        raise _bad(f'{name} must be a boolean')
    return value


def _choice(data, name, choices, *, required=False):
    value = _str(data, name, 60, required=required)
    if value is not None and value not in choices:
        raise _bad(f"{name} must be one of: {', '.join(choices)}")
    return value


def _uuid(value, name):
    if value is None or value == '':
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise _bad(f'{name} must be a UUID')


def _past_datetime(data, name):
    value = parse_datetime(data.get(name), name)
    if value is not None and value > datetime.now(timezone.utc) + CLOCK_SLACK:
        raise _bad(f'{name} must not be in the future')
    return value


def _hex_hash(algorithm, value, name='value'):
    if not isinstance(value, str):
        raise _bad(f'{name} must be a string')
    value = value.strip().lower()
    if len(value) != HASH_ALGORITHMS[algorithm] or not _HEX.match(value):
        raise _bad(f'{algorithm} {name} must be {HASH_ALGORITHMS[algorithm]} hexadecimal characters')
    return value


def _algorithm(data, name='algorithm', *, required=True, default=None):
    value = data.get(name, default)
    if value is None and not required:
        return None
    if not isinstance(value, str) or value.strip().lower() not in HASH_ALGORITHMS:
        raise _bad(f"{name} must be one of: {', '.join(HASH_ALGORITHMS)}")
    return value.strip().lower()


# ── Scoped lookups ──────────────────────────────────────────────────────────

def _get_item(incident, evidence_item_id):
    item = EvidenceItem.query.filter_by(id=evidence_item_id, incident_id=incident.id).first()
    if item is None:
        raise _not_found('Evidence item')
    return item


def _locked_item(incident, evidence_item_id):
    """Item under the incident's custody lock, re-read, checked against the
    client's ``If-Match`` / ``expected_version``. Returns (item, conflict)."""
    item = _get_item(incident, evidence_item_id)
    CustodyLedger.lock(incident.id)
    db.session.refresh(item)
    return item, precondition(item)


def _org_user(incident, user_id, name):
    uid = _uuid(user_id, name)
    if uid is None:
        return None
    user = User.query.filter_by(id=uid, organization_id=incident.organization_id).first()
    if user is None or not user.is_active:
        raise _not_found('User')
    return user


def _recipient_user(incident, user_id):
    user = _org_user(incident, user_id, 'to_user_id')
    if user is not None and not user_can_access_incident(user, incident):
        raise ApiError(400, 'recipient_no_access', 'The recipient cannot access this incident')
    return user


def _org_party(incident, party_id, name):
    pid = _uuid(party_id, name)
    if pid is None:
        return None
    party = CustodyParty.query.filter_by(id=pid, organization_id=incident.organization_id).first()
    if party is None:
        raise _not_found('Custody party')
    return party


def _incident_host(incident, host_id):
    hid = _uuid(host_id, 'source_host_id')
    if hid is None:
        return None
    host = CompromisedHost.query.filter_by(id=hid, incident_id=incident.id).first()
    if host is None:
        raise _not_found('Host')
    return host


def _incident_artifact(incident, artifact_id, name):
    aid = _uuid(artifact_id, name)
    if aid is None:
        return None
    artifact = Artifact.query.filter_by(id=aid, incident_id=incident.id).first()
    if artifact is None:
        raise _not_found('Artifact')
    return artifact


def _require_live(item):
    if item.is_voided:
        raise CustodyError(f'{item.evidence_number} is voided')


# ── Field parsing ───────────────────────────────────────────────────────────

def _hash_records(raw, actor):
    if not isinstance(raw, list) or len(raw) > MAX_HASHES:
        raise _bad(f'acquisition_hashes must be a list of at most {MAX_HASHES} hashes')
    seen, records = set(), []
    now = datetime.now(timezone.utc).isoformat(timespec='microseconds')
    for i, h in enumerate(raw):
        if not isinstance(h, dict):
            raise _bad(f'acquisition_hashes[{i}] must be an object')
        _check_keys(h, {'algorithm', 'value', 'source'})
        algorithm = _algorithm(h, required=True)
        value = _hex_hash(algorithm, h.get('value'), f'acquisition_hashes[{i}].value')
        source = h.get('source') or 'tool_reported'
        if source not in HASH_SOURCES:
            raise _bad(f"acquisition_hashes[{i}].source must be one of: {', '.join(HASH_SOURCES)}")
        if algorithm in seen:
            raise _bad(f'Duplicate {algorithm} hash; record one value per algorithm')
        seen.add(algorithm)
        records.append({'algorithm': algorithm, 'value': value, 'source': source, 'recorded_at': now,
                        'recorded_by': str(actor.id)})
    return records


def _item_fields(data, allowed, incident, actor):
    """Validated column values for the keys present in ``data``."""
    fields = {}
    for name, max_len in ITEM_STR_FIELDS.items():
        if name in allowed and name in data:
            fields[name] = _str(data, name, max_len)
    if 'evidence_type' in data:
        fields['evidence_type'] = _choice(data, 'evidence_type', EVIDENCE_TYPES, required=True)
    if 'capacity_bytes' in data:
        cap = data['capacity_bytes']
        if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or not 0 <= cap < 2 ** 63):
            raise _bad('capacity_bytes must be a non-negative integer')
        fields['capacity_bytes'] = cap
    if 'acquired_at' in data:
        fields['acquired_at'] = _past_datetime(data, 'acquired_at')
    if 'acquired_by_user_id' in data:
        acquirer = _org_user(incident, data['acquired_by_user_id'], 'acquired_by_user_id')
        fields['acquired_by_user_id'] = acquirer.id if acquirer is not None else None
    if 'source_host_id' in data:
        host = _incident_host(incident, data['source_host_id'])
        fields['source_host_id'] = host.id if host is not None else None
        fields['source_host_label'] = host.hostname[:255] if host is not None else None
    if 'parent_id' in allowed and 'parent_id' in data:
        pid = _uuid(data['parent_id'], 'parent_id')
        if pid is not None:
            fields['parent_id'] = _get_item(incident, pid).id
    if 'acquisition_hashes' in allowed and 'acquisition_hashes' in data:
        fields['acquisition_hashes'] = _hash_records(data['acquisition_hashes'] or [], actor)
    return fields


def _party_fields(data, *, creating):
    _check_keys(data, PARTY_FIELDS if creating else PARTY_FIELDS | {'is_active'})
    fields = {}
    for name, max_len in PARTY_STR_FIELDS.items():
        if name in data:
            fields[name] = _str(data, name, max_len, required=(name == 'name'))
    if creating and not fields.get('name'):
        raise _bad('name is required')
    if 'role' in data or creating:
        fields['role'] = _choice({'role': data.get('role') or 'other'}, 'role', PARTY_ROLES, required=True)
    if 'is_active' in data:
        fields['is_active'] = _bool(data, 'is_active', required=True)
    return fields


def _ledger_value(value):
    """Strict-JSON value for a signed ledger diff."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat(timespec='microseconds')
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


# ── Responses / side effects ────────────────────────────────────────────────

def _item_response(item, entries=(), status=200, **extra):
    data = item.to_dict()
    data['ledger_entries'] = [e.to_dict() for e in entries]
    data.update(extra)
    return set_etag((jsonify(data), status), item)


def _emit(incident_id, item, entries=(), op='updated'):
    """After commit only (realtime §1 #14)."""
    realtime.emit_change(incident_id, 'evidence_item', op, obj=item)
    for entry in entries:
        realtime.emit_change(incident_id, 'custody_entry', 'created', obj=entry)


def _commit(item):
    """Commit; a concurrent item update (version) becomes a 409 response."""
    return commit_or_conflict(item)


def _verify(*, item=None, incident=None, context):
    """Run ``CustodyLedger.verify`` and audit it (``custody_chain_verified``)."""
    result = CustodyLedger.verify(item=item, incident=incident)
    chain = result.get('item_chain') if item is not None else result.get('incident_chain')
    healthy = result['status'] in exports.OK_STATUSES or result['status'] == 'unverifiable'
    log_audit_event(
        event_type='data_access' if healthy else 'security_event',
        action='custody_chain_verified',
        resource_type='evidence_item' if item is not None else 'incident',
        resource_id=item.id if item is not None else incident.id,
        incident_id=result['incident_id'],
        details={
            'scope': result['scope'], 'context': context, 'status': result['status'],
            'head_seq': (chain or {}).get('head_seq'), 'head_hash': (chain or {}).get('head_hash'),
            'break_count': len(result['breaks']), 'signatures': result['signatures'],
            'evidence_number': item.evidence_number if item is not None else None,
        },
    )
    return result


def _download(data, mimetype, filename):
    return current_app.response_class(
        data, mimetype=mimetype, headers={'Content-Disposition': f'attachment; filename="{filename}"'})


def _case_label(incident):
    return f'CASE-{incident.incident_number}' if incident.incident_number else f'incident-{incident.id}'


def _require_export_permission(user):
    if not user.has_permission(EVIDENCE_PERMS['export']):
        raise _forbidden(EVIDENCE_PERMS['export'])


# ── List / detail ───────────────────────────────────────────────────────────

def _apply_evidence_search(query, term):
    if not term:
        return query
    pattern = f'%{escape_like(term)}%'
    clauses = [col.ilike(pattern, escape='\\') for col in (
        EvidenceItem.title, EvidenceItem.serial_number, EvidenceItem.seal_number, EvidenceItem.bag_number)]
    m = _EV_NUMBER.match(term.strip())
    if m:
        clauses.append(EvidenceItem.sequence_number == int(m.group(1)))
    value = term.strip().lower()
    if _HEX.match(value) and len(value) in HASH_ALGORITHMS.values():
        clauses.append(EvidenceItem.acquisition_hashes.contains([{'value': value}]))
    return query.filter(or_(*clauses))


def _flag(raw):
    return (raw or '').strip().lower() in ('1', 'true', 'yes', 'on')


@api_bp.route(BASE, methods=['GET'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['read'])
@_api_errors
def list_evidence(incident_id):
    """Evidence register (utils/pagination contract; default sort
    ``sequence_number``). Filters: type, custody_state, holder_user_id,
    holder_party_id, host_id, parent_id, legal_hold, verification
    (match|mismatch|none), include_voided; ``q``/``search`` over EV number,
    title, serial, seal, bag, or an exact hash value."""
    incident = g.incident
    la = parse_list_args(sortable=EVIDENCE_SORTABLE, default_sort='sequence_number')
    query = (EvidenceItem.query
             .options(selectinload(EvidenceItem.creator), selectinload(EvidenceItem.parent),
                      selectinload(EvidenceItem.current_holder_user),
                      selectinload(EvidenceItem.current_holder_party))
             .filter(EvidenceItem.incident_id == incident.id))
    if not _flag(request.args.get('include_voided')):
        query = query.filter(EvidenceItem.voided_at.is_(None))
    query = apply_filters(query, {
        'type': (EvidenceItem.evidence_type, ('enum', EVIDENCE_TYPES)),
        'evidence_type': (EvidenceItem.evidence_type, ('enum', EVIDENCE_TYPES)),
        'custody_state': (EvidenceItem.custody_state, ('enum', CUSTODY_STATES)),
        'holder_user_id': (EvidenceItem.current_holder_user_id, 'uuid'),
        'holder_party_id': (EvidenceItem.current_holder_party_id, 'uuid'),
        'host_id': (EvidenceItem.source_host_id, 'uuid'),
        'parent_id': (EvidenceItem.parent_id, 'uuid'),
    })
    hold = request.args.get('legal_hold')
    if hold:
        if hold.strip().lower() not in ('true', 'false', '1', '0', 'yes', 'no'):
            raise ApiError(400, 'invalid_filter', 'legal_hold must be true or false')
        held = or_(EvidenceItem.is_locked.is_(True), EvidenceItem.legal_hold_until > datetime.now(timezone.utc))
        query = query.filter(held if _flag(hold) else ~held)
    verification = (request.args.get('verification') or '').strip().lower()
    if verification:
        if verification not in ('match', 'mismatch', 'none'):
            raise ApiError(400, 'invalid_filter', 'verification must be match, mismatch or none')
        col = EvidenceItem.last_verification_result
        query = query.filter(col.is_(None) if verification == 'none' else col == verification)
    query = _apply_evidence_search(query, la.q)
    return jsonify(paginate_response(query, la, serialize=lambda i: i.to_dict(), sortable=EVIDENCE_SORTABLE,
                                     id_col=EvidenceItem.id)), 200


@api_bp.route(ITEM, methods=['GET'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['read'])
@_api_errors
def get_evidence(incident_id, evidence_item_id):
    """Item + stored copies (live and tombstoned) + derived items +
    ``chain_summary``. Metadata views write no ledger row."""
    item = _get_item(g.incident, evidence_item_id)
    data = item.to_dict()
    data['artifacts'] = [a.to_dict() for a in item.artifacts.order_by(Artifact.created_at, Artifact.id)]
    data['children'] = [c.summary() for c in item.children.order_by(EvidenceItem.sequence_number)]
    v = _verify(item=item, context='detail')
    data['chain_summary'] = {'status': v['status'], 'head_seq': v['item_chain']['head_seq'],
                             'head_hash': v['item_chain']['head_hash']}
    return set_etag(jsonify(data), item)


# ── Register / edit ─────────────────────────────────────────────────────────

@api_bp.route(BASE, methods=['POST'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['write'])
@audit_log('data_modification', 'register', 'evidence_item')
@_api_errors
def register_evidence(incident_id):
    """Register a (metadata-only) item: ``register`` entry with a full
    snapshot, plus ``derive`` on the parent when ``parent_id`` is set."""
    user, incident = get_current_user(), g.incident
    data = _body()
    _check_keys(data, REGISTER_FIELDS)
    fields = _item_fields(data, REGISTER_FIELDS, incident, user)
    if not fields.get('title'):
        raise _bad('title is required')
    if not fields.get('evidence_type'):
        raise _bad('evidence_type is required')
    item = EvidenceItem(incident_id=incident.id, organization_id=incident.organization_id, created_by=user.id,
                        **fields)
    entries = [CustodyLedger.register_item(item, actor=user)]
    if item.parent_id is not None:
        entries.append(ChainOfCustody.query.filter_by(evidence_item_id=item.parent_id, action='derive')
                       .order_by(ChainOfCustody.seq.desc()).first())
    db.session.commit()
    entries = [e for e in entries if e is not None]
    _emit(incident.id, item, entries, op='created')
    return _item_response(item, entries, 201)


@api_bp.route(ITEM, methods=['PATCH'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['write'])
@audit_log('data_modification', 'update', 'evidence_item')
@_api_errors
def update_evidence(incident_id, evidence_item_id):
    """Edit descriptive fields; appends ``update`` with ``{changes: {field:
    [old, new]}}``. Hashes, parent, number, custody state, holder and
    location are not patchable."""
    user, incident = get_current_user(), g.incident
    data = _body()
    _check_keys(data, PATCH_FIELDS)
    item, conflict = _locked_item(incident, evidence_item_id)
    if conflict:
        db.session.rollback()
        return conflict
    _require_live(item)
    fields = _item_fields(data, PATCH_FIELDS, incident, user)
    if 'title' in fields and not fields['title']:
        raise _bad('title cannot be empty')
    names = sorted(fields)
    before = snapshot(item, names)
    changes = {}
    for name, value in fields.items():
        old = getattr(item, name)
        if old == value:
            continue
        changes[name] = [_ledger_value(old), _ledger_value(value)]
        setattr(item, name, value)
    if not changes:
        db.session.rollback()
        return _item_response(item)
    entry = CustodyLedger.append(item, 'update', performed_by=user, extra={'changes': changes})
    record_changes(before, snapshot(item, names), evidence_number=item.evidence_number)
    conflict = _commit(item)
    if conflict:
        return conflict
    _emit(incident.id, item, [entry])
    return _item_response(item, [entry])


@api_bp.route(ITEM + '/hashes', methods=['POST'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['write'])
@audit_log('data_modification', 'add_hash', 'evidence_item')
@_api_errors
def add_evidence_hash(incident_id, evidence_item_id):
    """Record an acquisition hash ``{algorithm, value, source}``. One value
    per algorithm; a correction supersedes (``supersedes`` = the old value,
    ``reason`` required), never edits."""
    user, incident = get_current_user(), g.incident
    data = _body()
    _check_keys(data, {'algorithm', 'value', 'source', 'supersedes', 'reason'})
    algorithm = _algorithm(data)
    value = _hex_hash(algorithm, data.get('value'))
    source = _choice(data, 'source', HASH_SOURCES, required=True)
    supersedes = data.get('supersedes')
    reason = _str(data, 'reason', TEXT_MAX)
    item, conflict = _locked_item(incident, evidence_item_id)
    if conflict:
        db.session.rollback()
        return conflict
    _require_live(item)
    if supersedes is not None:
        supersedes = _hex_hash(algorithm, supersedes, 'supersedes')
        if supersedes not in {h.get('value') for h in exports.active_hashes(item)
                              if h.get('algorithm') == algorithm}:
            raise _bad(f'supersedes must be a recorded {algorithm} value of this item')
        if not reason:
            raise _bad('reason is required when superseding a hash')
    entry = CustodyLedger.add_hash(item, actor=user, algorithm=algorithm, value=value, source=source,
                                   supersedes=supersedes, reason=reason)
    conflict = _commit(item)
    if conflict:
        return conflict
    _emit(incident.id, item, [entry])
    return _item_response(item, [entry], 201)


@api_bp.route(ITEM + '/verify', methods=['POST'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['write'])
@audit_log('data_modification', 'verify_hash', 'evidence_item')
@_api_errors
def verify_evidence_hash(incident_id, evidence_item_id):
    """Record a hash verification.

    Lab: ``{algorithm, observed_hash, method?, tool?, notes?}`` compared with
    the item's recorded value. Stored copy: ``{recompute: true, artifact_id,
    algorithm? (sha256)}`` recomputes from the stored bytes. A mismatch is also
    a security event (``evidence_integrity_mismatch``).
    """
    user, incident = get_current_user(), g.incident
    data = _body()
    artifact = computed = None
    if data.get('recompute') is True:
        _check_keys(data, {'recompute', 'artifact_id', 'algorithm', 'notes'})
        algorithm = _algorithm(data, required=False, default='sha256')
        if algorithm not in ('md5', 'sha256', 'sha512'):
            raise _bad('algorithm must be md5, sha256 or sha512 for a recompute')
        notes = _str(data, 'notes', TEXT_MAX)
        item = _get_item(incident, evidence_item_id)
        artifact = _incident_artifact(incident, data.get('artifact_id'), 'artifact_id')
        if artifact is None or artifact.evidence_item_id != item.id:
            raise _not_found('Artifact')
        if artifact.is_deleted:
            raise ApiError(410, 'gone', 'Artifact was deleted; its stored content was purged')
        # Fetch + hash BEFORE taking the custody lock (Drive token refresh commits).
        from app.api.v1.endpoints.artifacts import _retrieve_artifact_file
        file_obj = _retrieve_artifact_file(artifact, user)
        if file_obj is None:
            raise ApiError(404, 'not_found', 'File not found in storage')
        computed = HashService.compute_hashes(file_obj)
        observed, method, tool = computed[algorithm], 'recompute_stored_file', 'SheetStorm'
    else:
        _check_keys(data, {'algorithm', 'observed_hash', 'method', 'tool', 'notes'})
        algorithm = _algorithm(data)
        observed = _hex_hash(algorithm, data.get('observed_hash'), 'observed_hash')
        method = _str(data, 'method', 100)
        tool = _str(data, 'tool', 150)
        notes = _str(data, 'notes', TEXT_MAX)
    item, conflict = _locked_item(incident, evidence_item_id)
    if conflict:
        db.session.rollback()
        return conflict
    _require_live(item)
    expected = exports.current_hash(item, algorithm)
    if expected is None and artifact is not None:
        expected = getattr(artifact, algorithm)
    if expected is None:
        raise ApiError(409, 'no_reference_hash', f'No {algorithm} value is recorded for {item.evidence_number}')
    extra = {'artifact_id': str(artifact.id), 'computed_hashes': computed} if artifact is not None else None
    entry = CustodyLedger.record_verification(item, actor=user, algorithm=algorithm, expected=expected,
                                              observed=observed, method=method, tool=tool, notes=notes,
                                              artifact=artifact, extra=extra)
    conflict = _commit(item)
    if conflict:
        return conflict
    match = entry.verification_result == 'match'
    if not match:
        log_security_event('evidence_integrity_mismatch', resource_type='evidence_item', resource_id=item.id,
                           incident_id=incident.id,
                           details={'evidence_number': item.evidence_number, 'algorithm': algorithm,
                                    'expected_hash': expected, 'observed_hash': observed,
                                    'artifact_id': str(artifact.id) if artifact is not None else None})
    _emit(incident.id, item, [entry])
    return _item_response(item, [entry], verification={'algorithm': algorithm, 'expected_hash': expected,
                                                       'observed_hash': observed, 'match': match})


# ── Custody workflow ────────────────────────────────────────────────────────

def _recipient(data, incident, user):
    """(to_user, to_party) from exactly one of to_user_id / to_party_id /
    new_party (created in this org; needs artifacts:upload, as the route)."""
    given = [k for k in ('to_user_id', 'to_party_id', 'new_party') if data.get(k) not in (None, '')]
    if len(given) != 1:
        raise _bad('Exactly one of to_user_id, to_party_id or new_party is required')
    if given[0] == 'to_user_id':
        return _recipient_user(incident, data['to_user_id']), None
    if given[0] == 'to_party_id':
        return None, _org_party(incident, data['to_party_id'], 'to_party_id')
    raw = data['new_party']
    if not isinstance(raw, dict):
        raise _bad('new_party must be an object')
    party = CustodyParty(organization_id=incident.organization_id, created_by=user.id,
                         **_party_fields(raw, creating=True))
    db.session.add(party)
    db.session.flush()
    return None, party


def _custody_action(incident_id, evidence_item_id, keys, action):
    user, incident = get_current_user(), g.incident
    data = _body()
    _check_keys(data, keys)
    item, conflict = _locked_item(incident, evidence_item_id)
    if conflict:
        db.session.rollback()
        return conflict
    entry = action(item, user, incident, data)
    conflict = _commit(item)
    if conflict:
        return conflict
    _emit(incident.id, item, [entry])
    return _item_response(item, [entry])


def _transfer_method(data, *, required=False):
    return _choice(data, 'transfer_method', TRANSFER_METHODS, required=required)


@api_bp.route(ITEM + '/custody/check-out', methods=['POST'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['write'])
@audit_log('data_modification', 'check_out', 'evidence_item')
@_api_errors
def check_out_evidence(incident_id, evidence_item_id):
    """``{to_user_id | to_party_id | new_party{}, purpose, transfer_method?,
    expected_return_at?}`` (in_storage -> checked_out)."""
    def act(item, user, incident, data):
        to_user, to_party = _recipient(data, incident, user)
        return CustodyLedger.check_out(
            item, actor=user, purpose=_str(data, 'purpose', TEXT_MAX, required=True), to_user=to_user,
            to_party=to_party, transfer_method=_transfer_method(data),
            expected_return_at=parse_datetime(data.get('expected_return_at'), 'expected_return_at'))
    return _custody_action(incident_id, evidence_item_id,
                           {'to_user_id', 'to_party_id', 'new_party', 'purpose', 'transfer_method',
                            'expected_return_at'}, act)


@api_bp.route(ITEM + '/custody/check-in', methods=['POST'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['write'])
@audit_log('data_modification', 'check_in', 'evidence_item')
@_api_errors
def check_in_evidence(incident_id, evidence_item_id):
    """``{storage_location, seal_intact, condition_notes?, seal_number?,
    received_from_party_id?}`` (checked_out | transferred -> in_storage)."""
    def act(item, user, incident, data):
        return CustodyLedger.check_in(
            item, actor=user, storage_location=_str(data, 'storage_location', 500, required=True),
            seal_intact=_bool(data, 'seal_intact', required=True),
            condition_notes=_str(data, 'condition_notes', TEXT_MAX), seal_number=_str(data, 'seal_number', 120),
            received_from_party=_org_party(incident, data.get('received_from_party_id'),
                                           'received_from_party_id'))
    return _custody_action(incident_id, evidence_item_id,
                           {'storage_location', 'seal_intact', 'condition_notes', 'seal_number',
                            'received_from_party_id'}, act)


@api_bp.route(ITEM + '/custody/transfer', methods=['POST'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['write'])
@audit_log('data_modification', 'transfer', 'evidence_item')
@_api_errors
def transfer_evidence(incident_id, evidence_item_id):
    """``{to_party_id | new_party{} | to_user_id, transfer_method, reason,
    tracking_number?, seal_number?}`` (in_storage | checked_out ->
    transferred). Party details are snapshotted into the signed entry."""
    def act(item, user, incident, data):
        to_user, to_party = _recipient(data, incident, user)
        extra = {k: _str(data, k, 120) for k in ('tracking_number', 'seal_number')}
        return CustodyLedger.transfer(
            item, actor=user, reason=_str(data, 'reason', TEXT_MAX, required=True),
            transfer_method=_transfer_method(data, required=True), to_user=to_user, to_party=to_party,
            extra={k: v for k, v in extra.items() if v is not None})
    return _custody_action(incident_id, evidence_item_id,
                           {'to_user_id', 'to_party_id', 'new_party', 'transfer_method', 'reason',
                            'tracking_number', 'seal_number'}, act)


@api_bp.route(ITEM + '/custody/<uuid:entry_id>/acknowledge', methods=['POST'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['write'])
@audit_log('data_modification', 'acknowledge', 'evidence_item')
@_api_errors
def acknowledge_custody(incident_id, evidence_item_id, entry_id):
    """Typed-name acknowledgment of a transfer / check-out entry (once).
    ``{typed_name, statement?, stated_at?, receipt_artifact_id?}``; the
    receipt must be a ``custody_receipt`` artifact of this incident (its
    sha256 is snapshotted). Server time is authoritative."""
    def act(item, user, incident, data):
        entry = ChainOfCustody.query.filter_by(id=entry_id, evidence_item_id=item.id).first()
        if entry is None:
            raise _not_found('Custody entry')
        return CustodyLedger.acknowledge(
            item, entry, actor=user, typed_name=_str(data, 'typed_name', 255, required=True),
            statement=_str(data, 'statement', TEXT_MAX),
            stated_at=parse_datetime(data.get('stated_at'), 'stated_at'),
            receipt_artifact=_incident_artifact(incident, data.get('receipt_artifact_id'), 'receipt_artifact_id'))
    return _custody_action(incident_id, evidence_item_id,
                           {'typed_name', 'statement', 'stated_at', 'receipt_artifact_id'}, act)


@api_bp.route(ITEM + '/dispose', methods=['POST'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['manage'])
@audit_log('data_modification', 'dispose', 'evidence_item')
@_api_errors
def dispose_evidence(incident_id, evidence_item_id):
    """``{method, reason, witness_name?}`` -> disposed (terminal; refused
    under legal hold)."""
    def act(item, user, incident, data):
        return CustodyLedger.dispose(item, actor=user, method=_choice(data, 'method', DISPOSE_METHODS, required=True),
                                     reason=_str(data, 'reason', TEXT_MAX, required=True),
                                     witness_name=_str(data, 'witness_name', 255))
    return _custody_action(incident_id, evidence_item_id, {'method', 'reason', 'witness_name'}, act)


@api_bp.route(ITEM + '/void', methods=['POST'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['manage'])
@audit_log('data_modification', 'void', 'evidence_item')
@_api_errors
def void_evidence(incident_id, evidence_item_id):
    """``{reason}``: tombstone an item entered in error (number kept; refused
    under legal hold or with live derived items)."""
    def act(item, user, incident, data):
        return CustodyLedger.void(item, actor=user, reason=_str(data, 'reason', TEXT_MAX, required=True))
    return _custody_action(incident_id, evidence_item_id, {'reason'}, act)


@api_bp.route(ITEM + '/legal-hold', methods=['POST'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['manage'])
@audit_log('admin_action', 'legal_hold', 'evidence_item')
@_api_errors
def set_evidence_legal_hold(incident_id, evidence_item_id):
    """Same contract as the artifact route: ``{hold: bool = true, until?
    (future ISO-8601; omitted = indefinite), reason?}``. A hold covers derived
    items and the item's stored copies."""
    user, incident = get_current_user(), g.incident
    data = _body()
    _check_keys(data, {'hold', 'until', 'reason'})
    hold = _bool(data, 'hold', default=True)
    reason = _str(data, 'reason', TEXT_MAX)
    until = None
    if hold and data.get('until') not in (None, ''):
        until = parse_datetime(data.get('until'), 'until')
        if until <= datetime.now(timezone.utc):
            raise _bad('until must be in the future')
    item, conflict = _locked_item(incident, evidence_item_id)
    if conflict:
        db.session.rollback()
        return conflict
    entry = CustodyLedger.set_legal_hold(item, actor=user, hold=hold, until=until, reason=reason)
    conflict = _commit(item)
    if conflict:
        return conflict
    log_security_event('evidence_legal_hold' if hold else 'evidence_legal_hold_released',
                       resource_type='evidence_item', resource_id=item.id, incident_id=incident.id,
                       details={'evidence_number': item.evidence_number, 'hold': hold, 'reason': reason,
                                'until': until.isoformat() if until else None})
    _emit(incident.id, item, [entry])
    return _item_response(item, [entry])


# ── Ledger reads / verification ─────────────────────────────────────────────

@api_bp.route(ITEM + '/custody', methods=['GET'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['read'])
@_api_errors
def list_custody(incident_id, evidence_item_id):
    """Ledger entries (legacy first, then chain order), each with
    ``signature_status``, ``link_status`` and ``acknowledged_by_entry_id``."""
    item = _get_item(g.incident, evidence_item_id)
    entries = CustodyLedger.entries(item=item)
    v = _verify(item=item, context='custody_list')
    return jsonify({
        'evidence_item_id': str(item.id),
        'evidence_number': item.evidence_number,
        'status': v['status'],
        'item_chain': v['item_chain'],
        'entries': exports.annotated_entries(entries, v),
    }), 200


@api_bp.route(ITEM + '/custody/verify', methods=['GET'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['read'])
@limiter.limit("20 per minute")  # rl-group: custody_verify
@_api_errors
def verify_item_custody(incident_id, evidence_item_id):
    """``CustodyLedger.verify(item=...)`` (audited as custody_chain_verified)."""
    item = _get_item(g.incident, evidence_item_id)
    return jsonify(_verify(item=item, context='verify')), 200


@api_bp.route(BASE + '/custody/verify', methods=['GET'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['read'])
@limiter.limit("20 per minute")  # rl-group: custody_verify
@_api_errors
def verify_incident_custody(incident_id):
    """Full incident chain plus every item chain."""
    return jsonify(_verify(incident=g.incident, context='verify')), 200


# ── Exports ─────────────────────────────────────────────────────────────────

def _blank_rows():
    raw = request.args.get('blank_rows')
    lo, hi, default = FORM_BLANK_ROWS
    if raw in (None, ''):
        return default
    try:
        value = int(raw)
    except ValueError:
        raise _bad(f'blank_rows must be an integer {lo}-{hi}')
    if not lo <= value <= hi:
        raise _bad(f'blank_rows must be an integer {lo}-{hi}')
    return value


@api_bp.route(ITEM + '/custody/export', methods=['GET'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['read'])
@limiter.limit("30 per minute")  # rl-group: exports
@audit_log('data_access', 'export_custody', 'evidence_item')
@_api_errors
def export_item_custody(incident_id, evidence_item_id):
    """``format=json|csv|pdf|form|bundle`` (form: ``blank_rows`` 0-20,
    default 8). ``bundle`` also needs ``incidents:export`` (C24). Appends an
    ``export`` ledger entry before the document is built, so the exported
    chain includes it."""
    user, incident = get_current_user(), g.incident
    fmt = (request.args.get('format') or 'json').strip().lower()
    if fmt not in ITEM_EXPORT_FORMATS:
        raise _bad(f"format must be one of: {', '.join(ITEM_EXPORT_FORMATS)}")
    if fmt == 'bundle':
        _require_export_permission(user)
    blank_rows = _blank_rows() if fmt == 'form' else 0
    item = _get_item(incident, evidence_item_id)
    entry = CustodyLedger.append(item, 'export', performed_by=user, extra={'format': fmt, 'scope': 'item'})
    db.session.commit()
    realtime.emit_change(incident.id, 'custody_entry', 'created', obj=entry)

    verification = _verify(item=item, context=f'export_{fmt}')
    entries = CustodyLedger.entries(item=item)
    base = f'{_case_label(incident)}_{item.evidence_number}_custody'
    if fmt == 'json':
        return jsonify(exports.item_report(incident, item, entries, verification, user)), 200
    if fmt == 'csv':
        return _download(exports.entries_csv(exports.entry_rows(entries, verification)), 'text/csv', f'{base}.csv')
    context = exports.item_context(incident, item, entries, verification, user, blank_rows=blank_rows)
    if fmt == 'pdf':
        return _download(exports.item_pdf(context), 'application/pdf', f'{base}.pdf')
    if fmt == 'form':
        return _download(exports.item_form_pdf(context), 'application/pdf', f'{base}_form.pdf')

    heads = CustodyLedger.heads(incident.id)
    item_head = heads['items'].get(str(item.id))
    manifest = exports.build_manifest(
        scope='item', incident=incident, items=[item], entries=entries,
        heads={'items': {str(item.id): item_head} if item_head else {}, 'incident': None},
        anchors=[], verification=verification, generated_by=user)
    files = {
        'manifest.json': exports.manifest_json(manifest),
        'entries.csv': exports.entries_csv(exports.entry_rows(entries, verification)),
        'chain_of_custody.pdf': exports.item_pdf(context),
        'README.txt': exports.readme_text('item', incident, item),
        **exports.verifier_sources(),
    }
    return send_file(exports.build_bundle(files), mimetype='application/zip', as_attachment=True,
                     download_name=f'{base}_bundle.zip')


@api_bp.route(BASE + '/export', methods=['GET'])
@jwt_required()
@require_incident_access(EVIDENCE_PERMS['read'])
@limiter.limit("30 per minute")  # rl-group: exports
@audit_log('data_access', 'export_evidence_register', 'incident')
@_api_errors
def export_register(incident_id):
    """Evidence register ``format=csv|pdf|bundle`` (needs ``incidents:export``
    too, C24). The bundle covers every item chain and the incident chain; its
    incident head is recorded as an ``export_manifest`` anchor."""
    user, incident = get_current_user(), g.incident
    fmt = (request.args.get('format') or 'csv').strip().lower()
    if fmt not in REGISTER_EXPORT_FORMATS:
        raise _bad(f"format must be one of: {', '.join(REGISTER_EXPORT_FORMATS)}")
    _require_export_permission(user)

    if fmt == 'bundle':
        CustodyLedger.lock(incident.id)
        head = CustodyLedger.heads(incident.id)['incident']
        if head is not None:
            db.session.add(CustodyAnchor(incident_id=incident.id, incident_seq=head['seq'], head_hash=head['hash'],
                                         anchor_type='export_manifest', status='granted', created_by=user.id))
        db.session.commit()

    items = (EvidenceItem.query.filter_by(incident_id=incident.id)
             .options(selectinload(EvidenceItem.current_holder_user), selectinload(EvidenceItem.current_holder_party),
                      selectinload(EvidenceItem.acquired_by))
             .order_by(EvidenceItem.sequence_number).all())
    verification = _verify(incident=incident, context=f'export_register_{fmt}')
    entries = CustodyLedger.entries(incident_id=incident.id)
    rows = exports.register_rows(items, exports.item_chain_statuses(verification, entries))
    base = f'{_case_label(incident)}_evidence_register'
    if fmt == 'csv':
        return _download(exports.register_csv(rows), 'text/csv', f'{base}.csv')
    if fmt == 'pdf':
        return _download(exports.register_pdf(exports.register_context(incident, rows, verification, user)),
                         'application/pdf', f'{base}.pdf')

    anchors = CustodyAnchor.query.filter_by(incident_id=incident.id).order_by(CustodyAnchor.created_at).all()
    manifest = exports.build_manifest(
        scope='incident', incident=incident, items=items, entries=entries, heads=CustodyLedger.heads(incident.id),
        anchors=anchors, verification=verification, generated_by=user)
    files = {
        'manifest.json': exports.manifest_json(manifest),
        'entries.csv': exports.entries_csv(exports.entry_rows(entries, verification)),
        'register.csv': exports.register_csv(rows),
        'chain_of_custody.pdf': exports.register_pdf(
            exports.register_context(incident, rows, verification, user, entries=entries)),
        'README.txt': exports.readme_text('incident', incident),
        **exports.verifier_sources(),
    }
    return send_file(exports.build_bundle(files), mimetype='application/zip', as_attachment=True,
                     download_name=f'{base}_bundle.zip')


# ── Custody parties (org address book) ──────────────────────────────────────

def _get_party(user, custody_party_id):
    party = CustodyParty.query.filter_by(id=custody_party_id, organization_id=user.organization_id).first()
    if party is None:
        raise _not_found('Custody party')
    return party


@api_bp.route('/custody-parties', methods=['GET'])
@jwt_required()
@require_permission(EVIDENCE_PERMS['read'])
@_api_errors
def list_custody_parties():
    """Org-scoped; ``q``/``search`` (name, organization, email), ``role``,
    ``include_inactive``. Default sort ``name``."""
    user = get_current_user()
    la = parse_list_args(sortable=PARTY_SORTABLE, default_sort='name')
    query = CustodyParty.query.filter(CustodyParty.organization_id == user.organization_id)
    if not _flag(request.args.get('include_inactive')):
        query = query.filter(CustodyParty.is_active.is_(True))
    query = apply_filters(query, {'role': (CustodyParty.role, ('enum', PARTY_ROLES))})
    if la.q:
        pattern = f'%{escape_like(la.q)}%'
        query = query.filter(or_(*[c.ilike(pattern, escape='\\') for c in (
            CustodyParty.name, CustodyParty.organization_name, CustodyParty.email)]))
    return jsonify(paginate_response(query, la, serialize=lambda p: p.to_dict(), sortable=PARTY_SORTABLE,
                                     id_col=CustodyParty.id)), 200


@api_bp.route('/custody-parties/<uuid:custody_party_id>', methods=['GET'])
@jwt_required()
@require_permission(EVIDENCE_PERMS['read'])
@_api_errors
def get_custody_party(custody_party_id):
    party = _get_party(get_current_user(), custody_party_id)
    return set_etag(jsonify(party.to_dict()), party)


@api_bp.route('/custody-parties', methods=['POST'])
@jwt_required()
@require_permission(EVIDENCE_PERMS['write'])
@audit_log('data_modification', 'create', 'custody_party')
@_api_errors
def create_custody_party():
    """``{name, role?, organization_name?, email?, phone?, address?, notes?}``."""
    user = get_current_user()
    party = CustodyParty(organization_id=user.organization_id, created_by=user.id,
                         **_party_fields(_body(), creating=True))
    db.session.add(party)
    db.session.commit()
    return set_etag((jsonify(party.to_dict()), 201), party)


@api_bp.route('/custody-parties/<uuid:custody_party_id>', methods=['PATCH'])
@jwt_required()
@require_permission(EVIDENCE_PERMS['manage'])
@audit_log('data_modification', 'update', 'custody_party')
@_api_errors
def update_custody_party(custody_party_id):
    """Edit or (de)activate a party (never deleted). Ledger entries keep the
    snapshot taken at the time, so edits never rewrite history."""
    user = get_current_user()
    party = _get_party(user, custody_party_id)
    conflict = precondition(party)
    if conflict:
        return conflict
    fields = _party_fields(_body(), creating=False)
    names = sorted(fields)
    before = snapshot(party, names)
    for name, value in fields.items():
        setattr(party, name, value)
    record_changes(before, snapshot(party, names), party_name=party.name)
    conflict = commit_or_conflict(party)
    if conflict:
        return conflict
    return set_etag(jsonify(party.to_dict()), party)
