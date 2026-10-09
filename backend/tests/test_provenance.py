"""W3-PROV: record provenance + host clock skew (decision-log-provenance
§3.2/§3.4/§3.5): normalization rules (offset / IANA / fixed offset / skew /
DST gap + fold), apply on create + update for events and the three IOC kinds,
same-incident source links, second-analyst verification, clock-skew routes and
the audited re-normalization, list filters, realtime and org isolation."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services import provenance_service as prov
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


@pytest.fixture
def inc(make_incident, users):
    return make_incident(assign=[users['Analyst'], users['Incident Responder']])


def _utc(s):
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def _timeline(inc):
    return f'{API}/incidents/{inc.id}/timeline'


def _host(client, inc, hostname='WS-01', **fields):
    r = client.post(f'{API}/incidents/{inc.id}/hosts', json={'hostname': hostname, **fields})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _set_skew(client, inc, host, seconds, basis='NTP offset measured against pool', **extra):
    r = client.put(f"{API}/incidents/{inc.id}/hosts/{host['id']}/clock-skew",
                   json={'clock_skew_seconds': seconds, 'clock_skew_basis': basis, **extra})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# -- environment ----------------------------------------------------------

def test_tzdata_available_in_image():
    """The backend image must resolve IANA names (system tzdata); the feature
    degrades to UTC+-HH:MM only otherwise (no new dependency was added)."""
    from zoneinfo import ZoneInfo
    assert ZoneInfo('Europe/Berlin').key == 'Europe/Berlin'
    assert ZoneInfo('America/New_York').key == 'America/New_York'


def test_migration_columns_exist(db):
    from sqlalchemy import text
    for table in ('timeline_events', 'network_indicators', 'host_based_indicators', 'malware_tools'):
        cols = set(db.session.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = :t"), {'t': table}).scalars())
        assert {'source_artifact_id', 'source_evidence_id', 'source_record_type', 'source_record_ref',
                'raw_timestamp', 'source_timezone', 'timestamp_type', 'timestamp_derivation',
                'clock_skew_applied_seconds', 'extraction_tool', 'extraction_tool_version',
                'provenance_verified_by', 'provenance_verified_at'} <= cols, table
    cols = set(db.session.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'compromised_hosts'")).scalars())
    assert {'clock_skew_seconds', 'clock_skew_basis', 'clock_skew_measured_by', 'clock_skew_measured_at',
            'timezone'} <= cols


# -- normalize (pure) -----------------------------------------------------

def test_normalize_offset_in_raw_timestamp():
    assert prov.normalize('2026-10-01T12:00:00+02:00').utc == _utc('2026-10-01T10:00:00+00:00')
    assert prov.normalize('2026-10-01 12:00:00Z').utc == _utc('2026-10-01T12:00:00+00:00')
    # An explicit offset wins over source_timezone.
    assert prov.normalize('2026-10-01T12:00:00+02:00', 'Asia/Tokyo').utc == _utc('2026-10-01T10:00:00+00:00')


def test_normalize_naive_with_iana_and_fixed_offset():
    assert prov.normalize('2026-07-01 12:00:00', 'Europe/Berlin').utc == _utc('2026-07-01T10:00:00+00:00')  # CEST
    assert prov.normalize('2026-01-01 12:00:00', 'Europe/Berlin').utc == _utc('2026-01-01T11:00:00+00:00')  # CET
    assert prov.normalize('2026-10-01 12:00', 'UTC+05:30').utc == _utc('2026-10-01T06:30:00+00:00')
    assert prov.normalize('2026-10-01 12:00', 'UTC-08:00').utc == _utc('2026-10-01T20:00:00+00:00')
    assert prov.normalize('2026-10-01 12:00', 'UTC').utc == _utc('2026-10-01T12:00:00+00:00')


def test_normalize_subtracts_host_clock_skew():
    # Host clock 300 s ahead: its 12:05 is really 12:00.
    r = prov.normalize('2026-10-01 12:05:00', 'UTC', 300)
    assert r.utc == _utc('2026-10-01T12:00:00+00:00') and r.skew_applied == 300
    # Host clock behind: negative skew adds.
    assert prov.normalize('2026-10-01 11:55:00', 'UTC', -300).utc == _utc('2026-10-01T12:00:00+00:00')
    # Default (host) time zone is used when the record has none.
    assert prov.normalize('2026-07-01 12:00', None, 0, default_timezone='Europe/Berlin').utc == \
        _utc('2026-07-01T10:00:00+00:00')


@pytest.mark.parametrize('raw, code', [
    ('2026-10-01 12:00:00', 'source_timezone_required'),
    ('2026-10-01', 'incomplete_raw_timestamp'),
    ('12:00:00', 'incomplete_raw_timestamp'),
    ('03/04/2026 12:00', 'ambiguous_date'),
    ('2026-10-01 12:00 EST', 'unknown_timezone_abbreviation'),
    ('not a date', 'invalid_raw_timestamp'),
    ('', 'invalid_raw_timestamp'),
])
def test_normalize_rejects_unusable_raw_timestamps(raw, code):
    with pytest.raises(prov.ProvenanceError) as exc:
        prov.normalize(raw, None)
    assert exc.value.code == code and exc.value.status == 400


def test_normalize_unambiguous_day_first_dates_are_accepted():
    assert prov.normalize('25/12/2026 08:00', 'UTC').utc == _utc('2026-12-25T08:00:00+00:00')
    assert prov.normalize('2026/04/03 08:00', 'UTC').utc == _utc('2026-04-03T08:00:00+00:00')


def test_normalize_dst_gap_and_fold():
    # 2026-03-29 02:30 does not exist in Berlin (clocks jump 02:00 -> 03:00).
    with pytest.raises(prov.ProvenanceError) as gap:
        prov.normalize('2026-03-29 02:30:00', 'Europe/Berlin')
    assert gap.value.code == 'nonexistent_local_time'
    # 2026-10-25 02:30 happens twice (CEST then CET).
    with pytest.raises(prov.ProvenanceError) as fold:
        prov.normalize('2026-10-25 02:30:00', 'Europe/Berlin')
    assert fold.value.code == 'ambiguous_local_time'
    assert fold.value.extra['candidates'] == ['2026-10-25T00:30:00+00:00', '2026-10-25T01:30:00+00:00']
    assert prov.normalize('2026-10-25 02:30:00', 'Europe/Berlin', fold=0).utc == _utc('2026-10-25T00:30:00+00:00')
    assert prov.normalize('2026-10-25 02:30:00', 'Europe/Berlin', fold=1).utc == _utc('2026-10-25T01:30:00+00:00')


@pytest.mark.parametrize('name', ['Mars/Olympus', '../etc/passwd', '/etc/localtime', 'UTC+25:00',
                                  'UTC+05:99', 'Europe/Berlin\n', 'a' * 70, 'Europe//Berlin', 'America'])
def test_parse_timezone_rejects_bad_names(name):
    with pytest.raises(prov.ProvenanceError) as exc:
        prov.parse_timezone(name)
    assert exc.value.code == 'invalid_timezone'


# -- timeline create / update ---------------------------------------------

def test_legacy_create_without_provenance_is_unchanged(admin, inc):
    r = admin.post(_timeline(inc), json={'timestamp': '2026-10-01T12:00:00Z', 'activity': 'plain event'})
    assert r.status_code == 201, r.get_json()
    ev = r.get_json()
    assert ev['timestamp'].startswith('2026-10-01T12:00:00')
    assert ev['provenance_level'] == 'none' and ev['provenance_verifier'] is None
    assert ev['timestamp_derivation'] is None and ev['raw_timestamp'] is None
    assert ev['source_artifact_id'] is None and ev['source_evidence_id'] is None


def test_create_derives_timestamp_from_raw_and_snapshots_skew(admin, inc, rt):
    host = _host(admin, inc)
    _set_skew(admin, inc, host, 300)
    rt.emits.clear()
    r = admin.post(_timeline(inc), json={
        'activity': 'logon', 'host_id': host['id'], 'raw_timestamp': '2026-10-01 14:05:00',
        'source_timezone': 'Europe/Berlin', 'timestamp_type': 'logged',
        'source_record_type': 'evtx_record', 'source_record_ref': 'Security.evtx EventRecordID=48213',
        'extraction_tool': 'EvtxECmd', 'extraction_tool_version': '1.5.0.0'})
    assert r.status_code == 201, r.get_json()
    ev = r.get_json()
    # 14:05 CEST = 12:05Z, minus the host's +300 s skew = 12:00Z.
    assert _utc(ev['timestamp']) == _utc('2026-10-01T12:00:00+00:00')
    assert ev['timestamp_derivation'] == 'computed' and ev['clock_skew_applied_seconds'] == 300
    assert ev['raw_timestamp'] == '2026-10-01 14:05:00' and ev['source_timezone'] == 'Europe/Berlin'
    assert ev['provenance_level'] == 'partial'
    # realtime: exactly one timeline_event:created after commit
    kinds = [(d['entity'], d['op']) for e, d, _ in rt.emits if e == 'entity:changed']
    assert ('timeline_event', 'created') in kinds


def test_host_timezone_is_the_default_for_naive_raw(admin, inc):
    host = _host(admin, inc)
    r = admin.put(f"{API}/incidents/{inc.id}/hosts/{host['id']}/clock-skew", json={'timezone': 'Asia/Tokyo'})
    assert r.status_code == 200 and r.get_json()['timezone'] == 'Asia/Tokyo'
    r = admin.post(_timeline(inc), json={'activity': 'x', 'host_id': host['id'],
                                         'raw_timestamp': '2026-10-01 21:00:00'})
    assert r.status_code == 201, r.get_json()
    assert _utc(r.get_json()['timestamp']) == _utc('2026-10-01T12:00:00+00:00')


def test_create_requires_timestamp_or_raw(admin, inc):
    r = admin.post(_timeline(inc), json={'activity': 'nothing'})
    assert r.status_code == 400
    r = admin.post(_timeline(inc), json={'activity': 'naive no tz', 'raw_timestamp': '2026-10-01 12:00'})
    assert r.status_code == 400 and r.get_json()['error'] == 'source_timezone_required'
    assert admin.get(_timeline(inc)).get_json()['total'] == 0  # nothing half-written


def test_timestamp_mismatch_is_400_unless_manual(admin, inc):
    body = {'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z', 'raw_timestamp': '2026-10-01 14:00:00',
            'source_timezone': 'UTC'}
    r = admin.post(_timeline(inc), json=body)
    assert r.status_code == 400
    err = r.get_json()
    assert err['error'] == 'timestamp_mismatch' and err['computed']['utc'].startswith('2026-10-01T14:00:00')
    r = admin.post(_timeline(inc), json={**body, 'timestamp_derivation': 'manual'})
    assert r.status_code == 201
    ev = r.get_json()
    assert ev['timestamp_derivation'] == 'manual' and ev['timestamp'].startswith('2026-10-01T12:00:00')
    # A matching explicit timestamp is simply 'computed'.
    r = admin.post(_timeline(inc), json={**body, 'timestamp': '2026-10-01T14:00:00Z'})
    assert r.status_code == 201 and r.get_json()['timestamp_derivation'] == 'computed'


def test_update_overriding_a_computed_timestamp_makes_it_manual(admin, inc):
    ev = admin.post(_timeline(inc), json={'activity': 'x', 'raw_timestamp': '2026-10-01 12:00:00',
                                          'source_timezone': 'UTC'}).get_json()
    assert ev['timestamp_derivation'] == 'computed'
    r = admin.put(f"{_timeline(inc)}/{ev['id']}", json={'timestamp': '2026-10-01T13:00:00Z'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['timestamp_derivation'] == 'manual'
    assert r.get_json()['clock_skew_applied_seconds'] is None
    # Editing something else leaves the derivation alone.
    ev2 = admin.post(_timeline(inc), json={'activity': 'y', 'raw_timestamp': '2026-10-01 12:00:00',
                                           'source_timezone': 'UTC'}).get_json()
    r = admin.put(f"{_timeline(inc)}/{ev2['id']}", json={'activity': 'y2'})
    assert r.get_json()['timestamp_derivation'] == 'computed'


def test_update_raw_timestamp_that_disagrees_is_rejected_and_rolled_back(admin, inc):
    ev = admin.post(_timeline(inc), json={'activity': 'x', 'raw_timestamp': '2026-10-01 12:00:00',
                                          'source_timezone': 'UTC'}).get_json()
    r = admin.put(f"{_timeline(inc)}/{ev['id']}", json={'activity': 'changed', 'raw_timestamp': '2026-10-02 12:00:00'})
    assert r.status_code == 400 and r.get_json()['error'] == 'timestamp_mismatch'
    got = admin.get(f"{_timeline(inc)}?q=changed").get_json()
    assert got['total'] == 0  # the activity edit did not persist


def test_resending_unchanged_provenance_after_a_skew_edit_is_not_a_conflict(admin, inc):
    """A client that resends the whole record (MCP, old forms) after the
    host's skew changed must not trip over the stored derivation."""
    host = _host(admin, inc)
    _set_skew(admin, inc, host, 300)
    ev = _computed_event(admin, inc, host)
    _set_skew(admin, inc, host, 100)
    r = admin.put(f"{_timeline(inc)}/{ev['id']}", json={
        'activity': 'edited', 'raw_timestamp': ev['raw_timestamp'], 'source_timezone': ev['source_timezone'],
        'timestamp_type': ev['timestamp_type']})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['timestamp'] == ev['timestamp'] and body['clock_skew_applied_seconds'] == 300
    assert body['timestamp_derivation'] == 'computed'


