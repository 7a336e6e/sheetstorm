"""Item 12: Google Drive OAuth callback — state validation, server-side token
storage, no tokens in redirect URL, redirect host from FRONTEND_URL only."""
import json
from urllib.parse import urlparse, parse_qs

import pytest


@pytest.fixture
def drive_app(app, db, users, org_a, monkeypatch):
    from app.models import Integration
    from app.services.encryption_service import encryption_service
    from app.services.google_drive_service import google_drive_service
    i = Integration(organization_id=org_a.id, type='google_drive', name='Google Drive', is_enabled=True,
                    config={}, created_by=users['Administrator'].id,
                    credentials_encrypted=encryption_service.encrypt(json.dumps(
                        {'client_id': 'cid', 'client_secret': 'csec'})))
    db.session.add(i)
    db.session.commit()
    monkeypatch.setitem(app.config, 'FRONTEND_URL', 'https://ir.example')
    calls = []

    def fake_exchange(code, org_id=None):
        calls.append((code, org_id))
        return {'access_token': 'ya29.ACCESS', 'refresh_token': '1//REFRESH'}
    monkeypatch.setattr(google_drive_service, 'exchange_code', fake_exchange)
    yield i, calls
    db.session.delete(db.session.get(Integration, i.id))
    db.session.commit()


def _start(auth, users):
    resp = auth(users['Administrator']).post('/api/v1/google-drive/auth')
    assert resp.status_code == 200
    return resp.get_json()['state']


def test_callback_stores_tokens_server_side(app, db, users, auth, drive_app, org_a):
    from app.models import Integration
    from app.services.encryption_service import encryption_service
    integ, calls = drive_app
    state = _start(auth, users)
    resp = app.test_client().get(f'/api/v1/google-drive/oauth/callback?code=abc&state={state}',
                                 headers={'Host': 'attacker.example'})
    assert resp.status_code == 302
    loc = resp.headers['Location']
    assert loc.startswith('https://ir.example/dashboard/admin/settings?')
    q = parse_qs(urlparse(loc).query)
    assert q == {'tab': ['storage'], 'drive': ['connected']}
    assert 'ya29' not in loc and 'REFRESH' not in loc
    assert calls == [('abc', str(org_a.id))]
    db.session.expire_all()
    creds = json.loads(encryption_service.decrypt(db.session.get(Integration, integ.id).credentials_encrypted))
    assert creds['refresh_token'] == '1//REFRESH' and creds['client_id'] == 'cid'

    # state is single-use
    again = app.test_client().get(f'/api/v1/google-drive/oauth/callback?code=abc&state={state}')
    assert 'drive_error=invalid_state' in again.headers['Location']


@pytest.mark.parametrize('qs', ['code=abc', 'code=abc&state=forged'])
def test_callback_rejects_missing_or_unknown_state(app, drive_app, qs):
    resp = app.test_client().get(f'/api/v1/google-drive/oauth/callback?{qs}')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('?tab=storage&drive_error=invalid_state')
    assert drive_app[1] == []  # never exchanged


def test_callback_error_param_sanitised(app, users, auth, drive_app):
    state = _start(auth, users)
    resp = app.test_client().get(f'/api/v1/google-drive/oauth/callback?error=access_denied%3Cscript%3E&state={state}')
    assert resp.headers['Location'].endswith('&drive_error=access_deniedscript')


def test_auth_requires_org_drive_config(app, users, auth):
    # org B has no Drive OAuth app configured (and env has none in tests)
    assert auth(users['admin_b']).post('/api/v1/google-drive/auth').status_code == 400
