"""Scoped API keys and service accounts.

Key format: ``ssk_<lookup>_<secret>``; ``lookup`` is 12 lowercase base32
chars, ``secret`` 43 url-safe chars (256 bits from ``secrets``). The public
``prefix`` is ``ssk_<lookup>`` (unique, indexed). Only
``HMAC-SHA256(pepper, secret)`` is stored (``hash_alg='hmac-sha256-v1'``);
the pepper comes from ``API_KEY_PEPPER`` or, when unset, is derived from
SECRET_KEY with HKDF (startup warning in create_app). The full key is
returned once, at creation or rotation, and is never stored or logged.

A key is used through an exchange (``POST /auth/token``): the key is
verified and a short-lived access JWT is minted for the owner with claims
``api_key_id``, ``api_key_prefix``, ``scopes`` and ``auth_method='api_key'``.
Effective permissions are ``owner role permissions ∩ scopes`` on every
request (``User.permissions`` + ``utils/token_scopes``); incident
visibility stays the owner's (``incident_scopes``).

Revocation: the DB row (re-checked at every exchange) plus a Redis marker
``revoked_api_key:<id>`` that ``app.is_token_revoked`` checks, so tokens
already minted die at once. Owner lifecycle events (disable, delete, forced
logout, password reset, MFA reset) revoke all of the owner's keys through
the token-revocation hook :func:`revoke_all_for_user`; the epoch bump in
``revoke_all_sessions`` already kills the tokens minted from them.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from flask import current_app, jsonify
from flask_jwt_extended import create_access_token

from app import db
from app.models import Organization, Role, User, UserRole
from app.models.api_key import HASH_ALG, ApiKey
from app.permissions import GROUPS, PERMISSIONS, PERMISSIONS_BY_KEY, api_key_grantable_keys, with_implied
from app.schemas.organization import API_KEY_MAX_LIFETIME_DAYS_DEFAULT, API_KEYS_ENABLED_DEFAULT
from app.services.token_revocation import register_revocation_hook

logger = logging.getLogger(__name__)

KEY_PREFIX = 'ssk_'
KEY_RE = re.compile(r'^(ssk_[a-z2-7]{12})_([A-Za-z0-9_-]{43})$')
PREFIX_RE = re.compile(r'ssk_[a-z2-7]{12}')
MAX_RAW_KEY_LENGTH = 64

DEFAULT_LIFETIME_DAYS = 90
MAX_LIFETIME_DAYS = 365
MAX_GRACE_MINUTES = 1440
REVOKED_MARKER_TTL = 86400  # seconds; far longer than any key token lives
SERVICE_EMAIL_DOMAIN = 'service.invalid'  # reserved TLD: never an OAuth identity

# Token-revocation reasons that revoke the owner's keys -> stored revoked_reason.
OWNER_REVOCATION_REASONS = {
    'disabled': 'owner_disabled',
    'deleted': 'owner_deleted',
    'force_logout': 'owner_force_logout',
    'password_reset': 'owner_password_reset',
    'mfa_reset': 'owner_mfa_reset',
}

# Flagged in the scope picker (UI warning) on top of the catalog's dangerous flag.
_SENSITIVE_KEYS = frozenset({'compromised_accounts:reveal', 'artifacts:download', 'audit_logs:read'})


class ApiKeyError(Exception):
    """A rejected API-key / service-account operation -> ``{error, message, **details}``."""

    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}

    def response(self):
        db.session.rollback()
        return jsonify({'error': self.code, 'message': self.message, **self.details}), self.status


class ExchangeError(Exception):
    """A failed exchange. ``reason`` is for the audit log only; clients always
    get the same 401 ``invalid_api_key``."""

    def __init__(self, reason: str, key: ApiKey | None = None, owner: User | None = None,
                 prefix: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.key = key
        self.owner = owner
        self.prefix = prefix


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Secrets ─────────────────────────────────────────────────────────

@lru_cache(maxsize=4)
def _derive_pepper(configured: str, secret_key: str) -> bytes:
    if configured:
        return configured.encode('utf-8')
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b'sheetstorm-api-key-v1').derive((secret_key or '').encode('utf-8'))


def _pepper() -> bytes:
    cfg = current_app.config
    return _derive_pepper(cfg.get('API_KEY_PEPPER') or '', cfg.get('SECRET_KEY') or '')


def hash_secret(secret: str) -> str:
    """Hex HMAC-SHA256(pepper, secret)."""
    return hmac.new(_pepper(), secret.encode('utf-8'), hashlib.sha256).hexdigest()


def generate_key() -> tuple[str, str, str]:
    """-> (full_key, prefix, key_hash). The full key must only be shown once."""
    lookup = base64.b32encode(secrets.token_bytes(8)).decode('ascii').lower()[:12]
    secret = secrets.token_urlsafe(32)
    prefix = f'{KEY_PREFIX}{lookup}'
    return f'{prefix}_{secret}', prefix, hash_secret(secret)


def parse_key(raw) -> tuple[str, str] | None:
    """(prefix, secret) of a well-formed key, else None."""
    if not isinstance(raw, str) or len(raw) > MAX_RAW_KEY_LENGTH:
        return None
    m = KEY_RE.match(raw.strip())
    return (m.group(1), m.group(2)) if m else None


def prefix_of(raw) -> str | None:
    """The public prefix of something key-shaped (for rate limiting / audit)."""
    if not isinstance(raw, str) or len(raw) > 256:
        return None
    m = PREFIX_RE.match(raw.strip())
    return m.group(0) if m else None


# ── Org settings ────────────────────────────────────────────────────

def _org_settings(org_id) -> dict:
    org = db.session.get(Organization, org_id) if org_id else None
    return dict(org.settings or {}) if org else {}


def api_keys_enabled(org_id) -> bool:
    value = _org_settings(org_id).get('api_keys_enabled', API_KEYS_ENABLED_DEFAULT)
    return value is not False


def max_lifetime_days(org_id) -> int:
    value = _org_settings(org_id).get('api_key_max_lifetime_days', API_KEY_MAX_LIFETIME_DAYS_DEFAULT)
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = API_KEY_MAX_LIFETIME_DAYS_DEFAULT
    return max(1, min(MAX_LIFETIME_DAYS, value))


def _lifetime(org_id, expires_in_days) -> int:
    cap = max_lifetime_days(org_id)
    if expires_in_days is None:
        return min(DEFAULT_LIFETIME_DAYS, cap)
    if isinstance(expires_in_days, bool) or not isinstance(expires_in_days, int) \
            or not 1 <= expires_in_days <= cap:
        raise ApiKeyError(400, 'validation_error', f'expires_in_days must be between 1 and {cap}',
                          {'fields': {'expires_in_days': f'Must be between 1 and {cap} days'}, 'max_days': cap})
    return expires_in_days


def token_ttl_minutes() -> int:
    try:
        ttl = int(current_app.config.get('API_KEY_TOKEN_TTL_MINUTES', 15))
    except (TypeError, ValueError):
        ttl = 15
    return max(1, min(60, ttl))


# ── Scopes ──────────────────────────────────────────────────────────

def is_sensitive(perm_key: str) -> bool:
    p = PERMISSIONS_BY_KEY.get(perm_key)
    return bool(p and p.dangerous) or perm_key in _SENSITIVE_KEYS or perm_key.endswith(':delete')


def grantable_scopes(owner: User, actor: User | None = None) -> list[str]:
    """Catalog-grantable ∩ owner's role permissions (∩ actor's when another
    user mints the key, so nobody hands out what they don't hold)."""
    allowed = api_key_grantable_keys() & set(owner.role_permissions)
    if actor is not None and actor.id != owner.id:
        allowed &= with_implied(actor.permissions)
    return sorted(allowed)


