"""User lifecycle (W1-LIFE-BE): invites, account state actions, admin resets,
restricted sessions, revocation, safe delete, bulk actions, activity, stats.

Everything mutating runs in throwaway orgs (rbac_helpers.new_org). Generated
secrets (invite tokens, reset links, temp passwords) stay inside the test:
assertions on them compare precomputed booleans so a failure never prints one.
"""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from conftest import TEST_PASSWORD
from rbac_helpers import last_audit, make_role, make_user, new_org, security_events  # noqa: F401

NEW_PASSWORD = 'N3w-Str0ng-Passw0rd!'


def _role(name):
    from app.models import Role
    return Role.query.filter(Role.organization_id.is_(None), Role.name == name).one()


def _login(app, email, password=TEST_PASSWORD, **extra):
    return app.test_client().post('/api/v1/auth/login', json={'email': email, 'password': password, **extra})


def _bearer(token):
    return {'Authorization': f'Bearer {token}'}


def _fresh(db, model, pk):
    db.session.expire_all()
    return db.session.get(model, pk)


@pytest.fixture
def org_admin(new_org, make_user):
    """(org, admin) in a fresh org; a second admin keeps last-admin guards quiet."""
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    make_user(org, roles=['Administrator'])
    return org, admin


@pytest.fixture
def revocations(monkeypatch):
    """Record realtime calls made by token_revocation: [(kind, uid, event, payload)]."""
    from app.services import realtime
    calls = []
    monkeypatch.setattr(realtime, 'emit_to_user',
                        lambda uid, event, payload: calls.append(('emit', str(uid), event, payload)) or True)
    monkeypatch.setattr(realtime, 'disconnect_user_sockets',
                        lambda uid: calls.append(('disconnect', str(uid), None, None)) or 0)
    return calls


@pytest.fixture
def redis_down(monkeypatch, redis_client):
    def boom(*_a, **_k):
        raise ConnectionError('redis down')
    monkeypatch.setattr(redis_client, 'incr', boom)


# ── Invites ─────────────────────────────────────────────────────────

def _invite(client, **body):
    body.setdefault('email', f'inv-{uuid.uuid4().hex[:10]}@lc.test')
    return client.post('/api/v1/users/invites', json=body)


def test_invite_create_returns_token_once_and_stores_hash(app, db, auth, org_admin):
    from app.models import UserInvite
    _, admin = org_admin
    client = auth(admin)
    resp = _invite(client, name='Ann', expires_in_days=3)
    assert resp.status_code == 201
    body = resp.get_json()
    token = body['token']
    inv = db.session.get(UserInvite, uuid.UUID(body['invite']['id']))
    assert (inv.token_hash == hashlib.sha256(token.encode()).hexdigest()) is True
    assert body['accept_path'].startswith('/auth/invite#token=')
    assert body['invite']['status'] == 'pending' and body['invite']['email'] == inv.email

    listing = client.get('/api/v1/users/invites').get_json()
    blob = json.dumps(listing)
    assert listing['total'] == 1
    leaked = token in blob or 'token_hash' in blob or inv.token_hash in blob
    assert leaked is False
    row = last_audit(db, 'create_invite', 'user_invite')
    assert str(row.resource_id) == body['id']
    assert (token in json.dumps(row.to_dict(), default=str)) is False


def test_invite_requires_users_manage(app, auth, users):
    for name in ('Analyst', 'Viewer'):
        assert _invite(auth(users[name])).status_code == 403


def test_invite_with_roles_requires_roles_manage_and_no_escalation(app, auth, new_org, make_user):
    org = new_org()
    make_user(org, roles=['Administrator'])
    only_users = make_user(org, perms=['users:manage', 'users:read'])
    resp = _invite(auth(only_users), role_ids=[str(_role('Analyst').id)])
    assert resp.status_code == 403
    deputy = make_user(org, perms=['users:manage', 'users:read', 'roles:manage'])
    resp = _invite(auth(deputy), role_ids=[str(_role('Administrator').id)])
    assert resp.status_code == 403 and resp.get_json()['error'] == 'privilege_escalation'


def test_invite_rejects_foreign_team_ids(app, db, auth, org_admin, org_b):
    from app.models import Team
    _, admin = org_admin
    team = Team(name=f't-{uuid.uuid4().hex[:6]}', organization_id=org_b.id)
    db.session.add(team)
    db.session.commit()
    resp = _invite(auth(admin), team_ids=[str(team.id)])
    assert resp.status_code == 400 and resp.get_json()['error'] == 'invalid_team'


def test_invite_existing_member_conflict_and_other_org_not_revealed(app, auth, org_admin, users):
    org, admin = org_admin
    client = auth(admin)
    resp = _invite(client, email=admin.email.upper())
    assert resp.status_code == 409 and resp.get_json()['error'] == 'already_member'
    assert _invite(client, email=users['Analyst'].email).status_code == 201


def test_invite_expiry_bounds_and_db_check(app, db, auth, org_admin):
    from sqlalchemy.exc import IntegrityError
    from app.models import UserInvite
    org, admin = org_admin
    client = auth(admin)
    for days in (0, 8, '3', True):
        assert _invite(client, expires_in_days=days).status_code == 400
    now = datetime.now(timezone.utc)
    db.session.add(UserInvite(organization_id=org.id, email='late@lc.test', token_hash='a' * 64,
                              created_at=now, expires_at=now + timedelta(days=8)))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_reinvite_supersedes_previous(app, auth, org_admin):
    _, admin = org_admin
    client = auth(admin)
    first = _invite(client, email='again@lc.test').get_json()
    second = _invite(client, email='again@lc.test').get_json()
    assert second['superseded_invite_id'] == first['invite']['id']
    anon = app.test_client()
    resp = anon.post('/api/v1/auth/invites/lookup', json={'token': first['token']})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'invite_invalid'
    assert anon.post('/api/v1/auth/invites/lookup', json={'token': second['token']}).status_code == 200


