"""W1-RT-EMIT: every incident-entity mutation emits one ``entity:changed``
to its scope room *after* commit (never on a failed/rolled-back write), PUT/
PATCH/DELETE on versioned rows honour If-Match / ``expected_version``, and
GET-one / update responses carry an ETag."""
import io
import os
import re
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services import realtime

API = '/api/v1'

# entity -> table (for the "already committed" check done at emit time).
TABLES = {
    'incident': 'incidents', 'assignment': 'incident_assignments', 'timeline_event': 'timeline_events',
    'task': 'tasks', 'task_comment': 'task_comments', 'case_note': 'case_notes',
    'host': 'compromised_hosts', 'account': 'compromised_accounts', 'network_ioc': 'network_indicators',
    'host_ioc': 'host_based_indicators', 'malware': 'malware_tools', 'artifact': 'artifacts',
    'graph_node': 'attack_graph_nodes', 'graph_edge': 'attack_graph_edges', 'playbook': 'incident_playbooks',
}
VERSIONED = {'incident', 'timeline_event', 'task', 'case_note', 'host', 'account', 'network_ioc',
             'host_ioc', 'malware', 'graph_node', 'graph_edge', 'playbook'}


class _Server:
    def __init__(self):
        self.calls = []

    def leave_room(self, sid, room, namespace=None):
        self.calls.append(('leave_room', sid, room))

    def disconnect(self, sid, namespace=None):
        self.calls.append(('disconnect', sid))

    def close_room(self, room, namespace=None):
        self.calls.append(('close_room', room))


class CommitCheckingEmitter:
    """Records emits; for each ``entity:changed`` it reads the row on a
    separate connection, i.e. it only sees what was already COMMITTED."""

    def __init__(self, engine):
        self.engine = engine
        self.server = _Server()
        self.emits = []
        self.committed = []

    def emit(self, event, data=None, to=None, **kw):
        self.emits.append((event, data, to))
        if event == 'entity:changed':
            self.committed.append(self._committed_state(data))

    def _committed_state(self, env):
        table = TABLES[env['entity']]
        with self.engine.connect() as conn:
            conn.execute(text("SET LOCAL lock_timeout = '2s'"))
            conn.execute(text("SET LOCAL statement_timeout = '5s'"))
            cols = 'version' if env['entity'] in VERSIONED else 'id'
            if env['entity'] == 'case_note':
                cols += ', is_archived'
            row = conn.execute(text(f'SELECT {cols} FROM {table} WHERE id = :i'), {'i': env['id']}).first()
            conn.rollback()
        return row

    def changes(self):
        return [(d, to) for e, d, to in self.emits if e == 'entity:changed']

    def clear(self):
        self.emits.clear()
        self.committed.clear()
        self.server.calls.clear()


@pytest.fixture
def rt(app, db):
    fake = CommitCheckingEmitter(db.engine)
    realtime.set_emitter(fake)
    yield fake
    realtime.set_emitter(None)


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


def _ok(resp, *codes):
    assert resp.status_code in (codes or (200, 201)), (resp.status_code, resp.get_json())
    return resp.get_json()


# ---------------------------------------------------------------------------
# Object factories (through the API, so they also exercise the create emits)
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc).isoformat()


def make_timeline_event(c, inc):
    return _ok(c.post(f'{API}/incidents/{inc.id}/timeline', json={'timestamp': _now(), 'activity': 'ran x'}))


def make_task(c, inc):
    return _ok(c.post(f'{API}/incidents/{inc.id}/tasks', json={'title': 'collect memory'}))


def make_comment(c, inc):
    task = make_task(c, inc)
    body = _ok(c.post(f"{API}/incidents/{inc.id}/tasks/{task['id']}/comments", json={'content': 'hi'}))
    return dict(body, task_id=task['id'])


def make_note(c, inc):
    return _ok(c.post(f'{API}/incidents/{inc.id}/case-notes', json={'title': 'n', 'content': 'body'}))


def make_host(c, inc):
    return _ok(c.post(f'{API}/incidents/{inc.id}/hosts', json={'hostname': f'ws-{uuid.uuid4().hex[:6]}'}))


def make_account(c, inc):
    return _ok(c.post(f'{API}/incidents/{inc.id}/accounts',
                      json={'account_name': 'svc', 'datetime_seen': _now(), 'password': 'hunter2'}))


