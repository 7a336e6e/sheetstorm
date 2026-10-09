"""Sign-in sessions: inventory, token issue/rotation, per-session revocation.

Every interactive sign-in creates one ``sessions`` row; its id travels as the
``sid`` claim in the access and refresh tokens minted for it. Refresh keeps
the row (``rotate``) and records the newest refresh ``jti``.

Revocation:

* one session (``revoke``) or every session but the current one
  (``revoke_others``, "sign out other devices"): ``revoked_at`` is stamped,
  ``revoked_session:<sid>`` is written to Redis (checked by
  ``app.is_token_revoked`` for access AND refresh tokens, so it also covers
  the WebSocket) and the latest refresh jti is blocklisted. No epoch bump:
  the user's other sessions keep working.
* all sessions: ``token_revocation.revoke_all_sessions`` (epoch bump); the
  hook registered here only stamps the rows.

Token lifetimes come from the org policy (``session.*``) and apply to newly
issued tokens only. API-key tokens carry no sid and never touch this module.
"""
from __future__ import annotations

import ipaddress
import logging
import uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

TOUCH_INTERVAL_SECONDS = 300
PRUNE_AFTER_DAYS = 30
REVOKED_MARKER_MAX_SECONDS = 30 * 24 * 3600
REASON_MAX = 32


def _now():
    return datetime.now(timezone.utc)


def _redis():
    from app import redis_client
    return redis_client


def _client_ip():
    from flask import has_request_context, request
    if not has_request_context():
        return None
    try:
        return str(ipaddress.ip_address((request.remote_addr or '').strip()))
    except ValueError:
        return None


def _user_agent():
    from flask import has_request_context, request
    if not has_request_context():
        return None
    ua = request.headers.get('User-Agent') or ''
    return ua[:500] or None


def _current_token_epoch(user_id) -> int:
    client = _redis()
    if client is None:
        return 0
    try:
        val = client.get(f'token_epoch:{user_id}')
        return int(val) if val is not None else 0
    except Exception:
        return 0


def _prune_user(user_id) -> None:
    """Drop the user's sessions that ended more than PRUNE_AFTER_DAYS ago."""
    from app.models import Session
    from sqlalchemy import or_
    cutoff = _now() - timedelta(days=PRUNE_AFTER_DAYS)
    Session.query.filter(Session.user_id == user_id,
                         or_(Session.revoked_at < cutoff, Session.expires_at < cutoff)) \
        .delete(synchronize_session=False)


def start_session(user, auth_method='password'):
    """Stage a new session row for `user` (IP / user agent from the request)."""
    from app import db
    from app.models import Session
    _prune_user(user.id)
    now = _now()
    session = Session(id=uuid.uuid4(), user_id=user.id, organization_id=user.organization_id,
                      auth_method=(auth_method or 'password')[:REASON_MAX], ip_address=_client_ip(),
                      user_agent=_user_agent(), created_at=now, last_seen_at=now, expires_at=now)
    db.session.add(session)
    return session


def _refresh_jti(refresh_token):
    import jwt as pyjwt
    return pyjwt.decode(refresh_token, options={'verify_signature': False}).get('jti')


def issue_tokens(user, *, session=None, auth_method='password', commit=True):
    """Mint (access, refresh) for `user` on `session` (a new one when None).

    Claims: ``token_epoch`` (all-sessions revocation) and ``sid``. Lifetimes
    come from the org policy. Commits by default (callers have committed
    their own work first)."""
    from app import db
    from flask_jwt_extended import create_access_token, create_refresh_token
    from app.services import security_policy

    access_ttl, refresh_ttl = security_policy.token_lifetimes(user.organization_id)
    if session is None:
        session = start_session(user, auth_method)
    claims = {'token_epoch': _current_token_epoch(user.id), 'sid': str(session.id)}
    access = create_access_token(identity=str(user.id), additional_claims=claims, expires_delta=access_ttl)
    refresh = create_refresh_token(identity=str(user.id), additional_claims=claims, expires_delta=refresh_ttl)
    now = _now()
    session.refresh_jti = _refresh_jti(refresh)
    session.expires_at = now + refresh_ttl
    session.last_seen_at = now
    if commit:
        db.session.commit()
    return access, refresh