def test_lookup_invite_returns_org_and_email(app, auth, org_admin):
    org, admin = org_admin
    body = _invite(auth(admin), email='look@lc.test', name='Look').get_json()
    resp = app.test_client().post('/api/v1/auth/invites/lookup', json={'token': body['token']})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data['email'] == 'look@lc.test' and data['name'] == 'Look' and data['organization_name'] == org.name


def test_accept_invite_creates_user_with_roles_teams_and_logs_in(app, db, auth, org_admin):
    from app.models import Team, User, UserInvite, UserRole
    org, admin = org_admin
    team = Team(name=f't-{uuid.uuid4().hex[:6]}', organization_id=org.id)
    db.session.add(team)
    db.session.commit()
    body = _invite(auth(admin), email='Joiner@LC.test', role_ids=[str(_role('Analyst').id)],
                   team_ids=[str(team.id)], organizational_role='DFIR').get_json()
    resp = app.test_client().post('/api/v1/auth/invites/accept',
                                  json={'token': body['token'], 'name': 'Joiner', 'password': NEW_PASSWORD})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['access_token'] and data['user']['email'] == 'joiner@lc.test'
    cookies = resp.headers.getlist('Set-Cookie')
    assert any(c.startswith('access_token_cookie=') for c in cookies)
    user = User.query.filter_by(email='joiner@lc.test').one()
    assert user.organization_id == org.id and user.role_names == ['Analyst']
    assert [t['id'] for t in user.teams] == [str(team.id)] and user.organizational_role == 'DFIR'
    assert UserRole.query.filter_by(user_id=user.id).one().granted_by == admin.id
    inv = db.session.get(UserInvite, uuid.UUID(body['invite']['id']))
    assert inv.accepted_at is not None and inv.accepted_user_id == user.id
    assert app.test_client().get('/api/v1/auth/me', headers=_bearer(data['access_token'])).status_code == 200
    assert _login(app, 'joiner@lc.test', NEW_PASSWORD).status_code == 200


def test_accept_invite_without_roles_gets_viewer(app, auth, org_admin):
    from app.models import User
    _, admin = org_admin
    body = _invite(auth(admin), email='plain@lc.test').get_json()
    app.test_client().post('/api/v1/auth/invites/accept',
                           json={'token': body['token'], 'name': 'P', 'password': NEW_PASSWORD})
    assert User.query.filter_by(email='plain@lc.test').one().role_names == ['Viewer']


def test_accept_invite_single_use(app, auth, org_admin):
    _, admin = org_admin
    body = _invite(auth(admin)).get_json()
    payload = {'token': body['token'], 'name': 'Once', 'password': NEW_PASSWORD}
    assert app.test_client().post('/api/v1/auth/invites/accept', json=payload).status_code == 201
    resp = app.test_client().post('/api/v1/auth/invites/accept', json=payload)
    assert resp.status_code == 400 and resp.get_json()['error'] == 'invite_invalid'


def test_accept_invite_expired_revoked_unknown_same_error(app, db, auth, org_admin):
    from app.models import UserInvite
    _, admin = org_admin
    client = auth(admin)
    expired = _invite(client).get_json()
    inv = db.session.get(UserInvite, uuid.UUID(expired['invite']['id']))
    inv.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.session.commit()
    revoked = _invite(client).get_json()
    assert client.delete(f"/api/v1/users/invites/{revoked['invite']['id']}").status_code == 200
    bodies = []
    for token in (expired['token'], revoked['token'], 'not-a-real-token'):
        resp = app.test_client().post('/api/v1/auth/invites/accept',
                                      json={'token': token, 'name': 'X', 'password': NEW_PASSWORD})
        assert resp.status_code == 400
        bodies.append(resp.get_json())
    assert bodies[0] == bodies[1] == bodies[2]


def test_accept_invite_enforces_password_policy(app, auth, org_admin):
    _, admin = org_admin
    body = _invite(auth(admin)).get_json()
    resp = app.test_client().post('/api/v1/auth/invites/accept',
                                  json={'token': body['token'], 'name': 'W', 'password': 'short'})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'bad_request'
    # The invite is still usable.
    resp = app.test_client().post('/api/v1/auth/invites/accept',
                                  json={'token': body['token'], 'name': 'W', 'password': NEW_PASSWORD})
    assert resp.status_code == 201


def test_accept_invite_fails_if_inviter_lost_rights(app, db, auth, org_admin, make_user):
    org, admin = org_admin
    inviter = make_user(org, roles=['Administrator'])
    body = _invite(auth(inviter), role_ids=[str(_role('Analyst').id)]).get_json()
    assert auth(admin).post(f'/api/v1/users/{inviter.id}/disable', json={'reason': 'left'}).status_code == 200
    resp = app.test_client().post('/api/v1/auth/invites/accept',
                                  json={'token': body['token'], 'name': 'Late', 'password': NEW_PASSWORD})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'invite_invalid'


