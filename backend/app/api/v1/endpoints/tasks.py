"""Task management endpoints"""
import uuid
from datetime import datetime, timezone
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from sqlalchemy import func, or_
from werkzeug.exceptions import BadRequest
from app.api.v1 import api_bp
from app import db
from app.models import Task, TaskComment, User
from app.middleware.rbac import require_incident_access, get_current_user
from app.middleware.audit import audit_log
from app.services.evidence_refs import (EvidenceRefsError, canonical_type, normalize_refs, resolve_refs,
                                        validate_refs)
from app.services.notification_service import notify_task_assigned
from app.services import realtime
from app.utils.concurrency import commit_or_conflict, precondition, set_etag
from app.utils.pagination import ListArgsError, in_list, list_response, severity_rank
from app.utils.validation import parse_datetime, check_choice, json_body


TASK_SORTABLE = {
    'order_index': Task.order_index,
    'created_at': Task.created_at,
    # Never-edited rows have no updated_at: they sort by creation time.
    'updated_at': func.coalesce(Task.updated_at, Task.created_at),
    'due_date': Task.due_date,
    'priority': severity_rank(Task.priority),
    'status': Task.status,
}
TASK_FILTERS = {
    'status': (Task.status, 'eq'),
    'priority': (Task.priority, 'eq'),
    'assignee_id': (Task.assignee_id, 'uuid'),
    'phase': (Task.phase, 'int'),
    'task_type': (Task.task_type, in_list(Task.TASK_TYPES)),
}

# Evidence a task may link to (services/evidence_refs.py registry names).
# The aliases host_indicator / network_indicator are accepted and stored
# canonically (host_ioc / network_ioc).
TASK_EVIDENCE_TYPES = ('timeline_event', 'host', 'account', 'network_ioc', 'host_ioc', 'malware',
                       'artifact', 'evidence_item')
MAX_TASK_EVIDENCE_REFS = 50
MAX_TITLE_LENGTH = 500
MAX_DIRECTION_LENGTH = 5000
# `lead_outcome=open` selects leads without an outcome yet.
LEAD_OUTCOME_FILTER_VALUES = ('open', *Task.LEAD_OUTCOMES)


