"""W3-DFIR-C: server-side CSV exports (surface-dfir §3.8; C23, C24).

GET /incidents/<id>/export/<entity> needs incident access + the entity read
permission + incidents:export, escapes formulas, never exposes passwords, takes
the list endpoint's filters, defangs on request and writes an audit row.
"""
import csv
import io
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest

API = '/api/v1'
ENTITIES = ['timeline', 'hosts', 'accounts', 'network-iocs', 'host-iocs', 'malware', 'tasks']
ENTITY_PERMS = {'timeline': 'timeline:read', 'hosts': 'hosts:read', 'accounts': 'accounts:read',
                'network-iocs': 'network_iocs:read', 'host-iocs': 'host_iocs:read',
                'malware': 'malware:read', 'tasks': 'tasks:read'}
T0 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)


def parse(resp):
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    text = resp.get_data().decode('utf-8-sig')
    return list(csv.reader(io.StringIO(text)))


def rows_by_header(resp):
    table = parse(resp)
    return table[0], [dict(zip(table[0], r)) for r in table[1:]]


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


@pytest.fixture
def case(app, db, users, make_incident):
    """An incident holding one record of every exportable entity."""
    from app.models import (CompromisedAccount, CompromisedHost, HostBasedIndicator, MalwareTool,
                            NetworkIndicator, Task, TimelineEvent)
    admin_id = users['Administrator'].id
    inc = make_incident(tlp='amber')
    host = CompromisedHost(incident_id=inc.id, hostname='WS-01', ip_address='10.0.0.5',
                           triage_status='compromised', containment_status='contained',
                           acquisition_status={'memory_captured': True, 'disk_imaged': False},
                           created_by=admin_id)
    db.session.add(host)
    db.session.flush()
    db.session.add_all([
        TimelineEvent(incident_id=inc.id, timestamp=T0, detection_time=T0 + timedelta(hours=2),
                      hostname='WS-01', activity='Initial access via phishing', confidence_level='high',
                      mitre_mappings=[{'tactic': 'initial-access', 'technique': 'T1566'}], created_by=admin_id),
        TimelineEvent(incident_id=inc.id, timestamp=T0 + timedelta(hours=1), hostname='WS-01',
                      activity='Persistence added', created_by=admin_id),
        CompromisedAccount(incident_id=inc.id, datetime_seen=T0, account_name='svc-backup',
                           account_type='domain', domain='CORP', password_encrypted=b'gAAAA-secret-token',
                           created_by=admin_id),
        NetworkIndicator(incident_id=inc.id, timestamp=T0, dns_ip='evil.example.com', protocol='tcp', port=443,
                         direction='outbound', created_by=admin_id),
        HostBasedIndicator(incident_id=inc.id, artifact_type='file', artifact_value='C:\\Users\\a\\evil.exe',
                           host='WS-01', datetime=T0, created_by=admin_id),
        MalwareTool(incident_id=inc.id, file_name='beacon.exe', sha256='a' * 64, md5='b' * 32,
                    malware_family='cobalt', created_by=admin_id),
        Task(incident_id=inc.id, title='Triage WS-01', created_by=admin_id, task_type='investigative_lead',
             assignee_id=users['Analyst'].id, evidence_refs=[{'evidence_type': 'host', 'evidence_id': str(host.id)}]),
    ])
    db.session.commit()
    inc.host_uuid = host.id
    return inc


def export(client, inc, entity, **params):
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    return client.get(f'{API}/incidents/{inc.id}/export/{entity}' + (f'?{query}' if query else ''))


@pytest.fixture
def export_as(auth):
    def go(user, inc, entity, **params):
        return export(auth(user), inc, entity, **params)
    return go