def test_invalid_provenance_values_are_400(admin, inc):
    base = {'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z'}
    for bad in ({'source_record_type': 'bogus'}, {'timestamp_type': 'bogus'}, {'source_timezone': 'Mars/Base'},
                {'source_record_ref': 'a' * 1001}, {'source_record_ref': 'line1\nline2'},
                {'extraction_tool': 123}, {'source_artifact_id': 'nope'}, {'fold': 2},
                {'timestamp_derivation': 'guessed'}):
        r = admin.post(_timeline(inc), json={**base, **bad})
        assert r.status_code == 400, bad


def test_server_controlled_columns_cannot_be_forged(admin, inc, users):
    r = admin.post(_timeline(inc), json={
        'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z', 'clock_skew_applied_seconds': 999,
        'provenance_verified_by': str(users['Analyst'].id), 'provenance_verified_at': '2026-10-01T00:00:00Z',
        'source_record_ref': 'ok'})
    assert r.status_code == 201
    ev = r.get_json()
    assert ev['clock_skew_applied_seconds'] is None and ev['provenance_verified_at'] is None
    assert ev['provenance_verifier'] is None


def test_url_reference_is_stored_as_text_only(admin, inc):
    r = admin.post(_timeline(inc), json={'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z',
                                         'source_record_type': 'url',
                                         'source_record_ref': 'javascript:alert(1)//http://evil.example/x'})
    assert r.status_code == 201
    assert r.get_json()['source_record_ref'].startswith('javascript:')