def make_network_ioc(c, inc):
    return _ok(c.post(f'{API}/incidents/{inc.id}/network-iocs', json={'dns_ip': '203.0.113.7', 'auto_enrich': False}))


def make_host_ioc(c, inc):
    return _ok(c.post(f'{API}/incidents/{inc.id}/host-iocs', json={'artifact_type': 'file', 'artifact_value': 'x.exe'}))


def make_malware(c, inc):
    return _ok(c.post(f'{API}/incidents/{inc.id}/malware', json={'file_name': 'evil.dll'}))


def make_node(c, inc):
    return _ok(c.post(f'{API}/incidents/{inc.id}/attack-graph/nodes', json={'node_type': 'server', 'label': 'n'}))


def make_edge(c, inc):
    a, b = make_node(c, inc), make_node(c, inc)
    return _ok(c.post(f'{API}/incidents/{inc.id}/attack-graph/edges',
                      json={'source_node_id': a['id'], 'target_node_id': b['id'], 'edge_type': 'lateral_movement'}))


def make_playbook(c, inc):
    pb = _ok(c.post(f'{API}/playbooks', json={'name': 'PB', 'definition': {'phases': [
        {'phase': 1, 'name': 'Identification', 'tasks': [{'title': 't'}], 'actions': []}]}}))
    return _ok(c.post(f"{API}/incidents/{inc.id}/playbooks/{pb['id']}/activate"))['incident_playbook']


def make_artifact(db, inc, user):
    from app.models import Artifact
    a = Artifact(incident_id=inc.id, filename='f', original_filename='disk.e01', storage_path='none',
                 storage_type='google_drive', file_size=1, md5='1' * 32, sha256='1' * 64,
                 sha512='1' * 128, uploaded_by=user.id)
    db.session.add(a)
    db.session.commit()
    return {'id': str(a.id)}


