"""User administration: invites, account state actions, bulk actions, stats
and per-user activity (services/user_lifecycle.py, services/invite_service.py).

Every route is org-scoped (a user or invite of another org is 404), guarded
by rbac_guard (anti-escalation, self and last-admin rules) and audited.
Secrets (invite tokens, reset links, temporary passwords) appear only in the
response body, once; they are never part of an audit row.
"""
import sqlalchemy as sa
from flask import current_app, jsonify, request
from flask_jwt_extended import jwt_required

from app.services.rate_limit_settings import limited
from app import db
from app.api.v1 import api_bp
from app.middleware.audit import audit_log
from app.middleware.rbac import get_current_user, require_permission
from app.models import AuditLog, User, UserInvite
from app.services import audit_service, invite_service, user_lifecycle
from app.services.rbac_guard import GuardError, guard_error_response
from app.services.token_revocation import SessionRevocationError, revocation_failed_response
from app.services.user_lifecycle import LifecycleError
from app.utils.audit_diff import record_changes, snapshot
from app.utils.pagination import list_response, paginate_response, parse_list_args

STATE_FIELDS = ('is_active', 'deactivation_reason', 'must_change_password', 'mfa_enabled', 'locked_until')
INVITE_STATUSES = ('pending', 'accepted', 'revoked', 'expired', 'all')


def _target(user_id):
    current = get_current_user()
    return current, User.query.filter_by(id=user_id, organization_id=current.organization_id).first()


def _not_found(what='User'):
    return jsonify({'error': 'not_found', 'message': f'{what} not found'}), 404


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _run(fn):
    """Run a lifecycle action; map its errors to responses (with rollback)."""
    try:
        return fn(), None
    except GuardError as e:
        return None, guard_error_response(e)
    except LifecycleError as e:
        return None, e.response()
    except SessionRevocationError:
        db.session.rollback()
        return None, revocation_failed_response()


def _user_payload(user):
    return {'user': user.to_admin_dict()}


def _accept_url(path):
    base = (current_app.config.get('FRONTEND_URL') or '').rstrip('/')
    return f'{base}{path}' if base else None


# ── Stats ───────────────────────────────────────────────────────────

@api_bp.route('/users/stats', methods=['GET'])
@jwt_required()
@require_permission('users:read')
def user_admin_stats():
    """Org-wide user counts (not just the current page)."""
    return jsonify(user_lifecycle.user_stats(get_current_user().organization_id)), 200


# ── Invites ─────────────────────────────────────────────────────────

@api_bp.route('/users/invites', methods=['POST'])
@limited('invite_create')
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'create_invite', 'user_invite')
def user_admin_create_invite():
    """Create an invite; the one-time link is returned once."""
    current = get_current_user()
    try:
        invite, token, superseded = invite_service.create_invite(current, _body())
    except GuardError as e:
        return guard_error_response(e)
    except LifecycleError as e:
        return e.response()
    db.session.commit()
    record_changes({}, {'email': invite.email, 'role_ids': invite.role_ids, 'team_ids': invite.team_ids,
                        'expires_at': invite.expires_at.isoformat()},
                   superseded_invite_id=superseded)
    path = f'/auth/invite#token={token}'
    body = {'id': str(invite.id), 'invite': invite_service.serialize([invite])[0], 'token': token,
            'accept_path': path, 'superseded_invite_id': superseded}
    url = _accept_url(path)
    if url:
        body['accept_url'] = url
    return jsonify(body), 201


@api_bp.route('/users/invites', methods=['GET'])
@jwt_required()
@require_permission('users:manage')
def user_admin_list_invites():
    """Paged invites of the org: status=pending|accepted|revoked|expired|all."""
    current = get_current_user()
    status = request.args.get('status') or 'pending'
    if status not in INVITE_STATUSES:
        return jsonify({'error': 'invalid_filter',
                        'message': f"status must be one of {', '.join(INVITE_STATUSES)}"}), 400
    now = sa.func.now()
    q = UserInvite.query.filter(UserInvite.organization_id == current.organization_id)
    if status == 'pending':
        q = q.filter(UserInvite.accepted_at.is_(None), UserInvite.revoked_at.is_(None), UserInvite.expires_at > now)
    elif status == 'accepted':
        q = q.filter(UserInvite.accepted_at.isnot(None))
    elif status == 'revoked':
        q = q.filter(UserInvite.accepted_at.is_(None), UserInvite.revoked_at.isnot(None))
    elif status == 'expired':
        q = q.filter(UserInvite.accepted_at.is_(None), UserInvite.revoked_at.is_(None), UserInvite.expires_at <= now)
    body = list_response(
        q, sortable={'created_at': UserInvite.created_at, 'expires_at': UserInvite.expires_at,
                     'email': UserInvite.email},
        default_sort='-created_at', id_col=UserInvite.id, search_columns=(UserInvite.email, UserInvite.name),
        serialize=lambda inv: inv, max_per_page=100)
    body['items'] = invite_service.serialize(body['items'])
    return jsonify(body), 200


