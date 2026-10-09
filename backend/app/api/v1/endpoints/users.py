"""User management endpoints"""
import uuid

from datetime import datetime, timezone

import sqlalchemy as sa
from flask import jsonify, request, g, current_app
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import User, Role, UserRole, Organization, TeamMember
from app.middleware.rbac import require_permission, get_current_user
from app.middleware.audit import audit_log
from app.utils.audit_diff import record_changes, snapshot
from app.utils.pagination import ListArgsError, list_response, parse_uuid
from app.permissions import with_implied
from app.services.rbac_guard import (
    GuardError, guard_error_response, assert_can_grant_roles, assert_can_manage_user,
    assert_admin_remains, assert_no_self_lockout, emit_permissions_changed,
)


USER_SORTABLE = {
    'name': User.name,
    'email': User.email,
    'created_at': User.created_at,
    'last_login': User.last_login,
}
USER_FILTERS = {'is_active': (User.is_active, 'bool'), 'mfa': (User.mfa_enabled, 'bool')}
USER_STATUSES = ('active', 'disabled', 'locked', 'must_change_password')


def _lifecycle_filters(query):
    """status / team_id / role_id filters of the admin user list."""
    args = request.args
    status = args.get('status')
    if status:
        if status not in USER_STATUSES:
            raise ListArgsError(f"invalid status {status!r}; allowed: {', '.join(USER_STATUSES)}", 'invalid_filter')
        now = datetime.now(timezone.utc)
        query = query.filter({
            'active': User.is_active.is_(True),
            'disabled': User.is_active.is_(False),
            'locked': User.locked_until > now,
            'must_change_password': User.must_change_password.is_(True),
        }[status])
    if args.get('team_id'):
        team_id = parse_uuid('team_id', args['team_id'])
        query = query.filter(User.id.in_(
            db.session.query(TeamMember.user_id).filter(TeamMember.team_id == team_id)))
    if args.get('role_id'):
        role_id = parse_uuid('role_id', args['role_id'])
        query = query.filter(User.id.in_(
            db.session.query(UserRole.user_id).filter(UserRole.role_id == role_id)))
    return query


def _guard_or_lifecycle_error(e):
    from app.services.user_lifecycle import LifecycleError
    if isinstance(e, GuardError):
        return guard_error_response(e)
    if isinstance(e, LifecycleError):
        return e.response()
    db.session.rollback()
    from app.services.token_revocation import revocation_failed_response
    return revocation_failed_response()


@api_bp.route('/users', methods=['GET'])
@jwt_required()
@require_permission('users:read')
def list_users():
    """List users in the organization (utils/pagination.py contract; q/search
    over name+email, filters role (name), role_id, is_active, status, team_id
    and mfa)."""
    user = get_current_user()
    query = User.query.filter_by(organization_id=user.organization_id)

    # Role filter is a subquery on the role name, outside the declarative FILTERS.
    role = request.args.get('role')
    if role:
        query = query.filter(User.id.in_(
            db.session.query(UserRole.user_id).join(Role, Role.id == UserRole.role_id).filter(Role.name == role)))
    query = _lifecycle_filters(query)

    return jsonify(list_response(
        query, sortable=USER_SORTABLE, default_sort='-created_at', id_col=User.id,
        filters=USER_FILTERS, search_columns=(User.name, User.email),
        serialize=lambda u: u.to_dict(),
    )), 200


