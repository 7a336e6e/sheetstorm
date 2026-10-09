"""W4-RL: admin-configurable rate limits (services/rate_limit_settings.py, /system/rate-limits)."""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.services import rate_limit_settings as rls

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENDPOINTS = BACKEND_DIR / 'app' / 'api' / 'v1' / 'endpoints'
URL = '/api/v1/system/rate-limits'


@pytest.fixture(autouse=True)
def _clean_settings(app, db, monkeypatch):
    from app.models.system_setting import SystemSetting
    monkeypatch.delenv('RATE_LIMIT_SETTINGS_LOCKED', raising=False)
    SystemSetting.query.filter_by(key=rls.SETTINGS_KEY).delete()
    db.session.commit()
    rls.invalidate()
    yield
    SystemSetting.query.filter_by(key=rls.SETTINGS_KEY).delete()
    db.session.commit()
    rls.invalidate()


def _store(db, doc):
    from app.models.system_setting import SystemSetting
    db.session.add(SystemSetting(key=rls.SETTINGS_KEY, value=doc))
    db.session.commit()
    rls.invalidate()


# ── Inventory ───────────────────────────────────────────────────────────────

def test_no_literal_limits_remain_outside_system_routes():
    offenders = []
    for path in ENDPOINTS.glob('*.py'):
        if path.name == 'system.py':
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r'@limiter\.limit\(', line):
                offenders.append(f'{path.name}:{n}')
    assert offenders == [], 'use @limited(<group>) instead of literal limits'


def test_every_group_used_exists_and_every_group_parses():
    used = set()
    for path in ENDPOINTS.glob('*.py'):
        used |= set(re.findall(r"@limited\('([a-z_]+)'", path.read_text()))
    assert used and used <= set(rls.GROUPS)
    from limits import parse_many
    for key, gdef in rls.GROUPS.items():
        assert parse_many(gdef.default), key


# ── Resolution ──────────────────────────────────────────────────────────────

def test_defaults_env_and_override_precedence(app, db, monkeypatch):
    with app.app_context():
        assert rls.effective_limit('auth_login') == '5 per minute'
        monkeypatch.setenv('RATE_LIMIT_AUTH_LOGIN', '7 per minute')
        assert rls.configured('auth_login')[:2] == ('7 per minute', 'env')
        _store(db, {'groups': {'auth_login': {'limit': '2 per minute'}}})
        assert rls.configured('auth_login')[:2] == ('2 per minute', 'override')
        monkeypatch.setenv('RATE_LIMIT_SETTINGS_LOCKED', 'true')
        rls.invalidate()
        assert rls.configured('auth_login')[:2] == ('7 per minute', 'env')  # overrides ignored when locked


def test_disabled_group_falls_back_to_api_default_and_global_off_exempts(app, db):
    with app.app_context():
        _store(db, {'groups': {'search': {'enabled': False}}})
        assert rls.effective_limit('search') == rls.effective_limit('api_default')
        assert rls.is_exempt('search') is False
        _store_replace(db, {'enabled': False, 'groups': {}})
        assert rls.is_exempt('auth_login') is True and rls.is_exempt('api_default') is True


def _store_replace(db, doc):
    from app.models.system_setting import SystemSetting
    SystemSetting.query.filter_by(key=rls.SETTINGS_KEY).delete()
    db.session.commit()
    _store(db, doc)


def test_unreadable_settings_fall_back_to_defaults_with_limiting_on(app, monkeypatch):
    with app.app_context():
        def boom():
            raise RuntimeError('db down')
        monkeypatch.setattr(rls, '_load_from_store', boom)
        rls.invalidate()
        assert rls.global_enabled() is True
        assert rls.effective_limit('auth_login') == '5 per minute'


# ── Validation ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize('groups,field', [
    ({'nope': {'limit': '1 per minute'}}, 'groups.nope'),
    ({'auth_login': {'limit': 'lots'}}, 'groups.auth_login.limit'),
    ({'auth_login': {'limit': '0 per minute'}}, 'groups.auth_login.limit'),
    ({'auth_login': {'limit': ';'.join(['1 per second'] * 6)}}, 'groups.auth_login.limit'),
    ({'api_default': {'limit': '100 per hour'}}, 'groups.api_default.limit'),  # below the UI floor
    ({'auth_login': {'enabled': 'no'}}, 'groups.auth_login.enabled'),
])
def test_validation_errors(groups, field):
    with pytest.raises(rls.RateLimitSettingsError) as exc:
        rls.validate({'groups': groups})
    assert field in exc.value.fields


def test_weakening_warnings():
    _, warnings = rls.validate({'enabled': True, 'groups': {'search': {'limit': '120 per minute'}}})
    assert warnings == []
    _, warnings = rls.validate({'enabled': False, 'groups': {
        'auth_login': {'enabled': False}, 'mfa_verify': {'limit': '1000 per hour'}, 'api_default': {'enabled': False}}})
    text = '\n'.join(warnings)
    assert 'turned off' in text and 'auth_login' in text and 'mfa_verify' in text and 'api_default' in text


