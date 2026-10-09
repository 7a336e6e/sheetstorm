"""Organization security policy: password rules, lockout values, MFA
requirement, token lifetimes and provisioning (allowed email domains,
self-registration, default role).

Storage: one ``organization_security_policies`` row per org (``policy``
JSONB + optimistic ``version``). No row means the code defaults below, which
reproduce the behaviour before the policy existed (registration is closed by
default, _integration.md C11).

Single entry points (_integration.md §1 #20, #21):

* :func:`set_password` — EVERY password write (register, change, admin
  create, admin reset, temp password, invite accept, reset completion, seed).
* :func:`validate_password` — rules only (``auth.validate_password`` is a
  thin wrapper over the code defaults).
* :func:`lockout_settings` — read by ``user_lifecycle`` (it owns the counter
  and the lock itself).

MFA enforcement and password expiry are DB-derived per request: the
``mfa_enrollment_required`` restriction (middleware/account_state.py) uses
:func:`mfa_enrollment_required`; an expired password sets
``users.must_change_password`` at sign-in/refresh, which the
``password_change_required`` restriction then enforces.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError, field_validator

logger = logging.getLogger(__name__)

PASSWORD_MAX_BYTES = 72  # bcrypt ignores everything after 72 bytes
HISTORY_MAX = 24
MAX_DOMAINS = 50
SECTIONS = ('password', 'lockout', 'mfa', 'session', 'provisioning')
MFA_SCOPES = ('none', 'privileged', 'all')
_MFA_RANK = {'none': 0, 'privileged': 1, 'all': 2}
_DOMAIN_RE = re.compile(r'^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$')


# ── Schema (pydantic v2, extra='forbid') ────────────────────────────────

class _Section(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PasswordPolicy(_Section):
    min_length: StrictInt = Field(12, ge=12, le=PASSWORD_MAX_BYTES)
    require_upper: StrictBool = True
    require_lower: StrictBool = True
    require_digit: StrictBool = True
    require_symbol: StrictBool = True
    history_count: StrictInt = Field(0, ge=0, le=HISTORY_MAX)
    max_age_days: StrictInt = Field(0, ge=0, le=730)

    @field_validator('max_age_days')
    @classmethod
    def _age(cls, v):
        if v != 0 and v < 30:
            raise ValueError('max_age_days must be 0 (off) or 30..730')
        return v


class LockoutPolicy(_Section):
    threshold: StrictInt = Field(10, ge=3, le=20)
    duration_minutes: StrictInt = Field(15, ge=1, le=1440)


class MfaPolicy(_Section):
    required_for: Literal['none', 'privileged', 'all'] = 'none'
    grace_days: StrictInt = Field(7, ge=0, le=90)
    # Server-managed: set when required_for widens, cleared at 'none'.
    enforced_since: Optional[datetime] = None


class SessionPolicy(_Section):
    access_token_minutes: StrictInt = Field(60, ge=5, le=60)
    refresh_token_days: StrictInt = Field(7, ge=1, le=30)


class ProvisioningPolicy(_Section):
    allowed_email_domains: List[str] = Field(default_factory=list)
    # Only meaningful for the platform org (self-registration lands there).
    registration_enabled: StrictBool = False
    default_role: str = Field('Viewer', min_length=1, max_length=100)

    @field_validator('allowed_email_domains')
    @classmethod
    def _domains(cls, v):
        if len(v) > MAX_DOMAINS:
            raise ValueError(f'At most {MAX_DOMAINS} domains')
        out = []
        for raw in v:
            if not isinstance(raw, str):
                raise ValueError('Domains must be strings')
            d = raw.strip().lower().lstrip('@')
            if not _DOMAIN_RE.match(d):
                raise ValueError(f'Invalid domain: {raw[:100]!r}')
            if d not in out:
                out.append(d)
        return out

    @field_validator('default_role')
    @classmethod
    def _role(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('default_role is required')
        return v


class SecurityPolicy(_Section):
    password: PasswordPolicy = Field(default_factory=PasswordPolicy)
    lockout: LockoutPolicy = Field(default_factory=LockoutPolicy)
    mfa: MfaPolicy = Field(default_factory=MfaPolicy)
    session: SessionPolicy = Field(default_factory=SessionPolicy)
    provisioning: ProvisioningPolicy = Field(default_factory=ProvisioningPolicy)


_SECTION_MODELS = {
    'password': PasswordPolicy, 'lockout': LockoutPolicy, 'mfa': MfaPolicy,
    'session': SessionPolicy, 'provisioning': ProvisioningPolicy,
}

DEFAULT_POLICY = SecurityPolicy()  # static code defaults (see default_policy())


def _env_int(name, default, lo, hi):
    import os
    try:
        value = int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def default_policy() -> SecurityPolicy:
    """Defaults for an org without a stored value: the code defaults, except
    lockout, whose defaults stay configurable by env
    (LOGIN_LOCKOUT_THRESHOLD 3..20, default 10; LOGIN_LOCKOUT_MINUTES
    1..1440, default 15) as before the policy existed."""
    return SecurityPolicy(lockout=LockoutPolicy(
        threshold=_env_int('LOGIN_LOCKOUT_THRESHOLD', 10, 3, 20),
        duration_minutes=_env_int('LOGIN_LOCKOUT_MINUTES', 15, 1, 1440)))

# Bounds for the admin UI (the schema above is authoritative).
BOUNDS = {
    'password.min_length': {'min': 12, 'max': PASSWORD_MAX_BYTES},
    'password.history_count': {'min': 0, 'max': HISTORY_MAX},
    'password.max_age_days': {'min': 30, 'max': 730, 'off': 0},
    'lockout.threshold': {'min': 3, 'max': 20},
    'lockout.duration_minutes': {'min': 1, 'max': 1440},
    'mfa.grace_days': {'min': 0, 'max': 90},
    'session.access_token_minutes': {'min': 5, 'max': 60},
    'session.refresh_token_days': {'min': 1, 'max': 30},
    'provisioning.allowed_email_domains': {'max_items': MAX_DOMAINS},
}


class PolicyValidationError(Exception):
    """400 ``validation_error`` with ``fields`` {dotted.path: message}."""

    def __init__(self, fields: dict, message: str = 'Invalid security policy'):
        super().__init__(message)
        self.fields = fields
        self.message = message


class PasswordPolicyError(Exception):
    """A password violates the policy. ``messages`` lists every violation."""

    def __init__(self, messages):
        self.messages = list(messages) or ['Password does not meet the password policy']
        super().__init__(self.message)

    @property
    def message(self) -> str:
        return ' '.join(self.messages)

    def response(self):
        from flask import jsonify
        return jsonify({'error': 'bad_request', 'code': 'password_policy', 'message': self.message,
                        'violations': self.messages}), 400


def _now():
    return datetime.now(timezone.utc)


def _aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ── Loading ─────────────────────────────────────────────────────────────

def parse_stored(doc) -> SecurityPolicy:
    """Policy from a stored document. Lenient: an unreadable section falls
    back to its defaults (logged) instead of failing every sign-in."""
    doc = doc if isinstance(doc, dict) else {}
    base = default_policy()
    sections = {}
    for name, model in _SECTION_MODELS.items():
        raw = doc.get(name)
        if raw is None:
            continue
        try:
            sections[name] = model.model_validate(raw)
        except ValidationError:
            logger.error('security policy: stored section %r is invalid; using defaults', name)
    return base.model_copy(update=sections)


def platform_org():
    """The platform organization (config PLATFORM_ORG_SLUG), or None."""
    from flask import current_app
    from app.models import Organization
    slug = current_app.config.get('PLATFORM_ORG_SLUG', 'default')
    return Organization.query.filter_by(slug=slug).first()


def is_platform_org(org) -> bool:
    from flask import current_app
    return org is not None and org.slug == current_app.config.get('PLATFORM_ORG_SLUG', 'default')


def policy_row(org_id):
    from app.models import OrganizationSecurityPolicy
    if not org_id:
        return None
    return OrganizationSecurityPolicy.query.filter_by(organization_id=org_id).first()


def _memo():
    """Per-request memo (never shared across requests or tests)."""
    from flask import g, has_request_context
    if not has_request_context():
        return None
    memo = getattr(g, '_security_policies', None)
    if memo is None:
        memo = g._security_policies = {}
    return memo


def invalidate_cache() -> None:
    from flask import g, has_request_context
    if has_request_context():
        g.pop('_security_policies', None)


def get_policy(org_id) -> SecurityPolicy:
    """The org's policy (row or defaults). Memoised per request."""
    memo = _memo()
    key = str(org_id) if org_id else None
    if memo is not None and key in memo:
        return memo[key]
    row = policy_row(org_id)
    policy = parse_stored(row.policy if row is not None else None)
    if memo is not None:
        memo[key] = policy
    return policy


