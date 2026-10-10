"""OpenID Connect single sign-on: authorization code flow with PKCE.

Flow (endpoints in api/v1/endpoints/sso.py):

1. ``start``: random ``state``, ``nonce`` and PKCE verifier are kept in Redis
   for 10 minutes (single use). The browser also gets a short-lived httpOnly
   cookie holding sha256(state), so a callback only completes in the browser
   that started it (login CSRF). Then 302 to the IdP.
2. ``callback``: the state is consumed and matched with the cookie, the code
   is exchanged at the token endpoint (client secret + PKCE verifier) and the
   ID token is verified: signature against the IdP's JWKS (RS/PS/ES only,
   never ``none`` or HMAC), exact ``iss``, ``aud`` containing the client id,
   ``azp``, ``exp``/``iat``/``nbf`` with 60 s leeway and the ``nonce``.
   Missing claims are filled from the userinfo endpoint (same ``sub``).
3. The user is resolved: by identity (provider, sub); else by email, only in
   the provider's organization, only with ``link_existing`` and a verified
   email (when required); else created when ``auto_provision`` is on. An
   email that belongs to another organization is always refused.
4. Group rules (allowed groups, role mappings, role sync that never removes
   the last admin), account checks (disabled, locked, service accounts) and
   the provider's MFA mode decide the outcome.

Every outbound URL (discovery, JWKS, token, userinfo) passes
``validate_outbound_url`` (private addresses only when on
OUTBOUND_URL_ALLOWLIST) and must be https unless SSO_ALLOW_HTTP_ISSUERS is on
(labs and tests). Discovery and JWKS are cached in Redis for an hour; an
unknown ``kid`` refetches the JWKS at most once a minute.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote, urlencode, urlparse

import jwt
import requests
from flask import current_app, request, url_for
from sqlalchemy import func

from app import db
from app.models import Role, User, UserRole
from app.models.sso import SsoProvider, UserIdentity
from app.services import security_policy
from app.services.encryption_service import encryption_service
from app.utils.url_validator import validate_outbound_url

logger = logging.getLogger(__name__)

STATE_TTL = 600
CACHE_TTL = 3600
JWKS_REFRESH_INTERVAL = 60
LEEWAY = 60
HTTP_TIMEOUT = 10
MAX_RESPONSE_BYTES = 1_000_000
ALLOWED_ALGS = ('RS256', 'RS384', 'RS512', 'PS256', 'PS384', 'PS512', 'ES256', 'ES384', 'ES512')
# RFC 8176 authentication method references that show a second factor or a
# phishing-resistant authenticator (used by mfa_mode 'idp_amr').
MFA_AMR = frozenset({'mfa', 'otp', 'hwk', 'swk', 'sms', 'tel', 'sc', 'fpt', 'face', 'iris', 'retina', 'vbm'})
STATE_COOKIE = 'sheetstorm_sso_state'
MFA_COOKIE = 'sheetstorm_sso_mfa'
DEFAULT_NEXT = '/dashboard'
_EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,255}$')

# Codes the login page turns into messages (frontend/src/lib/sso.ts).
ERROR_CODES = (
    'provider_unavailable', 'state_invalid', 'access_denied', 'token_invalid', 'email_missing',
    'email_unverified', 'domain_not_allowed', 'group_not_allowed', 'account_exists', 'account_conflict',
    'no_account', 'account_disabled', 'mfa_required', 'server_error',
)


class SsoError(Exception):
    """A refused or failed sign-in: ``code`` goes to the browser, ``detail``
    only to the audit log."""

    def __init__(self, code, detail=None, user=None):
        assert code in ERROR_CODES, code
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.user = user


@dataclass
class Profile:
    subject: str
    email: str | None
    email_verified: bool
    name: str
    groups: list = field(default_factory=list)
    amr: list = field(default_factory=list)


@dataclass
class Outcome:
    user: User
    identity: UserIdentity
    created: bool = False
    linked: bool = False
    roles_synced: bool = False
    needs_totp: bool = False


# ── Plumbing ────────────────────────────────────────────────────────

def _redis():
    from app import redis_client
    if redis_client is None:
        raise SsoError('server_error', 'Redis is not available')
    return redis_client


def _now():
    return datetime.now(timezone.utc)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _http_allowed(url) -> bool:
    return urlparse(url).scheme == 'https' or bool(current_app.config.get('SSO_ALLOW_HTTP_ISSUERS'))


def _http(method, url, **kwargs):
    """Call the IdP: SSRF-checked, no redirects, bounded time and size.
    Returns (status, body bytes, content type). Tests replace this."""
    if not _http_allowed(url):
        raise SsoError('provider_unavailable', f'refusing a non-https IdP URL: {url}')
    ok, reason = validate_outbound_url(url, allow_allowlisted_private=True)
    if not ok:
        raise SsoError('provider_unavailable', f'blocked IdP URL {url}: {reason}')
    try:
        resp = requests.request(method, url, timeout=HTTP_TIMEOUT, allow_redirects=False, stream=True, **kwargs)
        body = resp.raw.read(MAX_RESPONSE_BYTES + 1, decode_content=True)
        resp.close()
    except requests.RequestException as exc:
        raise SsoError('provider_unavailable', f'{method} {url}: {exc.__class__.__name__}')
    if len(body) > MAX_RESPONSE_BYTES:
        raise SsoError('provider_unavailable', f'{url}: response larger than {MAX_RESPONSE_BYTES} bytes')
    return resp.status_code, body, resp.headers.get('Content-Type', '')


def _json_object(status, body, what, code='provider_unavailable'):
    if status != 200:
        raise SsoError(code, f'{what}: HTTP {status}')
    try:
        data = json.loads(body)
    except ValueError:
        raise SsoError(code, f'{what}: not JSON')
    if not isinstance(data, dict):
        raise SsoError(code, f'{what}: not a JSON object')
    return data


def _cache_get(key):
    try:
        raw = _redis().get(key)
        return json.loads(raw) if raw else None
    except (SsoError, ValueError, Exception):  # cache trouble is never fatal
        return None


def _cache_set(key, value, ttl=CACHE_TTL):
    try:
        _redis().setex(key, ttl, json.dumps(value))
    except Exception:
        pass


def forget_cached(provider) -> None:
    """Drop cached discovery + JWKS (after the provider's issuer changes)."""
    try:
        _redis().delete(f'sso:disc:{provider.id}', f'sso:jwks:{provider.id}')
    except Exception:
        pass


def client_secret(provider):
    if not provider.client_secret_encrypted:
        return None
    return encryption_service.decrypt(provider.client_secret_encrypted)


def set_client_secret(provider, secret) -> None:
    provider.client_secret_encrypted = encryption_service.encrypt(secret) if secret else None


def safe_next(value) -> str:
    """A same-site relative path to land on after sign-in, else the dashboard."""
    if (not isinstance(value, str) or not value.startswith('/') or value.startswith('//')
            or '\\' in value or len(value) > 500 or any(ord(c) < 32 for c in value)):
        return DEFAULT_NEXT
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return DEFAULT_NEXT
    return value


def _public_base() -> str:
    base = (current_app.config.get('SSO_REDIRECT_BASE_URL') or current_app.config.get('FRONTEND_URL') or '')
    base = base.strip().rstrip('/')
    return base or request.host_url.rstrip('/')


def redirect_uri(provider) -> str:
    """The callback URL to register at the IdP."""
    return _public_base() + url_for('api_v1.sso_callback', slug=provider.slug)


def redirect_uri_template() -> str:
    """The callback URL with ``{slug}`` in place of the provider slug (the
    admin editor previews it before a provider exists)."""
    return _public_base() + url_for('api_v1.sso_callback', slug='SLUG').replace('/SLUG/', '/{slug}/')


def frontend_url(path) -> str:
    """Absolute URL of a frontend path when FRONTEND_URL is set (API on
    another origin), else the path itself (same origin behind the proxy)."""
    base = (current_app.config.get('FRONTEND_URL') or '').strip().rstrip('/')
    return base + path if base else path


# ── Discovery and keys ──────────────────────────────────────────────

_DISCOVERY_FIELDS = (
    'issuer', 'authorization_endpoint', 'token_endpoint', 'jwks_uri', 'userinfo_endpoint',
    'end_session_endpoint', 'id_token_signing_alg_values_supported', 'code_challenge_methods_supported',
    'token_endpoint_auth_methods_supported', 'scopes_supported', 'claims_supported',
)


def discovery(provider, refresh=False) -> dict:
    """The IdP's OpenID configuration (issuer must match the configured one,
    ignoring a trailing slash; the IdP's exact spelling is used afterwards)."""
    key = f'sso:disc:{provider.id}'
    if not refresh:
        cached = _cache_get(key)
        if cached and cached.get('_for') == provider.issuer:
            return cached
    url = provider.issuer.rstrip('/') + '/.well-known/openid-configuration'
    doc = _json_object(*_http('GET', url, headers={'Accept': 'application/json'})[:2], 'discovery')
    issuer = doc.get('issuer')
    if not isinstance(issuer, str) or issuer.rstrip('/') != provider.issuer.rstrip('/'):
        raise SsoError('provider_unavailable', f'discovery issuer {str(issuer)[:200]!r} does not match '
                                               f'the configured issuer {provider.issuer!r}')
    for name in ('authorization_endpoint', 'token_endpoint', 'jwks_uri'):
        value = doc.get(name)
        if not isinstance(value, str) or urlparse(value).scheme not in ('https', 'http') \
                or not urlparse(value).hostname:
            raise SsoError('provider_unavailable', f'discovery: missing or invalid {name}')
        if not _http_allowed(value):
            raise SsoError('provider_unavailable', f'discovery: {name} is not https')
    out = {k: doc[k] for k in _DISCOVERY_FIELDS if k in doc}
    out['_for'] = provider.issuer
    _cache_set(key, out)
    return out


def _jwks(provider, disc, refresh=False) -> list:
    key = f'sso:jwks:{provider.id}'
    if not refresh:
        cached = _cache_get(key)
        if cached is not None:
            return cached
    data = _json_object(*_http('GET', disc['jwks_uri'], headers={'Accept': 'application/json'})[:2], 'jwks')
    keys = [k for k in data.get('keys') or [] if isinstance(k, dict)]
    if not keys:
        raise SsoError('provider_unavailable', 'jwks: no keys')
    _cache_set(key, keys)
    return keys


def _may_refresh_jwks(provider) -> bool:
    try:
        return bool(_redis().set(f'sso:jwks_refresh:{provider.id}', '1', nx=True, ex=JWKS_REFRESH_INTERVAL))
    except Exception:
        return False


def _candidate_keys(provider, disc, kid, alg):
    for attempt in range(2):
        keys = _jwks(provider, disc, refresh=attempt == 1)
        found = []
        for jwk_dict in keys:
            if jwk_dict.get('use', 'sig') != 'sig':
                continue
            if kid is not None and jwk_dict.get('kid') != kid:
                continue
            if jwk_dict.get('alg') and jwk_dict['alg'] != alg:
                continue
            try:
                found.append(jwt.PyJWK(jwk_dict, algorithm=alg).key)
            except (jwt.PyJWTError, ValueError, TypeError, KeyError):
                continue
        if found:
            return found
        if attempt == 0 and not _may_refresh_jwks(provider):
            break
    raise SsoError('token_invalid', f'no usable signing key for kid={kid!r} alg={alg}')


def verify_id_token(provider, disc, id_token, nonce) -> dict:
    if not isinstance(id_token, str) or id_token.count('.') != 2:
        raise SsoError('token_invalid', 'missing or malformed ID token')
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise SsoError('token_invalid', f'ID token header: {exc}')
    alg = header.get('alg')
    if alg not in ALLOWED_ALGS:
        raise SsoError('token_invalid', f'ID token algorithm {alg!r} is not allowed')
    claims = None
    for key in _candidate_keys(provider, disc, header.get('kid'), alg):
        try:
            claims = jwt.decode(
                id_token, key, algorithms=[alg], audience=provider.client_id, issuer=disc['issuer'],
                leeway=LEEWAY, options={'require': ['iss', 'sub', 'aud', 'exp', 'iat']})
            break
        except jwt.InvalidSignatureError:
            continue
        except jwt.PyJWTError as exc:
            raise SsoError('token_invalid', f'ID token: {exc.__class__.__name__}: {exc}')
    if claims is None:
        raise SsoError('token_invalid', 'ID token signature does not verify')
    aud = claims['aud']
    audiences = [aud] if isinstance(aud, str) else list(aud)
    azp = claims.get('azp')
    if (len(audiences) > 1 or azp is not None) and azp != provider.client_id:
        raise SsoError('token_invalid', 'ID token azp is not this client')
    token_nonce = claims.get('nonce')
    if not isinstance(token_nonce, str) or not hmac.compare_digest(token_nonce, nonce):
        raise SsoError('token_invalid', 'ID token nonce does not match')
    sub = claims.get('sub')
    if not isinstance(sub, str) or not sub or len(sub) > 255:
        raise SsoError('token_invalid', 'ID token sub is missing or too long')
    return claims


# ── Flow ────────────────────────────────────────────────────────────

def provider_by_slug(slug):
    if not isinstance(slug, str) or len(slug) > 40:
        return None
    return SsoProvider.query.filter_by(slug=slug.lower()).first()


def start(provider, next_path):
    """(authorization URL, state). The caller sets the state cookie."""
    disc = discovery(provider)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    pending = {'provider_id': str(provider.id), 'nonce': nonce, 'verifier': verifier,
               'next': safe_next(next_path)}
    try:
        _redis().setex(f'sso:state:{state}', STATE_TTL, json.dumps(pending))
    except SsoError:
        raise
    except Exception as exc:
        raise SsoError('server_error', f'storing the sign-in state failed: {exc.__class__.__name__}')
    params = {
        'response_type': 'code', 'client_id': provider.client_id, 'redirect_uri': redirect_uri(provider),
        'scope': provider.scopes, 'state': state, 'nonce': nonce,
        'code_challenge': _b64url(hashlib.sha256(verifier.encode()).digest()), 'code_challenge_method': 'S256',
    }
    endpoint = disc['authorization_endpoint']
    return endpoint + ('&' if '?' in endpoint else '?') + urlencode(params), state


def state_cookie_value(state) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def consume_state(provider, state, cookie_value) -> dict:
    """The pending sign-in for `state` (single use), bound to this browser."""
    if not isinstance(state, str) or not 10 <= len(state) <= 200:
        raise SsoError('state_invalid', 'missing state')
    try:
        raw = _redis().getdel(f'sso:state:{state}')
    except SsoError:
        raise
    except Exception as exc:
        raise SsoError('server_error', f'reading the sign-in state failed: {exc.__class__.__name__}')
    if not raw:
        raise SsoError('state_invalid', 'unknown or expired state')
    pending = json.loads(raw)
    if not cookie_value or not hmac.compare_digest(cookie_value, state_cookie_value(state)):
        raise SsoError('state_invalid', 'state cookie missing or for another sign-in')
    if pending.get('provider_id') != str(provider.id):
        raise SsoError('state_invalid', 'state belongs to another provider')
    return pending


def exchange_code(provider, disc, code, verifier) -> dict:
    if not isinstance(code, str) or not code or len(code) > 4096:
        raise SsoError('token_invalid', 'missing authorization code')
    data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect_uri(provider),
            'code_verifier': verifier}
    headers = {'Accept': 'application/json'}
    secret = client_secret(provider)
    if provider.token_auth_method == 'client_secret_basic' and secret:
        # RFC 6749 2.3.1: form-encode each part before base64.
        pair = f'{quote(provider.client_id, safe="")}:{quote(secret, safe="")}'
        headers['Authorization'] = 'Basic ' + base64.b64encode(pair.encode()).decode()
    else:
        data['client_id'] = provider.client_id
        if provider.token_auth_method == 'client_secret_post' and secret:
            data['client_secret'] = secret
    status, body, _ctype = _http('POST', disc['token_endpoint'], data=data, headers=headers)
    if status != 200:
        try:
            err = json.loads(body)
            reason = f"{err.get('error')}: {str(err.get('error_description', ''))[:200]}"
        except (ValueError, AttributeError):
            reason = f'HTTP {status}'
        raise SsoError('token_invalid', f'token endpoint refused the code ({reason})')
    tokens = _json_object(status, body, 'token response', code='token_invalid')
    if not isinstance(tokens.get('id_token'), str):
        raise SsoError('token_invalid', 'token response has no id_token (is the openid scope granted?)')
    return tokens


