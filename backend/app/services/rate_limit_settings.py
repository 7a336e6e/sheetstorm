"""Admin-configurable rate limits (W4-RL, owner requirement).

Every rate-limited route belongs to a named *group* (``GROUPS``) and is
decorated with ``@limited('<group>')`` instead of a literal
``@limiter.limit("…")``. The limit applied to a group is resolved per request:

    RATELIMIT_ENABLED=False (Flask config)   hard off: tests / ops kill switch
    RATE_LIMIT_SETTINGS_LOCKED=true          DB overrides ignored, UI read-only
    DB override  system_settings['rate_limits']   set by platform admins
    env          RATE_LIMIT_<GROUP>  (RATE_LIMIT_DEFAULT for api_default)
    code default GROUPS[group].default

A group can be disabled: its routes then fall back to ``api_default`` (the
global safety net) rather than becoming unlimited. Turning off *all* rate
limiting is possible but needs an explicit confirmation and is audited.

The stored document holds only overrides::

    {"enabled": bool, "groups": {"<group>": {"limit": "5 per minute" | null, "enabled": bool}}}

It is cached per process for ``CACHE_TTL`` seconds, shared through Redis
(written on every change), and read from the database as a fallback, so a
change reaches every worker within a few seconds without a restart. Any load
or parse error falls back to env/code defaults with limiting ON: a broken
override can never switch rate limiting off.
"""
import json
import logging
import os
import time
from dataclasses import dataclass, field

from flask import current_app
from limits import parse_many

logger = logging.getLogger(__name__)

SETTINGS_KEY = 'rate_limits'
REDIS_KEY = 'ratelimit:settings'
CACHE_TTL = 5.0
MAX_ITEMS = 5
MAX_LIMIT_LENGTH = 200
MAX_AMOUNT = 1_000_000
API_DEFAULT_FLOOR_PER_MINUTE = 30
AUTH_LOOSEN_FACTOR = 10


@dataclass(frozen=True)
class GroupDef:
    default: str
    description: str
    category: str = 'feature'
    auth_sensitive: bool = False
    routes: tuple = field(default_factory=tuple)