def test_accept_invite_email_taken_generic_error(app, auth, org_admin, users):
    _, admin = org_admin
    body = _invite(auth(admin), email=users['Viewer'].email).get_json()  # a user of org A
    resp = app.test_client().post('/api/v1/auth/invites/accept',
                                  json={'token': body['token'], 'name': 'Dup', 'password': NEW_PASSWORD})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'invite_invalid'


def test_revoke_invite_cross_org_404_and_accepted_409(app, auth, org_admin, users):
    _, admin = org_admin
    body = _invite(auth(admin)).get_json()
    assert auth(users['admin_b']).delete(f"/api/v1/users/invites/{body['invite']['id']}").status_code == 404
    app.test_client().post('/api/v1/auth/invites/accept',
                           json={'token': body['token'], 'name': 'A', 'password': NEW_PASSWORD})
    resp = auth(admin).delete(f"/api/v1/users/invites/{body['invite']['id']}")
    assert resp.status_code == 409 and resp.get_json()['error'] == 'already_accepted'


def test_list_invites_status_filter(app, auth, org_admin):
    _, admin = org_admin
    client = auth(admin)
    keep = _invite(client).get_json()
    gone = _invite(client).get_json()
    client.delete(f"/api/v1/users/invites/{gone['invite']['id']}")
    pending = client.get('/api/v1/users/invites').get_json()
    assert [i['id'] for i in pending['items']] == [keep['invite']['id']]
    revoked = client.get('/api/v1/users/invites?status=revoked').get_json()
    assert [i['id'] for i in revoked['items']] == [gone['invite']['id']]
    assert client.get('/api/v1/users/invites?status=all').get_json()['total'] == 2
    assert client.get('/api/v1/users/invites?status=bogus').status_code == 400


# ── Disable / enable / force logout / unlock ───────────────────────

def test_disable_requires_reason_sets_columns_and_revokes(app, db, auth, org_admin, make_user, revocations):
    from app.models import User
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    victim_client = auth(victim)
    assert victim_client.get('/api/v1/auth/me').status_code == 200
    client = auth(admin)
    assert client.post(f'/api/v1/users/{victim.id}/disable', json={}).status_code == 400
    assert client.post(f'/api/v1/users/{victim.id}/disable', json={'reason': 'x' * 501}).status_code == 400
    resp = client.post(f'/api/v1/users/{victim.id}/disable', json={'reason': 'compromised laptop'})
    assert resp.status_code == 200
    data = resp.get_json()['user']
    assert data['is_active'] is False and data['deactivation_reason'] == 'compromised laptop'
    assert data['deactivated_by']['id'] == str(admin.id) and data['deactivated_at']
    u = _fresh(db, User, victim.id)
    assert u.deactivated_by == admin.id and u.deactivated_at is not None
    assert victim_client.get('/api/v1/auth/me').status_code == 401
    assert ('emit', str(victim.id), 'session:revoked', {'reason': 'disabled'}) in revocations
    assert ('disconnect', str(victim.id), None, None) in revocations
    row = last_audit(db, 'disable_user', 'user')
    assert row.details['changes']['is_active'] == {'from': True, 'to': False}
    again = client.post(f'/api/v1/users/{victim.id}/disable', json={'reason': 'again'})
    assert again.status_code == 409 and again.get_json()['error'] == 'already_disabled'


def test_disable_self_forbidden(app, auth, org_admin):
    _, admin = org_admin
    resp = auth(admin).post(f'/api/v1/users/{admin.id}/disable', json={'reason': 'me'})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'self_action'


def test_disable_more_privileged_target_forbidden(app, auth, org_admin, make_user):
    org, admin = org_admin
    deputy = make_user(org, perms=['users:manage', 'users:read'])
    resp = auth(deputy).post(f'/api/v1/users/{admin.id}/disable', json={'reason': 'coup'})
    assert resp.status_code == 403 and resp.get_json()['error'] == 'insufficient_privilege'


def test_disable_cross_org_404(app, auth, org_admin, users):
    _, admin = org_admin
    assert auth(admin).post(f"/api/v1/users/{users['Analyst'].id}/disable",
                            json={'reason': 'x'}).status_code == 404


def test_enable_does_not_restore_old_tokens(app, db, auth, org_admin, make_user):
    from app.models import User
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    old = auth(victim)
    client = auth(admin)
    client.post(f'/api/v1/users/{victim.id}/disable', json={'reason': 'r'})
    resp = client.post(f'/api/v1/users/{victim.id}/enable')
    assert resp.status_code == 200 and resp.get_json()['user']['is_active'] is True
    u = _fresh(db, User, victim.id)
    assert u.deactivated_at is None and u.deactivated_by is None and u.deactivation_reason is None
    assert old.get('/api/v1/auth/me').status_code == 401
    assert auth(_fresh(db, User, victim.id)).get('/api/v1/auth/me').status_code == 200


def test_force_logout_bumps_epoch_and_emits_session_revoked(app, auth, org_admin, make_user, revocations):
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    old = auth(victim)
    resp = auth(admin).post(f'/api/v1/users/{victim.id}/force-logout')
    assert resp.status_code == 200
    assert old.get('/api/v1/auth/me').status_code == 401
    assert ('emit', str(victim.id), 'session:revoked', {'reason': 'force_logout'}) in revocations


def test_force_logout_disconnects_live_socket(app, auth, org_admin, make_user):
    from app import socketio
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    sock = socketio.test_client(app, auth={'token': auth(victim).access_token})
    assert sock.is_connected()
    assert auth(admin).post(f'/api/v1/users/{victim.id}/force-logout').status_code == 200
    assert not sock.is_connected()


