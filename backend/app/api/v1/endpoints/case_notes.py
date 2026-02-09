"""Case notes endpoints for incident documentation."""
from datetime import datetime, timezone
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db, socketio
from app.models import CaseNote
from app.middleware.rbac import require_incident_access, get_current_user
from app.middleware.audit import audit_log


@api_bp.route('/incidents/<uuid:incident_id>/notes', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def list_case_notes(incident_id):
    """List case notes for an incident."""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)
    category = request.args.get('category')

    query = CaseNote.query.filter_by(incident_id=incident_id)

    if category:
        query = query.filter(CaseNote.category == category)

    # Pinned first, then by date
    query = query.order_by(CaseNote.is_pinned.desc(), CaseNote.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'items': [n.to_dict() for n in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/notes', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'create', 'case_note')
def create_case_note(incident_id):
    """Create a case note."""
    user = get_current_user()
    data = request.get_json()

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

    socketio.emit('case_note_created', note.to_dict(), room=f'incident_{incident_id}')

    return jsonify(note.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/notes/<uuid:note_id>', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def get_case_note(incident_id, note_id):
    """Get a single case note."""
    note = CaseNote.query.filter_by(id=note_id, incident_id=incident_id).first()
    if not note:
        return jsonify({'error': 'not_found', 'message': 'Case note not found'}), 404

    return jsonify(note.to_dict()), 200


@api_bp.route('/incidents/<uuid:incident_id>/notes/<uuid:note_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'update', 'case_note')
def update_case_note(incident_id, note_id):
    """Update a case note."""
    note = CaseNote.query.filter_by(id=note_id, incident_id=incident_id).first()
    if not note:
        return jsonify({'error': 'not_found', 'message': 'Case note not found'}), 404

    data = request.get_json()

    if 'title' in data:
        note.title = data['title'].strip()
    if 'content' in data:
        note.content = data['content'].strip()
    if 'category' in data and data['category'] in CaseNote.CATEGORIES:
        note.category = data['category']
    if 'is_pinned' in data:
        note.is_pinned = bool(data['is_pinned'])

    note.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    socketio.emit('case_note_updated', note.to_dict(), room=f'incident_{incident_id}')

    return jsonify(note.to_dict()), 200


@api_bp.route('/incidents/<uuid:incident_id>/notes/<uuid:note_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'delete', 'case_note')
def delete_case_note(incident_id, note_id):
    """Delete a case note."""
    note = CaseNote.query.filter_by(id=note_id, incident_id=incident_id).first()
    if not note:
        return jsonify({'error': 'not_found', 'message': 'Case note not found'}), 404

    db.session.delete(note)
    db.session.commit()

    return jsonify({'message': 'Case note deleted'}), 200
