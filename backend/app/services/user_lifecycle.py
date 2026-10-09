"""User account lifecycle: disable/enable, force-logout, unlock, admin
password and MFA resets, login lockout, safe delete and bulk actions.

Conventions
-----------
* Functions stage changes on ``db.session`` and never commit; the endpoint
  commits (bulk actions commit per item). Revocations go through
  ``token_revocation.revoke_all_sessions`` *before* the commit, so a failed
  revocation (SessionRevocationError -> 503 ``revocation_failed``) rolls the
  state change back.
* Privilege checks use ``rbac_guard`` (GuardError -> ``guard_error_response``).
  Other refusals raise :class:`LifecycleError` (status, code, message, details).
* Lockout values come from ``security_policy.lockout_settings(org_id)`` once
  that module exists, else from env ``LOGIN_LOCKOUT_THRESHOLD`` (default 10)
  and ``LOGIN_LOCKOUT_MINUTES`` (default 15), clamped to 3..20 and 1..1440.
* Password-reset links live in Redis only: ``pwd_reset:<sha256>`` -> JSON
  ``{user_id, org_id, created_by}`` and ``pwd_reset_user:<uid>`` -> current
  hash (a new link kills the previous one). TTL ``PASSWORD_RESET_TTL_HOURS``
  (default 24, 1..72).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from app import db
from app.services.rbac_guard import (
    GuardError, assert_admin_remains, assert_can_grant_roles, assert_can_manage_user, assert_no_self_lockout,
)
from app.services.token_revocation import SessionRevocationError, revoke_all_sessions

logger = logging.getLogger(__name__)

LOCKOUT_THRESHOLD_BOUNDS = (3, 20)
LOCKOUT_MINUTES_BOUNDS = (1, 1440)
DEFAULT_LOCKOUT = (10, 15)
RESET_TTL_BOUNDS = (1, 72)
DEFAULT_RESET_TTL_HOURS = 24
MAX_REASON_LENGTH = 500
BULK_MAX = 100
BULK_ACTIONS = ('disable', 'enable', 'force_logout', 'add_role', 'remove_role', 'add_team')
ROLE_BULK_ACTIONS = ('add_role', 'remove_role')
# FK violation / insufficient privilege (append-only trigger) on hard delete.
DELETE_BLOCKING_PGCODES = ('23503', '42501')
# Tables counted as attribution even though their FK cascades.
EXTRA_ATTRIBUTION_COLUMNS = (('incident_assignments', 'user_id'),)

PASSWORD_SPECIALS = '!@#$%^&*().?'


class LifecycleError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}

    def response(self):
        from flask import jsonify
        db.session.rollback()
        return jsonify({'error': self.code, 'message': self.message, **self.details}), self.status


def _now():
    return datetime.now(timezone.utc)


def _redis():
    from app import redis_client
    return redis_client


def _clamp(value, bounds, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(bounds[0], min(bounds[1], value))


# ── Passwords ───────────────────────────────────────────────────────

def generate_password(length: int = 20) -> str:
    """A random password meeting the password policy (one of each class)."""
    from app.api.v1.endpoints.auth import validate_password
    rng = secrets.SystemRandom()
    alphabet = string.ascii_letters + string.digits + PASSWORD_SPECIALS
    while True:
        chars = [secrets.choice(string.ascii_uppercase), secrets.choice(string.ascii_lowercase),
                 secrets.choice(string.digits), secrets.choice(PASSWORD_SPECIALS)]
        chars += [secrets.choice(alphabet) for _ in range(max(length, 12) - len(chars))]
        rng.shuffle(chars)
        candidate = ''.join(chars)
        if validate_password(candidate)[0]:
            return candidate


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


# ── Lockout ─────────────────────────────────────────────────────────

def lockout_settings(org_id) -> tuple[int, int]:
    """(threshold, minutes) for an org, bounded to 3..20 and 1..1440."""
    threshold = minutes = None
    try:
        from app.services import security_policy  # W3-SEC
        threshold, minutes = security_policy.lockout_settings(org_id)
    except (ImportError, AttributeError):
        threshold = os.getenv('LOGIN_LOCKOUT_THRESHOLD', DEFAULT_LOCKOUT[0])
        minutes = os.getenv('LOGIN_LOCKOUT_MINUTES', DEFAULT_LOCKOUT[1])
    return (_clamp(threshold, LOCKOUT_THRESHOLD_BOUNDS, DEFAULT_LOCKOUT[0]),
            _clamp(minutes, LOCKOUT_MINUTES_BOUNDS, DEFAULT_LOCKOUT[1]))


def register_failed_login(user, reason: str) -> bool:
    """Count a failed password/MFA attempt (atomically) and lock the account
    when the threshold is reached. Commits. Returns True if this call locked
    the account. A running lock is never extended."""
    from app.models import User
    threshold, minutes = lockout_settings(user.organization_id)
    now = _now()
    uid = user.id
    # An expired lock starts a fresh window.
    db.session.execute(
        sa.update(User).where(User.id == uid, User.locked_until.isnot(None), User.locked_until <= now)
        .values(failed_login_count=0, locked_until=None)
        .execution_options(synchronize_session=False))
    count = db.session.execute(
        sa.update(User).where(User.id == uid)
        .values(failed_login_count=User.failed_login_count + 1)
        .returning(User.failed_login_count)
        .execution_options(synchronize_session=False)).scalar() or 0
    until = None
    if count >= threshold:
        until = db.session.execute(
            sa.update(User)
            .where(User.id == uid, sa.or_(User.locked_until.is_(None), User.locked_until <= now))
            .values(locked_until=now + timedelta(minutes=minutes))
            .returning(User.locked_until)
            .execution_options(synchronize_session=False)).scalar()
    db.session.commit()
    db.session.expire(user)
    if until is not None:
        from app.middleware.audit import log_security_event
        log_security_event('account_locked', resource_type='user', resource_id=uid, user=user,
                           details={'attempts': count, 'until': until.isoformat(), 'trigger': reason,
                                    'minutes': minutes})
        return True
    return False


def register_successful_login(user) -> None:
    """Reset the lockout counter and stamp last_login (caller commits)."""
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login = _now()


def unlock_user(actor, target) -> None:
    target.failed_login_count = 0
    target.locked_until = None


# ── Reset links (Redis) ─────────────────────────────────────────────

def reset_ttl_hours() -> int:
    return _clamp(os.getenv('PASSWORD_RESET_TTL_HOURS', DEFAULT_RESET_TTL_HOURS), RESET_TTL_BOUNDS,
                  DEFAULT_RESET_TTL_HOURS)


def revoke_reset_link(user_id) -> None:
    """Kill the user's pending reset link, if any (best effort)."""
    client = _redis()
    if client is None:
        return
    try:
        old = client.get(f'pwd_reset_user:{user_id}')
        if old:
            client.delete(f'pwd_reset:{old.decode() if isinstance(old, bytes) else old}')
        client.delete(f'pwd_reset_user:{user_id}')
    except Exception:
        logger.warning('could not revoke reset link for %s', user_id)