def claim(claims, path):
    """A claim by exact name (URL-style names contain dots), else by dotted
    path into nested objects (``realm_access.roles``)."""
    if not path:
        return None
    if path in claims:
        return claims[path]
    current = claims
    for part in path.split('.'):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _needs_userinfo(provider, claims) -> bool:
    if not any(isinstance(claim(claims, c), str) for c in provider.email_claims):
        return True
    return bool(provider.groups_claim) and claim(claims, provider.groups_claim) is None


def merge_userinfo(provider, disc, claims, access_token) -> dict:
    endpoint = disc.get('userinfo_endpoint')
    if not endpoint or not isinstance(access_token, str) or not _needs_userinfo(provider, claims):
        return claims
    status, body, ctype = _http('GET', endpoint, headers={'Authorization': f'Bearer {access_token}',
                                                          'Accept': 'application/json'})
    if status != 200 or 'json' not in ctype.lower():
        logger.warning('SSO %s: userinfo returned HTTP %s (%s); using ID token claims only',
                       provider.slug, status, ctype[:50])
        return claims
    try:
        info = json.loads(body)
    except ValueError:
        return claims
    if not isinstance(info, dict):
        return claims
    if info.get('sub') != claims['sub']:
        raise SsoError('token_invalid', 'userinfo sub does not match the ID token')
    return {**info, **claims}  # the signed ID token wins