def scope_groups(owner: User, actor: User | None = None) -> list[dict]:
    """Grantable scopes grouped in catalog order, for the scope picker."""
    allowed = set(grantable_scopes(owner, actor))
    groups: dict[str, list] = {}
    for p in PERMISSIONS:
        if p.key in allowed:
            groups.setdefault(p.group, []).append({
                'value': p.key, 'label': p.label, 'description': p.description,
                'sensitive': is_sensitive(p.key),
            })
    return [{'group': g, 'label': GROUPS.get(g, g), 'scopes': groups[g]} for g in GROUPS if g in groups]


def validate_scopes(scopes, owner: User, actor: User | None = None) -> list[str]:
    """Sorted, deduplicated scopes, or ApiKeyError 400 `invalid_scopes`
    listing the unknown / forbidden (not grantable to keys) / not-held keys."""
    if not isinstance(scopes, (list, tuple)) or not scopes:
        raise ApiKeyError(400, 'invalid_scopes', 'At least one scope is required', {'empty': True})
    if not all(isinstance(s, str) for s in scopes):
        raise ApiKeyError(400, 'invalid_scopes', 'Scopes must be permission keys')
    wanted = set(scopes)
    unknown = sorted(s for s in wanted if s not in PERMISSIONS_BY_KEY)
    forbidden = sorted(s for s in wanted - set(unknown) if not PERMISSIONS_BY_KEY[s].api_key_grantable)
    allowed = set(grantable_scopes(owner, actor))
    not_held = sorted(wanted - set(unknown) - set(forbidden) - allowed)
    if unknown or forbidden or not_held:
        raise ApiKeyError(400, 'invalid_scopes', 'Some scopes cannot be granted to this key',
                          {'unknown': unknown, 'forbidden': forbidden, 'not_held': not_held})
    return sorted(wanted)