GROUPS: dict[str, GroupDef] = {
    'api_default': GroupDef('600 per minute', 'Safety net for every API route without a stricter group, per user / API key / client IP.', 'global', routes=('*',)),
    # Authentication (per client IP before login, per user after).
    'auth_login': GroupDef('5 per minute', 'Password sign-in attempts.', 'auth', True, ('POST /auth/login',)),
    'auth_register': GroupDef('3 per hour', 'Self-registration.', 'auth', True, ('POST /auth/register',)),
    'auth_refresh': GroupDef('30 per hour', 'Access-token refresh.', 'auth', True, ('POST /auth/refresh',)),
    'auth_logout': GroupDef('30 per minute', 'Sign-out.', 'auth', routes=('POST /auth/logout',)),
    'auth_me': GroupDef('60 per minute', 'Current user and public password policy.', 'auth', routes=('GET /auth/me', 'GET /auth/password-policy')),
    'auth_preferences': GroupDef('30 per minute', 'Saving personal preferences.', 'auth', routes=('PATCH /auth/me/preferences',)),
    'auth_password_change': GroupDef('5 per hour', 'Changing one\'s own password.', 'auth', True, ('POST /auth/change-password',)),
    'auth_sso_supabase': GroupDef('10 per minute', 'Supabase single sign-on.', 'auth', True, ('POST /auth/supabase',)),
    'auth_sso_github': GroupDef('20 per minute', 'GitHub OAuth redirect and callback.', 'auth', True, ('GET /auth/github', 'POST /auth/github/callback')),
    'auth_sso': GroupDef('30 per minute', 'OpenID Connect single sign-on: provider list, redirect, callback and admin tests.', 'auth', True, ('GET /auth/sso/providers', 'GET /auth/sso/<slug>/start', 'GET /auth/sso/<slug>/callback', 'POST /admin/sso-providers/<id>/test')),
    'mfa_enroll': GroupDef('5 per hour', 'MFA setup and disable.', 'auth', True, ('POST /auth/mfa/setup', 'POST /auth/mfa/disable')),
    'mfa_verify': GroupDef('10 per hour', 'MFA code verification.', 'auth', True, ('POST /auth/mfa/verify',)),
    'mfa_complete': GroupDef('10 per minute', 'MFA step after SSO sign-in.', 'auth', True, ('POST /auth/mfa/complete',)),
    'invites_lookup': GroupDef('10 per minute;60 per hour', 'Looking up an invitation link.', 'auth', True, ('GET /auth/invites/<token>',)),
    'invites_accept': GroupDef('5 per minute;20 per hour', 'Accepting an invitation.', 'auth', True, ('POST /auth/invites/<token>/accept',)),
    'password_reset_complete': GroupDef('5 per minute;20 per hour', 'Completing a password-reset link.', 'auth', True, ('POST /auth/password-reset/complete',)),
    'api_key_exchange': GroupDef('10 per minute', 'Exchanging an API key for a token, per client IP.', 'auth', True, ('POST /auth/token',)),
    'api_key_exchange_prefix': GroupDef('30 per hour', 'Exchanging an API key for a token, per key.', 'auth', True, ('POST /auth/token',)),
    # Administration.
    'api_keys_write': GroupDef('30 per hour', 'Creating and rotating API keys, creating service accounts.', 'admin', routes=('POST /api-keys', 'POST /api-keys/<id>/rotate', 'POST /service-accounts')),
    'invite_create': GroupDef('30 per hour', 'Sending invitations.', 'admin', routes=('POST /users/invites',)),
    'users_bulk': GroupDef('10 per minute', 'Bulk user actions.', 'admin', routes=('POST /users/bulk',)),
    'audit_export': GroupDef('10 per hour', 'Audit log export.', 'admin', routes=('GET /audit-logs/export',)),
    'audit_integrity': GroupDef('6 per hour', 'Audit chain integrity check.', 'admin', routes=('GET /admin/audit-integrity',)),
    'admin_status': GroupDef('30 per minute', 'System status page.', 'admin', routes=('GET /admin/system-status',)),
    'library_import': GroupDef('5 per hour', 'Importing the DFIQ question library.', 'admin', routes=('POST /questions/library/dfiq/import',)),
    'integrations_discovery': GroupDef('10 per minute', 'Listing models of a local AI server.', 'admin', routes=('GET /integrations/ollama/models',)),
    # Features.
    'search': GroupDef('60 per minute', 'Global search.', routes=('GET /search',)),
    'bulk_enrich': GroupDef('10 per minute', 'Bulk IOC enrichment.', routes=('POST /search/bulk-enrich',)),
    'exports': GroupDef('30 per minute', 'CSV/STIX exports, custody and decision-log exports.', routes=('GET /incidents/<id>/export/<entity>', 'GET …/stix', 'GET …/evidence/…/export', 'GET …/decisions/export')),
    'reports_generate': GroupDef('10 per minute', 'PDF and AI report generation.', routes=('POST …/reports/generate-pdf', 'POST …/reports/ai-generate')),
    'metrics': GroupDef('30 per minute', 'Response metrics and dashboard statistics.', routes=('GET /metrics/incidents', 'GET /dashboard/stats')),
    'custody_verify': GroupDef('20 per minute', 'Custody chain verification and RFC 3161 anchoring.', routes=('GET …/custody/verify', 'POST …/custody/anchor')),
    'template_apply': GroupDef('20 per minute', 'Applying a case template.', routes=('POST …/case-templates/<ref>/apply',)),
    'normalize_preview': GroupDef('60 per minute', 'Timestamp normalization preview.', routes=('POST /provenance/normalize-preview',)),
    'threat_intel_lookup': GroupDef('10 per minute', 'VirusTotal, IP, domain, e-mail and ransomware lookups.', 'threat_intel', routes=('POST /threat-intel/*/lookup',)),
    'threat_intel_cve': GroupDef('15 per minute', 'CVE lookups.', 'threat_intel', routes=('POST /threat-intel/cve/lookup',)),
    'threat_intel_misp_push': GroupDef('5 per minute', 'Pushing IOCs to MISP.', 'threat_intel', routes=('POST /threat-intel/misp/push',)),
}


def register_group(key, default, description, *, category='feature', auth_sensitive=False, routes=()):
    """Register a group from another module (idempotent for identical definitions)."""
    parse_many(default)
    GROUPS.setdefault(key, GroupDef(default, description, category, auth_sensitive, tuple(routes)))


class RateLimitSettingsError(ValueError):
    def __init__(self, message, fields=None):
        super().__init__(message)
        self.fields = fields or {}


# ── Loading (cache → Redis → DB; errors ⇒ defaults, limiting ON) ────────────