def profile_from_claims(provider, claims) -> Profile:
    email, verified = None, False
    for name in provider.email_claims:
        value = claim(claims, name)
        if isinstance(value, str) and _EMAIL_RE.match(value.strip()) and len(value) <= 255:
            email = value.strip().lower()
            # Only the standard `email` claim carries a verification flag.
            verified = name == 'email' and claims.get('email_verified') in (True, 'true')
            break
    display = claim(claims, provider.name_claim)
    if not isinstance(display, str) or not display.strip():
        parts = [claims.get('given_name'), claims.get('family_name')]
        display = ' '.join(p for p in parts if isinstance(p, str) and p) or claims.get('preferred_username')
    if not isinstance(display, str) or not display.strip():
        display = email.split('@')[0] if email else claims['sub']
    groups = []
    if provider.groups_claim:
        raw = claim(claims, provider.groups_claim)
        if isinstance(raw, str):
            raw = [raw]
        if isinstance(raw, list):
            groups = [str(g) for g in raw if isinstance(g, (str, int)) and str(g)][:1000]
        elif raw is None and 'groups' in (claims.get('_claim_names') or {}):
            logger.warning('SSO %s: the IdP left out the groups claim (too many groups: Entra ID '
                           '"overage"); map app roles instead', provider.slug)
    amr = [a for a in claims.get('amr') or [] if isinstance(a, str)]
    return Profile(subject=claims['sub'], email=email, email_verified=verified,
                   name=display.strip()[:255], groups=groups, amr=amr)


