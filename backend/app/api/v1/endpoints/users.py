"""User management endpoints"""
from flask import jsonify, request, g, current_app
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import User, Role, UserRole, Organization
from app.middleware.rbac import require_permission, get_current_user
from app.middleware.audit import audit_log


@api_bp.route('/users', methods=['GET'])
@jwt_required()
@require_permission('users:read')
def list_users():
    """List all users in the organization."""
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = User.query.filter_by(organization_id=user.organization_id)

    # Filter by role
    role = request.args.get('role')
    if role:
        query = query.join(UserRole).join(Role).filter(Role.name == role)

    # Filter by active status
    is_active = request.args.get('is_active')
    if is_active is not None:
        query = query.filter(User.is_active == (is_active.lower() == 'true'))

    # Search by name or email
    search = request.args.get('search')
    if search:
        query = query.filter(
            db.or_(
                User.name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )

    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [u.to_dict() for u in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    }), 200


@api_bp.route('/users', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'create_user', 'user')
def create_user():
    """Create a new user."""
    current = get_current_user()
    data = request.get_json()

    if not data.get('email') or not data.get('name') or not data.get('password'):
        return jsonify({'error': 'bad_request', 'message': 'Email, name, and password are required'}), 400

    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'conflict', 'message': 'Email already exists'}), 409

    user = User(
        email=data['email'],
        name=data['name'],
        organization_id=current.organization_id,
        is_active=data.get('is_active', True),
        is_verified=True,  # Admin created users are verified
        organizational_role=data.get('organizational_role', '').strip() or None,
    )
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()

    # Assign roles — accept array or single string
    role_names = data.get('roles', [])
    if not role_names:
        role_names = [data.get('role', 'Analyst')]
    for role_name in role_names:
        role = Role.query.filter_by(name=role_name).first()
        if role:
            user_role = UserRole(
                user_id=user.id,
                role_id=role.id,
                organization_id=current.organization_id,
                granted_by=current.id
            )
            db.session.add(user_role)
    db.session.commit()

    return jsonify(user.to_dict()), 201


@api_bp.route('/users/<uuid:user_id>', methods=['GET'])
@jwt_required()
@require_permission('users:read')
def get_user(user_id):
    """Get a specific user."""
    current = get_current_user()
    user = User.query.filter_by(id=user_id, organization_id=current.organization_id).first()

    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    return jsonify(user.to_dict(include_permissions=True)), 200


@api_bp.route('/users/<uuid:user_id>', methods=['PUT'])
@jwt_required()
@require_permission('users:update')
@audit_log('admin_action', 'update_user', 'user')
def update_user(user_id):
    """Update a user."""
    current = get_current_user()
    user = User.query.filter_by(id=user_id, organization_id=current.organization_id).first()

    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    data = request.get_json()

    # Update allowed fields
    if 'name' in data:
        user.name = data['name'].strip()
    if 'is_active' in data and current.has_permission('users:manage'):
        user.is_active = data['is_active']
    if 'organizational_role' in data:
        user.organizational_role = data['organizational_role'].strip() if data['organizational_role'] else None

    # Password update (admin only)
    if 'password' in data and current.has_permission('users:manage'):
        user.set_password(data['password'])

    db.session.commit()

    return jsonify(user.to_dict()), 200


