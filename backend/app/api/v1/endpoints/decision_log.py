"""Decision & response-action log API (W4-DEC; decision-log plan §3.5).

All routes are incident-scoped (``require_incident_access``) and every lookup
is ``filter_by(id, incident_id)``. Writes need ``If-Match`` (or body
``expected_version``) on existing records (C8: ``precondition(required=True)``)
and are serialised per incident by ``decision_log_service.lock``. There is no
DELETE: decisions are rejected/superseded, actions cancelled/rolled back.

Privileged decisions (C9): hidden (404) without ``decisions:read_privileged``;
their realtime events go only to scope ``decisions_privileged``, and their
audit rows use resource type ``decision_privileged`` so the ``activity:new``
broadcast follows the same scope. Their field diffs are recorded in the audit
log as ``{changed: true}`` only (the full history is the signed revision
chain). Nothing here is ever sent to ``ai_service``.
"""
from functools import wraps

from flask import g, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy.orm.exc import StaleDataError

from app import db, limiter
from app.api.v1 import api_bp
from app.middleware.audit import audit_log, log_audit_event
from app.middleware.rbac import get_current_user, require_incident_access
from app.models import IncidentDecision, ResponseAction
from app.models.decision_log import (
    ACTION_STATUSES, ACTION_TYPES, DECISION_CATEGORIES, DECISION_STATUSES, TARGET_TYPES,
)
from app.services import decision_log_service as svc
from app.services import realtime
from app.services.decision_log_service import DecisionLogError
from app.services.evidence_refs import EvidenceRefsError, canonical_type
from app.utils.audit_diff import record_changes
from app.utils.concurrency import commit_or_conflict, conflict_response, precondition, set_etag
from app.utils.pagination import ListArgsError, in_list, list_response, parse_uuid
from app.utils.validation import json_body

DECISION_SORTABLE = {
    'number': IncidentDecision.number,
    'decided_at': IncidentDecision.decided_at,
    'created_at': IncidentDecision.created_at,
    'status': IncidentDecision.status,
    'category': IncidentDecision.category,
}
DECISION_FILTERS = {
    'status': (IncidentDecision.status, in_list(DECISION_STATUSES)),
    'category': (IncidentDecision.category, in_list(DECISION_CATEGORIES)),
}
DECISION_SEARCH = (IncidentDecision.title, IncidentDecision.decision, IncidentDecision.rationale)

ACTION_SORTABLE = {
    'number': ResponseAction.number,
    'requested_at': ResponseAction.requested_at,
    'executed_at': ResponseAction.executed_at,
    'created_at': ResponseAction.created_at,
    'status': ResponseAction.status,
    'action_type': ResponseAction.action_type,
}
ACTION_FILTERS = {
    'status': (ResponseAction.status, in_list(ACTION_STATUSES)),
    'action_type': (ResponseAction.action_type, in_list(ACTION_TYPES)),
    'target_type': (ResponseAction.target_type, in_list(TARGET_TYPES)),
    'target_id': (ResponseAction.target_id, 'uuid'),
    'decision_id': (ResponseAction.decision_id, 'uuid'),
}
ACTION_SEARCH = (ResponseAction.title, ResponseAction.description, ResponseAction.target_label)

EXPORT_FORMATS = ('json', 'csv', 'pdf')


# ── Helpers ─────────────────────────────────────────────────────────────────

def _touches_privileged(kwargs):
    """Whether this request concerns a privileged decision (decided before
    the handler runs, so the audit row gets the right resource type)."""
    body = request.get_json(silent=True)
    if isinstance(body, dict) and body.get('is_privileged') is True:
        return True
    decision_id = kwargs.get('decision_id')
    if decision_id is None:
        return False
    flag = (db.session.query(IncidentDecision.is_privileged)
            .filter_by(id=decision_id, incident_id=kwargs.get('incident_id')).scalar())
    return flag is True


def audit_decision(action):
    """``@audit_log('data_modification', action, 'decision')`` whose resource
    type becomes ``decision_privileged`` for privileged decisions (C9)."""
    def decorator(f):
        plain = audit_log('data_modification', action, 'decision')(f)
        privileged = audit_log('data_modification', action, 'decision_privileged')(f)

        @wraps(f)
        def wrapper(*args, **kwargs):
            handler = privileged if _touches_privileged(kwargs) else plain
            return handler(*args, **kwargs)
        return wrapper
    return decorator


def _not_found(what):
    return jsonify({'error': 'not_found', 'message': f'{what} not found'}), 404