# -- source links -----------------------------------------------------------

def test_source_links_must_belong_to_the_incident(admin, inc, make_incident, make_evidence, make_artifact):
    other = make_incident()
    foreign_art = make_artifact(other)
    foreign_item = make_evidence(other)
    own_item = make_evidence(inc)
    own_art = make_artifact(inc, item=own_item)
    base = {'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z'}

    r = admin.post(_timeline(inc), json={**base, 'source_artifact_id': str(foreign_art.id)})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_source_artifact'
    r = admin.post(_timeline(inc), json={**base, 'source_evidence_id': str(foreign_item.id)})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_source_evidence'

    r = admin.post(_timeline(inc), json={**base, 'source_artifact_id': str(own_art.id),
                                         'source_evidence_id': str(own_item.id),
                                         'source_record_ref': 'Security.evtx#1', 'raw_timestamp': '2026-10-01 12:00',
                                         'source_timezone': 'UTC'})
    assert r.status_code == 201, r.get_json()
    ev = r.get_json()
    assert ev['source_artifact_id'] == str(own_art.id) and ev['source_evidence_id'] == str(own_item.id)
    assert ev['provenance_level'] == 'full'


def test_deleting_the_source_clears_the_link(admin, inc, make_evidence, db):
    from app.models import TimelineEvent
    item = make_evidence(inc, register=False)
    ev = admin.post(_timeline(inc), json={'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z',
                                          'source_evidence_id': str(item.id)}).get_json()
    assert ev['source_evidence_id'] == str(item.id)
    # FK is ON DELETE SET NULL: removing the evidence row keeps the event.
    from sqlalchemy import text
    db.session.execute(text('DELETE FROM evidence_items WHERE id = :i'), {'i': item.id})
    db.session.commit()
    db.session.expire_all()
    assert TimelineEvent.query.get(uuid.UUID(ev['id'])).source_evidence_id is None


# -- IOCs -------------------------------------------------------------------