# (case id, entity, op, factory, method, url, json body)
# url placeholders: {iid} incident, {oid} object, {tid} parent task.
EMIT_CASES = [
    ('incident-update', 'incident', 'updated', None, 'PUT', '/incidents/{iid}', {'title': 'Renamed'}),
    ('incident-status', 'incident', 'updated', None, 'PATCH', '/incidents/{iid}/status', {'status': 'investigating'}),
    ('timeline-create', 'timeline_event', 'created', None, 'POST', '/incidents/{iid}/timeline',
     {'timestamp': '2026-01-01T00:00:00Z', 'activity': 'logon'}),
    ('timeline-update', 'timeline_event', 'updated', make_timeline_event, 'PUT', '/incidents/{iid}/timeline/{oid}',
     {'activity': 'edited'}),
    ('timeline-delete', 'timeline_event', 'deleted', make_timeline_event, 'DELETE', '/incidents/{iid}/timeline/{oid}', None),
    ('task-create', 'task', 'created', None, 'POST', '/incidents/{iid}/tasks', {'title': 'triage'}),
    ('task-update', 'task', 'updated', make_task, 'PUT', '/incidents/{iid}/tasks/{oid}', {'status': 'in_progress'}),
    ('task-delete', 'task', 'deleted', make_task, 'DELETE', '/incidents/{iid}/tasks/{oid}', None),
    ('comment-create', 'task_comment', 'created', make_task, 'POST', '/incidents/{iid}/tasks/{oid}/comments',
     {'content': 'note'}),
    ('comment-delete', 'task_comment', 'deleted', make_comment, 'DELETE',
     '/incidents/{iid}/tasks/{tid}/comments/{oid}', None),
    ('note-create', 'case_note', 'created', None, 'POST', '/incidents/{iid}/case-notes', {'title': 't', 'content': 'c'}),
    ('note-update', 'case_note', 'updated', make_note, 'PUT', '/incidents/{iid}/case-notes/{oid}', {'content': 'c2'}),
    ('note-delete', 'case_note', 'deleted', make_note, 'DELETE', '/incidents/{iid}/case-notes/{oid}', None),
    ('host-create', 'host', 'created', None, 'POST', '/incidents/{iid}/hosts', {'hostname': 'dc01'}),
    ('host-update', 'host', 'updated', make_host, 'PUT', '/incidents/{iid}/hosts/{oid}', {'notes': 'imaged'}),
    ('host-delete', 'host', 'deleted', make_host, 'DELETE', '/incidents/{iid}/hosts/{oid}', None),
    ('account-create', 'account', 'created', None, 'POST', '/incidents/{iid}/accounts',
     {'account_name': 'adm', 'datetime_seen': '2026-01-01T00:00:00Z', 'password': 'p@ss'}),
    ('account-update', 'account', 'updated', make_account, 'PUT', '/incidents/{iid}/accounts/{oid}', {'status': 'disabled'}),
    ('account-delete', 'account', 'deleted', make_account, 'DELETE', '/incidents/{iid}/accounts/{oid}', None),
    ('netioc-create', 'network_ioc', 'created', None, 'POST', '/incidents/{iid}/network-iocs',
     {'dns_ip': '198.51.100.1', 'auto_enrich': False}),
    ('netioc-update', 'network_ioc', 'updated', make_network_ioc, 'PUT', '/incidents/{iid}/network-iocs/{oid}',
     {'description': 'c2'}),
    ('netioc-delete', 'network_ioc', 'deleted', make_network_ioc, 'DELETE', '/incidents/{iid}/network-iocs/{oid}', None),
    ('hostioc-create', 'host_ioc', 'created', None, 'POST', '/incidents/{iid}/host-iocs',
     {'artifact_type': 'registry', 'artifact_value': 'HKLM\\Run'}),
    ('hostioc-update', 'host_ioc', 'updated', make_host_ioc, 'PUT', '/incidents/{iid}/host-iocs/{oid}', {'notes': 'n'}),
    ('hostioc-delete', 'host_ioc', 'deleted', make_host_ioc, 'DELETE', '/incidents/{iid}/host-iocs/{oid}', None),
    ('malware-create', 'malware', 'created', None, 'POST', '/incidents/{iid}/malware', {'file_name': 'm.exe'}),
    ('malware-update', 'malware', 'updated', make_malware, 'PUT', '/incidents/{iid}/malware/{oid}', {'is_tool': True}),
    ('malware-delete', 'malware', 'deleted', make_malware, 'DELETE', '/incidents/{iid}/malware/{oid}', None),
    ('node-create', 'graph_node', 'created', None, 'POST', '/incidents/{iid}/attack-graph/nodes',
     {'node_type': 'workstation', 'label': 'ws'}),
    ('node-update', 'graph_node', 'updated', make_node, 'PUT', '/incidents/{iid}/attack-graph/nodes/{oid}',
     {'label': 'renamed'}),
    ('node-delete', 'graph_node', 'deleted', make_node, 'DELETE', '/incidents/{iid}/attack-graph/nodes/{oid}', None),
    ('edge-update', 'graph_edge', 'updated', make_edge, 'PUT', '/incidents/{iid}/attack-graph/edges/{oid}',
     {'label': 'psexec'}),
    ('edge-delete', 'graph_edge', 'deleted', make_edge, 'DELETE', '/incidents/{iid}/attack-graph/edges/{oid}', None),
    ('playbook-advance', 'playbook', 'updated', make_playbook, 'PUT', '/incidents/{iid}/playbook/advance', None),
    ('playbook-task', 'playbook', 'updated', make_playbook, 'PUT', '/incidents/{iid}/playbook/task',
     {'task_key': 'p1-t0', 'done': True}),
    ('artifact-hold', 'artifact', 'updated', 'artifact', 'POST', '/incidents/{iid}/artifacts/{oid}/legal-hold',
     {'hold': False}),
    ('artifact-delete', 'artifact', 'deleted', 'artifact', 'DELETE', '/incidents/{iid}/artifacts/{oid}', None),
]


def _prepare(db, users, admin, inc, factory):
    if factory is None:
        return {}
    if factory == 'artifact':
        return make_artifact(db, inc, users['Administrator'])
    return factory(admin, inc)


def _url(template, inc, obj):
    return API + template.format(iid=inc.id, oid=obj.get('id'), tid=obj.get('task_id'))


def _expected_id(case_entity, op, inc, obj, body):
    if case_entity == 'incident':
        return str(inc.id)
    if case_entity == 'playbook':
        return obj['id']
    if op == 'created':
        return body['id']
    return obj['id']