def test_force_logout_fails_closed_when_redis_down(app, db, auth, org_admin, make_user, redis_down):
    from app.models import User
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    client = auth(admin)
    resp = client.post(f'/api/v1/users/{victim.id}/force-logout')
    assert resp.status_code == 503 and resp.get_json()['error'] == 'revocation_failed'
    resp = client.post(f'/api/v1/users/{victim.id}/disable', json={'reason': 'r'})
    assert resp.status_code == 503
    assert _fresh(db, User, victim.id).is_active is True


def test_unlock_clears_lock(app, db, auth, org_admin, make_user):
    from app.models import User
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    victim.failed_login_count = 9
    victim.locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.session.commit()
    resp = auth(admin).post(f'/api/v1/users/{victim.id}/unlock')
    assert resp.status_code == 200 and resp.get_json()['user']['is_locked'] is False
    u = _fresh(db, User, victim.id)
    assert u.failed_login_count == 0 and u.locked_until is None
    assert _login(app, victim.email).status_code == 200


def test_put_is_active_routes_through_lifecycle(app, db, auth, org_admin, make_user):
    from app.models import User
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    assert auth(admin).put(f'/api/v1/users/{victim.id}', json={'is_active': False}).status_code == 200
    u = _fresh(db, User, victim.id)
    assert u.is_active is False and u.deactivated_by == admin.id and u.deactivation_reason == '(via update)'
    row = last_audit(db, 'update_user', 'user')
    assert row.details['changes']['is_active'] == {'from': True, 'to': False}
    assert auth(admin).put(f'/api/v1/users/{victim.id}', json={'is_active': True}).status_code == 200
    assert _fresh(db, User, victim.id).deactivated_at is None


def test_put_password_fails_closed_when_redis_down(app, db, auth, org_admin, make_user, redis_down):
    from app.models import User
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    resp = auth(admin).put(f'/api/v1/users/{victim.id}', json={'password': NEW_PASSWORD})
    assert resp.status_code == 503
    assert _fresh(db, User, victim.id).check_password(TEST_PASSWORD)


def test_revocation_hooks_receive_reason(app, auth, org_admin, make_user, monkeypatch):
    from app.services import token_revocation
    seen = []
    monkeypatch.setattr(token_revocation, '_hooks', [lambda user, reason: seen.append((user.id, reason))])
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    auth(admin).post(f'/api/v1/users/{victim.id}/force-logout')
    assert seen == [(victim.id, 'force_logout')]


def test_failing_revocation_hook_fails_closed(app, db, auth, org_admin, make_user, monkeypatch):
    from app.models import User
    from app.services import token_revocation

    def broken(user, reason):
        raise RuntimeError('hook down')
    monkeypatch.setattr(token_revocation, '_hooks', [broken])
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    resp = auth(admin).post(f'/api/v1/users/{victim.id}/disable', json={'reason': 'r'})
    assert resp.status_code == 503
    assert _fresh(db, User, victim.id).is_active is True


# ── Admin password / MFA resets + restricted sessions ───────────────

def test_reset_password_temp_sets_must_change_and_gate_blocks_routes(app, db, auth, org_admin, make_user):
    from app.models import User
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    old = auth(victim)
    resp = auth(admin).post(f'/api/v1/users/{victim.id}/reset-password', json={'mode': 'temp'})
    assert resp.status_code == 200
    temp = resp.get_json()['temp_password']
    assert old.get('/api/v1/auth/me').status_code == 401
    assert _login(app, victim.email).status_code == 401

    login = _login(app, victim.email, temp)
    assert login.status_code == 200
    body = login.get_json()
    assert body['user']['must_change_password'] is True
    client = app.test_client()
    h = _bearer(body['access_token'])
    blocked = client.get('/api/v1/incidents', headers=h)
    assert blocked.status_code == 403 and blocked.get_json()['error'] == 'password_change_required'
    assert client.get('/api/v1/auth/me', headers=h).status_code == 200
    same = client.post('/api/v1/auth/change-password', headers=h,
                       json={'current_password': temp, 'new_password': temp})
    assert same.status_code == 400
    changed = client.post('/api/v1/auth/change-password', headers=h,
                          json={'current_password': temp, 'new_password': NEW_PASSWORD})
    assert changed.status_code == 200
    h2 = _bearer(changed.get_json()['access_token'])
    assert client.get('/api/v1/incidents', headers=h2).status_code == 200
    assert _fresh(db, User, victim.id).must_change_password is False


def test_restricted_allowlist_endpoints(app, db, auth, org_admin, make_user):
    from app.models import User
    org, _ = org_admin
    u = make_user(org, roles=['Analyst'])
    u.must_change_password = True
    db.session.commit()
    client = auth(u)
    assert client.get('/api/v1/auth/me').status_code == 200
    assert client.get('/api/v1/health').status_code != 403  # 200, or 503 when Redis is degraded
    assert client.get('/api/v1/users').get_json()['error'] == 'password_change_required'
    assert client.patch('/api/v1/auth/me/preferences', json={'display_timezone': 'utc'}).status_code == 403
    refresh = app.test_client().post('/api/v1/auth/refresh', headers=_bearer(client.refresh_token))
    assert refresh.status_code == 200
    assert client.post('/api/v1/auth/logout').status_code == 200
    assert _fresh(db, User, u.id).must_change_password is True


