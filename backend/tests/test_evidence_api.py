"""W2-EVD-API: evidence register API (endpoints/evidence.py).

Register / list / detail / edit, hashes and verification, the custody
workflow, legal hold / dispose / void, ledger reads and verification (with
the ``custody_chain_verified`` audit row), custody parties, the C24
permission matrix, CSV formula escaping and PDFs without external fetches.
Bundles and the offline verifier: test_custody_export_bundle.py.
"""
import csv
import io
import uuid

import pytest

SHA256 = 'a' * 64
MD5 = 'b' * 32


def _url(inc, path=''):
    return f'/api/v1/incidents/{inc.id}/evidence{path}'


def _register(client, inc, **fields):
    body = {'title': fields.pop('title', 'Laptop SSD'), 'evidence_type': fields.pop('evidence_type', 'disk_image')}
    body.update(fields)
    return client.post(_url(inc), json=body)


def _ok_register(client, inc, **fields):
    resp = _register(client, inc, **fields)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _audit_rows(action, **filters):
    from app.models import AuditLog
    return AuditLog.query.filter_by(action=action, **filters).order_by(AuditLog.created_at).all()


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


@pytest.fixture
def fake_storage(monkeypatch):
    from app.services.storage_service import storage_service
    stored = {}

    def store(file_obj, path, content_type=None):
        file_obj.seek(0)
        stored[path] = file_obj.read()
        return True, 'local'

    monkeypatch.setattr(storage_service, 'store_file', store)
    monkeypatch.setattr(storage_service, 'retrieve_file',
                        lambda path, storage_type='local': io.BytesIO(stored[path]) if path in stored else None)
    monkeypatch.setattr(storage_service, 'delete_file', lambda path, storage_type='local': stored.pop(path, None))
    return stored


@pytest.fixture
def party(app, db, users, org_a):
    from app.models import CustodyParty
    p = CustodyParty(organization_id=org_a.id, name='Jane Counsel', organization_name='Law LLP', role='counsel',
                     email='jane@law.test', created_by=users['Administrator'].id)
    db.session.add(p)
    db.session.commit()
    return p


# ── Register / list / detail ────────────────────────────────────────────────

def test_register_list_search_and_detail(app, db, users, admin, make_incident):
    inc = make_incident()
    first = _ok_register(admin, inc, serial_number='SN-77', seal_number='SEAL-1', storage_location='Lab safe B/2',
                         acquisition_hashes=[{'algorithm': 'sha256', 'value': SHA256.upper()},
                                             {'algorithm': 'md5', 'value': MD5, 'source': 'computed_in_lab'}],
                         capacity_bytes=512 * 10 ** 9, acquired_at='2026-10-01T10:00:00Z')
    second = _ok_register(admin, inc, title='iPhone', evidence_type='mobile_device')
    assert (first['evidence_number'], second['evidence_number']) == ('EV-0001', 'EV-0002')
    assert first['ledger_entries'][0]['action'] == 'register'
    assert {h['value'] for h in first['acquisition_hashes']} == {SHA256, MD5}
    assert first['acquisition_hashes'][0]['source'] == 'tool_reported'

    body = admin.get(_url(inc)).get_json()
    assert body['total'] == 2 and [i['evidence_number'] for i in body['items']] == ['EV-0001', 'EV-0002']
    assert admin.get(_url(inc, '?sort=-sequence_number')).get_json()['items'][0]['evidence_number'] == 'EV-0002'
    for q in ('EV-0002', 'iphone', '2'):
        assert [i['id'] for i in admin.get(_url(inc, f'?q={q}')).get_json()['items']] == [second['id']], q
    assert [i['id'] for i in admin.get(_url(inc, f'?search={SHA256}')).get_json()['items']] == [first['id']]
    assert [i['id'] for i in admin.get(_url(inc, '?q=SEAL-1')).get_json()['items']] == [first['id']]
    assert admin.get(_url(inc, '?type=mobile_device')).get_json()['total'] == 1
    assert admin.get(_url(inc, '?custody_state=checked_out')).get_json()['total'] == 0
    assert admin.get(_url(inc, '?verification=none')).get_json()['total'] == 2
    assert admin.get(_url(inc, '?custody_state=lost')).status_code == 400
    assert admin.get(_url(inc, '?legal_hold=maybe')).status_code == 400

    resp = admin.get(_url(inc, f"/{first['id']}"))
    assert resp.status_code == 200 and resp.headers['ETag'] == f'"{resp.get_json()["version"]}"'
    detail = resp.get_json()
    assert detail['chain_summary']['status'] == 'intact' and detail['chain_summary']['head_seq'] == 1
    assert detail['artifacts'] == [] and detail['children'] == []
    # A healthy chain behind a plain detail / custody-list view writes no audit row.
    assert admin.get(_url(inc, f"/{first['id']}/custody")).status_code == 200
    assert _audit_rows('custody_chain_verified', resource_id=uuid.UUID(first['id'])) == []
    # An explicit verify always does.
    assert admin.get(_url(inc, f"/{first['id']}/custody/verify")).status_code == 200
    rows = _audit_rows('custody_chain_verified', resource_id=uuid.UUID(first['id']))
    assert len(rows) == 1 and rows[0].details['context'] == 'verify' and rows[0].details['status'] == 'intact'
    assert rows[0].event_type == 'data_access'