# ── basics ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('entity', ENTITIES)
def test_every_entity_exports_csv(admin, case, entity):
    resp = export(admin, case, entity)
    assert resp.status_code == 200
    assert resp.mimetype == 'text/csv'
    assert resp.get_data().startswith(b'\xef\xbb\xbf'), 'UTF-8 BOM first'
    disposition = resp.headers['Content-Disposition']
    assert re.fullmatch(rf'attachment; filename="incident-\d+-TLP_AMBER-{entity}-\d{{8}}T\d{{4}}Z\.csv"',
                        disposition), disposition
    header, rows = rows_by_header(resp)
    assert len(rows) >= 1 and header and resp.headers['X-Export-Rows'] == str(len(rows))


def test_timeline_dual_time_in_utc_z(admin, case):
    _, rows = rows_by_header(export(admin, case, 'timeline', sort='timestamp'))
    first = rows[0]
    assert first['Timestamp (UTC)'] == '2026-10-01T12:00:00Z'
    assert first['Detection Time (UTC)'] == '2026-10-01T14:00:00Z'
    assert first['Dwell (seconds)'] == '7200'
    assert first['MITRE'] == 'initial-access:T1566'
    assert rows[1]['Detection Time (UTC)'] == '' and rows[1]['Dwell (seconds)'] == ''


def test_hosts_columns_include_acquisition(admin, case):
    _, rows = rows_by_header(export(admin, case, 'hosts'))
    host = rows[0]
    assert host['Hostname'] == 'WS-01' and host['IP Address'] == '10.0.0.5'
    assert host['Memory Captured'] == 'true' and host['Disk Imaged'] == 'false'
    assert host['Logs Collected'] == ''


def test_tasks_resolve_evidence_assignee_and_missing(admin, case, db):
    from app.models import CompromisedHost
    _, rows = rows_by_header(export(admin, case, 'tasks'))
    assert rows[0]['Assignee'] == 'analyst' and rows[0]['Evidence'].startswith('host: WS-01')
    db.session.delete(db.session.get(CompromisedHost, case.host_uuid))
    db.session.commit()
    _, rows = rows_by_header(export(admin, case, 'tasks'))
    assert rows[0]['Evidence'] == 'host: [deleted]'


# ── security: formula injection, secrets ──────────────────────────────────

def test_formula_cells_are_neutralised(admin, case, db, users):
    from app.models import CompromisedHost, TimelineEvent
    payloads = ['=cmd|\' /C calc\'!A0', '+SUM(1+1)', '-2+3', '@SUM(A1)', '\t=1+1', '\r=1+1']
    for n, payload in enumerate(payloads):
        db.session.add(TimelineEvent(incident_id=case.id, timestamp=T0 + timedelta(days=1, minutes=n),
                                     activity=payload, created_by=users['Administrator'].id))
    db.session.add(CompromisedHost(incident_id=case.id, hostname='=HYPERLINK("http://x")',
                                   created_by=users['Administrator'].id))
    db.session.commit()
    table = parse(export(admin, case, 'timeline', sort='-timestamp'))
    activities = [r[table[0].index('Activity')] for r in table[1:]]
    for payload in payloads:
        assert "'" + payload in activities
        assert payload not in activities
    hosts = parse(export(admin, case, 'hosts'))
    names = [r[0] for r in hosts[1:]]
    assert "'=HYPERLINK(\"http://x\")" in names


def test_accounts_never_include_the_password(admin, case, export_as, make_user, org_a):
    resp = export(admin, case, 'accounts')
    body = resp.get_data(as_text=True)
    header, rows = rows_by_header(resp)
    assert 'Password' not in header and 'Has Password' in header
    assert rows[0]['Has Password'] == 'true'
    assert 'secret' not in body and 'gAAAA' not in body
    # even a holder of the reveal permission gets no password column
    revealer = make_user(org_a, perms=['incidents:read', 'incidents:read_all', 'incidents:export',
                                       'accounts:read', 'compromised_accounts:reveal'])
    resp = export_as(revealer, case, 'accounts', reveal='true')
    assert resp.status_code == 200 and 'gAAAA' not in resp.get_data(as_text=True)


