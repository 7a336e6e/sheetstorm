"""W2-DFIR-A: task evidence refs, lead filters and assignee / parent validation
(surface-dfir §3.4), plus the ``task_evidence_refs_backfill`` migration."""
import importlib.util
import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from app.services import realtime
from test_migrations import EXPECTED_HEAD, _current, _flask_db, scratch_db  # noqa: F401 (fixture)

API = '/api/v1'


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


@pytest.fixture
def ev(app, db, users, make_incident):
    """An incident with one record of each linkable type, plus a host in another incident."""
    from app.models import (CompromisedAccount, CompromisedHost, HostBasedIndicator, MalwareTool,
                            NetworkIndicator, TimelineEvent)
    admin_user = users['Administrator']
    inc, other = make_incident(), make_incident()
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    recs = {
        'host': CompromisedHost(incident_id=inc.id, hostname='WS-01', created_by=admin_user.id),
        'account': CompromisedAccount(incident_id=inc.id, account_name='svc_backup', domain='CORP',
                                      account_type='domain', datetime_seen=now, created_by=admin_user.id),
        'network_ioc': NetworkIndicator(incident_id=inc.id, dns_ip='198.51.100.7', created_by=admin_user.id),
        'host_ioc': HostBasedIndicator(incident_id=inc.id, artifact_type='file', artifact_value='C:\\x.exe',
                                       created_by=admin_user.id),
        'malware': MalwareTool(incident_id=inc.id, file_name='beacon.dll', created_by=admin_user.id),
        'timeline_event': TimelineEvent(incident_id=inc.id, timestamp=now, activity='psexec to DC',
                                        created_by=admin_user.id),
        'foreign': CompromisedHost(incident_id=other.id, hostname='OTHER', created_by=admin_user.id),
    }
    db.session.add_all(recs.values())
    db.session.commit()
    return {'inc': inc, 'other': other, **recs}


def _ref(t, obj):
    return {'evidence_type': t, 'evidence_id': str(obj.id)}


def _tasks(inc):
    return f'{API}/incidents/{inc.id}/tasks'


def _create(client, inc, **body):
    body.setdefault('title', 'Chase lateral movement')
    return client.post(_tasks(inc), json=body)


# ── evidence refs ─────────────────────────────────────────────────────────

def test_create_normalizes_aliases_and_resolves_labels(admin, ev):
    r = _create(admin, ev['inc'], task_type='investigative_lead', evidence_refs=[
        _ref('host', ev['host']),
        _ref('host_indicator', ev['host_ioc']),        # alias
        _ref('network_indicator', ev['network_ioc']),  # alias
        _ref('host', ev['host']),                      # duplicate
        _ref('account', ev['account']),
        _ref('malware', ev['malware']),
        _ref('timeline_event', ev['timeline_event']),
    ])
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    assert [x['evidence_type'] for x in body['evidence_refs']] == [
        'host', 'host_ioc', 'network_ioc', 'account', 'malware', 'timeline_event']
    labels = {e['evidence_type']: e['label'] for e in body['evidence']}
    assert labels['host'] == 'WS-01'
    assert labels['host_ioc'] == 'file: C:\\x.exe'
    assert labels['network_ioc'] == '198.51.100.7'
    assert labels['account'] == 'CORP\\svc_backup'
    assert labels['malware'] == 'beacon.dll'
    assert labels['timeline_event'].endswith('psexec to DC')
    assert not any(e['missing'] for e in body['evidence'])

    listed = admin.get(_tasks(ev['inc'])).get_json()['items']
    assert [e['label'] for e in listed[0]['evidence']][0] == 'WS-01'
    one = admin.get(f"{_tasks(ev['inc'])}/{body['id']}").get_json()
    assert len(one['evidence']) == 6


def test_cross_incident_ref_rejected_with_body_index(admin, ev, db):
    from app.models import Task
    before = Task.query.filter_by(incident_id=ev['inc'].id).count()
    r = _create(admin, ev['inc'], evidence_refs=[_ref('host', ev['host']), _ref('host', ev['foreign'])])
    assert r.status_code == 400
    body = r.get_json()
    assert body['error'] == 'invalid_evidence_refs'
    assert body['invalid'] == [{'index': 1, 'evidence_type': 'host', 'evidence_id': str(ev['foreign'].id),
                                'reason': 'not_found'}]
    assert Task.query.filter_by(incident_id=ev['inc'].id).count() == before