@pytest.mark.parametrize('body,needle', [
    ({'evidence_type': 'disk_image'}, 'title'),
    ({'title': 'x'}, 'evidence_type'),
    ({'title': 'x', 'evidence_type': 'teleporter'}, 'evidence_type'),
    ({'title': 'x', 'evidence_type': 'other', 'extra_data': {'a': 1}}, 'extra_data'),
    ({'title': 'x', 'evidence_type': 'other', 'custody_state': 'disposed'}, 'custody_state'),
    ({'title': 'x', 'evidence_type': 'other', 'acquisition_hashes': [{'algorithm': 'sha256', 'value': 'abc'}]},
     'sha256'),
    ({'title': 'x', 'evidence_type': 'other', 'acquisition_hashes': [{'algorithm': 'md5', 'value': 'g' * 32}]},
     'md5'),
    ({'title': 'x', 'evidence_type': 'other', 'acquisition_hashes': [{'algorithm': 'crc32', 'value': 'ab'}]},
     'algorithm'),
    ({'title': 'x', 'evidence_type': 'other',
      'acquisition_hashes': [{'algorithm': 'md5', 'value': MD5}, {'algorithm': 'md5', 'value': 'c' * 32}]},
     'Duplicate'),
    ({'title': 'x', 'evidence_type': 'other', 'acquired_at': '2999-01-01T00:00:00Z'}, 'future'),
    ({'title': 'x', 'evidence_type': 'other', 'acquired_at': 'yesterday'}, 'acquired_at'),
    ({'title': 'x', 'evidence_type': 'other', 'capacity_bytes': -1}, 'capacity_bytes'),
    ({'title': 'x', 'evidence_type': 'other', 'capacity_bytes': True}, 'capacity_bytes'),
    ({'title': 'x' * 256, 'evidence_type': 'other'}, 'title'),
    ({'title': 'x', 'evidence_type': 'other', 'serial_number': 'y' * 121}, 'serial_number'),
])
def test_register_validation(app, admin, make_incident, body, needle):
    resp = admin.post(_url(make_incident()), json=body)
    assert resp.status_code == 400, resp.get_json()
    assert needle in resp.get_json()['message']


def test_cross_scope_references_are_404(app, db, users, auth, admin, make_incident, make_evidence, org_b, party):
    from app.models import CompromisedHost, CustodyParty
    inc, other = make_incident(), make_incident()
    foreign_item = make_evidence(other)
    host = CompromisedHost(incident_id=other.id, hostname='WS-OTHER', created_by=users['Administrator'].id)
    b_party = CustodyParty(organization_id=org_b.id, name='B lab', role='third_party_lab',
                           created_by=users['admin_b'].id)
    db.session.add_all([host, b_party])
    db.session.commit()
    for extra in ({'parent_id': str(foreign_item.id)}, {'source_host_id': str(host.id)},
                  {'acquired_by_user_id': str(users['admin_b'].id)}):
        assert _register(admin, inc, **extra).status_code == 404, extra
    item = _ok_register(admin, inc)
    for body in ({'to_party_id': str(b_party.id), 'purpose': 'p'},
                 {'to_user_id': str(users['admin_b'].id), 'purpose': 'p'}):
        assert admin.post(_url(inc, f"/{item['id']}/custody/check-out"), json=body).status_code == 404, body
    # Another incident's item through this incident's URL, and org B on org A.
    assert admin.get(_url(inc, f'/{foreign_item.id}')).status_code == 404
    assert auth(users['admin_b']).get(_url(inc, f"/{item['id']}")).status_code == 404
    b_list = auth(users['admin_b']).get('/api/v1/custody-parties?include_inactive=true').get_json()['items']
    assert str(party.id) not in [p['id'] for p in b_list] and str(b_party.id) in [p['id'] for p in b_list]


