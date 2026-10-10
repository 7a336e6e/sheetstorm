"""Guided tours: per-user switch (admins only) and the user's own seen list."""
import pytest


@pytest.fixture(autouse=True)
def _clean_tour_prefs(app, db):
    """Tests share one database: drop the tour keys again afterwards."""
    yield
    from app.models import User
    for user in User.query.all():
        prefs = dict(user.preferences or {})
        if prefs.pop('tours_enabled', None) is not None or prefs.pop('tours_seen', None) is not None:
            prefs.pop('tours_seen', None)
            user.preferences = prefs
    db.session.commit()


def test_user_marks_tours_seen_but_cannot_switch_them(users, auth):
    analyst = auth(users['Analyst'])
    assert analyst.get('/api/v1/auth/me').get_json()['tours_enabled'] is True

    r = analyst.patch('/api/v1/auth/me/preferences', json={'tours_seen': ['dashboard', 'incident-detail', 'dashboard']})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['preferences']['tours_seen'] == ['dashboard', 'incident-detail']

    assert analyst.patch('/api/v1/auth/me/preferences', json={'tours_enabled': False}).status_code == 400
    assert analyst.patch('/api/v1/auth/me/preferences', json={'tours_seen': ['Bad Id!']}).status_code == 400
    assert analyst.patch('/api/v1/auth/me/preferences', json={'tours_seen': 'dashboard'}).status_code == 400


def test_admin_switches_and_resets_tours_for_a_user(users, auth):
    from app.models import AuditLog
    admin, analyst_user = auth(users['Administrator']), users['Analyst']
    auth(analyst_user).patch('/api/v1/auth/me/preferences', json={'tours_seen': ['dashboard']})

    r = admin.put(f'/api/v1/users/{analyst_user.id}/tours', json={'enabled': False})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['user']['tours_enabled'] is False

    r = admin.put(f'/api/v1/users/{analyst_user.id}/tours', json={'enabled': True, 'reset': True})
    body = r.get_json()['user']
    assert body['tours_enabled'] is True and body['preferences']['tours_seen'] == []
    assert AuditLog.query.filter_by(action='tours_update').count() >= 2

    assert admin.put(f'/api/v1/users/{analyst_user.id}/tours', json={}).status_code == 400
    assert auth(analyst_user).put(f'/api/v1/users/{users["Viewer"].id}/tours', json={'enabled': False}).status_code == 403


def test_admin_switches_tours_for_everyone(users, auth, db):
    from app.models import User
    admin = auth(users['Administrator'])
    r = admin.put('/api/v1/users/tours', json={'enabled': False})
    assert r.status_code == 200 and r.get_json()['updated'] >= 2
    db.session.expire_all()
    assert all(not u.tours_enabled for u in User.query.filter_by(organization_id=users['Administrator'].organization_id))
    assert admin.put('/api/v1/users/tours', json={'enabled': True, 'reset': True}).status_code == 200
    assert auth(users['Analyst']).put('/api/v1/users/tours', json={'enabled': False}).status_code == 403