def rotate(session, user):
    """Refresh: new token pair on the same session."""
    return issue_tokens(user, session=session)


def get_session(sid):
    from app import db
    from app.models import Session
    if not sid:
        return None
    try:
        return db.session.get(Session, uuid.UUID(str(sid)))
    except (ValueError, TypeError):
        return None


def active_query(user_id):
    from app.models import Session
    return Session.query.filter(Session.user_id == user_id, Session.revoked_at.is_(None),
                                Session.expires_at > _now())


def _mark_revoked(session, reason, *, strict):
    """Redis markers for one session (raises SessionRevocationError when
    strict and the store is down)."""
    from app.services.token_revocation import SessionRevocationError
    client = _redis()
    remaining = int(((session.expires_at or _now()) - _now()).total_seconds())
    ttl = max(min(max(remaining, 3600) + 60, REVOKED_MARKER_MAX_SECONDS), 60)
    try:
        if client is None:
            raise RuntimeError('token store unavailable')
        client.setex(f'revoked_session:{session.id}', ttl, reason[:REASON_MAX])
        if session.refresh_jti:
            client.setex(f'revoked_token:{session.refresh_jti}', ttl, 'true')
    except Exception as exc:
        logger.error('session revocation marker failed for %s: %s', session.id, type(exc).__name__)
        if strict:
            raise SessionRevocationError('token store unavailable') from exc


def revoke(session, reason, *, strict=True):
    """Revoke one session (stages revoked_at; the caller commits)."""
    if session.revoked_at is None:
        session.revoked_at = _now()
        session.revoked_reason = (reason or 'revoked')[:REASON_MAX]
    _mark_revoked(session, reason or 'revoked', strict=strict)


def revoke_others(user, current_sid, reason='signed_out_elsewhere') -> int:
    """Revoke every active session of `user` except `current_sid`. Returns
    the count. No epoch bump; the caller commits."""
    count = 0
    for session in active_query(user.id).all():
        if current_sid and str(session.id) == str(current_sid):
            continue
        revoke(session, reason)
        count += 1
    return count


def touch(sid) -> None:
    """Record activity at most every TOUCH_INTERVAL_SECONDS per session (Redis
    gate, then one UPDATE on its own connection). Never raises."""
    if not sid:
        return
    try:
        sid = uuid.UUID(str(sid))
        client = _redis()
        if client is None or not client.set(f'session_seen:{sid}', '1', nx=True, ex=TOUCH_INTERVAL_SECONDS):
            return
        import sqlalchemy as sa
        from app import db
        from app.models import Session
        with db.engine.begin() as conn:
            conn.execute(sa.update(Session.__table__)
                         .where(Session.__table__.c.id == sid, Session.__table__.c.revoked_at.is_(None))
                         .values(last_seen_at=_now()))
    except Exception:
        logger.debug('session touch failed', exc_info=True)


def prune() -> int:
    """Delete sessions that ended more than PRUNE_AFTER_DAYS ago (job)."""
    from app import db
    from app.models import Session
    from sqlalchemy import or_
    cutoff = _now() - timedelta(days=PRUNE_AFTER_DAYS)
    deleted = Session.query.filter(or_(Session.revoked_at < cutoff, Session.expires_at < cutoff)) \
        .delete(synchronize_session=False)
    db.session.commit()
    return deleted


def _stamp_all_revoked(user, reason):
    """token_revocation hook: the epoch bump already killed every token;
    record it on the session rows (inside the caller's transaction)."""
    from app.models import Session
    Session.query.filter(Session.user_id == user.id, Session.revoked_at.is_(None)) \
        .update({Session.revoked_at: _now(), Session.revoked_reason: (reason or 'revoked')[:REASON_MAX]},
                synchronize_session=False)


def _register():
    from app.services.token_revocation import register_revocation_hook
    register_revocation_hook(_stamp_all_revoked)
    from app.cli import register_job
    register_job('prune-sessions', prune, every_seconds=24 * 3600, lock_ttl=600)


_register()


__all__ = ['start_session', 'issue_tokens', 'rotate', 'get_session', 'active_query', 'revoke',
           'revoke_others', 'touch', 'prune', 'TOUCH_INTERVAL_SECONDS', 'PRUNE_AFTER_DAYS']
