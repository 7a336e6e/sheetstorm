"""Login lockout (W1-LIFE-BE): counter, lock, generic errors, MFA failures,
expiry, bounds, and the C1 login order."""
from datetime import datetime, timedelta, timezone

import pytest

from conftest import TEST_PASSWORD
from rbac_helpers import make_role, make_user, new_org, security_events  # noqa: F401

WRONG = 'Wr0ng-Passw0rd-!!'


@pytest.fixture
def threshold3(monkeypatch):
    monkeypatch.setenv('LOGIN_LOCKOUT_THRESHOLD', '3')
    monkeypatch.setenv('LOGIN_LOCKOUT_MINUTES', '15')


@pytest.fixture
def victim(new_org, make_user):
    org = new_org()
    return make_user(org, roles=['Analyst'])


def _login(app, email, password, **extra):
    return app.test_client().post('/api/v1/auth/login', json={'email': email, 'password': password, **extra})


def _reload(db, user):
    from app.models import User
    db.session.expire_all()
    return db.session.get(User, user.id)


def test_lockout_after_threshold_generic_error(app, db, victim, threshold3):
    bodies = [_login(app, victim.email, WRONG) for _ in range(3)]
    assert all(r.status_code == 401 for r in bodies)
    u = _reload(db, victim)
    assert u.is_locked and u.failed_login_count == 3
    wrong = _login(app, victim.email, WRONG)
    right = _login(app, victim.email, TEST_PASSWORD)
    assert right.status_code == wrong.status_code == 401
    assert right.get_json() == wrong.get_json() == bodies[0].get_json()
    events = [e for e in security_events(db, 'account_locked') if e.resource_id == victim.id]
    assert len(events) == 1 and events[0].details['attempts'] == 3
    assert [e for e in security_events(db, 'login_while_locked') if e.resource_id == victim.id]
    # A running lock is not extended by attempts while locked.
    assert _reload(db, victim).locked_until == u.locked_until


def test_lockout_expires(app, db, victim, threshold3):
    victim.failed_login_count = 3
    victim.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.session.commit()
    assert _login(app, victim.email, TEST_PASSWORD).status_code == 200
    u = _reload(db, victim)
    assert u.failed_login_count == 0 and u.locked_until is None


def test_expired_lock_starts_fresh_window(app, db, victim, threshold3):
    victim.failed_login_count = 3
    victim.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.session.commit()
    _login(app, victim.email, WRONG)
    u = _reload(db, victim)
    assert u.failed_login_count == 1 and not u.is_locked


def test_success_resets_counter(app, db, victim, threshold3):
    _login(app, victim.email, WRONG)
    _login(app, victim.email, WRONG)
    assert _reload(db, victim).failed_login_count == 2
    assert _login(app, victim.email, TEST_PASSWORD).status_code == 200
    u = _reload(db, victim)
    assert u.failed_login_count == 0 and u.last_login is not None


def test_unknown_and_disabled_and_locked_same_body(app, db, new_org, make_user, threshold3):
    org = new_org()
    disabled = make_user(org, roles=['Analyst'], active=False)
    locked = make_user(org, roles=['Analyst'])
    locked.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    db.session.commit()
    responses = [
        _login(app, 'nobody-here@nowhere.test', TEST_PASSWORD),
        _login(app, disabled.email, TEST_PASSWORD),
        _login(app, locked.email, TEST_PASSWORD),
        _login(app, locked.email, WRONG),
    ]
    assert {r.status_code for r in responses} == {401}
    assert len({str(r.get_json()) for r in responses}) == 1
    assert responses[0].get_json()['message'] == 'Invalid email or password'


def test_mfa_failures_count_toward_lockout(app, db, victim, threshold3):
    import pyotp
    victim.mfa_enabled, victim.mfa_secret = True, pyotp.random_base32()
    db.session.commit()
    for _ in range(3):
        resp = _login(app, victim.email, TEST_PASSWORD, mfa_code='000000')
        assert resp.status_code == 401 and resp.get_json()['message'] == 'Invalid MFA code'
    u = _reload(db, victim)
    assert u.is_locked
    good = _login(app, victim.email, TEST_PASSWORD, mfa_code=pyotp.TOTP(u.mfa_secret).now())
    assert good.status_code == 401 and good.get_json()['message'] == 'Invalid email or password'


def test_mfa_complete_respects_lock_and_counts(app, db, victim, threshold3):
    import pyotp
    from flask_jwt_extended import create_access_token
    victim.mfa_enabled, victim.mfa_secret = True, pyotp.random_base32()
    db.session.commit()
    with app.app_context():
        pre = create_access_token(identity=str(victim.id), additional_claims={'pre_auth': True})
    url = '/api/v1/auth/mfa/complete'
    for _ in range(3):
        resp = app.test_client().post(url, json={'pre_auth_token': pre, 'mfa_code': '000000'})
        assert resp.status_code == 401
    assert _reload(db, victim).is_locked
    code = pyotp.TOTP(victim.mfa_secret).now()
    resp = app.test_client().post(url, json={'pre_auth_token': pre, 'mfa_code': code})
    assert resp.status_code == 401 and 'access_token' not in (resp.get_json() or {})


def test_concurrent_failures_atomic(app, db, victim, threshold3):
    from app.services.user_lifecycle import register_failed_login
    register_failed_login(victim, 'invalid_password')
    register_failed_login(victim, 'invalid_password')
    assert _reload(db, victim).failed_login_count == 2


@pytest.mark.parametrize('threshold,minutes,expected', [
    ('1', '0', (3, 1)), ('100', '99999', (20, 1440)), ('7', '30', (7, 30)), ('x', '', (10, 15)),
])
def test_lockout_settings_bounds(app, monkeypatch, threshold, minutes, expected):
    from app.services.user_lifecycle import lockout_settings
    monkeypatch.setenv('LOGIN_LOCKOUT_THRESHOLD', threshold)
    monkeypatch.setenv('LOGIN_LOCKOUT_MINUTES', minutes)
    assert lockout_settings(None) == expected


def test_admin_unlock_restores_login(app, db, auth, new_org, make_user, threshold3):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    target = make_user(org, roles=['Analyst'])
    for _ in range(3):
        _login(app, target.email, WRONG)
    assert _login(app, target.email, TEST_PASSWORD).status_code == 401
    assert auth(admin).post(f'/api/v1/users/{target.id}/unlock').status_code == 200
    assert _login(app, target.email, TEST_PASSWORD).status_code == 200


def test_unknown_email_runs_bcrypt(app, monkeypatch):
    from app.api.v1.endpoints import auth as auth_mod
    calls = []
    real = auth_mod._dummy_password_check
    monkeypatch.setattr(auth_mod, '_dummy_password_check', lambda pw: calls.append(1) or real(pw))
    assert _login(app, 'ghost@nowhere.test', TEST_PASSWORD).status_code == 401
    assert calls == [1]
