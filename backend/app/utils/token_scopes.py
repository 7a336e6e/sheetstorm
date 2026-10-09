"""API-key token introspection for the current request.

An access token minted by ``POST /auth/token`` carries ``api_key_id``,
``api_key_prefix`` and ``scopes`` claims. ``User.permissions`` intersects the
owner's role permissions with those scopes (``current_scope_limit``), which
covers every permission decorator, ``check_permission`` and direct
``has_permission`` call in one place.

Imports only flask / flask_jwt_extended (no models), so the User model can
use it without an import cycle.
"""
from __future__ import annotations

from flask import has_request_context


def _claims() -> dict:
    """Claims of the JWT verified in this request, or {} (none / not verified)."""
    if not has_request_context():
        return {}
    from flask_jwt_extended import get_jwt
    try:
        claims = get_jwt()
    except RuntimeError:  # no JWT verified in this request
        return {}
    return claims or {}


def current_scope_limit(user_id) -> frozenset | None:
    """The scope set limiting `user_id` in this request, or None (no limit).

    Only applies when the request's token is an API-key token whose subject
    is `user_id`; any other user object (e.g. a target user) is unaffected.
    """
    claims = _claims()
    if not claims.get('api_key_id') or claims.get('sub') != str(user_id):
        return None
    scopes = claims.get('scopes')
    if not isinstance(scopes, (list, tuple)):
        return frozenset()
    return frozenset(s for s in scopes if isinstance(s, str))


def is_api_key_request() -> bool:
    """True when the current request is authenticated by an API-key token."""
    return bool(_claims().get('api_key_id'))


def api_key_auth_context() -> dict | None:
    """``{method, api_key_id, api_key_prefix}`` for audit attribution, or None."""
    claims = _claims()
    if not claims.get('api_key_id'):
        return None
    return {
        'method': 'api_key',
        'api_key_id': str(claims.get('api_key_id')),
        'api_key_prefix': claims.get('api_key_prefix'),
    }


__all__ = ['current_scope_limit', 'is_api_key_request', 'api_key_auth_context']
