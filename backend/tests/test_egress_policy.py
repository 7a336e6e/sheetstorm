"""W0-FND: server-side TLP enrichment block (services/egress_policy.py).

RED is always blocked (no setting unblocks it); AMBER+STRICT is blocked unless
the org setting enrichment_allow_amber_strict is true. Covers auto-enrich,
playbook enrich_iocs, /bulk-enrich and /threat-intel lookups.
"""
import uuid

import pytest


@pytest.fixture
def org_settings(app, db, org_a):
    original = dict(org_a.settings or {})

    def set_(**kv):
        org_a.settings = {**original, **kv}
        db.session.commit()
    yield set_
    org_a.settings = original
    db.session.commit()


@pytest.fixture
def restricted_value(app, db, users, make_incident):
    """make(tlp) -> (incident, unique value stored as a network IOC in it)."""
    from app.models import NetworkIndicator

    def make(tlp):
        inc = make_incident(tlp=tlp)
        value = f'{uuid.uuid4().hex[:12]}.{tlp.replace("_", "-")}.example'
        db.session.add(NetworkIndicator(incident_id=inc.id, dns_ip=value, created_by=users['Administrator'].id))
        db.session.commit()
        return inc, value
    return make


@pytest.fixture
def bg_tasks(monkeypatch):
    from app import socketio
    tasks = []
    monkeypatch.setattr(socketio, 'start_background_task', lambda fn, *a, **k: tasks.append((fn, a, k)))
    return tasks


def test_red_always_blocked_even_with_setting(app, org_a, org_settings, restricted_value):
    from app.services.egress_policy import EgressBlocked, assert_enrichment_allowed, filter_values_for_enrichment
    org_settings(enrichment_allow_amber_strict=True)
    inc, value = restricted_value('red')
    with pytest.raises(EgressBlocked) as exc:
        assert_enrichment_allowed(inc)
    assert exc.value.status == 403 and exc.value.to_dict()['error'] == 'tlp_restricted'
    allowed, blocked = filter_values_for_enrichment(org_a.id, [value.upper(), 'fresh.example'])
    assert blocked == [value.upper()] and allowed == ['fresh.example']


def test_amber_strict_depends_on_setting(app, org_a, org_settings, restricted_value):
    from app.services.egress_policy import enrichment_allowed, filter_values_for_enrichment
    inc, value = restricted_value('amber_strict')
    assert enrichment_allowed(inc) is False
    assert filter_values_for_enrichment(org_a.id, [value])[1] == [value]
    org_settings(enrichment_allow_amber_strict=True)
    assert enrichment_allowed(inc) is True
    assert filter_values_for_enrichment(org_a.id, [value]) == ([value], [])


def test_other_orgs_red_values_do_not_block(app, org_a, org_b, db, users, make_incident):
    from app.models import NetworkIndicator
    from app.services.egress_policy import filter_values_for_enrichment
    inc_b = make_incident(org=org_b, tlp='red')
    value = f'{uuid.uuid4().hex[:12]}.orgb.example'
    db.session.add(NetworkIndicator(incident_id=inc_b.id, dns_ip=value, created_by=users['admin_b'].id))
    db.session.commit()
    assert filter_values_for_enrichment(org_a.id, [value]) == ([value], [])
    assert filter_values_for_enrichment(org_b.id, [value]) == ([], [value])


def test_auto_enrich_skipped_for_restricted(app, users, auth, org_settings, make_incident,
                                            restricted_value, bg_tasks):
    org_settings(auto_enrich_iocs=True)
    client = auth(users['Analyst'])
    red_inc, red_value = restricted_value('red')
    # 1. IOC created in a RED incident: not enriched
    assert client.post(f'/api/v1/incidents/{red_inc.id}/network-iocs',
                       json={'dns_ip': f'{uuid.uuid4().hex[:8]}.new.example'}).status_code == 201
    assert bg_tasks == []
    # 2. Amber incident, but the value also lives in a RED incident: not enriched
    amber = make_incident()
    assert client.post(f'/api/v1/incidents/{amber.id}/network-iocs',
                       json={'dns_ip': red_value}).status_code == 201
    assert bg_tasks == []
    # 3. Unrestricted value in an amber incident: enriched
    assert client.post(f'/api/v1/incidents/{amber.id}/network-iocs',
                       json={'dns_ip': f'{uuid.uuid4().hex[:8]}.ok.example'}).status_code == 201
    assert len(bg_tasks) == 1


