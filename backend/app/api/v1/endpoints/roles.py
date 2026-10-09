"""Role and permission-catalog endpoints.

System roles are global and immutable (clone them to customise). Custom
roles belong to one organization; every lookup goes through
`Role.visible_to(org)`, so a foreign role id answers 404.
"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.api.v1 import api_bp
from app import db
from app.models import Organization, Role, User, UserRole
from app.middleware.rbac import require_permission, get_current_user
from app.middleware.audit import audit_log
from app.permissions import GROUPS, PERMISSIONS, PLATFORM_ONLY_KEYS, with_implied
from app.services.rbac_guard import (
    GuardError, guard_error_response, assert_known_permissions, assert_can_grant, assert_platform_scope,
    assert_admin_remains, assert_no_self_lockout, emit_permissions_changed,
)
from app.utils.audit_diff import record_changes, snapshot

_ROLE_AUDIT_FIELDS = ('name', 'description', 'permissions')


@api_bp.route('/permissions', methods=['GET'])
@jwt_required()
def list_permissions():
    """The permission catalog (static metadata; any authenticated user)."""
    if not get_current_user():
        return jsonify({'error': 'unauthorized', 'message': 'Authentication required'}), 401
    return jsonify({
        'groups': [{'key': k, 'label': v} for k, v in GROUPS.items()],
        'items': [p.to_dict() for p in PERMISSIONS],
    }), 200


@api_bp.route('/roles', methods=['GET'])
@jwt_required()
@require_permission('users:read')
def list_roles():
    """System roles plus the caller's org roles."""
    user = get_current_user()
    roles = Role.visible_to(user.organization_id).order_by(Role.is_system.desc(), Role.name).all()
    counts = _user_counts(user.organization_id)
    return jsonify({'items': [_role_to_dict(r, user, counts.get(r.id, 0)) for r in roles]}), 200


@api_bp.route('/roles/<uuid:role_id>', methods=['GET'])
@jwt_required()
@require_permission('users:read')
def get_role(role_id):
    user = get_current_user()
    role = _visible_role(user, role_id)
    if not role:
        return _not_found()
    return jsonify(_role_to_dict(role, user, _user_counts(user.organization_id).get(role.id, 0))), 200


@api_bp.route('/roles', methods=['POST'])
@jwt_required()
@require_permission('roles:manage')
@audit_log('admin_action', 'create', 'role')
def create_role():
    """Create a custom role in the caller's organization."""
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        name, description, permissions = _validate_role_body(data, user, require_all=True)
        assert_can_grant(user, permissions)
        assert_platform_scope(db.session.get(Organization, user.organization_id), permissions)
    except GuardError as e:
        return guard_error_response(e)
    except _BadRequest as e:
        return e.response()

    role = Role(name=name, description=description, permissions=permissions,
                is_system=False, organization_id=user.organization_id)
    db.session.add(role)
    if not _commit_or_conflict():
        return _name_conflict()
    record_changes({}, snapshot(role, _ROLE_AUDIT_FIELDS))
    return jsonify(_role_to_dict(role, user, 0)), 201


@api_bp.route('/roles/<uuid:role_id>', methods=['PUT'])
@jwt_required()
@require_permission('roles:manage')
@audit_log('admin_action', 'update', 'role')
def update_role(role_id):
    """Update a custom role. Old AND new permissions must be within the caller's."""
    user = get_current_user()
    role = _visible_role(user, role_id)
    if not role:
        return _not_found()
    if role.organization_id is None:
        return jsonify({'error': 'system_role_immutable',
                        'message': 'System roles cannot be changed; clone the role and edit the copy'}), 403

    data = request.get_json(silent=True) or {}
    try:
        name, description, permissions = _validate_role_body(data, user, exclude_id=role.id)
        assert_can_grant(user, role.permissions or [], resource_id=role.id)
        if permissions is not None:
            assert_can_grant(user, permissions, resource_id=role.id)
            assert_platform_scope(db.session.get(Organization, user.organization_id), permissions,
                                  resource_id=role.id)
            overrides = {role.id: permissions}
            assert_admin_remains(user.organization_id, role_overrides=overrides,
                                 resource_type='role', resource_id=role.id)
            assert_no_self_lockout(user, role_overrides=overrides, resource_type='role', resource_id=role.id)
    except GuardError as e:
        return guard_error_response(e)
    except _BadRequest as e:
        return e.response()

    before = snapshot(role, _ROLE_AUDIT_FIELDS)
    if name is not None:
        role.name = name
    if description is not None:
        role.description = description
    if permissions is not None:
        role.permissions = permissions
    holders = [uid for (uid,) in db.session.query(UserRole.user_id).filter(UserRole.role_id == role.id).all()]
    if not _commit_or_conflict():
        return _name_conflict()
    changes = record_changes(before, snapshot(role, _ROLE_AUDIT_FIELDS))
    if 'permissions' in changes:
        emit_permissions_changed(holders)
    return jsonify(_role_to_dict(role, user, len(holders))), 200


