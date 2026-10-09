"""Org-scoped roles: visibility, uniqueness, system-role immutability,
clone, permission validation, grant ceiling and diff audit."""
import uuid

from rbac_helpers import default_org, last_audit, make_role, make_user, new_org  # noqa: F401


def _name(prefix='R'):
    return f'{prefix}-{uuid.uuid4().hex[:8]}'


def test_list_roles_excludes_other_org_custom_roles(app, users, auth):
    name = _name('B-Only')
    assert auth(users['admin_b']).post('/api/v1/roles', json={'name': name, 'permissions': []}).status_code == 201
    names_a = {r['name'] for r in auth(users['Administrator']).get('/api/v1/roles').get_json()['items']}
    names_b = {r['name'] for r in auth(users['admin_b']).get('/api/v1/roles').get_json()['items']}
    assert name not in names_a and name in names_b
    assert {'Administrator', 'Viewer'} <= names_a


def test_list_roles_shape(app, users, auth):
    items = auth(users['Administrator']).get('/api/v1/roles').get_json()['items']
    analyst = next(r for r in items if r['name'] == 'Analyst')
    assert analyst['is_system'] is True and analyst['organization_id'] is None
    assert analyst['editable'] is False and analyst['user_count'] >= 1


def test_get_update_delete_other_org_role_404(app, users, auth, org_b, make_role):
    role = make_role(org_b, ['incidents:read'])
    admin_a = auth(users['Administrator'])
    assert admin_a.get(f'/api/v1/roles/{role.id}').status_code == 404
    assert admin_a.put(f'/api/v1/roles/{role.id}', json={'description': 'x'}).status_code == 404
    assert admin_a.post(f'/api/v1/roles/{role.id}/clone', json={'name': _name()}).status_code == 404
    assert admin_a.delete(f'/api/v1/roles/{role.id}').status_code == 404


def test_custom_role_name_unique_per_org_not_global(app, users, auth):
    name = _name('Hunters')
    assert auth(users['Administrator']).post('/api/v1/roles', json={'name': name}).status_code == 201
    assert auth(users['admin_b']).post('/api/v1/roles', json={'name': name}).status_code == 201
    dup = auth(users['Administrator']).post('/api/v1/roles', json={'name': name.upper()})
    assert dup.status_code == 409


def test_cannot_shadow_system_role_name(app, users, auth):
    assert auth(users['Administrator']).post('/api/v1/roles', json={'name': 'administrator'}).status_code == 409


def test_system_role_immutable(app, db, users, auth):
    from app.models import Role
    analyst = Role.query.filter(Role.organization_id.is_(None), Role.name == 'Analyst').one()
    before = sorted(analyst.permissions)
    resp = auth(users['Administrator']).put(f'/api/v1/roles/{analyst.id}', json={'permissions': before + ['incidents:purge']})
    assert resp.status_code == 403 and resp.get_json()['error'] == 'system_role_immutable'
    assert auth(users['Administrator']).delete(f'/api/v1/roles/{analyst.id}').status_code == 403
    db.session.expire_all()
    assert sorted(Role.query.get(analyst.id).permissions) == before


def test_clone_system_role(app, db, users, auth, org_a):
    from app.models import Role
    analyst = Role.query.filter(Role.organization_id.is_(None), Role.name == 'Analyst').one()
    admin = auth(users['Administrator'])
    resp = admin.post(f'/api/v1/roles/{analyst.id}/clone', json={'name': _name('Analyst copy')})
    assert resp.status_code == 201
    clone = resp.get_json()
    assert clone['organization_id'] == str(org_a.id) and clone['is_system'] is False
    assert sorted(clone['permissions']) == sorted(analyst.permissions) and clone['editable'] is True
    perms = [p for p in clone['permissions'] if p != 'network_iocs:update']
    assert admin.put(f"/api/v1/roles/{clone['id']}", json={'permissions': perms}).status_code == 200
    db.session.expire_all()
    assert 'network_iocs:update' in Role.query.get(analyst.id).permissions


def test_clone_administrator_outside_platform_org_drops_platform_only(app, users, auth):
    from app.models import Role
    admin_role = Role.query.filter(Role.organization_id.is_(None), Role.name == 'Administrator').one()
    resp = auth(users['admin_b']).post(f'/api/v1/roles/{admin_role.id}/clone', json={'name': _name('Admin copy')})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body['dropped_permissions'] == ['system:manage'] and 'system:manage' not in body['permissions']


