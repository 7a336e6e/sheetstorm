"""Archived incidents: hidden without `incidents:archive`, read-only with it.

An archived incident must not be reachable through an old link, a sub-resource
URL, the websocket room or the MCP/API by anyone lacking `incidents:archive`;
those callers get the same 404 as for a missing incident. Archive holders can
browse it, but every mutating request answers 409 `incident_archived` until it
is unarchived.
"""
import pytest


@pytest.fixture
def archived(users, auth, make_incident):
    """An incident visible to the Analyst (assigned) that the admin archived."""
    admin = auth(users['Administrator'])
    inc = make_incident(assign=(users['Analyst'],))
    resp = admin.post(f'/api/v1/incidents/{inc.id}/archive', json={})
    assert resp.status_code == 200, resp.get_json()
    return inc


def test_without_archive_permission_archived_incident_is_not_found(users, auth, archived):
    analyst = auth(users['Analyst'])
    for path in ('', '/timeline', '/hosts', '/tasks', '/evidence', '/questions'):
        resp = analyst.get(f'/api/v1/incidents/{archived.id}{path}')
        assert resp.status_code == 404, (path, resp.get_json())
        assert resp.get_json()['error'] == 'not_found'
    # Writes are refused the same way (no existence oracle).
    resp = analyst.post(f'/api/v1/incidents/{archived.id}/timeline',
                        json={'timestamp': '2026-10-01T10:00:00Z', 'activity': 'x'})
    assert resp.status_code == 404
    # Nor does it show in the active list.
    ids = [i['id'] for i in analyst.get('/api/v1/incidents').get_json()['items']]
    assert str(archived.id) not in ids


def test_archive_holder_can_browse_read_only(users, auth, archived):
    admin = auth(users['Administrator'])
    resp = admin.get(f'/api/v1/incidents/{archived.id}')
    assert resp.status_code == 200 and resp.get_json()['is_archived'] is True
    assert admin.get(f'/api/v1/incidents/{archived.id}/timeline').status_code == 200

    blocked = [
        admin.put(f'/api/v1/incidents/{archived.id}', json={'title': 'Renamed'}),
        admin.post(f'/api/v1/incidents/{archived.id}/timeline',
                   json={'timestamp': '2026-10-01T10:00:00Z', 'activity': 'x'}),
        admin.post(f'/api/v1/incidents/{archived.id}/tasks', json={'title': 'Do a thing'}),
        admin.patch(f'/api/v1/incidents/{archived.id}/status', json={'status': 'closed'}),
    ]
    for resp in blocked:
        assert resp.status_code == 409, resp.get_json()
        assert resp.get_json()['error'] == 'incident_archived'


def test_unarchive_restores_normal_access(users, auth, archived):
    admin, analyst = auth(users['Administrator']), auth(users['Analyst'])
    assert admin.post(f'/api/v1/incidents/{archived.id}/unarchive', json={}).status_code == 200
    assert analyst.get(f'/api/v1/incidents/{archived.id}').status_code == 200
    resp = admin.put(f'/api/v1/incidents/{archived.id}', json={'title': 'Renamed after unarchive'})
    assert resp.status_code == 200, resp.get_json()


def test_access_helpers_hide_archived(app, users, archived):
    from app.middleware.rbac import check_incident_access, user_can_access_incident
    with app.test_request_context():
        assert user_can_access_incident(users['Analyst'], archived) is False
        assert check_incident_access(users['Analyst'], archived.id) == (False, None)
        allowed, incident = check_incident_access(users['Administrator'], archived.id)
        assert allowed is True and incident.id == archived.id


def test_legal_hold_can_change_on_archived_incident(users, auth, make_incident):
    """Records management still works while archived (release a hold, then purge)."""
    admin = auth(users['Administrator'])
    inc = make_incident()
    item = admin.post(f'/api/v1/incidents/{inc.id}/evidence', json={'title': 'Disk', 'evidence_type': 'disk_image'})
    assert item.status_code == 201, item.get_json()
    eid = item.get_json()['id']
    assert admin.post(f'/api/v1/incidents/{inc.id}/archive', json={}).status_code == 200
    resp = admin.post(f'/api/v1/incidents/{inc.id}/evidence/{eid}/legal-hold', json={'hold': True, 'reason': 'litigation'})
    assert resp.status_code == 200, resp.get_json()
    # Other evidence writes stay blocked.
    resp = admin.patch(f'/api/v1/incidents/{inc.id}/evidence/{eid}', json={'title': 'Renamed'})
    assert resp.status_code == 409 and resp.get_json()['error'] == 'incident_archived'