# ── Users and roles ─────────────────────────────────────────────────

def _domain_allowed(provider, email) -> bool:
    domain = email.rsplit('@', 1)[1]
    if provider.allowed_domains and domain not in provider.allowed_domains:
        return False
    return security_policy.check_email_domain(email, security_policy.get_policy(provider.organization_id))


def _groups_match(groups, wanted) -> set:
    have = {g.casefold() for g in groups}
    return {w for w in wanted if w.casefold() in have}


def _visible_roles(provider, ids):
    if not ids:
        return []
    return Role.visible_to(provider.organization_id).filter(Role.id.in_(list(ids))).all()


def _editor_may_grant(provider, roles) -> bool:
    """The admin who last configured the provider must still be able to grant
    every role it hands out (same rule as an invitation)."""
    from app.services.rbac_guard import GuardError, assert_can_grant_roles
    if not roles:
        return True
    editor_id = provider.updated_by or provider.created_by
    editor = db.session.get(User, editor_id) if editor_id else None
    if (editor is None or not editor.is_active or editor.organization_id != provider.organization_id
            or not editor.has_permission('roles:manage')):
        return False
    try:
        assert_can_grant_roles(editor, roles)
    except GuardError:
        return False
    return True


def target_roles(provider, groups):
    """Roles a sign-in grants: the mapped groups' roles, else the provider's
    default role, else the organization policy's default role. Configured
    roles the provider's editor can no longer grant are not handed out."""
    from app.middleware.audit import log_security_event
    wanted = {m['role_id'] for m in provider.role_mappings or []
              if _groups_match(groups, [m.get('group', '')])}
    roles = _visible_roles(provider, wanted)
    if not roles and provider.default_role_id:
        roles = _visible_roles(provider, [provider.default_role_id])
    if roles and not _editor_may_grant(provider, roles):
        log_security_event('sso_role_mapping_ignored', resource_type='sso_provider', resource_id=provider.id,
                           organization_id=provider.organization_id,
                           details={'provider': provider.slug, 'roles': sorted(r.name for r in roles)})
        roles = []
    if not roles:
        fallback = security_policy.default_role(security_policy.get_policy(provider.organization_id),
                                                provider.organization_id)
        roles = [fallback] if fallback else []
    return roles