@pytest.mark.parametrize('refs, reason', [
    ([{'evidence_type': 'nope', 'evidence_id': str(uuid.uuid4())}], 'unknown_type'),
    ([{'evidence_type': 'case_note', 'evidence_id': str(uuid.uuid4())}], 'type_not_allowed'),
    ([{'evidence_type': 'host', 'evidence_id': 'not-a-uuid'}], 'invalid_id'),
    ([{'evidence_type': 'host', 'evidence_id': str(uuid.uuid4())}], 'not_found'),
    (['junk'], 'not_an_object'),
])
def test_bad_refs_rejected(admin, ev, refs, reason):
    r = _create(admin, ev['inc'], evidence_refs=refs)
    assert r.status_code == 400
    assert r.get_json()['error'] == 'invalid_evidence_refs'
    assert r.get_json()['invalid'][0]['reason'] == reason


def test_ref_list_shape_and_cap(admin, ev):
    assert _create(admin, ev['inc'], evidence_refs={'evidence_type': 'host'}).get_json()['error'] == \
        'invalid_evidence_refs'
    r = _create(admin, ev['inc'], evidence_refs=[_ref('host', ev['host'])] * 51)
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_evidence_refs'
    # 50 duplicates are fine and collapse to one ref.
    r = _create(admin, ev['inc'], evidence_refs=[_ref('host', ev['host'])] * 50)
    assert r.status_code == 201 and len(r.get_json()['evidence_refs']) == 1


def test_update_replaces_refs_and_cross_incident_rejected(admin, ev):
    task = _create(admin, ev['inc'], evidence_refs=[_ref('host', ev['host'])]).get_json()
    url = f"{_tasks(ev['inc'])}/{task['id']}"
    r = admin.put(url, json={'evidence_refs': [_ref('foreign_type', ev['host'])]})
    assert r.status_code == 400
    r = admin.put(url, json={'evidence_refs': [_ref('host', ev['foreign'])]})
    assert r.status_code == 400 and r.get_json()['invalid'][0]['reason'] == 'not_found'
    r = admin.put(url, json={'evidence_refs': [_ref('malware', ev['malware'])]})
    assert r.status_code == 200
    assert r.get_json()['evidence_refs'] == [_ref('malware', ev['malware'])]
    assert r.get_json()['evidence'][0]['label'] == 'beacon.dll'


def test_missing_after_delete_and_kept_on_edit(admin, ev, db):
    task = _create(admin, ev['inc'], evidence_refs=[_ref('host', ev['host']), _ref('malware', ev['malware'])]).get_json()
    url = f"{_tasks(ev['inc'])}/{task['id']}"
    host_url = f"{API}/incidents/{ev['inc'].id}/hosts/{ev['host'].id}"
    assert admin.delete(host_url).status_code == 200

    got = admin.get(url).get_json()
    host_ev = next(e for e in got['evidence'] if e['evidence_type'] == 'host')
    assert host_ev['missing'] is True and host_ev['label'] is None
    # Re-saving the task with the now-dangling ref still works (stored refs are kept).
    r = admin.put(url, json={'title': 'renamed', 'evidence_refs': got['evidence_refs']})
    assert r.status_code == 200, r.get_json()
    assert len(r.get_json()['evidence_refs']) == 2


def test_labels_restricted_without_read_permission(admin, ev, auth, make_user, org_a, db):
    from app.models import IncidentAssignment
    reader = make_user(org_a, perms=['incidents:read', 'incidents:read_team', 'tasks:read', 'hosts:read'])
    db.session.add(IncidentAssignment(incident_id=ev['inc'].id, user_id=reader.id,
                                      assigned_by=ev['inc'].created_by))
    db.session.commit()
    _create(admin, ev['inc'], evidence_refs=[_ref('host', ev['host']), _ref('account', ev['account'])])
    items = auth(reader).get(_tasks(ev['inc'])).get_json()['items']
    evidence = {e['evidence_type']: e for e in items[0]['evidence']}
    assert evidence['host']['label'] == 'WS-01'
    assert evidence['account']['label'] is None and evidence['account']['restricted'] is True