def test_create_role_rejects_unknown_permission(app, users, auth):
    resp = auth(users['Administrator']).post('/api/v1/roles', json={
        'name': _name(), 'permissions': ['incidents:read', 'incidents:nuke']})
    assert resp.status_code == 400 and resp.get_json()['unknown'] == ['incidents:nuke']


def test_create_role_rejects_platform_only_outside_platform_org(app, users, auth):
    resp = auth(users['admin_b']).post('/api/v1/roles', json={'name': _name(), 'permissions': ['system:manage']})
    assert resp.status_code == 403 and resp.get_json()['platform_only'] == ['system:manage']


def test_create_role_validation(app, users, auth):
    admin = auth(users['Administrator'])
    assert admin.post('/api/v1/roles', json={'name': '   '}).status_code == 400
    assert admin.post('/api/v1/roles', json={'name': 'x' * 101}).status_code == 400
    assert admin.post('/api/v1/roles', json={'name': _name(), 'description': 'd' * 501}).status_code == 400
    assert admin.post('/api/v1/roles', json={'name': _name(), 'permissions': 'incidents:read'}).status_code == 400


def test_create_role_cannot_exceed_caller(app, auth, new_org, make_user):
    org = new_org()
    role_mgr = make_user(org, perms=['roles:manage', 'users:read'])
    resp = auth(role_mgr).post('/api/v1/roles', json={'name': _name(), 'permissions': ['users:read', 'users:manage']})
    assert resp.status_code == 403
    body = resp.get_json()
    assert body['error'] == 'privilege_escalation' and body['missing'] == ['users:manage']


def test_update_role_holding_perms_caller_lacks_forbidden(app, auth, new_org, make_user, make_role):
    org = new_org()
    role_mgr = make_user(org, perms=['roles:manage', 'users:read'])
    strong = make_role(org, ['users:read', 'incidents:purge'])
    resp = auth(role_mgr).put(f'/api/v1/roles/{strong.id}', json={'permissions': ['users:read']})
    assert resp.status_code == 403 and resp.get_json()['missing'] == ['incidents:purge']
    assert auth(role_mgr).delete(f'/api/v1/roles/{strong.id}').status_code == 403
    listed = {r['id']: r for r in auth(role_mgr).get('/api/v1/roles').get_json()['items']}
    assert listed[str(strong.id)]['editable'] is False


def test_role_update_audits_permission_diff(app, db, users, auth, org_a, make_role):
    role = make_role(org_a, ['incidents:read', 'tasks:read'])
    resp = auth(users['Administrator']).put(f'/api/v1/roles/{role.id}', json={
        'permissions': ['incidents:read', 'tasks:update'], 'description': 'new'})
    assert resp.status_code == 200
    row = last_audit(db, 'update', 'role')
    assert str(row.resource_id) == str(role.id)
    changes = row.details['changes']
    assert changes['permissions'] == {'added': ['tasks:update'], 'removed': ['tasks:read']}
    assert changes['description'] == {'from': '', 'to': 'new'}


def test_role_update_emits_permissions_changed_to_holders(app, users, auth, new_org, make_user, make_role,
                                                         monkeypatch):
    from app import socketio
    calls = []
    monkeypatch.setattr(socketio, 'emit',
                        lambda e, p=None, room=None, to=None, **kw: calls.append((e, room or to)))
    holder = make_user(new_org(), perms=[])
    # A holder in org A of a fresh org-A role.
    from app.models import Role, UserRole
    from app import db
    role = Role.query.get(make_role(users['Administrator'].organization, ['incidents:read']).id)
    db.session.add(UserRole(user_id=users['Analyst'].id, role_id=role.id, organization_id=role.organization_id))
    db.session.commit()
    try:
        resp = auth(users['Administrator']).put(f'/api/v1/roles/{role.id}', json={'permissions': ['tasks:read']})
        assert resp.status_code == 200
        assert ('permissions_changed', f'user_{users["Analyst"].id}') in calls
        assert ('permissions_changed', f'user_{holder.id}') not in calls
    finally:
        UserRole.query.filter_by(role_id=role.id).delete()
        db.session.commit()