# ── Queries ─────────────────────────────────────────────────────────

def active_filter(now=None):
    """SQL: not revoked (or revocation still scheduled) and not expired."""
    now = now or _now()
    return db.and_(db.or_(ApiKey.revoked_at.is_(None), ApiKey.revoked_at > now), ApiKey.expires_at > now)


def status_filter(status, now=None):
    now = now or _now()
    if status == 'active':
        return active_filter(now)
    if status == 'revoked':
        return db.and_(ApiKey.revoked_at.isnot(None), ApiKey.revoked_at <= now)
    if status == 'expired':
        return db.and_(db.or_(ApiKey.revoked_at.is_(None), ApiKey.revoked_at > now), ApiKey.expires_at <= now)
    raise ApiKeyError(400, 'validation_error', 'status must be active, expired, revoked or all',
                      {'fields': {'status': 'Invalid status'}})


def get_org_key(org_id, key_id) -> ApiKey | None:
    return ApiKey.query.filter_by(id=key_id, organization_id=org_id).first()


def active_key_count(owner_id) -> int:
    return ApiKey.query.filter(ApiKey.owner_user_id == owner_id, active_filter()).count()


# ── Create / revoke / rotate ────────────────────────────────────────

def _check_caps(owner: User) -> None:
    cfg = current_app.config
    per_owner = int(cfg.get('API_KEY_MAX_PER_SERVICE_ACCOUNT' if owner.is_service_account
                            else 'API_KEY_MAX_PER_USER', 10))
    if active_key_count(owner.id) >= per_owner:
        raise ApiKeyError(409, 'api_key_limit', f'This owner already has {per_owner} active keys',
                          {'limit': per_owner, 'scope': 'owner'})
    per_org = int(cfg.get('API_KEY_MAX_PER_ORG', 200))
    if ApiKey.query.filter(ApiKey.organization_id == owner.organization_id, active_filter()).count() >= per_org:
        raise ApiKeyError(409, 'api_key_limit', f'The organization already has {per_org} active keys',
                          {'limit': per_org, 'scope': 'organization'})


def _release_name(owner: User, name: str) -> None:
    """Expired keys stop holding their name; an active one is a 409."""
    now = _now()
    same = ApiKey.query.filter(ApiKey.owner_user_id == owner.id, ApiKey.revoked_at.is_(None),
                               db.func.lower(ApiKey.name) == name.lower()).all()
    for key in same:
        if key.is_expired(now):
            key.revoked_at = now
            key.revoked_reason = 'expired'
        else:
            raise ApiKeyError(409, 'name_conflict', 'An active key with this name already exists',
                              {'fields': {'name': 'Already used by an active key'}})
    db.session.flush()


def _new_key(owner: User, created_by: User | None, *, name, description, scopes, lifetime_days,
             rotated_from: ApiKey | None = None) -> tuple[ApiKey, str]:
    full_key, prefix, key_hash = generate_key()
    now = _now()
    key = ApiKey(organization_id=owner.organization_id, owner_user_id=owner.id,
                 created_by=created_by.id if created_by else None, name=name, description=description,
                 prefix=prefix, key_hash=key_hash, hash_alg=HASH_ALG, scopes=list(scopes),
                 created_at=now, expires_at=now + timedelta(days=lifetime_days), use_count=0,
                 rotated_from_id=rotated_from.id if rotated_from else None)
    db.session.add(key)
    db.session.flush()
    return key, full_key


def assert_enabled(org_id) -> None:
    if not api_keys_enabled(org_id):
        raise ApiKeyError(403, 'api_keys_disabled', 'API keys are disabled for this organization')