def _record_audit(before, record):
    """Audit diff of the head row; privileged decisions record changed field
    names only (``{field: {changed: true}}``)."""
    after = svc.snapshot(record)
    if getattr(record, 'is_privileged', False) or before.get('is_privileged'):
        changed = sorted(k for k in after if k not in ('version', 'updated_at', 'updated_by')
                         and before.get(k) != after.get(k))
        g.audit_changes = {**(g.get('audit_changes') or {}), **{k: {'changed': True} for k in changed}}
        g.audit_extra = {**(g.get('audit_extra') or {}), 'privileged': True}
    else:
        record_changes(before, after)


def _commit(record, run):
    """Run a service mutation and commit. Returns an error response or None."""
    try:
        run()
    except (DecisionLogError, EvidenceRefsError) as exc:
        db.session.rollback()
        return exc.to_response()
    except StaleDataError:
        db.session.rollback()
        return conflict_response(None), 409
    conflict = commit_or_conflict(record)
    if conflict is not None:
        return conflict, conflict.status_code
    return None


def _flag(name):
    raw = (request.args.get(name) or '').strip().lower()
    if raw in ('', '0', 'false', 'no'):
        return False
    if raw in ('1', 'true', 'yes'):
        return True
    raise ListArgsError(f'{name} must be true or false', 'invalid_filter')


def _linked_filter(query, model):
    """``linked_type`` + ``linked_id``: records whose links cite that record."""
    ltype, lid = request.args.get('linked_type'), request.args.get('linked_id')
    if not ltype and not lid:
        return query
    etype = canonical_type(ltype or '')
    if not etype or not lid:
        raise ListArgsError('linked_type (a known evidence type) and linked_id are both required',
                            'invalid_filter')
    ref = {'evidence_type': etype, 'evidence_id': str(parse_uuid('linked_id', lid))}
    return query.filter(model.links.contains([ref]))


def _decision_response(decision, user, status=200):
    body = svc.serialize_decisions([decision], user)[0]
    return set_etag(jsonify(body), decision), status


def _load_decision_for_write(incident, decision_id, user):
    """Lock the incident's decision log, then load + precondition the row.
    Returns (decision, error_response)."""
    svc.lock(incident.id)
    decision = svc.get_decision(incident.id, decision_id, user)
    if decision is None:
        return None, _not_found('Decision')
    conflict = precondition(decision, required=True)
    if conflict is not None:
        return None, (conflict, conflict.status_code)
    return decision, None


# ── Decisions ───────────────────────────────────────────────────────────────

@api_bp.route('/incidents/<uuid:incident_id>/decisions', methods=['GET'])
@jwt_required()
@require_incident_access('decisions:read')
def list_decisions(incident_id):
    """Decisions (pagination contract). Filters: status, category (comma
    lists), linked_type + linked_id; q over title/decision/rationale.
    Privileged decisions are only listed with decisions:read_privileged."""
    user = get_current_user()
    query = _linked_filter(svc.decisions_query(g.incident.id, user), IncidentDecision)
    body = list_response(query, sortable=DECISION_SORTABLE, default_sort='number', id_col=IncidentDecision.id,
                         filters=DECISION_FILTERS, search_columns=DECISION_SEARCH, serialize=lambda d: d)
    body['items'] = svc.serialize_decisions(body['items'], user)
    return jsonify(body), 200


@api_bp.route('/incidents/<uuid:incident_id>/decisions', methods=['POST'])
@jwt_required()
@require_incident_access('decisions:create')
@audit_decision('create')
def create_decision(incident_id):
    """Record a decision (201). ``is_privileged`` needs decisions:read_privileged;
    ``approve: true`` needs decisions:approve; ``approved_by_name`` records an
    external approval."""
    user, incident = get_current_user(), g.incident
    data = json_body()
    holder = {}

    def run():
        holder['d'] = svc.create_decision(incident, user, data)
    error = _commit(None, run)
    if error is not None:
        return error
    decision = holder['d']
    _record_audit({}, decision)
    svc.emit_decision(decision, 'created')
    return _decision_response(decision, user, 201)


@api_bp.route('/incidents/<uuid:incident_id>/decisions/<uuid:decision_id>', methods=['GET'])
@jwt_required()
@require_incident_access('decisions:read')
def get_decision(incident_id, decision_id):
    user = get_current_user()
    decision = svc.get_decision(g.incident.id, decision_id, user)
    if decision is None:
        return _not_found('Decision')
    return _decision_response(decision, user)


