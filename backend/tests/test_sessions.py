"""Sign-in session inventory (W3-SEC): rows on sign-in, sid claim, refresh
rotation, listing/revocation permissions, per-session revocation, "sign out
other devices", password change, token lifetimes, logout and touch."""
import uuid

from conftest import TEST_PASSWORD
from rbac_helpers import last_audit, make_role, make_user, new_org  # noqa: F401

UA = 'Mozilla/5.0 (SessionTest)'


def _login(app, user, client=None):
    client = client or app.test_client()
    resp = client.post('/api/v1/auth/login', json={'email': user.email, 'password': TEST_PASSWORD},
                       headers={'User-Agent': UA})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _bearer(token):
    return {'Authorization': f'Bearer {token}'}


def _claims(app, token):
    from flask_jwt_extended import decode_token
    with app.app_context():
        return decode_token(token)


def _refresh(app, token):
    return app.test_client().post('/api/v1/auth/refresh', headers=_bearer(token))


def _session(db, sid):
    from app.models import Session
    db.session.expire_all()
    return db.session.get(Session, uuid.UUID(sid))


def test_login_creates_session_with_sid(app, db, new_org, make_user):
    user = make_user(new_org(), roles=['Analyst'])
    body = _login(app, user)
    access, refresh = _claims(app, body['access_token']), _claims(app, body['refresh_token'])
    assert access['sid'] == refresh['sid']
    row = _session(db, access['sid'])
    assert row.user_id == user.id and row.organization_id == user.organization_id
    assert row.auth_method == 'password' and row.user_agent == UA
    assert row.refresh_jti == refresh['jti'] and row.revoked_at is None and row.last_seen_at


def test_refresh_keeps_sid_and_rotates_jti(app, db, new_org, make_user):
    user = make_user(new_org(), roles=['Analyst'])
    body = _login(app, user)
    sid = _claims(app, body['access_token'])['sid']
    resp = _refresh(app, body['refresh_token'])
    assert resp.status_code == 200
    new_refresh = _claims(app, resp.get_json()['refresh_token'])
    assert new_refresh['sid'] == sid
    assert _session(db, sid).refresh_jti == new_refresh['jti'] != _claims(app, body['refresh_token'])['jti']


def test_list_own_sessions_marks_current(app, db, new_org, make_user):
    user = make_user(new_org(), roles=['Analyst'])
    first, second = _login(app, user), _login(app, user)
    resp = app.test_client().get(f'/api/v1/users/{user.id}/sessions', headers=_bearer(second['access_token']))
    assert resp.status_code == 200
    items = resp.get_json()['items']
    current = [s for s in items if s['current']]
    assert len(items) >= 2 and len(current) == 1
    assert current[0]['id'] == _claims(app, second['access_token'])['sid']
    assert {'ip_address', 'user_agent', 'created_at', 'last_seen_at', 'auth_method'} <= set(items[0])
    assert first  # both sessions listed


def test_listing_permissions(app, db, auth, new_org, make_user):
    org, other_org = new_org(), new_org()
    user = make_user(org, roles=['Analyst'])
    peer = make_user(org, roles=['Analyst'])
    admin = make_user(org, roles=['Administrator'])
    foreign_admin = make_user(other_org, roles=['Administrator'])
    _login(app, user)
    assert auth(peer).get(f'/api/v1/users/{user.id}/sessions').status_code == 403
    resp = auth(admin).get(f'/api/v1/users/{user.id}/sessions')
    assert resp.status_code == 200 and resp.get_json()['total'] >= 1
    assert auth(foreign_admin).get(f'/api/v1/users/{user.id}/sessions').status_code == 404
    assert auth(foreign_admin).delete(f'/api/v1/users/{user.id}/sessions').status_code == 404


def test_revoke_one_session_kills_its_tokens_only(app, db, auth, new_org, make_user):
    org = new_org()
    user = make_user(org, roles=['Analyst'])
    admin = make_user(org, roles=['Administrator'])
    victim, survivor = _login(app, user), _login(app, user)
    sid = _claims(app, victim['access_token'])['sid']
    resp = auth(admin).delete(f'/api/v1/users/{user.id}/sessions/{sid}')
    assert resp.status_code == 200
    client = app.test_client()
    assert client.get('/api/v1/auth/me', headers=_bearer(victim['access_token'])).status_code == 401
    assert _refresh(app, victim['refresh_token']).status_code == 401
    assert client.get('/api/v1/auth/me', headers=_bearer(survivor['access_token'])).status_code == 200
    assert _refresh(app, survivor['refresh_token']).status_code == 200
    row = _session(db, sid)
    assert row.revoked_at is not None and row.revoked_reason == 'revoked_by_admin'
    audit = last_audit(db, 'session_revoke', 'session')
    assert audit is not None and audit.details['session_id'] == sid
    # Already revoked -> 404; another user's session id -> 404.
    assert auth(admin).delete(f'/api/v1/users/{user.id}/sessions/{sid}').status_code == 404
    other_sid = _claims(app, _login(app, admin)['access_token'])['sid']
    assert auth(admin).delete(f'/api/v1/users/{user.id}/sessions/{other_sid}').status_code == 404


def test_cannot_revoke_sessions_of_higher_ranked_user(app, db, auth, new_org, make_user):
    org = new_org()
    manager = make_user(org, perms=['users:manage', 'users:read'])
    admin = make_user(org, roles=['Administrator'])
    sid = _claims(app, _login(app, admin)['access_token'])['sid']
    resp = auth(manager).delete(f'/api/v1/users/{admin.id}/sessions/{sid}')
    assert resp.status_code == 403