@api_bp.route('/users', methods=['POST'])
@jwt_required()
@require_permission('users:create')
@audit_log('admin_action', 'create_user', 'user')
def create_user():
    """Create a new user in the caller's org.

    Explicit roles need roles:manage; every role (including the default
    Viewer) must be within the caller's own permissions.
    """
    current = get_current_user()
    data = request.get_json(silent=True) or {}

    if not data.get('email') or not data.get('name') or not data.get('password'):
        return jsonify({'error': 'bad_request', 'message': 'Email, name, and password are required'}), 400
    if not isinstance(data['email'], str):
        return jsonify({'error': 'bad_request', 'message': 'Invalid email address'}), 400
    # Login lowercases the email, so store it lowercased (a mixed-case
    # admin-created address could never sign in).
    email = data['email'].strip().lower()

    # Admin-created accounts must still meet email/password policy.
    from app.api.v1.endpoints.auth import validate_password, validate_email
    if not validate_email(email):
        return jsonify({'error': 'bad_request', 'message': 'Invalid email address'}), 400
    valid, message = validate_password(data['password'])
    if not valid:
        return jsonify({'error': 'bad_request', 'message': message}), 400

    if User.query.filter(sa.func.lower(User.email) == email).first():
        return jsonify({'error': 'conflict', 'message': 'Email already exists'}), 409

    role_names = data.get('roles') or ([data['role']] if data.get('role') else [])
    if not isinstance(role_names, list) or not all(isinstance(n, str) for n in role_names):
        return jsonify({'error': 'bad_request', 'message': 'roles must be an array of role names'}), 400
    if role_names and not current.has_permission('roles:manage'):
        return jsonify({
            'error': 'forbidden',
            'message': 'roles:manage permission is required to assign roles'
        }), 403

    # Default to least privilege (Viewer) when no explicit role is given.
    requested = role_names or ['Viewer']
    roles, unknown = [], []
    for role_name in requested:
        role = Role.resolve(role_name, current.organization_id)
        if role is None:
            unknown.append(role_name)
        elif role not in roles:
            roles.append(role)
    if unknown:
        return jsonify({'error': 'unknown_role', 'message': 'Unknown role(s)', 'unknown': unknown}), 400
    try:
        assert_can_grant_roles(current, roles)
    except GuardError as e:
        return guard_error_response(e)

    user = User(
        email=email,
        name=data['name'],
        organization_id=current.organization_id,
        is_active=data.get('is_active', True),
        is_verified=True,  # Admin created users are verified
        organizational_role=data.get('organizational_role', '').strip() or None,
    )
    user.set_password(data['password'])
    db.session.add(user)
    db.session.flush()
    for role in roles:
        db.session.add(UserRole(
            user_id=user.id,
            role_id=role.id,
            organization_id=current.organization_id,
            granted_by=current.id
        ))
    db.session.commit()
    record_changes({}, {'email': user.email, 'name': user.name, 'roles': [r.name for r in roles],
                        'is_active': user.is_active})

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

    if current.has_permission('users:manage'):
        return jsonify(user.to_admin_dict(include_permissions=True)), 200
    return jsonify(user.to_dict(include_permissions=True)), 200


_UPDATABLE_FIELDS = ('name', 'is_active', 'organizational_role', 'password', 'must_change_password')
_DIFF_FIELDS = ('name', 'is_active', 'organizational_role', 'must_change_password', 'deactivation_reason')


@api_bp.route('/users/<uuid:user_id>', methods=['PUT'])
@jwt_required()
@require_permission('users:update')
@audit_log('admin_action', 'update_user', 'user')
def update_user(user_id):
    """Update a user.

    Acting on anyone else requires outranking them (their permissions are a
    subset of yours). Nobody disables themselves or resets their own password
    here (use /auth/change-password). Disabling the last admin is refused.
    With users:manage, `is_active` goes through the lifecycle service
    (disable records who/why and revokes every session; reason optional,
    default "(via update)") and `password` resets it (all sessions revoked;
    optional `must_change_password`). A failed revocation is 503 and nothing
    changes.
    """
    from app.services import user_lifecycle
    from app.services.token_revocation import SessionRevocationError, revoke_all_sessions

    current = get_current_user()
    user = User.query.filter_by(id=user_id, organization_id=current.organization_id).first()

    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    data = request.get_json(silent=True) or {}
    from app.api.v1.endpoints.auth import validate_password
    can_manage = current.has_permission('users:manage')
    if 'is_active' in data and can_manage and not isinstance(data['is_active'], bool):
        return jsonify({'error': 'bad_request', 'message': 'is_active must be a boolean'}), 400
    if 'must_change_password' in data and not isinstance(data['must_change_password'], bool):
        return jsonify({'error': 'bad_request', 'message': 'must_change_password must be a boolean'}), 400
    disabling = can_manage and data.get('is_active') is False and user.is_active
    enabling = can_manage and data.get('is_active') is True and not user.is_active
    resetting = can_manage and 'password' in data

    before = snapshot(user, _DIFF_FIELDS)
    try:
        if any(f in data for f in _UPDATABLE_FIELDS):
            assert_can_manage_user(current, user, 'update')
        if resetting:
            assert_can_manage_user(current, user, 'reset_password')

        if 'name' in data:
            user.name = data['name'].strip()
        if 'organizational_role' in data:
            user.organizational_role = data['organizational_role'].strip() if data['organizational_role'] else None

        # Password reset (users:manage) — same policy as self-service changes, and
        # all of the user's existing sessions are revoked.
        if resetting:
            valid, message = validate_password(data['password'] or '')
            if not valid:
                db.session.rollback()
                return jsonify({'error': 'bad_request', 'message': message}), 400
            user.set_password(data['password'])
            user.failed_login_count = 0
            user.locked_until = None
        if can_manage and 'must_change_password' in data:
            user.must_change_password = data['must_change_password']

        if disabling:
            reason = data.get('reason') if isinstance(data.get('reason'), str) and data['reason'].strip() \
                else '(via update)'
            user_lifecycle.disable_user(current, user, reason)  # revokes sessions
        elif enabling:
            user_lifecycle.enable_user(current, user)
        if resetting and not disabling:
            db.session.flush()
            user_lifecycle.revoke_reset_link(user.id)
            revoke_all_sessions(user, 'password_reset')
    except (GuardError, user_lifecycle.LifecycleError, SessionRevocationError) as e:
        return _guard_or_lifecycle_error(e)

    db.session.commit()
    after = snapshot(user, _DIFF_FIELDS)
    if resetting:
        before['password'], after['password'] = None, 'reset'
    record_changes(before, after, target_email=user.email)

    return jsonify(user.to_dict()), 200