def test_bulk_enrich_blocks_restricted_values(app, users, auth, restricted_value, monkeypatch):
    from app.models import AuditLog
    from app.services.enrichment_service import EnrichmentService
    sent = []
    monkeypatch.setattr(EnrichmentService, 'auto_enrich_ioc',
                        staticmethod(lambda t, v, o: sent.append(v) or {'ok': True}))
    _, red_value = restricted_value('red')
    before = AuditLog.query.filter_by(action='enrichment_blocked_by_tlp').count()
    resp = auth(users['Analyst']).post('/api/v1/bulk-enrich', json={'ioc_values': [
        {'value': red_value, 'type': 'domain'}, {'value': 'fresh-bulk.example', 'type': 'domain'}]})
    assert resp.status_code == 200
    body = resp.get_json()
    statuses = {r['value']: r['status'] for r in body['results']}
    assert statuses == {red_value: 'blocked', 'fresh-bulk.example': 'success'}
    assert body['blocked'] == 1 and sent == ['fresh-bulk.example']
    assert AuditLog.query.filter_by(action='enrichment_blocked_by_tlp').count() == before + 1


@pytest.mark.parametrize('path,key', [
    ('/api/v1/threat-intel/domain/lookup', 'domain'),
    ('/api/v1/threat-intel/ip/lookup', 'ip'),
    ('/api/v1/threat-intel/email/lookup', 'email'),
    ('/api/v1/threat-intel/virustotal/lookup', 'value'),
])
def test_threat_intel_lookups_blocked(app, users, auth, db, make_incident, path, key, monkeypatch):
    from app.models import CompromisedAccount, NetworkIndicator
    import requests
    monkeypatch.setattr(requests, 'get', lambda *a, **k: pytest.fail('outbound call made'))
    inc = make_incident(tlp='red')
    rnd = uuid.uuid4().int
    value = {'ip': f'198.18.{rnd % 250}.{(rnd >> 8) % 250 + 1}', 'email': f'{uuid.uuid4().hex[:8]}@victim.example'}.get(
        key, f'{uuid.uuid4().hex[:10]}.ti.example')
    if key == 'email':
        from datetime import datetime, timezone
        db.session.add(CompromisedAccount(incident_id=inc.id, account_name=value, account_type='domain',
                                          datetime_seen=datetime.now(timezone.utc),
                                          created_by=users['Administrator'].id))
    else:
        db.session.add(NetworkIndicator(incident_id=inc.id, dns_ip=value, created_by=users['Administrator'].id))
    db.session.commit()
    resp = auth(users['Analyst']).post(path, json={key: value, 'type': 'domain'})
    assert resp.status_code == 403 and resp.get_json()['error'] == 'tlp_restricted'


def test_playbook_enrich_skipped_for_red(app, users, auth, make_incident, monkeypatch):
    from app.services.enrichment_service import EnrichmentService
    monkeypatch.setattr(EnrichmentService, 'auto_enrich_ioc',
                        staticmethod(lambda *a, **k: pytest.fail('enrichment called')))
    admin = auth(users['Administrator'])
    inc = make_incident(tlp='red')
    resp = admin.post('/api/v1/playbooks', json={'name': 'PB-enrich', 'definition': {'phases': [
        {'phase': 1, 'name': 'Identification', 'tasks': [{'title': 't'}],
         'actions': [{'key': 'e', 'type': 'enrich_iocs', 'auto_run': True}]}]}})
    assert resp.status_code == 201, resp.get_json()
    result = admin.post(f'/api/v1/incidents/{inc.id}/playbooks/{resp.get_json()["id"]}/activate'
                        ).get_json()['actions_executed'][0]['result']
    assert result['status'] == 'skipped' and result['code'] == 'tlp_restricted'
