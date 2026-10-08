"""Item 3: WebSocket authentication picks the first VALID access token from
any candidate location, applies revocation / epoch checks and rejects
inactive users; incident rooms require incident access."""
import pytest


def _connect(app, **kw):
    from app import socketio
    return socketio.test_client(app, **kw)


def _connected_event(client):
    events = [e for e in client.get_received() if e['name'] == 'connected']
    assert events, 'no connected event'
    return events[-1]['args'][0]


def test_auth_payload_token(app, users, auth):
    ac = auth(users['Analyst'])
    c = _connect(app, auth={'token': ac.access_token})
    assert _connected_event(c).get('user_id') == str(users['Analyst'].id)


def test_garbage_candidate_does_not_shadow_valid_cookie(app, users, auth):
    ac = auth(users['Analyst'], mode='cookie')
    c = _connect(app, auth={'token': 'garbage'}, query_string='token=also-garbage',
                 flask_test_client=ac.client)
    assert _connected_event(c).get('user_id') == str(users['Analyst'].id)


def test_refresh_token_rejected(app, users, auth):
    ac = auth(users['Analyst'])
    c = _connect(app, auth={'token': ac.refresh_token})
    assert _connected_event(c).get('anonymous') is True


def test_revoked_token_rejected(app, users, auth, redis_client):
    from flask_jwt_extended import decode_token
    ac = auth(users['Manager'])
    with app.app_context():
        jti = decode_token(ac.access_token)['jti']
    redis_client.setex(f'revoked_token:{jti}', 60, 'true')
    c = _connect(app, auth={'token': ac.access_token})
    assert _connected_event(c).get('anonymous') is True


def test_epoch_bump_rejects_old_token(app, db, org_a, auth):
    from app.models import User
    from app.api.v1.endpoints.auth import _bump_token_epoch
    u = User(email='ws-epoch@a.test', name='ws', organization_id=org_a.id)
    db.session.add(u)
    db.session.commit()
    ac = auth(u)
    with app.app_context():
        _bump_token_epoch(str(u.id))
    c = _connect(app, auth={'token': ac.access_token})
    assert _connected_event(c).get('anonymous') is True


def test_inactive_user_rejected(app, db, org_a, auth):
    from app.models import User
    u = User(email='ws-inactive@a.test', name='ws', organization_id=org_a.id, is_active=True)
    db.session.add(u)
    db.session.commit()
    ac = auth(u)
    u.is_active = False
    db.session.commit()
    c = _connect(app, auth={'token': ac.access_token})
    assert _connected_event(c).get('anonymous') is True


def test_join_incident_requires_access(app, users, auth, make_incident):
    hidden = make_incident(tlp='amber')
    visible = make_incident(tlp='white')
    ac = auth(users['Viewer'])
    c = _connect(app, auth={'token': ac.access_token})
    c.get_received()
    c.emit('join_incident', {'incident_id': str(hidden.id)})
    assert any(e['name'] == 'error' for e in c.get_received())
    c.emit('join_incident', {'incident_id': 'not-a-uuid'})
    assert any(e['name'] == 'error' for e in c.get_received())
    c.emit('join_incident', {'incident_id': str(visible.id)})
    names = [e['name'] for e in c.get_received()]
    assert 'users_in_room' in names and 'error' not in names


def test_spoofed_identity_in_events_is_ignored(app, users, auth, make_incident):
    inc = make_incident(tlp='white')
    a = _connect(app, auth={'token': auth(users['Viewer']).access_token})
    b = _connect(app, auth={'token': auth(users['Administrator']).access_token})
    for c in (a, b):
        c.emit('join_incident', {'incident_id': str(inc.id)})
        c.get_received()
    a.emit('typing_start', {'incident_id': str(inc.id), 'field': 'x',
                            'user_id': str(users['Administrator'].id), 'user_name': 'Admin'})
    typing = [e for e in b.get_received() if e['name'] == 'user_typing']
    assert typing and typing[0]['args'][0]['user_id'] == str(users['Viewer'].id)