def _store_reset_link(actor, target) -> tuple[str, datetime]:
    client = _redis()
    if client is None:
        raise SessionRevocationError('token store unavailable')
    token = secrets.token_urlsafe(32)
    digest = hash_token(token)
    ttl = reset_ttl_hours() * 3600
    payload = json.dumps({'user_id': str(target.id), 'org_id': str(target.organization_id),
                          'created_by': str(actor.id)})
    try:
        old = client.get(f'pwd_reset_user:{target.id}')
        pipe = client.pipeline()
        if old:
            pipe.delete(f'pwd_reset:{old.decode() if isinstance(old, bytes) else old}')
        pipe.setex(f'pwd_reset:{digest}', ttl, payload)
        pipe.setex(f'pwd_reset_user:{target.id}', ttl, digest)
        pipe.execute()
    except Exception as exc:
        raise SessionRevocationError('token store unavailable') from exc
    return token, _now() + timedelta(seconds=ttl)


def consume_reset_token(token: str):
    """Atomically take a reset link: returns its payload dict or None."""
    client = _redis()
    if client is None or not token or not isinstance(token, str) or len(token) > 200:
        return None
    digest = hash_token(token)
    try:
        raw = client.getdel(f'pwd_reset:{digest}')
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    try:
        current = client.get(f'pwd_reset_user:{data.get("user_id")}')
        if current and (current.decode() if isinstance(current, bytes) else current) == digest:
            client.delete(f'pwd_reset_user:{data.get("user_id")}')
    except Exception:
        pass
    return data


