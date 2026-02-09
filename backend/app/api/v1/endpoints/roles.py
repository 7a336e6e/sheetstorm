"""Role management endpoints"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Role, UserRole
from app.middleware.rbac import require_permission, get_current_user
from app.middleware.audit import audit_log


@api_bp.route('/roles', methods=['GET'])
@jwt_required()
@require_permission('users:read')
def list_roles():
    """List all roles."""
    roles = Role.query.order_by(Role.is_system.desc(), Role.name).all()

    return jsonify({
        'items': [_role_to_dict(r) for r in roles]
    }), 200


@api_bp.route('/roles/<uuid:role_id>', methods=['GET'])
@jwt_required()
@require_permission('users:read')
def get_role(role_id):
    """Get role details."""
    role = Role.query.get(role_id)
    if not role:
        return jsonify({'error': 'not_found', 'message': 'Role not found'}), 404

    return jsonify(_role_to_dict(role)), 200


@api_bp.route('/roles', methods=['POST'])
@jwt_required()
@require_permission('roles:manage')
@audit_log('admin_action', 'create', 'role')
def create_role():
    """Create a new custom role."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'bad_request', 'message': 'Name is required'}), 400

    # Check for duplicate
    existing = Role.query.filter_by(name=name).first()
    if existing:
        return jsonify({'error': 'conflict', 'message': 'A role with this name already exists'}), 409

    permissions = data.get('permissions', [])
    if not isinstance(permissions, list):
        return jsonify({'error': 'bad_request', 'message': 'Permissions must be an array'}), 400

    role = Role(
        name=name,
        description=data.get('description', ''),
        permissions=permissions,
        is_system=False,
    )
    db.session.add(role)
    db.session.commit()

    return jsonify(_role_to_dict(role)), 201


@api_bp.route('/roles/<uuid:role_id>', methods=['PUT'])
@jwt_required()
@require_permission('roles:manage')
@audit_log('admin_action', 'update', 'role')
def update_role(role_id):
    """Update a role."""
    role = Role.query.get(role_id)
    if not role:
        return jsonify({'error': 'not_found', 'message': 'Role not found'}), 404

    data = request.get_json()

    # For system roles, only allow adding permissions (not removing or renaming)
    if role.is_system:
        if 'permissions' in data:
            new_perms = set(data['permissions'])
            # System roles can only gain permissions, never lose them
            current_perms = set(role.permissions or [])
            merged = list(current_perms.union(new_perms))
            role.permissions = merged
    else:
        if 'name' in data:
            new_name = data['name'].strip()
            if new_name:
                # Check for duplicates
                existing = Role.query.filter(Role.name == new_name, Role.id != role.id).first()
                if existing:
                    return jsonify({'error': 'conflict', 'message': 'A role with this name already exists'}), 409
                role.name = new_name
        if 'description' in data:
            role.description = data['description']
        if 'permissions' in data:
            role.permissions = data['permissions']

    db.session.commit()

    return jsonify(_role_to_dict(role)), 200


@api_bp.route('/roles/<uuid:role_id>', methods=['DELETE'])
@jwt_required()
@require_permission('roles:manage')
@audit_log('admin_action', 'delete', 'role')
def delete_role(role_id):
    """Delete a custom role."""
    role = Role.query.get(role_id)
    if not role:
        return jsonify({'error': 'not_found', 'message': 'Role not found'}), 404

    if role.is_system:
        return jsonify({'error': 'forbidden', 'message': 'System roles cannot be deleted'}), 403

    # Check if any users are assigned to this role
    assignments = UserRole.query.filter_by(role_id=role.id).count()
    if assignments > 0:
        return jsonify({
            'error': 'conflict',
            'message': f'Cannot delete role "{role.name}" — it is assigned to {assignments} user(s). Reassign them first.'
        }), 409

    db.session.delete(role)
    db.session.commit()

    return jsonify({'message': 'Role deleted'}), 200


def _role_to_dict(role):
    """Convert role to dictionary."""
    return {
        'id': str(role.id),
        'name': role.name,
        'description': role.description or '',
        'permissions': role.permissions or [],
        'is_system': role.is_system,
        'created_at': role.created_at.isoformat() if role.created_at else None,
    }
