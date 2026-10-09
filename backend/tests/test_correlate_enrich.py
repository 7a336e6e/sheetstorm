"""W3-DFIR-C: /correlate-iocs and /bulk-enrich (surface-dfir §3.8): input
bounds, incident_id access checks, TLP, audit rows and provider names."""
import uuid

import pytest

API = '/api/v1'


@pytest.fixture
def analyst(users, auth):
    return auth(users['Analyst'])


@pytest.fixture
def shared_ioc(app, db, users, make_incident):
    """(value, incident A, incident B, incident C): the value lives in A and B (org A) only."""
    from app.models import NetworkIndicator
    value = f'corr-{uuid.uuid4().hex[:10]}.shared.example'
    a, b, c = make_incident(), make_incident(), make_incident()
    for inc in (a, b):
        db.session.add(NetworkIndicator(incident_id=inc.id, dns_ip=value, created_by=users['Administrator'].id))
    db.session.add(NetworkIndicator(incident_id=c.id, dns_ip=f'solo-{uuid.uuid4().hex[:8]}.example',
                                    created_by=users['Administrator'].id))
    db.session.commit()
    return value, a, b, c


# ── correlate ─────────────────────────────────────────────────────────────

def test_correlate_by_value_and_by_incident(analyst, shared_ioc):
    value, a, b, c = shared_ioc
    body = analyst.post(f'{API}/correlate-iocs', json={'ioc_values': [value]}).get_json()
    assert body['total'] == 1 and body['correlations'][0]['incident_count'] == 2
    assert {i['id'] for i in body['correlations'][0]['incidents']} == {str(a.id), str(b.id)}

    # values taken from the incident when ioc_values is empty
    body = analyst.post(f'{API}/correlate-iocs', json={'incident_id': str(a.id)}).get_json()
    assert body['incident_id'] == str(a.id)
    assert value in {x['ioc_value'] for x in body['correlations']}
    # an incident whose values are not shared elsewhere correlates with nothing of its own
    body = analyst.post(f'{API}/correlate-iocs', json={'incident_id': str(c.id)}).get_json()
    assert value not in {x['ioc_value'] for x in body['correlations']}


def test_correlate_input_bounds(analyst):
    def post(**body):
        return analyst.post(f'{API}/correlate-iocs', json=body)
    assert post(ioc_values=['x'] * 1001).status_code == 400
    assert post(ioc_values=['x' * 2049]).status_code == 400
    assert post(ioc_values=[1]).status_code == 400
    assert post(ioc_values='nope').status_code == 400
    assert post(ioc_types=['bogus']).status_code == 400
    assert post(ioc_types='ip').status_code == 400
    assert post(incident_id='not-a-uuid').status_code == 400
    assert post(ioc_values=['x' * 2048] * 1000).status_code == 200
    assert analyst.post(f'{API}/correlate-iocs', json=['list']).status_code == 400


def test_correlate_incident_access_checks(app, users, auth, make_incident, org_b):
    foreign = make_incident(org=org_b)
    analyst = auth(users['Analyst'])
    assert analyst.post(f'{API}/correlate-iocs', json={'incident_id': str(foreign.id)}).status_code == 404
    hidden = make_incident(tlp='amber')
    viewer = auth(users['Viewer'])  # Viewer sees only assigned / TLP:WHITE incidents
    assert viewer.post(f'{API}/correlate-iocs', json={'incident_id': str(hidden.id)}).status_code == 403


def test_correlate_never_lists_inaccessible_incidents(app, db, users, auth, make_incident):
    from app.models import NetworkIndicator
    value = f'hid-{uuid.uuid4().hex[:8]}.example'
    visible = make_incident(tlp='white')
    hidden = make_incident(tlp='red')
    for inc in (visible, hidden):
        db.session.add(NetworkIndicator(incident_id=inc.id, dns_ip=value, created_by=users['Administrator'].id))
    db.session.commit()
    body = auth(users['Viewer']).post(f'{API}/correlate-iocs', json={'ioc_values': [value]}).get_json()
    assert body['total'] == 0   # the only other incident is not visible to the viewer
    body = auth(users['Administrator']).post(f'{API}/correlate-iocs', json={'ioc_values': [value]}).get_json()
    assert body['total'] == 1


def test_correlate_is_audited(app, db, analyst, shared_ioc):
    from app.models import AuditLog
    value, a, *_ = shared_ioc
    analyst.post(f'{API}/correlate-iocs', json={'incident_id': str(a.id)})
    db.session.expire_all()
    row = (AuditLog.query.filter_by(event_type='data_access', action='correlate_iocs', incident_id=a.id)
           .order_by(AuditLog.created_at.desc()).first())
    assert row is not None and row.details['correlations'] >= 1


# ── bulk enrich ───────────────────────────────────────────────────────────

@pytest.fixture
def enrich(monkeypatch):
    from app.services.enrichment_service import EnrichmentService
    calls = []

    def fake(ioc_type, value, org_id):
        calls.append((ioc_type, value))
        return {'virustotal': {'malicious': 3}} if ioc_type != 'email' else {}
    monkeypatch.setattr(EnrichmentService, 'auto_enrich_ioc', staticmethod(fake))
    return calls