def test_sign_out_other_devices_keeps_current(app, db, new_org, make_user):
    user = make_user(new_org(), roles=['Analyst'])
    other, current = _login(app, user), _login(app, user)
    client = app.test_client()
    resp = client.delete(f'/api/v1/users/{user.id}/sessions?except_current=true',
                         headers=_bearer(current['access_token']))
    assert resp.status_code == 200 and resp.get_json()['revoked'] >= 1
    assert client.get('/api/v1/auth/me', headers=_bearer(current['access_token'])).status_code == 200
    assert client.get('/api/v1/auth/me', headers=_bearer(other['access_token'])).status_code == 401
    items = client.get(f'/api/v1/users/{user.id}/sessions', headers=_bearer(current['access_token'])).get_json()['items']
    assert [s['current'] for s in items] == [True]


def test_password_change_revokes_every_session(app, db, new_org, make_user):
    from app.models import Session
    user = make_user(new_org(), roles=['Analyst'])
    old, current = _login(app, user), _login(app, user)
    resp = app.test_client().post('/api/v1/auth/change-password', headers=_bearer(current['access_token']),
                                  json={'current_password': TEST_PASSWORD, 'new_password': 'Brand-New-Passw0rd!'})
    assert resp.status_code == 200
    for body in (old, current):
        assert _session(db, _claims(app, body['access_token'])['sid']).revoked_at is not None
    new_sid = _claims(app, resp.get_json()['access_token'])['sid']
    assert _session(db, new_sid).revoked_at is None
    assert Session.query.filter(Session.user_id == user.id, Session.revoked_at.is_(None)).count() == 1


def test_force_logout_stamps_sessions(app, db, auth, new_org, make_user):
    org = new_org()
    user = make_user(org, roles=['Analyst'])
    admin = make_user(org, roles=['Administrator'])
    sid = _claims(app, _login(app, user)['access_token'])['sid']
    assert auth(admin).post(f'/api/v1/users/{user.id}/force-logout').status_code == 200
    row = _session(db, sid)
    assert row.revoked_at is not None and row.revoked_reason == 'force_logout'


def test_token_lifetimes_follow_policy(app, db, new_org, make_user, set_policy):
    org = new_org()
    set_policy(org, {'session': {'access_token_minutes': 10, 'refresh_token_days': 2}})
    user = make_user(org, roles=['Analyst'])
    body = _login(app, user)
    access, refresh = _claims(app, body['access_token']), _claims(app, body['refresh_token'])
    assert access['exp'] - access['iat'] == 600
    assert refresh['exp'] - refresh['iat'] == 2 * 86400


def test_logout_revokes_session(app, db, new_org, make_user):
    user = make_user(new_org(), roles=['Analyst'])
    body = _login(app, user)
    sid = _claims(app, body['access_token'])['sid']
    client = app.test_client()
    assert client.post('/api/v1/auth/logout', headers=_bearer(body['access_token']),
                       json={'refresh_token': body['refresh_token']}).status_code == 200
    assert _session(db, sid).revoked_reason == 'logout'
    assert _refresh(app, body['refresh_token']).status_code == 401


def test_legacy_token_without_sid_gets_a_session_on_refresh(app, db, new_org, make_user):
    from flask_jwt_extended import create_refresh_token
    user = make_user(new_org(), roles=['Analyst'])
    with app.app_context():
        legacy = create_refresh_token(identity=str(user.id), additional_claims={'token_epoch': 0})
    resp = _refresh(app, legacy)
    assert resp.status_code == 200
    sid = _claims(app, resp.get_json()['access_token'])['sid']
    assert _session(db, sid).auth_method == 'refresh'


def test_touch_updates_last_seen_once_per_interval(app, db, redis_client, new_org, make_user):
    from datetime import datetime, timedelta, timezone
    from app.services import session_service
    user = make_user(new_org(), roles=['Analyst'])
    sid = _claims(app, _login(app, user)['access_token'])['sid']
    row = _session(db, sid)
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    row.last_seen_at = old
    db.session.commit()
    redis_client.delete(f'session_seen:{sid}')
    session_service.touch(sid)
    assert _session(db, sid).last_seen_at > old
    stamped = _session(db, sid).last_seen_at
    session_service.touch(sid)  # inside the interval: no write
    assert _session(db, sid).last_seen_at == stamped


def test_prune_removes_long_dead_sessions(app, db, new_org, make_user):
    from datetime import datetime, timedelta, timezone
    from app.models import Session
    from app.services import session_service
    user = make_user(new_org(), roles=['Analyst'])
    old = datetime.now(timezone.utc) - timedelta(days=40)
    dead = Session(user_id=user.id, organization_id=user.organization_id, expires_at=old, created_at=old)
    db.session.add(dead)
    db.session.commit()
    dead_id = dead.id
    session_service.prune()
    db.session.expire_all()
    assert db.session.get(Session, dead_id) is None


def test_api_keys_cannot_use_session_endpoints(app, db, new_org, make_user, make_api_key, key_client):
    user = make_user(new_org(), roles=['Analyst'])
    _, full = make_api_key(user, ['incidents:read'])
    resp = key_client(full).get(f'/api/v1/users/{user.id}/sessions')
    assert resp.status_code == 403 and resp.get_json()['error'] == 'interactive_session_required'
