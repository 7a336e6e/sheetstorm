"""Admin guardrails: grant ceiling, hierarchy, last-admin (incl. races),
self guards, users:create/users:delete, security events."""
import threading
import uuid

import pytest

from conftest import TEST_PASSWORD
from rbac_helpers import default_org, emitted, last_audit, make_role, make_user, new_org, security_events  # noqa: F401

ADMIN_CORE = ['users:manage', 'roles:manage', 'users:read', 'users:update', 'users:create', 'users:delete']
DEPUTY = ['users:read', 'users:update', 'users:manage', 'roles:manage']


def _role(name):
    from app.models import Role
    return Role.query.filter(Role.organization_id.is_(None), Role.name == name).one()


def _new_user_body(**kw):
    return {'email': f'n-{uuid.uuid4().hex[:10]}@rbac.test', 'name': 'N', 'password': 'An0ther-Str0ng-Pass!', **kw}


# ── grant ceiling ───────────────────────────────────────────────────

def test_assign_role_exceeding_caller_forbidden(app, auth, new_org, make_user):
    org = new_org()
    deputy, target = make_user(org, perms=DEPUTY), make_user(org, perms=[])
    resp = auth(deputy).post(f'/api/v1/users/{target.id}/roles', json={'role_id': str(_role('Administrator').id)})
    assert resp.status_code == 403
    body = resp.get_json()
    assert body['error'] == 'privilege_escalation' and 'incidents:purge' in body['missing']


def test_assign_role_within_ceiling_ok_and_emits(app, auth, new_org, make_user, make_role, emitted):
    org = new_org()
    deputy, target = make_user(org, perms=DEPUTY + ['incidents:read']), make_user(org, perms=[])
    role = make_role(org, ['incidents:read'])
    assert auth(deputy).post(f'/api/v1/users/{target.id}/roles', json={'role_id': str(role.id)}).status_code == 201
    assert ('permissions_changed', {}, f'user_{target.id}') in emitted


def test_assign_other_org_role_404(app, users, auth, org_b, make_role, make_user, new_org):
    foreign = make_role(org_b, ['incidents:read'])
    target = make_user(users['Administrator'].organization, perms=[])
    resp = auth(users['Administrator']).post(f'/api/v1/users/{target.id}/roles', json={'role_id': str(foreign.id)})
    assert resp.status_code == 404


def test_create_user_role_ceiling(app, auth, new_org, make_user):
    org = new_org()
    deputy = make_user(org, perms=DEPUTY + ['users:create', 'incidents:read'])
    resp = auth(deputy).post('/api/v1/users', json=_new_user_body(roles=['Administrator']))
    assert resp.status_code == 403 and resp.get_json()['error'] == 'privilege_escalation'


def test_create_user_unknown_role_400(app, users, auth):
    resp = auth(users['Administrator']).post('/api/v1/users', json=_new_user_body(roles=['Overlords']))
    assert resp.status_code == 400 and resp.get_json()['unknown'] == ['Overlords']


def test_create_user_resolves_org_custom_role(app, users, auth, org_a, make_role):
    role = make_role(org_a, ['incidents:read'], name=f'Hunters-{uuid.uuid4().hex[:6]}')
    resp = auth(users['Administrator']).post('/api/v1/users', json=_new_user_body(roles=[role.name.lower()]))
    assert resp.status_code == 201 and resp.get_json()['roles'] == [role.name]


def test_create_user_cannot_use_other_org_custom_role(app, users, auth, org_b, make_role):
    role = make_role(org_b, ['incidents:read'])
    resp = auth(users['Administrator']).post('/api/v1/users', json=_new_user_body(roles=[role.name]))
    assert resp.status_code == 400


def test_create_user_requires_users_create(app, auth, new_org, make_user):
    org = new_org()
    manager_only = make_user(org, perms=['users:manage', 'users:read'])
    assert auth(manager_only).post('/api/v1/users', json=_new_user_body()).status_code == 403


def test_delete_user_requires_users_delete(app, auth, new_org, make_user):
    org = new_org()
    manager_only = make_user(org, perms=['users:manage', 'users:read'])
    target = make_user(org, perms=[])
    assert auth(manager_only).delete(f'/api/v1/users/{target.id}').status_code == 403


# ── hierarchy ───────────────────────────────────────────────────────

def test_users_manage_cannot_disable_or_reset_administrator(app, db, auth, new_org, make_user):
    from app.models import User
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    deputy = make_user(org, perms=DEPUTY)
    client = auth(deputy)
    resp = client.put(f'/api/v1/users/{admin.id}', json={'is_active': False})
    assert resp.status_code == 403 and resp.get_json()['error'] == 'insufficient_privilege'
    assert client.put(f'/api/v1/users/{admin.id}', json={'password': 'An0ther-Str0ng-Pass!'}).status_code == 403
    assert client.put(f'/api/v1/users/{admin.id}', json={'name': 'pwned'}).status_code == 403
    db.session.expire_all()
    fresh = User.query.get(admin.id)
    assert fresh.is_active is True and fresh.name != 'pwned' and fresh.check_password(TEST_PASSWORD)


