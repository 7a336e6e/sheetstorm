"""Task management endpoints"""
from datetime import datetime, timezone
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from dateutil.parser import parse as parse_date
from app.api.v1 import api_bp
from app import db, socketio
from app.models import Task, TaskComment
from app.middleware.rbac import require_incident_access, get_current_user
from app.middleware.audit import audit_log
from app.services.notification_service import notify_task_assigned


@api_bp.route('/incidents/<uuid:incident_id>/tasks', methods=['GET'])
@jwt_required()
@require_incident_access('tasks:read')
def list_tasks(incident_id):
    """List tasks for an incident."""
    incident = g.incident
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    query = Task.query.filter_by(incident_id=incident.id, parent_task_id=None)

    status = request.args.get('status')
    if status:
        query = query.filter(Task.status == status)

    priority = request.args.get('priority')
    if priority:
        query = query.filter(Task.priority == priority)

    assignee_id = request.args.get('assignee_id')
    if assignee_id:
        query = query.filter(Task.assignee_id == assignee_id)

    phase = request.args.get('phase', type=int)
    if phase:
        query = query.filter(Task.phase == phase)

    pagination = query.order_by(Task.order_index.asc(), Task.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [t.to_dict(include_comments=True) for t in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/tasks', methods=['POST'])
@jwt_required()
@require_incident_access('tasks:create')
@audit_log('data_modification', 'create', 'task')
def create_task(incident_id):
    """Create a new task."""
    user = get_current_user()
    incident = g.incident
    data = request.get_json()

    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400

    title = data.get('title', '').strip()
    if not title:
        return jsonify({'error': 'bad_request', 'message': 'title is required'}), 400

    priority = data.get('priority', 'medium')
    if priority not in Task.PRIORITIES:
        return jsonify({'error': 'bad_request', 'message': 'Invalid priority'}), 400

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
        due_date=parse_date(data['due_date']) if data.get('due_date') else None,
        checklist=data.get('checklist', []),
        phase=data.get('phase'),
        parent_task_id=parent_task_id,
        order_index=data.get('order_index', 0),
        extra_data=data.get('extra_data', {}),
        created_by=user.id
    )

    db.session.add(task)
    db.session.commit()

    # Notify assignee
    if task.assignee_id:
        notify_task_assigned(str(task.assignee_id), task)

    socketio.emit('task_added', task.to_dict(), room=f'incident_{incident_id}')

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

    return jsonify(task.to_dict(include_comments=True)), 200


@api_bp.route('/incidents/<uuid:incident_id>/tasks/<uuid:task_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('tasks:update')
@audit_log('data_modification', 'update', 'task')
def update_task(incident_id, task_id):
    """Update a task."""
    incident = g.incident
    data = request.get_json()

    task = Task.query.filter_by(id=task_id, incident_id=incident.id).first()
    if not task:
        return jsonify({'error': 'not_found', 'message': 'Task not found'}), 404

    old_assignee = task.assignee_id

    # Convert empty strings to None for UUID fields
    for uuid_field in ['assignee_id', 'parent_task_id']:
        if uuid_field in data and data[uuid_field] == '':
            data[uuid_field] = None

    # Update fields
    for field in ['title', 'description', 'priority', 'assignee_id', 'checklist',
                  'phase', 'order_index', 'extra_data']:
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
        task.due_date = parse_date(data['due_date']) if data['due_date'] else None

    db.session.commit()

    # Notify new assignee
    if task.assignee_id and task.assignee_id != old_assignee:
        notify_task_assigned(str(task.assignee_id), task)

    socketio.emit('task_updated', task.to_dict(), room=f'incident_{incident_id}')

    return jsonify(task.to_dict(include_comments=True)), 200


@api_bp.route('/incidents/<uuid:incident_id>/tasks/<uuid:task_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('tasks:delete')
@audit_log('data_modification', 'delete', 'task')
def delete_task(incident_id, task_id):
    """Delete a task."""
    incident = g.incident

    task = Task.query.filter_by(id=task_id, incident_id=incident.id).first()
    if not task:
        return jsonify({'error': 'not_found', 'message': 'Task not found'}), 404

    db.session.delete(task)
    db.session.commit()

    socketio.emit('task_deleted', {'id': str(task_id)}, room=f'incident_{incident_id}')

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

    socketio.emit('task_comment_added', {
        'task_id': str(task_id),
        'comment': comment.to_dict()
    }, room=f'incident_{incident_id}')

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

    return jsonify({'message': 'Comment deleted'}), 200
