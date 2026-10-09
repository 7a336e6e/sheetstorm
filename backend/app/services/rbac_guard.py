"""RBAC guardrails: anti-escalation, hierarchy, last-admin and self guards.

Every admin mutation that changes who can do what runs these checks BEFORE
mutating anything:

- assert_can_grant(caller, perms)      nobody grants a permission they lack
- assert_outranks(caller, target)      nobody acts on a user holding more
- assert_admin_remains(org_id, ...)    an org never loses its last admin
- assert_no_self_lockout(caller, ...)  an admin never strips their own admin core

"Admin" = an active user whose effective permissions include ADMIN_CORE
(users:manage + roles:manage). The last-admin guard serialises per org with
`SELECT ... FOR UPDATE` on the organization row and only fires on a
transition from >=1 to 0 admins, so an org that already lacks an admin is
never bricked.

Endpoints catch GuardError and return `guard_error_response(e)`, which rolls
back (dropping pending changes and the org lock), records a security event
for 403/409 denials and renders `{error: code, message, **details}`.

Error codes: 403 privilege_escalation {missing}, 403 insufficient_privilege
{missing}, 409 last_admin, 409 self_lockout {lost}, 400 self_action {action},
400 use_change_password, 400 unknown_permissions {unknown}.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from flask import jsonify
from sqlalchemy import and_, or_, select

from app import db
from app.permissions import ADMIN_CORE, PLATFORM_ONLY_KEYS, unknown_permissions, with_implied

# Above this many affected users a role edit relies on the next refresh
# instead of pushing `permissions_changed` to each of them.
PERMISSIONS_CHANGED_FANOUT_CAP = 500

_SECURITY_EVENTS = {
    'privilege_escalation': 'privilege_escalation_blocked',
    'insufficient_privilege': 'privilege_escalation_blocked',
    'last_admin': 'last_admin_blocked',
    'self_lockout': 'last_admin_blocked',
}


class GuardError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None,
                 *, resource_type: str | None = None, resource_id=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        self.resource_type = resource_type
        self.resource_id = resource_id


def guard_error_response(e: GuardError):
    """Roll back, log a security event for denials, return (json, status)."""
    from app.middleware.audit import log_security_event

    db.session.rollback()
    event = _SECURITY_EVENTS.get(e.code)
    if event:
        log_security_event(event, resource_type=e.resource_type, resource_id=e.resource_id,
                           details={'code': e.code, **e.details})
    return jsonify({'error': e.code, 'message': e.message, **e.details}), e.status


def lock_org(org_id) -> None:
    """Serialise admin changes within an org until the transaction ends."""
    from app.models import Organization
    db.session.execute(select(Organization.id).where(Organization.id == org_id).with_for_update())


# ── Grants ──────────────────────────────────────────────────────────

def assert_known_permissions(perms: Iterable[str]) -> None:
    unknown = unknown_permissions(perms)
    if unknown:
        raise GuardError(400, 'unknown_permissions', 'Unknown permission key(s)', {'unknown': unknown})


def assert_can_grant(caller, perms: Iterable[str], *, resource_type='role', resource_id=None) -> None:
    """Every permission in `perms` must be held by `caller`."""
    missing = sorted(set(perms or ()) - with_implied(caller.permissions))
    if missing:
        raise GuardError(403, 'privilege_escalation',
                         "You cannot grant permissions you don't hold", {'missing': missing},
                         resource_type=resource_type, resource_id=resource_id)


def assert_can_grant_roles(actor, roles, *, resource_type='user', resource_id=None) -> None:
    """assert_can_grant over the union of the roles' permissions."""
    perms = set()
    for role in roles:
        perms.update(role.permissions or [])
    assert_can_grant(actor, perms, resource_type=resource_type, resource_id=resource_id)


def assert_platform_scope(org, perms: Iterable[str], *, resource_type='role', resource_id=None) -> None:
    """Platform-only permissions may only sit in the platform org's custom roles."""
    from flask import current_app
    if org is not None and org.slug == current_app.config.get('PLATFORM_ORG_SLUG', 'default'):
        return
    blocked = sorted(set(perms or ()) & PLATFORM_ONLY_KEYS)
    if blocked:
        raise GuardError(403, 'privilege_escalation',
                         'Platform-only permissions cannot be granted in this organization',
                         {'missing': [], 'platform_only': blocked},
                         resource_type=resource_type, resource_id=resource_id)


# ── Hierarchy ───────────────────────────────────────────────────────