def test_same_org_host_snapshot_and_derived_item(app, db, users, admin, make_incident):
    from app.models import ChainOfCustody, CompromisedHost
    inc = make_incident()
    host = CompromisedHost(incident_id=inc.id, hostname='WS-042', created_by=users['Administrator'].id)
    db.session.add(host)
    db.session.commit()
    parent = _ok_register(admin, inc, source_host_id=str(host.id))
    assert parent['source_host_label'] == 'WS-042'
    child = _ok_register(admin, inc, title='$MFT', evidence_type='digital_file', parent_id=parent['id'],
                         derivation_note='extracted with FTK')
    assert child['parent']['evidence_number'] == 'EV-0001'
    assert [e['action'] for e in child['ledger_entries']] == ['register', 'derive']
    derive = ChainOfCustody.query.filter_by(evidence_item_id=uuid.UUID(parent['id']), action='derive').one()
    assert derive.extra_data['child']['evidence_number'] == 'EV-0002'
    assert [c['evidence_number'] for c in admin.get(_url(inc, f"/{parent['id']}")).get_json()['children']] == [
        'EV-0002']
    assert admin.get(_url(inc, f"?parent_id={parent['id']}")).get_json()['total'] == 1


def test_patch_appends_update_entry_and_honours_if_match(app, db, admin, make_incident):
    inc = make_incident()
    item = _ok_register(admin, inc, serial_number='OLD')
    url = _url(inc, f"/{item['id']}")
    resp = admin.patch(url, json={'serial_number': 'NEW', 'make': 'Samsung'},
                       headers={'If-Match': f'"{item["version"]}"'})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['serial_number'] == 'NEW' and body['version'] > item['version']
    assert resp.headers['ETag'] == f'"{body["version"]}"'
    entry = body['ledger_entries'][0]
    assert entry['action'] == 'update'
    assert entry['extra_data']['changes'] == {'serial_number': ['OLD', 'NEW'], 'make': [None, 'Samsung']}
    rows = _audit_rows('update', resource_id=uuid.UUID(item['id']))
    assert rows[-1].details['changes']['serial_number'] == {'from': 'OLD', 'to': 'NEW'}

    stale = admin.patch(url, json={'model': 'X'}, headers={'If-Match': f'"{item["version"]}"'})
    assert stale.status_code == 409 and stale.get_json()['error'] == 'conflict'
    assert admin.patch(url, json={'model': 'X', 'expected_version': item['version']}).status_code == 409
    for field in ('acquisition_hashes', 'parent_id', 'storage_location', 'custody_state', 'sequence_number'):
        assert admin.patch(url, json={field: None}).status_code == 400, field
    assert admin.patch(url, json={'title': ''}).status_code == 400
    # A no-op edit appends nothing.
    assert admin.patch(url, json={'serial_number': 'NEW'}).get_json()['ledger_entries'] == []


def test_add_hash_and_supersede(app, admin, make_incident):
    inc = make_incident()
    item = _ok_register(admin, inc)
    url = _url(inc, f"/{item['id']}/hashes")
    assert admin.post(url, json={'algorithm': 'sha256', 'value': SHA256}).status_code == 400  # source required
    resp = admin.post(url, json={'algorithm': 'sha256', 'value': SHA256, 'source': 'computed_in_lab'})
    assert resp.status_code == 201 and resp.get_json()['ledger_entries'][0]['action'] == 'add_hash'
    dup = admin.post(url, json={'algorithm': 'sha256', 'value': 'c' * 64, 'source': 'computed_in_lab'})
    assert dup.status_code == 409
    assert admin.post(url, json={'algorithm': 'sha256', 'value': 'c' * 64, 'source': 'computed_in_lab',
                                 'supersedes': SHA256}).status_code == 400  # reason required
    assert admin.post(url, json={'algorithm': 'sha256', 'value': 'c' * 64, 'source': 'computed_in_lab',
                                 'supersedes': 'd' * 64, 'reason': 'typo'}).status_code == 400  # unknown value
    resp = admin.post(url, json={'algorithm': 'sha256', 'value': 'c' * 64, 'source': 'computed_in_lab',
                                 'supersedes': SHA256, 'reason': 'typo in tool output'})
    assert resp.status_code == 201, resp.get_json()
    hashes = resp.get_json()['acquisition_hashes']
    assert [(h['value'][:1], bool(h.get('superseded'))) for h in hashes] == [('a', True), ('c', False)]