def test_restricted_user_socket_is_anonymous(app, db, auth, org_admin, make_user):
    from app import socketio
    org, _ = org_admin
    u = make_user(org, roles=['Analyst'])
    u.must_change_password = True
    db.session.commit()
    sock = socketio.test_client(app, auth={'token': auth(u).access_token})
    events = [e for e in sock.get_received() if e['name'] == 'connected']
    assert events and events[-1]['args'][0].get('anonymous') is True


def test_reset_password_link_single_use_and_supersedes(app, db, auth, org_admin, make_user):
    from app.models import User
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    old = auth(victim)
    client = auth(admin)
    first = client.post(f'/api/v1/users/{victim.id}/reset-password', json={'mode': 'link'}).get_json()
    second = client.post(f'/api/v1/users/{victim.id}/reset-password', json={'mode': 'link'}).get_json()
    assert second['accept_path'].startswith('/auth/reset-password#token=') and second['expires_at']
    assert old.get('/api/v1/auth/me').status_code == 401  # revoke_sessions defaults to true
    anon = app.test_client()
    url = '/api/v1/auth/password-reset/complete'
    stale = anon.post(url, json={'token': first['token'], 'new_password': NEW_PASSWORD})
    assert stale.status_code == 400 and stale.get_json()['error'] == 'reset_invalid'
    assert anon.post(url, json={'token': second['token'], 'new_password': NEW_PASSWORD}).status_code == 200
    assert anon.post(url, json={'token': second['token'], 'new_password': NEW_PASSWORD}).status_code == 400
    assert _fresh(db, User, victim.id).check_password(NEW_PASSWORD)
    assert _login(app, victim.email, NEW_PASSWORD).status_code == 200


def test_reset_link_without_session_revoke(app, auth, org_admin, make_user):
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    live = auth(victim)
    resp = auth(admin).post(f'/api/v1/users/{victim.id}/reset-password',
                            json={'mode': 'link', 'revoke_sessions': False})
    assert resp.status_code == 200
    assert live.get('/api/v1/auth/me').status_code == 200


def test_reset_password_complete_policy_and_inactive_user(app, db, auth, org_admin, make_user):
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    link = auth(admin).post(f'/api/v1/users/{victim.id}/reset-password', json={'mode': 'link'}).get_json()
    url = '/api/v1/auth/password-reset/complete'
    weak = app.test_client().post(url, json={'token': link['token'], 'new_password': 'weak'})
    assert weak.status_code == 400 and weak.get_json()['error'] == 'bad_request'
    victim.is_active = False  # disabled behind the link's back (the API also kills the link)
    db.session.commit()
    resp = app.test_client().post(url, json={'token': link['token'], 'new_password': NEW_PASSWORD})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'reset_invalid'


def test_reset_password_self_and_bad_mode(app, auth, org_admin, make_user):
    org, admin = org_admin
    client = auth(admin)
    resp = client.post(f'/api/v1/users/{admin.id}/reset-password', json={'mode': 'temp'})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'use_change_password'
    other = make_user(org, roles=['Analyst'])
    assert client.post(f'/api/v1/users/{other.id}/reset-password', json={'mode': 'sms'}).status_code == 400


def test_reset_mfa_clears_secret_and_backup_codes_and_revokes(app, db, auth, org_admin, make_user, revocations):
    import pyotp
    from app.models import User
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    victim.mfa_enabled, victim.mfa_secret, victim.mfa_backup_codes = True, pyotp.random_base32(), 'AAAA1111'
    db.session.commit()
    resp = auth(admin).post(f'/api/v1/users/{victim.id}/reset-mfa')
    assert resp.status_code == 200 and resp.get_json()['user']['mfa_enabled'] is False
    u = _fresh(db, User, victim.id)
    assert u.mfa_secret is None and u.mfa_backup_codes is None
    assert ('emit', str(victim.id), 'session:revoked', {'reason': 'mfa_reset'}) in revocations
    again = auth(admin).post(f'/api/v1/users/{victim.id}/reset-mfa')
    assert again.status_code == 409 and again.get_json()['error'] == 'mfa_not_enabled'
    me = auth(admin).post(f'/api/v1/users/{admin.id}/reset-mfa')
    assert me.status_code == 400 and me.get_json()['error'] == 'self_action'


def test_admin_reset_responses_not_in_audit_details(app, db, auth, org_admin, make_user):
    from app.models import AuditLog
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    client = auth(admin)
    temp = client.post(f'/api/v1/users/{victim.id}/reset-password', json={'mode': 'temp'}).get_json()
    link = client.post(f'/api/v1/users/{victim.id}/reset-password', json={'mode': 'link'}).get_json()
    invite = _invite(client).get_json()
    secrets_ = (temp['temp_password'], link['token'], invite['token'])
    db.session.expire_all()
    blob = json.dumps([r.to_dict() for r in AuditLog.query.filter(AuditLog.organization_id == org.id)],
                      default=str)
    leaked = any(s in blob for s in secrets_)
    assert leaked is False


# ── Delete ──────────────────────────────────────────────────────────

def test_delete_user_with_records_409_with_counts(app, db, auth, org_admin, make_user, make_incident):
    from app.models import User
    org, admin = org_admin
    author = make_user(org, roles=['Analyst'])
    make_incident(org=org, creator=author)
    resp = auth(admin).delete(f'/api/v1/users/{author.id}')
    body = resp.get_json()
    assert resp.status_code == 409 and body['error'] == 'user_has_records' and body['hint'] == 'deactivate'
    assert body['counts']['incidents'] >= 1
    assert _fresh(db, User, author.id) is not None
    anon = auth(admin).delete(f'/api/v1/users/{author.id}?anonymize=true')
    assert anon.status_code == 409