def assert_outranks(caller, target) -> None:
    """`target` must not hold any permission `caller` lacks."""
    missing = sorted(set(target.permissions) - with_implied(caller.permissions))
    if missing:
        raise GuardError(403, 'insufficient_privilege',
                         'This user holds permissions you do not have', {'missing': missing},
                         resource_type='user', resource_id=target.id)


def assert_can_manage_user(actor, target, action: str) -> None:
    """Self rules + hierarchy for an action on `target`.

    action: 'update' | 'disable' | 'delete' | 'reset_password' | 'assign_role' | 'revoke_role'
    """
    if actor.id == target.id:
        if action == 'reset_password':
            raise GuardError(400, 'use_change_password',
                             'Change your own password via /auth/change-password',
                             resource_type='user', resource_id=target.id)
        if action in ('disable', 'delete'):
            raise GuardError(400, 'self_action', f'You cannot {action} your own account',
                             {'action': action}, resource_type='user', resource_id=target.id)
        return
    assert_outranks(actor, target)


# ── Last admin / self lockout ───────────────────────────────────────

def _effective_permissions(org_id, *, exclude_users=(), drop_assignments=(), role_overrides=None,
                           add_assignments=()) -> dict[str, set[str]]:
    """{user_id: perms} for the org's ACTIVE users, read fresh from the DB,
    with a hypothetical change applied.

    exclude_users:    user ids treated as disabled / deleted
    drop_assignments: (user_id, role_id) pairs treated as revoked
    role_overrides:   {role_id: new permission list}
    add_assignments:  (user_id, permission list) pairs treated as granted
    """
    from app.models import Role, User, UserRole

    rows = db.session.execute(
        select(UserRole.user_id, UserRole.role_id, Role.permissions)
        .join(User, User.id == UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(User.organization_id == org_id, User.is_active.is_(True),
               or_(and_(Role.organization_id.is_(None), Role.is_system.is_(True)),
                   Role.organization_id == org_id))
    ).all()
    excluded = {str(u) for u in exclude_users}
    dropped = {(str(u), str(r)) for u, r in drop_assignments}
    overrides = {str(k): set(v or ()) for k, v in (role_overrides or {}).items()}

    perms: dict[str, set[str]] = defaultdict(set)
    for user_id, role_id, role_perms in rows:
        uid, rid = str(user_id), str(role_id)
        if uid in excluded or (uid, rid) in dropped:
            continue
        perms[uid] |= overrides.get(rid, set(role_perms or ()))
    for user_id, extra in add_assignments:
        if str(user_id) not in excluded:
            perms[str(user_id)] |= set(extra or ())
    return perms


def admin_holders(org_id, **hypothetical) -> set[str]:
    """Ids (str) of active users in the org holding ADMIN_CORE."""
    return {uid for uid, p in _effective_permissions(org_id, **hypothetical).items() if ADMIN_CORE <= p}


def assert_admin_remains(org_id, *, resource_type='user', resource_id=None, **hypothetical) -> None:
    """409 last_admin if the change takes the org from >=1 admins to 0."""
    lock_org(org_id)
    if not admin_holders(org_id):
        return
    if not admin_holders(org_id, **hypothetical):
        raise GuardError(409, 'last_admin',
                         'This change would leave the organization without an active administrator',
                         resource_type=resource_type, resource_id=resource_id)


def assert_no_self_lockout(caller, *, resource_type='user', resource_id=None, **hypothetical) -> None:
    """409 self_lockout if the caller would lose users:manage or roles:manage."""
    lock_org(caller.organization_id)
    uid = str(caller.id)
    before = _effective_permissions(caller.organization_id).get(uid, set())
    after = _effective_permissions(caller.organization_id, **hypothetical).get(uid, set())
    lost = sorted((ADMIN_CORE & before) - after)
    if lost:
        raise GuardError(409, 'self_lockout',
                         'You cannot remove your own administrative permissions; ask another administrator',
                         {'lost': lost}, resource_type=resource_type, resource_id=resource_id)


# ── Notifications ───────────────────────────────────────────────────

def emit_permissions_changed(user_ids) -> None:
    """Tell clients to refetch /auth/me. Call after commit.

    Delegates to realtime.notify_permissions_changed (emits
    `permissions_changed` to `user_<id>`, then disconnects the user's sockets
    so their incident rooms are recomputed on reconnect).
    """
    ids = list(dict.fromkeys(str(u) for u in user_ids))
    if not ids or len(ids) > PERMISSIONS_CHANGED_FANOUT_CAP:
        return
    try:
        from app.services.realtime import notify_permissions_changed
        notify_permissions_changed(ids)
    except Exception:  # never fail the request on a notification
        pass