def test_network_ioc_provenance_maps_to_timestamp(admin, inc):
    r = admin.post(f'{API}/incidents/{inc.id}/network-iocs', json={
        'dns_ip': '203.0.113.9', 'raw_timestamp': '2026-10-01T12:00:00+02:00', 'timestamp_type': 'first_seen',
        'source_record_type': 'log_line', 'source_record_ref': 'fw.log:4411'})
    assert r.status_code == 201, r.get_json()
    ioc = r.get_json()
    assert _utc(ioc['timestamp']) == _utc('2026-10-01T10:00:00+00:00')
    assert ioc['timestamp_derivation'] == 'computed'
    r = admin.put(f"{API}/incidents/{inc.id}/network-iocs/{ioc['id']}", json={'raw_timestamp': '2026-10-01T13:00:00+02:00'})
    assert r.status_code == 400 and r.get_json()['error'] == 'timestamp_mismatch'


def test_host_ioc_provenance_maps_to_datetime(admin, inc):
    r = admin.post(f'{API}/incidents/{inc.id}/host-iocs', json={
        'artifact_type': 'registry', 'artifact_value': r'HKLM\Run\evil', 'raw_timestamp': '2026-10-01 12:00',
        'source_timezone': 'UTC-05:00', 'source_record_type': 'registry_key', 'source_record_ref': r'HKLM\Run'})
    assert r.status_code == 201, r.get_json()
    ioc = r.get_json()
    assert _utc(ioc['datetime']) == _utc('2026-10-01T17:00:00+00:00') and ioc['timestamp_derivation'] == 'computed'


def test_malware_provenance_uses_the_macb_type(admin, inc):
    url = f'{API}/incidents/{inc.id}/malware'
    r = admin.post(url, json={'file_name': 'evil.exe', 'raw_timestamp': '2026-10-01 12:00', 'source_timezone': 'UTC',
                              'timestamp_type': 'modified', 'source_record_type': 'offset',
                              'source_record_ref': '$MFT @0x1A2B00'})
    assert r.status_code == 201, r.get_json()
    m = r.get_json()
    assert _utc(m['modification_time']) == _utc('2026-10-01T12:00:00+00:00')
    assert m['access_time'] is None and m['creation_time'] is None and m['timestamp_derivation'] == 'computed'
    r = admin.post(url, json={'file_name': 'born.exe', 'raw_timestamp': '2026-10-01 12:00', 'source_timezone': 'UTC',
                              'timestamp_type': 'born'})
    assert _utc(r.get_json()['creation_time']) == _utc('2026-10-01T12:00:00+00:00')
    # A non-MACB type records the raw value only: nothing to derive.
    r = admin.post(url, json={'file_name': 'seen.exe', 'raw_timestamp': '2026-10-01 12:00', 'source_timezone': 'UTC',
                              'timestamp_type': 'first_seen'})
    assert r.status_code == 201
    m = r.get_json()
    assert m['modification_time'] is None and m['timestamp_derivation'] is None and m['raw_timestamp']


def test_ioc_source_links_are_incident_scoped(admin, inc, make_incident, make_artifact):
    foreign = make_artifact(make_incident())
    for path, body in (('network-iocs', {'dns_ip': '1.2.3.4'}),
                       ('host-iocs', {'artifact_type': 'file', 'artifact_value': 'x'}),
                       ('malware', {'file_name': 'x.exe'})):
        r = admin.post(f'{API}/incidents/{inc.id}/{path}', json={**body, 'source_artifact_id': str(foreign.id)})
        assert r.status_code == 400, path


def test_mark_as_ioc_inherits_provenance_but_not_verification(admin, inc, users, auth):
    ev = admin.post(_timeline(inc), json={
        'activity': 'persistence key', 'raw_timestamp': '2026-10-01 12:00', 'source_timezone': 'UTC',
        'source_record_type': 'registry_key', 'source_record_ref': 'HKLM\\Run'}).get_json()
    r = admin.post(f"{_timeline(inc)}/{ev['id']}/mark-as-ioc", json={'artifact_type': 'registry'})
    assert r.status_code == 201, r.get_json()
    ioc = r.get_json()['ioc']
    assert ioc['source_record_ref'] == 'HKLM\\Run' and ioc['raw_timestamp'] == '2026-10-01 12:00'
    assert ioc['timestamp_derivation'] == 'computed' and ioc['provenance_verified_at'] is None


# -- verification ----------------------------------------------------------

def _verify_body(kind, rec):
    return {'record_type': kind, 'record_id': rec['id']}


def test_verification_requires_a_second_analyst(admin, inc, users, auth):
    ev = admin.post(_timeline(inc), json={'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z',
                                          'source_record_ref': 'a.evtx#1'}).get_json()
    url = f'{API}/incidents/{inc.id}/provenance/verify'
    r = admin.post(url, json=_verify_body('timeline_event', ev))
    assert r.status_code == 400 and r.get_json()['error'] == 'same_analyst'

    analyst = auth(users['Analyst'])
    r = analyst.post(url, json=_verify_body('timeline_event', ev))
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['provenance_level'] == 'verified'
    assert body['provenance_verifier'] == {'id': str(users['Analyst'].id), 'name': users['Analyst'].name}
    assert r.headers['ETag'] == f'"{body["version"]}"'

    r = analyst.post(url, json=_verify_body('timeline_event', ev))
    assert r.status_code == 409 and r.get_json()['error'] == 'already_verified'


def test_verification_audits_and_emits(admin, inc, users, auth, rt, db):
    from app.models import AuditLog
    ev = admin.post(_timeline(inc), json={'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z',
                                          'source_record_ref': 'a.evtx#1'}).get_json()
    rt.emits.clear()
    r = auth(users['Analyst']).post(f'{API}/incidents/{inc.id}/provenance/verify', json=_verify_body('timeline_event', ev))
    assert r.status_code == 200
    assert [(d['entity'], d['op']) for e, d, _ in rt.emits if e == 'entity:changed'] == [('timeline_event', 'updated')]
    row = AuditLog.query.filter_by(action='verify_provenance', resource_type='provenance').order_by(
        AuditLog.created_at.desc()).first()
    assert row and row.status_code == 200 and row.details['record_type'] == 'timeline_event'
    assert 'provenance_verified_at' in row.details['changes']


