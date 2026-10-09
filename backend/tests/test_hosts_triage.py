"""W2-DFIR-A: host triage and acquisition (surface-dfir §3.3): acquisition
allowlist, triage / acquisition filters, and the bulk PATCH (cap, incident
scoping, versioning, audit, one ``hosts`` resync)."""
import uuid

import pytest

from app.services import realtime

API = '/api/v1'


class FakeEmitter:
    def __init__(self):
        self.emits = []

    def emit(self, event, data=None, to=None, **kw):
        self.emits.append((event, data, to))


@pytest.fixture
def rt():
    fake = FakeEmitter()
    realtime.set_emitter(fake)
    yield fake
    realtime.set_emitter(None)


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


def _hosts_url(inc):
    return f'{API}/incidents/{inc.id}/hosts'


def _add(client, inc, hostname, **fields):
    r = client.post(_hosts_url(inc), json={'hostname': hostname, **fields})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# ── acquisition allowlist ─────────────────────────────────────────────────

def test_acquisition_status_validated_on_create_and_update(admin, make_incident):
    inc = make_incident()
    host = _add(admin, inc, 'WS-01', acquisition_status={
        'disk_imaged': True, 'memory_captured': False, 'acquired_at': '2026-10-01T12:00:00'})
    assert host['acquisition_status'] == {'disk_imaged': True, 'memory_captured': False,
                                          'acquired_at': '2026-10-01T12:00:00+00:00'}

    for bad in ({'disk_imaged': True, 'owner': 'x'}, {'disk_imaged': 'yes'}, ['disk_imaged'],
                {'acquired_at': 'not a date'}):
        r = admin.post(_hosts_url(inc), json={'hostname': 'WS-02', 'acquisition_status': bad})
        assert r.status_code == 400, bad

    url = f"{_hosts_url(inc)}/{host['id']}"
    r = admin.put(url, json={'acquisition_status': {'unknown': 1}})
    assert r.status_code == 400
    r = admin.put(url, json={'acquisition_status': {'forensically_sound': True, 'acquired_at': None}})
    assert r.status_code == 200
    assert r.get_json()['acquisition_status'] == {'forensically_sound': True, 'acquired_at': None}
    r = admin.put(url, json={'acquisition_status': None})
    assert r.status_code == 200 and r.get_json()['acquisition_status'] == {}


# ── filters / sort ────────────────────────────────────────────────────────

@pytest.fixture
def hosts(admin, make_incident):
    inc = make_incident()
    _add(admin, inc, 'mem-only', triage_status='suspicious', acquisition_status={'memory_captured': True})
    _add(admin, inc, 'full', triage_status='compromised',
         acquisition_status={'memory_captured': True, 'disk_imaged': True})
    _add(admin, inc, 'nothing', triage_status='clean')
    _add(admin, inc, 'pending')  # under_analysis by default
    return inc


def _names(admin, inc, query):
    r = admin.get(f'{_hosts_url(inc)}?{query}')
    assert r.status_code == 200, r.get_json()
    return sorted(h['hostname'] for h in r.get_json()['items'])


def test_triage_filter(admin, hosts):
    assert _names(admin, hosts, 'triage_status=under_analysis') == ['pending']
    assert _names(admin, hosts, 'triage_status=suspicious,compromised') == ['full', 'mem-only']
    r = admin.get(f'{_hosts_url(hosts)}?triage_status=owned')
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_filter'


def test_acquisition_filter_with_negation(admin, hosts):
    assert _names(admin, hosts, 'acquisition=memory_captured') == ['full', 'mem-only']
    assert _names(admin, hosts, 'acquisition=memory_captured,!disk_imaged') == ['mem-only']
    assert _names(admin, hosts, 'acquisition=!disk_imaged') == ['mem-only', 'nothing', 'pending']
    r = admin.get(f'{_hosts_url(hosts)}?acquisition=registry_dumped')
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_filter'


def test_sort_by_triage(admin, hosts):
    r = admin.get(f'{_hosts_url(hosts)}?sort=triage_status')
    assert [h['triage_status'] for h in r.get_json()['items']] == [
        'clean', 'compromised', 'suspicious', 'under_analysis']


# ── bulk PATCH ────────────────────────────────────────────────────────────