def test_cannot_delete_or_revoke_superior(app, auth, new_org, make_user):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    deputy = make_user(org, perms=DEPUTY + ['users:delete'])
    assert auth(deputy).delete(f'/api/v1/users/{admin.id}').status_code == 403
    rid = _role('Administrator').id
    assert auth(deputy).delete(f'/api/v1/users/{admin.id}/roles/{rid}').status_code == 403


def test_manage_subordinate_ok(app, auth, new_org, make_user):
    org = new_org()
    deputy = make_user(org, perms=DEPUTY + ['incidents:read'])
    target = make_user(org, perms=['incidents:read'])
    assert auth(deputy).put(f'/api/v1/users/{target.id}', json={'is_active': False}).status_code == 200


# ── last admin ──────────────────────────────────────────────────────

def test_last_admin_revoke_409(app, auth, new_org, make_user):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    resp = auth(admin).delete(f'/api/v1/users/{admin.id}/roles/{_role("Administrator").id}')
    assert resp.status_code == 409 and resp.get_json()['error'] in ('last_admin', 'self_lockout')


def test_self_lockout_even_with_other_admins(app, auth, new_org, make_user):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    make_user(org, roles=['Administrator'])
    resp = auth(admin).delete(f'/api/v1/users/{admin.id}/roles/{_role("Administrator").id}')
    assert resp.status_code == 409 and resp.get_json()['error'] == 'self_lockout'


def test_last_admin_disable_and_delete_409(app, auth, new_org, make_user):
    org = new_org()
    a1, a2 = make_user(org, roles=['Administrator']), make_user(org, roles=['Administrator'])
    assert auth(a1).put(f'/api/v1/users/{a2.id}', json={'is_active': False}).status_code == 200
    # a1 is now the only active admin and cannot remove themselves.
    assert auth(a1).put(f'/api/v1/users/{a1.id}', json={'is_active': False}).status_code == 400
    assert auth(a1).delete(f'/api/v1/users/{a1.id}').status_code == 400
    # The hypothetical guard itself: excluding the last admin is refused.
    from app.services.rbac_guard import GuardError, admin_holders, assert_admin_remains
    from app import db
    assert admin_holders(org.id) == {str(a1.id)}
    for hyp in ({'exclude_users': {a1.id}},
                {'drop_assignments': [(a1.id, _role('Administrator').id)]},
                {'role_overrides': {_role('Administrator').id: ['users:read']}}):
        with pytest.raises(GuardError) as exc:
            assert_admin_remains(org.id, **hyp)
        assert exc.value.status == 409 and exc.value.code == 'last_admin'
        db.session.rollback()
    # Adding a hypothetical second admin makes excluding a1 fine.
    assert_admin_remains(org.id, exclude_users={a1.id}, add_assignments=[(a2.id, ADMIN_CORE)])
    db.session.rollback()


def test_admin_holders_ignores_inactive_and_foreign_roles(app, db, new_org, make_user, make_role):
    from app.models import UserRole
    from app.services.rbac_guard import admin_holders
    org, other = new_org(), new_org()
    active = make_user(org, perms=ADMIN_CORE)
    make_user(org, perms=ADMIN_CORE, active=False)
    sneaky = make_user(org, perms=[])
    foreign_admin_role = make_role(other, ADMIN_CORE)
    db.session.add(UserRole(user_id=sneaky.id, role_id=foreign_admin_role.id, organization_id=org.id))
    db.session.commit()
    assert admin_holders(org.id) == {str(active.id)}
    db.session.expire_all()
    from app.models import User
    assert not set(['users:manage']) & set(User.query.get(sneaky.id).permissions)


def test_role_edit_removing_admin_core_last_holder_409(app, auth, new_org, make_user, make_role):
    from app.models import UserRole
    from app import db
    org = new_org()
    admin_role = make_role(org, ADMIN_CORE)
    admin = make_user(org, roles=['Administrator'])
    other = make_user(org, perms=[])
    db.session.add(UserRole(user_id=other.id, role_id=admin_role.id, organization_id=org.id))
    db.session.commit()
    # Drop the system Administrator from `admin` so `other` (custom role) is the only admin source.
    assert auth(admin).delete(f'/api/v1/users/{admin.id}/roles/{_role("Administrator").id}').status_code == 409
    resp = auth(other).put(f'/api/v1/roles/{admin_role.id}', json={'permissions': ['users:read']})
    assert resp.status_code == 409 and resp.get_json()['error'] in ('self_lockout', 'last_admin')