def test_delete_user_referenced_by_evidence_item_409(app, db, auth, org_admin, make_user, make_incident):
    """The evidence register's NO ACTION FKs to users (W1-EVD-CORE) are read
    from the live schema: a user referenced only by an evidence item is not
    hard-deleted."""
    from app.models import EvidenceItem, User
    org, admin = org_admin
    holder = make_user(org, roles=['Analyst'])
    inc = make_incident(org=org, creator=admin)
    db.session.add(EvidenceItem(incident_id=inc.id, organization_id=org.id, evidence_type='disk_image',
                                title='laptop', created_by=admin.id, acquired_by_user_id=holder.id,
                                sequence_number=1))
    db.session.commit()
    resp = auth(admin).delete(f'/api/v1/users/{holder.id}')
    body = resp.get_json()
    assert resp.status_code == 409 and body['error'] == 'user_has_records'
    assert body['counts'] == {'evidence_items': 1}
    assert _fresh(db, User, holder.id) is not None


def test_delete_user_without_records_hard_deletes(app, db, auth, org_admin, make_user):
    import sqlalchemy as sa
    from app.models import AuditLog, User
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    email = victim.email
    auth(victim).patch('/api/v1/auth/me/preferences', json={'display_timezone': 'utc'})  # an audit row
    resp = auth(admin).delete(f'/api/v1/users/{victim.id}')
    assert resp.status_code == 200 and resp.get_json()['outcome'] == 'deleted'
    assert _fresh(db, User, victim.id) is None
    rows = AuditLog.query.filter_by(user_email=email, action='update_preferences').all()
    assert rows
    fk_on_audit = any(fk['referred_table'] == 'users' and fk['constrained_columns'] == ['user_id']
                      for fk in sa.inspect(db.engine).get_foreign_keys('audit_logs'))
    for row in rows:
        assert row.to_dict()['user'] is None
        # C3: once audit-governance drops the audit FKs, user_id is retained.
        assert row.user_id is None if fk_on_audit else row.user_id == victim.id
    delete_row = last_audit(db, 'delete_user', 'user')
    assert str(delete_row.resource_id) == str(victim.id)
    assert delete_row.details['changes']['email'] == {'from': email, 'to': None}


def test_delete_anonymize_scrubs_pii_keeps_row(app, db, auth, org_admin, make_user):
    from app.models import TeamMember, User, UserRole
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    resp = auth(admin).delete(f'/api/v1/users/{victim.id}?anonymize=true')
    assert resp.status_code == 200 and resp.get_json()['outcome'] == 'anonymized'
    u = _fresh(db, User, victim.id)
    assert u is not None and u.email == f'deleted+{victim.id}@invalid.local' and u.name == 'Deleted user'
    assert u.password_hash is None and u.is_active is False
    assert UserRole.query.filter_by(user_id=u.id).count() == 0
    assert TeamMember.query.filter_by(user_id=u.id).count() == 0


def test_delete_user_who_granted_roles_succeeds(app, db, auth, org_admin, make_user):
    from app.models import UserRole
    org, admin = org_admin
    granter = make_user(org, roles=['Administrator'])
    grantee = make_user(org, perms=[])
    assert auth(granter).post(f'/api/v1/users/{grantee.id}/roles',
                              json={'role_id': str(_role('Analyst').id)}).status_code == 201
    resp = auth(admin).delete(f'/api/v1/users/{granter.id}')
    assert resp.status_code == 200
    db.session.expire_all()
    assignment = UserRole.query.filter_by(user_id=grantee.id, role_id=_role('Analyst').id).one()
    assert assignment.granted_by is None


def test_delete_backstop_maps_fk_violation_to_409(app, db, auth, org_admin, make_user, make_incident,
                                                   monkeypatch):
    from app.models import User
    from app.services import user_lifecycle
    org, admin = org_admin
    author = make_user(org, roles=['Analyst'])
    make_incident(org=org, creator=author)
    monkeypatch.setattr(user_lifecycle, 'user_reference_counts', lambda uid: {})
    resp = auth(admin).delete(f'/api/v1/users/{author.id}')
    assert resp.status_code == 409 and resp.get_json() == {
        'error': 'user_has_records', 'counts': {}, 'hint': 'deactivate',
        'message': resp.get_json()['message']}
    assert _fresh(db, User, author.id) is not None


def test_reference_counts_cover_no_action_fks(app, db, org_admin, make_user, make_incident):
    from app.services.user_lifecycle import _attribution_columns, user_reference_counts
    org, _ = org_admin
    u = make_user(org, roles=['Analyst'])
    cols = set(_attribution_columns())
    assert ('incidents', 'created_by') in cols and ('timeline_events', 'created_by') in cols
    assert ('user_roles', 'granted_by') not in cols and ('audit_logs', 'user_id') not in cols
    assert ('incident_assignments', 'user_id') in cols
    assert user_reference_counts(u.id) == {}
    make_incident(org=org, creator=u, assign=[u])
    counts = user_reference_counts(u.id)
    assert counts['incidents'] >= 1 and counts['incident_assignments'] >= 1


# ── Bulk ────────────────────────────────────────────────────────────

