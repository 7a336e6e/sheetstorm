"""Organization management endpoints"""
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Organization
from app.middleware.rbac import require_permission, get_current_user
from app.middleware.audit import audit_log


@api_bp.route('/organization', methods=['GET'])
@jwt_required()
def get_organization():
    """Get current user's organization details."""
    user = get_current_user()
    
    org = Organization.query.get(user.organization_id)
    if not org:
        return jsonify({'error': 'not_found', 'message': 'Organization not found'}), 404
        
    return jsonify({
        'id': str(org.id),
        'name': org.name,
        'slug': org.slug,
        'settings': org.settings,
        'updated_at': org.updated_at.isoformat() if org.updated_at else None
    }), 200


@api_bp.route('/organization', methods=['PUT'])
@jwt_required()
@require_permission('organization:update')  # Ensure this permission exists or use admin role check
@audit_log('admin_action', 'update', 'organization')
def update_organization():
    """Update organization settings."""
    user = get_current_user()
    data = request.get_json()
    
    org = Organization.query.get(user.organization_id)
    if not org:
        return jsonify({'error': 'not_found', 'message': 'Organization not found'}), 404
        
    if 'name' in data:
        org.name = data['name'].strip()
        
    if 'settings' in data:
        # Deep merge or replace? For now, let's assume replacement or partial update
        # If settings is JSONB, we might want to be careful.
        # Simple approach: update top-level keys
        current_settings = dict(org.settings) if org.settings else {}
        current_settings.update(data['settings'])
        org.settings = current_settings
        
    from datetime import datetime, timezone
    org.updated_at = datetime.now(timezone.utc)
    
    db.session.commit()
    
    return jsonify({
        'id': str(org.id),
        'name': org.name,
        'slug': org.slug,
        'settings': org.settings,
        'updated_at': org.updated_at.isoformat()
    }), 200