# ── C24 permission matrix ─────────────────────────────────────────────────

@pytest.mark.parametrize('role,allowed', [
    ('Administrator', True), ('Incident Responder', True), ('Manager', True),
    ('Analyst', False), ('Operator', False), ('Viewer', False),
])
def test_system_roles_follow_incidents_export(app, users, auth, case, role, allowed):
    """Only roles holding incidents:export may export (Analyst, Operator and Viewer may not)."""
    client = auth(users[role])
    wanted = 200 if allowed else 403
    for entity in ('hosts', 'tasks'):
        status = export(client, case, entity).status_code
        # Operators additionally lack incident visibility for an unassigned incident.
        assert status == wanted or (role == 'Operator' and status == 403), (role, entity, status)
    stix = client.get(f'{API}/incidents/{case.id}/export/stix').status_code
    assert stix == wanted or (role == 'Operator' and stix == 403), (role, stix)


def test_export_needs_both_entity_read_and_export(app, case, export_as, make_user, org_a):
    base = ['incidents:read', 'incidents:read_all']
    only_export = make_user(org_a, perms=base + ['incidents:export'])
    only_read = make_user(org_a, perms=base + ['hosts:read', 'timeline:read'])
    both = make_user(org_a, perms=base + ['incidents:export', 'hosts:read'])
    assert export_as(only_export, case, 'hosts').status_code == 403
    assert export_as(only_read, case, 'hosts').status_code == 403
    r = export_as(both, case, 'hosts')
    assert r.status_code == 200
    assert 'incidents:export' not in r.get_data(as_text=True)
    assert export_as(both, case, 'timeline').status_code == 403  # lacks timeline:read
    # STIX needs incidents:export on top of incidents:read
    assert export_as(only_export, case, 'stix').status_code == 200
    assert export_as(only_read, case, 'stix').status_code == 403


def test_stix_route_still_wins_over_the_entity_route(app, admin, case):
    resp = admin.get(f'{API}/incidents/{case.id}/export/stix')
    assert resp.status_code == 200 and resp.mimetype == 'application/stix+json'


def test_unknown_entity_and_cross_org(app, admin, case, make_incident, org_b, users, auth):
    assert export(admin, case, 'passwords').status_code == 404
    assert export(admin, case, 'audit-logs').status_code == 404
    foreign = make_incident(org=org_b)
    assert export(admin, foreign, 'hosts').status_code == 404
    # org B's admin cannot read org A's incident either
    assert export(auth(users['admin_b']), case, 'hosts').status_code == 404


def test_incident_visibility_still_applies(app, case, export_as, make_user, org_a):
    """incidents:export does not bypass incident visibility (no read_all / not assigned)."""
    narrow = make_user(org_a, perms=['incidents:read', 'incidents:export', 'hosts:read'])
    assert export_as(narrow, case, 'hosts').status_code == 403


# ── filters / sort / search ──────────────────────────────────────────────

def test_filters_apply_like_the_list_endpoint(admin, case, db, users):
    from app.models import CompromisedHost
    for name, triage in (('CLEAN-1', 'clean'), ('SUSP-1', 'suspicious')):
        db.session.add(CompromisedHost(incident_id=case.id, hostname=name, triage_status=triage,
                                       created_by=users['Administrator'].id))
    db.session.commit()
    _, rows = rows_by_header(export(admin, case, 'hosts', triage_status='clean,suspicious', sort='hostname'))
    assert [r['Hostname'] for r in rows] == ['CLEAN-1', 'SUSP-1']
    _, rows = rows_by_header(export(admin, case, 'hosts', q='susp'))
    assert [r['Hostname'] for r in rows] == ['SUSP-1']
    # acquisition filter is the list endpoint's own
    _, rows = rows_by_header(export(admin, case, 'hosts', acquisition='memory_captured'))
    assert [r['Hostname'] for r in rows] == ['WS-01']
    _, rows = rows_by_header(export(admin, case, 'timeline', mitre_tactic='initial-access'))
    assert len(rows) == 1


