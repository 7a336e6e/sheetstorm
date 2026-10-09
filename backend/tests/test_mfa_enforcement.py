"""MFA enforcement by the org security policy (W3-SEC): grace period, the
DB-derived ``mfa_enrollment_required`` restriction, enrollment lifting it,
the privileged scope, the disable guard, API keys and the WebSocket."""
from datetime import datetime, timedelta, timezone

import pyotp

from conftest import TEST_PASSWORD
from rbac_helpers import make_role, make_user, new_org  # noqa: F401


def _login(app, user):
    resp = app.test_client().post('/api/v1/auth/login', json={'email': user.email, 'password': TEST_PASSWORD})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _bearer(token):
    return {'Authorization': f'Bearer {token}'}


def _age(db, user, days):
    user.created_at = datetime.now(timezone.utc) - timedelta(days=days)
    db.session.commit()


def test_within_grace_full_access_and_flag(app, db, new_org, make_user, set_policy):
    org = new_org()
    set_policy(org, {'mfa': {'required_for': 'all', 'grace_days': 7}})
    user = make_user(org, roles=['Analyst'])
    body = _login(app, user)
    sec = body['user']['security']
    assert sec['mfa_required'] is True and sec['mfa_enrollment_required'] is False
    assert sec['mfa_grace_ends_at']
    client = app.test_client()
    assert client.get('/api/v1/incidents', headers=_bearer(body['access_token'])).status_code == 200
    me = client.get('/api/v1/auth/me', headers=_bearer(body['access_token'])).get_json()
    assert me['security']['mfa_grace_ends_at'] == sec['mfa_grace_ends_at']


def test_after_grace_restricted_until_enrolled(app, db, new_org, make_user, set_policy):
    org = new_org()
    set_policy(org, {'mfa': {'required_for': 'all', 'grace_days': 0}})
    user = make_user(org, roles=['Analyst'])
    body = _login(app, user)
    assert body['user']['security']['mfa_enrollment_required'] is True
    client = app.test_client()
    h = _bearer(body['access_token'])

    blocked = client.get('/api/v1/incidents', headers=h)
    assert blocked.status_code == 403 and blocked.get_json()['error'] == 'mfa_enrollment_required'
    assert client.get('/api/v1/auth/me', headers=h).status_code == 200
    assert client.get('/api/v1/auth/password-policy', headers=h).status_code == 200

    setup = client.post('/api/v1/auth/mfa/setup', headers=h)
    assert setup.status_code == 200
    code = pyotp.TOTP(setup.get_json()['secret']).now()
    assert client.post('/api/v1/auth/mfa/verify', headers=h, json={'code': code}).status_code == 200
    # Lifted at once on the same token (state is read from the DB per request).
    assert client.get('/api/v1/incidents', headers=h).status_code == 200


def test_grace_counts_from_later_of_policy_and_account(app, db, new_org, make_user, set_policy):
    from app.services import security_policy
    org = new_org()
    set_policy(org, {'mfa': {'required_for': 'all', 'grace_days': 7}})
    old_user = make_user(org, roles=['Analyst'])
    _age(db, old_user, 30)
    status = security_policy.mfa_status(old_user)
    # Enforcement started now, so even an old account gets the full grace.
    assert status['enforce_now'] is False
    assert status['grace_ends_at'] > datetime.now(timezone.utc) + timedelta(days=6)


def test_privileged_scope(app, db, new_org, make_user, set_policy):
    org = new_org()
    set_policy(org, {'mfa': {'required_for': 'privileged', 'grace_days': 0}})
    admin = make_user(org, roles=['Administrator'])
    viewer = make_user(org, roles=['Viewer'])
    client = app.test_client()
    admin_body = _login(app, admin)
    assert admin_body['user']['security']['mfa_enrollment_required'] is True
    assert client.get('/api/v1/incidents', headers=_bearer(admin_body['access_token'])).status_code == 403
    viewer_body = _login(app, viewer)
    assert viewer_body['user']['security']['mfa_required'] is False
    assert client.get('/api/v1/incidents', headers=_bearer(viewer_body['access_token'])).status_code == 200


def test_mfa_disable_blocked_by_policy(app, db, auth, new_org, make_user, set_policy):
    org = new_org()
    user = make_user(org, roles=['Analyst'])
    user.mfa_enabled, user.mfa_secret = True, pyotp.random_base32()
    db.session.commit()
    set_policy(org, {'mfa': {'required_for': 'all'}})
    resp = auth(user).post('/api/v1/auth/mfa/disable', json={'password': TEST_PASSWORD})
    assert resp.status_code == 403 and resp.get_json()['error'] == 'mfa_required_by_policy'
    set_policy(org, {'mfa': {'required_for': 'none'}})
    assert auth(user).post('/api/v1/auth/mfa/disable', json={'password': TEST_PASSWORD}).status_code == 200


def test_api_keys_exempt(app, db, new_org, make_user, set_policy, make_api_key, key_client):
    org = new_org()
    owner = make_user(org, roles=['Analyst'])
    _, full = make_api_key(owner, ['incidents:read'])
    set_policy(org, {'mfa': {'required_for': 'all', 'grace_days': 0}})
    assert key_client(full).get('/api/v1/incidents').status_code == 200


def test_websocket_treats_restricted_as_anonymous(app, db, auth, new_org, make_user, set_policy):
    from app import socketio
    org = new_org()
    user = make_user(org, roles=['Analyst'])
    token = auth(user).access_token
    set_policy(org, {'mfa': {'required_for': 'all', 'grace_days': 0}})
    c = socketio.test_client(app, auth={'token': token})
    events = [e for e in c.get_received() if e['name'] == 'connected']
    assert events and events[-1]['args'][0].get('anonymous') is True
    c.disconnect()


def test_service_accounts_never_restricted(app, db, new_org, make_user, set_policy):
    from app.services import security_policy
    org = new_org()
    set_policy(org, {'mfa': {'required_for': 'all', 'grace_days': 0}})
    sa = make_user(org, roles=['Analyst'])
    sa.is_service_account = True
    db.session.commit()
    assert security_policy.mfa_enrollment_required(sa) is False


def test_stats_count_adoption(app, db, auth, new_org, make_user, set_policy):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    admin.mfa_enabled = True
    db.session.commit()
    make_user(org, roles=['Viewer'])
    set_policy(org, {'mfa': {'required_for': 'all', 'grace_days': 0}})
    stats = auth(admin).get('/api/v1/organization/security-policy').get_json()['stats']
    assert stats == {'users_total': 2, 'users_mfa': 1, 'privileged_total': 1, 'privileged_mfa': 1,
                     'users_without_mfa_past_grace': 1}