# ── Account state ───────────────────────────────────────────────────

def _check_reason(reason) -> str:
    if not isinstance(reason, str) or not reason.strip():
        raise LifecycleError(400, 'bad_request', 'reason is required')
    reason = reason.strip()
    if len(reason) > MAX_REASON_LENGTH:
        raise LifecycleError(400, 'bad_request', f'reason must be at most {MAX_REASON_LENGTH} characters')
    return reason


def disable_user(actor, target, reason) -> None:
    """Deactivate `target` and revoke all its sessions."""
    reason = _check_reason(reason)
    assert_can_manage_user(actor, target, 'disable')
    if not target.is_active:
        raise LifecycleError(409, 'already_disabled', 'User is already disabled')
    assert_admin_remains(actor.organization_id, exclude_users={target.id}, resource_id=target.id)
    target.is_active = False
    target.deactivated_at = _now()
    target.deactivated_by = actor.id
    target.deactivation_reason = reason
    db.session.flush()
    revoke_reset_link(target.id)
    revoke_all_sessions(target, 'disabled')


def enable_user(actor, target) -> None:
    """Reactivate `target`. Old tokens stay dead (the epoch never goes back)."""
    assert_can_manage_user(actor, target, 'enable')
    target.is_active = True
    target.deactivated_at = None
    target.deactivated_by = None
    target.deactivation_reason = None


def force_logout(actor, target) -> None:
    assert_can_manage_user(actor, target, 'force_logout')
    revoke_all_sessions(target, 'force_logout')


def admin_reset_password(actor, target, mode, *, revoke_sessions=True) -> dict:
    """mode 'link' -> {token, accept_path, expires_at}; 'temp' -> {temp_password}.

    The returned secret is shown once and must never be logged."""
    if mode not in ('link', 'temp'):
        raise LifecycleError(400, 'bad_request', "mode must be 'link' or 'temp'")
    if not isinstance(revoke_sessions, bool):
        raise LifecycleError(400, 'bad_request', 'revoke_sessions must be a boolean')
    assert_can_manage_user(actor, target, 'reset_password')
    if not target.is_active:
        raise LifecycleError(409, 'user_disabled', 'Enable the user before resetting the password')

    if mode == 'link':
        token, expires_at = _store_reset_link(actor, target)
        if revoke_sessions:
            revoke_all_sessions(target, 'password_reset')
        return {'mode': 'link', 'token': token, 'accept_path': f'/auth/reset-password#token={token}',
                'expires_at': expires_at.isoformat()}

    temp = generate_password(20)
    target.set_password(temp)
    target.must_change_password = True
    target.failed_login_count = 0
    target.locked_until = None
    db.session.flush()
    revoke_reset_link(target.id)
    revoke_all_sessions(target, 'password_reset')
    return {'mode': 'temp', 'temp_password': temp}


def complete_password_reset(token, new_password):
    """Public reset completion. Returns the user, or raises LifecycleError
    400 `reset_invalid` / `bad_request` (policy). Caller commits."""
    from app.api.v1.endpoints.auth import validate_password
    from app.models import User
    if not isinstance(new_password, str):
        raise LifecycleError(400, 'bad_request', 'new_password is required')
    ok, message = validate_password(new_password)
    if not ok:
        raise LifecycleError(400, 'bad_request', message)
    data = consume_reset_token(token)
    invalid = LifecycleError(400, 'reset_invalid', 'This reset link is invalid or has expired')
    if not data:
        raise invalid
    try:
        user = db.session.get(User, uuid.UUID(str(data.get('user_id'))))
    except (ValueError, TypeError):
        raise invalid
    if user is None or not user.is_active or str(user.organization_id) != str(data.get('org_id')):
        raise invalid
    user.set_password(new_password)
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None
    db.session.flush()
    revoke_all_sessions(user, 'password_reset')
    return user