def create_key(owner: User, created_by: User, *, name: str, scopes, expires_in_days=None,
               description: str | None = None) -> tuple[ApiKey, str]:
    """Create a key for `owner` -> (key, full_key). Caller commits.

    `created_by` is the owner (personal key) or a manager creating a key for
    a service account (the endpoint enforces who may do what)."""
    from app.services.rbac_guard import lock_org
    assert_enabled(owner.organization_id)
    if not owner.is_active:
        raise ApiKeyError(409, 'owner_inactive', 'The key owner is disabled')
    lifetime = _lifetime(owner.organization_id, expires_in_days)
    scopes = validate_scopes(scopes, owner, created_by)
    lock_org(owner.organization_id)  # serialises the caps check
    _release_name(owner, name)
    _check_caps(owner)
    return _new_key(owner, created_by, name=name, description=description, scopes=scopes,
                    lifetime_days=lifetime)


def mark_revoked(key_ids) -> None:
    """Redis markers so tokens already minted from these keys die at once.
    Call AFTER the revocation is committed. Failures are logged: the DB state
    is authoritative at the next exchange and key tokens live <= 60 min."""
    from app import redis_client
    ids = [str(i) for i in key_ids]
    if not ids:
        return
    if redis_client is None:
        logger.error('API key revocation marker not written (no token store); %d key(s)', len(ids))
        return
    try:
        pipe = redis_client.pipeline()
        for kid in ids:
            pipe.setex(f'revoked_api_key:{kid}', REVOKED_MARKER_TTL, '1')
        pipe.execute()
    except Exception as exc:
        logger.error('API key revocation marker write failed: %s', type(exc).__name__)


def revoke_key(key: ApiKey, actor: User | None, reason: str = 'manual') -> bool:
    """Revoke now (also cuts a scheduled grace revocation short). Returns
    False when already revoked (idempotent). Caller commits, then mark_revoked."""
    now = _now()
    if key.is_revoked(now):
        return False
    key.revoked_at = now
    key.revoked_by = actor.id if actor else None
    key.revoked_reason = (reason or 'manual')[:200]
    return True