@api_bp.route('/users/<uuid:user_id>', methods=['DELETE'])
@jwt_required()
@require_permission('users:delete')
@audit_log('admin_action', 'delete_user', 'user')
def delete_user(user_id):
    """Delete a user you outrank (never yourself, never the last admin).

    Only users with no attributed records can be deleted: otherwise 409
    `user_has_records` {counts, hint: 'deactivate'} (disable them instead).
    `?anonymize=true` keeps the row but scrubs its personal data.
    """
    from app.services import user_lifecycle
    from app.services.token_revocation import SessionRevocationError

    current = get_current_user()
    user = User.query.filter_by(id=user_id, organization_id=current.organization_id).first()

    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    anonymize = (request.args.get('anonymize') or '').lower() in ('1', 'true', 'yes')
    before = {'email': user.email, 'name': user.name, 'roles': user.role_names, 'is_active': user.is_active}
    try:
        outcome = user_lifecycle.delete_user(current, user, anonymize=anonymize)
    except (GuardError, user_lifecycle.LifecycleError, SessionRevocationError) as e:
        return _guard_or_lifecycle_error(e)
    db.session.commit()
    record_changes(before, {}, outcome=outcome)

    if outcome == 'anonymized':
        return jsonify({'message': 'User anonymized', 'outcome': outcome}), 200
    return jsonify({'message': 'User deleted successfully', 'outcome': outcome}), 200


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
    """Assign a role (system or own org) the caller could grant."""
    current = get_current_user()
    user = User.query.filter_by(id=user_id, organization_id=current.organization_id).first()

    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    data = request.get_json(silent=True) or {}
    role_id = data.get('role_id')

    if not role_id:
        return jsonify({'error': 'bad_request', 'message': 'role_id is required'}), 400
    try:
        role_uuid = uuid.UUID(str(role_id))
    except ValueError:
        return jsonify({'error': 'not_found', 'message': 'Role not found'}), 404

    role = Role.visible_to(current.organization_id).filter(Role.id == role_uuid).first()
    if not role:
        return jsonify({'error': 'not_found', 'message': 'Role not found'}), 404

    try:
        assert_can_grant_roles(current, [role], resource_id=user.id)
        assert_can_manage_user(current, user, 'assign_role')
    except GuardError as e:
        return guard_error_response(e)

    # Check if already assigned
    existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
    if existing:
        return jsonify({'error': 'already_assigned', 'message': 'Role already assigned'}), 409

    user_role = UserRole(
        user_id=user.id,
        role_id=role.id,
        organization_id=current.organization_id,
        granted_by=current.id
    )
    roles_before = user.role_names
    db.session.add(user_role)
    db.session.commit()
    db.session.expire(user, ['user_roles'])
    record_changes({'roles': roles_before}, {'roles': user.role_names}, target_email=user.email)
    emit_permissions_changed([user.id])

    # Push updated roles to Supabase app_metadata
    from app.services.supabase_role_sync import push_roles_to_supabase
    push_roles_to_supabase(user)

    return jsonify({'message': 'Role assigned successfully'}), 201


@api_bp.route('/users/<uuid:user_id>/roles/<uuid:role_id>', methods=['DELETE'])
@jwt_required()
@require_permission('roles:manage')
@audit_log('admin_action', 'revoke_role', 'user')
def revoke_role(user_id, role_id):
    """Revoke a role from a user you outrank, keeping at least one admin and
    never stripping your own admin core."""
    current = get_current_user()
    user = User.query.filter_by(id=user_id, organization_id=current.organization_id).first()

    if not user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    user_role = UserRole.query.filter_by(user_id=user.id, role_id=role_id).first()
    if not user_role:
        return jsonify({'error': 'not_found', 'message': 'Role assignment not found'}), 404

    drop = [(user.id, role_id)]
    try:
        assert_can_manage_user(current, user, 'revoke_role')
        assert_admin_remains(current.organization_id, drop_assignments=drop, resource_id=user.id)
        if user.id == current.id:
            assert_no_self_lockout(current, drop_assignments=drop, resource_id=user.id)
    except GuardError as e:
        return guard_error_response(e)

    roles_before = user.role_names
    db.session.delete(user_role)
    db.session.commit()
    db.session.expire(user, ['user_roles'])
    record_changes({'roles': roles_before}, {'roles': user.role_names}, target_email=user.email)
    emit_permissions_changed([user.id])

    # Push updated roles to Supabase app_metadata
    from app.services.supabase_role_sync import push_roles_to_supabase
    push_roles_to_supabase(user)

    return jsonify({'message': 'Role revoked successfully'}), 200