def test_cannot_verify_a_record_without_provenance(admin, inc, auth, users):
    ev = admin.post(_timeline(inc), json={'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z'}).get_json()
    r = auth(users['Analyst']).post(f'{API}/incidents/{inc.id}/provenance/verify', json=_verify_body('timeline_event', ev))
    assert r.status_code == 400 and r.get_json()['error'] == 'no_provenance'


def test_verification_permissions_and_scoping(admin, inc, users, auth, make_incident):
    ev = admin.post(_timeline(inc), json={'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z',
                                          'source_record_ref': 'a.evtx#1'}).get_json()
    url = f'{API}/incidents/{inc.id}/provenance/verify'
    # Viewer / Manager cannot update timeline events.
    for role in ('Viewer', 'Manager'):
        r = auth(users[role]).post(url, json=_verify_body('timeline_event', ev))
        assert r.status_code == 403, role
    # Org B cannot see the incident at all.
    assert auth(users['admin_b']).post(url, json=_verify_body('timeline_event', ev)).status_code == 404
    # Record from another incident -> 404; bad ids / kinds -> 400.
    other = make_incident()
    ev2 = admin.post(_timeline(other), json={'activity': 'y', 'timestamp': '2026-10-01T12:00:00Z',
                                             'source_record_ref': 'a'}).get_json()
    assert auth(users['Analyst']).post(url, json=_verify_body('timeline_event', ev2)).status_code == 404
    assert auth(users['Analyst']).post(url, json={'record_type': 'timeline_event', 'record_id': 'nope'}).status_code == 400
    assert auth(users['Analyst']).post(url, json={'record_type': 'case_note', 'record_id': ev['id']}).status_code == 400


def test_verification_per_record_type(admin, inc, auth, users):
    analyst = auth(users['Analyst'])
    url = f'{API}/incidents/{inc.id}/provenance/verify'
    made = {
        'network_ioc': admin.post(f'{API}/incidents/{inc.id}/network-iocs',
                                  json={'dns_ip': '1.2.3.4', 'source_record_ref': 'x'}).get_json(),
        'host_ioc': admin.post(f'{API}/incidents/{inc.id}/host-iocs', json={
            'artifact_type': 'file', 'artifact_value': 'x', 'source_record_ref': 'x'}).get_json(),
        'malware': admin.post(f'{API}/incidents/{inc.id}/malware',
                              json={'file_name': 'x.exe', 'source_record_ref': 'x'}).get_json(),
    }
    for kind, rec in made.items():
        r = analyst.post(url, json=_verify_body(kind, rec))
        assert r.status_code == 200 and r.get_json()['provenance_level'] == 'verified', kind
    # legacy aliases are accepted
    alias = admin.post(f'{API}/incidents/{inc.id}/network-iocs', json={'dns_ip': '5.6.7.8', 'source_record_ref': 'x'}).get_json()
    assert analyst.post(url, json={'record_type': 'network_indicator', 'record_id': alias['id']}).status_code == 200


