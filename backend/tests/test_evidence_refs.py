"""W0-FND: services/evidence_refs.py — incident-scoped typed references."""
import uuid

import pytest


@pytest.fixture
def records(app, db, users, make_incident):
    from app.models import CompromisedHost, HostBasedIndicator, NetworkIndicator, Artifact
    admin = users['Administrator']
    inc, other = make_incident(), make_incident()
    host = CompromisedHost(incident_id=inc.id, hostname='WS-01', created_by=admin.id)
    hioc = HostBasedIndicator(incident_id=inc.id, artifact_type='file', artifact_value='C:\\evil.exe',
                              created_by=admin.id)
    nioc = NetworkIndicator(incident_id=inc.id, dns_ip='198.51.100.9', created_by=admin.id)
    foreign = CompromisedHost(incident_id=other.id, hostname='OTHER', created_by=admin.id)
    db.session.add_all([host, hioc, nioc, foreign])
    db.session.commit()
    return {'inc': inc, 'host': host, 'hioc': hioc, 'nioc': nioc, 'foreign': foreign}


def test_validate_normalizes_aliases_and_dedupes(app, records):
    from app.services.evidence_refs import validate_refs
    r = records
    out = validate_refs(r['inc'].id, [
        {'evidence_type': 'host', 'evidence_id': str(r['host'].id).upper()},
        {'evidence_type': 'host_indicator', 'evidence_id': str(r['hioc'].id)},
        {'evidence_type': 'network_indicator', 'evidence_id': str(r['nioc'].id)},
        {'evidence_type': 'host', 'evidence_id': str(r['host'].id)},
    ])
    assert out == [{'evidence_type': 'host', 'evidence_id': str(r['host'].id)},
                   {'evidence_type': 'host_ioc', 'evidence_id': str(r['hioc'].id)},
                   {'evidence_type': 'network_ioc', 'evidence_id': str(r['nioc'].id)}]


def test_cross_incident_and_unknown_rejected(app, records):
    from app.services.evidence_refs import EvidenceRefsError, validate_refs
    r = records
    with pytest.raises(EvidenceRefsError) as exc:
        validate_refs(r['inc'].id, [
            {'evidence_type': 'host', 'evidence_id': str(r['foreign'].id)},
            {'evidence_type': 'nope', 'evidence_id': str(uuid.uuid4())},
            {'evidence_type': 'host', 'evidence_id': 'not-a-uuid'},
            'junk',
        ])
    err = exc.value
    assert err.status == 400 and err.to_dict()['error'] == 'invalid_evidence_refs'
    assert [i['reason'] for i in err.invalid] == ['not_found', 'unknown_type', 'invalid_id', 'not_an_object']


def test_allowed_types_and_max_refs(app, records):
    from app.services.evidence_refs import EvidenceRefsError, validate_refs
    r = records
    with pytest.raises(EvidenceRefsError) as exc:
        validate_refs(r['inc'].id, [{'evidence_type': 'host', 'evidence_id': str(r['host'].id)}],
                      allowed=['malware'])
    assert exc.value.invalid[0]['reason'] == 'type_not_allowed'
    with pytest.raises(EvidenceRefsError):
        validate_refs(r['inc'].id, [{'evidence_type': 'host', 'evidence_id': str(r['host'].id)}] * 51)
    with pytest.raises(EvidenceRefsError):
        validate_refs(r['inc'].id, {'evidence_type': 'host'})
    assert validate_refs(r['inc'].id, None) == []


def test_resolve_labels_missing_and_restricted(app, db, users, records):
    from app.services.evidence_refs import resolve_refs
    r = records
    refs = [{'evidence_type': 'host', 'evidence_id': str(r['host'].id)},
            {'evidence_type': 'host_indicator', 'evidence_id': str(r['hioc'].id)},
            {'evidence_type': 'host', 'evidence_id': str(r['foreign'].id)}]
    out = resolve_refs(r['inc'].id, refs)
    assert out[0] == {'evidence_type': 'host', 'evidence_id': str(r['host'].id), 'label': 'WS-01', 'missing': False}
    assert out[1]['label'] == 'file: C:\\evil.exe'
    assert out[2]['missing'] is True and out[2]['label'] is None

    class NoPerms:
        def has_permission(self, p):
            return False
    restricted = resolve_refs(r['inc'].id, refs[:1], user=NoPerms())
    assert restricted[0]['label'] is None and restricted[0]['restricted'] is True


def test_register_custom_type(app, records):
    from app.models import CompromisedHost
    from app.services import evidence_refs as er
    er.register_ref_type('test_host_alias_type', CompromisedHost, label=lambda o: f'H:{o.hostname}',
                         aliases=('thx',))
    try:
        out = er.resolve_refs(records['inc'].id, [{'evidence_type': 'thx', 'evidence_id': str(records['host'].id)}])
        assert out[0]['evidence_type'] == 'test_host_alias_type' and out[0]['label'] == 'H:WS-01'
    finally:
        er._REGISTRY.pop('test_host_alias_type', None)
        er._ALIASES.pop('thx', None)