def test_bad_filters_are_400(admin, case):
    assert export(admin, case, 'hosts', triage_status='nope').status_code == 400
    assert export(admin, case, 'timeline', sort='bogus').status_code == 400
    assert export(admin, case, 'timeline', mitre_tactic='x;y').status_code == 400


def test_paging_params_are_ignored(admin, case):
    _, rows = rows_by_header(export(admin, case, 'timeline', per_page=1, page=2))
    assert len(rows) == 2


def test_row_cap(admin, case, monkeypatch):
    from app.services import csv_export
    monkeypatch.setattr(csv_export, 'MAX_EXPORT_ROWS', 1)
    resp = export(admin, case, 'timeline')
    assert resp.status_code == 400 and resp.get_json()['error'] == 'export_too_large'


def test_streams_more_rows_than_one_chunk(admin, case, db, users, monkeypatch):
    from app.models import NetworkIndicator
    from app.services import csv_export
    monkeypatch.setattr(csv_export, 'CHUNK', 3)
    db.session.add_all([NetworkIndicator(incident_id=case.id, dns_ip=f'10.1.0.{i}',
                                         created_by=users['Administrator'].id) for i in range(8)])
    db.session.commit()
    table = parse(export(admin, case, 'network-iocs'))
    assert len(table) - 1 == 9


# ── defang ───────────────────────────────────────────────────────────────

def test_defang_ioc_columns_only_when_asked(admin, case, db, users):
    from app.models import HostBasedIndicator, MalwareTool, NetworkIndicator
    uid = users['Administrator'].id
    db.session.add_all([
        NetworkIndicator(incident_id=case.id, dns_ip='1.2.3.4', created_by=uid),
        NetworkIndicator(incident_id=case.id, dns_ip='http://bad.example/x.php', created_by=uid),
        HostBasedIndicator(incident_id=case.id, artifact_type='file', artifact_value='evil.exe', created_by=uid),
        MalwareTool(incident_id=case.id, file_name='dropper.exe', sandbox_report_url='https://sb.example/r/1',
                    created_by=uid),
    ])
    db.session.commit()
    _, plain = rows_by_header(export(admin, case, 'network-iocs'))
    assert {'evil.example.com', '1.2.3.4', 'http://bad.example/x.php'} <= {r['DNS / IP'] for r in plain}
    _, defanged = rows_by_header(export(admin, case, 'network-iocs', defang='true'))
    values = {r['DNS / IP'] for r in defanged}
    assert {'evil[.]example[.]com', '1[.]2[.]3[.]4', 'hxxp://bad[.]example/x.php'} <= values
    _, host = rows_by_header(export(admin, case, 'host-iocs', defang='true'))
    assert {r['Artifact Value'] for r in host} == {'C:\\Users\\a\\evil.exe', 'evil.exe'}  # not network-shaped
    _, mal = rows_by_header(export(admin, case, 'malware', defang='true'))
    assert 'hxxps://sb[.]example/r/1' in {r['Sandbox Report URL'] for r in mal}
    assert 'dropper.exe' in {r['File Name'] for r in mal}  # file names are never defanged


# ── audit ─────────────────────────────────────────────────────────────────

def test_export_writes_audit_row(app, db, admin, case):
    from app.models import AuditLog
    export(admin, case, 'hosts', triage_status='compromised')
    db.session.expire_all()
    row = (AuditLog.query.filter_by(event_type='data_access', action='export_csv', incident_id=case.id)
           .order_by(AuditLog.created_at.desc()).first())
    assert row is not None and row.details['entity'] == 'hosts' and row.details['rows'] == 1
    assert row.details['filters'] == {'triage_status': 'compromised'}
    # denied exports are not logged as successful data access
    assert export(admin, case, 'nothing').status_code == 404
