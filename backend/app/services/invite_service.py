"""User invitations: create, look up, accept, revoke.

The one-time token (``secrets.token_urlsafe(32)``) is returned once at
creation; only its SHA-256 is stored. Acceptance re-checks everything that
may have changed since the invite was issued (inviter still active and still
allowed to grant the stored roles, roles/teams still present, email still
free) and every failure surfaces as one generic ``InviteInvalid``.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app import db
from app.services.rbac_guard import GuardError, assert_can_grant_roles
from app.services.user_lifecycle import LifecycleError, hash_token

MAX_PENDING_PER_ORG = 500
MAX_EXPIRY_DAYS = 7
DEFAULT_ROLE = 'Viewer'
INVALID_MESSAGE = 'This invitation is invalid or has expired'


class InviteInvalid(Exception):
    """Any reason an invite cannot be looked up or accepted (one message)."""


def _now():
    return datetime.now(timezone.utc)


def _uuid_list(values, name):
    if values is None:
        return []
    if not isinstance(values, list):
        raise LifecycleError(400, 'bad_request', f'{name} must be an array of ids')
    try:
        out = [uuid.UUID(str(v)) for v in values]
    except (ValueError, TypeError, AttributeError):
        raise LifecycleError(400, 'bad_request', f'{name} must contain UUIDs')
    return list(dict.fromkeys(out))


def _optional_str(value, name, max_len):
    if value is None:
        return None
    if not isinstance(value, str):
        raise LifecycleError(400, 'bad_request', f'{name} must be a string')
    value = value.strip()
    if len(value) > max_len:
        raise LifecycleError(400, 'bad_request', f'{name} must be at most {max_len} characters')
    return value or None


def _roles_for(org_id, role_ids):
    """Roles (visible to the org) for stored ids; empty -> [the security
    policy's default role] (Viewer unless the org chose another
    non-privileged role)."""
    from app.models import Role
    if not role_ids:
        from app.services import security_policy
        role = security_policy.default_role(security_policy.get_policy(org_id), org_id) \
            or Role.resolve(DEFAULT_ROLE, org_id)
        return [role] if role else []
    return Role.visible_to(org_id).filter(Role.id.in_(role_ids)).all()


def pending_query(org_id):
    from app.models import UserInvite
    return UserInvite.query.filter(UserInvite.organization_id == org_id, UserInvite.accepted_at.is_(None),
                                   UserInvite.revoked_at.is_(None))


def create_invite(actor, data: dict):
    """Validate and create an invite. Returns (invite, token, superseded_id).

    data: {email, name?, role_ids?, team_ids?, organizational_role?, expires_in_days?}"""
    from app.api.v1.endpoints.auth import validate_email
    from app.models import Team, User, UserInvite

    if not isinstance(data, dict):
        raise LifecycleError(400, 'bad_request', 'JSON object body required')
    email = data.get('email')
    if not isinstance(email, str) or not email.strip():
        raise LifecycleError(400, 'bad_request', 'email is required')
    email = email.strip().lower()
    if len(email) > 255 or not validate_email(email):
        raise LifecycleError(400, 'bad_request', 'Invalid email address')
    from app.services import security_policy
    if not security_policy.check_email_domain(email, security_policy.get_policy(actor.organization_id)):
        raise LifecycleError(400, 'email_domain_not_allowed',
                             'This email domain is not allowed by the security policy')
    name = _optional_str(data.get('name'), 'name', 255)
    org_role = _optional_str(data.get('organizational_role'), 'organizational_role', 150)
    days = data.get('expires_in_days', MAX_EXPIRY_DAYS)
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_EXPIRY_DAYS:
        raise LifecycleError(400, 'bad_request', f'expires_in_days must be an integer 1..{MAX_EXPIRY_DAYS}')
    role_ids = _uuid_list(data.get('role_ids'), 'role_ids')
    team_ids = _uuid_list(data.get('team_ids'), 'team_ids')
    org_id = actor.organization_id

    if role_ids and not actor.has_permission('roles:manage'):
        raise LifecycleError(403, 'forbidden', 'roles:manage permission is required to assign roles')
    roles = _roles_for(org_id, role_ids)
    if role_ids and len(roles) != len(role_ids):
        found = {r.id for r in roles}
        raise LifecycleError(400, 'unknown_role', 'Unknown role(s)',
                             {'unknown': [str(r) for r in role_ids if r not in found]})
    assert_can_grant_roles(actor, roles, resource_type='user_invite')

    if team_ids:
        found = {t.id for t in Team.query.filter(Team.organization_id == org_id, Team.id.in_(team_ids))}
        if len(found) != len(team_ids):
            raise LifecycleError(400, 'invalid_team', 'Unknown team(s)',
                                 {'unknown': [str(t) for t in team_ids if t not in found]})

    existing = User.query.filter(sa.func.lower(User.email) == email).first()
    if existing is not None and existing.organization_id == org_id:
        raise LifecycleError(409, 'already_member', 'A user with this email is already a member')
    # A user of another org is not revealed here: acceptance fails generically.

    previous = pending_query(org_id).filter(sa.func.lower(UserInvite.email) == email).with_for_update().first()
    pending = pending_query(org_id).filter(UserInvite.expires_at > _now()).count()
    if pending - (1 if previous is not None and previous.status == 'pending' else 0) >= MAX_PENDING_PER_ORG:
        raise LifecycleError(409, 'too_many_pending', f'At most {MAX_PENDING_PER_ORG} pending invites per organization')

    superseded_id = None
    now = _now()
    if previous is not None:
        previous.revoked_at = now
        previous.revoked_by = actor.id
        superseded_id = str(previous.id)
        db.session.flush()

    token = secrets.token_urlsafe(32)
    invite = UserInvite(
        organization_id=org_id, email=email, name=name, organizational_role=org_role,
        role_ids=[str(r) for r in role_ids], team_ids=[str(t) for t in team_ids],
        token_hash=hash_token(token), created_at=now, expires_at=now + timedelta(days=days),
        created_by=actor.id,
    )
    db.session.add(invite)
    db.session.flush()
    return invite, token, superseded_id


def revoke_invite(actor, invite) -> None:
    if invite.accepted_at:
        raise LifecycleError(409, 'already_accepted', 'The invitation was already accepted')
    if invite.revoked_at is None:
        invite.revoked_at = _now()
        invite.revoked_by = actor.id


def _find(token, *, lock=False):
    from app.models import UserInvite
    if not token or not isinstance(token, str) or len(token) > 200:
        return None
    q = UserInvite.query.filter(UserInvite.token_hash == hash_token(token))
    if lock:
        q = q.with_for_update()
    return q.first()


def lookup_invite(token):
    """The pending, unexpired invite for `token`, or None."""
    invite = _find(token)
    if invite is None or invite.status != 'pending':
        return None
    return invite


def accept_invite(token, name, password):
    """Create the invited user. Returns it (caller commits). Raises
    InviteInvalid (generic) or LifecycleError 400 for bad name/password."""
    from app.models import Team, TeamMember, User, UserRole
    from app.services import security_policy

    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 255:
        raise LifecycleError(400, 'bad_request', 'name must be 1..255 characters')
    if not isinstance(password, str):
        raise LifecycleError(400, 'bad_request', 'password is required')
    # Code-default rules first (no invite lookup needed); the invite's org
    # policy is applied by set_password below.
    ok, messages = security_policy.validate_password(password)
    if not ok:
        raise LifecycleError(400, 'bad_request', ' '.join(messages), {'violations': messages})

    invite = _find(token, lock=True)
    if invite is None or invite.status != 'pending':
        raise InviteInvalid()
    inviter = db.session.get(User, invite.created_by) if invite.created_by else None
    if inviter is None or not inviter.is_active or inviter.organization_id != invite.organization_id:
        raise InviteInvalid()

    role_ids = [uuid.UUID(r) for r in invite.role_ids or []]
    roles = _roles_for(invite.organization_id, role_ids)  # roles deleted since are dropped
    if role_ids and not roles:
        roles = _roles_for(invite.organization_id, [])
    if role_ids and not inviter.has_permission('roles:manage'):
        raise InviteInvalid()
    try:
        assert_can_grant_roles(inviter, roles)
    except GuardError:
        raise InviteInvalid()

    if User.query.filter(sa.func.lower(User.email) == invite.email.lower()).first() is not None:
        raise InviteInvalid()
    # The domain allowlist may have been tightened since the invite was sent.
    if not security_policy.check_email_domain(invite.email, security_policy.get_policy(invite.organization_id)):
        raise InviteInvalid()

    user = User(email=invite.email.lower(), name=name.strip(), organization_id=invite.organization_id,
                auth_provider='local', is_active=True, is_verified=True,
                organizational_role=invite.organizational_role)
    try:
        security_policy.set_password(user, password, enforce_history=False)
    except security_policy.PasswordPolicyError as e:
        raise LifecycleError(400, 'bad_request', e.message, {'violations': e.messages})
    db.session.add(user)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise InviteInvalid()
    for role in roles:
        db.session.add(UserRole(user_id=user.id, role_id=role.id, organization_id=invite.organization_id,
                                granted_by=inviter.id))
    team_ids = [uuid.UUID(t) for t in invite.team_ids or []]
    if team_ids:
        for team in Team.query.filter(Team.organization_id == invite.organization_id, Team.id.in_(team_ids)):
            db.session.add(TeamMember(team_id=team.id, user_id=user.id))
    invite.accepted_at = _now()
    invite.accepted_user_id = user.id
    db.session.flush()
    return user


def serialize(invites):
    """to_dict() for a list of invites with role/team names and creators resolved."""
    from app.models import Role, Team, User
    role_ids, team_ids, user_ids = set(), set(), set()
    for inv in invites:
        role_ids.update(inv.role_ids or [])
        team_ids.update(inv.team_ids or [])
        if inv.created_by:
            user_ids.add(inv.created_by)
    roles = {str(r.id): r.name for r in Role.query.filter(Role.id.in_(role_ids))} if role_ids else {}
    teams = {str(t.id): t.name for t in Team.query.filter(Team.id.in_(team_ids))} if team_ids else {}
    users = {u.id: u.name for u in User.query.filter(User.id.in_(user_ids))} if user_ids else {}
    out = []
    for inv in invites:
        out.append(inv.to_dict(
            roles=[{'id': r, 'name': roles[r]} for r in inv.role_ids or [] if r in roles],
            teams=[{'id': t, 'name': teams[t]} for t in inv.team_ids or [] if t in teams],
            created_by={'id': str(inv.created_by), 'name': users.get(inv.created_by)} if inv.created_by else None,
        ))
    return out


__all__ = ['InviteInvalid', 'INVALID_MESSAGE', 'MAX_PENDING_PER_ORG', 'create_invite', 'revoke_invite',
           'lookup_invite', 'accept_invite', 'pending_query', 'serialize']
