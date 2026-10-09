"""Items 11, 17 + refresh contract: refresh rotation with a grace window,
cookie paths, is_active enforcement on every login path, admin password
reset policy and session revocation."""
import time
import uuid

import pytest

from conftest import TEST_PASSWORD


@pytest.fixture
def fresh_user(app, db, org_a):
    """A throwaway Analyst in org A (safe to disable / reset)."""
    from app.models import User, Role, UserRole

    def make(**kw):
        u = User(email=f'u-{uuid.uuid4().hex[:10]}@a.test', name='tmp', organization_id=org_a.id,
                 auth_provider=kw.pop('auth_provider', 'local'), is_active=kw.pop('is_active', True), **kw)
        u.set_password(TEST_PASSWORD)
        db.session.add(u)
        db.session.flush()
        db.session.add(UserRole(user_id=u.id, role_id=Role.query.filter_by(name='Analyst').one().id,
                                organization_id=org_a.id))
        db.session.commit()
        return u
    return make


def _refresh(client, token):
    return client.post('/api/v1/auth/refresh', headers={'Authorization': f'Bearer {token}'})


def test_refresh_rotates_and_returns_new_refresh_token(app, users, auth):
    ac = auth(users['Analyst'])
    resp = _refresh(ac.client, ac.refresh_token)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['access_token'] and body['refresh_token'] and body['refresh_token'] != ac.refresh_token
    # The new refresh token works.
    assert _refresh(ac.client, body['refresh_token']).status_code == 200


def test_refresh_grace_window_allows_exactly_one_reuse(app, users, auth):
    ac = auth(users['Analyst'])
    assert _refresh(ac.client, ac.refresh_token).status_code == 200
    # Concurrent refresh with the just-rotated token: accepted once ...
    assert _refresh(ac.client, ac.refresh_token).status_code == 200
    # ... and never again.
    assert _refresh(ac.client, ac.refresh_token).status_code == 401


def test_refresh_grace_window_expires(app, users, auth, redis_client):
    from flask_jwt_extended import decode_token
    ac = auth(users['Analyst'])
    assert _refresh(ac.client, ac.refresh_token).status_code == 200
    with app.app_context():
        jti = decode_token(ac.refresh_token)['jti']
    redis_client.delete(f'refresh_grace:{jti}')  # simulate the 30 s TTL elapsing
    assert _refresh(ac.client, ac.refresh_token).status_code == 401


def test_access_token_cannot_refresh(app, users, auth):
    ac = auth(users['Analyst'])
    assert _refresh(ac.client, ac.access_token).status_code in (401, 422)


def test_refresh_via_cookie_sets_scoped_cookies(app, users):
    from app.api.v1.endpoints.auth import issue_tokens
    from flask_jwt_extended import get_csrf_token
    client = app.test_client()
    with app.app_context():
        _, refresh = issue_tokens(users['Analyst'])
        csrf = get_csrf_token(refresh)
    client.set_cookie('refresh_token_cookie', refresh, path='/api/v1/auth')
    client.set_cookie('csrf_refresh_token', csrf)
    # Missing CSRF header -> rejected
    assert client.post('/api/v1/auth/refresh').status_code == 401
    resp = client.post('/api/v1/auth/refresh', headers={'X-CSRF-TOKEN': csrf})
    assert resp.status_code == 200
    cookies = resp.headers.getlist('Set-Cookie')
    refresh_cookie = next(c for c in cookies if c.startswith('refresh_token_cookie='))
    csrf_refresh = next(c for c in cookies if c.startswith('csrf_refresh_token='))
    assert 'Path=/api/v1/auth' in refresh_cookie and 'HttpOnly' in refresh_cookie
    assert 'Path=/' in csrf_refresh and 'HttpOnly' not in csrf_refresh
    assert resp.get_json()['refresh_token']


def test_cookie_auth_requires_csrf_on_mutations(app, users, auth, make_incident):
    ac = auth(users['Administrator'], mode='cookie')
    inc = make_incident()
    assert ac.get(f'/api/v1/incidents/{inc.id}').status_code == 200
    ok = ac.post(f'/api/v1/incidents/{inc.id}/tasks', json={'title': 't'})
    assert ok.status_code == 201
    bad = ac.client.post(f'/api/v1/incidents/{inc.id}/tasks', json={'title': 't'})
    assert bad.status_code == 401


def test_me_rejects_inactive_user(app, db, auth, fresh_user):
    u = fresh_user()
    ac = auth(u)
    assert ac.get('/api/v1/auth/me').status_code == 200
    u.is_active = False
    db.session.commit()
    assert ac.get('/api/v1/auth/me').status_code == 401


def test_password_login_rejects_inactive(app, fresh_user):
    u = fresh_user(is_active=False)
    resp = app.test_client().post('/api/v1/auth/login', json={'email': u.email, 'password': TEST_PASSWORD})
    assert resp.status_code == 401


def test_admin_reset_enforces_policy_and_revokes_sessions(app, users, auth, fresh_user):
    u = fresh_user()
    victim = auth(u)
    admin = auth(users['Administrator'])
    weak = admin.put(f'/api/v1/users/{u.id}', json={'password': 'short'})
    assert weak.status_code == 400
    assert victim.get('/api/v1/auth/me').status_code == 200
    ok = admin.put(f'/api/v1/users/{u.id}', json={'password': 'An0ther-Str0ng-Pass!'})
    assert ok.status_code == 200
    assert victim.get('/api/v1/auth/me').status_code == 401  # token epoch bumped