def test_role_edit_by_other_admin_removing_holder_ok(app, auth, new_org, make_user, make_role):
    from app.models import UserRole
    from app import db
    org = new_org()
    admin_role = make_role(org, ADMIN_CORE)
    holder = make_user(org, perms=[])
    db.session.add(UserRole(user_id=holder.id, role_id=admin_role.id, organization_id=org.id))
    db.session.commit()
    editor = make_user(org, perms=ADMIN_CORE)  # admin via a different role
    # editor's own admin-core is unaffected; holder loses it but editor remains -> allowed.
    assert auth(editor).put(f'/api/v1/roles/{admin_role.id}', json={'permissions': ['users:read']}).status_code == 200


def test_guard_noop_when_org_has_no_admin(app, auth, new_org, make_user, make_role):
    org = new_org()
    role_mgr = make_user(org, perms=['roles:manage', 'users:read', 'incidents:read'])
    target = make_user(org, perms=['incidents:read'])
    rid = target.user_roles[0].role_id
    assert auth(role_mgr).delete(f'/api/v1/users/{target.id}/roles/{rid}').status_code == 200


def test_concurrent_last_admin_demotion(app, new_org, make_user):
    """Two admins disable each other at the same time: at most one succeeds."""
    from app.models import User
    from app import db
    from conftest import AuthClient
    org = new_org()
    a1, a2 = make_user(org, roles=['Administrator']), make_user(org, roles=['Administrator'])
    c1, c2 = AuthClient(app, a1), AuthClient(app, a2)
    barrier, results = threading.Barrier(2), {}

    def go(name, client, target):
        barrier.wait()
        results[name] = client.put(f'/api/v1/users/{target.id}', json={'is_active': False}).status_code

    threads = [threading.Thread(target=go, args=('a', c1, a2)), threading.Thread(target=go, args=('b', c2, a1))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sorted(results.values()) in ([200, 409], [200, 401], [200, 403])
    db.session.expire_all()
    assert sum(User.query.get(u.id).is_active for u in (a1, a2)) == 1


# ── self guards ─────────────────────────────────────────────────────

def test_self_disable_400(app, auth, new_org, make_user):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    make_user(org, roles=['Administrator'])
    resp = auth(admin).put(f'/api/v1/users/{admin.id}', json={'is_active': False})
    body = resp.get_json()
    assert resp.status_code == 400 and body['error'] == 'self_action' and body['action'] == 'disable'


def test_self_delete_400(app, auth, new_org, make_user):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    resp = auth(admin).delete(f'/api/v1/users/{admin.id}')
    assert resp.status_code == 400 and resp.get_json()['action'] == 'delete'


def test_self_password_via_admin_endpoint_400(app, auth, new_org, make_user):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    resp = auth(admin).put(f'/api/v1/users/{admin.id}', json={'password': 'An0ther-Str0ng-Pass!'})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'use_change_password'


def test_self_rename_allowed(app, auth, new_org, make_user):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    assert auth(admin).put(f'/api/v1/users/{admin.id}', json={'name': 'Me'}).status_code == 200


# ── security events / audit ─────────────────────────────────────────

def test_guard_denial_logs_security_event(app, db, auth, new_org, make_user):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    deputy = make_user(org, perms=DEPUTY)
    auth(deputy).put(f'/api/v1/users/{admin.id}', json={'is_active': False})
    events = [e for e in security_events(db, 'privilege_escalation_blocked') if e.user_id == deputy.id]
    assert events and events[0].details['code'] == 'insufficient_privilege'
    assert str(events[0].resource_id) == str(admin.id)

    auth(admin).delete(f'/api/v1/users/{admin.id}/roles/{_role("Administrator").id}')
    assert [e for e in security_events(db, 'last_admin_blocked') if e.user_id == admin.id]


def test_guard_denial_rolls_back(app, db, auth, new_org, make_user):
    from app.models import UserRole
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    auth(admin).delete(f'/api/v1/users/{admin.id}/roles/{_role("Administrator").id}')
    db.session.expire_all()
    assert UserRole.query.filter_by(user_id=admin.id).count() == 1


def test_oauth_google_azure_creation_refused(app, users, auth):
    admin = auth(users['Administrator'])
    for t in ('oauth_google', 'oauth_azure'):
        resp = admin.post('/api/v1/integrations', json={'type': t, 'name': f'x-{t}', 'config': {}})
        assert resp.status_code == 400 and resp.get_json()['error'] == 'not_supported'
    types = admin.get('/api/v1/integrations/types').get_json()
    flat = {t['id']: t for t in types['types']}
    assert flat['oauth_github']['login_supported'] is True
    assert flat['oauth_google']['login_supported'] is False and flat['oauth_azure']['login_supported'] is False


def test_platform_admin_requires_platform_org(app, users, default_org, make_user):
    default_org_admin = make_user(default_org, roles=['Administrator'])
    from app.middleware.rbac import is_platform_admin
    assert is_platform_admin(default_org_admin) is True
    assert is_platform_admin(users['Administrator']) is False  # holds system:manage, wrong org
    assert is_platform_admin(users['Manager']) is False