def _check_committed(entity, op, env, committed):
    if op == 'deleted':
        if entity == 'case_note':   # soft delete
            assert committed is not None and committed.is_archived is True
        else:
            assert committed is None, f'{entity} still present when the delete was emitted'
        assert 'data' not in env
    else:
        assert committed is not None, f'{entity} not committed when the emit happened'
        if entity in VERSIONED:
            assert committed.version == env['version'], 'emitted version is not the committed one'
        assert env['data']['id'] == env['id']


@pytest.mark.parametrize('case', EMIT_CASES, ids=[c[0] for c in EMIT_CASES])
def test_mutation_emits_one_entity_changed_after_commit(rt, db, users, admin, make_incident, case):
    _, entity, op, factory, method, url, body = case
    inc = make_incident()
    obj = _prepare(db, users, admin, inc, factory)
    rt.clear()

    resp = admin.open(method, _url(url, inc, obj), json=body)
    data = _ok(resp)

    changes = [(env, to) for env, to in rt.changes() if env['entity'] == entity]
    assert len(changes) == 1, rt.emits
    env, room = changes[0]
    assert env['op'] == op and env['incident_id'] == str(inc.id)
    assert room == realtime.scope_room(str(inc.id), realtime.scope_for_entity(entity))
    assert env['id'] == _expected_id(entity, op, inc, obj, data)
    idx = [e for e, _ in rt.changes()].index(env)
    _check_committed(entity, op, env, rt.committed[idx])
    assert env['actor'] == {'id': str(users['Administrator'].id), 'name': users['Administrator'].name}


def test_create_emits_for_incident_assignment_and_mark_as_ioc(rt, db, users, admin, make_incident, fresh_user):
    inc = make_incident()
    analyst = fresh_user('Analyst')
    body = _ok(admin.post(f'{API}/incidents/{inc.id}/assignments', json={'user_id': str(analyst.id)}))
    (env, room), = [(e, r) for e, r in rt.changes() if e['entity'] == 'assignment']
    assert env['op'] == 'created' and env['id'] == body['id'] and room == f'incident_{inc.id}'

    rt.clear()
    _ok(admin.delete(f"{API}/incidents/{inc.id}/assignments/{body['id']}"))
    assert [(e['entity'], e['op'], e['id']) for e, _ in rt.changes()] == [('assignment', 'deleted', body['id'])]

    ev = make_timeline_event(admin, inc)
    rt.clear()
    out = _ok(admin.post(f"{API}/incidents/{inc.id}/timeline/{ev['id']}/mark-as-ioc", json={'artifact_type': 'file'}))
    got = {(e['entity'], e['op'], e['id']) for e, _ in rt.changes()}
    assert got == {('timeline_event', 'updated', ev['id']), ('host_ioc', 'created', out['ioc']['id'])}
    assert all(c is not None for c in rt.committed)

    rt.clear()
    created = _ok(admin.post(f'{API}/incidents', json={'title': 'New one', 'severity': 'low'}))
    assert [(e['entity'], e['op'], e['id']) for e, _ in rt.changes()] == [('incident', 'created', created['id'])]


def test_network_ioc_with_graph_node_emits_both(rt, admin, make_incident):
    inc = make_incident()
    _ok(admin.post(f'{API}/incidents/{inc.id}/network-iocs',
                   json={'dns_ip': '192.0.2.10', 'auto_enrich': False, 'add_to_attack_graph': True}))
    assert sorted(e['entity'] for e, _ in rt.changes()) == ['graph_node', 'network_ioc']


def test_artifact_upload_emits_created(rt, monkeypatch, admin, make_incident):
    from app.api.v1.endpoints import artifacts
    monkeypatch.setattr(artifacts, '_try_google_drive_primary', lambda *a, **k: None)
    monkeypatch.setattr(artifacts.storage_service, 'store_file', lambda *a, **k: (True, 'local'))
    inc = make_incident()
    resp = admin.post(f'{API}/incidents/{inc.id}/artifacts', data={'file': (io.BytesIO(b'evidence'), 'e.bin')},
                      content_type='multipart/form-data')
    body = _ok(resp)
    (env, room), = rt.changes()
    assert (env['entity'], env['op'], env['id']) == ('artifact', 'created', body['id'])
    assert room == f'incident_{inc.id}:artifacts'
    assert 'storage_path' not in env['data'] and 'extra_data' not in env['data']
    assert rt.committed[0] is not None