def test_lab_verification_match_mismatch_and_no_reference(app, admin, make_incident):
    inc = make_incident()
    item = _ok_register(admin, inc, acquisition_hashes=[{'algorithm': 'sha256', 'value': SHA256}])
    url = _url(inc, f"/{item['id']}/verify")
    ok = admin.post(url, json={'algorithm': 'sha256', 'observed_hash': SHA256, 'tool': 'FTK Imager 4.7'})
    assert ok.status_code == 200 and ok.get_json()['verification']['match'] is True
    assert ok.get_json()['last_verification_result'] == 'match'
    bad = admin.post(url, json={'algorithm': 'sha256', 'observed_hash': 'f' * 64})
    assert bad.status_code == 200 and bad.get_json()['last_verification_result'] == 'mismatch'
    assert _audit_rows('evidence_integrity_mismatch', resource_id=uuid.UUID(item['id']))
    assert admin.post(url, json={'algorithm': 'md5', 'observed_hash': MD5}).status_code == 409
    assert admin.post(url, json={'algorithm': 'sha256', 'observed_hash': 'zz'}).status_code == 400


def test_recompute_verification_from_stored_file(app, db, admin, make_incident, fake_storage):
    inc = make_incident()
    up = admin.post(f'/api/v1/incidents/{inc.id}/artifacts', data={'file': (io.BytesIO(b'bytes'), 'disk.raw')},
                    content_type='multipart/form-data')
    assert up.status_code == 201, up.get_json()
    art = up.get_json()
    url = _url(inc, f"/{art['evidence_item']['id']}/verify")
    resp = admin.post(url, json={'recompute': True, 'artifact_id': art['id']})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['verification']['match'] is True
    entry = resp.get_json()['ledger_entries'][0]
    assert entry['artifact_id'] == art['id'] and entry['extra_data']['method'] == 'recompute_stored_file'
    fake_storage[next(iter(fake_storage))] = b'tampered'
    assert admin.post(url, json={'recompute': True, 'artifact_id': art['id']}).get_json()['verification'][
        'match'] is False
    other = _ok_register(admin, inc)
    assert admin.post(_url(inc, f"/{other['id']}/verify"),
                      json={'recompute': True, 'artifact_id': art['id']}).status_code == 404


# ── Custody workflow ────────────────────────────────────────────────────────

def test_custody_workflow_end_to_end(app, db, users, admin, make_incident):
    from app.models import CustodyParty
    inc = make_incident()
    item = _ok_register(admin, inc, storage_location='Lab safe B/2')
    iurl = _url(inc, f"/{item['id']}")

    out = admin.post(iurl + '/custody/check-out', json={'to_user_id': str(users['Analyst'].id),
                                                         'purpose': 'imaging', 'transfer_method': 'internal'})
    assert out.status_code == 200, out.get_json()
    assert out.get_json()['custody_state'] == 'checked_out' and out.get_json()['holder']['type'] == 'user'
    assert admin.post(iurl + '/custody/check-out', json={'to_user_id': str(users['Analyst'].id),
                                                         'purpose': 'again'}).status_code == 409
    back = admin.post(iurl + '/custody/check-in', json={'storage_location': 'Lab safe B/3', 'seal_intact': True,
                                                         'seal_number': 'S-2'})
    assert back.status_code == 200 and back.get_json()['storage_location'] == 'Lab safe B/3'
    assert admin.post(iurl + '/custody/check-in', json={'storage_location': 'x', 'seal_intact': True}
                      ).status_code == 409
    assert admin.post(iurl + '/custody/transfer', json={'new_party': {'name': 'Acme Lab', 'role': 'third_party_lab'},
                                                        'reason': 'expert review'}).status_code == 400  # method
    xfer = admin.post(iurl + '/custody/transfer', json={
        'new_party': {'name': 'Acme Lab', 'role': 'third_party_lab', 'email': 'lab@acme.test'},
        'reason': 'expert review', 'transfer_method': 'courier', 'tracking_number': 'TRACK-1'})
    assert xfer.status_code == 200, xfer.get_json()
    body = xfer.get_json()
    entry = body['ledger_entries'][0]
    assert body['custody_state'] == 'transferred' and body['holder']['name'] == 'Acme Lab'
    assert entry['extra_data']['party']['name'] == 'Acme Lab' and entry['extra_data']['tracking_number'] == 'TRACK-1'
    assert CustodyParty.query.filter_by(name='Acme Lab').one().created_by == users['Administrator'].id

    ack_url = iurl + f"/custody/{entry['id']}/acknowledge"
    assert admin.post(ack_url, json={}).status_code == 400
    ack = admin.post(ack_url, json={'typed_name': 'Dr. Lab', 'statement': 'received sealed',
                                    'stated_at': '2026-10-02T09:00:00Z'})
    assert ack.status_code == 200, ack.get_json()
    assert admin.post(ack_url, json={'typed_name': 'Dr. Lab'}).status_code == 409
    assert admin.post(iurl + f'/custody/{uuid.uuid4()}/acknowledge', json={'typed_name': 'x'}).status_code == 404

    custody = admin.get(iurl + '/custody').get_json()
    by_action = {e['action']: e for e in custody['entries']}
    assert by_action['transfer']['acknowledged_by_entry_id'] == by_action['acknowledge']['id']
    assert {e['signature_status'] for e in custody['entries']} == {'valid'}
    assert {e['link_status'] for e in custody['entries']} == {'ok'}

    assert admin.post(iurl + '/custody/check-in', json={'storage_location': 'Vault', 'seal_intact': False}
                      ).status_code == 200
    assert admin.post(iurl + '/dispose', json={'method': 'destroyed', 'reason': 'retention ended',
                                               'witness_name': 'W. Itness'}).get_json()['custody_state'] == 'disposed'
    assert admin.post(iurl + '/custody/check-out', json={'to_user_id': str(users['Analyst'].id),
                                                         'purpose': 'p'}).status_code == 409
    verify = admin.get(iurl + '/custody/verify').get_json()
    assert verify['status'] == 'intact' and verify['item_chain']['length'] == 7
    incident_verify = admin.get(_url(inc, '/custody/verify')).get_json()
    assert incident_verify['status'] == 'intact' and incident_verify['items'][item['id']]['length'] == 7


