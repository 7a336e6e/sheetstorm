"""Item 14: activity broadcasts go to the right room without sensitive
details; /activity-feed only shows accessible incidents and hides
admin_action from non-admins."""
import pytest


@pytest.fixture
def emitted(monkeypatch):
    from app import socketio
    calls = []
    monkeypatch.setattr(socketio, 'emit', lambda event, payload, room=None, **kw: calls.append((event, payload, room)))
    return calls


def _log(app, user, event_type, action, incident_id=None, details=None):
    from app.middleware.audit import log_audit_event
    with app.test_request_context():
        return log_audit_event(event_type, action, resource_type='artifact', incident_id=incident_id,
                               details=details or {}, user=user)


def test_incident_event_goes_to_incident_room_without_hashes(app, users, make_incident, emitted):
    inc = make_incident()
    _log(app, users['Analyst'], 'security_event', 'artifact_delete', incident_id=inc.id,
         details={'filename': 'a.bin', 'hashes': {'sha256': 'ab'}, 'reason': 'secret case'})
    assert len(emitted) == 1
    event, payload, room = emitted[0]
    assert room == f'incident_{inc.id}'
    assert payload['details'] == {'filename': 'a.bin'}


def test_org_event_goes_to_org_room(app, users, emitted):
    _log(app, users['Analyst'], 'data_modification', 'update', details={'sha256': 'x', 'k': 1})
    (_, payload, room), = emitted
    assert room == f'org_{users["Analyst"].organization_id}' and payload['details'] == {'k': 1}


def test_admin_action_only_to_admins(app, users, emitted):
    _log(app, users['Administrator'], 'admin_action', 'update_integration')
    rooms = {room for _, _, room in emitted}
    assert rooms == {f'user_{users["Administrator"].id}'}


def test_activity_feed_scoped(app, users, auth, make_incident):
    hidden = make_incident(tlp='amber')
    visible = make_incident(tlp='white')
    _log(app, users['Administrator'], 'data_modification', 'feed_hidden', incident_id=hidden.id)
    _log(app, users['Administrator'], 'data_modification', 'feed_visible', incident_id=visible.id,
         details={'hashes': {'md5': 'x'}, 'note': 'ok'})
    _log(app, users['Administrator'], 'admin_action', 'feed_admin_only')

    items = auth(users['Viewer']).get('/api/v1/activity-feed?limit=100').get_json()['items']
    actions = {i['action'] for i in items}
    assert 'feed_visible' in actions
    assert 'feed_hidden' not in actions and 'feed_admin_only' not in actions
    vis = next(i for i in items if i['action'] == 'feed_visible')
    assert 'hashes' not in vis['details']

    admin_actions = {i['action'] for i in auth(users['Administrator']).get('/api/v1/activity-feed?limit=100')
                     .get_json()['items']}
    assert {'feed_hidden', 'feed_visible', 'feed_admin_only'} <= admin_actions