@api_bp.route('/users/<uuid:user_id>', methods=['DELETE'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'delete_user', 'user')
def delete_user(user_id):
    """Delete a user."""
    current = get_current_user()
    user = User.query.filter_by(id=user_id, organization_id=current.organization_id).first()

    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404
        
    if user.id == current.id:
        return jsonify({'error': 'bad_request', 'message': 'Cannot delete yourself'}), 400

    db.session.delete(user)
    db.session.commit()

    return jsonify({'message': 'User deleted successfully'}), 200


@api_bp.route('/users/<uuid:user_id>/roles', methods=['GET'])
@jwt_required()
@require_permission('users:read')
def get_user_roles(user_id):
    """Get roles for a user."""
    current = get_current_user()
    user = User.query.filter_by(id=user_id, organization_id=current.organization_id).first()

    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    return jsonify({
        'user_id': str(user.id),
        'roles': [
            {
                'id': str(ur.role.id),
                'name': ur.role.name,
                'description': ur.role.description,
                'granted_at': ur.granted_at.isoformat() if ur.granted_at else None
            }
            for ur in user.user_roles
        ]
    }), 200


@api_bp.route('/users/<uuid:user_id>/roles', methods=['POST'])
@jwt_required()
@require_permission('roles:manage')
@audit_log('admin_action', 'assign_role', 'user')
def assign_role(user_id):
    """Assign a role to a user."""
    current = get_current_user()
    user = User.query.filter_by(id=user_id, organization_id=current.organization_id).first()

    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    data = request.get_json()
    role_id = data.get('role_id')

    if not role_id:
        return jsonify({'error': 'bad_request', 'message': 'role_id is required'}), 400

    role = Role.query.get(role_id)
    if not role:
        return jsonify({'error': 'not_found', 'message': 'Role not found'}), 404

    # Check if already assigned
    existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
    if existing:
        return jsonify({'error': 'conflict', 'message': 'Role already assigned'}), 409

    user_role = UserRole(
        user_id=user.id,
        role_id=role.id,
        organization_id=current.organization_id,
        granted_by=current.id
    )
    db.session.add(user_role)
    db.session.commit()

    return jsonify({'message': 'Role assigned successfully'}), 201


@api_bp.route('/users/<uuid:user_id>/roles/<uuid:role_id>', methods=['DELETE'])
@jwt_required()
@require_permission('roles:manage')
@audit_log('admin_action', 'revoke_role', 'user')
def revoke_role(user_id, role_id):
    """Revoke a role from a user."""
    current = get_current_user()
    user = User.query.filter_by(id=user_id, organization_id=current.organization_id).first()

    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    user_role = UserRole.query.filter_by(user_id=user.id, role_id=role_id).first()
    if not user_role:
        return jsonify({'error': 'not_found', 'message': 'Role assignment not found'}), 404

    db.session.delete(user_role)
    db.session.commit()

    return jsonify({'message': 'Role revoked successfully'}), 200


@api_bp.route('/roles', methods=['GET'])
@jwt_required()
@require_permission('users:read')
def list_roles():
    """List all available roles."""
    roles = Role.query.all()

    return jsonify({
        'items': [
            {
                'id': str(r.id),
                'name': r.name,
                'description': r.description,
                'permissions': r.permissions,
                'is_system': r.is_system
            }
            for r in roles
        ]
    }), 200


@api_bp.route('/users/sync-supabase', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
def sync_supabase_users():
    """Fetch users from Supabase and sync them into local DB.

    Uses the Supabase Admin API (service_role key) to list all Supabase
    users.  For each one that doesn't already exist locally, a local User
    record is created with auth_provider='supabase' and assigned the Viewer
    role.  Already-existing users are left unchanged.
    """
    import requests as http_requests

    supabase_url = current_app.config.get('SUPABASE_URL')
    service_key = current_app.config.get('SUPABASE_SERVICE_ROLE_KEY')

    if not supabase_url or not service_key:
        return jsonify({'error': 'not_configured', 'message': 'Supabase service role key not configured'}), 501

    current = get_current_user()

    try:
        # Paginate through all Supabase users
        all_sb_users = []
        page = 1
        per_page = 100
        while True:
            resp = http_requests.get(
                f"{supabase_url}/auth/v1/admin/users",
                headers={
                    'Authorization': f'Bearer {service_key}',
                    'apikey': service_key,
                },
                params={'page': page, 'per_page': per_page},
                timeout=15,
            )
            if resp.status_code != 200:
                current_app.logger.error(f"Supabase admin API error: {resp.status_code} {resp.text}")
                return jsonify({'error': 'supabase_error', 'message': 'Failed to fetch Supabase users'}), 502

            data = resp.json()
            users_list = data.get('users', data) if isinstance(data, dict) else data
            if not users_list:
                break
            all_sb_users.extend(users_list)
            if len(users_list) < per_page:
                break
            page += 1

        # Sync into local DB
        created = 0
        skipped = 0
        org = Organization.query.filter_by(slug='default').first()
        if not org:
            org = Organization(name='Default Organization', slug='default')
            db.session.add(org)
            db.session.flush()

        viewer_role = Role.query.filter_by(name='Viewer').first()

        for sb_user in all_sb_users:
            email = sb_user.get('email')
            if not email:
                continue

            existing = User.query.filter_by(email=email.lower()).first()
            if existing:
                # Update supabase_id if missing
                if not existing.supabase_id and sb_user.get('id'):
                    existing.supabase_id = sb_user['id']
                skipped += 1
                continue

            user_meta = sb_user.get('user_metadata', {}) or {}
            name = (
                user_meta.get('name')
                or user_meta.get('full_name')
                or user_meta.get('user_name')
                or email.split('@')[0]
            )
            avatar = user_meta.get('avatar_url')

            new_user = User(
                email=email.lower(),
                name=name,
                avatar_url=avatar,
                organization_id=org.id,
                auth_provider='supabase',
                supabase_id=sb_user.get('id', ''),
                is_active=True,
                is_verified=True,
            )
            db.session.add(new_user)
            db.session.flush()

            if viewer_role:
                ur = UserRole(
                    user_id=new_user.id,
                    role_id=viewer_role.id,
                    organization_id=org.id,
                    granted_by=current.id,
                )
                db.session.add(ur)

            created += 1

        db.session.commit()

        return jsonify({
            'message': f'Synced Supabase users: {created} created, {skipped} already existed',
            'created': created,
            'skipped': skipped,
            'total_supabase': len(all_sb_users),
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Supabase sync error: {e}")
        return jsonify({'error': 'server_error', 'message': 'Failed to sync Supabase users'}), 500
