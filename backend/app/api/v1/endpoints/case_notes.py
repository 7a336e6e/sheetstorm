"""Case notes endpoints for incident documentation."""
from datetime import datetime, timezone
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import CaseNote
from app.middleware.rbac import require_incident_access, get_current_user
from app.middleware.audit import audit_log
from app.utils.pagination import list_response
from app.services import realtime
from app.utils.concurrency import commit_or_conflict, precondition, set_etag


CASE_NOTE_SORTABLE = {
    'is_pinned': CaseNote.is_pinned,
    'created_at': CaseNote.created_at,
    'updated_at': CaseNote.updated_at,
    'title': CaseNote.title,
}


@api_bp.route('/incidents/<uuid:incident_id>/case-notes', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def list_case_notes(incident_id):
    """List case notes, pinned first by default (utils/pagination.py
    contract; q/search over title+content; filter category)."""
    query = CaseNote.query.filter_by(incident_id=incident_id, is_archived=False)
    return jsonify(list_response(
        query, sortable=CASE_NOTE_SORTABLE, default_sort='-is_pinned,-created_at', id_col=CaseNote.id,
        filters={'category': (CaseNote.category, 'eq')},
        search_columns=(CaseNote.title, CaseNote.content),
        serialize=lambda n: n.to_dict(),
    )), 200


@api_bp.route('/incidents/<uuid:incident_id>/case-notes', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'create', 'case_note')
def create_case_note(incident_id):
    """Create a case note."""
    user = get_current_user()
    data = request.get_json()
    if not data:
        return jsonify({'error': 'bad_request', 'message': 'Request body required'}), 400

    title = data.get('title', '').strip()
    content = data.get('content', '').strip()

    if not title or not content:
        return jsonify({'error': 'bad_request', 'message': 'Title and content are required'}), 400

    category = data.get('category', 'general')
    if category not in CaseNote.CATEGORIES:
        category = 'general'

    note = CaseNote(
        incident_id=incident_id,
        title=title,
        content=content,
        category=category,
        is_pinned=data.get('is_pinned', False),
        created_by=user.id,
    )
    db.session.add(note)
    db.session.commit()
    realtime.emit_change(incident_id, 'case_note', 'created', obj=note)

    return jsonify(note.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/case-notes/<uuid:note_id>', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def get_case_note(incident_id, note_id):
    """Get a single case note."""
    note = CaseNote.query.filter_by(id=note_id, incident_id=incident_id, is_archived=False).first()
    if not note:
        return jsonify({'error': 'not_found', 'message': 'Case note not found'}), 404

    return set_etag(jsonify(note.to_dict()), note), 200


@api_bp.route('/incidents/<uuid:incident_id>/case-notes/<uuid:note_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'update', 'case_note')
def update_case_note(incident_id, note_id):
    """Update a case note."""
    note = CaseNote.query.filter_by(id=note_id, incident_id=incident_id, is_archived=False).first()
    if not note:
        return jsonify({'error': 'not_found', 'message': 'Case note not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'bad_request', 'message': 'Request body required'}), 400
    conflict = precondition(note)
    if conflict:
        return conflict, conflict.status_code

    if 'title' in data:
        title = data['title'].strip()
        if not title:
            return jsonify({'error': 'bad_request', 'message': 'Title cannot be empty'}), 400
        note.title = title
    if 'content' in data:
        content = data['content'].strip()
        if not content:
            return jsonify({'error': 'bad_request', 'message': 'Content cannot be empty'}), 400
        note.content = content
    if 'category' in data and data['category'] in CaseNote.CATEGORIES:
        note.category = data['category']
    if 'is_pinned' in data:
        note.is_pinned = bool(data['is_pinned'])

    note.updated_at = datetime.now(timezone.utc)
    note.updated_by = get_current_user().id
    conflict = commit_or_conflict(note)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident_id, 'case_note', 'updated', obj=note)

    return set_etag(jsonify(note.to_dict()), note), 200


@api_bp.route('/incidents/<uuid:incident_id>/case-notes/<uuid:note_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('case_notes:delete')
@audit_log('data_modification', 'delete', 'case_note')
def delete_case_note(incident_id, note_id):
    """Soft-delete a case note (case_notes:delete on an incident you can access)."""
    note = CaseNote.query.filter_by(id=note_id, incident_id=incident_id, is_archived=False).first()
    if not note:
        return jsonify({'error': 'not_found', 'message': 'Case note not found'}), 404
    conflict = precondition(note)
    if conflict:
        return conflict, conflict.status_code

    note.is_archived = True
    note.updated_at = datetime.now(timezone.utc)
    note.updated_by = get_current_user().id
    conflict = commit_or_conflict(note)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident_id, 'case_note', 'deleted', id=note_id)

    return jsonify({'message': 'Case note deleted'}), 200