def test_recipient_must_reach_the_incident(app, db, users, admin, make_incident):
    inc = make_incident()
    item = _ok_register(admin, inc)
    resp = admin.post(_url(inc, f"/{item['id']}/custody/check-out"),
                      json={'to_user_id': str(users['Operator'].id), 'purpose': 'p'})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'recipient_no_access'
    two = admin.post(_url(inc, f"/{item['id']}/custody/check-out"),
                     json={'to_user_id': str(users['Analyst'].id), 'to_party_id': str(uuid.uuid4()), 'purpose': 'p'})
    assert two.status_code == 400


def test_inactive_party_cannot_receive(app, db, users, admin, make_incident, party):
    party.is_active = False
    db.session.commit()
    inc = make_incident()
    item = _ok_register(admin, inc)
    resp = admin.post(_url(inc, f"/{item['id']}/custody/check-out"),
                      json={'to_party_id': str(party.id), 'purpose': 'p'})
    assert resp.status_code == 409


def test_legal_hold_void_and_dispose_rules(app, db, users, admin, make_incident):
    inc = make_incident()
    parent = _ok_register(admin, inc)
    child = _ok_register(admin, inc, parent_id=parent['id'])
    purl, curl = _url(inc, f"/{parent['id']}"), _url(inc, f"/{child['id']}")
    assert admin.post(purl + '/legal-hold', json={'hold': 'yes'}).status_code == 400
    assert admin.post(purl + '/legal-hold', json={'until': '2000-01-01T00:00:00Z'}).status_code == 400
    held = admin.post(purl + '/legal-hold', json={'reason': 'litigation'})
    assert held.status_code == 200 and held.get_json()['under_legal_hold'] is True
    assert _audit_rows('evidence_legal_hold', resource_id=uuid.UUID(parent['id']))
    # The parent's hold covers the derived item.
    assert admin.post(curl + '/dispose', json={'method': 'destroyed', 'reason': 'r'}).status_code == 409
    assert admin.post(purl + '/void', json={'reason': 'mistake'}).status_code == 409
    assert admin.post(purl + '/legal-hold', json={'hold': False}).get_json()['under_legal_hold'] is False
    assert admin.post(purl + '/void', json={'reason': 'mistake'}).status_code == 409  # live child
    assert admin.post(curl + '/void', json={}).status_code == 400
    assert admin.post(curl + '/void', json={'reason': 'entered in error'}).get_json()['voided_at']
    assert admin.post(purl + '/void', json={'reason': 'mistake'}).status_code == 200
    assert admin.get(_url(inc)).get_json()['total'] == 0
    assert admin.get(_url(inc, '?include_voided=true')).get_json()['total'] == 2
    assert admin.patch(curl, json={'title': 'x'}).status_code == 409
    assert admin.post(curl + '/hashes', json={'algorithm': 'md5', 'value': MD5, 'source': 'tool_reported'}
                      ).status_code == 409
    assert admin.post(purl + '/dispose', json={'method': 'shredded', 'reason': 'r'}).status_code == 400