def reset_mfa(actor, target) -> None:
    if actor.id == target.id:
        raise GuardError(400, 'self_action', 'You cannot reset_mfa your own account',
                         {'action': 'reset_mfa'}, resource_type='user', resource_id=target.id)
    assert_can_manage_user(actor, target, 'reset_mfa')
    if not target.mfa_enabled:
        raise LifecycleError(409, 'mfa_not_enabled', 'MFA is not enabled for this user')
    target.mfa_enabled = False
    target.mfa_secret = None
    target.mfa_backup_codes = None
    db.session.flush()
    revoke_all_sessions(target, 'mfa_reset')


# ── Delete ──────────────────────────────────────────────────────────

def _attribution_columns():
    """[(table, column)] of FKs to users.id that neither cascade nor set null
    (read from the live schema, so tables added later are covered)."""
    insp = sa.inspect(db.session.connection())
    cols = set()
    for (_schema, table), fks in insp.get_multi_foreign_keys().items():
        if table == 'users':
            continue
        for fk in fks:
            if fk.get('referred_table') != 'users' or len(fk.get('constrained_columns') or ()) != 1:
                continue
            ondelete = ((fk.get('options') or {}).get('ondelete') or '').upper()
            if ondelete in ('CASCADE', 'SET NULL', 'SET DEFAULT'):
                continue
            cols.add((table, fk['constrained_columns'][0]))
    cols.update(EXTRA_ATTRIBUTION_COLUMNS)
    return sorted(cols)


def user_reference_counts(user_id) -> dict:
    """{table: rows} attributing records to the user (non-zero only)."""
    counts: dict[str, int] = {}
    for table, column in _attribution_columns():
        t = sa.table(table, sa.column(column))
        n = db.session.execute(
            sa.select(sa.func.count()).select_from(t).where(t.c[column] == user_id)).scalar() or 0
        if n:
            counts[table] = counts.get(table, 0) + int(n)
    return counts


def _has_records(counts=None):
    return LifecycleError(409, 'user_has_records',
                          'This user is referenced by records they authored; deactivate the user instead',
                          {'counts': counts or {}, 'hint': 'deactivate'})


def delete_user(actor, target, *, anonymize=False) -> str:
    """Hard-delete (or anonymize) a user with no attributed records.

    Returns 'deleted' | 'anonymized'. Raises LifecycleError 409
    `user_has_records` {counts, hint:'deactivate'} otherwise."""
    from app.models import TeamMember, UserRole
    assert_can_manage_user(actor, target, 'delete')
    assert_admin_remains(actor.organization_id, exclude_users={target.id}, resource_id=target.id)
    counts = user_reference_counts(target.id)
    if counts:
        raise _has_records(counts)

    revoke_reset_link(target.id)
    revoke_all_sessions(target, 'deleted')
    if anonymize:
        target.email = f'deleted+{target.id}@invalid.local'
        target.name = 'Deleted user'
        for attr in ('password_hash', 'avatar_url', 'supabase_id', 'auth_provider_id', 'mfa_secret',
                     'mfa_backup_codes', 'organizational_role', 'locked_until'):
            setattr(target, attr, None)
        target.mfa_enabled = False
        target.is_active = False
        target.deactivated_at = target.deactivated_at or _now()
        target.deactivated_by = actor.id
        target.deactivation_reason = 'anonymized'
        UserRole.query.filter_by(user_id=target.id).delete(synchronize_session=False)
        TeamMember.query.filter_by(user_id=target.id).delete(synchronize_session=False)
        db.session.flush()
        db.session.expire(target, ['user_roles', 'team_memberships'])
        return 'anonymized'

    try:
        db.session.delete(target)
        db.session.flush()
    except DBAPIError as exc:
        if getattr(getattr(exc, 'orig', None), 'pgcode', None) in DELETE_BLOCKING_PGCODES:
            db.session.rollback()
            raise _has_records({})
        raise
    return 'deleted'


# ── Roles / teams (bulk) ────────────────────────────────────────────

def _role_visible(org_id, role_id):
    from app.models import Role
    return Role.visible_to(org_id).filter(Role.id == role_id).first()