def test_disabling_user_revokes_tokens(app, users, auth, fresh_user):
    u = fresh_user()
    victim = auth(u)
    admin = auth(users['Administrator'])
    assert admin.put(f'/api/v1/users/{u.id}', json={'is_active': False}).status_code == 200
    # Re-enable: old tokens must stay dead (epoch), not just the is_active check.
    assert admin.put(f'/api/v1/users/{u.id}', json={'is_active': True}).status_code == 200
    assert victim.get('/api/v1/auth/me').status_code == 401


def test_mfa_complete_rejects_inactive(app, db, fresh_user):
    import pyotp
    from flask_jwt_extended import create_access_token
    u = fresh_user()
    u.mfa_enabled, u.mfa_secret = True, pyotp.random_base32()
    u.is_active = False
    db.session.commit()
    with app.app_context():
        pre = create_access_token(identity=str(u.id), additional_claims={'pre_auth': True})
    resp = app.test_client().post('/api/v1/auth/mfa/complete', json={
        'pre_auth_token': pre, 'mfa_code': pyotp.TOTP(u.mfa_secret).now()})
    assert resp.status_code == 401
    assert 'access_token' not in (resp.get_json() or {})


class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


def test_supabase_login_rejects_inactive(app, monkeypatch, fresh_user):
    import requests
    u = fresh_user(is_active=False, auth_provider='supabase')
    monkeypatch.setitem(app.config, 'SUPABASE_URL', 'https://sb.example')
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp(200, {'email': u.email, 'id': 'sb1'}))
    resp = app.test_client().post('/api/v1/auth/supabase', json={'access_token': 'x'})
    assert resp.status_code == 401
    assert 'access_token' not in resp.get_json()


def test_github_login_rejects_inactive_and_requires_state(app, monkeypatch, redis_client, fresh_user):
    import requests
    u = fresh_user(is_active=False)
    monkeypatch.setitem(app.config, 'GITHUB_CLIENT_ID', 'cid')
    monkeypatch.setitem(app.config, 'GITHUB_CLIENT_SECRET', 'csecret')
    monkeypatch.setattr(requests, 'post', lambda *a, **k: _Resp(200, {'access_token': 'gh'}))

    def fake_get(url, *a, **k):
        if url.endswith('/user/emails'):
            return _Resp(200, [{'email': u.email, 'primary': True, 'verified': True}])
        return _Resp(200, {'id': 1, 'login': 'x'})
    monkeypatch.setattr(requests, 'get', fake_get)
    client = app.test_client()
    # No / unknown state -> rejected before any token exchange
    assert client.post('/api/v1/auth/github/callback', json={'code': 'c'}).status_code == 400
    assert client.post('/api/v1/auth/github/callback', json={'code': 'c', 'state': 'nope'}).status_code == 400
    redis_client.setex('github_oauth_state:s1', 60, '1')
    resp = client.post('/api/v1/auth/github/callback', json={'code': 'c', 'state': 's1'})
    assert resp.status_code == 401
    assert 'access_token' not in resp.get_json()


# -- Supabase bulk sync (admin guardrails) ---------------------------------

from rbac_helpers import default_org, make_role, make_user  # noqa: E402,F401


@pytest.fixture
def supabase_config(app, monkeypatch):
    monkeypatch.setitem(app.config, 'SUPABASE_URL', 'https://sb.example')
    monkeypatch.setitem(app.config, 'SUPABASE_SERVICE_ROLE_KEY', 'service-key')


def test_sync_supabase_rejects_non_default_org(app, users, auth, supabase_config):
    resp = auth(users['Administrator']).post('/api/v1/users/sync-supabase')
    assert resp.status_code == 403 and resp.get_json()['error'] == 'not_default_org'


def test_sync_supabase_audited_and_skips_other_org_users(app, db, users, auth, monkeypatch, supabase_config,
                                                        default_org, make_user):
    import requests
    from app.models import AuditLog, User
    deputy = make_user(default_org, perms=['users:manage', 'users:read'], roles=['Viewer'])
    new_email = f'sb-{uuid.uuid4().hex[:8]}@sb.test'
    sb_users = [
        {'id': 'sb-new', 'email': new_email, 'app_metadata': {'sheetstorm_roles': ['Administrator']}},
        {'id': 'sb-foreign', 'email': users['Analyst'].email, 'app_metadata': {'sheetstorm_roles': ['Administrator']}},
    ]
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp(200, {'users': sb_users}))
    resp = auth(deputy).post('/api/v1/users/sync-supabase')
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['created'] == 1 and body['skipped_other_org'] == 1
    assert body['roles_skipped'] == ['Administrator']
    db.session.expire_all()
    created = User.query.filter_by(email=new_email).one()
    assert created.organization_id == default_org.id and created.role_names == ['Viewer']
    analyst = User.query.get(users['Analyst'].id)
    assert analyst.supabase_id != 'sb-foreign' and analyst.role_names == ['Analyst']
    row = (AuditLog.query.filter_by(action='sync_supabase', user_id=deputy.id)
           .order_by(AuditLog.created_at.desc()).first())
    assert row is not None and row.event_type == 'admin_action'