def test_mutations_emit_after_commit_and_stamp_the_client(app, db, users, admin, make_incident, monkeypatch):
    from app.models import ChainOfCustody
    from app.services import realtime
    seen = []

    def emit(incident_id, entity, op, obj=None, id=None, data=None):
        from app import db as _db
        seen.append((entity, op, obj in _db.session.new or obj in _db.session.dirty))
    monkeypatch.setattr(realtime, 'emit_change', emit)
    inc = make_incident()
    item = admin.post(_url(inc), json={'title': 'Phone', 'evidence_type': 'mobile_device'},
                      headers={'X-SheetStorm-Client': 'mcp-server'}).get_json()
    assert seen == [('evidence_item', 'created', False), ('custody_entry', 'created', False)]
    entry = ChainOfCustody.query.filter_by(evidence_item_id=uuid.UUID(item['id'])).one()
    assert entry.extra_data['client'] == 'mcp-server'
    seen.clear()
    admin.patch(_url(inc, f"/{item['id']}"), json={'model': 'X'})
    assert [s[:2] for s in seen] == [('evidence_item', 'updated'), ('custody_entry', 'created')]


def test_tampered_chain_is_audited_as_security_event(app, db, admin, make_incident, ledger_tamper):
    from app.models import ChainOfCustody
    inc = make_incident()
    item = _ok_register(admin, inc)
    admin.patch(_url(inc, f"/{item['id']}"), json={'model': 'X'})
    with ledger_tamper() as s:
        s.query(ChainOfCustody).filter_by(evidence_item_id=uuid.UUID(item['id']), seq=1).update(
            {'purpose': 'rewritten'})
    v = admin.get(_url(inc, f"/{item['id']}/custody/verify")).get_json()
    assert v['status'] == 'compromised'
    row = _audit_rows('custody_chain_verified', resource_id=uuid.UUID(item['id']))[-1]
    assert row.event_type == 'security_event' and row.details['status'] == 'compromised'
    assert row.details['context'] == 'verify' and row.details['break_count'] >= 1
    # The implicit verification of a plain detail view audits an unhealthy chain.
    assert admin.get(_url(inc, f"/{item['id']}")).status_code == 200
    row = _audit_rows('custody_chain_verified', resource_id=uuid.UUID(item['id']))[-1]
    assert row.event_type == 'security_event' and row.details['context'] == 'detail'
    assert row.details['status'] == 'compromised'


# ── Custody parties ─────────────────────────────────────────────────────────

def test_custody_parties_crud_scoping_and_versioning(app, db, users, auth, admin, org_b):
    analyst = auth(users['Analyst'])
    name = f'Det. Smith {uuid.uuid4().hex[:8]}'
    created = analyst.post('/api/v1/custody-parties', json={'name': name, 'role': 'law_enforcement',
                                                            'organization_name': 'City PD'})
    assert created.status_code == 201, created.get_json()
    p = created.get_json()
    assert analyst.post('/api/v1/custody-parties', json={'name': 'x', 'role': 'wizard'}).status_code == 400
    assert analyst.post('/api/v1/custody-parties', json={'role': 'counsel'}).status_code == 400
    assert analyst.post('/api/v1/custody-parties', json={'name': 'x', 'is_active': False}).status_code == 400
    url = f"/api/v1/custody-parties/{p['id']}"
    assert analyst.patch(url, json={'phone': '555'}).status_code == 403  # artifacts:delete
    assert auth(users['Viewer']).get('/api/v1/custody-parties').status_code == 403
    assert auth(users['admin_b']).get(url).status_code == 404
    assert auth(users['admin_b']).patch(url, json={'phone': '1'}).status_code == 404
    names = [x['name'] for x in admin.get(f'/api/v1/custody-parties?q={name[-8:]}').get_json()['items']]
    assert names == [name]

    resp = admin.patch(url, json={'is_active': False, 'phone': '555-0100'}, headers={'If-Match': f'"{p["version"]}"'})
    assert resp.status_code == 200 and resp.headers['ETag'] == f'"{resp.get_json()["version"]}"'
    assert admin.patch(url, json={'phone': '1'}, headers={'If-Match': f'"{p["version"]}"'}).status_code == 409
    assert p['id'] not in [x['id'] for x in admin.get('/api/v1/custody-parties').get_json()['items']]
    assert p['id'] in [x['id'] for x in admin.get('/api/v1/custody-parties?include_inactive=true&role=law_enforcement'
                                                  ).get_json()['items']]
    ok_rows = [r for r in _audit_rows('update', resource_id=uuid.UUID(p['id'])) if r.status_code == 200]
    assert ok_rows[-1].details['changes']['is_active'] == {'from': True, 'to': False}