def test_account_payload_masked_over_socket(rt, admin, make_incident):
    inc = make_incident()
    make_account(admin, inc)
    (env, _), = [(e, r) for e, r in rt.changes() if e['entity'] == 'account']
    assert 'hunter2' not in repr(env)


def test_bulk_operations_resync(rt, monkeypatch, admin, make_incident):
    inc = make_incident()
    _ok(admin.post(f'{API}/incidents/{inc.id}/attack-graph/auto-generate'), 200, 201)
    assert ('incident:resync', {'incident_id': str(inc.id), 'scopes': ['attack_graph'], 'reason': 'auto_generate'},
            f'incident_{inc.id}:attack_graph') in rt.emits

    rt.clear()
    from app.services import import_service
    monkeypatch.setattr(import_service.ImportService, 'bulk_create_entities',
                        staticmethod(lambda *a, **k: {'created': 0}))
    _ok(admin.post(f'{API}/incidents/{inc.id}/import/submit', json={'hosts': []}))
    scopes = {d['scopes'][0] for e, d, _ in rt.emits if e == 'incident:resync'}
    assert scopes == set(realtime.SCOPE_PERMS)


def test_playbook_actions_resync_their_scopes(rt, admin, make_incident):
    inc = make_incident()
    pb = _ok(admin.post(f'{API}/playbooks', json={'name': 'PB', 'definition': {'phases': [
        {'phase': 1, 'name': 'Identification', 'tasks': [],
         'actions': [{'key': 'c', 'type': 'create_task', 'auto_run': True, 'config': {'title': 'auto'}}]}]}}))
    _ok(admin.post(f"{API}/incidents/{inc.id}/playbooks/{pb['id']}/activate"))
    assert ('incident:resync', {'incident_id': str(inc.id), 'scopes': ['tasks'], 'reason': 'playbook_action'},
            f'incident_{inc.id}:tasks') in rt.emits
    assert [(e['entity'], e['op']) for e, _ in rt.changes()] == [('playbook', 'created')]


# ---------------------------------------------------------------------------
# Not on rollback
# ---------------------------------------------------------------------------

def test_failed_validation_emits_nothing(rt, admin, make_incident):
    inc = make_incident()
    task = make_task(admin, inc)
    rt.clear()
    assert admin.put(f"{API}/incidents/{inc.id}/tasks/{task['id']}", json={'priority': 'bogus'}).status_code == 400
    assert admin.post(f'{API}/incidents/{inc.id}/hosts', json={}).status_code == 400
    assert rt.changes() == []


def test_concurrent_writer_conflict_rolls_back_and_emits_nothing(rt, db, monkeypatch, admin, make_incident):
    """StaleDataError at commit (another writer won the race) -> 409, the
    change is rolled back and nothing is broadcast."""
    from sqlalchemy.orm.exc import StaleDataError
    inc = make_incident()
    task = make_task(admin, inc)
    rt.clear()
    real_commit = db.session.commit
    calls = []

    def stale_once():
        if not calls:
            calls.append(1)
            raise StaleDataError('simulated concurrent update')
        return real_commit()

    monkeypatch.setattr(db.session, 'commit', stale_once)
    resp = admin.put(f"{API}/incidents/{inc.id}/tasks/{task['id']}", json={'title': 'mine'})
    monkeypatch.undo()
    assert resp.status_code == 409 and resp.get_json()['error'] == 'conflict'
    assert resp.get_json()['current']['title'] == 'collect memory'
    assert rt.changes() == []
    db.session.expire_all()
    from app.models import Task
    assert db.session.get(Task, task['id']).title == 'collect memory'


# ---------------------------------------------------------------------------
# If-Match / expected_version / ETag
# ---------------------------------------------------------------------------