def add_role(actor, target, role) -> bool:
    from app.models import UserRole
    assert_can_grant_roles(actor, [role], resource_id=target.id)
    assert_can_manage_user(actor, target, 'assign_role')
    if UserRole.query.filter_by(user_id=target.id, role_id=role.id).first():
        raise LifecycleError(409, 'already_assigned', 'Role already assigned')
    db.session.add(UserRole(user_id=target.id, role_id=role.id, organization_id=actor.organization_id,
                            granted_by=actor.id))
    return True


def remove_role(actor, target, role) -> bool:
    from app.models import UserRole
    assignment = UserRole.query.filter_by(user_id=target.id, role_id=role.id).first()
    if not assignment:
        raise LifecycleError(409, 'not_assigned', 'Role is not assigned')
    drop = [(target.id, role.id)]
    assert_can_manage_user(actor, target, 'revoke_role')
    assert_admin_remains(actor.organization_id, drop_assignments=drop, resource_id=target.id)
    if target.id == actor.id:
        assert_no_self_lockout(actor, drop_assignments=drop, resource_id=target.id)
    db.session.delete(assignment)
    return True


def add_team(actor, target, team) -> bool:
    from app.models import TeamMember
    assert_can_manage_user(actor, target, 'update')
    if TeamMember.query.filter_by(team_id=team.id, user_id=target.id).first():
        raise LifecycleError(409, 'already_member', 'User is already in the team')
    db.session.add(TeamMember(team_id=team.id, user_id=target.id))
    return True


def parse_bulk(actor, body) -> dict:
    """Validate a bulk request body; returns {action, ids, reason, role, team}."""
    from app.models import Team
    if not isinstance(body, dict):
        raise LifecycleError(400, 'bad_request', 'JSON object body required')
    action = body.get('action')
    if action not in BULK_ACTIONS:
        raise LifecycleError(400, 'bad_request', f"action must be one of {', '.join(BULK_ACTIONS)}")
    raw_ids = body.get('user_ids')
    if not isinstance(raw_ids, list) or not 1 <= len(raw_ids) <= BULK_MAX:
        raise LifecycleError(400, 'bad_request', f'user_ids must list 1..{BULK_MAX} ids')
    try:
        ids = [uuid.UUID(str(v)) for v in raw_ids]
    except (ValueError, TypeError, AttributeError):
        raise LifecycleError(400, 'bad_request', 'user_ids must be UUIDs')
    if len(set(ids)) != len(ids):
        raise LifecycleError(400, 'bad_request', 'user_ids must be unique')
    parsed = {'action': action, 'ids': ids, 'reason': None, 'role': None, 'team': None}
    if action == 'disable':
        parsed['reason'] = _check_reason(body.get('reason'))
    if action in ROLE_BULK_ACTIONS:
        if not actor.has_permission('roles:manage'):
            raise LifecycleError(403, 'forbidden', 'Permission denied. Required: roles:manage')
        try:
            role_id = uuid.UUID(str(body.get('role_id')))
        except (ValueError, TypeError):
            raise LifecycleError(400, 'bad_request', 'role_id must be a UUID')
        parsed['role'] = _role_visible(actor.organization_id, role_id)
        if parsed['role'] is None:
            raise LifecycleError(404, 'not_found', 'Role not found')
    if action == 'add_team':
        try:
            team_id = uuid.UUID(str(body.get('team_id')))
        except (ValueError, TypeError):
            raise LifecycleError(400, 'bad_request', 'team_id must be a UUID')
        parsed['team'] = Team.query.filter_by(id=team_id, organization_id=actor.organization_id).first()
        if parsed['team'] is None:
            raise LifecycleError(404, 'not_found', 'Team not found')
    return parsed