def test_socket_payload_never_carries_labels(admin, ev):
    class Fake:
        def __init__(self):
            self.emits = []

        def emit(self, event, data=None, to=None, **kw):
            self.emits.append((event, data, to))

    fake = Fake()
    realtime.set_emitter(fake)
    try:
        r = _create(admin, ev['inc'], evidence_refs=[_ref('host', ev['host'])])
        assert r.status_code == 201
    finally:
        realtime.set_emitter(None)
    payload = next(d for e, d, _ in fake.emits if e == 'entity:changed')['data']
    assert payload['evidence'] == [{'evidence_type': 'host', 'evidence_id': str(ev['host'].id),
                                    'label': None, 'missing': False}]


# ── assignee / parent ─────────────────────────────────────────────────────

def test_cross_org_assignee_rejected(admin, ev, users, db):
    from app.models import Task
    r = _create(admin, ev['inc'], assignee_id=str(users['admin_b'].id))
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_assignee'
    assert not Task.query.filter_by(incident_id=ev['inc'].id, assignee_id=users['admin_b'].id).count()

    task = _create(admin, ev['inc']).get_json()
    r = admin.put(f"{_tasks(ev['inc'])}/{task['id']}", json={'assignee_id': str(users['admin_b'].id)})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_assignee'


def test_inactive_unknown_and_malformed_assignee_rejected(admin, ev, fresh_user, db):
    inactive = fresh_user('Analyst', is_active=False)
    deactivated = fresh_user('Analyst')
    deactivated.deactivated_at = datetime.now(timezone.utc)
    db.session.commit()
    for bad in (str(inactive.id), str(deactivated.id), str(uuid.uuid4()), 'nope'):
        r = _create(admin, ev['inc'], assignee_id=bad)
        assert r.status_code == 400 and r.get_json()['error'] == 'invalid_assignee', bad


def test_same_org_assignee_accepted_and_cleared(admin, ev, users):
    analyst = users['Analyst']
    task = _create(admin, ev['inc'], assignee_id=str(analyst.id)).get_json()
    assert task['assignee']['id'] == str(analyst.id)
    r = admin.put(f"{_tasks(ev['inc'])}/{task['id']}", json={'assignee_id': ''})
    assert r.status_code == 200 and r.get_json()['assignee'] is None


def test_parent_must_be_same_incident_and_acyclic(admin, ev, make_incident):
    other_task = _create(admin, ev['other']).get_json()
    r = _create(admin, ev['inc'], parent_task_id=other_task['id'])
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_parent_task'

    parent = _create(admin, ev['inc'], title='parent').get_json()
    child = _create(admin, ev['inc'], title='child', parent_task_id=parent['id'])
    assert child.status_code == 201 and child.get_json()['parent_task_id'] == parent['id']
    child = child.get_json()

    url = f"{_tasks(ev['inc'])}/{parent['id']}"
    r = admin.put(url, json={'parent_task_id': parent['id']})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_parent_task'
    r = admin.put(url, json={'parent_task_id': child['id']})  # cycle
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_parent_task'
    r = admin.put(f"{_tasks(ev['inc'])}/{child['id']}", json={'parent_task_id': None})
    assert r.status_code == 200 and r.get_json()['parent_task_id'] is None


def test_direction_and_title_caps(admin, ev):
    r = _create(admin, ev['inc'], investigation_direction='x' * 5001)
    assert r.status_code == 400
    r = _create(admin, ev['inc'], investigation_direction=['not', 'text'])
    assert r.status_code == 400
    r = _create(admin, ev['inc'], title='t' * 501)
    assert r.status_code == 400
    r = _create(admin, ev['inc'], investigation_direction='x' * 5000)
    assert r.status_code == 201


def test_due_date_naive_is_utc(admin, ev):
    r = _create(admin, ev['inc'], due_date='2026-10-10T08:30:00')
    assert r.status_code == 201
    assert r.get_json()['due_date'].startswith('2026-10-10T08:30:00')
    assert r.get_json()['due_date'].endswith('+00:00')


