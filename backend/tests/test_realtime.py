"""Realtime core (W0-RT-CORE): scope rooms, envelope, presence, socket
abuse limits and the cross-worker helpers in app/services/realtime.py."""
import time
import uuid

import pytest

from app.services import realtime


def _connect(app, token=None):
    from app import socketio
    kw = {'auth': {'token': token}} if token else {}
    c = socketio.test_client(app, **kw)
    c.get_received()
    return c


@pytest.fixture
def sock(app, auth):
    """sock(user) -> connected socket test client (events drained)."""
    clients = []

    def make(user=None):
        c = _connect(app, auth(user).access_token if user is not None else None)
        clients.append(c)
        return c
    yield make
    for c in clients:
        if c.is_connected():
            c.disconnect()


def _events(client, name):
    return [e['args'][0] if e['args'] else None for e in client.get_received() if e['name'] == name]


def _join(client, incident):
    return client.emit('incident:join', {'incident_id': str(incident.id)}, callback=True)


# ---------------------------------------------------------------------------
# Join / room authorization
# ---------------------------------------------------------------------------

def test_anonymous_socket_cannot_join(sock, make_incident):
    inc = make_incident(tlp='white')
    c = sock(None)
    c.emit('incident:join', {'incident_id': str(inc.id)})
    errors = _events(c, 'rt:error')
    assert errors == [{'code': 'denied', 'event': 'incident:join'}]


def test_cross_org_join_denied_and_audited(app, db, sock, users, make_incident, org_b):
    from app.models import AuditLog
    inc = make_incident(org=org_b)
    c = sock(users['Administrator'])
    c.emit('incident:join', {'incident_id': str(inc.id)})
    assert _events(c, 'rt:error') == [{'code': 'denied', 'event': 'incident:join'}]
    # A second denial within the minute is not audited again (throttled).
    c.emit('incident:join', {'incident_id': str(inc.id)})
    rows = AuditLog.query.filter_by(action='ws_join_denied', resource_id=inc.id).all()
    assert len(rows) == 1
    assert rows[0].user_id == users['Administrator'].id


def test_invalid_payloads_rejected(sock, users):
    c = sock(users['Analyst'])
    for payload in ('nope', {'incident_id': 'not-a-uuid'}, {'incident_id': 12}, None):
        c.emit('incident:join', payload)
        assert _events(c, 'rt:error') == [{'code': 'invalid', 'event': 'incident:join'}]


def test_join_ack_shape_and_scope_rooms(sock, users, make_incident):
    inc = make_incident(tlp='white')
    viewer = sock(users['Viewer'])
    ack = _join(viewer, inc)
    assert ack['incident_id'] == str(inc.id)
    assert 'artifacts' not in ack['scopes']          # Viewer lacks artifacts:read
    assert {'incident', 'hosts', 'tasks', 'timeline'} <= set(ack['scopes'])
    assert set(ack['seq']) == set(ack['scopes'])
    assert [u['user_id'] for u in ack['presence']] == [str(users['Viewer'].id)]
    joined = _events(viewer, 'incident:joined')
    assert joined and joined[0]['scopes'] == ack['scopes']

    analyst = sock(users['Analyst'])
    assert 'artifacts' in _join(analyst, inc)['scopes']


def test_viewer_does_not_receive_artifact_events(sock, users, make_incident):
    inc = make_incident(tlp='white')
    viewer, analyst = sock(users['Viewer']), sock(users['Analyst'])
    _join(viewer, inc)
    _join(analyst, inc)
    viewer.get_received()
    analyst.get_received()

    aid = str(uuid.uuid4())
    realtime.emit_change(inc.id, 'artifact', 'created', data={'id': aid, 'original_filename': 'x.bin'})
    assert _events(viewer, 'entity:changed') == []
    got = _events(analyst, 'entity:changed')
    assert len(got) == 1 and got[0]['entity'] == 'artifact' and got[0]['id'] == aid

    realtime.emit_change(inc.id, 'host', 'created', data={'id': str(uuid.uuid4()), 'hostname': 'h1'})
    assert len(_events(viewer, 'entity:changed')) == 1
    assert len(_events(analyst, 'entity:changed')) == 1