def apply_bulk(actor, parsed) -> dict:
    """Run one action over many users. Each item is its own transaction and
    gets its own audit row (`bulk_<action>`). Returns the response body."""
    from app.middleware.audit import log_audit_event
    from app.models import User
    action = parsed['action']
    request_id = str(uuid.uuid4())
    results = []
    perms_changed = []
    for uid in parsed['ids']:
        item = {'user_id': str(uid), 'status': 'ok'}
        target = User.query.filter_by(id=uid, organization_id=actor.organization_id).first()
        try:
            if target is None:
                item.update(status='error', code='not_found', message='User not found')
            else:
                if action == 'disable':
                    disable_user(actor, target, parsed['reason'])
                elif action == 'enable':
                    enable_user(actor, target)
                elif action == 'force_logout':
                    force_logout(actor, target)
                elif action == 'add_role':
                    add_role(actor, target, parsed['role'])
                elif action == 'remove_role':
                    remove_role(actor, target, parsed['role'])
                elif action == 'add_team':
                    add_team(actor, target, parsed['team'])
                db.session.commit()
                if action in ROLE_BULK_ACTIONS or action == 'add_team':
                    perms_changed.append(target)
        except (GuardError, LifecycleError) as e:
            db.session.rollback()
            item.update(status='skipped', code=e.code, message=e.message)
        except SessionRevocationError:
            db.session.rollback()
            item.update(status='error', code='revocation_failed', message='Sessions could not be revoked')
        except Exception:
            db.session.rollback()
            logger.exception('bulk %s failed for %s', action, uid)
            item.update(status='error', code='server_error', message='Unexpected error')
        details = {'bulk_request_id': request_id, 'result': item['status']}
        if item.get('code'):
            details['code'] = item['code']
        if action == 'disable':
            details['reason'] = parsed['reason']
        if parsed.get('role') is not None:
            details['role'] = parsed['role'].name
        if parsed.get('team') is not None:
            details['team'] = parsed['team'].name
        log_audit_event('admin_action', f'bulk_{action}', 'user', resource_id=uid, details=details, user=actor)
        results.append(item)

    if perms_changed:
        from app.services.rbac_guard import emit_permissions_changed
        emit_permissions_changed([u.id for u in perms_changed])
        if action in ROLE_BULK_ACTIONS:
            from app.services.supabase_role_sync import push_roles_to_supabase
            for u in perms_changed:
                try:
                    push_roles_to_supabase(u)
                except Exception:
                    logger.warning('supabase role push failed for %s', u.id)

    summary = {'ok': 0, 'skipped': 0, 'failed': 0}
    for r in results:
        summary['ok' if r['status'] == 'ok' else 'skipped' if r['status'] == 'skipped' else 'failed'] += 1
    return {'action': action, 'bulk_request_id': request_id, 'results': results, 'summary': summary}


# ── Stats / overview ────────────────────────────────────────────────

def _pending_invites_query(org_id):
    from app.models import UserInvite
    return UserInvite.query.filter(UserInvite.organization_id == org_id, UserInvite.accepted_at.is_(None),
                                   UserInvite.revoked_at.is_(None), UserInvite.expires_at > _now())


def overview_counts(org_id) -> dict:
    """{locked, pending_invites} for the admin overview (/admin/overview)."""
    from app.models import User
    locked = User.query.filter(User.organization_id == org_id, User.locked_until > _now()).count()
    return {'locked': locked, 'pending_invites': _pending_invites_query(org_id).count()}


def user_stats(org_id) -> dict:
    from app.models import Role, User, UserRole
    base = User.query.filter(User.organization_id == org_id)
    by_role = dict(
        db.session.query(Role.name, sa.func.count(sa.distinct(UserRole.user_id)))
        .join(UserRole, UserRole.role_id == Role.id)
        .join(User, User.id == UserRole.user_id)
        .filter(User.organization_id == org_id,
                sa.or_(sa.and_(Role.organization_id.is_(None), Role.is_system.is_(True)),
                       Role.organization_id == org_id))
        .group_by(Role.name).all())
    return {
        'total': base.count(),
        'active': base.filter(User.is_active.is_(True)).count(),
        'disabled': base.filter(User.is_active.is_(False)).count(),
        'mfa_enabled': base.filter(User.mfa_enabled.is_(True)).count(),
        'must_change_password': base.filter(User.must_change_password.is_(True)).count(),
        **overview_counts(org_id),
        'by_role': by_role,
    }


__all__ = [
    'LifecycleError', 'generate_password', 'hash_token', 'lockout_settings', 'register_failed_login',
    'register_successful_login', 'unlock_user', 'disable_user', 'enable_user', 'force_logout',
    'admin_reset_password', 'complete_password_reset', 'reset_mfa', 'revoke_reset_link',
    'user_reference_counts', 'delete_user', 'parse_bulk', 'apply_bulk', 'overview_counts', 'user_stats',
    'add_role', 'remove_role', 'add_team',
]