def _decision_mutation(incident_id, decision_id, op):
    user, incident = get_current_user(), g.incident
    data = json_body()
    decision, error = _load_decision_for_write(incident, decision_id, user)
    if error is not None:
        return error
    before = svc.snapshot(decision)
    error = _commit(decision, lambda: op(decision, user, data))
    if error is not None:
        return error
    _record_audit(before, decision)
    svc.emit_decision(decision, 'updated', was_privileged=before.get('is_privileged'))
    return _decision_response(decision, user)


@api_bp.route('/incidents/<uuid:incident_id>/decisions/<uuid:decision_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('decisions:update')
@audit_decision('update')
def update_decision(incident_id, decision_id):
    """Edit descriptive fields; ``reason`` required; If-Match required."""
    return _decision_mutation(incident_id, decision_id, svc.update_decision)


@api_bp.route('/incidents/<uuid:incident_id>/decisions/<uuid:decision_id>/approve', methods=['POST'])
@jwt_required()
@require_incident_access('decisions:read')
@audit_decision('approve')
def approve_decision(incident_id, decision_id):
    """In-app approval needs decisions:approve (never grantable to API keys);
    an external ``approved_by_name`` attestation needs decisions:update."""
    return _decision_mutation(incident_id, decision_id, svc.approve_decision)


@api_bp.route('/incidents/<uuid:incident_id>/decisions/<uuid:decision_id>/reject', methods=['POST'])
@jwt_required()
@require_incident_access('decisions:approve')
@audit_decision('reject')
def reject_decision(incident_id, decision_id):
    return _decision_mutation(incident_id, decision_id, svc.reject_decision)


@api_bp.route('/incidents/<uuid:incident_id>/decisions/<uuid:decision_id>/reopen', methods=['POST'])
@jwt_required()
@require_incident_access('decisions:update')
@audit_decision('reopen')
def reopen_decision(incident_id, decision_id):
    return _decision_mutation(incident_id, decision_id, svc.reopen_decision)


@api_bp.route('/incidents/<uuid:incident_id>/decisions/<uuid:decision_id>/supersede', methods=['POST'])
@jwt_required()
@require_incident_access('decisions:update')
@audit_decision('supersede')
def supersede_decision(incident_id, decision_id):
    return _decision_mutation(incident_id, decision_id, svc.supersede_decision)


@api_bp.route('/incidents/<uuid:incident_id>/decisions/<uuid:decision_id>/revisions', methods=['GET'])
@jwt_required()
@require_incident_access('decisions:read')
def list_decision_revisions(incident_id, decision_id):
    """Every revision with its ``signature_status``, plus chain verification."""
    user = get_current_user()
    decision = svc.get_decision(g.incident.id, decision_id, user)
    if decision is None:
        return _not_found('Decision')
    rows = svc.revisions(decision)
    verification = svc.verify_record(decision, rows)
    verification.pop('signature_status_by_id', None)
    return jsonify({'items': svc.serialize_revisions(rows, decision), 'verification': verification}), 200


# ── Response actions ────────────────────────────────────────────────────────

def _action_response(action, user, status=200):
    body = svc.serialize_actions([action], user)[0]
    return set_etag(jsonify(body), action), status


def _load_action_for_write(incident, action_id):
    svc.lock(incident.id)
    action = svc.get_action(incident.id, action_id)
    if action is None:
        return None, _not_found('Response action')
    conflict = precondition(action, required=True)
    if conflict is not None:
        return None, (conflict, conflict.status_code)
    return action, None


@api_bp.route('/incidents/<uuid:incident_id>/response-actions', methods=['GET'])
@jwt_required()
@require_incident_access('response_actions:read')
def list_response_actions(incident_id):
    """Response actions (pagination contract). Filters: status, action_type,
    target_type (comma lists), target_id, decision_id, linked_type +
    linked_id; q over title/description/target label."""
    user = get_current_user()
    query = _linked_filter(svc.actions_query(g.incident.id), ResponseAction)
    body = list_response(query, sortable=ACTION_SORTABLE, default_sort='number', id_col=ResponseAction.id,
                         filters=ACTION_FILTERS, search_columns=ACTION_SEARCH, serialize=lambda a: a)
    body['items'] = svc.serialize_actions(body['items'], user)
    return jsonify(body), 200


@api_bp.route('/incidents/<uuid:incident_id>/response-actions', methods=['POST'])
@jwt_required()
@require_incident_access('response_actions:create')
@audit_log('data_modification', 'create', 'response_action')
def create_response_action(incident_id):
    """Record a response action (201); later-stage fields log it retroactively.
    Target-state changes are only applied by ``/execute``."""
    user, incident = get_current_user(), g.incident
    data = json_body()
    holder = {}

    def run():
        holder['a'] = svc.create_action(incident, user, data)
    error = _commit(None, run)
    if error is not None:
        return error
    action = holder['a']
    record_changes({}, svc.snapshot(action))
    svc.emit_action(action, 'created')
    return _action_response(action, user, 201)


@api_bp.route('/incidents/<uuid:incident_id>/response-actions/<uuid:action_id>', methods=['GET'])
@jwt_required()
@require_incident_access('response_actions:read')
def get_response_action(incident_id, action_id):
    action = svc.get_action(g.incident.id, action_id)
    if action is None:
        return _not_found('Response action')
    return _action_response(action, get_current_user())


@api_bp.route('/incidents/<uuid:incident_id>/response-actions/<uuid:action_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('response_actions:update')
@audit_log('data_modification', 'update', 'response_action')
def update_response_action(incident_id, action_id):
    """Edit descriptive fields; ``reason`` required; If-Match required."""
    user, incident = get_current_user(), g.incident
    data = json_body()
    action, error = _load_action_for_write(incident, action_id)
    if error is not None:
        return error
    before = svc.snapshot(action)
    error = _commit(action, lambda: svc.update_action(action, user, data))
    if error is not None:
        return error
    record_changes(before, svc.snapshot(action))
    svc.emit_action(action, 'updated')
    return _action_response(action, user)


def _audit_side_effects(action, effects):
    """Audit + emit target-state changes made by execute / rollback (after commit)."""
    for fx in effects:
        target = fx['target']
        entity = 'host' if fx['target_type'] == 'host' else 'account'
        log_audit_event('data_modification', 'update',
                        'compromised_host' if entity == 'host' else 'compromised_account',
                        resource_id=target.id, incident_id=action.incident_id,
                        details={'field': fx['field'], 'old': fx['old'], 'new': fx['new'],
                                 'response_action_id': str(action.id)})
        realtime.emit_change(action.incident_id, entity, 'updated', obj=target)


def _action_transition(incident_id, action_id, event):
    user, incident = get_current_user(), g.incident
    data = json_body()
    action, error = _load_action_for_write(incident, action_id)
    if error is not None:
        return error
    before = svc.snapshot(action)
    effects = []

    def run():
        _rev, fx = svc.transition_action(action, user, event, data)
        effects.extend(fx)
    error = _commit(action, run)
    if error is not None:
        return error
    record_changes(before, svc.snapshot(action))
    svc.emit_action(action, 'updated')
    _audit_side_effects(action, effects)
    return _action_response(action, user)


@api_bp.route('/incidents/<uuid:incident_id>/response-actions/<uuid:action_id>/authorize', methods=['POST'])
@jwt_required()
@require_incident_access('response_actions:read')
@audit_log('data_modification', 'authorize', 'response_action')
def authorize_response_action(incident_id, action_id):
    """In-app authorization needs response_actions:authorize (never grantable
    to API keys); ``authorized_by_name`` (external) needs response_actions:update.
    From ``failed`` this is a retry and needs a reason."""
    return _action_transition(incident_id, action_id, 'authorize')


@api_bp.route('/incidents/<uuid:incident_id>/response-actions/<uuid:action_id>/start', methods=['POST'])
@jwt_required()
@require_incident_access('response_actions:update')
@audit_log('data_modification', 'start', 'response_action')
def start_response_action(incident_id, action_id):
    return _action_transition(incident_id, action_id, 'start')


@api_bp.route('/incidents/<uuid:incident_id>/response-actions/<uuid:action_id>/execute', methods=['POST'])
@jwt_required()
@require_incident_access('response_actions:update')
@audit_log('data_modification', 'execute', 'response_action')
def execute_response_action(incident_id, action_id):
    """``{executed_at?, executed_by_name?, apply_target_state?, target_state?}``;
    applying the target state also needs hosts:update / accounts:update."""
    return _action_transition(incident_id, action_id, 'execute')


@api_bp.route('/incidents/<uuid:incident_id>/response-actions/<uuid:action_id>/fail', methods=['POST'])
@jwt_required()
@require_incident_access('response_actions:update')
@audit_log('data_modification', 'fail', 'response_action')
def fail_response_action(incident_id, action_id):
    return _action_transition(incident_id, action_id, 'fail')


@api_bp.route('/incidents/<uuid:incident_id>/response-actions/<uuid:action_id>/verify', methods=['POST'])
@jwt_required()
@require_incident_access('response_actions:update')
@audit_log('data_modification', 'verify', 'response_action')
def verify_response_action(incident_id, action_id):
    """``{verification_result, verification_method, verified_at?, verification_notes?, verified_by_name?}``."""
    return _action_transition(incident_id, action_id, 'verify')


@api_bp.route('/incidents/<uuid:incident_id>/response-actions/<uuid:action_id>/rollback', methods=['POST'])
@jwt_required()
@require_incident_access('response_actions:update')
@audit_log('data_modification', 'rollback', 'response_action')
def rollback_response_action(incident_id, action_id):
    """``{reason, restore_target_state?}``: restores the target only if it
    still has the executed state (else 409 ``target_state_changed``)."""
    return _action_transition(incident_id, action_id, 'rollback')


@api_bp.route('/incidents/<uuid:incident_id>/response-actions/<uuid:action_id>/cancel', methods=['POST'])
@jwt_required()
@require_incident_access('response_actions:update')
@audit_log('data_modification', 'cancel', 'response_action')
def cancel_response_action(incident_id, action_id):
    return _action_transition(incident_id, action_id, 'cancel')


@api_bp.route('/incidents/<uuid:incident_id>/response-actions/<uuid:action_id>/revisions', methods=['GET'])
@jwt_required()
@require_incident_access('response_actions:read')
def list_response_action_revisions(incident_id, action_id):
    action = svc.get_action(g.incident.id, action_id)
    if action is None:
        return _not_found('Response action')
    rows = svc.revisions(action)
    verification = svc.verify_record(action, rows)
    verification.pop('signature_status_by_id', None)
    return jsonify({'items': svc.serialize_revisions(rows, action), 'verification': verification}), 200


# ── Virtual timeline and export ─────────────────────────────────────────────

@api_bp.route('/incidents/<uuid:incident_id>/response-timeline', methods=['GET'])
@jwt_required()
@require_incident_access('timeline:read')
def response_timeline(incident_id):
    """Virtual ``response`` rows (response_actions:read) and ``decision`` rows
    (decisions:read, privileged filtered) for the Events table toggle."""
    return jsonify({'items': svc.virtual_timeline(g.incident, get_current_user())}), 200


@api_bp.route('/incidents/<uuid:incident_id>/decision-log/export', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:export')
@limiter.limit('30 per minute')  # rl-group: exports
@audit_log('data_access', 'export', 'decision_log')
def export_decision_log(incident_id):
    """``?format=json|csv|pdf&kind=decisions|actions|all&include_revisions=0|1
    &include_privileged=0|1``. Needs incidents:export (C24) plus the read
    permission of each exported kind; privileged decisions only with
    include_privileged=1 and decisions:read_privileged."""
    user, incident = get_current_user(), g.incident
    fmt = (request.args.get('format') or 'json').strip().lower()
    kind = (request.args.get('kind') or 'all').strip().lower()
    if fmt not in EXPORT_FORMATS or kind not in svc.EXPORT_KINDS:
        return jsonify({'error': 'bad_request', 'message': 'format must be json|csv|pdf and kind '
                                                           'decisions|actions|all'}), 400
    needs = {'decisions': ['decisions:read'], 'actions': ['response_actions:read'],
             'all': ['decisions:read', 'response_actions:read']}[kind]
    missing = [p for p in needs if not user.has_permission(p)]
    if missing:
        return jsonify({'error': 'forbidden', 'message': f'Permission denied. Required: {", ".join(missing)}'}), 403
    include_privileged = _flag('include_privileged')
    if include_privileged and not svc.can_read_privileged(user):
        return jsonify({'error': 'forbidden', 'message': f'Permission denied. Required: {svc.PRIVILEGED_PERM}'}), 403
    payload = svc.export_payload(incident, user, kind=kind, include_privileged=include_privileged,
                                 include_revisions=_flag('include_revisions'))
    record_changes({}, {}, format=fmt, kind=kind, include_privileged=include_privileged,
                   decisions=len(payload['decisions']), response_actions=len(payload['response_actions']))
    base = f'incident_{incident.incident_number}_decision_log'
    if fmt == 'json':
        resp = jsonify(payload)
        resp.headers['Content-Disposition'] = f'attachment; filename="{base}.json"'
        return resp, 200
    if fmt == 'csv':
        return _download(svc.to_csv(payload).encode('utf-8'), 'text/csv; charset=utf-8', f'{base}.csv')
    from app.services.pdf_render import render_pdf
    pdf = render_pdf('decisions/decision_log.html', payload=payload, incident=incident)
    return _download(pdf, 'application/pdf', f'{base}.pdf')


def _download(data, mimetype, filename):
    from flask import Response
    resp = Response(data, mimetype=mimetype)
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    resp.headers['Cache-Control'] = 'no-store'
    return resp, 200