def rotate_key(key: ApiKey, actor: User, *, expires_in_days=None, grace_minutes: int = 0) -> tuple[ApiKey, str]:
    """Issue a replacement (same owner, name, description, scopes) -> (new, full_key).

    grace_minutes 0 revokes the old key at once; otherwise its revocation is
    scheduled at now + grace (and its expiry capped there). Scopes the owner
    no longer holds are dropped. Caller commits, then mark_revoked([old.id])
    when there is no grace."""
    now = _now()
    assert_enabled(key.organization_id)
    if key.is_revoked(now) or key.is_expired(now):
        raise ApiKeyError(409, 'key_not_active', 'Only an active key can be rotated')
    if key.revoked_at is not None:
        raise ApiKeyError(409, 'key_not_active', 'This key is already being rotated')
    owner = db.session.get(User, key.owner_user_id)
    if owner is None or not owner.is_active:
        raise ApiKeyError(409, 'owner_inactive', 'The key owner is disabled')
    if isinstance(grace_minutes, bool) or not isinstance(grace_minutes, int) \
            or not 0 <= grace_minutes <= MAX_GRACE_MINUTES:
        raise ApiKeyError(400, 'validation_error', f'grace_minutes must be between 0 and {MAX_GRACE_MINUTES}',
                          {'fields': {'grace_minutes': 'Out of range'}})

    if expires_in_days is None:
        original = max(1, -(-(key.expires_at - key.created_at).total_seconds() // 86400))
        expires_in_days = min(int(original), max_lifetime_days(key.organization_id))
    lifetime = _lifetime(key.organization_id, expires_in_days)

    allowed = set(grantable_scopes(owner))
    scopes = [s for s in (key.scopes or []) if s in allowed]
    if not scopes:
        raise ApiKeyError(400, 'invalid_scopes', 'The owner no longer holds any of this key\'s scopes',
                          {'unknown': [], 'forbidden': [], 'not_held': sorted(key.scopes or [])})
    if actor.id != owner.id:
        missing = sorted(set(scopes) - with_implied(actor.permissions))
        if missing:
            raise ApiKeyError(403, 'privilege_escalation',
                              "You cannot rotate a key holding scopes you don't hold", {'missing': missing})

    key.revoked_by = actor.id
    key.revoked_reason = 'rotated'
    if grace_minutes:
        until = now + timedelta(minutes=grace_minutes)
        key.revoked_at = until
        key.expires_at = min(key.expires_at, until)
    else:
        key.revoked_at = now
    db.session.flush()  # frees the name before the replacement is inserted
    return _new_key(owner, actor, name=key.name, description=key.description, scopes=scopes,
                    lifetime_days=lifetime, rotated_from=key)


def revoke_all_for_user(user, reason: str) -> int:
    """Token-revocation hook (``register_revocation_hook``): revoke every
    still-usable key of `user` for the owner lifecycle reasons in
    OWNER_REVOCATION_REASONS. Runs inside the caller's transaction (no
    commit); the caller's epoch bump already killed the tokens minted from
    these keys. Returns the number of keys revoked."""
    stored = OWNER_REVOCATION_REASONS.get(reason)
    if stored is None:
        return 0
    now = _now()
    keys = ApiKey.query.filter(ApiKey.owner_user_id == user.id,
                               db.or_(ApiKey.revoked_at.is_(None), ApiKey.revoked_at > now)).all()
    for key in keys:
        key.revoked_at = now
        key.revoked_by = None
        key.revoked_reason = stored
    if keys:
        db.session.flush()
        logger.info('Revoked %d API key(s) of user %s (%s)', len(keys), user.id, reason)
    return len(keys)


register_revocation_hook(revoke_all_for_user)


# ── Exchange ────────────────────────────────────────────────────────

def _current_token_epoch(user_id) -> int:
    from app import redis_client
    if redis_client is None:
        return 0
    try:
        val = redis_client.get(f'token_epoch:{user_id}')
        return int(val) if val is not None else 0
    except Exception:
        return 0


def _client_ip(ip):
    try:
        return str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        return None


def exchange(raw_key, ip=None) -> tuple[str, ApiKey, User, int]:
    """Verify `raw_key` and mint an access token for its owner.

    -> (access_token, key, owner, expires_in_seconds); raises ExchangeError
    (reason for the audit log only). Commits the usage stamp."""
    parsed = parse_key(raw_key)
    if parsed is None:
        raise ExchangeError('malformed', prefix=prefix_of(raw_key))
    prefix, secret = parsed
    key = ApiKey.query.filter_by(prefix=prefix).first()
    if key is None:
        hmac.compare_digest(hash_secret(secret), '0' * 64)  # equalise timing
        raise ExchangeError('unknown_prefix', prefix=prefix)
    if key.hash_alg != HASH_ALG or not hmac.compare_digest(hash_secret(secret), key.key_hash):
        raise ExchangeError('invalid_secret', key=key, prefix=prefix)

    now = _now()
    owner = db.session.get(User, key.owner_user_id)
    if key.is_revoked(now):
        raise ExchangeError('revoked', key=key, owner=owner, prefix=prefix)
    if key.is_expired(now):
        raise ExchangeError('expired', key=key, owner=owner, prefix=prefix)
    if owner is None or not owner.is_active:
        raise ExchangeError('owner_inactive', key=key, owner=owner, prefix=prefix)
    if owner.organization_id != key.organization_id:
        raise ExchangeError('org_mismatch', key=key, owner=owner, prefix=prefix)
    if not api_keys_enabled(key.organization_id):
        raise ExchangeError('org_disabled', key=key, owner=owner, prefix=prefix)

    # The token never outlives the key (expiry or a scheduled grace revocation).
    limit = key.expires_at if key.revoked_at is None else min(key.expires_at, key.revoked_at)
    ttl = min(timedelta(minutes=token_ttl_minutes()), limit - now)
    expires_in = max(1, int(ttl.total_seconds()))
    grantable = api_key_grantable_keys()
    claims = {
        'token_epoch': _current_token_epoch(owner.id),
        'api_key_id': str(key.id),
        'api_key_prefix': key.prefix,
        'scopes': sorted(s for s in (key.scopes or []) if s in grantable),
        'auth_method': 'api_key',
    }
    token = create_access_token(identity=str(owner.id), additional_claims=claims,
                                expires_delta=timedelta(seconds=expires_in))

    key.last_used_at = now
    key.last_used_ip = _client_ip(ip)
    key.use_count = (key.use_count or 0) + 1
    db.session.commit()
    return token, key, owner, expires_in


# ── Service accounts ────────────────────────────────────────────────

def _slug(name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:40].strip('-')
    return slug or 'account'


def _resolve_roles(org_id, role_ids) -> list[Role]:
    ids = list(dict.fromkeys(str(r) for r in role_ids or ()))
    if not ids:
        return []
    roles = Role.visible_to(org_id).filter(Role.id.in_(ids)).all()
    found = {str(r.id) for r in roles}
    missing = [r for r in ids if r not in found]
    if missing:
        raise ApiKeyError(400, 'validation_error', 'Unknown role(s)',
                          {'fields': {'role_ids': 'Unknown role'}, 'unknown_roles': missing})
    return roles


def create_service_account(actor: User, *, name: str, role_ids=()) -> User:
    """A non-interactive user that owns API keys. Roles go through the
    anti-escalation guard (RBAC GuardError propagates). Caller commits."""
    from app.services.rbac_guard import assert_can_grant_roles
    roles = _resolve_roles(actor.organization_id, role_ids)
    assert_can_grant_roles(actor, roles, resource_type='user')
    email = f'svc-{_slug(name)}-{secrets.token_hex(3)}@{SERVICE_EMAIL_DOMAIN}'
    sa = User(email=email, name=name, organization_id=actor.organization_id, auth_provider='service',
              password_hash=None, is_service_account=True, is_active=True, is_verified=True,
              organizational_role='Service account')
    db.session.add(sa)
    db.session.flush()
    for role in roles:
        db.session.add(UserRole(user_id=sa.id, role_id=role.id, organization_id=actor.organization_id,
                                granted_by=actor.id))
    db.session.flush()
    db.session.expire(sa, ['user_roles'])
    return sa


def update_service_account(actor: User, sa: User, *, name=None, is_active=None, role_ids=None) -> dict:
    """Rename / (de)activate / replace roles. Deactivation revokes every
    session and key of the account (revoke_all_sessions -> hook). Caller
    commits; SessionRevocationError / GuardError propagate."""
    from app.services.rbac_guard import assert_can_grant_roles, assert_outranks
    from app.services.token_revocation import revoke_all_sessions
    assert_outranks(actor, sa)
    changed = {}
    if name is not None and name != sa.name:
        changed['name'] = {'from': sa.name, 'to': name}
        sa.name = name
    if role_ids is not None:
        roles = _resolve_roles(actor.organization_id, role_ids)
        assert_can_grant_roles(actor, roles, resource_type='user', resource_id=sa.id)
        old = sorted(str(ur.role_id) for ur in sa.user_roles)
        new = sorted(str(r.id) for r in roles)
        if old != new:
            UserRole.query.filter_by(user_id=sa.id).delete(synchronize_session=False)
            for role in roles:
                db.session.add(UserRole(user_id=sa.id, role_id=role.id, organization_id=actor.organization_id,
                                        granted_by=actor.id))
            db.session.flush()
            db.session.expire(sa, ['user_roles'])
            changed['roles'] = {'added': sorted(set(new) - set(old)), 'removed': sorted(set(old) - set(new))}
    if is_active is not None and is_active != sa.is_active:
        changed['is_active'] = {'from': sa.is_active, 'to': is_active}
        sa.is_active = is_active
        if is_active:
            sa.deactivated_at = sa.deactivated_by = sa.deactivation_reason = None
        else:
            sa.deactivated_at = _now()
            sa.deactivated_by = actor.id
            sa.deactivation_reason = 'service account disabled'
            db.session.flush()
            revoke_all_sessions(sa, 'disabled')
    return changed


def delete_service_account(actor: User, sa: User) -> None:
    """Revoke every key, then soft-disable (the row stays for audit
    attribution). Caller commits."""
    from app.services.rbac_guard import assert_outranks
    from app.services.token_revocation import revoke_all_sessions
    assert_outranks(actor, sa)
    revoke_all_sessions(sa, 'deleted')
    sa.is_active = False
    sa.deactivated_at = sa.deactivated_at or _now()
    sa.deactivated_by = actor.id
    sa.deactivation_reason = 'service account deleted'


__all__ = [
    'ApiKeyError', 'ExchangeError', 'KEY_RE', 'hash_secret', 'generate_key', 'parse_key', 'prefix_of',
    'api_keys_enabled', 'max_lifetime_days', 'token_ttl_minutes', 'grantable_scopes', 'scope_groups',
    'validate_scopes', 'is_sensitive', 'active_filter', 'status_filter', 'get_org_key', 'active_key_count',
    'create_key', 'revoke_key', 'rotate_key', 'mark_revoked', 'revoke_all_for_user', 'exchange',
    'create_service_account', 'update_service_account', 'delete_service_account',
]