def _sync_roles(provider, user, roles) -> bool:
    """Make the user's roles exactly `roles`; refused (and logged) when it
    would leave the organization without an administrator."""
    from app.middleware.audit import log_security_event
    from app.services.rbac_guard import GuardError, assert_admin_remains
    target_ids = {r.id for r in roles}
    current = list(user.user_roles)
    remove = [ur for ur in current if ur.role_id not in target_ids]
    have = {ur.role_id for ur in current}
    add = [r for r in roles if r.id not in have]
    if not remove and not add:
        return False
    if remove:
        try:
            assert_admin_remains(provider.organization_id, resource_type='user', resource_id=user.id,
                                 drop_assignments=[(user.id, ur.role_id) for ur in remove])
        except GuardError:
            log_security_event('sso_role_sync_blocked', resource_type='user', resource_id=user.id,
                               organization_id=provider.organization_id,
                               details={'provider': provider.slug, 'reason': 'last_admin'})
            return False
    for ur in remove:
        db.session.delete(ur)
    for role in add:
        db.session.add(UserRole(user_id=user.id, role_id=role.id, organization_id=provider.organization_id))
    return True


def _check_account(user):
    if user.is_service_account or not user.is_active:
        raise SsoError('account_disabled', 'account is disabled or a service account', user=user)
    if user.is_locked:
        raise SsoError('account_disabled', 'account is locked', user=user)