# ── lead filters ──────────────────────────────────────────────────────────

def test_lead_filters_counts_and_include_comments(admin, ev):
    inc = ev['inc']
    _create(admin, inc, title='action')
    open_lead = _create(admin, inc, title='open lead', task_type='investigative_lead').get_json()
    fp = _create(admin, inc, title='fp lead', task_type='investigative_lead', lead_outcome='false_positive').get_json()
    _create(admin, inc, title='bad lead', task_type='investigative_lead', lead_outcome='confirmed_malicious')

    def titles(query):
        r = admin.get(f'{_tasks(inc)}?{query}')
        assert r.status_code == 200, r.get_json()
        return sorted(t['title'] for t in r.get_json()['items'])

    assert titles('task_type=investigative_lead') == ['bad lead', 'fp lead', 'open lead']
    assert titles('task_type=action_item') == ['action']
    assert titles('task_type=investigative_lead&lead_outcome=open') == ['open lead']
    assert titles('lead_outcome=open,false_positive&task_type=investigative_lead') == ['fp lead', 'open lead']

    r = admin.get(f'{_tasks(inc)}?lead_outcome=maybe')
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_filter'
    r = admin.get(f'{_tasks(inc)}?task_type=nope')
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_filter'

    body = admin.get(f'{_tasks(inc)}?task_type=investigative_lead&include_comments=false&lead_counts=true'
                     f'&sort=-updated_at').get_json()
    assert all('comments' not in t for t in body['items'])
    assert body['lead_counts'] == {'open': 1, 'false_positive': 1, 'confirmed_malicious': 1,
                                   'inconclusive': 0, 'resolved': 0}
    assert body['sort'] == '-updated_at'
    assert 'comments' in admin.get(_tasks(inc)).get_json()['items'][0]

    # Inline outcome update (leads view) moves the lead out of "open".
    r = admin.put(f"{_tasks(inc)}/{open_lead['id']}", json={'lead_outcome': 'resolved'})
    assert r.status_code == 200
    assert titles('task_type=investigative_lead&lead_outcome=open') == []
    assert fp['lead_outcome'] == 'false_positive'


def test_viewer_cannot_mutate_tasks(ev, users, auth, make_incident):
    viewer = users['Viewer']
    inc = make_incident(assign=[viewer])
    r = auth(viewer).post(_tasks(inc), json={'title': 'x'})
    assert r.status_code == 403


# ── migration: task_evidence_refs_backfill ───────────────────────────────

_MIGRATION = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'migrations', 'versions', 'task_evidence_refs_backfill.py')