def test_bulk_enrich_results_summary_and_providers(analyst, enrich):
    resp = analyst.post(f'{API}/bulk-enrich', json={'ioc_values': [
        {'value': 'one.enrich.example', 'type': 'domain'},
        {'value': '203.0.113.7', 'type': 'ip'},
        {'value': 'a' * 64, 'type': 'hash'},
        {'value': 'who@enrich.example', 'type': 'email'},
    ]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['total'] == 4 and body['enriched'] == 4 and body['providers'] == ['virustotal']
    assert [r['status'] for r in body['results']] == ['success'] * 4
    assert 'malicious 3' in body['results'][0]['summary'] and 'tlp' not in body
    assert ('ip-src', '203.0.113.7') in enrich and ('sha256', 'a' * 64) in enrich


@pytest.mark.parametrize('item', [
    {'value': '', 'type': 'ip'},
    {'value': 123, 'type': 'ip'},
    {'value': 'x' * 2049, 'type': 'domain'},
    {'value': 'ok.example', 'type': 'weird'},
    {'value': '../../etc/passwd', 'type': 'domain'},        # URL-path injection into provider URLs
    {'value': 'a/b?x=1', 'type': 'hostname'},
    {'value': 'not-an-ip', 'type': 'ip'},
    {'value': 'zz' * 16, 'type': 'md5'},
    'not-an-object',
])
def test_bulk_enrich_validates_every_item(analyst, enrich, item):
    resp = analyst.post(f'{API}/bulk-enrich', json={'ioc_values': [item]})
    assert resp.status_code == 400 and enrich == []


def test_bulk_enrich_limits_and_shape(analyst, enrich):
    assert analyst.post(f'{API}/bulk-enrich', json={'ioc_values': []}).status_code == 400
    assert analyst.post(f'{API}/bulk-enrich', json={'ioc_values': 'x'}).status_code == 400
    too_many = [{'value': f'h{i}.example', 'type': 'domain'} for i in range(101)]
    assert analyst.post(f'{API}/bulk-enrich', json={'ioc_values': too_many}).status_code == 400
    assert analyst.post(f'{API}/bulk-enrich', json=['x']).status_code == 400
    assert enrich == []


def test_bulk_enrich_incident_access_and_tlp(app, db, users, auth, make_incident, org_b, enrich):
    from app.models import AuditLog
    item = [{'value': 'tlp.enrich.example', 'type': 'domain'}]
    analyst = auth(users['Analyst'])
    foreign = make_incident(org=org_b)
    assert analyst.post(f'{API}/bulk-enrich', json={'ioc_values': item, 'incident_id': str(foreign.id)}
                        ).status_code == 404
    assert analyst.post(f'{API}/bulk-enrich', json={'ioc_values': item, 'incident_id': 'x'}).status_code == 400
    hidden = make_incident(tlp='amber')
    assert auth(users['Viewer']).post(f'{API}/bulk-enrich', json={'ioc_values': item, 'incident_id': str(hidden.id)}
                                      ).status_code == 403

    red = make_incident(tlp='red')
    before = AuditLog.query.filter_by(action='enrichment_blocked_by_tlp').count()
    resp = analyst.post(f'{API}/bulk-enrich', json={'ioc_values': item, 'incident_id': str(red.id)})
    assert resp.status_code == 403 and resp.get_json()['error'] == 'tlp_restricted'
    assert resp.get_json()['tlp'] == 'red' and enrich == []
    assert AuditLog.query.filter_by(action='enrichment_blocked_by_tlp').count() == before + 1

    strict = make_incident(tlp='amber_strict')
    resp = analyst.post(f'{API}/bulk-enrich', json={'ioc_values': item, 'incident_id': str(strict.id)})
    assert resp.status_code == 403 and enrich == []        # org has not enabled amber_strict enrichment


def test_bulk_enrich_amber_strict_allowed_by_org_setting(app, db, org_a, users, auth, make_incident, enrich):
    original = dict(org_a.settings or {})
    org_a.settings = {**original, 'enrichment_allow_amber_strict': True}
    db.session.commit()
    try:
        strict = make_incident(tlp='amber_strict')
        resp = auth(users['Analyst']).post(f'{API}/bulk-enrich', json={
            'ioc_values': [{'value': 'strict.enrich.example', 'type': 'domain'}], 'incident_id': str(strict.id)})
        assert resp.status_code == 200 and resp.get_json()['tlp'] == 'amber_strict'
        assert enrich == [('domain', 'strict.enrich.example')]
    finally:
        org_a.settings = original
        db.session.commit()


def test_bulk_enrich_is_audited(app, db, analyst, make_incident, enrich):
    from app.models import AuditLog
    inc = make_incident(tlp='green')
    analyst.post(f'{API}/bulk-enrich', json={
        'ioc_values': [{'value': 'audit.enrich.example', 'type': 'domain'}], 'incident_id': str(inc.id)})
    db.session.expire_all()
    row = (AuditLog.query.filter_by(event_type='data_access', action='bulk_enrich', incident_id=inc.id)
           .order_by(AuditLog.created_at.desc()).first())
    assert row is not None and row.details['providers'] == ['virustotal'] and row.details['tlp'] == 'green'