class TaskInputError(BadRequest):
    """400 whose JSON ``error`` is ``code`` (rendered by the global handler)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.error_code = code

    @property
    def name(self):  # the global handler derives `error` from the name
        return self.error_code.replace('_', ' ')


# ── Validation ───────────────────────────────────────────────────────────

def _parse_uuid_field(value, field, code):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise TaskInputError(code, f'{field} must be a UUID')


def _validate_title(value):
    if not isinstance(value, str) or not value.strip():
        raise TaskInputError('bad_request', 'title is required')
    title = value.strip()
    if len(title) > MAX_TITLE_LENGTH:
        raise TaskInputError('bad_request', f'title must be at most {MAX_TITLE_LENGTH} characters')
    return title


def _validate_assignee(value, incident):
    """An active user of the incident's organization, or None.

    A client-supplied id is never trusted: a user of another organization (or
    a disabled one) is rejected, so assignment notifications cannot cross
    tenants.
    """
    if value in (None, ''):
        return None
    user_id = _parse_uuid_field(value, 'assignee_id', 'invalid_assignee')
    user = User.query.filter_by(id=user_id, organization_id=incident.organization_id).first()
    if user is None or not user.is_active or user.deactivated_at is not None:
        raise TaskInputError('invalid_assignee', 'invalid assignee: must be an active user of this organization')
    return user.id


def _validate_parent(value, incident, task=None):
    """A task of the same incident that is neither ``task`` nor one of its
    descendants, or None."""
    if value in (None, ''):
        return None
    parent_id = _parse_uuid_field(value, 'parent_task_id', 'invalid_parent_task')
    parent = Task.query.filter_by(id=parent_id, incident_id=incident.id).first()
    if parent is None:
        raise TaskInputError('invalid_parent_task', 'parent_task_id must be a task of this incident')
    if task is not None:
        node, seen = parent, set()
        while node is not None and node.id not in seen:
            if node.id == task.id:
                raise TaskInputError('invalid_parent_task', 'a task cannot be its own ancestor')
            seen.add(node.id)
            node = db.session.get(Task, node.parent_task_id) if node.parent_task_id else None
    return parent.id


def _validate_direction(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise TaskInputError('bad_request', 'investigation_direction must be a string')
    if len(value) > MAX_DIRECTION_LENGTH:
        raise TaskInputError('bad_request',
                             f'investigation_direction must be at most {MAX_DIRECTION_LENGTH} characters')
    return value or None


def _ref_key(ref):
    if not isinstance(ref, dict):
        return None
    try:
        eid = str(uuid.UUID(str(ref.get('evidence_id'))))
    except (ValueError, TypeError, AttributeError):
        return None
    return canonical_type(ref.get('evidence_type')), eid


def _validate_evidence(incident, refs, existing=None):
    """Validated, canonical, de-duplicated evidence refs (400
    ``invalid_evidence_refs`` otherwise).

    New refs must exist in this incident (one ``id IN (...)`` query per
    type, cross-incident ids rejected). Refs already stored on the task are
    kept without re-checking, so editing a task whose linked record was since
    deleted still works.
    """
    if refs is None:
        return []
    if not isinstance(refs, list):
        raise EvidenceRefsError('evidence_refs must be a list')
    if len(refs) > MAX_TASK_EVIDENCE_REFS:
        raise EvidenceRefsError(f'At most {MAX_TASK_EVIDENCE_REFS} evidence references are allowed')
    kept = {(r['evidence_type'], r['evidence_id']) for r in normalize_refs(existing or [])}
    positions, fresh = [], []
    for index, ref in enumerate(refs):
        if _ref_key(ref) in kept:
            continue
        positions.append(index)
        fresh.append(ref)
    try:
        validate_refs(incident.id, fresh, allowed=TASK_EVIDENCE_TYPES, max_refs=MAX_TASK_EVIDENCE_REFS)
    except EvidenceRefsError as exc:
        for item in exc.invalid:  # report indices of the request body
            if 'index' in item:
                item['index'] = positions[item['index']]
        raise
    return normalize_refs(refs)


def _invalid_refs(exc):
    return exc.to_response()


# ── Serialization ────────────────────────────────────────────────────────

def _attach_evidence(items, incident_id, user):
    """Add ``evidence: [{evidence_type, evidence_id, label, missing}]`` to
    serialized tasks. Labels are resolved server-side (one query per type for
    the whole page; stored client labels are never trusted). With ``user``,
    records of a type the user cannot read get ``label: null,
    restricted: true``."""
    union = [ref for item in items for ref in (item.get('evidence_refs') or [])]
    resolved = {}
    if union:
        resolved = {(r['evidence_type'], r['evidence_id']): r
                    for r in resolve_refs(incident_id, union, user=user)}
    for item in items:
        item['evidence'] = [resolved[(r['evidence_type'], r['evidence_id'])]
                            for r in normalize_refs(item.get('evidence_refs') or [])
                            if (r['evidence_type'], r['evidence_id']) in resolved]
    return items


def _task_body(task, user, include_comments=True):
    return _attach_evidence([task.to_dict(include_comments=include_comments)], task.incident_id, user)[0]


def _socket_payload(task):
    """Realtime payload: evidence refs with ``missing`` but **no labels**
    (recipients' read permissions differ; clients read labels over REST)."""
    data = _task_body(task, None)
    data['evidence'] = [dict(r, label=None) for r in data['evidence']]
    return data


# ── List helpers ─────────────────────────────────────────────────────────

def _lead_outcome_filter(query, raw):
    values = [v.strip() for v in raw.split(',') if v.strip()]
    if not values:
        return query
    bad = [v for v in values if v not in LEAD_OUTCOME_FILTER_VALUES]
    if bad:
        raise ListArgsError(f"invalid lead_outcome {bad[0]!r}; allowed: {', '.join(LEAD_OUTCOME_FILTER_VALUES)}",
                            'invalid_filter')
    clauses = []
    if 'open' in values:
        clauses.append(Task.lead_outcome.is_(None))
    outcomes = [v for v in values if v != 'open']
    if outcomes:
        clauses.append(Task.lead_outcome.in_(outcomes))
    return query.filter(or_(*clauses))


def _flag_arg(name, default):
    raw = (request.args.get(name) or '').strip().lower()
    if not raw:
        return default
    if raw in ('true', '1', 'yes'):
        return True
    if raw in ('false', '0', 'no'):
        return False
    raise ListArgsError(f'{name} must be true or false', 'invalid_filter')


def _lead_counts(incident_id):
    rows = (db.session.query(Task.lead_outcome, func.count(Task.id))
            .filter(Task.incident_id == incident_id, Task.parent_task_id.is_(None),
                    Task.task_type == 'investigative_lead')
            .group_by(Task.lead_outcome).all())
    counts = {'open': 0, **{o: 0 for o in Task.LEAD_OUTCOMES}}
    for outcome, n in rows:
        key = outcome or 'open'
        counts[key] = counts.get(key, 0) + n
    return counts


# ── Routes ───────────────────────────────────────────────────────────────

@api_bp.route('/incidents/<uuid:incident_id>/tasks', methods=['GET'])
@jwt_required()
@require_incident_access('tasks:read')
def list_tasks(incident_id):
    """List top-level tasks (utils/pagination.py contract; q/search over
    title+description).

    Filters: status, priority, assignee_id, phase, task_type (comma list),
    lead_outcome (comma list; ``open`` = no outcome yet). Sort also accepts
    ``updated_at``. ``include_comments=false`` skips the embedded comments.
    ``lead_counts=true`` adds ``lead_counts`` ({open, <outcome>: n} over the
    incident's top-level investigative leads, ignoring the other filters).
    Every item carries server-resolved ``evidence``.
    """
    user = get_current_user()
    incident = g.incident
    include_comments = _flag_arg('include_comments', True)
    query = Task.query.filter_by(incident_id=incident.id, parent_task_id=None)
    if request.args.get('lead_outcome'):
        query = _lead_outcome_filter(query, request.args['lead_outcome'])
    extra = {'lead_counts': _lead_counts(incident.id)} if _flag_arg('lead_counts', False) else None

    body = list_response(
        query, sortable=TASK_SORTABLE, default_sort='order_index,-created_at', id_col=Task.id,
        filters=TASK_FILTERS,
        search_columns=(Task.title, Task.description),
        serialize=lambda t: t.to_dict(include_comments=include_comments),
        extra=extra,
    )
    _attach_evidence(body['items'], incident.id, user)
    return jsonify(body), 200


@api_bp.route('/incidents/<uuid:incident_id>/tasks', methods=['POST'])
@jwt_required()
@require_incident_access('tasks:create')
@audit_log('data_modification', 'create', 'task')
def create_task(incident_id):
    """Create a new task.

    ``assignee_id`` must be an active user of the incident's organization,
    ``parent_task_id`` a task of this incident, ``evidence_refs`` at most 50
    ``{evidence_type, evidence_id}`` refs to records of this incident.
    """
    user = get_current_user()
    incident = g.incident
    data = json_body()

    title = _validate_title(data.get('title') or '')
    priority = data.get('priority') or 'medium'
    if priority not in Task.PRIORITIES:
        return jsonify({'error': 'bad_request', 'message': 'Invalid priority'}), 400
    task_type = check_choice(data.get('task_type') or 'action_item', Task.TASK_TYPES, 'task_type')
    lead_outcome = check_choice(data.get('lead_outcome') or None, Task.LEAD_OUTCOMES, 'lead_outcome', allow_none=True)
    due_date = parse_datetime(data.get('due_date'), 'due_date')
    direction = _validate_direction(data.get('investigation_direction'))
    assignee_id = _validate_assignee(data.get('assignee_id'), incident)
    parent_task_id = _validate_parent(data.get('parent_task_id'), incident)
    try:
        evidence_refs = _validate_evidence(incident, data.get('evidence_refs'))
    except EvidenceRefsError as exc:
        return _invalid_refs(exc)

    task = Task(
        incident_id=incident.id,
        title=title,
        description=data.get('description'),
        status='pending',
        priority=priority,
        assignee_id=assignee_id,
        due_date=due_date,
        checklist=data.get('checklist') or [],
        phase=data.get('phase'),
        parent_task_id=parent_task_id,
        order_index=data.get('order_index', 0),
        task_type=task_type,
        lead_outcome=lead_outcome,
        investigation_direction=direction,
        evidence_refs=evidence_refs,
        extra_data=data.get('extra_data') or {},
        created_by=user.id
    )

    db.session.add(task)
    db.session.commit()

    # Notify assignee
    if task.assignee_id:
        notify_task_assigned(str(task.assignee_id), task)

    realtime.emit_change(incident.id, 'task', 'created', obj=task, data=_socket_payload(task))

    return jsonify(_task_body(task, user, include_comments=False)), 201


@api_bp.route('/incidents/<uuid:incident_id>/tasks/<uuid:task_id>', methods=['GET'])
@jwt_required()
@require_incident_access('tasks:read')
def get_task(incident_id, task_id):
    """Get task details (with server-resolved ``evidence``)."""
    incident = g.incident

    task = Task.query.filter_by(id=task_id, incident_id=incident.id).first()
    if not task:
        return jsonify({'error': 'not_found', 'message': 'Task not found'}), 404

    return set_etag(jsonify(_task_body(task, get_current_user())), task), 200


@api_bp.route('/incidents/<uuid:incident_id>/tasks/<uuid:task_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('tasks:update')
@audit_log('data_modification', 'update', 'task')
def update_task(incident_id, task_id):
    """Update a task (same validation as create; ``evidence_refs`` replaces
    the list, refs already on the task are kept even if their record was
    deleted since)."""
    incident = g.incident
    data = json_body()

    task = Task.query.filter_by(id=task_id, incident_id=incident.id).first()
    if not task:
        return jsonify({'error': 'not_found', 'message': 'Task not found'}), 404
    conflict = precondition(task)
    if conflict:
        return conflict, conflict.status_code

    old_assignee = task.assignee_id

    # Validate before mutating anything.
    if 'title' in data:
        data['title'] = _validate_title(data['title'])
    if 'priority' in data:
        check_choice(data['priority'], Task.PRIORITIES, 'priority')
    if 'task_type' in data:
        # Explicit null resets to the default (column is NOT NULL).
        data['task_type'] = check_choice(data['task_type'] or 'action_item', Task.TASK_TYPES, 'task_type')
    if 'lead_outcome' in data:
        data['lead_outcome'] = check_choice(data['lead_outcome'] or None, Task.LEAD_OUTCOMES,
                                            'lead_outcome', allow_none=True)
    if 'due_date' in data:
        data['due_date'] = parse_datetime(data['due_date'], 'due_date')
    if 'investigation_direction' in data:
        data['investigation_direction'] = _validate_direction(data['investigation_direction'])
    if 'assignee_id' in data:
        data['assignee_id'] = _validate_assignee(data['assignee_id'], incident)
    if 'parent_task_id' in data:
        data['parent_task_id'] = _validate_parent(data['parent_task_id'], incident, task)
    if 'evidence_refs' in data:
        try:
            data['evidence_refs'] = _validate_evidence(incident, data['evidence_refs'], task.evidence_refs)
        except EvidenceRefsError as exc:
            return _invalid_refs(exc)
    if 'status' in data and data['status'] not in Task.STATUSES:
        return jsonify({'error': 'bad_request', 'message': 'Invalid status'}), 400

    # Update fields
    for field in ['title', 'description', 'priority', 'assignee_id', 'checklist',
                  'phase', 'parent_task_id', 'order_index', 'extra_data', 'due_date',
                  'task_type', 'lead_outcome', 'investigation_direction', 'evidence_refs']:
        if field in data:
            setattr(task, field, data[field])

    if 'status' in data:
        task.status = data['status']
        if data['status'] == 'completed':
            task.completed_at = datetime.now(timezone.utc)

    conflict = commit_or_conflict(task)
    if conflict:
        return conflict, conflict.status_code

    # Notify new assignee
    if task.assignee_id and task.assignee_id != old_assignee:
        notify_task_assigned(str(task.assignee_id), task)

    realtime.emit_change(incident.id, 'task', 'updated', obj=task, data=_socket_payload(task))

    return set_etag(jsonify(_task_body(task, get_current_user())), task), 200


@api_bp.route('/incidents/<uuid:incident_id>/tasks/<uuid:task_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('tasks:delete')
@audit_log('data_modification', 'delete', 'task')
def delete_task(incident_id, task_id):
    """Delete a task (tasks:delete on an incident you can access)."""
    incident = g.incident

    task = Task.query.filter_by(id=task_id, incident_id=incident.id).first()
    if not task:
        return jsonify({'error': 'not_found', 'message': 'Task not found'}), 404
    conflict = precondition(task)
    if conflict:
        return conflict, conflict.status_code

    db.session.delete(task)
    conflict = commit_or_conflict(task)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'task', 'deleted', id=task_id)

    return jsonify({'message': 'Task deleted'}), 200


# =============================================================================
# Task Comments
# =============================================================================

@api_bp.route('/incidents/<uuid:incident_id>/tasks/<uuid:task_id>/comments', methods=['GET'])
@jwt_required()
@require_incident_access('tasks:read')
def list_task_comments(incident_id, task_id):
    """List comments on a task."""
    incident = g.incident

    task = Task.query.filter_by(id=task_id, incident_id=incident.id).first()
    if not task:
        return jsonify({'error': 'not_found', 'message': 'Task not found'}), 404

    comments = TaskComment.query.filter_by(task_id=task.id).order_by(TaskComment.created_at.asc()).all()

    return jsonify({
        'items': [c.to_dict() for c in comments]
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/tasks/<uuid:task_id>/comments', methods=['POST'])
@jwt_required()
@require_incident_access('tasks:update')
def add_task_comment(incident_id, task_id):
    """Add a comment to a task."""
    user = get_current_user()
    incident = g.incident
    data = request.get_json()

    task = Task.query.filter_by(id=task_id, incident_id=incident.id).first()
    if not task:
        return jsonify({'error': 'not_found', 'message': 'Task not found'}), 404

    content = data.get('content', '').strip()
    if not content:
        return jsonify({'error': 'bad_request', 'message': 'content is required'}), 400

    comment = TaskComment(
        task_id=task.id,
        content=content,
        author_id=user.id
    )

    db.session.add(comment)
    db.session.commit()
    realtime.emit_change(incident.id, 'task_comment', 'created', obj=comment)

    return jsonify(comment.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/tasks/<uuid:task_id>/comments/<uuid:comment_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('tasks:update')
def delete_task_comment(incident_id, task_id, comment_id):
    """Delete a task comment."""
    user = get_current_user()
    incident = g.incident

    task = Task.query.filter_by(id=task_id, incident_id=incident.id).first()
    if not task:
        return jsonify({'error': 'not_found', 'message': 'Task not found'}), 404

    comment = TaskComment.query.filter_by(id=comment_id, task_id=task.id).first()
    if not comment:
        return jsonify({'error': 'not_found', 'message': 'Comment not found'}), 404

    # Only author or admin can delete
    if comment.author_id != user.id and not user.has_permission('tasks:delete'):
        return jsonify({'error': 'forbidden', 'message': 'Cannot delete this comment'}), 403

    db.session.delete(comment)
    db.session.commit()
    realtime.emit_change(incident.id, 'task_comment', 'deleted', id=comment_id)

    return jsonify({'message': 'Comment deleted'}), 200
