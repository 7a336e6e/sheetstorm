"""Post-incident metrics, after-action review and improvement actions
(W3-RT-POST, realtime-collab-metrics §3.5).

Routes
    GET  /incidents/<id>/metrics               incidents:read
    GET  /metrics/incidents                    metrics:read (org aggregates)
    GET  /incidents/<id>/review                incidents:read
    PUT  /incidents/<id>/review                incidents:update (+ see below)
    GET  /incidents/<id>/improvement-actions   improvements:read
    POST /incidents/<id>/improvement-actions   improvements:create
    GET  /improvement-actions                  improvements:read (org list)
    PUT  /improvement-actions/<id>             improvements:update
    DELETE /improvement-actions/<id>           improvements:delete

Review: a draft is edited with ``incidents:update``. Finalizing a review,
reopening it, or editing a finalized one needs the unrestricted improvement
tier (``improvements:create`` + ``improvements:update``: Administrator,
Incident Responder, Manager).

Improvement actions: ``improvements:update`` without ``improvements:create``
(Analyst, Operator) only covers actions the caller owns or created.
Everything is scoped to the caller's organization; an action linked to an
incident is visible when the incident is, or when the caller owns it. Writes
use If-Match / ``expected_version`` (``precondition``) when the client sends one.
"""
from datetime import datetime, timezone

from flask import g, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app import db, limiter
from app.api.v1 import api_bp
from app.middleware.audit import audit_log
from app.middleware.rbac import (
    accessible_incidents_query, get_current_user, require_incident_access, require_permission,
    user_can_access_incident,
)
from app.models import ImprovementAction, Incident, IncidentReview, Team, User
from app.models.post_incident import ACTION_OPEN_STATUSES, ACTION_PRIORITIES, ACTION_STATUSES
from app.schemas.post_incident import (
    ImprovementActionCreate, ImprovementActionUpdate, ReviewUpdate, first_error, validate_control,
)
from app.services import metrics_service, realtime
from app.services.incident_purge import register_purge_step
from app.utils.audit_diff import record_changes, snapshot
from app.utils.concurrency import commit_or_conflict, conflict_response, precondition, set_etag
from app.utils.pagination import in_list, list_response, parse_uuid, severity_rank

REVIEW_FIELDS = ('what_went_well', 'what_went_wrong', 'root_cause', 'contributing_factors', 'detection_source',
                 'review_date', 'participants', 'status')
ACTION_FIELDS = ('title', 'description', 'owner_id', 'team_id', 'due_date', 'status', 'priority', 'category',
                 'control_framework', 'control_ref', 'review_id')

ACTION_SORTABLE = {
    'due_date': ImprovementAction.due_date,
    'created_at': ImprovementAction.created_at,
    'updated_at': ImprovementAction.updated_at,
    'title': ImprovementAction.title,
    'status': ImprovementAction.status,
    'priority': severity_rank(ImprovementAction.priority),
}
ACTION_FILTERS = {
    'status': (ImprovementAction.status, in_list(ACTION_STATUSES)),
    'priority': (ImprovementAction.priority, in_list(ACTION_PRIORITIES)),
    'incident_id': (ImprovementAction.incident_id, 'uuid'),
}
ACTION_SEARCH = (ImprovementAction.title, ImprovementAction.description, ImprovementAction.incident_ref)


def _error(status, code, message, **extra):
    return jsonify({'error': code, 'message': message, **extra}), status