# (case id, factory, method, url, body, get-one url or None)
PRECONDITION_CASES = [
    ('incident', None, 'PUT', '/incidents/{iid}', {'title': 'Second title'}, '/incidents/{iid}'),
    ('incident-status', None, 'PATCH', '/incidents/{iid}/status', {'status': 'contained'}, None),
    ('timeline_event', make_timeline_event, 'PUT', '/incidents/{iid}/timeline/{oid}', {'activity': 'a2'}, None),
    ('task', make_task, 'PUT', '/incidents/{iid}/tasks/{oid}', {'title': 't2'}, '/incidents/{iid}/tasks/{oid}'),
    ('case_note', make_note, 'PUT', '/incidents/{iid}/case-notes/{oid}', {'content': 'c2'},
     '/incidents/{iid}/case-notes/{oid}'),
    ('host', make_host, 'PUT', '/incidents/{iid}/hosts/{oid}', {'notes': 'x'}, None),
    ('account', make_account, 'PUT', '/incidents/{iid}/accounts/{oid}', {'notes': 'x'},
     '/incidents/{iid}/accounts/{oid}'),
    ('network_ioc', make_network_ioc, 'PUT', '/incidents/{iid}/network-iocs/{oid}', {'port': 443}, None),
    ('host_ioc', make_host_ioc, 'PUT', '/incidents/{iid}/host-iocs/{oid}', {'notes': 'x'}, None),
    ('malware', make_malware, 'PUT', '/incidents/{iid}/malware/{oid}', {'description': 'x'}, None),
    ('graph_node', make_node, 'PUT', '/incidents/{iid}/attack-graph/nodes/{oid}', {'label': 'x'}, None),
    ('graph_edge', make_edge, 'PUT', '/incidents/{iid}/attack-graph/edges/{oid}', {'label': 'x'}, None),
    ('playbook-advance', make_playbook, 'PUT', '/incidents/{iid}/playbook/advance', None, '/incidents/{iid}/playbook'),
    ('playbook-task', make_playbook, 'PUT', '/incidents/{iid}/playbook/task', {'task_key': 'k', 'done': True}, None),
]


def _current_version(admin, inc, obj, factory):
    if factory is None:
        return _ok(admin.get(f'{API}/incidents/{inc.id}'))['version']
    return obj['version']


@pytest.mark.parametrize('case', PRECONDITION_CASES, ids=[c[0] for c in PRECONDITION_CASES])
def test_if_match_precondition(rt, db, users, admin, make_incident, case):
    _, factory, method, url, body, get_url = case
    inc = make_incident()
    obj = _prepare(db, users, admin, inc, factory)
    version = _current_version(admin, inc, obj, factory)
    target = _url(url, inc, obj)
    rt.clear()

    # Stale If-Match -> 409 conflict with the current row, nothing written or emitted.
    stale = admin.open(method, target, json=body, headers={'If-Match': f'"{version + 7}"'})
    assert stale.status_code == 409, stale.get_json()
    payload = stale.get_json()
    assert payload['error'] == 'conflict' and payload['current_version'] == version
    assert payload['current'] is not None and stale.headers['ETag'] == f'"{version}"'
    assert rt.changes() == []

    # Stale body expected_version -> 409 as well.
    stale_body = dict(body or {}, expected_version=version + 7)
    assert admin.open(method, target, json=stale_body).status_code == 409

    # Matching If-Match -> 200, version bumped, ETag set.
    ok = admin.open(method, target, json=body, headers={'If-Match': f'W/"{version}"'})
    assert ok.status_code == 200, ok.get_json()
    new_etag = ok.headers.get('ETag')
    assert new_etag and int(new_etag.strip('"')) > version

    # No If-Match: last-write-wins still works (required=False).
    again = admin.open(method, target, json=body)
    assert again.status_code == 200, again.get_json()

    if get_url:
        got = admin.get(_url(get_url, inc, obj))
        assert got.status_code == 200 and re.fullmatch(r'"\d+"', got.headers['ETag'])


DELETE_CASES = [
    ('timeline_event', make_timeline_event, '/incidents/{iid}/timeline/{oid}'),
    ('task', make_task, '/incidents/{iid}/tasks/{oid}'),
    ('case_note', make_note, '/incidents/{iid}/case-notes/{oid}'),
    ('host', make_host, '/incidents/{iid}/hosts/{oid}'),
    ('account', make_account, '/incidents/{iid}/accounts/{oid}'),
    ('network_ioc', make_network_ioc, '/incidents/{iid}/network-iocs/{oid}'),
    ('host_ioc', make_host_ioc, '/incidents/{iid}/host-iocs/{oid}'),
    ('malware', make_malware, '/incidents/{iid}/malware/{oid}'),
    ('graph_node', make_node, '/incidents/{iid}/attack-graph/nodes/{oid}'),
    ('graph_edge', make_edge, '/incidents/{iid}/attack-graph/edges/{oid}'),
]