def platform_policy() -> SecurityPolicy:
    org = platform_org()
    return get_policy(org.id) if org is not None else default_policy()


def serialize(policy: SecurityPolicy) -> dict:
    return policy.model_dump(mode='json')


# ── Update ──────────────────────────────────────────────────────────────

def _field_errors(exc: ValidationError, prefix='') -> dict:
    out = {}
    for err in exc.errors():
        path = '.'.join(str(p) for p in err['loc'])
        out[f'{prefix}{path}' if path else prefix.rstrip('.') or 'policy'] = err['msg']
    return out


def _flat(policy: SecurityPolicy) -> dict:
    data = serialize(policy)
    return {f'{s}.{k}': v for s in SECTIONS for k, v in data[s].items()}


def policy_changes(before: SecurityPolicy, after: SecurityPolicy) -> dict:
    """Audit diff in the shared shape ({field: {from, to}}, lists ->
    {added, removed}). Built here because the generic differ redacts any key
    containing "password"/"token", and the policy holds no secrets."""
    b, a = _flat(before), _flat(after)
    changes = {}
    for key in sorted(set(b) | set(a)):
        if b.get(key) == a.get(key):
            continue
        if isinstance(b.get(key), list) or isinstance(a.get(key), list):
            old, new = b.get(key) or [], a.get(key) or []
            changes[key] = {'added': [v for v in new if v not in old],
                            'removed': [v for v in old if v not in new]}
        else:
            changes[key] = {'from': b.get(key), 'to': a.get(key)}
    return changes