def test_resync_is_scope_filtered(sock, users, make_incident):
    inc = make_incident(tlp='white')
    viewer, analyst = sock(users['Viewer']), sock(users['Analyst'])
    _join(viewer, inc)
    _join(analyst, inc)
    viewer.get_received()
    analyst.get_received()
    sent = realtime.emit_resync(inc.id, ['artifacts', 'hosts', 'bogus'], 'import')
    assert sent == ['artifacts', 'hosts']
    v = _events(viewer, 'incident:resync')
    a = _events(analyst, 'incident:resync')
    assert v == [{'incident_id': str(inc.id), 'scopes': ['hosts'], 'reason': 'import'}]
    assert sorted(e['scopes'][0] for e in a) == ['artifacts', 'hosts']


def test_other_incident_room_receives_nothing(sock, users, make_incident):
    a, b = make_incident(tlp='white'), make_incident(tlp='white')
    c = sock(users['Analyst'])
    _join(c, a)
    c.get_received()
    realtime.emit_change(b.id, 'task', 'created', data={'id': str(uuid.uuid4())})
    assert _events(c, 'entity:changed') == []


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

def test_envelope_shape_and_seq_per_scope(sock, users, make_incident):
    inc = make_incident(tlp='white')
    c = sock(users['Analyst'])
    _join(c, inc)
    c.get_received()
    tid = str(uuid.uuid4())
    e1 = realtime.emit_change(inc.id, 'task', 'created', data={'id': tid, 'title': 't', 'version': 1})
    e2 = realtime.emit_change(inc.id, 'task', 'updated', data={'id': tid, 'title': 't2', 'version': 2})
    e3 = realtime.emit_change(inc.id, 'task', 'deleted', id=tid)
    other = realtime.emit_change(inc.id, 'host', 'created', data={'id': str(uuid.uuid4())})
    got = _events(c, 'entity:changed')
    assert [g['op'] for g in got] == ['created', 'updated', 'deleted', 'created']
    first = got[0]
    assert set(first) == {'incident_id', 'entity', 'op', 'id', 'version', 'scope', 'seq',
                          'actor', 'at', 'data'}
    assert first['incident_id'] == str(inc.id) and first['scope'] == 'tasks'
    assert first['version'] == 1 and first['data']['title'] == 't'
    assert e2['seq'] == e1['seq'] + 1 and e3['seq'] == e2['seq'] + 1
    assert other['seq'] == 1                     # independent counter per scope
    assert 'data' not in got[2] and got[2]['id'] == tid
    assert first['actor'] is None                # no request user outside HTTP


def test_envelope_actor_and_object_serialization(app, users, make_incident):
    from flask import g
    inc = make_incident()

    class Obj:
        id = uuid.uuid4()
        version = 3

        def to_dict(self):
            return {'id': str(self.id), 'title': 'x', 'version': self.version}

    with app.test_request_context():
        previous = g.pop('current_user', None)
        g.current_user = users['Analyst']
        try:
            env = realtime.build_envelope(inc.id, 'task', 'updated', obj=Obj())
        finally:
            g.pop('current_user', None)
            if previous is not None:
                g.current_user = previous
    assert env['actor'] == {'id': str(users['Analyst'].id), 'name': users['Analyst'].name}
    assert env['version'] == 3 and env['id'] == str(Obj.id) and env['data']['title'] == 'x'


def test_account_payload_is_always_masked():
    class Account:
        id = uuid.uuid4()
        version = 1

        def to_dict(self, reveal_password=True, decrypted_password=None):
            return {'id': str(self.id), 'password': 'hunter2' if reveal_password else '********'}

    env = realtime.build_envelope(uuid.uuid4(), 'account', 'updated', obj=Account())
    assert env['data']['password'] == '********'


def test_artifact_payload_drops_storage_internals():
    class Artifact:
        id = uuid.uuid4()

        def to_dict(self):
            return {'id': str(self.id), 'storage_path': '/srv/x', 'extra_data': {'drive_file_id': 'f'},
                    'sha256': 'ab', 'original_filename': 'x'}

    env = realtime.build_envelope(uuid.uuid4(), 'artifact', 'created', obj=Artifact())
    assert 'storage_path' not in env['data'] and 'extra_data' not in env['data']
    assert env['data']['sha256'] == 'ab'