@pytest.mark.parametrize('case', DELETE_CASES, ids=[c[0] for c in DELETE_CASES])
def test_delete_honours_stale_if_match(rt, db, users, admin, make_incident, case):
    entity, factory, url = case
    inc = make_incident()
    obj = factory(admin, inc)
    target = _url(url, inc, obj)
    rt.clear()
    stale = admin.delete(target, headers={'If-Match': f'"{obj["version"] + 1}"'})
    assert stale.status_code == 409 and stale.get_json()['current_version'] == obj['version']
    assert rt.changes() == []
    assert admin.delete(target, headers={'If-Match': f'"{obj["version"]}"'}).status_code == 200
    assert [(e['entity'], e['op']) for e, _ in rt.changes()] == [(entity, 'deleted')]


def test_update_response_etag_matches_body_version(admin, make_incident):
    inc = make_incident()
    task = make_task(admin, inc)
    resp = admin.put(f"{API}/incidents/{inc.id}/tasks/{task['id']}", json={'title': 'x'})
    assert resp.headers['ETag'] == f'"{resp.get_json()["version"]}"'


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------

def test_archive_revokes_and_closes_rooms(rt, admin, make_incident):
    inc = make_incident()
    _ok(admin.post(f'{API}/incidents/{inc.id}/archive'))
    assert ('incident:access_revoked', {'incident_id': str(inc.id), 'reason': 'archived'},
            f'incident_{inc.id}') in rt.emits
    closed = {c[1] for c in rt.server.calls if c[0] == 'close_room'}
    assert closed == set(realtime.all_rooms(str(inc.id)))


def test_remove_assignment_evicts_only_users_who_lost_access(rt, db, users, admin, make_incident, fresh_user):
    inc = make_incident()
    operator = fresh_user('Operator')          # sees assigned incidents only
    manager = fresh_user('Manager')            # incidents:read_all
    ids = {}
    for u in (operator, manager):
        ids[u.id] = _ok(admin.post(f'{API}/incidents/{inc.id}/assignments', json={'user_id': str(u.id)}))['id']
        realtime.register_sid(u.id, f'sid-{u.id}')
    try:
        rt.clear()
        for u in (operator, manager):
            _ok(admin.delete(f'{API}/incidents/{inc.id}/assignments/{ids[u.id]}'))
        revoked = [to for e, d, to in rt.emits if e == 'incident:access_revoked']
        assert revoked == [f'user_{operator.id}']
        left = {c[1] for c in rt.server.calls if c[0] == 'leave_room'}
        assert left == {f'sid-{operator.id}'}
    finally:
        for u in (operator, manager):
            realtime.unregister_sid(u.id, f'sid-{u.id}')


def test_tlp_change_evicts_present_viewer(rt, db, users, admin, make_incident, fresh_user):
    inc = make_incident(tlp='white')
    viewer = fresh_user('Viewer')
    realtime.presence_set(str(inc.id), 'pid-viewer', {'user_id': str(viewer.id), 'name': 'v', 'focus': None,
                                                     'mode': 'viewing', 'since': _now()})
    realtime.register_sid(viewer.id, 'sid-viewer')
    try:
        rt.clear()
        _ok(admin.put(f'{API}/incidents/{inc.id}', json={'tlp': 'amber'}))
        assert ('incident:access_revoked', {'incident_id': str(inc.id), 'reason': 'access_removed'},
                f'user_{viewer.id}') in rt.emits
    finally:
        realtime.unregister_sid(viewer.id, 'sid-viewer')
        realtime.presence_remove(str(inc.id), 'pid-viewer')


def test_team_membership_removal_disconnects_sockets(rt, db, users, admin, fresh_user):
    member = fresh_user('Analyst')
    team = _ok(admin.post(f'{API}/teams', json={'name': f'team-{uuid.uuid4().hex[:6]}'}))
    _ok(admin.post(f"{API}/teams/{team['id']}/members", json={'user_id': str(member.id)}))
    realtime.register_sid(member.id, 'sid-member')
    try:
        _ok(admin.delete(f"{API}/teams/{team['id']}/members/{member.id}"))
        assert ('disconnect', 'sid-member') in rt.server.calls
    finally:
        realtime.unregister_sid(member.id, 'sid-member')