def update_policy(org, data, actor):
    """Validate and stage a policy update for `org` (caller checks the
    version precondition first and commits). `data` may hold any subset of
    sections and fields; unspecified fields keep their current value.

    Returns (row, before, after). Raises PolicyValidationError."""
    from app import db
    from app.models import OrganizationSecurityPolicy
    from app.permissions import is_privileged
    from app.models import Role

    if not isinstance(data, dict):
        raise PolicyValidationError({'policy': 'Must be an object'})
    unknown = sorted(set(data) - set(SECTIONS))
    if unknown:
        raise PolicyValidationError({k: 'Unknown section' for k in unknown})

    row = policy_row(org.id)
    before = parse_stored(row.policy if row is not None else None)
    merged = serialize(before)
    for name, section in data.items():
        if not isinstance(section, dict):
            raise PolicyValidationError({name: 'Must be an object'})
        section = dict(section)
        if name == 'mfa':
            section.pop('enforced_since', None)  # server-managed
        merged[name] = {**merged[name], **section}
    try:
        after = SecurityPolicy.model_validate(merged)
    except ValidationError as exc:
        raise PolicyValidationError(_field_errors(exc))

    errors = {}
    role = Role.resolve(after.provisioning.default_role, org.id)
    if role is None:
        errors['provisioning.default_role'] = 'Unknown role'
    elif is_privileged(role.permissions or []):
        errors['provisioning.default_role'] = 'A privileged role cannot be the default role'
    if (after.provisioning.registration_enabled and not before.provisioning.registration_enabled
            and not is_platform_org(org)):
        errors['provisioning.registration_enabled'] = 'Only applies to the platform organization'
    if errors:
        raise PolicyValidationError(errors)
    after.provisioning.default_role = role.name

    old_scope, new_scope = before.mfa.required_for, after.mfa.required_for
    if new_scope == 'none':
        after.mfa.enforced_since = None
    elif _MFA_RANK[new_scope] > _MFA_RANK[old_scope] or before.mfa.enforced_since is None:
        after.mfa.enforced_since = _now()
    else:
        after.mfa.enforced_since = before.mfa.enforced_since

    if row is None:
        row = OrganizationSecurityPolicy(organization_id=org.id)
        db.session.add(row)
    row.policy = serialize(after)
    row.updated_by = actor.id if actor is not None else None
    row.updated_at = _now()
    invalidate_cache()
    return row, before, after


