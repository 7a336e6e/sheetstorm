"""Scoped API keys + service accounts (api-keys plan §6, _integration.md C30).

Keys are generated inside the tests and never leave them.
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.models import AuditLog, User
from app.models.api_key import ApiKey

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INVALID = {'error': 'invalid_api_key', 'message': 'Invalid API key'}


def _now():
    return datetime.now(timezone.utc)


def _decode(app, token):
    from flask_jwt_extended import decode_token
    with app.app_context():
        return decode_token(token)


def _create(client, **body):
    return client.post('/api/v1/api-keys', json=body)


def _audit_rows(db, action, **detail_match):
    rows = AuditLog.query.filter(AuditLog.action == action).order_by(AuditLog.chain_seq.desc()).all()
    return [r for r in rows if all((r.details or {}).get(k) == v for k, v in detail_match.items())]


def _role_id(name):
    from app.models import Role
    return str(Role.query.filter_by(name=name, is_system=True).one().id)


def _secret_in_audit(db, secret):
    return db.session.execute(text("SELECT count(*) FROM audit_logs a WHERE a::text LIKE :s"),
                              {'s': f'%{secret}%'}).scalar()


# ── Create ──────────────────────────────────────────────────────────

def test_create_returns_secret_once_and_never_the_hash(app, db, make_user, key_org, auth):
    owner = make_user(key_org, roles=['Analyst'])
    c = auth(owner)
    resp = _create(c, name='mcp', scopes=['incidents:read', 'timeline:read'], expires_in_days=30)
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body['secret'].startswith(body['prefix'] + '_')
    assert 'key_hash' not in body and body['status'] == 'active'
    assert body['scopes'] == ['incidents:read', 'timeline:read']
    assert resp.headers['Cache-Control'] == 'no-store'
    assert 'Set-Cookie' not in resp.headers

    got = c.get(f"/api/v1/api-keys/{body['id']}").get_json()
    assert 'secret' not in got and 'key_hash' not in got
    listed = c.get('/api/v1/api-keys').get_json()
    assert [k['id'] for k in listed['items']] == [body['id']]
    assert all('secret' not in k and 'key_hash' not in k for k in listed['items'])

    stored = db.session.get(ApiKey, body['id'])
    assert stored.key_hash != body['secret'] and len(stored.key_hash) == 64
    assert body['secret'].split('_', 2)[2] not in stored.key_hash
    assert _secret_in_audit(db, body['secret']) == 0


@pytest.mark.parametrize('scopes, field', [
    (['users:manage'], 'forbidden'),            # not grantable to keys at all
    (['decisions:approve'], 'forbidden'),        # C30: no LLM approvals
    (['api_keys:own'], 'forbidden'),             # keys can't mint keys
    (['no:such'], 'unknown'),
    (['incidents:create'], 'not_held'),          # Analyst lacks it
])
def test_create_rejects_bad_scopes(app, make_user, key_org, auth, scopes, field):
    owner = make_user(key_org, roles=['Analyst'])
    resp = _create(auth(owner), name='k', scopes=scopes)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body['error'] == 'invalid_scopes' and body[field] == scopes


def test_admin_cannot_grant_non_grantable_scopes(app, make_user, key_org, auth):
    admin = make_user(key_org, roles=['Administrator'])
    for scope in ('system:manage', 'decisions:read_privileged', 'response_actions:authorize',
                  'organizations:manage', 'roles:manage', 'integrations:update', 'api_keys:manage'):
        resp = _create(auth(admin), name=f'k-{scope}', scopes=[scope])
        assert resp.status_code == 400 and resp.get_json()['forbidden'] == [scope], scope


def test_create_rejects_empty_scopes_and_bad_lifetime(app, db, make_user, key_org, auth):
    owner = make_user(key_org, roles=['Analyst'])
    c = auth(owner)
    assert _create(c, name='k', scopes=[]).get_json()['error'] == 'invalid_scopes'
    for days in (0, 366, -1):
        resp = _create(c, name='k', scopes=['incidents:read'], expires_in_days=days)
        assert resp.status_code == 400 and resp.get_json()['error'] == 'validation_error', days
    key_org.settings = {'api_key_max_lifetime_days': 30}
    db.session.commit()
    resp = _create(c, name='k', scopes=['incidents:read'], expires_in_days=31)
    assert resp.status_code == 400 and resp.get_json()['max_days'] == 30
    resp = _create(c, name='k', scopes=['incidents:read'])  # default 90 capped to 30
    assert resp.status_code == 201
    exp = datetime.fromisoformat(resp.get_json()['expires_at'])
    assert timedelta(days=29) < exp - _now() <= timedelta(days=30)


def test_name_unique_among_active_keys_and_caps(app, make_user, key_org, auth, monkeypatch):
    owner = make_user(key_org, roles=['Analyst'])
    c = auth(owner)
    assert _create(c, name='dup', scopes=['incidents:read']).status_code == 201
    resp = _create(c, name='DUP', scopes=['incidents:read'])
    assert resp.status_code == 409 and resp.get_json()['error'] == 'name_conflict'

    monkeypatch.setitem(app.config, 'API_KEY_MAX_PER_USER', 2)
    assert _create(c, name='two', scopes=['incidents:read']).status_code == 201
    resp = _create(c, name='three', scopes=['incidents:read'])
    assert resp.status_code == 409 and resp.get_json()['scope'] == 'owner'


def test_expired_key_releases_its_name(app, db, make_user, key_org, make_api_key):
    owner = make_user(key_org, roles=['Analyst'])
    key, _ = make_api_key(owner, ['incidents:read'], name='reuse')
    key.created_at = _now() - timedelta(days=2)
    key.expires_at = _now() - timedelta(days=1)
    db.session.commit()
    new, _ = make_api_key(owner, ['incidents:read'], name='reuse')
    db.session.refresh(key)
    assert key.status == 'revoked' and key.revoked_reason == 'expired' and new.status == 'active'


# ── Ownership / visibility ──────────────────────────────────────────

def test_non_manager_sees_only_own_keys(app, make_user, key_org, auth, make_api_key):
    alice = make_user(key_org, roles=['Analyst'])
    bob = make_user(key_org, roles=['Analyst'])
    key, _ = make_api_key(alice, ['incidents:read'])
    cb = auth(bob)
    assert cb.get(f'/api/v1/api-keys/{key.id}').status_code == 404
    assert cb.post(f'/api/v1/api-keys/{key.id}/rotate', json={}).status_code == 404
    assert cb.delete(f'/api/v1/api-keys/{key.id}').status_code == 404
    assert cb.get('/api/v1/api-keys').get_json()['items'] == []
    resp = _create(cb, name='x', scopes=['incidents:read'], owner_id=str(alice.id))
    assert resp.status_code == 403


def test_manager_creates_for_service_account_not_for_humans(app, make_user, key_org, auth):
    admin = make_user(key_org, roles=['Administrator'])
    human = make_user(key_org, roles=['Analyst'])
    ca = auth(admin)
    sa = ca.post('/api/v1/service-accounts', json={'name': 'Ingest Bot', 'role_ids': [_role_id('Analyst')]})
    assert sa.status_code == 201, sa.get_json()
    sa = sa.get_json()
    assert sa['email'].endswith('@service.invalid') and sa['is_service_account'] is True

    resp = _create(ca, name='ingest', scopes=['timeline:create', 'incidents:read'], owner_id=sa['id'])
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()['owner']['is_service_account'] is True

    resp = _create(ca, name='impersonate', scopes=['incidents:read'], owner_id=str(human.id))
    assert resp.status_code == 403 and resp.get_json()['error'] == 'not_service_account'

    # The manager sees every org key; the scopes endpoint resolves the SA's.
    listed = ca.get('/api/v1/api-keys').get_json()
    assert any(k['owner_user_id'] == sa['id'] for k in listed['items'])
    groups = ca.get(f"/api/v1/api-keys/scopes?owner_id={sa['id']}").get_json()['groups']
    values = {s['value'] for g in groups for s in g['scopes']}
    assert 'timeline:create' in values and 'users:manage' not in values and 'api_keys:own' not in values


def test_manager_cannot_rotate_another_humans_key_but_can_revoke(app, make_user, key_org, auth, make_api_key):
    admin = make_user(key_org, roles=['Administrator'])
    human = make_user(key_org, roles=['Analyst'])
    key, _ = make_api_key(human, ['incidents:read'])
    ca = auth(admin)
    assert ca.get(f'/api/v1/api-keys/{key.id}').status_code == 200
    assert ca.post(f'/api/v1/api-keys/{key.id}/rotate', json={}).status_code == 403
    resp = ca.delete(f'/api/v1/api-keys/{key.id}')
    assert resp.status_code == 200 and resp.get_json()['status'] == 'revoked'


def test_cross_org_is_404(app, users, make_user, key_org, make_api_key, auth):
    owner = make_user(key_org, roles=['Analyst'])
    key, _ = make_api_key(owner, ['incidents:read'])
    cb = auth(users['admin_b'])
    assert cb.get(f'/api/v1/api-keys/{key.id}').status_code == 404
    assert cb.delete(f'/api/v1/api-keys/{key.id}').status_code == 404
    assert all(k['id'] != str(key.id) for k in cb.get('/api/v1/api-keys').get_json()['items'])
    assert cb.get(f'/api/v1/api-keys/scopes?owner_id={owner.id}').status_code == 404


def test_viewer_without_api_keys_own_is_forbidden(app, make_user, key_org, auth):
    viewer = make_user(key_org, roles=['Viewer'])
    assert auth(viewer).get('/api/v1/api-keys').status_code == 403
    assert _create(auth(viewer), name='k', scopes=['incidents:read']).status_code == 403


def test_service_account_roles_go_through_escalation_guard(app, make_user, key_org, auth):
    manager = make_user(key_org, perms=['api_keys:manage', 'roles:manage'])
    ca = auth(manager)
    resp = ca.post('/api/v1/service-accounts', json={'name': 'root bot', 'role_ids': [_role_id('Administrator')]})
    assert resp.status_code == 403 and resp.get_json()['error'] == 'privilege_escalation'


# ── Exchange ────────────────────────────────────────────────────────

def test_exchange_mints_short_header_only_token(app, db, make_user, key_org, make_api_key, exchange_key):
    owner = make_user(key_org, roles=['Analyst'])
    key, full = make_api_key(owner, ['incidents:read', 'timeline:read'])
    resp = exchange_key(full, environ_base={'REMOTE_ADDR': '198.51.100.7'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['token_type'] == 'Bearer' and body['expires_in'] == 15 * 60
    assert 'refresh_token' not in body and 'Set-Cookie' not in resp.headers
    assert resp.headers['Cache-Control'] == 'no-store'
    claims = _decode(app, body['access_token'])
    assert claims['sub'] == str(owner.id) and claims['type'] == 'access'
    assert claims['api_key_id'] == str(key.id) and claims['api_key_prefix'] == key.prefix
    assert claims['scopes'] == ['incidents:read', 'timeline:read'] and claims['auth_method'] == 'api_key'
    assert claims['exp'] - claims['iat'] == 15 * 60

    db.session.refresh(key)
    assert key.use_count == 1 and str(key.last_used_ip) == '198.51.100.7' and key.last_used_at

    # Also accepted as `Authorization: ApiKey <key>` (this endpoint only).
    resp = app.test_client().post('/api/v1/auth/token', headers={'Authorization': f'ApiKey {full}'})
    assert resp.status_code == 200


def test_exchange_failures_share_one_401(app, db, make_user, key_org, make_api_key, exchange_key):
    owner = make_user(key_org, roles=['Analyst'])
    _, good = make_api_key(owner, ['incidents:read'])
    prefix = good[:16]  # ssk_ + 12-char lookup id

    revoked, revoked_full = make_api_key(owner, ['incidents:read'])
    revoked.revoked_at = _now()
    expired, expired_full = make_api_key(owner, ['incidents:read'])
    expired.created_at = _now() - timedelta(days=2)
    expired.expires_at = _now() - timedelta(seconds=1)
    db.session.commit()

    other = make_user(key_org, roles=['Analyst'])
    _, inactive_full = make_api_key(other, ['incidents:read'])
    other.is_active = False
    db.session.commit()

    secret_part = good[17:]
    wrong_secret = good[:-1] + ('A' if good[-1] != 'A' else 'B')
    unknown_prefix = 'ssk_' + 'a' * 12 + '_' + secret_part
    cases = {
        'malformed': 'not-a-key', 'invalid_secret': wrong_secret, 'unknown_prefix': unknown_prefix,
        'revoked': revoked_full, 'expired': expired_full, 'owner_inactive': inactive_full,
    }
    for reason, raw in cases.items():
        resp = exchange_key(raw)
        assert resp.status_code == 401 and resp.get_json() == INVALID, reason
        assert _audit_rows(db, 'api_key_exchange', reason=reason), reason
    assert exchange_key(None).get_json() == INVALID

    key_org.settings = {'api_keys_enabled': False}
    db.session.commit()
    resp = exchange_key(good)
    assert resp.status_code == 401 and resp.get_json() == INVALID
    assert _audit_rows(db, 'api_key_exchange', reason='org_disabled', prefix=prefix)
    for raw in list(cases.values()) + [good]:
        assert _secret_in_audit(db, raw[-20:]) == 0


def test_org_kill_switch_blocks_creation(app, db, make_user, key_org, auth):
    admin = make_user(key_org, roles=['Administrator'])
    ca = auth(admin)
    resp = ca.put('/api/v1/organization', json={'settings': {'api_keys_enabled': False,
                                                             'api_key_max_lifetime_days': 30}})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['settings']['api_keys_enabled'] is False
    resp = _create(ca, name='k', scopes=['incidents:read'])
    assert resp.status_code == 403 and resp.get_json()['error'] == 'api_keys_disabled'
    for bad in ({'api_keys_enabled': 'no'}, {'api_key_max_lifetime_days': 0},
                {'api_key_max_lifetime_days': 366}, {'api_key_max_lifetime_days': '30'}):
        assert ca.put('/api/v1/organization', json={'settings': bad}).status_code == 400, bad


def test_exchange_rate_limits(app):
    # The suite runs with the limiter disabled and Flask-Limiter is a
    # process-wide singleton, so exercise it in a separate interpreter.
    r = subprocess.run([sys.executable, '-c', _RATE_LIMIT_SCRIPT], cwd=BACKEND_DIR, capture_output=True,
                       text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-3000:]
    per_ip, per_prefix = r.stdout.strip().splitlines()[-2:]
    per_ip, per_prefix = per_ip.split(','), per_prefix.split(',')
    assert per_ip[:10] == ['401'] * 10 and per_ip[10] == '429'
    assert per_prefix[:30] == ['401'] * 30 and per_prefix[30] == '429'


_RATE_LIMIT_SCRIPT = r"""
import app.config as config
config.TestingConfig.RATELIMIT_ENABLED = True
from app import create_app, limiter
application = create_app('testing')
with application.app_context():
    limiter.reset()
    client = application.test_client()
    bad = 'ssk_' + 'b' * 12 + '_' + 'x' * 43
    per_ip = [client.post('/api/v1/auth/token', json={'api_key': 'ssk_' + 'c' * 12 + '_' + str(i).rjust(43, 'y')},
                          environ_base={'REMOTE_ADDR': '203.0.113.9'}).status_code for i in range(11)]
    limiter.reset()
    per_prefix = [client.post('/api/v1/auth/token', json={'api_key': bad},
                              environ_base={'REMOTE_ADDR': f'10.9.{i // 200}.{i % 200 + 1}'}).status_code
                  for i in range(31)]
    limiter.reset()