@api_bp.route('/users/invites/<uuid:user_invite_id>', methods=['DELETE'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'revoke_invite', 'user_invite')
def user_admin_revoke_invite(user_invite_id):
    current = get_current_user()
    invite = UserInvite.query.filter_by(id=user_invite_id, organization_id=current.organization_id).first()
    if invite is None:
        return _not_found('Invite')
    try:
        invite_service.revoke_invite(current, invite)
    except LifecycleError as e:
        return e.response()
    db.session.commit()
    record_changes({'status': 'pending'}, {'status': invite.status}, email=invite.email)
    return jsonify({'invite': invite_service.serialize([invite])[0]}), 200


# ── Account state ───────────────────────────────────────────────────

def _state_action(user_id, action):
    """Shared shape: load target, snapshot, run, commit, diff."""
    current, target = _target(user_id)
    if target is None:
        return _not_found()
    before = snapshot(target, STATE_FIELDS)
    _, error = _run(lambda: action(current, target))
    if error:
        return error
    db.session.commit()
    record_changes(before, snapshot(target, STATE_FIELDS), target_email=target.email)
    return jsonify(_user_payload(target)), 200


@api_bp.route('/users/<uuid:user_id>/disable', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'disable_user', 'user')
def user_admin_disable(user_id):
    """Disable with a reason (1..500); revokes every session and socket."""
    reason = _body().get('reason')
    resp = _state_action(user_id, lambda cur, tgt: user_lifecycle.disable_user(cur, tgt, reason))
    if resp[1] == 200 and isinstance(reason, str):
        record_changes({}, {}, reason=reason.strip())
    return resp


@api_bp.route('/users/<uuid:user_id>/enable', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'enable_user', 'user')
def user_admin_enable(user_id):
    return _state_action(user_id, user_lifecycle.enable_user)


@api_bp.route('/users/<uuid:user_id>/force-logout', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'force_logout_user', 'user')
def user_admin_force_logout(user_id):
    current, target = _target(user_id)
    if target is None:
        return _not_found()
    _, error = _run(lambda: user_lifecycle.force_logout(current, target))
    if error:
        return error
    db.session.commit()
    record_changes({}, {}, target_email=target.email)
    return jsonify({'message': 'All sessions of the user were revoked'}), 200


@api_bp.route('/users/<uuid:user_id>/unlock', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'unlock_user', 'user')
def user_admin_unlock(user_id):
    return _state_action(user_id, user_lifecycle.unlock_user)


@api_bp.route('/users/<uuid:user_id>/reset-password', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'admin_reset_password', 'user')
def user_admin_reset_password(user_id):
    """mode=link -> one-time reset link; mode=temp -> temporary password and a
    forced change at next login. The secret is in this response only."""
    current, target = _target(user_id)
    if target is None:
        return _not_found()
    body = _body()
    mode = body.get('mode')
    result, error = _run(lambda: user_lifecycle.admin_reset_password(
        current, target, mode, revoke_sessions=body.get('revoke_sessions', True)))
    if error:
        return error
    db.session.commit()
    record_changes({}, {'password': 'reset'}, mode=mode, target_email=target.email)
    if mode == 'link':
        url = _accept_url(result['accept_path'])
        if url:
            result['accept_url'] = url
    return jsonify(result), 200


@api_bp.route('/users/<uuid:user_id>/reset-mfa', methods=['POST'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'admin_reset_mfa', 'user')
def user_admin_reset_mfa(user_id):
    return _state_action(user_id, user_lifecycle.reset_mfa)


# ── Bulk ────────────────────────────────────────────────────────────

@api_bp.route('/users/bulk', methods=['POST'])
@limited('users_bulk')
@jwt_required()
@require_permission('users:manage')
def user_admin_bulk():
    """One action over up to 100 users; per-item results and audit rows."""
    current = get_current_user()
    try:
        parsed = user_lifecycle.parse_bulk(current, request.get_json(silent=True))
    except LifecycleError as e:
        return e.response()
    return jsonify(user_lifecycle.apply_bulk(current, parsed)), 200


# ── Activity ────────────────────────────────────────────────────────

@api_bp.route('/users/<uuid:user_id>/activity', methods=['GET'])
@jwt_required()
@require_permission('audit_logs:read')
def user_admin_activity(user_id):
    """Audit rows by the user (scope=actor), about the user (target) or both."""
    current, target = _target(user_id)
    if target is None:
        return _not_found()
    scope = request.args.get('scope') or 'all'
    if scope not in ('actor', 'target', 'all'):
        return jsonify({'error': 'invalid_filter', 'message': 'scope must be actor, target or all'}), 400
    by_actor = AuditLog.user_id == target.id
    about = sa.and_(AuditLog.resource_type.in_(('user', 'user_invite')), AuditLog.resource_id == target.id)
    sortable = {'created_at': AuditLog.created_at}
    la = parse_list_args(sortable=sortable, default_sort='-created_at', default_per_page=20, max_per_page=100)
    audit_service.check_page_depth(la.page, la.per_page)
    # Org-pinned audit query; the audit filters (event_type, dates, action, q, ...) apply on top.
    q = audit_service.build_audit_query(current.organization_id, request.args)
    q = q.filter(by_actor if scope == 'actor' else about if scope == 'target' else sa.or_(by_actor, about))
    body = paginate_response(q, la, serialize=lambda r: r.to_dict(), sortable=sortable, id_col=AuditLog.id,
                             extra={'scope': scope})
    return jsonify(body), 200


# ── Guided tours ────────────────────────────────────────────────────────

def _tours_body():
    body = _body()
    enabled, reset = body.get('enabled'), body.get('reset', False)
    if (enabled is not None and not isinstance(enabled, bool)) or not isinstance(reset, bool) \
            or (enabled is None and not reset):
        return None
    return enabled, reset


def _apply_tours(user, enabled, reset):
    prefs = dict(user.preferences or {})
    if enabled is not None:
        prefs['tours_enabled'] = enabled
    if reset:
        prefs['tours_seen'] = []
    user.preferences = prefs  # reassign so the JSONB change is detected


@api_bp.route('/users/<uuid:user_id>/tours', methods=['PUT'])
@jwt_required()
@require_permission('users:update')
@audit_log('admin_action', 'tours_update', 'user')
def update_user_tours(user_id):
    """Switch guided tours on/off for one user (``enabled``), and/or replay
    them from the start (``reset: true`` clears the tours they have seen)."""
    _current, user = _target(user_id)
    if user is None:
        return _not_found()
    parsed = _tours_body()
    if parsed is None:
        return jsonify({'error': 'validation_error',
                        'message': 'Send enabled (true/false) and/or reset: true'}), 400
    enabled, reset = parsed
    before = {'tours_enabled': user.tours_enabled}
    _apply_tours(user, enabled, reset)
    record_changes(before, {'tours_enabled': user.tours_enabled}, reset=reset, target_email=user.email)
    db.session.commit()
    return jsonify(_user_payload(user)), 200


@api_bp.route('/users/tours', methods=['PUT'])
@jwt_required()
@require_permission('users:manage')
@audit_log('admin_action', 'tours_update_all', 'user')
def update_all_user_tours():
    """The same for every user of the organization."""
    current = get_current_user()
    parsed = _tours_body()
    if parsed is None:
        return jsonify({'error': 'validation_error',
                        'message': 'Send enabled (true/false) and/or reset: true'}), 400
    enabled, reset = parsed
    users = User.query.filter_by(organization_id=current.organization_id).all()
    for user in users:
        _apply_tours(user, enabled, reset)
    record_changes({}, {'tours_enabled': enabled}, reset=reset, users=len(users))
    db.session.commit()
    return jsonify({'updated': len(users), 'tours_enabled': enabled, 'reset': reset}), 200