# ── Passwords ───────────────────────────────────────────────────────────

def _password_section(policy) -> PasswordPolicy:
    if policy is None:
        return DEFAULT_POLICY.password
    if isinstance(policy, SecurityPolicy):
        return policy.password
    return policy


def password_rules(policy=None) -> dict:
    """Public description of the password rules (register / change hints)."""
    pw = _password_section(policy)
    return {
        'min_length': pw.min_length,
        'max_bytes': PASSWORD_MAX_BYTES,
        'require_upper': pw.require_upper,
        'require_lower': pw.require_lower,
        'require_digit': pw.require_digit,
        'require_symbol': pw.require_symbol,
        'history_count': pw.history_count,
        'max_age_days': pw.max_age_days,
    }


def validate_password(password, policy=None, user=None):
    """(ok, [messages]). `policy`: a SecurityPolicy / PasswordPolicy; None
    means `user`'s org policy, or the code defaults without a user.

    A symbol is any non-alphanumeric character (a superset of the old
    class, so no previously valid password becomes invalid by rule)."""
    if policy is None and user is not None and getattr(user, 'organization_id', None):
        policy = get_policy(user.organization_id)
    pw = _password_section(policy)
    if not isinstance(password, str) or not password:
        return False, ['Password is required']
    msgs = []
    if len(password) < pw.min_length:
        msgs.append(f'Password must be at least {pw.min_length} characters')
    if len(password.encode('utf-8')) > PASSWORD_MAX_BYTES:
        msgs.append(f'Password must be at most {PASSWORD_MAX_BYTES} bytes')
    if pw.require_upper and not any(c.isupper() for c in password):
        msgs.append('Password must contain an uppercase letter')
    if pw.require_lower and not any(c.islower() for c in password):
        msgs.append('Password must contain a lowercase letter')
    if pw.require_digit and not any(c.isdigit() for c in password):
        msgs.append('Password must contain a number')
    if pw.require_symbol and not any(not c.isalnum() for c in password):
        msgs.append('Password must contain a special character')
    email = (getattr(user, 'email', None) or '').lower()
    if email:
        local = email.split('@', 1)[0]
        if password.lower() in {email, local}:
            msgs.append('Password must not be your email address')
    return (not msgs), msgs