def test_bulk_mixed_results_and_audit_rows(app, db, auth, org_admin, make_user, users):
    from app.models import AuditLog
    org, admin = org_admin
    ok_user = make_user(org, roles=['Analyst'])
    ids = [str(ok_user.id), str(admin.id), str(users['admin_b'].id)]
    resp = auth(admin).post('/api/v1/users/bulk', json={'action': 'disable', 'user_ids': ids, 'reason': 'sweep'})
    assert resp.status_code == 200
    body = resp.get_json()
    by_id = {r['user_id']: r for r in body['results']}
    assert by_id[ids[0]]['status'] == 'ok'
    assert by_id[ids[1]]['status'] == 'skipped' and by_id[ids[1]]['code'] == 'self_action'
    assert by_id[ids[2]]['status'] == 'error' and by_id[ids[2]]['code'] == 'not_found'
    assert body['summary'] == {'ok': 1, 'skipped': 1, 'failed': 1}
    db.session.expire_all()
    rows = AuditLog.query.filter(AuditLog.action == 'bulk_disable',
                                 AuditLog.details['bulk_request_id'].astext == body['bulk_request_id']).all()
    assert len(rows) == 3
    assert {str(r.resource_id) for r in rows} == set(ids)
    assert users['admin_b'].is_active  # untouched


def test_bulk_role_actions_need_roles_manage(app, auth, new_org, make_user):
    org = new_org()
    make_user(org, roles=['Administrator'])
    deputy = make_user(org, perms=['users:manage', 'users:read'])
    target = make_user(org, perms=[])
    resp = auth(deputy).post('/api/v1/users/bulk', json={'action': 'add_role', 'user_ids': [str(target.id)],
                                                         'role_id': str(_role('Viewer').id)})
    assert resp.status_code == 403


def test_bulk_add_and_remove_role(app, db, auth, org_admin, make_user, monkeypatch):
    from app.models import User
    from app.services import realtime
    changed = []
    monkeypatch.setattr(realtime, 'notify_permissions_changed', lambda ids: changed.extend(ids))
    org, admin = org_admin
    a, b = make_user(org, perms=[]), make_user(org, perms=[])
    client = auth(admin)
    body = {'action': 'add_role', 'user_ids': [str(a.id), str(b.id)], 'role_id': str(_role('Analyst').id)}
    assert client.post('/api/v1/users/bulk', json=body).get_json()['summary']['ok'] == 2
    assert 'Analyst' in _fresh(db, User, a.id).role_names
    assert set(changed) == {str(a.id), str(b.id)}
    again = client.post('/api/v1/users/bulk', json=body).get_json()
    assert again['summary']['skipped'] == 2 and again['results'][0]['code'] == 'already_assigned'
    body['action'] = 'remove_role'
    assert client.post('/api/v1/users/bulk', json=body).get_json()['summary']['ok'] == 2
    assert 'Analyst' not in _fresh(db, User, b.id).role_names


def test_bulk_add_team_and_force_logout(app, db, auth, org_admin, make_user):
    from app.models import Team, TeamMember
    org, admin = org_admin
    team = Team(name=f't-{uuid.uuid4().hex[:6]}', organization_id=org.id)
    db.session.add(team)
    db.session.commit()
    u = make_user(org, roles=['Analyst'])
    client = auth(admin)
    resp = client.post('/api/v1/users/bulk', json={'action': 'add_team', 'user_ids': [str(u.id)],
                                                   'team_id': str(team.id)})
    assert resp.get_json()['summary']['ok'] == 1
    assert TeamMember.query.filter_by(team_id=team.id, user_id=u.id).count() == 1
    live = auth(u)
    resp = client.post('/api/v1/users/bulk', json={'action': 'force_logout', 'user_ids': [str(u.id)]})
    assert resp.get_json()['summary']['ok'] == 1
    assert live.get('/api/v1/auth/me').status_code == 401


def test_bulk_shape_validation(app, auth, org_admin):
    _, admin = org_admin
    client = auth(admin)
    ids = [str(uuid.uuid4()) for _ in range(101)]
    assert client.post('/api/v1/users/bulk', json={'action': 'enable', 'user_ids': ids}).status_code == 400
    dup = [ids[0], ids[0]]
    assert client.post('/api/v1/users/bulk', json={'action': 'enable', 'user_ids': dup}).status_code == 400
    assert client.post('/api/v1/users/bulk', json={'action': 'explode', 'user_ids': ids[:1]}).status_code == 400
    assert client.post('/api/v1/users/bulk', json={'action': 'disable', 'user_ids': ids[:1]}).status_code == 400
    assert client.post('/api/v1/users/bulk', json={'action': 'enable', 'user_ids': ['x']}).status_code == 400


# ── Activity / stats / list / get / create ──────────────────────────