def _json_object():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None
    return payload


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@api_bp.route('/incidents/<uuid:incident_id>/metrics', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def get_incident_metrics(incident_id):
    """Durations between the IR milestones of one incident.

    Negative intervals come back as ``null`` plus an entry in ``anomalies``;
    ``sources.first_malicious`` says whether the dwell start is the manual
    override, derived from the timeline, or ``restricted`` (the caller lacks
    ``timeline:read`` so the timeline is not consulted).
    """
    user = get_current_user()
    return jsonify(metrics_service.incident_metrics(
        g.incident, derive_first_malicious=user.has_permission('timeline:read'))), 200


@api_bp.route('/metrics/incidents', methods=['GET'])
@jwt_required()
@require_permission('metrics:read')
@limiter.limit("30 per minute")  # rl-group: metrics
def get_org_metrics():
    """Median / p90 per metric over the incidents the caller can see.

    Query: ``from`` and ``to`` (required, ISO date or datetime; at most 731
    days), ``group_by`` = none|severity|classification|detection_source,
    ``date_field`` = detected_at|closed_at. Archived incidents are excluded.
    A metric with fewer than 3 values reports ``n`` but no median / p90.
    """
    user = get_current_user()
    try:
        start, end, date_field, group_by = metrics_service.parse_range(
            request.args.get('from'), request.args.get('to'),
            request.args.get('date_field', 'detected_at'), request.args.get('group_by', 'none'))
    except metrics_service.MetricsRangeError as exc:
        return _error(400, 'invalid_range', str(exc))
    return jsonify(metrics_service.org_metrics(user, start, end, date_field, group_by)), 200


# ---------------------------------------------------------------------------
# After-action review
# ---------------------------------------------------------------------------

def _review_manager(user):
    """Unrestricted improvement tier (may finalize / reopen / edit a final review)."""
    return user.has_permission('improvements:create') and user.has_permission('improvements:update')


def _review_dict(review):
    data = review.to_dict()
    ids = review.participants or []
    users = {str(u.id): u for u in User.query.filter(
        User.id.in_(ids), User.organization_id == review.organization_id).all()} if ids else {}
    data['participant_users'] = [{'id': i, 'name': users[i].name} for i in ids if i in users]
    return data


@api_bp.route('/incidents/<uuid:incident_id>/review', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def get_review(incident_id):
    """The incident's after-action review (``review: null`` until created).
    ``legacy_lessons_learned`` is the old free-text field, shown read-only."""
    review = IncidentReview.query.filter_by(incident_id=incident_id).first()
    body = {
        'review': _review_dict(review) if review else None,
        'legacy_lessons_learned': g.incident.lessons_learned,
        'can_manage': _review_manager(get_current_user()),
    }
    return set_etag(jsonify(body), review) if review else (jsonify(body), 200)


@api_bp.route('/incidents/<uuid:incident_id>/review', methods=['PUT'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'update', 'incident_review')
def put_review(incident_id):
    """Create or update the review (upsert, sent fields only)."""
    user = get_current_user()
    incident = g.incident
    payload = _json_object()
    if payload is None:
        return _error(400, 'bad_request', 'A JSON object body is required')
    try:
        data = ReviewUpdate(**payload)
    except ValidationError as exc:
        return _error(400, 'validation_error', first_error(exc))
    changes = data.model_dump(exclude_unset=True, mode='python')

    review = IncidentReview.query.filter_by(incident_id=incident.id).first()
    manager = _review_manager(user)
    if review is not None and review.status == 'final' and not manager:
        return _error(403, 'review_finalized', 'This review is final; only an incident responder or manager can edit it')
    wants_final = changes.get('status') == 'final' and (review is None or review.status != 'final')
    if wants_final and not manager:
        return _error(403, 'forbidden', 'Finalizing a review requires improvements:create and improvements:update')
    if 'status' in changes and changes['status'] is None:
        return _error(400, 'validation_error', 'status cannot be null')

    participants = changes.get('participants')
    if participants is not None:
        wanted = list(dict.fromkeys(str(p) for p in participants))
        found = {str(u.id) for u in User.query.filter(
            User.id.in_(wanted), User.organization_id == user.organization_id).all()}
        missing = [p for p in wanted if p not in found]
        if missing:
            return _error(400, 'invalid_participants', 'participants must be users of your organization',
                          invalid=missing)
        changes['participants'] = wanted

    created = review is None
    if created:
        review = IncidentReview(incident_id=incident.id, organization_id=incident.organization_id,
                                created_by=user.id)
        db.session.add(review)
        before = {}
    else:
        conflict = precondition(review)
        if conflict:
            return conflict, conflict.status_code
        before = snapshot(review, REVIEW_FIELDS)

    if 'contributing_factors' in changes and changes['contributing_factors'] is not None:
        changes['contributing_factors'] = [
            {'category': f['category'], 'description': f['description'].strip()}
            for f in changes['contributing_factors']]
    elif 'contributing_factors' in changes:
        changes['contributing_factors'] = []
    if 'participants' in changes and changes['participants'] is None:
        changes['participants'] = []
    for field, value in changes.items():
        setattr(review, field, value)
    if review.status == 'final' and review.finalized_at is None:
        review.finalized_at, review.finalized_by = _now(), user.id
    elif review.status == 'draft' and review.finalized_at is not None:
        review.finalized_at = review.finalized_by = None

    record_changes(before, snapshot(review, REVIEW_FIELDS))
    try:
        if created:
            db.session.commit()
        else:
            conflict = commit_or_conflict(review)
            if conflict:
                return conflict, conflict.status_code
    except IntegrityError:
        # Two first saves raced on the unique incident_id.
        db.session.rollback()
        current = IncidentReview.query.filter_by(incident_id=incident.id).first()
        return conflict_response(current, _review_dict)

    body = _review_dict(review)
    realtime.emit_change(incident.id, 'review', 'created' if created else 'updated', obj=review, data=body)
    return set_etag((jsonify(body), 201 if created else 200), review)


# ---------------------------------------------------------------------------
# Improvement actions
# ---------------------------------------------------------------------------

def _action_manager(user):
    """Unrestricted tier: may change any visible action, not only own ones."""
    return user.has_permission('improvements:create')


def _is_own(user, action):
    return action.owner_id == user.id or action.created_by == user.id


def _incident_visible(user, action):
    if action.incident_id is None:
        return True
    incident = db.session.get(Incident, action.incident_id)
    return incident is not None and incident.organization_id == user.organization_id \
        and user_can_access_incident(user, incident)


def _load_action(user, action_id):
    """The action if it is in the caller's org and visible to them, else None."""
    action = ImprovementAction.query.filter_by(id=action_id, organization_id=user.organization_id).first()
    if action is None:
        return None
    if action.owner_id == user.id or _incident_visible(user, action):
        return action
    return None


def _action_dict(action, include_incident=True):
    return action.to_dict(include_incident=include_incident)


def _validate_action_refs(user, incident, fields):
    """Owner / team / review / control checks shared by create and update.
    Returns an error response tuple or None."""
    owner_id = fields.get('owner_id')
    if owner_id and not User.query.filter_by(id=owner_id, organization_id=user.organization_id,
                                             is_active=True).first():
        return _error(400, 'invalid_owner', 'owner_id is not an active user of your organization')
    team_id = fields.get('team_id')
    if team_id and not Team.query.filter_by(id=team_id, organization_id=user.organization_id).first():
        return _error(400, 'invalid_team', 'team_id is not a team of your organization')
    review_id = fields.get('review_id')
    if review_id and incident is not None and not IncidentReview.query.filter_by(
            id=review_id, incident_id=incident.id).first():
        return _error(400, 'invalid_review', 'review_id is not the review of this incident')
    return None


def _snapshot_ref(incident):
    return f'#{incident.incident_number} {incident.title}'[:600]


@api_bp.route('/incidents/<uuid:incident_id>/improvement-actions', methods=['GET'])
@jwt_required()
@require_incident_access('improvements:read')
def list_incident_improvement_actions(incident_id):
    query = ImprovementAction.query.filter_by(incident_id=incident_id,
                                              organization_id=g.incident.organization_id)
    return jsonify(list_response(
        query, sortable=ACTION_SORTABLE, default_sort='due_date', id_col=ImprovementAction.id,
        filters=ACTION_FILTERS, search_columns=ACTION_SEARCH, max_per_page=100,
        serialize=lambda a: _action_dict(a),
    )), 200


@api_bp.route('/incidents/<uuid:incident_id>/improvement-actions', methods=['POST'])
@jwt_required()
@require_incident_access('improvements:create')
@audit_log('data_modification', 'create', 'improvement_action')
def create_improvement_action(incident_id):
    user = get_current_user()
    incident = g.incident
    payload = _json_object()
    if payload is None:
        return _error(400, 'bad_request', 'A JSON object body is required')
    try:
        data = ImprovementActionCreate(**payload)
    except ValidationError as exc:
        return _error(400, 'validation_error', first_error(exc))
    fields = data.model_dump(mode='python')
    bad = _validate_action_refs(user, incident, fields) or _control_error(fields)
    if bad:
        return bad

    review = IncidentReview.query.filter_by(incident_id=incident.id).first()
    action = ImprovementAction(
        organization_id=incident.organization_id, incident_id=incident.id,
        incident_ref=_snapshot_ref(incident), created_by=user.id,
        review_id=fields.get('review_id') or (review.id if review else None),
        **{k: fields[k] for k in ACTION_FIELDS if k not in ('review_id',) and k in fields},
    )
    if action.status == 'done':
        action.completed_at, action.completed_by = _now(), user.id
    db.session.add(action)
    db.session.commit()

    body = _action_dict(action)
    realtime.emit_change(incident.id, 'improvement_action', 'created', obj=action, data=body)
    return set_etag((jsonify(body), 201), action)


def _control_error(fields):
    message = validate_control(fields.get('control_framework'), fields.get('control_ref'))
    return _error(400, 'invalid_control', message) if message else None


@api_bp.route('/improvement-actions', methods=['GET'])
@jwt_required()
@require_permission('improvements:read')
def list_improvement_actions():
    """Org-wide list. An action is listed when its incident is visible to the
    caller, it has no incident (deleted), or the caller owns it.

    Filters: status, priority (comma lists), incident_id, owner_id (a user id
    or ``me``), overdue=true (open statuses past due), q. Sorted by due date
    (nulls last) unless ``sort`` says otherwise.
    """
    user = get_current_user()
    visible_ids = accessible_incidents_query(user).with_entities(Incident.id)
    query = ImprovementAction.query.filter(
        ImprovementAction.organization_id == user.organization_id,
        db.or_(ImprovementAction.incident_id.is_(None),
               ImprovementAction.owner_id == user.id,
               ImprovementAction.incident_id.in_(visible_ids.scalar_subquery())))

    owner = request.args.get('owner_id')
    if owner:
        query = query.filter(ImprovementAction.owner_id == (user.id if owner == 'me' else parse_uuid('owner_id', owner)))
    if (request.args.get('overdue') or '').strip().lower() in ('1', 'true', 'yes'):
        query = query.filter(ImprovementAction.due_date < _now(),
                             ImprovementAction.status.in_(ACTION_OPEN_STATUSES))

    body = list_response(
        query, sortable=ACTION_SORTABLE, default_sort='due_date', id_col=ImprovementAction.id,
        filters=ACTION_FILTERS, search_columns=ACTION_SEARCH, max_per_page=100,
        serialize=lambda a: a)
    rows = body['items']
    # The incident object (title, number) only for incidents the caller can
    # see; an owner-visible action on a hidden incident keeps `incident_ref`.
    linked = {a.incident_id for a in rows if a.incident_id}
    visible = {r[0] for r in accessible_incidents_query(user).with_entities(Incident.id).filter(
        Incident.id.in_(linked)).all()} if linked else set()
    body['items'] = [_action_dict(a, include_incident=a.incident_id in visible) for a in rows]
    return jsonify(body), 200


@api_bp.route('/improvement-actions/<uuid:improvement_action_id>', methods=['PUT'])
@jwt_required()
@require_permission('improvements:update')
@audit_log('data_modification', 'update', 'improvement_action')
def update_improvement_action(improvement_action_id):
    user = get_current_user()
    action = _load_action(user, improvement_action_id)
    if action is None:
        return _error(404, 'not_found', 'Improvement action not found')
    if not (_action_manager(user) or _is_own(user, action)):
        return _error(403, 'forbidden', 'You can only change improvement actions you own or created')
    payload = _json_object()
    if payload is None:
        return _error(400, 'bad_request', 'A JSON object body is required')
    try:
        changes = ImprovementActionUpdate(**payload).model_dump(exclude_unset=True, mode='python')
    except ValidationError as exc:
        return _error(400, 'validation_error', first_error(exc))
    for key in ('title', 'status', 'priority'):
        if key in changes and changes[key] is None:
            return _error(400, 'validation_error', f'{key} cannot be null')
    conflict = precondition(action)
    if conflict:
        return conflict, conflict.status_code

    incident = db.session.get(Incident, action.incident_id) if action.incident_id else None
    bad = _validate_action_refs(user, incident, changes)
    if not bad:
        merged = {'control_framework': changes.get('control_framework', action.control_framework),
                  'control_ref': changes.get('control_ref', action.control_ref)}
        if 'control_framework' in changes and changes['control_framework'] is None and 'control_ref' not in changes:
            merged['control_ref'] = None
            changes['control_ref'] = None
        bad = _control_error(merged)
    if bad:
        return bad

    before = snapshot(action, ACTION_FIELDS)
    previous_status = action.status
    for field, value in changes.items():
        setattr(action, field, value)
    if action.status == 'done' and previous_status != 'done':
        action.completed_at, action.completed_by = _now(), user.id
    elif action.status != 'done' and previous_status == 'done':
        action.completed_at = action.completed_by = None
    if incident is not None and ('title' in changes or 'status' in changes):
        action.incident_ref = _snapshot_ref(incident)
    record_changes(before, snapshot(action, ACTION_FIELDS))

    conflict = commit_or_conflict(action)
    if conflict:
        return conflict, conflict.status_code
    body = _action_dict(action, include_incident=_incident_visible(user, action))
    if action.incident_id:
        realtime.emit_change(action.incident_id, 'improvement_action', 'updated', obj=action, data=body)
    return set_etag((jsonify(body), 200), action)


@api_bp.route('/improvement-actions/<uuid:improvement_action_id>', methods=['DELETE'])
@jwt_required()
@require_permission('improvements:delete')
@audit_log('data_modification', 'delete', 'improvement_action')
def delete_improvement_action(improvement_action_id):
    user = get_current_user()
    action = _load_action(user, improvement_action_id)
    if action is None:
        return _error(404, 'not_found', 'Improvement action not found')
    conflict = precondition(action)
    if conflict:
        return conflict, conflict.status_code
    incident_id, action_id = action.incident_id, action.id
    db.session.delete(action)
    db.session.commit()
    if incident_id:
        realtime.emit_change(incident_id, 'improvement_action', 'deleted', id=action_id)
    return jsonify({'message': 'Improvement action deleted', 'id': str(action_id)}), 200


def _purge_refresh_refs(ctx):
    """incident_purge pre step `improvement_refs`: improvement actions outlive
    a permanent delete (their incident_id becomes NULL through the foreign
    key), so refresh the "#<n> <title>" label they keep. ORM objects, not
    ``query.update()``, so the row versions are bumped."""
    for action in ImprovementAction.query.filter_by(incident_id=ctx.incident_id).all():
        action.incident_ref = f'#{ctx.incident_number} {ctx.title}'[:600]


register_purge_step('improvement_refs', _purge_refresh_refs, phase='pre')
