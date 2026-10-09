"""Teams endpoints enforce teams:* (members additionally need users:read)."""
import uuid

from rbac_helpers import make_role, make_user, new_org  # noqa: F401


def test_viewer_cannot_list_or_read_teams(app, users, auth):
    # Viewer holds neither teams:read nor users:read (unchanged from before).
    viewer = auth(users['Viewer'])
    assert viewer.get('/api/v1/teams').status_code == 403


def test_team_members_need_users_read(app, auth, new_org, make_user):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    team_id = auth(admin).post('/api/v1/teams', json={'name': f'T-{uuid.uuid4().hex[:6]}'}).get_json()['id']
    teams_only = make_user(org, perms=['teams:read'])
    assert auth(teams_only).get('/api/v1/teams').status_code == 200
    assert auth(teams_only).get(f'/api/v1/teams/{team_id}').status_code == 403
    both = make_user(org, perms=['teams:read', 'users:read'])
    assert auth(both).get(f'/api/v1/teams/{team_id}').status_code == 200


def test_users_manage_without_teams_create_forbidden(app, auth, new_org, make_user):
    org = new_org()
    manager_only = make_user(org, perms=['users:manage', 'users:read', 'teams:read'])
    assert auth(manager_only).post('/api/v1/teams', json={'name': 'X'}).status_code == 403


def test_teams_crud_by_permission(app, auth, new_org, make_user):
    org = new_org()
    member = make_user(org, perms=[])
    lead = make_user(org, perms=['teams:create', 'teams:update', 'teams:delete', 'teams:read', 'users:read'])
    c = auth(lead)
    resp = c.post('/api/v1/teams', json={'name': f'T-{uuid.uuid4().hex[:6]}'})
    assert resp.status_code == 201
    tid = resp.get_json()['id']
    assert c.put(f'/api/v1/teams/{tid}', json={'description': 'd'}).status_code == 200
    assert c.post(f'/api/v1/teams/{tid}/members', json={'user_id': str(member.id)}).status_code == 201
    assert c.delete(f'/api/v1/teams/{tid}/members/{member.id}').status_code == 200
    assert c.delete(f'/api/v1/teams/{tid}').status_code == 200


def test_administrator_teams_crud(app, users, auth):
    admin = auth(users['Administrator'])
    tid = admin.post('/api/v1/teams', json={'name': f'T-{uuid.uuid4().hex[:6]}'}).get_json()['id']
    assert admin.get(f'/api/v1/teams/{tid}').status_code == 200
    assert admin.delete(f'/api/v1/teams/{tid}').status_code == 200
