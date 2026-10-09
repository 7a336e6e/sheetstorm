"""Org security policy (W3-SEC): API, validation, versioning, audit, the
password rules on every write path, history, expiry, provisioning
(registration, email domains, default role) and lockout values."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from conftest import TEST_PASSWORD
from rbac_helpers import default_org, last_audit, make_role, make_user, new_org  # noqa: F401

URL = '/api/v1/organization/security-policy'
STRONG = 'Fresh-Passw0rd-2026!'


def _admin(auth, make_user, org):
    user = make_user(org, roles=['Administrator'])
    return user, auth(user)


def _put(client, policy, version):
    return client.put(URL, json={'policy': policy, 'version': version})


def _reload(db, model, obj_id):
    db.session.expire_all()
    return db.session.get(model, obj_id)


# ── API ────────────────────────────────────────────────────────────────

def test_defaults_when_no_row(app, auth, new_org, make_user):
    org = new_org()
    _, c = _admin(auth, make_user, org)
    resp = c.get(URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['version'] == 0 and body['updated_at'] is None and body['is_platform_org'] is False
    assert body['policy'] == body['defaults']
    pol = body['policy']
    assert pol['password']['min_length'] == 12 and pol['password']['history_count'] == 0
    assert pol['lockout'] == {'threshold': 10, 'duration_minutes': 15}
    assert pol['mfa']['required_for'] == 'none'
    assert pol['session'] == {'access_token_minutes': 60, 'refresh_token_days': 7}
    assert pol['provisioning'] == {'allowed_email_domains': [], 'registration_enabled': False,
                                   'default_role': 'Viewer'}
    assert body['stats']['users_total'] == 1 and body['bounds']['password.min_length']['max'] == 72


@pytest.mark.parametrize('policy,field', [
    ({'password': {'min_length': 11}}, 'password.min_length'),
    ({'password': {'min_length': 73}}, 'password.min_length'),
    ({'password': {'history_count': 25}}, 'password.history_count'),
    ({'password': {'max_age_days': 10}}, 'password.max_age_days'),
    ({'password': {'require_upper': 'yes'}}, 'password.require_upper'),
    ({'lockout': {'threshold': 2}}, 'lockout.threshold'),
    ({'lockout': {'duration_minutes': 1441}}, 'lockout.duration_minutes'),
    ({'mfa': {'required_for': 'admins'}}, 'mfa.required_for'),
    ({'mfa': {'grace_days': 91}}, 'mfa.grace_days'),
    ({'session': {'access_token_minutes': 61}}, 'session.access_token_minutes'),
    ({'session': {'refresh_token_days': 0}}, 'session.refresh_token_days'),
    ({'provisioning': {'allowed_email_domains': ['not a domain']}}, 'provisioning.allowed_email_domains'),
    ({'provisioning': {'allowed_email_domains': [f'd{i}.example' for i in range(51)]}},
     'provisioning.allowed_email_domains'),
    ({'password': {'bogus': 1}}, 'password.bogus'),
    ({'bogus': {}}, 'bogus'),
])
def test_bounds_and_unknown_keys(app, auth, new_org, make_user, policy, field):
    _, c = _admin(auth, make_user, new_org())
    resp = _put(c, policy, 0)
    assert resp.status_code == 400, resp.get_json()
    body = resp.get_json()
    assert body['error'] == 'validation_error' and field in body['fields'], body


def test_default_role_must_exist_and_not_be_privileged(app, auth, new_org, make_user, make_role):
    org = new_org()
    _, c = _admin(auth, make_user, org)
    for name in ('Administrator', 'No Such Role'):
        resp = _put(c, {'provisioning': {'default_role': name}}, 0)
        assert resp.status_code == 400 and 'provisioning.default_role' in resp.get_json()['fields']
    risky = make_role(org, ['incidents:read', 'users:manage'])
    assert _put(c, {'provisioning': {'default_role': risky.name}}, 0).status_code == 400
    resp = _put(c, {'provisioning': {'default_role': 'analyst'}}, 0)
    assert resp.status_code == 200
    assert resp.get_json()['policy']['provisioning']['default_role'] == 'Analyst'


def test_version_required_and_conflict(app, auth, new_org, make_user):
    _, c = _admin(auth, make_user, new_org())
    assert c.put(URL, json={'policy': {'lockout': {'threshold': 5}}}).status_code == 428
    first = _put(c, {'lockout': {'threshold': 5}}, 0)
    assert first.status_code == 200 and first.get_json()['version'] == 1
    assert first.headers['ETag'] == '"1"'
    stale = _put(c, {'lockout': {'threshold': 6}}, 0)
    assert stale.status_code == 409 and stale.get_json()['error'] == 'conflict'
    assert stale.get_json()['current']['policy']['lockout']['threshold'] == 5
    resp = c.put(URL, json={'policy': {'lockout': {'threshold': 6}}}, headers={'If-Match': '"1"'})
    assert resp.status_code == 200 and resp.get_json()['version'] == 2
    # Partial update: other fields keep their value.
    assert resp.get_json()['policy']['lockout'] == {'threshold': 6, 'duration_minutes': 15}


def test_requires_organizations_manage(app, auth, new_org, make_user):
    org = new_org()
    analyst = auth(make_user(org, roles=['Analyst']))
    assert analyst.get(URL).status_code == 403
    assert _put(analyst, {'lockout': {'threshold': 5}}, 0).status_code == 403


def test_cross_org_isolation(app, auth, new_org, make_user):
    org_x, org_y = new_org(), new_org()
    _, cx = _admin(auth, make_user, org_x)
    _, cy = _admin(auth, make_user, org_y)
    assert _put(cx, {'password': {'min_length': 20}}, 0).status_code == 200
    assert cy.get(URL).get_json()['policy']['password']['min_length'] == 12
    assert cx.get(URL).get_json()['policy']['password']['min_length'] == 20


def test_audit_row_has_changes(app, db, auth, new_org, make_user):
    org = new_org()
    _, c = _admin(auth, make_user, org)
    resp = _put(c, {'password': {'min_length': 14},
                    'provisioning': {'allowed_email_domains': ['Example.COM', 'corp.example']}}, 0)
    assert resp.status_code == 200
    assert resp.get_json()['policy']['provisioning']['allowed_email_domains'] == ['example.com', 'corp.example']
    row = last_audit(db, 'security_policy_update', 'organization_security_policy')
    assert row is not None and row.organization_id == org.id
    changes = row.details['changes']
    assert changes['password.min_length'] == {'from': 12, 'to': 14}
    assert changes['provisioning.allowed_email_domains'] == {'added': ['example.com', 'corp.example'],
                                                             'removed': []}


def test_registration_flag_only_on_platform_org(app, auth, new_org, make_user):
    _, c = _admin(auth, make_user, new_org())
    resp = _put(c, {'provisioning': {'registration_enabled': True}}, 0)
    assert resp.status_code == 400
    assert 'provisioning.registration_enabled' in resp.get_json()['fields']


def test_platform_admin_toggles_registration(app, db, auth, default_org, make_user, set_policy):
    set_policy(default_org, {})  # registers the platform policy for restoration
    _, c = _admin(auth, make_user, default_org)
    body = c.get(URL).get_json()
    assert body['is_platform_org'] is True
    resp = _put(c, {'provisioning': {'registration_enabled': True}}, body['version'])
    assert resp.status_code == 200
    assert app.test_client().get('/api/v1/auth/registration-status').get_json()['registration_enabled'] is True
    resp = _put(c, {'provisioning': {'registration_enabled': False}}, resp.get_json()['version'])
    assert resp.status_code == 200
    assert app.test_client().get('/api/v1/auth/registration-status').get_json()['registration_enabled'] is False


def test_enforced_since_is_server_managed(app, auth, new_org, make_user):
    _, c = _admin(auth, make_user, new_org())
    resp = _put(c, {'mfa': {'required_for': 'privileged', 'enforced_since': '2000-01-01T00:00:00Z'}}, 0)
    first = resp.get_json()['policy']['mfa']['enforced_since']
    assert first and not first.startswith('2000')
    # Same scope: unchanged. Wider scope: reset. None: cleared.
    resp = _put(c, {'mfa': {'grace_days': 3}}, 1)
    assert resp.get_json()['policy']['mfa']['enforced_since'] == first
    resp = _put(c, {'mfa': {'required_for': 'all'}}, 2)
    assert resp.get_json()['policy']['mfa']['enforced_since'] >= first
    resp = _put(c, {'mfa': {'required_for': 'none'}}, 3)
    assert resp.get_json()['policy']['mfa']['enforced_since'] is None


def test_password_policy_endpoint_public_and_org_specific(app, auth, new_org, make_user, set_policy):
    org = new_org()
    set_policy(org, {'password': {'min_length': 18, 'require_symbol': False}})
    anon = app.test_client().get('/api/v1/auth/password-policy')
    assert anon.status_code == 200 and anon.get_json()['max_bytes'] == 72
    own = auth(make_user(org, roles=['Viewer'])).get('/api/v1/auth/password-policy').get_json()
    assert own['min_length'] == 18 and own['require_symbol'] is False


# ── Password rules ─────────────────────────────────────────────────────

def test_validate_password_rules(app):
    from app.services.security_policy import PasswordPolicy, validate_password
    assert validate_password(STRONG)[0]
    assert not validate_password('Aa1!' + 'x' * 69)[0]  # 73 bytes
    ok, msgs = validate_password('Aa1!' + 'é' * 35)  # 4 + 70 bytes = 74 bytes, 39 chars
    assert not ok and any('72 bytes' in m for m in msgs)
    assert validate_password('Aa1~' + 'x' * 10)[0]  # any non-alphanumeric is a symbol
    ok, msgs = validate_password('short')
    assert not ok and len(msgs) >= 3
    relaxed = PasswordPolicy(min_length=12, require_symbol=False, require_upper=False)
    assert validate_password('lowercase1234', relaxed)[0]

    class U:
        email = 'alice.smith-2026@example.com'
        organization_id = None
    assert not validate_password('Alice.Smith-2026', relaxed, U())[0]


def test_wrapper_keeps_signature(app):
    from app.api.v1.endpoints.auth import validate_password
    assert validate_password(STRONG) == (True, None)
    ok, message = validate_password('weak')
    assert ok is False and isinstance(message, str)


def test_policy_applies_to_change_admin_create_and_reset(app, db, auth, new_org, make_user, set_policy):
    org = new_org()
    set_policy(org, {'password': {'min_length': 20}})
    admin, c = _admin(auth, make_user, org)
    weak = 'Only-15-Chars!1'  # valid under the default 12, not under 20

    resp = c.post('/api/v1/users', json={'email': f'n-{uuid.uuid4().hex[:6]}@x.test', 'name': 'n',
                                         'password': weak})
    assert resp.status_code == 400 and resp.get_json()['code'] == 'password_policy'
    resp = c.post('/api/v1/users', json={'email': f'n-{uuid.uuid4().hex[:6]}@x.test', 'name': 'n',
                                         'password': 'A-much-longer-Passw0rd!'})
    assert resp.status_code == 201

    target = make_user(org, roles=['Analyst'])
    assert c.put(f'/api/v1/users/{target.id}', json={'password': weak}).status_code == 400
    assert c.put(f'/api/v1/users/{target.id}', json={'password': 'A-much-longer-Passw0rd!'}).status_code == 200

    me = auth(make_user(org, roles=['Analyst']))
    resp = me.post('/api/v1/auth/change-password', json={'current_password': TEST_PASSWORD, 'new_password': weak})
    assert resp.status_code == 400 and resp.get_json()['violations']
    resp = me.post('/api/v1/auth/change-password',
                   json={'current_password': TEST_PASSWORD, 'new_password': 'A-much-longer-Passw0rd!'})
    assert resp.status_code == 200


def test_temp_password_meets_long_policy(app, db, auth, new_org, make_user, set_policy):
    org = new_org()
    set_policy(org, {'password': {'min_length': 30}})
    _, c = _admin(auth, make_user, org)
    target = make_user(org, roles=['Analyst'])
    resp = c.post(f'/api/v1/users/{target.id}/reset-password', json={'mode': 'temp'})
    assert resp.status_code == 200, resp.get_json()
    assert len(resp.get_json()['temp_password']) >= 30


def test_invite_accept_and_reset_complete_follow_org_policy(app, db, auth, new_org, make_user, set_policy):
    org = new_org()
    set_policy(org, {'password': {'min_length': 20}})
    _, c = _admin(auth, make_user, org)
    weak = 'Only-15-Chars!1'
    invite = c.post('/api/v1/users/invites', json={'email': f'i-{uuid.uuid4().hex[:6]}@x.test'}).get_json()
    anon = app.test_client()
    resp = anon.post('/api/v1/auth/invites/accept', json={'token': invite['token'], 'name': 'I', 'password': weak})
    assert resp.status_code == 400 and resp.get_json()['violations']
    resp = anon.post('/api/v1/auth/invites/accept',
                     json={'token': invite['token'], 'name': 'I', 'password': 'A-much-longer-Passw0rd!'})
    assert resp.status_code == 201

    target = make_user(org, roles=['Analyst'])
    link = c.post(f'/api/v1/users/{target.id}/reset-password', json={'mode': 'link'}).get_json()
    url = '/api/v1/auth/password-reset/complete'
    resp = anon.post(url, json={'token': link['token'], 'new_password': weak})
    assert resp.status_code == 400 and resp.get_json()['violations']
    # A rejected password does not burn the link.
    assert anon.post(url, json={'token': link['token'], 'new_password': 'A-much-longer-Passw0rd!'}).status_code == 200


def test_history_blocks_recent_passwords(app, db, new_org, make_user, set_policy):
    from app.models import PasswordHistory, User
    from app.services.security_policy import PasswordPolicyError, set_password
    org = new_org()
    set_policy(org, {'password': {'history_count': 2}})
    user = make_user(org, roles=['Analyst'])  # current: TEST_PASSWORD
    p1, p2 = 'History-Passw0rd-1!', 'History-Passw0rd-2!'

    with pytest.raises(PasswordPolicyError):
        set_password(user, TEST_PASSWORD)  # the current one
    set_password(user, p1)
    db.session.commit()
    with pytest.raises(PasswordPolicyError):
        set_password(user, TEST_PASSWORD)  # within the last 2
    set_password(user, p2)
    db.session.commit()
    set_password(user, TEST_PASSWORD)  # now 3 back: allowed
    db.session.commit()
    assert PasswordHistory.query.filter_by(user_id=user.id).count() == 3
    assert _reload(db, User, user.id).check_password(TEST_PASSWORD)
    # history_count 0 (default) allows reusing the current password.
    set_policy(org, {'password': {'history_count': 0}})
    set_password(db.session.get(User, user.id), TEST_PASSWORD)


def test_history_capped_at_24(app, db, new_org, make_user):
    from app.models import PasswordHistory
    from app.services.security_policy import set_password
    user = make_user(new_org(), roles=['Analyst'])
    for i in range(26):
        set_password(user, f'Rotating-Passw0rd-{i:02d}!', enforce_history=False)
    db.session.commit()
    assert PasswordHistory.query.filter_by(user_id=user.id).count() == 24


def test_change_password_rejects_reuse_via_api(app, db, auth, new_org, make_user, set_policy):
    org = new_org()
    set_policy(org, {'password': {'history_count': 3}})
    me = auth(make_user(org, roles=['Analyst']))
    resp = me.post('/api/v1/auth/change-password',
                   json={'current_password': TEST_PASSWORD, 'new_password': TEST_PASSWORD})
    assert resp.status_code == 400 and 'used recently' in resp.get_json()['message']


# ── Expiry ─────────────────────────────────────────────────────────────

def test_expired_password_restricts_to_change(app, db, new_org, make_user, set_policy):
    from app.models import User
    org = new_org()
    set_policy(org, {'password': {'max_age_days': 30}})
    user = make_user(org, roles=['Analyst'])
    user.password_changed_at = datetime.now(timezone.utc) - timedelta(days=31)
    db.session.commit()

    client = app.test_client()
    resp = client.post('/api/v1/auth/login', json={'email': user.email, 'password': TEST_PASSWORD})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['user']['must_change_password'] is True
    assert body['user']['security']['password_change_required'] is True
    headers = {'Authorization': f"Bearer {body['access_token']}"}
    blocked = client.get('/api/v1/incidents', headers=headers)
    assert blocked.status_code == 403 and blocked.get_json()['error'] == 'password_change_required'
    assert client.get('/api/v1/auth/password-policy', headers=headers).status_code == 200
    resp = client.post('/api/v1/auth/change-password', headers=headers,
                       json={'current_password': TEST_PASSWORD, 'new_password': STRONG})
    assert resp.status_code == 200
    assert _reload(db, User, user.id).must_change_password is False
    headers = {'Authorization': f"Bearer {resp.get_json()['access_token']}"}
    assert client.get('/api/v1/incidents', headers=headers).status_code == 200


def test_fresh_password_not_expired(app, db, new_org, make_user, set_policy):
    org = new_org()
    set_policy(org, {'password': {'max_age_days': 30}})
    user = make_user(org, roles=['Analyst'])
    resp = app.test_client().post('/api/v1/auth/login', json={'email': user.email, 'password': TEST_PASSWORD})
    assert resp.get_json()['user']['must_change_password'] is False
    assert resp.get_json()['user']['security']['password_expires_at']


# ── Provisioning ───────────────────────────────────────────────────────

def _register(app, email, password=STRONG):
    return app.test_client().post('/api/v1/auth/register', json={'email': email, 'name': 'R', 'password': password})


def test_register_uses_platform_policy(app, db, open_registration):
    from app.models import User
    open_registration(provisioning={'allowed_email_domains': ['ok.example'], 'default_role': 'Analyst'},
                      password={'min_length': 16})
    assert _register(app, f'r-{uuid.uuid4().hex[:6]}@bad.example').get_json()['error'] == 'email_domain_not_allowed'
    short = _register(app, f'r-{uuid.uuid4().hex[:6]}@ok.example', 'Short-Pass-1!')
    assert short.status_code == 400 and short.get_json()['code'] == 'password_policy'
    email = f'r-{uuid.uuid4().hex[:6]}@ok.example'
    resp = _register(app, email)
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()['user']['roles'] == ['Analyst']
    assert 'security' in resp.get_json()['user']
    assert User.query.filter_by(email=email).one().role_names == ['Analyst']


def test_register_closed_by_default(app, db, default_org):
    resp = _register(app, f'r-{uuid.uuid4().hex[:6]}@x.test')
    assert resp.status_code == 403 and resp.get_json()['error'] == 'registration_disabled'


def test_admin_create_and_invite_check_domains(app, db, auth, new_org, make_user, set_policy):
    org = new_org()
    set_policy(org, {'provisioning': {'allowed_email_domains': ['corp.example'], 'default_role': 'Analyst'}})
    _, c = _admin(auth, make_user, org)
    bad = c.post('/api/v1/users', json={'email': 'x@evil.example', 'name': 'x', 'password': STRONG})
    assert bad.status_code == 400 and bad.get_json()['error'] == 'email_domain_not_allowed'
    good = c.post('/api/v1/users', json={'email': f'x-{uuid.uuid4().hex[:6]}@corp.example', 'name': 'x',
                                         'password': STRONG})
    assert good.status_code == 201 and good.get_json()['roles'] == ['Analyst']
    inv = c.post('/api/v1/users/invites', json={'email': 'y@evil.example'})
    assert inv.status_code == 400 and inv.get_json()['error'] == 'email_domain_not_allowed'


class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


def test_sso_auto_provisioning_checks_domains(app, db, monkeypatch, redis_client, open_registration):
    import requests
    open_registration(provisioning={'allowed_email_domains': ['ok.example']})
    monkeypatch.setitem(app.config, 'SUPABASE_URL', 'https://sb.example')
    bad_email = f'sb-{uuid.uuid4().hex[:6]}@bad.example'
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp(200, {'email': bad_email, 'id': 'sb-x'}))
    resp = app.test_client().post('/api/v1/auth/supabase', json={'access_token': 'x'})
    assert resp.status_code == 403 and resp.get_json()['error'] == 'email_domain_not_allowed'

    monkeypatch.setitem(app.config, 'GITHUB_CLIENT_ID', 'cid')
    monkeypatch.setitem(app.config, 'GITHUB_CLIENT_SECRET', 'csecret')
    monkeypatch.setattr(requests, 'post', lambda *a, **k: _Resp(200, {'access_token': 'gh'}))

    def fake_get(url, *a, **k):
        if url.endswith('/user/emails'):
            return _Resp(200, [{'email': bad_email, 'primary': True, 'verified': True}])
        return _Resp(200, {'id': 42, 'login': 'x'})
    monkeypatch.setattr(requests, 'get', fake_get)
    redis_client.setex('github_oauth_state:sp1', 60, '1')
    resp = app.test_client().post('/api/v1/auth/github/callback', json={'code': 'c', 'state': 'sp1'})
    assert resp.status_code == 403 and resp.get_json()['error'] == 'email_domain_not_allowed'

    ok_email = f'sb-{uuid.uuid4().hex[:6]}@ok.example'
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp(200, {'email': ok_email, 'id': 'sb-y'}))
    resp = app.test_client().post('/api/v1/auth/supabase', json={'access_token': 'x'})
    assert resp.status_code == 200 and resp.get_json()['user']['roles'] == ['Viewer']


def test_domain_list_does_not_block_existing_users(app, db, new_org, make_user, set_policy):
    org = new_org()
    user = make_user(org, roles=['Analyst'])  # @rbac.test
    set_policy(org, {'provisioning': {'allowed_email_domains': ['corp.example']}})
    resp = app.test_client().post('/api/v1/auth/login', json={'email': user.email, 'password': TEST_PASSWORD})
    assert resp.status_code == 200


# ── Lockout values ─────────────────────────────────────────────────────

def test_lockout_values_come_from_policy(app, db, new_org, make_user, set_policy):
    from app.services.user_lifecycle import lockout_settings
    org = new_org()
    assert lockout_settings(org.id) == (10, 15)
    set_policy(org, {'lockout': {'threshold': 3, 'duration_minutes': 5}})
    assert lockout_settings(org.id) == (3, 5)
    user = make_user(org, roles=['Analyst'])
    client = app.test_client()
    for _ in range(3):
        client.post('/api/v1/auth/login', json={'email': user.email, 'password': 'Wr0ng-Passw0rd-!!'})
    from app.models import User
    assert _reload(db, User, user.id).is_locked