def test_user_activity_scopes(app, db, auth, org_admin, make_user, users):
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    auth(victim).patch('/api/v1/auth/me/preferences', json={'display_timezone': 'utc'})
    auth(admin).post(f'/api/v1/users/{victim.id}/unlock')
    client = auth(admin)
    actor = client.get(f'/api/v1/users/{victim.id}/activity?scope=actor').get_json()
    assert {i['action'] for i in actor['items']} == {'update_preferences'}
    target = client.get(f'/api/v1/users/{victim.id}/activity?scope=target').get_json()
    assert 'unlock_user' in {i['action'] for i in target['items']}
    assert 'update_preferences' in {i['action'] for i in target['items']}  # resource_type user = self
    every = client.get(f'/api/v1/users/{victim.id}/activity').get_json()
    assert every['scope'] == 'all' and every['total'] >= 2
    assert client.get(f"/api/v1/users/{users['admin_b'].id}/activity").status_code == 404
    assert client.get(f'/api/v1/users/{victim.id}/activity?scope=x').status_code == 400
    analyst = make_user(org, roles=['Analyst'])
    assert auth(analyst).get(f'/api/v1/users/{victim.id}/activity').status_code == 403
    # Built on audit_service.build_audit_query: its filters and deep-page cap apply.
    filtered = client.get(f'/api/v1/users/{victim.id}/activity?scope=target&action=unlock_user').get_json()
    assert {i['action'] for i in filtered['items']} == {'unlock_user'}
    bad = client.get(f'/api/v1/users/{victim.id}/activity?event_type=bogus')
    assert bad.status_code == 400 and bad.get_json()['error'] == 'invalid_filter'
    deep = client.get(f'/api/v1/users/{victim.id}/activity?page=1001&per_page=100')
    assert deep.status_code == 400 and deep.get_json()['error'] == 'invalid_filter'


def test_user_stats_and_overview_counts(app, db, auth, org_admin, make_user):
    from app.services.user_lifecycle import overview_counts
    org, admin = org_admin
    locked = make_user(org, roles=['Analyst'])
    locked.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    make_user(org, roles=['Viewer'], active=False)
    db.session.commit()
    _invite(auth(admin))
    stats = auth(admin).get('/api/v1/users/stats').get_json()
    assert stats['total'] == 4 and stats['active'] == 3 and stats['disabled'] == 1
    assert stats['locked'] == 1 and stats['pending_invites'] == 1
    assert stats['by_role']['Administrator'] == 2
    assert overview_counts(org.id) == {'locked': 1, 'pending_invites': 1}
    overview = auth(admin).get('/api/v1/admin/overview').get_json()['users']
    assert overview['locked'] == 1 and overview['pending_invites'] == 1


def test_users_list_lifecycle_filters(app, db, auth, org_admin, make_user):
    from app.models import Team, TeamMember
    org, admin = org_admin
    locked = make_user(org, roles=['Analyst'])
    locked.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    must = make_user(org, roles=['Analyst'])
    must.must_change_password = True
    mfa = make_user(org, roles=['Viewer'])
    mfa.mfa_enabled = True
    off = make_user(org, roles=['Viewer'], active=False)
    team = Team(name=f't-{uuid.uuid4().hex[:6]}', organization_id=org.id)
    db.session.add(team)
    db.session.flush()
    db.session.add(TeamMember(team_id=team.id, user_id=mfa.id))
    db.session.commit()
    client = auth(admin)

    def ids(qs):
        resp = client.get(f'/api/v1/users?{qs}')
        assert resp.status_code == 200, qs
        return {i['id'] for i in resp.get_json()['items']}
    assert ids('status=locked') == {str(locked.id)}
    assert ids('status=must_change_password') == {str(must.id)}
    assert ids('status=disabled') == {str(off.id)}
    assert str(off.id) not in ids('status=active')
    assert ids('mfa=true') == {str(mfa.id)}
    assert ids(f'team_id={team.id}') == {str(mfa.id)}
    assert ids(f"role_id={_role('Viewer').id}") == {str(mfa.id), str(off.id)}
    assert ids('q=%25') == set()  # an escaped % does not match everything
    assert client.get('/api/v1/users?status=bogus').status_code == 400
    assert client.get('/api/v1/users?team_id=nope').status_code == 400


def test_get_user_admin_fields_only_for_managers(app, db, auth, org_admin, make_user):
    org, admin = org_admin
    victim = make_user(org, roles=['Analyst'])
    auth(admin).post(f'/api/v1/users/{victim.id}/disable', json={'reason': 'r'})
    full = auth(admin).get(f'/api/v1/users/{victim.id}').get_json()
    assert full['deactivation_reason'] == 'r' and 'failed_login_count' in full
    reader = make_user(org, perms=['users:read'])
    plain = auth(reader).get(f'/api/v1/users/{victim.id}').get_json()
    assert 'deactivation_reason' not in plain and plain['is_active'] is False


def test_create_user_lowercases_email(app, auth, org_admin):
    _, admin = org_admin
    client = auth(admin)
    email = f'Mixed-{uuid.uuid4().hex[:6]}@Case.TEST'
    resp = client.post('/api/v1/users', json={'email': email, 'name': 'M', 'password': NEW_PASSWORD})
    assert resp.status_code == 201 and resp.get_json()['email'] == email.lower()
    dup = client.post('/api/v1/users', json={'email': email.lower(), 'name': 'M', 'password': NEW_PASSWORD})
    assert dup.status_code == 409
    assert _login(app, email, NEW_PASSWORD).status_code == 200


# ── Migration ───────────────────────────────────────────────────────

def test_user_lifecycle_schema(app, db):
    import sqlalchemy as sa
    insp = sa.inspect(db.engine)
    cols = {c['name'] for c in insp.get_columns('users')}
    assert {'failed_login_count', 'locked_until', 'must_change_password', 'deactivated_at',
            'deactivated_by', 'deactivation_reason'} <= cols
    granted = [fk for fk in insp.get_foreign_keys('user_roles') if fk['constrained_columns'] == ['granted_by']]
    assert granted and granted[0]['options'].get('ondelete') == 'SET NULL'
    assert 'uq_user_invites_pending' in {i['name'] for i in insp.get_indexes('user_invites')}
    checks = {c['name'] for c in insp.get_check_constraints('user_invites')}
    assert 'ck_user_invites_max_expiry' in checks