def _migration_module():
    spec = importlib.util.spec_from_file_location('task_evidence_refs_backfill_mig', _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    # `alembic.op` is only a proxy at import time; the pure helpers don't touch it.
    spec.loader.exec_module(mod)
    return mod


def test_map_linked_entities_normalizes():
    mod = _migration_module()
    h, i = str(uuid.uuid4()), str(uuid.uuid4())
    assert mod.map_linked_entities([
        {'type': 'host', 'id': h.upper(), 'label': 'WS'},
        {'type': 'host_indicator', 'id': i, 'label': 'x'},
        {'type': 'host', 'id': h},
        {'type': 'bogus', 'id': h},
        {'type': 'malware', 'id': 'nope'},
        'junk',
    ]) == [{'evidence_type': 'host', 'evidence_id': h}, {'evidence_type': 'host_ioc', 'evidence_id': i}]
    assert mod.map_linked_entities(None) == []
    assert len(mod.map_linked_entities([{'type': 'host', 'id': str(uuid.uuid4())} for _ in range(60)])) == 50


def _seed_linked_tasks(url):
    eng = create_engine(url)
    host, ioc = uuid.uuid4(), uuid.uuid4()
    try:
        with eng.begin() as conn:
            def q(sql, **kw):
                return conn.execute(text(sql), kw)
            org = q("INSERT INTO organizations (name, slug, settings) VALUES ('tk', 'tk-org', '{}') RETURNING id").scalar()
            user = q("INSERT INTO users (organization_id, email, name) VALUES (:o, 'tk@x.test', 'tk') RETURNING id",
                     o=org).scalar()
            inc = q("INSERT INTO incidents (organization_id, title, severity, status, phase, created_by) "
                    "VALUES (:o, 'inc', 'high', 'open', 1, :u) RETURNING id", o=org, u=user).scalar()

            def task(title, extra, refs):
                return q("INSERT INTO tasks (incident_id, title, created_by, extra_data, evidence_refs) "
                         "VALUES (:i, :t, :u, CAST(:e AS jsonb), CAST(:r AS jsonb)) RETURNING id",
                         i=inc, t=title, u=user, e=json.dumps(extra), r=json.dumps(refs)).scalar()
            linked = [{'type': 'host', 'id': str(host), 'label': 'WS-01'},
                      {'type': 'host_indicator', 'id': str(ioc), 'label': 'evil.exe'},
                      {'type': 'host', 'id': str(host), 'label': 'dup'},
                      {'type': 'weird', 'id': str(host), 'label': 'skip'}]
            ids = {
                'legacy': task('legacy', {'linked_entities': linked, 'other': 1}, []),
                'legacy_null': task('legacy-null', {'linked_entities': linked[:1]}, None),
                'mcp': task('mcp', {'linked_entities': linked},
                            [{'evidence_type': 'malware', 'evidence_id': str(host)}]),
                'none': task('none', {}, []),
                'junk': task('junk', {'linked_entities': [{'type': 'nope', 'id': 'x'}]}, []),
            }
        return ids, str(host), str(ioc)
    finally:
        eng.dispose()


def _task_rows(url):
    eng = create_engine(url)
    try:
        with eng.connect() as conn:
            return {r['title']: r for r in conn.execute(text(
                'SELECT title, evidence_refs, extra_data, version FROM tasks')).mappings().all()}
    finally:
        eng.dispose()


def test_backfill_migration_round_trip(scratch_db):
    down = _migration_module().down_revision

    r = _flask_db(scratch_db, 'upgrade', down)
    assert r.returncode == 0, r.stderr[-3000:]
    _, host, ioc = _seed_linked_tasks(scratch_db)
    before = _task_rows(scratch_db)

    r = _flask_db(scratch_db, 'upgrade')
    assert r.returncode == 0, r.stderr[-3000:]
    assert _current(scratch_db) == EXPECTED_HEAD
    after = _task_rows(scratch_db)
    expected = [{'evidence_type': 'host', 'evidence_id': host}, {'evidence_type': 'host_ioc', 'evidence_id': ioc}]
    assert after['legacy']['evidence_refs'] == expected
    assert after['legacy']['extra_data'] == before['legacy']['extra_data']  # untouched
    assert after['legacy']['version'] == before['legacy']['version'] + 1
    assert after['legacy-null']['evidence_refs'] == expected[:1]
    assert after['mcp']['evidence_refs'] == before['mcp']['evidence_refs']  # existing refs win
    assert after['mcp']['version'] == before['mcp']['version']
    assert after['none']['evidence_refs'] == [] and after['junk']['evidence_refs'] == []

    # Downgrade clears only what the upgrade wrote; extra_data still has the source.
    r = _flask_db(scratch_db, 'downgrade', down)
    assert r.returncode == 0, r.stderr[-3000:]
    downgraded = _task_rows(scratch_db)
    assert downgraded['legacy']['evidence_refs'] == []
    assert downgraded['legacy-null']['evidence_refs'] == []
    assert downgraded['mcp']['evidence_refs'] == before['mcp']['evidence_refs']
    assert downgraded['legacy']['extra_data'] == before['legacy']['extra_data']

    # Re-upgrade restores the backfill (idempotent mapping).
    r = _flask_db(scratch_db, 'upgrade')
    assert r.returncode == 0, r.stderr[-3000:]
    assert _task_rows(scratch_db)['legacy']['evidence_refs'] == expected
    r = _flask_db(scratch_db, 'upgrade')  # no-op at head
    assert r.returncode == 0, r.stderr[-3000:]
    assert _task_rows(scratch_db)['legacy']['evidence_refs'] == expected