def test_emit_change_swallows_errors():
    assert realtime.emit_change('not-a-uuid', 'task', 'created', data={}) is None
    assert realtime.emit_change(uuid.uuid4(), 'unknown_entity', 'created', data={}) is None
    assert realtime.emit_change(uuid.uuid4(), 'task', 'exploded', data={}) is None


def test_registry_and_resource_type_mapping():
    assert realtime.scope_for_resource_type('compromised_host') == 'hosts'
    assert realtime.scope_for_resource_type('host_indicator') == 'host_iocs'
    assert realtime.scope_for_resource_type('artifact') == 'artifacts'
    assert realtime.scope_for_resource_type('attack_graph_edge') == 'attack_graph'
    assert realtime.scope_for_resource_type('incident') == 'incident'
    assert realtime.scope_for_resource_type('report') is None
    for reserved in ('evidence_item', 'custody_entry', 'question', 'decision',
                     'decision_privileged', 'response_action', 'review', 'improvement_action'):
        assert reserved in realtime.ENTITY_SCOPES
    assert realtime.scope_for_entity('decision_privileged') == 'decisions_privileged'
    names = realtime.known_resource_types()
    assert {'compromised_host', 'chain_of_custody', 'artifact', 'incident'} <= names
    assert all(realtime.scope_for_resource_type(n) is not None for n in names)
    with pytest.raises(ValueError):
        realtime.register_entity('sneaky', 'artifacts', 'incidents:read')


# ---------------------------------------------------------------------------
# Leave / spoofing
# ---------------------------------------------------------------------------

def test_leave_by_non_member_or_anonymous_broadcasts_nothing(sock, users, make_incident):
    inc = make_incident(tlp='white')
    member = sock(users['Analyst'])
    outsider = sock(users['Manager'])
    anon = sock(None)
    _join(member, inc)
    member.get_received()

    outsider.emit('incident:leave', {'incident_id': str(inc.id)})
    anon.emit('incident:leave', {'incident_id': str(inc.id)})
    anon.emit('presence:update', {'incident_id': str(inc.id), 'mode': 'editing'})
    assert member.get_received() == []
    assert _events(anon, 'rt:error') == [{'code': 'denied', 'event': 'incident:leave'},
                                         {'code': 'denied', 'event': 'presence:update'}]


def test_member_leave_updates_presence_and_rooms(sock, users, make_incident):
    inc = make_incident(tlp='white')
    a, b = sock(users['Analyst']), sock(users['Incident Responder'])
    _join(a, inc)
    _join(b, inc)
    a.get_received()
    b.get_received()
    b.emit('incident:leave', {'incident_id': str(inc.id)})
    states = _events(a, 'presence:state')
    assert states and [u['user_id'] for u in states[-1]['users']] == [str(users['Analyst'].id)]
    realtime.emit_change(inc.id, 'task', 'created', data={'id': str(uuid.uuid4())})
    assert _events(b, 'entity:changed') == []


def test_sixth_room_evicts_oldest(sock, users, make_incident):
    incs = [make_incident(tlp='white') for _ in range(6)]
    c = sock(users['Administrator'])
    for inc in incs:
        _join(c, inc)
    c.get_received()
    realtime.emit_change(incs[0].id, 'incident', 'updated', data={'id': str(incs[0].id)})
    realtime.emit_change(incs[5].id, 'incident', 'updated', data={'id': str(incs[5].id)})
    got = _events(c, 'entity:changed')
    assert [g['incident_id'] for g in got] == [str(incs[5].id)]
    assert realtime.presence_list(incs[0].id) == []


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------