def _checkpw(password: str, hashed: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except (ValueError, TypeError):
        return False


def _check_many(password: str, hashes) -> bool:
    """True when `password` matches any hash. Runs off the eventlet hub when
    available (up to 25 bcrypt verifications)."""
    def work():
        return any(_checkpw(password, h) for h in hashes if h)
    try:
        from flask import current_app
        if current_app.config.get('SOCKETIO_ASYNC_MODE') == 'eventlet':
            import eventlet.patcher
            if eventlet.patcher.is_monkey_patched('thread'):
                from eventlet import tpool
                return tpool.execute(work)
    except Exception:  # pragma: no cover - fall back to running inline
        pass
    return work()


def check_password_change(user, new_password, *, policy=None, enforce_history=True) -> None:
    """Everything set_password checks, without writing. Raises
    PasswordPolicyError: rules, then reuse of the current password and the
    last ``history_count - 1`` earlier ones (``history_count`` = how many
    most recent passwords are blocked; 0 = off)."""
    from app import db
    from app.models import PasswordHistory

    if policy is None:
        policy = get_policy(user.organization_id) if getattr(user, 'organization_id', None) else default_policy()
    pw = _password_section(policy)
    ok, msgs = validate_password(new_password, pw, user)
    if not ok:
        raise PasswordPolicyError(msgs)
    if enforce_history and pw.history_count > 0 and user.password_hash:
        previous = []
        if user.id is not None and pw.history_count > 1:
            previous = [h for (h,) in db.session.query(PasswordHistory.password_hash)
                        .filter(PasswordHistory.user_id == user.id)
                        .order_by(PasswordHistory.created_at.desc()).limit(pw.history_count - 1).all()]
        if _check_many(new_password, [user.password_hash] + previous):
            raise PasswordPolicyError([
                f'Password was used recently; choose one that is not among your last '
                f'{pw.history_count} passwords'])


def set_password(user, new_password, *, policy=None, enforce_history=True):
    """The single entry point for every password write.

    Runs check_password_change (policy of the user's org unless given),
    pushes the old hash into ``password_history`` (newest 24 kept), then
    hashes. Raises PasswordPolicyError; stages changes only."""
    from app import db
    from app.models import PasswordHistory

    check_password_change(user, new_password, policy=policy, enforce_history=enforce_history)

    if user.id is not None and user.password_hash:
        db.session.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash,
                                       created_at=_now()))
        db.session.flush()
        stale = (db.session.query(PasswordHistory.id).filter(PasswordHistory.user_id == user.id)
                 .order_by(PasswordHistory.created_at.desc()).offset(HISTORY_MAX).all())
        if stale:
            PasswordHistory.query.filter(PasswordHistory.id.in_([i for (i,) in stale])) \
                .delete(synchronize_session=False)
    user.set_password(new_password)
    return user


def password_expires_at(user, policy=None):
    if user is None or not getattr(user, 'password_hash', None) or getattr(user, 'is_service_account', False):
        return None
    policy = policy or get_policy(user.organization_id)
    days = policy.password.max_age_days
    if not days:
        return None
    changed = _aware(user.password_changed_at or user.created_at)
    if changed is None:
        return None
    return changed + timedelta(days=days)


def password_expired(user, policy=None) -> bool:
    """Local password older than ``max_age_days`` (0 = never)."""
    expires = password_expires_at(user, policy)
    return expires is not None and _now() >= expires


def apply_password_expiry(user, policy=None) -> bool:
    """Set ``must_change_password`` when the password expired (sign-in /
    refresh). Returns True when the flag was set now. Caller commits."""
    if user.must_change_password or not password_expired(user, policy):
        return False
    user.must_change_password = True
    return True


# ── Provisioning ────────────────────────────────────────────────────────

def email_domain(email) -> str:
    return (email or '').rsplit('@', 1)[-1].strip().lower()


def check_email_domain(email, policy) -> bool:
    """True when the policy allows `email` (an empty list allows any)."""
    domains = policy.provisioning.allowed_email_domains
    return not domains or email_domain(email) in domains


def registration_enabled() -> bool:
    """Self-registration and first SSO sign-in (platform org policy)."""
    org = platform_org()
    return org is not None and get_policy(org.id).provisioning.registration_enabled


def default_role(policy, org_id):
    """The policy's default role for new accounts of `org_id`; Viewer when
    it has disappeared or became privileged since it was chosen."""
    from app.models import Role
    from app.permissions import is_privileged
    role = Role.resolve(policy.provisioning.default_role, org_id)
    if role is None or is_privileged(role.permissions or []):
        role = Role.resolve('Viewer', org_id)
    return role


# ── Lockout and sessions ────────────────────────────────────────────────

def lockout_settings(org_id) -> tuple[int, int]:
    """(threshold, duration minutes): the only lockout values user_lifecycle reads."""
    lock = get_policy(org_id).lockout
    return lock.threshold, lock.duration_minutes


def token_lifetimes(org_id) -> tuple[timedelta, timedelta]:
    """(access, refresh) lifetimes for newly issued tokens."""
    sess = get_policy(org_id).session
    return timedelta(minutes=sess.access_token_minutes), timedelta(days=sess.refresh_token_days)