# ── C24 permission matrix ───────────────────────────────────────────────────

READ, WRITE, MANAGE, EXPORT = 'read', 'write', 'manage', 'export'
ROLE_GRANTS = {
    'Administrator': {READ, WRITE, MANAGE, EXPORT},
    'Incident Responder': {READ, WRITE, EXPORT},
    'Analyst': {READ, WRITE},
    'Manager': {READ, EXPORT},
    'Operator': {READ},
    'Viewer': set(),
}
# (name, method, path (formatted with item), body, needs)
MATRIX = [
    ('list', 'GET', '', None, {READ}),
    ('detail', 'GET', '/{item}', None, {READ}),
    ('custody', 'GET', '/{item}/custody', None, {READ}),
    ('verify_item', 'GET', '/{item}/custody/verify', None, {READ}),
    ('verify_incident', 'GET', '/custody/verify', None, {READ}),
    ('export_json', 'GET', '/{item}/custody/export?format=json', None, {READ}),
    ('export_csv', 'GET', '/{item}/custody/export?format=csv', None, {READ}),
    ('export_form', 'GET', '/{item}/custody/export?format=form&blank_rows=2', None, {READ}),
    ('export_bundle', 'GET', '/{item}/custody/export?format=bundle', None, {READ, EXPORT}),
    ('register_csv', 'GET', '/export?format=csv', None, {READ, EXPORT}),
    ('register_pdf', 'GET', '/export?format=pdf', None, {READ, EXPORT}),
    ('register_bundle', 'GET', '/export?format=bundle', None, {READ, EXPORT}),
    ('register', 'POST', '', {'title': 'x', 'evidence_type': 'other'}, {WRITE}),
    ('patch', 'PATCH', '/{item}', {'model': 'M'}, {WRITE}),
    ('void', 'POST', '/{item}/void', {}, {MANAGE}),            # allowed -> 400 (reason missing)
    ('dispose', 'POST', '/{item}/dispose', {}, {MANAGE}),      # allowed -> 400
    ('hold', 'POST', '/{item}/legal-hold', {'hold': 'x'}, {MANAGE}),  # allowed -> 400
]


@pytest.fixture
def matrix_setup(app, db, users, make_incident, make_evidence):
    # TLP:WHITE + Operator assigned: every role can SEE the incident, so a 403
    # is about the permission under test, not visibility.
    inc = make_incident(tlp='white', assign=[users['Operator']])
    return inc, make_evidence(inc)


@pytest.mark.parametrize('role', list(ROLE_GRANTS))
def test_permission_matrix(app, users, auth, matrix_setup, role):
    inc, item = matrix_setup
    client = auth(users[role])
    failures = []
    for name, method, path, body, needs in MATRIX:
        resp = client.open(method, _url(inc, path.format(item=item.id)), json=body)
        allowed = needs <= ROLE_GRANTS[role]
        ok = resp.status_code != 403 and resp.status_code < 500 if allowed else resp.status_code == 403
        if not ok:
            failures.append((name, resp.status_code, (resp.get_json(silent=True) or {}).get('message')))
    assert not failures, f'{role}: {failures}'


def test_export_permission_alone_is_not_enough(app, db, make_user, org_a, auth, matrix_setup):
    inc, item = matrix_setup
    exporter = auth(make_user(org_a, perms=['incidents:read', 'incidents:read_all', 'incidents:export']))
    assert exporter.get(_url(inc, '/export?format=csv')).status_code == 403
    assert exporter.get(_url(inc, f'/{item.id}/custody/export?format=bundle')).status_code == 403
    reader = auth(make_user(org_a, perms=['incidents:read', 'incidents:read_all', 'artifacts:read']))
    resp = reader.get(_url(inc, '/export?format=csv'))
    assert resp.status_code == 403 and 'incidents:export' in resp.get_json()['message']
    assert reader.get(_url(inc, f'/{item.id}/custody/export?format=csv')).status_code == 200