def test_bulk_update_happy_path(admin, make_incident, rt, db):
    from app.models import AuditLog, CompromisedHost
    inc = make_incident()
    created = [_add(admin, inc, f'ws-{i}') for i in range(3)]
    ids = [h['id'] for h in created]
    rt.emits.clear()

    r = admin.patch(f'{_hosts_url(inc)}/bulk', json={
        'host_ids': ids + [ids[0]], 'triage_status': 'clean', 'containment_status': 'isolated'})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['updated'] == 3 and [h['id'] for h in body['items']] == ids
    db.session.expire_all()
    for h in CompromisedHost.query.filter(CompromisedHost.id.in_(ids)).all():
        assert h.triage_status == 'clean' and h.containment_status == 'isolated'
        assert h.version == 2  # ORM update: optimistic-concurrency version bumped

    # Exactly one resync for the hosts scope; no per-row entity events.
    events = [(e, d) for e, d, _ in rt.emits if e in ('incident:resync', 'entity:changed')]
    assert [e for e, _ in events] == ['incident:resync']
    assert events[0][1] == {'incident_id': str(inc.id), 'scopes': ['hosts'], 'reason': 'bulk_update'}

    row = (AuditLog.query.filter_by(action='bulk_update', resource_type='compromised_host')
           .order_by(AuditLog.created_at.desc()).first())
    assert row is not None and row.status_code == 200
    assert sorted(row.details['host_ids']) == sorted(ids)
    assert row.details['triage_status'] == 'clean'


def test_bulk_update_rejects_foreign_and_bad_ids_atomically(admin, make_incident, db, rt):
    from app.models import CompromisedHost
    inc, other = make_incident(), make_incident()
    mine = _add(admin, inc, 'mine')
    foreign = _add(admin, other, 'foreign')
    url = f'{_hosts_url(inc)}/bulk'

    r = admin.patch(url, json={'host_ids': [mine['id'], foreign['id']], 'triage_status': 'clean'})
    assert r.status_code == 400
    assert r.get_json()['error'] == 'invalid_host_ids' and r.get_json()['invalid'] == [foreign['id']]
    r = admin.patch(url, json={'host_ids': [mine['id'], 'nope'], 'triage_status': 'clean'})
    assert r.status_code == 400 and r.get_json()['invalid'] == ['nope']
    db.session.expire_all()
    assert db.session.get(CompromisedHost, uuid.UUID(mine['id'])).triage_status == 'under_analysis'
    assert db.session.get(CompromisedHost, uuid.UUID(foreign['id'])).triage_status == 'under_analysis'
    assert not [e for e, _, _ in rt.emits if e == 'incident:resync']


@pytest.mark.parametrize('body', [
    {'host_ids': [], 'triage_status': 'clean'},
    {'host_ids': 'abc', 'triage_status': 'clean'},
    {'host_ids': ['00000000-0000-0000-0000-000000000001']},
    {'host_ids': ['00000000-0000-0000-0000-000000000001'], 'triage_status': 'owned'},
    {'host_ids': ['00000000-0000-0000-0000-000000000001'], 'containment_status': 'vaporized'},
    {'host_ids': ['00000000-0000-0000-0000-000000000001'], 'triage_status': 'clean', 'hostname': 'x'},
])
def test_bulk_update_input_validation(admin, make_incident, body):
    inc = make_incident()
    r = admin.patch(f'{_hosts_url(inc)}/bulk', json=body)
    assert r.status_code == 400, r.get_json()


def test_bulk_update_cap(admin, make_incident):
    inc = make_incident()
    ids = [str(uuid.uuid4()) for _ in range(501)]
    r = admin.patch(f'{_hosts_url(inc)}/bulk', json={'host_ids': ids, 'triage_status': 'clean'})
    assert r.status_code == 400 and '500' in r.get_json()['message']


def test_bulk_update_viewer_forbidden_and_cross_org(users, auth, make_incident, org_b, admin):
    viewer = users['Viewer']
    inc = make_incident(assign=[viewer])
    host = _add(admin, inc, 'ws')
    body = {'host_ids': [host['id']], 'triage_status': 'clean'}
    assert auth(viewer).patch(f'{_hosts_url(inc)}/bulk', json=body).status_code == 403
    # Another org's admin cannot reach the incident at all.
    r = auth(users['admin_b']).patch(f'{_hosts_url(inc)}/bulk', json=body)
    assert r.status_code in (403, 404)