def test_presence_update_and_no_sids(monkeypatch, sock, users, make_incident):
    from app.api import websocket as ws
    monkeypatch.setattr(ws, 'PRESENCE_BROADCAST_INTERVAL', 0.0)
    inc = make_incident(tlp='white')
    a, b = sock(users['Analyst']), sock(users['Administrator'])
    _join(a, inc)
    _join(b, inc)
    a.get_received()
    b.get_received()
    task_id = str(uuid.uuid4())
    a.emit('presence:update', {'incident_id': str(inc.id), 'mode': 'editing',
                               'focus': {'entity': 'task', 'id': task_id}})
    states = _events(b, 'presence:state')
    assert states
    me = [u for u in states[-1]['users'] if u['user_id'] == str(users['Analyst'].id)][0]
    assert me['focus'] == {'entity': 'task', 'id': task_id} and me['mode'] == 'editing'
    assert set(me) == {'pid', 'user_id', 'name', 'focus', 'mode', 'since'}
    all_sids = set(realtime.user_sids(users['Analyst'].id)) | set(realtime.user_sids(users['Administrator'].id))
    assert all_sids
    for u in states[-1]['users']:
        assert u['pid'] not in all_sids
        assert 'sid' not in u


def test_presence_update_validation(sock, users, make_incident):
    inc = make_incident(tlp='white')
    viewer = sock(users['Viewer'])
    _join(viewer, inc)
    viewer.get_received()
    bad = [
        {'incident_id': str(inc.id), 'mode': 'hacking'},
        {'incident_id': str(inc.id), 'focus': {'entity': 'nope', 'id': str(uuid.uuid4())}},
        {'incident_id': str(inc.id), 'focus': {'entity': 'task', 'id': 'x'}},
        # Viewer cannot read artifacts, so cannot advertise focus on one.
        {'incident_id': str(inc.id), 'focus': {'entity': 'artifact', 'id': str(uuid.uuid4())}},
        {'incident_id': str(inc.id), 'focus': 'task'},
    ]
    for payload in bad:
        viewer.emit('presence:update', payload)
        assert _events(viewer, 'rt:error') == [{'code': 'invalid', 'event': 'presence:update'}]
    other = make_incident(tlp='white')
    viewer.emit('presence:update', {'incident_id': str(other.id), 'mode': 'viewing'})
    assert _events(viewer, 'rt:error') == [{'code': 'denied', 'event': 'presence:update'}]


def test_presence_ttl_prunes_stale_entries(make_incident):
    iid = str(uuid.uuid4())
    realtime.presence_set(iid, 'pid-old', {'user_id': 'u1', 'name': 'A', 'focus': None,
                                           'mode': 'viewing', 'since': 's'})
    assert [u['pid'] for u in realtime.presence_list(iid)] == ['pid-old']
    later = time.time() + realtime.PRESENCE_STALE_SECONDS + 1
    assert realtime.presence_list(iid, now=later) == []
    # Pruned from the store, not just filtered.
    assert realtime.presence_list(iid) == []


def test_disconnect_clears_presence(sock, users, make_incident):
    inc = make_incident(tlp='white')
    a, b = sock(users['Analyst']), sock(users['Administrator'])
    _join(a, inc)
    _join(b, inc)
    a.get_received()
    b.disconnect()
    states = _events(a, 'presence:state')
    assert states and [u['user_id'] for u in states[-1]['users']] == [str(users['Analyst'].id)]


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------

def test_presence_update_burst_is_rate_limited(sock, users, make_incident):
    inc = make_incident(tlp='white')
    c = sock(users['Analyst'])
    _join(c, inc)
    c.get_received()
    for _ in range(9):
        c.emit('presence:update', {'incident_id': str(inc.id), 'mode': 'viewing'})
    errors = _events(c, 'rt:error')
    assert errors == [{'code': 'rate_limited', 'event': 'presence:update'}]


def test_join_rate_limit(sock, users, make_incident):
    inc = make_incident(tlp='white')
    c = sock(users['Analyst'])
    for _ in range(11):
        c.emit('incident:join', {'incident_id': str(inc.id)})
    errors = _events(c, 'rt:error')
    assert errors == [{'code': 'rate_limited', 'event': 'incident:join'}]


def test_repeated_violations_disconnect_and_audit(monkeypatch, db, sock, users):
    from app.api import websocket as ws
    from app.models import AuditLog
    monkeypatch.setitem(ws.RATE_LIMITS, 'default', (1, 0.0001))
    monkeypatch.setattr(ws, 'VIOLATION_LIMIT', 3)
    user = users['Operator']
    before = AuditLog.query.filter_by(action='ws_rate_limited', user_id=user.id).count()
    c = sock(user)
    for _ in range(6):
        if not c.is_connected():
            break
        c.emit('ping')
    assert not c.is_connected()
    assert AuditLog.query.filter_by(action='ws_rate_limited', user_id=user.id).count() == before + 1