@api_bp.route('/users/sync-supabase', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'sync_supabase', 'user')
def sync_supabase_users():
    """Fetch users from Supabase and sync them into the default org.

    Supabase sign-ins land in the default organization, so only an admin of
    that org may sync. Existing users of other orgs are never touched
    (counted in `skipped_other_org`). Roles from Supabase app_metadata are
    resolved in the default org and only assigned when within the caller's
    permissions (others are listed in `roles_skipped`); new users without
    assignable roles get Viewer.
    """
    import requests as http_requests

    supabase_url = current_app.config.get('SUPABASE_URL')
    service_key = current_app.config.get('SUPABASE_SERVICE_ROLE_KEY')

    if not supabase_url or not service_key:
        return jsonify({'error': 'not_configured', 'message': 'Supabase service role key not configured'}), 501

    current = get_current_user()
    org = Organization.query.filter_by(slug='default').first()
    if not org or org.id != current.organization_id:
        return jsonify({'error': 'not_default_org',
                        'message': 'Supabase users can only be synced by an administrator of the default organization'}), 403

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
                current_app.logger.error(f"Supabase admin API error: {resp.status_code}")
                return jsonify({'error': 'supabase_error', 'message': 'Failed to fetch Supabase users'}), 502

            data = resp.json()
            users_list = data.get('users', data) if isinstance(data, dict) else data
            if not users_list:
                break
            all_sb_users.extend(users_list)
            if len(users_list) < per_page:
                break
            page += 1

        created = skipped = skipped_other_org = 0
        roles_skipped = []
        viewer_role = Role.resolve('Viewer', org.id)

        from app.services.supabase_role_sync import roles_from_supabase_metadata, assign_roles_from_list

        for sb_user in all_sb_users:
            email = sb_user.get('email')
            if not email:
                continue

            existing = User.query.filter_by(email=email.lower()).first()
            if existing:
                if existing.organization_id != org.id:
                    skipped_other_org += 1
                    continue
                # Update supabase_id if missing
                if not existing.supabase_id and sb_user.get('id'):
                    existing.supabase_id = sb_user['id']
                # Restore roles from Supabase app_metadata if user has none
                if not existing.user_roles:
                    sb_roles = roles_from_supabase_metadata(sb_user)
                    if sb_roles:
                        assign_roles_from_list(existing, sb_roles, organization_id=org.id,
                                               granted_by=current.id, ceiling=current, skipped=roles_skipped)
                skipped += 1
                continue

            user_meta = sb_user.get('user_metadata', {}) or {}
            name = (
                user_meta.get('name')
                or user_meta.get('full_name')
                or user_meta.get('user_name')
                or email.split('@')[0]
            )

            new_user = User(
                email=email.lower(),
                name=name,
                avatar_url=user_meta.get('avatar_url'),
                organization_id=org.id,
                auth_provider='supabase',
                supabase_id=sb_user.get('id', ''),
                is_active=True,
                is_verified=True,
            )
            db.session.add(new_user)
            db.session.flush()

            # Assign roles from Supabase app_metadata, fall back to Viewer
            sb_roles = roles_from_supabase_metadata(sb_user)
            assigned = 0
            if sb_roles:
                assigned = assign_roles_from_list(new_user, sb_roles, organization_id=org.id,
                                                  granted_by=current.id, ceiling=current, skipped=roles_skipped)
            if not assigned and viewer_role and set(viewer_role.permissions or []) <= with_implied(current.permissions):
                db.session.add(UserRole(user_id=new_user.id, role_id=viewer_role.id,
                                        organization_id=org.id, granted_by=current.id))

            created += 1

        db.session.commit()

        return jsonify({
            'message': f'Synced Supabase users: {created} created, {skipped} already existed',
            'created': created,
            'skipped': skipped,
            'skipped_other_org': skipped_other_org,
            'roles_skipped': roles_skipped,
            'total_supabase': len(all_sb_users),
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Supabase sync error: {type(e).__name__}")
        return jsonify({'error': 'server_error', 'message': 'Failed to sync Supabase users'}), 500