print(','.join(map(str, per_ip)))
print(','.join(map(str, per_prefix)))
"""


# ── Scope intersection ──────────────────────────────────────────────

def test_scopes_intersect_owner_permissions_per_request(app, db, make_user, key_org, make_api_key,
                                                        key_client, make_incident):
    owner = make_user(key_org, roles=['Incident Responder'])
    inc = make_incident(org=key_org, creator=owner, assign=[owner])
    from app.models import CompromisedAccount
    acct = CompromisedAccount(incident_id=inc.id, datetime_seen=_now(), account_name='svc-x',
                              account_type='domain', created_by=owner.id)
    db.session.add(acct)
    db.session.commit()

    _, full = make_api_key(owner, ['incidents:read', 'accounts:read'])
    kc = key_client(full)
    assert kc.get(f'/api/v1/incidents/{inc.id}').status_code == 200
    assert kc.put(f'/api/v1/incidents/{inc.id}', json={'title': 'nope'}).status_code == 403
    assert kc.post('/api/v1/incidents', json={'title': 'x', 'severity': 'low'}).status_code == 403
    # Direct user.has_permission() call site (not a decorator).
    resp = kc.get(f'/api/v1/incidents/{inc.id}/accounts/{acct.id}?reveal=true')
    assert resp.status_code == 403 and 'compromised_accounts:reveal' in resp.get_json()['message']

    me = kc.get('/api/v1/auth/me').get_json()
    assert me['permissions'] == ['accounts:read', 'incidents:read']
    assert me['auth']['method'] == 'api_key' and me['auth']['scopes'] == ['accounts:read', 'incidents:read']

    # Owner downgrade: the same token loses what the owner lost.
    from app.models import Role, UserRole
    UserRole.query.filter_by(user_id=owner.id).delete()
    narrow = Role(name=f'narrow-{owner.id.hex[:8]}', permissions=['incidents:read'], is_system=False,
                  organization_id=key_org.id)
    db.session.add(narrow)
    db.session.flush()
    db.session.add(UserRole(user_id=owner.id, role_id=narrow.id, organization_id=key_org.id))
    db.session.commit()
    db.session.expire_all()
    assert kc.get(f'/api/v1/auth/me').get_json()['permissions'] == ['incidents:read']
    assert kc.get(f'/api/v1/incidents/{inc.id}/accounts/{acct.id}').status_code == 403


def test_visibility_follows_owner_incident_scopes(app, make_user, key_org, make_api_key, key_client,
                                                  make_incident):
    manager = make_user(key_org, roles=['Manager'])  # incidents:read_all
    other = make_user(key_org, roles=['Administrator'])
    inc = make_incident(org=key_org, creator=other)  # not assigned to the manager
    _, full = make_api_key(manager, ['incidents:read'])
    assert key_client(full).get(f'/api/v1/incidents/{inc.id}').status_code == 200


def test_password_change_restriction_applies_to_keys(app, db, make_user, key_org, make_api_key, key_client):
    owner = make_user(key_org, roles=['Analyst'])
    _, full = make_api_key(owner, ['incidents:read'])
    kc = key_client(full)
    owner.must_change_password = True
    db.session.commit()
    resp = kc.get('/api/v1/incidents')
    assert resp.status_code == 403 and resp.get_json()['error'] == 'password_change_required'


def test_restricted_owner_can_exchange_but_token_stays_gated(app, db, make_user, key_org, make_api_key,
                                                             key_client, exchange_key):
    owner = make_user(key_org, roles=['Analyst'])
    _, full = make_api_key(owner, ['incidents:read'])
    owner.must_change_password = True
    db.session.commit()
    # /auth/token is on the account_state allowlist, even with a (restricted)
    # bearer token on the request ...
    stale = key_client(full)
    resp = exchange_key(full, headers={'Authorization': f'Bearer {stale.token}'})
    assert resp.status_code == 200, resp.get_json()
    # ... but the issued token is still refused everywhere else.
    kc = key_client(full)
    for path in ('/api/v1/incidents', '/api/v1/users'):
        r = kc.get(path)
        assert r.status_code == 403 and r.get_json()['error'] == 'password_change_required', path


# ── Interactive-only routes / websocket ─────────────────────────────

@pytest.mark.parametrize('method, path', [
    ('POST', '/api/v1/auth/change-password'),
    ('POST', '/api/v1/auth/mfa/setup'),
    ('POST', '/api/v1/auth/mfa/verify'),
    ('POST', '/api/v1/auth/mfa/disable'),
    ('PATCH', '/api/v1/auth/me/preferences'),
    ('GET', '/api/v1/api-keys'),
    ('POST', '/api/v1/api-keys'),
    ('GET', '/api/v1/api-keys/scopes'),
    ('GET', '/api/v1/service-accounts'),
])
def test_key_tokens_cannot_use_interactive_routes(app, make_user, key_org, make_api_key, key_client,
                                                  method, path):
    owner = make_user(key_org, roles=['Administrator'])
    _, full = make_api_key(owner, ['incidents:read'])
    resp = key_client(full).open(method, path, json={})
    assert resp.status_code == 403 and resp.get_json()['error'] == 'interactive_session_required'


def test_websocket_key_token_is_anonymous(app, make_user, key_org, make_api_key, exchange_key):
    from app import socketio
    owner = make_user(key_org, roles=['Analyst'])
    _, full = make_api_key(owner, ['incidents:read'])
    token = exchange_key(full).get_json()['access_token']
    c = socketio.test_client(app, auth={'token': token})
    events = [e for e in c.get_received() if e['name'] == 'connected']
    assert events and events[-1]['args'][0].get('anonymous') is True


# ── Revocation / rotation ───────────────────────────────────────────

def test_revoke_kills_existing_token_at_once(app, make_user, key_org, make_api_key, key_client, auth):
    owner = make_user(key_org, roles=['Analyst'])
    key, full = make_api_key(owner, ['incidents:read'])
    kc = key_client(full)
    assert kc.get('/api/v1/auth/me').status_code == 200
    resp = auth(owner).delete(f'/api/v1/api-keys/{key.id}', json={'reason': 'leaked'})
    assert resp.status_code == 200 and resp.get_json()['revoked_reason'] == 'manual'
    resp = kc.get('/api/v1/auth/me')
    assert resp.status_code == 401 and resp.get_json()['error'] == 'token_revoked'
    # Idempotent.
    assert auth(owner).delete(f'/api/v1/api-keys/{key.id}').status_code == 200


def test_rotate_replaces_secret(app, db, make_user, key_org, make_api_key, auth, exchange_key, key_client):
    owner = make_user(key_org, roles=['Analyst'])
    key, old = make_api_key(owner, ['incidents:read'], name='rot')
    kc = key_client(old)
    resp = auth(owner).post(f'/api/v1/api-keys/{key.id}/rotate', json={})
    assert resp.status_code == 201, resp.get_json()
    new = resp.get_json()
    assert new['name'] == 'rot' and new['rotated_from_id'] == str(key.id) and new['secret'] != old
    assert exchange_key(old).status_code == 401
    assert exchange_key(new['secret']).status_code == 200
    assert kc.get('/api/v1/auth/me').status_code == 401
    db.session.refresh(key)
    assert key.status == 'revoked' and key.revoked_reason == 'rotated'


def test_rotate_with_grace_keeps_old_key_until_grace_end(app, db, make_user, key_org, make_api_key, auth,
                                                        exchange_key):
    owner = make_user(key_org, roles=['Analyst'])
    key, old = make_api_key(owner, ['incidents:read'], name='graceful')
    resp = auth(owner).post(f'/api/v1/api-keys/{key.id}/rotate', json={'grace_minutes': 10})
    assert resp.status_code == 201
    new = resp.get_json()['secret']
    ok = exchange_key(old)
    assert ok.status_code == 200 and ok.get_json()['expires_in'] <= 10 * 60
    assert exchange_key(new).status_code == 200
    # A second rotation of the old key is refused while it is winding down.
    assert auth(owner).post(f'/api/v1/api-keys/{key.id}/rotate', json={}).status_code == 409

    db.session.refresh(key)
    key.revoked_at = _now() - timedelta(seconds=1)
    db.session.commit()
    assert exchange_key(old).status_code == 401
    assert exchange_key(new).status_code == 200


def test_owner_password_change_kills_key_token_but_key_survives(app, make_user, key_org, make_api_key,
                                                                 key_client, exchange_key, auth):
    from conftest import TEST_PASSWORD
    owner = make_user(key_org, roles=['Analyst'])
    _, full = make_api_key(owner, ['incidents:read'])
    kc = key_client(full)
    resp = auth(owner).post('/api/v1/auth/change-password', json={
        'current_password': TEST_PASSWORD, 'new_password': 'An0ther-Str0ng-Passw0rd!'})
    assert resp.status_code == 200, resp.get_json()
    assert kc.get('/api/v1/auth/me').status_code == 401
    assert exchange_key(full).status_code == 200


@pytest.mark.parametrize('reason, stored', [
    ('disabled', 'owner_disabled'), ('deleted', 'owner_deleted'), ('force_logout', 'owner_force_logout'),
    ('password_reset', 'owner_password_reset'), ('mfa_reset', 'owner_mfa_reset'),
])
def test_revocation_hook_revokes_owner_keys(app, db, make_user, key_org, make_api_key, reason, stored):
    from app.services.token_revocation import revoke_all_sessions
    owner = make_user(key_org, roles=['Analyst'])
    key, _ = make_api_key(owner, ['incidents:read'])
    revoke_all_sessions(owner, reason, notify=False)
    db.session.commit()
    db.session.refresh(key)
    assert key.status == 'revoked' and key.revoked_reason == stored


def test_password_changed_does_not_revoke_keys(app, db, make_user, key_org, make_api_key):
    from app.services.api_key_service import revoke_all_for_user
    from app.services.token_revocation import _hooks
    assert revoke_all_for_user in _hooks
    owner = make_user(key_org, roles=['Analyst'])
    key, _ = make_api_key(owner, ['incidents:read'])
    assert revoke_all_for_user(owner, 'password_changed') == 0
    assert key.status == 'active'


def test_admin_disable_user_revokes_keys(app, db, make_user, key_org, make_api_key, auth, exchange_key):
    admin = make_user(key_org, roles=['Administrator'])
    owner = make_user(key_org, roles=['Analyst'])
    key, full = make_api_key(owner, ['incidents:read'])
    resp = auth(admin).post(f'/api/v1/users/{owner.id}/disable', json={'reason': 'left the company'})
    assert resp.status_code == 200, resp.get_json()
    db.session.refresh(key)
    assert key.status == 'revoked' and key.revoked_reason == 'owner_disabled'
    assert exchange_key(full).status_code == 401


# ── Service accounts ────────────────────────────────────────────────

def _service_account(app, db, key_org, admin, auth, name='bot'):
    resp = auth(admin).post('/api/v1/service-accounts', json={'name': name, 'role_ids': [_role_id('Analyst')]})
    assert resp.status_code == 201, resp.get_json()
    return db.session.get(User, resp.get_json()['id'])


def test_service_account_cannot_login_or_refresh(app, db, make_user, key_org, auth):
    from app.api.v1.endpoints.auth import issue_tokens
    admin = make_user(key_org, roles=['Administrator'])
    sa = _service_account(app, db, key_org, admin, auth)
    assert sa.password_hash is None and sa.auth_provider == 'service'
    sa.set_password('Some-Valid-Passw0rd!')  # e.g. an admin temp-password reset
    db.session.commit()
    resp = app.test_client().post('/api/v1/auth/login', json={'email': sa.email,
                                                               'password': 'Some-Valid-Passw0rd!'})
    assert resp.status_code == 401
    assert _audit_rows(db, 'login', reason='service_account')
    _, refresh = issue_tokens(sa)
    resp = app.test_client().post('/api/v1/auth/refresh', headers={'Authorization': f'Bearer {refresh}'})
    assert resp.status_code == 401


def test_service_account_deactivation_and_delete_revoke_keys(app, db, make_user, key_org, auth, make_api_key,
                                                            exchange_key):
    admin = make_user(key_org, roles=['Administrator'])
    sa = _service_account(app, db, key_org, admin, auth)
    key, full = make_api_key(sa, ['incidents:read'], created_by=admin)
    assert exchange_key(full).status_code == 200
    ca = auth(admin)
    listed = ca.get('/api/v1/service-accounts').get_json()['items']
    assert next(s for s in listed if s['id'] == str(sa.id))['active_key_count'] == 1

    resp = ca.patch(f'/api/v1/service-accounts/{sa.id}', json={'is_active': False})
    assert resp.status_code == 200 and resp.get_json()['active_key_count'] == 0
    db.session.refresh(key)
    assert key.revoked_reason == 'owner_disabled'
    assert exchange_key(full).status_code == 401

    resp = ca.delete(f'/api/v1/service-accounts/{sa.id}')
    assert resp.status_code == 200
    assert db.session.get(User, sa.id) is not None  # soft: kept for attribution
    assert ca.patch(f'/api/v1/service-accounts/{admin.id}', json={'name': 'x'}).status_code == 404


# ── Audit ───────────────────────────────────────────────────────────

def test_audit_trail_attributes_key_and_never_holds_secrets(app, db, make_user, key_org, auth, exchange_key,
                                                           make_incident):
    owner = make_user(key_org, roles=['Analyst'])
    c = auth(owner)
    created = _create(c, name='audited', scopes=['incidents:read', 'incidents:update']).get_json()
    kid, prefix = created['id'], created['prefix']
    assert any(r.resource_id and str(r.resource_id) == kid and r.details.get('prefix') == prefix
               for r in _audit_rows(db, 'create'))

    token = exchange_key(created['secret']).get_json()['access_token']
    assert _audit_rows(db, 'api_key_exchange', api_key_id=kid, prefix=prefix)

    inc = make_incident(org=key_org, creator=owner, assign=[owner])
    resp = app.test_client().put(f'/api/v1/incidents/{inc.id}', json={'title': 'via key'},
                                 headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200, resp.get_json()
    row = next(r for r in _audit_rows(db, 'update') if r.resource_id and str(r.resource_id) == str(inc.id))
    assert row.user_id == owner.id
    assert row.details['auth_context'] == {'method': 'api_key', 'api_key_id': kid, 'api_key_prefix': prefix}

    rotated = c.post(f'/api/v1/api-keys/{kid}/rotate', json={}).get_json()
    assert _audit_rows(db, 'rotate', new_api_key_id=rotated['id'])
    c.delete(f"/api/v1/api-keys/{rotated['id']}")
    assert _audit_rows(db, 'revoke', api_key_id=rotated['id'])

    for secret in (created['secret'], rotated['secret']):
        assert _secret_in_audit(db, secret) == 0
        assert _secret_in_audit(db, secret.split('_', 2)[2]) == 0


# ── Migration ───────────────────────────────────────────────────────

def test_schema_at_head(app, db):
    cols = db.session.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='users'")).scalars().all()
    assert 'is_service_account' in cols
    idx = dict(db.session.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='api_keys'")).all())
    assert 'WHERE (revoked_at IS NULL)' in idx['uq_api_keys_owner_name_active']
    assert 'ix_api_keys_org_revoked' in idx and 'ix_api_keys_owner' in idx
    # No role grants in this migration (C13): the catalog grants came from W0.
    perms = dict(db.session.execute(text(
        "SELECT name, permissions FROM roles WHERE is_system AND organization_id IS NULL")).all())
    assert 'api_keys:own' in perms['Analyst'] and 'api_keys:own' not in perms['Viewer']
    assert 'api_keys:manage' in perms['Administrator']


def test_migration_round_trip_with_data(scratch_db):
    import uuid
    from sqlalchemy import create_engine
    from test_migrations import EXPECTED_HEAD, _current, _flask_db

    r = _flask_db(scratch_db, 'upgrade')
    assert r.returncode == 0, r.stderr[-3000:]
    eng = create_engine(scratch_db)
    try:
        with eng.begin() as conn:
            org = conn.execute(text("INSERT INTO organizations (name, slug, settings, created_at) "
                                    "VALUES ('o', 'mig-keys', '{}', now()) RETURNING id")).scalar()
            uid = conn.execute(text("INSERT INTO users (id, email, name, organization_id, is_service_account) "
                                    "VALUES (:i, 'svc@service.invalid', 'svc', :o, true) RETURNING id"),
                               {'i': uuid.uuid4(), 'o': org}).scalar()
            conn.execute(text(
                "INSERT INTO api_keys (id, organization_id, owner_user_id, name, prefix, key_hash, scopes, "
                "expires_at, created_at) VALUES (:i, :o, :u, 'k', 'ssk_aaaaaaaaaaaa', :h, '[\"incidents:read\"]', "
                "now() + interval '1 day', now())"), {'i': uuid.uuid4(), 'o': org, 'u': uid, 'h': '0' * 64})
            with pytest.raises(Exception):
                with conn.begin_nested():
                    conn.execute(text(
                        "INSERT INTO api_keys (id, organization_id, owner_user_id, name, prefix, key_hash, "
                        "expires_at, created_at) VALUES (:i, :o, :u, 'K', 'ssk_bbbbbbbbbbbb', :h, "
                        "now() + interval '1 day', now())"), {'i': uuid.uuid4(), 'o': org, 'u': uid, 'h': '0' * 64})
    finally:
        eng.dispose()

    r = _flask_db(scratch_db, 'downgrade', 'evidence_register_ledger')
    assert r.returncode == 0, r.stderr[-3000:]
    eng = create_engine(scratch_db)
    try:
        with eng.connect() as conn:
            assert not conn.execute(text("SELECT to_regclass('api_keys')")).scalar()
            cols = conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users'")).scalars().all()
            assert 'is_service_account' not in cols
    finally:
        eng.dispose()

    r = _flask_db(scratch_db, 'upgrade')
    assert r.returncode == 0, r.stderr[-3000:]
    assert _current(scratch_db) == EXPECTED_HEAD


from test_migrations import scratch_db  # noqa: E402,F401  (fixture reuse)