# ── API ─────────────────────────────────────────────────────────────────────

def test_org_admin_can_read_but_not_change(users, auth):
    admin = auth(users['Administrator'])  # org A: not the platform org
    body = admin.get(URL).get_json()
    assert body['can_edit'] is False and body['enabled'] is True and body['version'] == 0
    login = next(g for g in body['groups'] if g['key'] == 'auth_login')
    assert login['default'] == '5 per minute' and login['source'] == 'code' and login['auth_sensitive']
    assert admin.put(URL, json={'groups': {}, 'version': 0}).status_code == 403
    assert auth(users['Analyst']).get(URL).status_code == 403


def test_platform_admin_changes_resets_and_is_audited(platform_admin, auth):
    from app.models import AuditLog
    client = auth(platform_admin)
    assert client.get(URL).get_json()['can_edit'] is True
    assert client.put(URL, json={'groups': {}}).status_code == 428

    resp = client.put(URL, json={'version': 0, 'groups': {'search': {'limit': '120 per minute'}}})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    search = next(g for g in body['groups'] if g['key'] == 'search')
    assert search['source'] == 'override' and search['effective'] == '120 per minute' and body['version'] == 1
    assert client.put(URL, json={'version': 0, 'groups': {}}).status_code == 409  # stale

    rows = AuditLog.query.filter_by(action='rate_limits_update').all()  # incl. the refused 428/409 attempts
    assert any('search.limit' in (r.details or {}).get('changes', {}) for r in rows)

    resp = client.post(URL + '/reset', json={'groups': ['search']})
    assert resp.status_code == 200
    search = next(g for g in resp.get_json()['groups'] if g['key'] == 'search')
    assert search['source'] == 'code'


def test_weakening_needs_confirmation_and_logs_a_security_event(platform_admin, auth):
    from app.models import AuditLog
    client = auth(platform_admin)
    resp = client.put(URL, json={'version': 0, 'enabled': False, 'groups': {}})
    assert resp.status_code == 409 and resp.get_json()['error'] == 'confirmation_required'
    assert resp.get_json()['warnings']
    resp = client.put(URL, json={'version': 0, 'enabled': False, 'groups': {}, 'confirm_weakening': True})
    assert resp.status_code == 200 and resp.get_json()['enabled'] is False
    assert AuditLog.query.filter_by(action='rate_limits_weakened').count() >= 1


def test_locked_settings_refuse_changes(platform_admin, auth, monkeypatch):
    monkeypatch.setenv('RATE_LIMIT_SETTINGS_LOCKED', 'true')
    client = auth(platform_admin)
    assert client.get(URL).get_json()['locked'] is True
    resp = client.put(URL, json={'version': 0, 'groups': {}})
    assert resp.status_code == 409 and resp.get_json()['error'] == 'settings_locked'


# ── Enforcement (separate interpreter: the suite runs with the limiter off) ──

_ENFORCE_SCRIPT = r"""
import app.config as config
config.TestingConfig.RATELIMIT_ENABLED = True
from app import create_app, db, limiter
from app.models.system_setting import SystemSetting
from app.services import rate_limit_settings as rls
application = create_app('testing')
with application.app_context():
    SystemSetting.query.filter_by(key=rls.SETTINGS_KEY).delete()
    db.session.add(SystemSetting(key=rls.SETTINGS_KEY, value={'groups': {'auth_login': {'limit': '2 per minute'}}}))
    db.session.commit()
    rls.invalidate()
    limiter.reset()
    client = application.test_client()
    body = {'email': 'nobody@example.test', 'password': 'wrong-password-123'}
    codes = [client.post('/api/v1/auth/login', json=body).status_code for _ in range(3)]
    # Turn rate limiting off entirely: no 429 any more, without a restart.
    SystemSetting.query.filter_by(key=rls.SETTINGS_KEY).update({'value': {'enabled': False, 'groups': {}}})
    db.session.commit()
    rls.invalidate()
    after = [client.post('/api/v1/auth/login', json=body).status_code for _ in range(3)]
    SystemSetting.query.filter_by(key=rls.SETTINGS_KEY).delete()
    db.session.commit()
    rls.invalidate()
    limiter.reset()
print(','.join(map(str, codes)) + '|' + ','.join(map(str, after)))
"""


def test_override_applies_without_restart_and_global_switch(app):
    r = subprocess.run([sys.executable, '-c', _ENFORCE_SCRIPT], cwd=BACKEND_DIR, capture_output=True,
                       text=True, timeout=120, env=os.environ.copy())
    assert r.returncode == 0, r.stderr[-3000:]
    first, after = r.stdout.strip().splitlines()[-1].split('|')
    assert first.split(',')[-1] == '429' and '429' not in first.split(',')[:2]
    assert '429' not in after.split(',')