def resolve_user(provider, profile) -> Outcome:
    """Find, link or create the SheetStorm user for a verified IdP identity
    and apply the provider's group and role rules. Flushes, does not commit."""
    if provider.allowed_groups and not _groups_match(profile.groups, provider.allowed_groups):
        raise SsoError('group_not_allowed',
                       f'groups {profile.groups[:20]} do not include an allowed group')

    identity = UserIdentity.query.filter_by(provider_id=provider.id, subject=profile.subject).first()
    if identity is not None:
        user = identity.user
        if user is None or user.organization_id != provider.organization_id:
            raise SsoError('account_conflict', 'identity linked to a user of another organization')
        _check_account(user)
        if profile.email:
            identity.email = profile.email
        outcome = Outcome(user=user, identity=identity)
    else:
        if not profile.email:
            raise SsoError('email_missing', f'none of the claims {provider.email_claims} holds an email')
        if provider.require_email_verified and not profile.email_verified:
            raise SsoError('email_unverified', f'{profile.email} is not marked verified by the IdP')
        if not _domain_allowed(provider, profile.email):
            raise SsoError('domain_not_allowed', f'{profile.email} is outside the allowed domains')
        user = User.query.filter(func.lower(User.email) == profile.email).first()
        if user is not None:
            if user.organization_id != provider.organization_id:
                raise SsoError('account_conflict', f'{profile.email} belongs to another organization')
            if not provider.link_existing:
                raise SsoError('account_exists', f'{profile.email} exists and account linking is off', user=user)
            if UserIdentity.query.filter_by(provider_id=provider.id, user_id=user.id).first() is not None:
                raise SsoError('account_conflict',
                               f'{profile.email} is already linked to another subject of this provider', user=user)
            _check_account(user)
            identity = UserIdentity(user_id=user.id, provider_id=provider.id, subject=profile.subject,
                                    email=profile.email)
            db.session.add(identity)
            outcome = Outcome(user=user, identity=identity, linked=True)
        else:
            if not provider.auto_provision:
                raise SsoError('no_account', f'no account for {profile.email} and auto-provisioning is off')
            user = User(email=profile.email, name=profile.name, organization_id=provider.organization_id,
                        auth_provider='oidc', is_active=True, is_verified=True)
            db.session.add(user)
            db.session.flush()
            identity = UserIdentity(user_id=user.id, provider_id=provider.id, subject=profile.subject,
                                    email=profile.email)
            db.session.add(identity)
            for role in target_roles(provider, profile.groups):
                db.session.add(UserRole(user_id=user.id, role_id=role.id,
                                        organization_id=provider.organization_id))
            outcome = Outcome(user=user, identity=identity, created=True)

    if not outcome.created and provider.role_sync == 'every_login':
        outcome.roles_synced = _sync_roles(provider, outcome.user, target_roles(provider, profile.groups))

    if provider.mfa_mode == 'idp_amr' and not (set(profile.amr) & MFA_AMR):
        raise SsoError('mfa_required', f'amr {profile.amr} shows no second factor', user=outcome.user)
    outcome.needs_totp = (provider.mfa_mode == 'sheetstorm' and bool(outcome.user.mfa_enabled)
                          and bool(outcome.user.mfa_secret))
    db.session.flush()
    return outcome


