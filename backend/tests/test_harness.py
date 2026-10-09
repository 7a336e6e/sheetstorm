"""Self-tests for the shared test helpers (conftest.py + tests/fixtures/)."""
import conftest


def test_feature_fixture_modules_are_registered():
    assert 'fixtures.harness' in conftest.pytest_plugins


def test_feature_fixture_is_usable(harness_viewer, org_a):
    assert harness_viewer.organization_id == org_a.id
    assert harness_viewer.has_role('Viewer')


def test_make_user_with_system_roles(make_user, org_b):
    user = make_user(org_b, roles=['Analyst', 'Operator'])
    assert user.organization_id == org_b.id
    assert user.has_role('Analyst') and user.has_role('Operator')
    assert user.check_password(conftest.TEST_PASSWORD)


def test_make_user_with_custom_permissions(make_user, org_a):
    user = make_user(org_a, perms=['incidents:read', 'timeline:read'])
    assert set(user.permissions) == {'incidents:read', 'timeline:read'}
    assert not user.has_permission('incidents:create')


def test_make_user_without_roles_has_no_permissions(make_user, org_a):
    user = make_user(org_a)
    assert list(user.permissions) == []


def test_fresh_user_is_unique_and_authenticates(fresh_user, auth):
    a, b = fresh_user(), fresh_user()
    assert a.id != b.id and a.email != b.email
    assert a.has_role('Analyst')
    assert auth(a).get('/api/v1/auth/me').status_code == 200


def test_fresh_user_inactive(fresh_user, app):
    user = fresh_user('Viewer', is_active=False)
    assert user.is_active is False
    resp = app.test_client().post('/api/v1/auth/login',
                                  json={'email': user.email, 'password': conftest.TEST_PASSWORD})
    assert resp.status_code == 401


def test_platform_admin(platform_admin, platform_org, app):
    assert platform_org.slug == app.config.get('PLATFORM_ORG_SLUG', 'default')
    assert platform_admin.organization_id == platform_org.id
    assert platform_admin.has_role('Administrator')


def test_g_is_fresh_for_every_request(app, db, auth, fresh_user, make_incident):
    """The session-wide app context is shared by every test request; g must
    not carry an earlier request's incident into the next audit row."""
    from flask import g
    from app.models import AuditLog
    admin = fresh_user('Administrator')
    inc = make_incident(assign=[admin])
    client = auth(admin)
    assert client.get(f'/api/v1/incidents/{inc.id}').status_code == 200
    assert getattr(g, 'incident', None) is not None  # left behind by the shared context
    assert client.patch('/api/v1/auth/me/preferences', json={'display_timezone': 'utc'}).status_code == 200
    row = (AuditLog.query.filter_by(action='update_preferences', user_id=admin.id)
           .order_by(AuditLog.chain_seq.desc()).first())
    assert row is not None and row.incident_id is None