def _team(db, org_id, *members):
    from app.models import Team, TeamMember
    team = Team(organization_id=org_id, name=f'ir-{uuid.uuid4().hex[:6]}')
    db.session.add(team)
    db.session.flush()
    db.session.add_all([TeamMember(team_id=team.id, user_id=m.id) for m in members])
    db.session.commit()
    return team


def test_incident_team_changes_evict_users_who_lost_access(rt, db, users, admin, make_incident, fresh_user):
    """Team scope: an incident without teams is org-wide for read_team users;
    linking a team restricts it, unlinking a member's team revokes it."""
    from app.models import IncidentTeam
    inc = make_incident()
    member, outsider = fresh_user('Analyst'), fresh_user('Analyst')     # incidents:read_team
    team_a, team_b = _team(db, inc.organization_id, member), _team(db, inc.organization_id)
    realtime.presence_set(str(inc.id), 'pid-out', {'user_id': str(outsider.id), 'name': 'o', 'focus': None,
                                                  'mode': 'viewing', 'since': _now()})
    for u in (member, outsider):
        realtime.register_sid(u.id, f'sid-{u.id}')
    try:
        # Linking team A makes the incident team-restricted: the present outsider is evicted.
        rt.clear()
        _ok(admin.post(f'{API}/incidents/{inc.id}/teams', json={'team_id': str(team_a.id)}))
        revoked = [to for e, d, to in rt.emits if e == 'incident:access_revoked']
        assert revoked == [f'user_{outsider.id}']
        assert [(e['entity'], e['op']) for e, _ in rt.changes()] == [('incident', 'updated')]

        # Unlinking team A while team B stays: team A's member loses access.
        db.session.add(IncidentTeam(incident_id=inc.id, team_id=team_b.id))
        db.session.commit()
        rt.clear()
        _ok(admin.delete(f'{API}/incidents/{inc.id}/teams/{team_a.id}'))
        revoked = [to for e, d, to in rt.emits if e == 'incident:access_revoked']
        assert revoked == [f'user_{member.id}']
        assert [(e['entity'], e['op']) for e, _ in rt.changes()] == [('incident', 'updated')]
    finally:
        for u in (member, outsider):
            realtime.unregister_sid(u.id, f'sid-{u.id}')
        realtime.presence_remove(str(inc.id), 'pid-out')


def test_purge_step_revokes_and_closes_rooms(rt, db, make_incident):
    """The post-commit step works on a deleted + committed instance (only
    its identity is left)."""
    from app.api.v1.endpoints.incidents import _purge_access_revoked
    inc = make_incident()
    iid = str(inc.id)
    db.session.delete(inc)
    db.session.commit()
    _purge_access_revoked(inc, None)
    assert ('incident:access_revoked', {'incident_id': iid, 'reason': 'purged'}, f'incident_{iid}') in rt.emits
    assert {c[1] for c in rt.server.calls if c[0] == 'close_room'} == set(realtime.all_rooms(iid))


def test_purge_step_accepts_a_context_dict(rt):
    from app.api.v1.endpoints.incidents import _purge_access_revoked
    iid = str(uuid.uuid4())
    _purge_access_revoked({'incident_id': iid})
    assert ('incident:access_revoked', {'incident_id': iid, 'reason': 'purged'}, f'incident_{iid}') in rt.emits


def test_purge_step_registered_when_purge_service_exists():
    try:
        from app.services import incident_purge
    except ImportError:
        pytest.skip('incident_purge (W1-EVD-CORE) not merged yet')
    import app.api.v1.endpoints.incidents as incidents_ep
    steps = repr(vars(incident_purge))
    assert 'access_revoked' in steps and incidents_ep._purge_access_revoked.__name__ in steps


# ---------------------------------------------------------------------------
# Legacy events are gone (C9)
# ---------------------------------------------------------------------------

ENDPOINT_FILES = ['incidents', 'timeline', 'tasks', 'case_notes', 'compromised', 'iocs', 'artifacts',
                  'attack_graph', 'playbooks', 'teams']


@pytest.mark.parametrize('name', ENDPOINT_FILES)
def test_no_legacy_socket_emits(name):
    import app.api.v1.endpoints as pkg
    path = os.path.join(os.path.dirname(pkg.__file__), f'{name}.py')
    with open(path, encoding='utf-8') as fh:
        src = fh.read()
    assert 'socketio.emit(' not in src
    assert not re.search(r"'\w+_(added|updated|deleted|created)'", src)
