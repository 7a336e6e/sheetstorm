"""Restricted-account gate: one ``api_bp.before_request`` for every
account-state restriction.

A restriction is ``(code, predicate(user), allowlist, applies_to_api_keys)``.
For an authenticated request whose user matches a predicate, every endpoint
outside that restriction's allowlist answers 403 ``{error: <code>}``.

State is derived from the DB on every request (there is no JWT claim), so
lifting a restriction (e.g. changing the password) takes effect at once and
a stale token cannot carry an old state. The WebSocket treats restricted
users as anonymous (``restriction_for`` in ``api/websocket``).

Registered here: ``password_change_required`` (``users.must_change_password``,
set by an admin temp-password reset or the seeded bootstrap admin). The
security-policy feature registers ``mfa_enrollment_required`` with
``applies_to_api_keys=False``.

Unauthenticated requests, refresh tokens and invalid tokens fall through to
the route's own handling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from flask import g, jsonify, request

# Endpoints a restricted user still needs: read their own state, leave the
# restriction, end the session. `api_key_exchange` (POST /auth/token)
# authenticates by the API key alone and never reads the JWT identity; the
# token it issues is still gated on every other route.
BASE_ALLOWLIST = frozenset({
    'api_v1.api_key_exchange',
    'api_v1.get_current_user',
    'api_v1.change_password',
    'api_v1.logout',
    'api_v1.refresh',
    'api_v1.health_check',
    'api_v1.readiness_check',
    'api_v1.liveness_check',
})

MESSAGES = {
    'password_change_required': 'You must change your password before continuing.',
    'mfa_enrollment_required': 'You must enroll in multi-factor authentication before continuing.',
}


@dataclass
class Restriction:
    code: str
    predicate: Callable
    allowlist: set = field(default_factory=set)
    applies_to_api_keys: bool = True


_RESTRICTIONS: dict[str, Restriction] = {}


def register_restriction(code: str, predicate: Callable, allowlist=(), *, applies_to_api_keys: bool = True):
    """Register (or replace) restriction `code`. `allowlist` holds endpoint
    names (``api_v1.<function>``) on top of BASE_ALLOWLIST."""
    _RESTRICTIONS[code] = Restriction(code, predicate, set(BASE_ALLOWLIST) | set(allowlist or ()),
                                      applies_to_api_keys)


def extend_allowlist(code: str, *endpoints: str) -> None:
    """Allow more endpoints for an already registered restriction."""
    _RESTRICTIONS[code].allowlist.update(endpoints)


def restriction_for(user, *, api_key: bool = False, endpoint: str | None = None):
    """The first restriction code that applies to `user`, else None.

    With `endpoint`, restrictions allowlisting that endpoint are skipped."""
    if user is None:
        return None
    for r in _RESTRICTIONS.values():
        if api_key and not r.applies_to_api_keys:
            continue
        if endpoint is not None and endpoint in r.allowlist:
            continue
        try:
            if r.predicate(user):
                return r.code
        except Exception:  # a broken predicate must not open the gate
            return r.code
    return None


def _gate():
    if request.method == 'OPTIONS' or not _RESTRICTIONS:
        return None
    from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
    except Exception:
        return None  # invalid / refresh / revoked token: the route answers
    if not identity:
        return None

    from app import db
    from app.models import User
    user = db.session.get(User, identity)
    if user is None or not user.is_active:
        return None
    g.current_user = user

    claims = get_jwt() or {}
    code = restriction_for(user, api_key=bool(claims.get('api_key_id')), endpoint=request.endpoint)
    if code:
        return jsonify({'error': code, 'message': MESSAGES.get(code, 'Account restricted')}), 403
    return None


def register(api_bp) -> None:
    """Install the gate on the API blueprint (once)."""
    if getattr(api_bp, '_account_state_gate', False):
        return
    api_bp.before_request(_gate)
    api_bp._account_state_gate = True


register_restriction('password_change_required', lambda u: bool(getattr(u, 'must_change_password', False)))


def _mfa_enrollment_required(user):
    """Security policy requires MFA for the user, they have not enrolled and
    the grace period is over (services/security_policy.py)."""
    from app.services.security_policy import mfa_enrollment_required
    return mfa_enrollment_required(user)


# W3-SEC: API keys are exempt (a key never enrolls MFA; C30).
register_restriction('mfa_enrollment_required', _mfa_enrollment_required,
                     ('api_v1.mfa_setup', 'api_v1.mfa_verify', 'api_v1.password_policy'),
                     applies_to_api_keys=False)
extend_allowlist('password_change_required', 'api_v1.password_policy')


__all__ = ['BASE_ALLOWLIST', 'register_restriction', 'extend_allowlist', 'restriction_for', 'register']