def test_team_restricted_incident_is_hidden(app, db, users, auth, make_incident, make_evidence, org_a):
    from app.models import IncidentTeam, Team
    team = Team(organization_id=org_a.id, name=f'T-{uuid.uuid4().hex[:6]}')
    db.session.add(team)
    db.session.flush()
    inc = make_incident()
    db.session.add(IncidentTeam(incident_id=inc.id, team_id=team.id))
    db.session.commit()
    item = make_evidence(inc)
    assert auth(users['Analyst']).get(_url(inc, f'/{item.id}')).status_code == 403
    assert auth(users['Analyst']).get(_url(inc)).status_code == 403


# ── Export safety ───────────────────────────────────────────────────────────

FORMULA = "=cmd|' /C calc'!A0"


def _csv_rows(resp):
    assert resp.status_code == 200 and resp.mimetype == 'text/csv'
    return list(csv.reader(io.StringIO(resp.get_data(as_text=True))))


def test_csv_exports_escape_formulas(app, users, admin, make_incident):
    inc = make_incident()
    item = _ok_register(admin, inc, title=FORMULA, serial_number='+1-800', seal_number='@SUM(A1)')
    admin.post(_url(inc, f"/{item['id']}/custody/check-out"),
               json={'to_user_id': str(users['Analyst'].id), 'purpose': '=HYPERLINK("http://evil")'})
    register = _csv_rows(admin.get(_url(inc, '/export?format=csv')))
    header, row = register[0], register[1]
    assert row[header.index('title')] == "'" + FORMULA
    assert row[header.index('serial_number')] == "'+1-800" and row[header.index('seal_number')] == "'@SUM(A1)"
    assert row[header.index('chain_status')] == 'intact'
    entries = _csv_rows(admin.get(_url(inc, f"/{item['id']}/custody/export?format=csv")))
    purposes = [r[entries[0].index('purpose')] for r in entries[1:]]
    assert "'=HYPERLINK(\"http://evil\")" in purposes
    assert not any(cell[:1] in ('=', '+', '-', '@') for r in register[1:] + entries[1:] for cell in r)


def test_item_json_export_appends_export_entry(app, admin, make_incident):
    inc = make_incident()
    item = _ok_register(admin, inc)
    report = admin.get(_url(inc, f"/{item['id']}/custody/export?format=json")).get_json()
    assert [e['action'] for e in report['entries']] == ['register', 'export']
    assert report['entries'][-1]['extra_data']['format'] == 'json'
    assert report['verification']['status'] == 'intact' and report['signing_key_id']
    assert admin.get(_url(inc, f"/{item['id']}/custody/export?format=xml")).status_code == 400
    assert admin.get(_url(inc, f"/{item['id']}/custody/export?format=form&blank_rows=21")).status_code == 400
    assert admin.get(_url(inc, '/export?format=json')).status_code == 400


def test_pdfs_are_escaped_and_never_fetch(app, users, admin, make_incident, monkeypatch):
    from app.services import pdf_render
    fetched, rendered = [], []
    original = pdf_render.html_to_pdf

    def recorder(url, *a, **k):
        fetched.append(url)
        raise ValueError('denied')

    def capture(html):
        rendered.append(html)
        return original(html)
    monkeypatch.setattr(pdf_render, 'deny_all_url_fetcher', recorder)
    monkeypatch.setattr(pdf_render, 'html_to_pdf', capture)
    inc = make_incident(title='<script>x</script>')
    hostile = '<img src="http://169.254.169.254/latest/meta-data/"><link rel="stylesheet" href="file:///etc/passwd">'
    item = _ok_register(admin, inc, title=hostile, description=hostile, serial_number='<b>SN</b>')
    admin.post(_url(inc, f"/{item['id']}/custody/check-out"),
               json={'to_user_id': str(users['Analyst'].id), 'purpose': hostile})
    for path in (f"/{item['id']}/custody/export?format=pdf", f"/{item['id']}/custody/export?format=form",
                 '/export?format=pdf'):
        resp = admin.get(_url(inc, path))
        assert resp.status_code == 200 and resp.mimetype == 'application/pdf', path
        assert resp.get_data().startswith(b'%PDF'), path
    assert len(rendered) == 3 and fetched == []
    for html in rendered:
        assert '&lt;img' in html and '<img' not in html and '<link' not in html and '<script>' not in html
        assert 'src="http' not in html and 'href="file' not in html
    form = rendered[1]
    assert 'Chain of Custody Form' in form and form.count('class="blank"') == 8 and 'EV-0001' in form