def test_frame_size_cap(app):
    from app import socketio
    assert socketio.server.eio.max_http_buffer_size == 64 * 1024


# ---------------------------------------------------------------------------
# Graph drag
# ---------------------------------------------------------------------------

def _node(db, incident, user):
    from app.models import AttackGraphNode
    n = AttackGraphNode(incident_id=incident.id, node_type='workstation', label='n',
                        created_by=user.id)
    db.session.add(n)
    db.session.commit()
    return n


def test_graph_node_drag(db, sock, users, make_incident):
    inc, other = make_incident(tlp='white'), make_incident(tlp='white')
    node, foreign = _node(db, inc, users['Administrator']), _node(db, other, users['Administrator'])
    analyst, admin, viewer = sock(users['Analyst']), sock(users['Administrator']), sock(users['Viewer'])
    for c in (analyst, admin, viewer):
        _join(c, inc)
        c.get_received()

    analyst.emit('graph:node_drag', {'incident_id': str(inc.id), 'node_id': str(node.id), 'x': 10, 'y': -2.5})
    got = _events(admin, 'graph:node_drag')
    assert got == [{'incident_id': str(inc.id), 'node_id': str(node.id), 'x': 10.0, 'y': -2.5,
                    'user_id': str(users['Analyst'].id)}]
    assert _events(analyst, 'graph:node_drag') == []      # not echoed to self

    analyst.emit('graph:node_drag', {'incident_id': str(inc.id), 'node_id': str(foreign.id), 'x': 1, 'y': 1})
    assert _events(analyst, 'rt:error') == [{'code': 'invalid', 'event': 'graph:node_drag'}]
    for bad in (float('nan'), 1e7, True, '5'):
        analyst.emit('graph:node_drag', {'incident_id': str(inc.id), 'node_id': str(node.id), 'x': bad, 'y': 1})
        assert _events(analyst, 'rt:error') == [{'code': 'invalid', 'event': 'graph:node_drag'}]
    viewer.emit('graph:node_drag', {'incident_id': str(inc.id), 'node_id': str(node.id), 'x': 1, 'y': 1})
    assert _events(viewer, 'rt:error') == [{'code': 'denied', 'event': 'graph:node_drag'}]
    assert _events(admin, 'graph:node_drag') == []


# ---------------------------------------------------------------------------
# SID registry, eviction, disconnect (real in-process server)
# ---------------------------------------------------------------------------

def test_sid_registry_tracks_connections(app, db, org_a, sock):
    from app.models import User
    u = User(email=f'rt-{uuid.uuid4().hex[:6]}@a.test', name='rt', organization_id=org_a.id, is_active=True)
    db.session.add(u)
    db.session.commit()
    c1, c2 = sock(u), sock(u)
    sids = realtime.user_sids(u.id)
    assert len(sids) == 2
    c1.disconnect()
    assert len(realtime.user_sids(u.id)) == 1
    assert realtime.disconnect_user_sockets(u.id) == 1
    assert not c2.is_connected()
    assert realtime.user_sids(u.id) == []


def test_evict_user_from_incident(sock, users, make_incident):
    op = users['Operator']
    inc = make_incident(tlp='amber', assign=[op])
    victim, other = sock(op), sock(users['Administrator'])
    _join(victim, inc)
    _join(other, inc)
    victim.get_received()
    other.get_received()

    assert realtime.evict_user_from_incident(op.id, inc.id) is True
    assert _events(victim, 'incident:access_revoked') == [{'incident_id': str(inc.id)}]
    states = _events(other, 'presence:state')
    assert states and str(op.id) not in [u['user_id'] for u in states[-1]['users']]

    realtime.emit_change(inc.id, 'task', 'created', data={'id': str(uuid.uuid4())})
    realtime.emit_change(inc.id, 'incident', 'updated', data={'id': str(inc.id)})
    assert _events(victim, 'entity:changed') == []
    assert len(_events(other, 'entity:changed')) == 2
    # The stale membership is dropped: presence updates are now denied.
    victim.emit('presence:update', {'incident_id': str(inc.id), 'mode': 'viewing'})
    assert _events(victim, 'rt:error') == [{'code': 'denied', 'event': 'presence:update'}]