def test_material_edit_clears_verification(admin, inc, users, auth):
    from app.models import AuditLog
    analyst = auth(users['Analyst'])
    ev = admin.post(_timeline(inc), json={'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z',
                                          'source_record_ref': 'a.evtx#1'}).get_json()
    v = analyst.post(f'{API}/incidents/{inc.id}/provenance/verify', json=_verify_body('timeline_event', ev)).get_json()
    # Unrelated edit keeps it.
    r = admin.put(f"{_timeline(inc)}/{ev['id']}", json={'activity': 'x2'})
    assert r.get_json()['provenance_level'] == 'verified'
    # Changing the record reference or the timestamp clears it.
    r = admin.put(f"{_timeline(inc)}/{ev['id']}", json={'source_record_ref': 'a.evtx#2'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['provenance_level'] == 'partial' and body['provenance_verified_at'] is None
    assert body['provenance_verifier'] is None
    row = AuditLog.query.filter_by(action='update', resource_type='timeline_event').order_by(
        AuditLog.created_at.desc()).first()
    assert row.details.get('provenance_verification_cleared') is True
    assert 'source_record_ref' in row.details['changes']

    analyst.post(f'{API}/incidents/{inc.id}/provenance/verify', json=_verify_body('timeline_event', ev))
    r = admin.put(f"{_timeline(inc)}/{ev['id']}", json={'timestamp': '2026-10-01T13:00:00Z'})
    assert r.get_json()['provenance_verified_at'] is None


def test_unverify_only_by_verifier_or_org_manager(admin, inc, users, auth, make_user, org_a):
    analyst, responder = auth(users['Analyst']), auth(users['Incident Responder'])
    ev = admin.post(_timeline(inc), json={'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z',
                                          'source_record_ref': 'a'}).get_json()
    url = f'{API}/incidents/{inc.id}/provenance/verify'
    analyst.post(url, json=_verify_body('timeline_event', ev))
    r = responder.delete(url, json=_verify_body('timeline_event', ev))
    assert r.status_code == 403
    r = analyst.delete(url, json=_verify_body('timeline_event', ev))
    assert r.status_code == 200 and r.get_json()['provenance_level'] == 'partial'
    assert analyst.delete(url, json=_verify_body('timeline_event', ev)).status_code == 409
    analyst.post(url, json=_verify_body('timeline_event', ev))
    assert admin.delete(url, json=_verify_body('timeline_event', ev)).status_code == 200  # organizations:manage


def test_verify_respects_optimistic_concurrency(admin, inc, users, auth):
    ev = admin.post(_timeline(inc), json={'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z',
                                          'source_record_ref': 'a'}).get_json()
    r = auth(users['Analyst']).post(f'{API}/incidents/{inc.id}/provenance/verify',
                                    json={**_verify_body('timeline_event', ev), 'expected_version': ev['version'] + 5})
    assert r.status_code == 409 and r.get_json()['error'] == 'conflict'


# -- normalize-preview ------------------------------------------------------

def test_normalize_preview(admin, inc, users, auth):
    url = f'{API}/incidents/{inc.id}/provenance/normalize-preview'
    host = _host(admin, inc)
    _set_skew(admin, inc, host, 60, timezone='Europe/Berlin')
    r = admin.post(url, json={'raw_timestamp': '2026-07-01 12:01:00', 'host_id': host['id']})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['utc'].startswith('2026-07-01T10:00:00') and body['skew_applied'] == 60
    assert body['timezone_used'] == 'Europe/Berlin' and body['offset_seconds'] == 7200

    assert admin.post(url, json={'raw_timestamp': '2026-07-01 12:00'}).get_json()['error'] == 'source_timezone_required'
    assert admin.post(url, json={}).status_code == 400
    assert admin.post(url, json={'raw_timestamp': 'x', 'host_id': str(uuid.uuid4())}).status_code == 400
    assert auth(users['Analyst']).post(url, json={'raw_timestamp': '2026-07-01 12:00Z'}).status_code == 200  # timeline:read
    assert auth(users['Viewer']).post(url, json={'raw_timestamp': '2026-07-01 12:00Z'}).status_code == 403  # not assigned
    assert auth(users['admin_b']).post(url, json={'raw_timestamp': '2026-07-01 12:00Z'}).status_code == 404


# -- clock skew routes ------------------------------------------------------

def test_clock_skew_bounds_and_basis(admin, inc):
    host = _host(admin, inc)
    url = f"{API}/incidents/{inc.id}/hosts/{host['id']}/clock-skew"
    assert admin.put(url, json={'clock_skew_seconds': 604801, 'clock_skew_basis': 'x'}).status_code == 400
    assert admin.put(url, json={'clock_skew_seconds': -604801, 'clock_skew_basis': 'x'}).status_code == 400
    assert admin.put(url, json={'clock_skew_seconds': 1.5, 'clock_skew_basis': 'x'}).status_code == 400
    assert admin.put(url, json={'clock_skew_seconds': True, 'clock_skew_basis': 'x'}).status_code == 400
    assert admin.put(url, json={}).status_code == 400
    r = admin.put(url, json={'clock_skew_seconds': 30})
    assert r.status_code == 400 and r.get_json()['error'] == 'basis_required'
    assert admin.put(url, json={'clock_skew_seconds': 0}).status_code == 200  # zero needs no basis
    assert admin.put(url, json={'timezone': 'Not/AZone'}).status_code == 400
    r = admin.put(url, json={'clock_skew_seconds': 604800, 'clock_skew_basis': 'bound'})
    assert r.status_code == 200


def test_clock_skew_stamps_measurer_audits_and_clears(admin, inc, users, db, rt):
    from app.models import AuditLog
    host = _host(admin, inc)
    rt.emits.clear()
    body = _set_skew(admin, inc, host, -90, 'compared against DC time at triage')
    assert body['clock_skew_seconds'] == -90 and body['clock_skew_measured_at']
    assert body['clock_skew_measurer'] == {'id': str(users['Administrator'].id), 'name': users['Administrator'].name}
    assert [(d['entity'], d['op']) for e, d, _ in rt.emits if e == 'entity:changed'] == [('host', 'updated')]
    row = AuditLog.query.filter_by(action='update_clock_skew', resource_type='compromised_host').order_by(
        AuditLog.created_at.desc()).first()
    assert row.details['changes']['clock_skew_seconds'] == {'from': None, 'to': -90}

    url = f"{API}/incidents/{inc.id}/hosts/{host['id']}/clock-skew"
    cleared = admin.put(url, json={'clock_skew_seconds': None}).get_json()
    assert cleared['clock_skew_seconds'] is None and cleared['clock_skew_basis'] is None
    assert cleared['clock_skew_measured_by'] is None and cleared['clock_skew_measured_at'] is None


def test_clock_skew_requires_hosts_update_and_respects_version(admin, inc, users, auth):
    host = _host(admin, inc)
    url = f"{API}/incidents/{inc.id}/hosts/{host['id']}/clock-skew"
    assert auth(users['Viewer']).put(url, json={'timezone': 'UTC'}).status_code == 403
    assert auth(users['admin_b']).put(url, json={'timezone': 'UTC'}).status_code == 404
    r = admin.put(url, json={'timezone': 'UTC', 'expected_version': host['version'] + 3})
    assert r.status_code == 409
    # PUT /hosts/<id> cannot smuggle skew in.
    r = admin.put(f"{API}/incidents/{inc.id}/hosts/{host['id']}", json={'clock_skew_seconds': 500, 'notes': 'n'})
    assert r.status_code == 200 and r.get_json()['clock_skew_seconds'] is None


def _computed_event(client, inc, host, raw='2026-10-01 12:05:00'):
    r = client.post(_timeline(inc), json={'activity': 'e', 'host_id': host['id'], 'raw_timestamp': raw,
                                          'source_timezone': 'UTC'})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_reapply_dry_run_then_real_run(admin, inc, users, auth, db, rt):
    from app.models import AuditLog, HostBasedIndicator, TimelineEvent
    host = _host(admin, inc)
    _set_skew(admin, inc, host, 300)
    computed = _computed_event(admin, inc, host)                     # 12:00Z under +300
    manual = admin.post(_timeline(inc), json={'activity': 'm', 'host_id': host['id'],
                                              'timestamp': '2026-10-01T09:00:00Z'}).get_json()
    forced = admin.post(_timeline(inc), json={'activity': 'f', 'host_id': host['id'], 'timestamp_derivation': 'manual',
                                              'timestamp': '2026-10-01T09:00:00Z', 'raw_timestamp': '2026-10-01 10:00',
                                              'source_timezone': 'UTC'}).get_json()
    ioc = admin.post(f'{API}/incidents/{inc.id}/host-iocs', json={
        'artifact_type': 'file', 'artifact_value': 'x', 'host_id': host['id'],
        'raw_timestamp': '2026-10-01 12:05:00', 'source_timezone': 'UTC'}).get_json()
    other = _host(admin, inc, 'OTHER')
    other_ev = _computed_event(admin, inc, other)                    # different host, untouched
    _set_skew(admin, inc, host, 100)

    url = f"{API}/incidents/{inc.id}/hosts/{host['id']}/clock-skew/reapply"
    r = admin.post(url, json={})  # dry run by default
    assert r.status_code == 200, r.get_json()
    dry = r.get_json()
    assert dry['dry_run'] is True and dry['count'] == 2
    by_id = {c['id']: c for c in dry['changes']}
    assert set(by_id) == {computed['id'], ioc['id']}
    # skew 300 -> 100: values move 200 s later.
    assert _utc(by_id[computed['id']]['new']) == _utc('2026-10-01T12:03:20+00:00')
    assert by_id[computed['id']]['old_skew'] == 300 and by_id[computed['id']]['new_skew'] == 100
    db.session.expire_all()
    assert _utc(TimelineEvent.query.get(uuid.UUID(computed['id'])).timestamp.isoformat()) == _utc('2026-10-01T12:00:00+00:00')

    rt.emits.clear()
    r = admin.post(url, json={'dry_run': False})
    assert r.status_code == 200 and r.get_json()['count'] == 2 and r.get_json()['dry_run'] is False
    db.session.expire_all()
    ev = TimelineEvent.query.get(uuid.UUID(computed['id']))
    assert _utc(ev.timestamp.isoformat()) == _utc('2026-10-01T12:03:20+00:00')
    assert ev.clock_skew_applied_seconds == 100 and ev.timestamp_derivation == 'computed' and ev.version == 2
    assert _utc(HostBasedIndicator.query.get(uuid.UUID(ioc['id'])).datetime.isoformat()) == _utc('2026-10-01T12:03:20+00:00')
    for rec, expect in ((manual, '2026-10-01T09:00:00'), (forced, '2026-10-01T09:00:00')):
        assert TimelineEvent.query.get(uuid.UUID(rec['id'])).timestamp.isoformat().startswith(expect)
    assert _utc(TimelineEvent.query.get(uuid.UUID(other_ev['id'])).timestamp.isoformat()) == _utc('2026-10-01T12:05:00+00:00')

    resyncs = [d for e, d, _ in rt.emits if e == 'incident:resync']
    assert sorted(d['scopes'][0] for d in resyncs) == ['host_iocs', 'malware', 'network_iocs', 'timeline']
    rows = AuditLog.query.filter_by(action='renormalize', resource_type='compromised_host').order_by(
        AuditLog.created_at.desc()).all()
    real = [r_ for r_ in rows if r_.details.get('dry_run') is False]
    assert len(real) == 1 and real[0].details['count'] == 2 and real[0].details['new_skew'] == 100
    assert len(real[0].details['records']) == 2

    # Idempotent: nothing left to change.
    again = admin.post(url, json={'dry_run': False}).get_json()
    assert again['count'] == 0


def test_reapply_clears_verification_of_changed_records(admin, inc, users, auth, db):
    from app.models import TimelineEvent
    host = _host(admin, inc)
    ev = _computed_event(admin, inc, host)
    admin.put(f"{_timeline(inc)}/{ev['id']}", json={'source_record_ref': 'a'})
    auth(users['Analyst']).post(f'{API}/incidents/{inc.id}/provenance/verify', json=_verify_body('timeline_event', ev))
    _set_skew(admin, inc, host, 600)
    r = admin.post(f"{API}/incidents/{inc.id}/hosts/{host['id']}/clock-skew/reapply", json={'dry_run': False})
    assert r.get_json()['count'] == 1
    db.session.expire_all()
    assert TimelineEvent.query.get(uuid.UUID(ev['id'])).provenance_verified_at is None


def test_reapply_permissions_and_validation(admin, inc, users, auth, make_user, org_a, make_incident):
    host = _host(admin, inc)
    url = f"{API}/incidents/{inc.id}/hosts/{host['id']}/clock-skew/reapply"
    assert admin.post(url, json={'dry_run': 'yes'}).status_code == 400
    assert auth(users['Viewer']).post(url, json={}).status_code == 403
    # hosts:update alone is not enough: the records of every kind change too.
    partial = make_user(org_a, perms=['incidents:read_all', 'incidents:read', 'hosts:read', 'hosts:update',
                                      'timeline:read', 'timeline:update'])
    r = auth(partial).post(url, json={})
    assert r.status_code == 403 and 'network_iocs:update' in r.get_json()['message']
    assert auth(users['admin_b']).post(url, json={}).status_code == 404
    other = make_incident()
    assert admin.post(f"{API}/incidents/{other.id}/hosts/{host['id']}/clock-skew/reapply", json={}).status_code == 404


def test_reapply_requires_current_version_for_a_real_run(admin, inc):
    host = _host(admin, inc)
    r = admin.post(f"{API}/incidents/{inc.id}/hosts/{host['id']}/clock-skew/reapply",
                   json={'dry_run': False, 'expected_version': host['version'] + 4})
    assert r.status_code == 409


# -- list filters -----------------------------------------------------------

def test_list_filters(admin, inc, users, auth, make_evidence):
    item = make_evidence(inc)
    none = admin.post(_timeline(inc), json={'activity': 'none', 'timestamp': '2026-10-01T12:00:00Z'}).get_json()
    partial = admin.post(_timeline(inc), json={'activity': 'partial', 'timestamp': '2026-10-01T12:00:00Z',
                                               'extraction_tool': 'Plaso'}).get_json()
    full = admin.post(_timeline(inc), json={
        'activity': 'full', 'raw_timestamp': '2026-10-01 12:00', 'source_timezone': 'UTC',
        'source_record_ref': 'x', 'source_evidence_id': str(item.id)}).get_json()
    verified = admin.post(_timeline(inc), json={'activity': 'verified', 'timestamp': '2026-10-01T12:00:00Z',
                                                'source_record_ref': 'y'}).get_json()
    auth(users['Analyst']).post(f'{API}/incidents/{inc.id}/provenance/verify', json=_verify_body('timeline_event', verified))

    def ids(**params):
        q = '&'.join(f'{k}={v}' for k, v in params.items())
        r = admin.get(f'{_timeline(inc)}?{q}')
        assert r.status_code == 200, r.get_json()
        return {e['id'] for e in r.get_json()['items']}

    assert ids(provenance_level='none') == {none['id']}
    assert ids(provenance_level='partial') == {partial['id']}
    assert ids(provenance_level='full') == {full['id']}
    assert ids(provenance_level='verified') == {verified['id']}
    assert ids(unverified='true') == {partial['id'], full['id']}
    assert ids(source_evidence_id=item.id) == {full['id']}
    assert admin.get(f'{_timeline(inc)}?provenance_level=bogus').status_code == 400
    assert admin.get(f'{_timeline(inc)}?source_artifact_id=nope').status_code == 400

    admin.post(f'{API}/incidents/{inc.id}/network-iocs', json={'dns_ip': '9.9.9.9', 'source_record_ref': 'r'})
    admin.post(f'{API}/incidents/{inc.id}/network-iocs', json={'dns_ip': '8.8.8.8'})
    r = admin.get(f'{API}/incidents/{inc.id}/network-iocs?provenance_level=partial').get_json()
    assert [i['dns_ip'] for i in r['items']] == ['9.9.9.9']


def test_cross_org_source_links_are_rejected(admin, inc, org_b, make_incident, make_artifact, make_evidence, users):
    inc_b = make_incident(org=org_b)
    art_b = make_artifact(inc_b, actor=users['admin_b'])
    item_b = make_evidence(inc_b, actor=users['admin_b'])
    base = {'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z'}
    assert admin.post(_timeline(inc), json={**base, 'source_artifact_id': str(art_b.id)}).status_code == 400
    assert admin.post(_timeline(inc), json={**base, 'source_evidence_id': str(item_b.id)}).status_code == 400


def test_incident_purge_with_linked_provenance_sources(admin, inc, make_evidence, make_artifact, db):
    """Events / IOCs whose provenance points at the incident's own evidence and
    artifacts must not block the permanent delete (SET NULL during cascades)."""
    from app.models import Incident, TimelineEvent
    item = make_evidence(inc)
    art = make_artifact(inc, item=item)
    admin.post(_timeline(inc), json={'activity': 'x', 'timestamp': '2026-10-01T12:00:00Z',
                                     'source_evidence_id': str(item.id), 'source_artifact_id': str(art.id)})
    admin.post(f'{API}/incidents/{inc.id}/network-iocs', json={'dns_ip': '1.2.3.4', 'source_artifact_id': str(art.id)})
    iid = inc.id
    assert admin.post(f'{API}/incidents/{iid}/archive').status_code == 200
    r = admin.delete(f'{API}/incidents/{iid}/permanent')
    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert db.session.get(Incident, iid) is None
    assert TimelineEvent.query.filter_by(incident_id=iid).count() == 0


def test_migration_is_idempotent_and_reversible(db):
    """upgrade() on a migrated DB is a no-op; downgrade() removes exactly the
    new columns/indexes (twice is fine) and upgrade() restores them. Runs in
    one transaction that is rolled back, so the shared test DB is untouched."""
    import importlib.util
    import os
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'migrations', 'versions', 'add_record_provenance.py')
    spec = importlib.util.spec_from_file_location('add_record_provenance_under_test', path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    db.session.rollback()
    db.session.close()
    with db.engine.connect() as conn:
        tx = conn.begin()
        try:
            with Operations.context(MigrationContext.configure(conn)):
                def shape():
                    insp = sa.inspect(conn)
                    cols = {t: {c['name'] for c in insp.get_columns(t)} for t in
                            (*mig.PROVENANCE_TABLES, mig.HOST_TABLE)}
                    idx = {t: {i['name'] for i in insp.get_indexes(t)} for t in mig.PROVENANCE_TABLES}
                    return cols, idx

                full = shape()
                mig.upgrade()                       # already applied: no-op
                assert shape() == full
                mig.downgrade()
                mig.downgrade()                     # second run: nothing left to drop
                cols, idx = shape()
                for table in mig.PROVENANCE_TABLES:
                    assert 'raw_timestamp' not in cols[table] and 'source_evidence_id' not in cols[table]
                    assert not any(name.startswith('idx_') and 'source_' in name for name in idx[table])
                assert 'clock_skew_seconds' not in cols[mig.HOST_TABLE] and 'timezone' not in cols[mig.HOST_TABLE]
                # Pre-existing columns survive the downgrade.
                assert {'timestamp', 'activity', 'version'} <= cols['timeline_events']
                mig.upgrade()
                mig.upgrade()
                assert shape() == full
        finally:
            tx.rollback()