def idp_handles_mfa(user) -> bool:
    """True for an SSO-only user (no password) whose every linked provider
    enforces MFA itself (mfa_mode idp / idp_amr): SheetStorm then does not
    require its own TOTP enrollment for them."""
    if user is None or user.password_hash or user.auth_provider != 'oidc':
        return False
    modes = [m for (m,) in db.session.query(SsoProvider.mfa_mode)
             .join(UserIdentity, UserIdentity.provider_id == SsoProvider.id)
             .filter(UserIdentity.user_id == user.id).all()]
    return bool(modes) and all(m in ('idp', 'idp_amr') for m in modes)


def check_configuration(provider) -> dict:
    """Admin "Test": fetch discovery and keys fresh and report what matters."""
    checks = []

    def add(name, ok, detail, warn=False):
        checks.append({'name': name, 'ok': bool(ok), 'warning': bool(warn and ok), 'detail': detail})

    try:
        disc = discovery(provider, refresh=True)
        add('discovery', True, f"issuer {disc['issuer']}")
    except SsoError as exc:
        add('discovery', False, exc.detail)
        return {'ok': False, 'checks': checks, 'redirect_uri': redirect_uri(provider)}
    try:
        keys = _jwks(provider, disc, refresh=True)
        add('signing keys', True, f'{len(keys)} key(s) published')
    except SsoError as exc:
        add('signing keys', False, exc.detail)
    algs = disc.get('id_token_signing_alg_values_supported') or []
    usable = [a for a in algs if a in ALLOWED_ALGS]
    add('ID token algorithm', bool(usable) or not algs,
        f"supported: {', '.join(algs) or 'not advertised'}" + ('' if usable or not algs else
                                                              ' (none of RS/PS/ES: not supported)'))
    methods = disc.get('code_challenge_methods_supported')
    add('PKCE', True, 'S256 supported' if methods and 'S256' in methods else
        'S256 not advertised (PKCE is sent anyway)', warn=not (methods and 'S256' in methods))
    auth_methods = disc.get('token_endpoint_auth_methods_supported') or ['client_secret_basic']
    configured = provider.token_auth_method
    add('client authentication', configured in auth_methods or configured == 'none',
        f"configured {configured}; IdP supports {', '.join(auth_methods)}")
    if configured != 'none' and not provider.client_secret_encrypted:
        add('client secret', True, 'no client secret stored (public client)', warn=True)
    scopes = disc.get('scopes_supported')
    missing = [s for s in provider.scopes.split() if scopes and s not in scopes]
    add('scopes', True, f"missing from the IdP's list: {', '.join(missing)}" if missing else 'all advertised',
        warn=bool(missing))
    return {'ok': all(c['ok'] for c in checks), 'checks': checks, 'redirect_uri': redirect_uri(provider)}


__all__ = [
    'SsoError', 'Profile', 'Outcome', 'ERROR_CODES', 'STATE_COOKIE', 'MFA_COOKIE', 'ALLOWED_ALGS', 'MFA_AMR',
    'safe_next', 'redirect_uri', 'redirect_uri_template', 'frontend_url', 'discovery', 'verify_id_token', 'provider_by_slug', 'start',
    'state_cookie_value', 'consume_state', 'exchange_code', 'claim', 'merge_userinfo', 'profile_from_claims',
    'target_roles', 'resolve_user', 'idp_handles_mfa', 'check_configuration', 'client_secret',
    'set_client_secret', 'forget_cached',
]