@api_bp.route('/roles/<uuid:role_id>/clone', methods=['POST'])
@jwt_required()
@require_permission('roles:manage')
@audit_log('admin_action', 'clone', 'role')
def clone_role(role_id):
    """Copy a visible role (system or own org) into a new custom role.

    Platform-only permissions are dropped when cloning outside the platform
    org (they would be ineffective there); the response lists them.
    """
    user = get_current_user()
    source = _visible_role(user, role_id)
    if not source:
        return _not_found()
    data = request.get_json(silent=True) or {}
    org = db.session.get(Organization, user.organization_id)
    try:
        name, description, _ = _validate_role_body(
            {'name': data.get('name'), 'description': data.get('description', source.description or '')},
            user, require_all=True, permissions_required=False)
        assert_can_grant(user, source.permissions or [], resource_id=source.id)
    except GuardError as e:
        return guard_error_response(e)
    except _BadRequest as e:
        return e.response()

    permissions = sorted(set(source.permissions or []))
    dropped = []
    try:
        assert_platform_scope(org, permissions)
    except GuardError:
        dropped = sorted(set(permissions) & PLATFORM_ONLY_KEYS)
        permissions = [p for p in permissions if p not in dropped]

    role = Role(name=name, description=description, permissions=permissions,
                is_system=False, organization_id=user.organization_id)
    db.session.add(role)
    if not _commit_or_conflict():
        return _name_conflict()
    record_changes({}, snapshot(role, _ROLE_AUDIT_FIELDS), cloned_from=str(source.id))
    body = _role_to_dict(role, user, 0)
    body['cloned_from'] = str(source.id)
    if dropped:
        body['dropped_permissions'] = dropped
    return jsonify(body), 201


@api_bp.route('/roles/<uuid:role_id>', methods=['DELETE'])
@jwt_required()
@require_permission('roles:manage')
@audit_log('admin_action', 'delete', 'role')
def delete_role(role_id):
    """Delete an unassigned custom role of the caller's org."""
    user = get_current_user()
    role = _visible_role(user, role_id)
    if not role:
        return _not_found()
    if role.organization_id is None:
        return jsonify({'error': 'system_role_immutable', 'message': 'System roles cannot be deleted'}), 403
    try:
        assert_can_grant(user, role.permissions or [], resource_id=role.id)
    except GuardError as e:
        return guard_error_response(e)

    assignments = UserRole.query.filter_by(role_id=role.id).count()
    if assignments > 0:
        return jsonify({
            'error': 'conflict',
            'message': f'Cannot delete role "{role.name}" — it is assigned to {assignments} user(s). Reassign them first.'
        }), 409

    record_changes(snapshot(role, _ROLE_AUDIT_FIELDS), {})
    db.session.delete(role)
    db.session.commit()
    return jsonify({'message': 'Role deleted'}), 200


# ── helpers ─────────────────────────────────────────────────────────

class _BadRequest(Exception):
    def __init__(self, status, payload):
        super().__init__(payload.get('message'))
        self.status, self.payload = status, payload

    def response(self):
        return jsonify(self.payload), self.status


def _validate_role_body(data, user, *, require_all=False, permissions_required=True, exclude_id=None):
    """-> (name|None, description|None, sorted permissions|None); raises _BadRequest / GuardError."""
    name = description = permissions = None

    if require_all or 'name' in data:
        raw = data.get('name')
        name = raw.strip() if isinstance(raw, str) else ''
        if not 1 <= len(name) <= 100:
            raise _BadRequest(400, {'error': 'validation_error', 'message': 'Name must be 1-100 characters',
                                    'fields': {'name': 'Name must be 1-100 characters'}})
        system_clash = Role.query.filter(Role.organization_id.is_(None),
                                         func.lower(Role.name) == name.lower()).first()
        if system_clash:
            raise _BadRequest(409, {'error': 'conflict',
                                    'message': f'"{system_clash.name}" is a system role name'})
        q = Role.query.filter(Role.organization_id == user.organization_id, func.lower(Role.name) == name.lower())
        if exclude_id is not None:
            q = q.filter(Role.id != exclude_id)
        if q.first():
            raise _BadRequest(409, {'error': 'conflict', 'message': 'A role with this name already exists'})

    if require_all or 'description' in data:
        raw = data.get('description') or ''
        if not isinstance(raw, str) or len(raw) > 500:
            raise _BadRequest(400, {'error': 'validation_error', 'message': 'Description must be at most 500 characters',
                                    'fields': {'description': 'Description must be at most 500 characters'}})
        description = raw.strip()

    if (require_all and permissions_required) or 'permissions' in data:
        raw = data.get('permissions', [])
        if not isinstance(raw, list) or not all(isinstance(p, str) for p in raw):
            raise _BadRequest(400, {'error': 'validation_error', 'message': 'Permissions must be an array of strings',
                                    'fields': {'permissions': 'Permissions must be an array of strings'}})
        assert_known_permissions(raw)
        permissions = sorted(set(raw))

    return name, description, permissions


def _visible_role(user, role_id):
    return Role.visible_to(user.organization_id).filter(Role.id == role_id).first()


def _user_counts(org_id):
    rows = (db.session.query(UserRole.role_id, func.count(func.distinct(UserRole.user_id)))
            .join(User, User.id == UserRole.user_id)
            .filter(User.organization_id == org_id)
            .group_by(UserRole.role_id).all())
    return dict(rows)


def _commit_or_conflict():
    """Commit; False on a unique-name race (partial unique indexes)."""
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def _not_found():
    return jsonify({'error': 'not_found', 'message': 'Role not found'}), 404


def _name_conflict():
    return jsonify({'error': 'conflict', 'message': 'A role with this name already exists'}), 409


def _role_to_dict(role, caller, user_count):
    perms = role.permissions or []
    caller_perms = with_implied(caller.permissions)
    return {
        'id': str(role.id),
        'name': role.name,
        'description': role.description or '',
        'permissions': perms,
        'is_system': role.organization_id is None and bool(role.is_system),
        'organization_id': str(role.organization_id) if role.organization_id else None,
        'user_count': user_count,
        'editable': (role.organization_id is not None and 'roles:manage' in caller_perms
                     and set(perms) <= caller_perms),
        'created_at': role.created_at.isoformat() if role.created_at else None,
    }