# ── MFA ─────────────────────────────────────────────────────────────────

def is_privileged(user) -> bool:
    """Holds any privileged permission (the MFA "privileged" scope)."""
    from app.permissions import is_privileged as perms_privileged
    return perms_privileged(user.role_permissions)


def mfa_required(user, policy=None) -> bool:
    if user is None or getattr(user, 'is_service_account', False):
        return False
    policy = policy or get_policy(user.organization_id)
    scope = policy.mfa.required_for
    return scope == 'all' or (scope == 'privileged' and is_privileged(user))


def mfa_status(user, policy=None) -> dict:
    """{required, enrolled, grace_ends_at (datetime|None), enforce_now}.

    Grace deadline = max(enforced_since, user.created_at) + grace_days;
    ``enforce_now`` means the account is restricted to MFA enrollment."""
    policy = policy or get_policy(user.organization_id)
    required = mfa_required(user, policy)
    enrolled = bool(user.mfa_enabled)
    grace_ends_at = None
    enforce_now = False
    if required and not enrolled:
        since = _aware(policy.mfa.enforced_since) or _now()
        created = _aware(user.created_at) or since
        grace_ends_at = max(since, created) + timedelta(days=policy.mfa.grace_days)
        enforce_now = _now() >= grace_ends_at
    return {'required': required, 'enrolled': enrolled, 'grace_ends_at': grace_ends_at,
            'enforce_now': enforce_now}


def mfa_enrollment_required(user) -> bool:
    """Restriction predicate (account_state ``mfa_enrollment_required``)."""
    if user is None or user.mfa_enabled or getattr(user, 'is_service_account', False):
        return False
    policy = get_policy(user.organization_id)
    if policy.mfa.required_for == 'none':
        return False
    return mfa_status(user, policy)['enforce_now']


def security_status(user) -> dict:
    """The ``security`` block of /auth/me and sign-in responses."""
    policy = get_policy(user.organization_id)
    mfa = mfa_status(user, policy)
    expires = password_expires_at(user, policy)
    return {
        'mfa_required': mfa['required'],
        'mfa_enrollment_required': bool(mfa['enforce_now']),
        'mfa_grace_ends_at': mfa['grace_ends_at'].isoformat() if mfa['grace_ends_at'] else None,
        'password_change_required': bool(user.must_change_password),
        'password_expires_at': expires.isoformat() if expires else None,
    }


def stats(org_id) -> dict:
    """MFA adoption counts for the admin UI (active, non-service users)."""
    from app.models import User
    policy = get_policy(org_id)
    users = User.query.filter(User.organization_id == org_id, User.is_active.is_(True),
                              User.is_service_account.is_(False)).all()
    out = {'users_total': 0, 'users_mfa': 0, 'privileged_total': 0, 'privileged_mfa': 0,
           'users_without_mfa_past_grace': 0}
    for u in users:
        out['users_total'] += 1
        out['users_mfa'] += 1 if u.mfa_enabled else 0
        if is_privileged(u):
            out['privileged_total'] += 1
            out['privileged_mfa'] += 1 if u.mfa_enabled else 0
        if not u.mfa_enabled and mfa_status(u, policy)['enforce_now']:
            out['users_without_mfa_past_grace'] += 1
    return out


__all__ = [
    'SecurityPolicy', 'DEFAULT_POLICY', 'default_policy', 'BOUNDS', 'PASSWORD_MAX_BYTES', 'PolicyValidationError',
    'PasswordPolicyError', 'parse_stored', 'platform_org', 'is_platform_org', 'policy_row', 'get_policy',
    'platform_policy', 'serialize', 'update_policy', 'policy_changes', 'invalidate_cache', 'password_rules',
    'validate_password', 'check_password_change', 'set_password', 'password_expired', 'password_expires_at', 'apply_password_expiry',
    'check_email_domain', 'registration_enabled', 'default_role', 'lockout_settings', 'token_lifetimes',
    'is_privileged', 'mfa_required', 'mfa_status', 'mfa_enrollment_required', 'security_status', 'stats',
]