_cache = {'at': 0.0, 'doc': None}
_last_error_log = [0.0]


def _redis():
    try:
        from app import redis_client
        return redis_client
    except Exception:  # pragma: no cover - import cycle guard
        return None


def _clean_doc(raw):
    if not isinstance(raw, dict):
        return {}
    groups = raw.get('groups') if isinstance(raw.get('groups'), dict) else {}
    out = {'groups': {}}
    if isinstance(raw.get('enabled'), bool):
        out['enabled'] = raw['enabled']
    for key, ov in groups.items():
        if key in GROUPS and isinstance(ov, dict):
            entry = {}
            if isinstance(ov.get('limit'), str):
                parse_many(ov['limit'])  # raises on garbage ⇒ caller falls back
                entry['limit'] = ov['limit']
            if isinstance(ov.get('enabled'), bool):
                entry['enabled'] = ov['enabled']
            if entry:
                out['groups'][key] = entry
    return out


def _load_from_store():
    r = _redis()
    if r is not None:
        try:
            cached = r.get(REDIS_KEY)
            if cached:
                return _clean_doc(json.loads(cached))
        except Exception:
            pass  # Redis down or bad value: read the database
    from app.models.system_setting import SystemSetting
    doc = _clean_doc(SystemSetting.get_value(SETTINGS_KEY, {}) or {})
    if r is not None:
        try:
            r.set(REDIS_KEY, json.dumps(doc))
        except Exception:
            pass
    return doc


def stored_doc():
    """The active override document ({} when none, locked, or unreadable)."""
    if is_locked():
        return {}
    now = time.monotonic()
    if _cache['doc'] is not None and now - _cache['at'] < CACHE_TTL:
        return _cache['doc']
    try:
        doc = _load_from_store()
    except Exception:
        if now - _last_error_log[0] > CACHE_TTL:
            _last_error_log[0] = now
            logger.exception('Could not load rate-limit overrides; using defaults (rate limiting stays on)')
        doc = {}
    _cache.update(at=now, doc=doc)
    return doc


def invalidate(doc=None):
    """Drop the process cache; publish ``doc`` to Redis when given (after a change)."""
    _cache.update(at=0.0, doc=None)
    r = _redis()
    if r is None:
        return
    try:
        if doc is None:
            r.delete(REDIS_KEY)
        else:
            r.set(REDIS_KEY, json.dumps(doc))
    except Exception:
        logger.warning('Could not publish rate-limit settings to Redis; workers pick them up from the database')


# ── Resolution ──────────────────────────────────────────────────────────────

def is_locked() -> bool:
    return os.getenv('RATE_LIMIT_SETTINGS_LOCKED', '').strip().lower() in ('1', 'true', 'yes', 'on')


def hard_disabled() -> bool:
    try:
        return not current_app.config.get('RATELIMIT_ENABLED', True)
    except RuntimeError:
        return False


def _env_limit(group):
    names = ['RATE_LIMIT_' + group.upper()]
    if group == 'api_default':
        names.append('RATE_LIMIT_DEFAULT')
    for name in names:
        value = (os.getenv(name) or '').strip()
        if value:
            try:
                parse_many(value)
                return value
            except ValueError:
                logger.error('Ignoring invalid %s=%r', name, value)
    return None


def configured(group):
    """(limit, source, enabled, override) for a group, ignoring the fallback."""
    gdef = GROUPS[group]
    override = stored_doc().get('groups', {}).get(group, {})
    env = _env_limit(group)
    if override.get('limit'):
        limit, source = override['limit'], 'override'
    elif env:
        limit, source = env, 'env'
    else:
        limit, source = gdef.default, 'code'
    return limit, source, override.get('enabled', True), override


def global_enabled() -> bool:
    return stored_doc().get('enabled', True)


def effective_limit(group) -> str:
    """Limit string applied to ``group`` now (a disabled group uses api_default's)."""
    limit, _, enabled, _ = configured(group)
    if enabled:
        return limit
    return configured('api_default')[0]


def is_exempt(group) -> bool:
    """No limit at all: rate limiting off, or the group and api_default both off."""
    if not global_enabled():
        return True
    if configured(group)[2]:
        return False
    return not configured('api_default')[2]


def limited(group, **kwargs):
    """``@limited('auth_login')``: the route's limit comes from the group settings."""
    if group not in GROUPS:
        raise KeyError(f'unknown rate-limit group {group!r}')
    from app import limiter
    return limiter.limit(lambda: effective_limit(group), exempt_when=lambda: is_exempt(group), **kwargs)


