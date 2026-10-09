"""Sign-in session inventory (services/session_service.py).

Self, or a holder of ``users:manage`` in the same organization (acting on
someone else also requires outranking them). Another org's user is a 404.
Interactive sessions only: API keys can neither read session IPs nor sign
anyone out. Revoking a session kills its access and refresh tokens at once;
the user's other sessions keep working (no token-epoch bump). Session data
is never broadcast.
"""
from flask import jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

from app import db
from app.api.v1 import api_bp
from app.middleware.audit import audit_log
from app.middleware.rbac import get_current_user, require_interactive_session
from app.models import Session, User
from app.services import session_service
from app.services.rbac_guard import GuardError, assert_can_manage_user, guard_error_response
from app.services.token_revocation import SessionRevocationError, revocation_failed_response
from app.utils.audit_diff import record_changes
from app.utils.pagination import list_response

SESSION_SORTABLE = {
    'created_at': Session.created_at,
    'last_seen_at': Session.last_seen_at,
}


def _target(user_id, *, mutate):
    """(caller, target, error_response). Self always; others need
    users:manage in the same org (and outranking them to mutate)."""
    caller = get_current_user()
    if not caller:
        return None, None, (jsonify({'error': 'unauthorized', 'message': 'Authentication required'}), 401)
    if caller.id == user_id:
        return caller, caller, None
    if not caller.has_permission('users:manage'):
        return caller, None, (jsonify({'error': 'forbidden', 'message': 'Permission denied'}), 403)
    target = User.query.filter_by(id=user_id, organization_id=caller.organization_id).first()
    if target is None:
        return caller, None, (jsonify({'error': 'not_found', 'message': 'User not found'}), 404)
    if mutate:
        try:
            assert_can_manage_user(caller, target, 'force_logout')
        except GuardError as e:
            return caller, None, guard_error_response(e)
    return caller, target, None


def _current_sid():
    return (get_jwt() or {}).get('sid')


def _after_revoke(target):
    from app.services import realtime
    realtime.disconnect_user_sockets(str(target.id))


@api_bp.route('/users/<uuid:user_id>/sessions', methods=['GET'])
@jwt_required()
@require_interactive_session
def list_user_sessions(user_id):
    """Active (not revoked, not expired) sessions; ``current`` marks the
    caller's own session. Pagination contract (sort created_at /
    last_seen_at, default -last_seen_at)."""
    _, target, error = _target(user_id, mutate=False)
    if error:
        return error
    sid = _current_sid()
    body = list_response(session_service.active_query(target.id), sortable=SESSION_SORTABLE,
                         default_sort='-last_seen_at', id_col=Session.id,
                         serialize=lambda s: s.to_dict(current_sid=sid))
    return jsonify(body), 200


@api_bp.route('/users/<uuid:user_id>/sessions/<uuid:session_id>', methods=['DELETE'])
@jwt_required()
@require_interactive_session
@audit_log('admin_action', 'session_revoke', 'session')
def revoke_user_session(user_id, session_id):
    """Revoke one session of the user."""
    caller, target, error = _target(user_id, mutate=True)
    if error:
        return error
    session = Session.query.filter_by(id=session_id, user_id=target.id).first()
    if session is None or session.revoked_at is not None:
        return jsonify({'error': 'not_found', 'message': 'Session not found'}), 404
    reason = 'revoked_by_user' if caller.id == target.id else 'revoked_by_admin'
    try:
        session_service.revoke(session, reason)
    except SessionRevocationError:
        db.session.rollback()
        return revocation_failed_response()
    db.session.commit()
    _after_revoke(target)
    record_changes({}, {}, target_user_id=str(target.id), target_email=target.email,
                   session_id=str(session.id), current=str(session.id) == str(_current_sid() or ''))
    return jsonify({'id': str(session.id), 'revoked': True}), 200


@api_bp.route('/users/<uuid:user_id>/sessions', methods=['DELETE'])
@jwt_required()
@require_interactive_session
@audit_log('admin_action', 'session_revoke_all', 'user')
def revoke_user_sessions(user_id):
    """Revoke every active session of the user. ``?except_current=true``
    keeps the caller's own session ("sign out other devices")."""
    caller, target, error = _target(user_id, mutate=True)
    if error:
        return error
    keep = request.args.get('except_current', 'false').lower() in ('1', 'true', 'yes')
    current_sid = _current_sid() if keep else None
    reason = 'revoked_by_user' if caller.id == target.id else 'revoked_by_admin'
    try:
        count = session_service.revoke_others(target, current_sid, reason=reason)
    except SessionRevocationError:
        db.session.rollback()
        return revocation_failed_response()
    db.session.commit()
    if count:
        _after_revoke(target)
    record_changes({}, {}, target_email=target.email, revoked=count, except_current=bool(current_sid))
    return jsonify({'id': str(target.id), 'revoked': count}), 200


__all__ = ['list_user_sessions', 'revoke_user_session', 'revoke_user_sessions']
