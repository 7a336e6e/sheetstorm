"""Task management endpoints"""
from datetime import datetime, timezone
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Task, TaskComment
from app.middleware.rbac import require_incident_access, get_current_user
from app.middleware.audit import audit_log
from app.services.notification_service import notify_task_assigned
from app.services import realtime
from app.utils.concurrency import commit_or_conflict, precondition, set_etag
from app.utils.pagination import list_response, severity_rank
from app.utils.validation import parse_datetime, check_choice, json_body


TASK_SORTABLE = {
    'order_index': Task.order_index,
    'created_at': Task.created_at,
    'due_date': Task.due_date,
    'priority': severity_rank(Task.priority),
    'status': Task.status,
}


@api_bp.route('/incidents/<uuid:incident_id>/tasks', methods=['GET'])
@jwt_required()
@require_incident_access('tasks:read')
def list_tasks(incident_id):
    """List top-level tasks (utils/pagination.py contract; q/search over
    title+description; filters status, priority, assignee_id, phase)."""
    incident = g.incident
    query = Task.query.filter_by(incident_id=incident.id, parent_task_id=None)
    return jsonify(list_response(
        query, sortable=TASK_SORTABLE, default_sort='order_index,-created_at', id_col=Task.id,
        filters={
            'status': (Task.status, 'eq'),
            'priority': (Task.priority, 'eq'),
            'assignee_id': (Task.assignee_id, 'uuid'),
            'phase': (Task.phase, 'int'),
        },
        search_columns=(Task.title, Task.description),
        serialize=lambda t: t.to_dict(include_comments=True),
    )), 200


@api_bp.route('/incidents/<uuid:incident_id>/tasks', methods=['POST'])
@jwt_required()
@require_incident_access('tasks:create')
@audit_log('data_modification', 'create', 'task')
def create_task(incident_id):
    """Create a new task."""
    user = get_current_user()
    incident = g.incident
    data = json_body()

    title = (data.get('title') or '').strip() if isinstance(data.get('title') or '', str) else ''
    if not title:
        return jsonify({'error': 'bad_request', 'message': 'title is required'}), 400

    priority = data.get('priority') or 'medium'
    if priority not in Task.PRIORITIES:
        return jsonify({'error': 'bad_request', 'message': 'Invalid priority'}), 400
    task_type = check_choice(data.get('task_type') or 'action_item', Task.TASK_TYPES, 'task_type')
    lead_outcome = check_choice(data.get('lead_outcome') or None, Task.LEAD_OUTCOMES, 'lead_outcome', allow_none=True)
    due_date = parse_datetime(data.get('due_date'), 'due_date')

    # Convert empty strings to None for UUID fields
    assignee_id = data.get('assignee_id') or None
    parent_task_id = data.get('parent_task_id') or None

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
        investigation_direction=data.get('investigation_direction'),
        evidence_refs=data.get('evidence_refs') or [],
        extra_data=data.get('extra_data') or {},
        created_by=user.id
    )

    db.session.add(task)
    db.session.commit()

    # Notify assignee
    if task.assignee_id:
        notify_task_assigned(str(task.assignee_id), task)

    realtime.emit_change(incident.id, 'task', 'created', obj=task,
                         data=task.to_dict(include_comments=True))

    return jsonify(task.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/tasks/<uuid:task_id>', methods=['GET'])
@jwt_required()
@require_incident_access('tasks:read')
def get_task(incident_id, task_id):
    """Get task details."""
    incident = g.incident

    task = Task.query.filter_by(id=task_id, incident_id=incident.id).first()
    if not task:
        return jsonify({'error': 'not_found', 'message': 'Task not found'}), 404

    return set_etag(jsonify(task.to_dict(include_comments=True)), task), 200


@api_bp.route('/incidents/<uuid:incident_id>/tasks/<uuid:task_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('tasks:update')
@audit_log('data_modification', 'update', 'task')
def update_task(incident_id, task_id):
    """Update a task."""
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
    if 'title' in data and (not isinstance(data['title'], str) or not data['title'].strip()):
        return jsonify({'error': 'bad_request', 'message': 'title must be a non-empty string'}), 400
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

    # Convert empty strings to None for UUID fields
    for uuid_field in ['assignee_id', 'parent_task_id']:
        if uuid_field in data and data[uuid_field] == '':
            data[uuid_field] = None

    # Update fields
    for field in ['title', 'description', 'priority', 'assignee_id', 'checklist',
                  'phase', 'order_index', 'extra_data',
                  'task_type', 'lead_outcome', 'investigation_direction', 'evidence_refs']:
        if field in data:
            setattr(task, field, data[field])

    if 'status' in data:
        new_status = data['status']
        if new_status not in Task.STATUSES:
            return jsonify({'error': 'bad_request', 'message': 'Invalid status'}), 400
        task.status = new_status
        if new_status == 'completed':
            task.completed_at = datetime.now(timezone.utc)

    if 'due_date' in data:
        task.due_date = data['due_date']

    conflict = commit_or_conflict(task)
    if conflict:
        return conflict, conflict.status_code

    # Notify new assignee
    if task.assignee_id and task.assignee_id != old_assignee:
        notify_task_assigned(str(task.assignee_id), task)

    realtime.emit_change(incident.id, 'task', 'updated', obj=task,
                         data=task.to_dict(include_comments=True))

    return set_etag(jsonify(task.to_dict(include_comments=True)), task), 200


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