# ── Validation ──────────────────────────────────────────────────────────────

def _items(limit):
    return parse_many(limit)


def _per_second(limit) -> float:
    """Strictest rate of a limit string, in requests per second."""
    return min(item.amount / item.get_expiry() for item in _items(limit))


def validate(doc):
    """Normalize an override document. Raises RateLimitSettingsError (400);
    returns (clean_doc, warnings). Warnings mean the change weakens protection
    and must be confirmed."""
    if not isinstance(doc, dict):
        raise RateLimitSettingsError('Body must be an object')
    fields = {}
    clean = {'enabled': True, 'groups': {}}
    if 'enabled' in doc:
        if not isinstance(doc['enabled'], bool):
            fields['enabled'] = 'Must be true or false'
        else:
            clean['enabled'] = doc['enabled']
    groups = doc.get('groups') or {}
    if not isinstance(groups, dict):
        fields['groups'] = 'Must be an object keyed by group'
        groups = {}
    for key, ov in groups.items():
        where = f'groups.{key}'
        if key not in GROUPS:
            fields[where] = 'Unknown group'
            continue
        if not isinstance(ov, dict):
            fields[where] = 'Must be an object'
            continue
        entry = {}
        limit = ov.get('limit')
        if limit not in (None, ''):
            if not isinstance(limit, str) or len(limit) > MAX_LIMIT_LENGTH:
                fields[f'{where}.limit'] = f'Must be a string of at most {MAX_LIMIT_LENGTH} characters'
            else:
                try:
                    items = _items(limit)
                except ValueError:
                    fields[f'{where}.limit'] = 'Not a valid limit, e.g. "5 per minute" or "10 per minute;100 per day"'
                else:
                    if not items or len(items) > MAX_ITEMS:
                        fields[f'{where}.limit'] = f'Give 1 to {MAX_ITEMS} limits separated by ";"'
                    elif any(not 1 <= item.amount <= MAX_AMOUNT for item in items):
                        fields[f'{where}.limit'] = f'Each amount must be between 1 and {MAX_AMOUNT}'
                    elif key == 'api_default' and any(
                            item.amount / item.get_expiry() * 60 < API_DEFAULT_FLOOR_PER_MINUTE for item in items):
                        fields[f'{where}.limit'] = (f'The default limit must allow at least {API_DEFAULT_FLOOR_PER_MINUTE} '
                                                    'requests per minute, or the web UI becomes unusable')
                    else:
                        entry['limit'] = limit.strip()
        if 'enabled' in ov:
            if not isinstance(ov['enabled'], bool):
                fields[f'{where}.enabled'] = 'Must be true or false'
            elif ov['enabled'] is False:
                entry['enabled'] = False
        if entry:
            clean['groups'][key] = entry
    if fields:
        raise RateLimitSettingsError('Invalid rate-limit settings', fields)
    return clean, weakening_warnings(clean)


def weakening_warnings(doc):
    warnings = []
    if doc.get('enabled') is False:
        warnings.append('Rate limiting is turned off for every route, including sign-in.')
    for key, ov in doc.get('groups', {}).items():
        gdef = GROUPS[key]
        if key == 'api_default' and ov.get('enabled') is False:
            warnings.append('The global safety-net limit (api_default) is disabled.')
        if not gdef.auth_sensitive:
            continue
        if ov.get('enabled') is False:
            warnings.append(f'{key}: an authentication limit is disabled (it falls back to api_default).')
        elif ov.get('limit') and _per_second(ov['limit']) > AUTH_LOOSEN_FACTOR * _per_second(gdef.default):
            warnings.append(f'{key}: more than {AUTH_LOOSEN_FACTOR}× the default ({gdef.default}).')
    return warnings


# ── Views ───────────────────────────────────────────────────────────────────

def describe():
    """Per-group view for the admin UI / API."""
    rows = []
    for key, gdef in GROUPS.items():
        limit, source, enabled, override = configured(key)
        rows.append({
            'key': key,
            'description': gdef.description,
            'category': gdef.category,
            'auth_sensitive': gdef.auth_sensitive,
            'routes': list(gdef.routes),
            'default': gdef.default,
            'env': _env_limit(key),
            'override': override.get('limit'),
            'limit': limit,
            'source': source,
            'enabled': enabled,
            'effective': None if is_exempt(key) else effective_limit(key),
        })
    return rows