def test_notify_permissions_changed(app, db, org_a, sock):
    from app.models import User
    u = User(email=f'rt-{uuid.uuid4().hex[:6]}@a.test', name='rt', organization_id=org_a.id, is_active=True)
    db.session.add(u)
    db.session.commit()
    c = sock(u)
    realtime.notify_permissions_changed([u.id])
    assert not c.is_connected()


# ---------------------------------------------------------------------------
# Cross-worker helpers with a mocked emitter / message queue
# ---------------------------------------------------------------------------

class FakeServer:
    def __init__(self):
        self.calls = []

    def leave_room(self, sid, room, namespace=None):
        self.calls.append(('leave_room', sid, room, namespace))

    def disconnect(self, sid, namespace=None):
        self.calls.append(('disconnect', sid, namespace))

    def close_room(self, room, namespace=None):
        self.calls.append(('close_room', room, namespace))


class FakeEmitter:
    def __init__(self):
        self.server = FakeServer()
        self.emits = []

    def emit(self, event, data=None, to=None, **kw):
        self.emits.append((event, data, to))


@pytest.fixture
def fake_emitter():
    fake = FakeEmitter()
    realtime.set_emitter(fake)
    yield fake
    realtime.set_emitter(None)


def test_cross_worker_eviction_uses_queue_propagated_calls(fake_emitter):
    uid, iid = str(uuid.uuid4()), str(uuid.uuid4())
    realtime.register_sid(uid, 'sid-on-worker-2')
    try:
        realtime.evict_user_from_incident(uid, iid)
        leaves = [c for c in fake_emitter.server.calls if c[0] == 'leave_room']
        assert {c[2] for c in leaves} == set(realtime.all_rooms(iid))
        assert all(c[1] == 'sid-on-worker-2' and c[3] == '/' for c in leaves)
        assert ('incident:access_revoked', {'incident_id': iid}, f'user_{uid}') in fake_emitter.emits

        realtime.notify_permissions_changed(uid)
        assert ('permissions_changed', {}, f'user_{uid}') in fake_emitter.emits
        assert ('disconnect', 'sid-on-worker-2', '/') in fake_emitter.server.calls
        assert realtime.user_sids(uid) == []
    finally:
        realtime.unregister_sid(uid, 'sid-on-worker-2')


def test_emit_helpers_target_scope_rooms(fake_emitter):
    iid = str(uuid.uuid4())
    realtime.emit_change(iid, 'malware', 'created', data={'id': 'm'})
    realtime.emit_change(iid, 'incident', 'updated', data={'id': iid})
    realtime.emit_to_user('u1', 'session:revoked', {'reason': 'x'})
    realtime.close_incident_rooms(iid)
    targets = [(e[0], e[2]) for e in fake_emitter.emits]
    assert ('entity:changed', f'incident_{iid}:malware') in targets
    assert ('entity:changed', f'incident_{iid}') in targets
    assert ('session:revoked', 'user_u1') in targets
    closed = {c[1] for c in fake_emitter.server.calls if c[0] == 'close_room'}
    assert closed == set(realtime.all_rooms(iid))


def test_cli_uses_write_only_emitter(app, monkeypatch):
    import flask_socketio
    created = []

    class FakeSocketIO:
        def __init__(self, app=None, **kw):
            created.append((app, kw))

    monkeypatch.setattr(flask_socketio, 'SocketIO', FakeSocketIO)
    monkeypatch.setattr(realtime, '_in_cli', lambda: True)
    monkeypatch.setattr(realtime, '_write_only_emitter', None)
    monkeypatch.setitem(app.config, 'TESTING', False)
    monkeypatch.setitem(app.config, 'REDIS_URL', 'redis://example:6379/0')
    emitter = realtime.get_emitter()
    assert isinstance(emitter, FakeSocketIO)
    assert created == [(None, {'message_queue': 'redis://example:6379/0'})]
    assert realtime.get_emitter() is emitter        # cached

    monkeypatch.setattr(realtime, '_in_cli', lambda: False)
    from app import socketio
    assert realtime.get_emitter() is socketio
