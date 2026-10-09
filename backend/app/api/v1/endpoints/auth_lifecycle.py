"""Public account-lifecycle routes: invite lookup/accept and password-reset
completion. Tokens travel in POST bodies (never URLs or logs); every failure
of a kind returns one generic error so nothing can be enumerated."""
from flask import jsonify, request

from app.services.rate_limit_settings import limited
from app import db
from app.api.v1 import api_bp
from app.api.v1.endpoints.auth import _auth_cookies, issue_tokens
from app.middleware.audit import log_auth_event
from app.models import Organization
from app.services import invite_service, user_lifecycle
from app.services.token_revocation import SessionRevocationError, revocation_failed_response
from app.services.user_lifecycle import LifecycleError


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _invite_invalid():
    return jsonify({'error': 'invite_invalid', 'message': invite_service.INVALID_MESSAGE}), 400


@api_bp.route('/auth/invites/lookup', methods=['POST'])
@limited('invites_lookup')
def lookup_invite_public():
    """{token} -> {email, name, organization_name, expires_at}."""
    invite = invite_service.lookup_invite(_body().get('token'))
    if invite is None:
        return _invite_invalid()
    org = db.session.get(Organization, invite.organization_id)
    return jsonify({
        'email': invite.email,
        'name': invite.name,
        'organization_name': org.name if org else None,
        'expires_at': invite.expires_at.isoformat(),
    }), 200


@api_bp.route('/auth/invites/accept', methods=['POST'])
@limited('invites_accept')
def accept_invite_public():
    """{token, name, password} -> 201 {access_token, refresh_token, user} + cookies."""
    data = _body()
    try:
        user = invite_service.accept_invite(data.get('token'), data.get('name'), data.get('password'))
    except LifecycleError as e:
        return e.response()
    except invite_service.InviteInvalid:
        db.session.rollback()
        log_auth_event('invite_accept', success=False, details={'reason': 'invite_invalid'})
        return _invite_invalid()
    db.session.commit()

    access_token, refresh_token = issue_tokens(user)
    log_auth_event('invite_accept', user=user, success=True)
    resp = jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user.to_dict(include_permissions=True),
    })
    return _auth_cookies(resp, access_token, refresh_token), 201


@api_bp.route('/auth/password-reset/complete', methods=['POST'])
@limited('password_reset_complete')
def complete_password_reset_public():
    """{token, new_password}: sets the password, clears must-change and the
    lockout, revokes every session. The user then signs in normally."""
    data = _body()
    try:
        user = user_lifecycle.complete_password_reset(data.get('token'), data.get('new_password'))
    except LifecycleError as e:
        if e.code == 'reset_invalid':
            log_auth_event('password_reset_complete', success=False, details={'reason': 'reset_invalid'})
        return e.response()
    except SessionRevocationError:
        db.session.rollback()
        return revocation_failed_response()
    db.session.commit()
    log_auth_event('password_reset_complete', user=user, success=True)
    return jsonify({'message': 'Password has been reset. Sign in with your new password.'}), 200
