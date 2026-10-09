"""Session revocation: the single way to invalidate a user's tokens.

Every JWT carries the user's ``token_epoch`` at issue time; the blocklist
loader (``app.is_token_revoked``) rejects tokens minted before the current
epoch kept in Redis under ``token_epoch:<uid>``. Advancing the epoch therefore
revokes every outstanding access and refresh token of the user at once.

The bump is STRICT: when Redis is unavailable :func:`bump_token_epoch_strict`
raises :class:`SessionRevocationError` instead of silently doing nothing.
Endpoints roll back the state change that asked for the revocation and
answer 503 ``revocation_failed`` (an admin must never see "disabled" while
the account's tokens still work).

Other features attach to revocations through hooks
(``register_revocation_hook(fn)``, ``fn(user, reason)``), e.g. stamping
``Session.revoked_at`` (security-policy) or revoking API keys (api-keys).
Hooks run inside the caller's transaction, before it commits; a failing hook
fails the revocation (and so the request) with SessionRevocationError.

Reasons in use: ``disabled``, ``deleted``, ``force_logout``,
``password_reset``, ``mfa_reset``, ``password_changed``.
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

REVOCATION_REASONS = ('disabled', 'deleted', 'force_logout', 'password_reset', 'mfa_reset',
                      'password_changed')

_hooks: list[Callable] = []


class SessionRevocationError(Exception):
    """The epoch bump (or a revocation hook) failed; nothing may be reported
    as revoked. Endpoints answer 503 ``revocation_failed`` and roll back."""


def register_revocation_hook(fn: Callable) -> Callable:
    """Register ``fn(user, reason)`` to run on every revoke_all_sessions().
    Idempotent; usable as a decorator."""
    if fn not in _hooks:
        _hooks.append(fn)
    return fn


def _redis():
    from app import redis_client
    return redis_client


def bump_token_epoch_strict(user_id) -> int:
    """Advance ``token_epoch:<uid>``; returns the new epoch.

    Raises SessionRevocationError when the token store is unavailable."""
    client = _redis()
    if client is None:
        raise SessionRevocationError('token store unavailable')
    try:
        return int(client.incr(f'token_epoch:{user_id}'))
    except Exception as exc:
        logger.error('token epoch bump failed for user %s: %s', user_id, type(exc).__name__)
        raise SessionRevocationError('token store unavailable') from exc


def revoke_all_sessions(user, reason: str, *, notify: bool = True) -> None:
    """Revoke every token and live socket of ``user``.

    1. strict epoch bump (raises SessionRevocationError);
    2. revocation hooks (inside the caller's transaction);
    3. ``session:revoked`` {reason} to ``user_<id>`` (skipped with
       ``notify=False``, e.g. the user's own password change);
    4. server-side disconnect of every socket of the user (all workers).

    Call it after staging the state change and before committing; on
    SessionRevocationError roll back and answer 503 ``revocation_failed``.
    """
    uid = str(user.id)
    bump_token_epoch_strict(uid)
    for hook in list(_hooks):
        try:
            hook(user, reason)
        except SessionRevocationError:
            raise
        except Exception as exc:
            logger.exception('revocation hook %r failed', getattr(hook, '__name__', hook))
            raise SessionRevocationError('revocation hook failed') from exc

    from app.services import realtime
    if notify:
        realtime.emit_to_user(uid, 'session:revoked', {'reason': reason})
    realtime.disconnect_user_sockets(uid)


def revocation_failed_response():
    """(json, 503) for a failed revocation. Callers roll back first."""
    from flask import jsonify
    return jsonify({'error': 'revocation_failed',
                    'message': 'Sessions could not be revoked; no change was made. Try again.'}), 503


__all__ = ['SessionRevocationError', 'REVOCATION_REASONS', 'register_revocation_hook',
           'bump_token_epoch_strict', 'revoke_all_sessions', 'revocation_failed_response']
