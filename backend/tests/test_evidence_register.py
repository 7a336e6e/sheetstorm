"""W1-EVD-CORE: evidence register model + v3 custody ledger.

Numbering, chain integrity (item + incident chains), append-only triggers,
tamper detection (with the triggers disabled via ``ledger_tamper``), legacy
seal, key rotation, concurrency, custody state machine, one-transaction
upload, tombstone delete, offline verifier, registrations.
"""
import ast
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UTILS_DIR = os.path.join(BACKEND_DIR, 'app', 'utils')


def _ledger():
    from app.services.custody_ledger import CustodyLedger
    return CustodyLedger


def _reasons(result):
    return {b['reason'] for b in result['breaks']}


# ── Registration / numbering ────────────────────────────────────────────────

def test_register_numbers_items_per_incident_and_writes_register_entry(app, db, users, make_incident,
                                                                        make_evidence):
    from app.models import ChainOfCustody
    inc, other = make_incident(), make_incident()
    a, b = make_evidence(inc, title='Laptop SSD'), make_evidence(inc)
    c = make_evidence(other)
    assert (a.evidence_number, b.evidence_number, c.evidence_number) == ('EV-0001', 'EV-0002', 'EV-0001')
    assert a.display_id == f'CASE-{inc.incident_number}/EV-0001' or inc.incident_number is None
    entry = ChainOfCustody.query.filter_by(evidence_item_id=a.id).one()
    assert entry.action == 'register' and entry.seq == 1 and entry.incident_seq == 1
    assert entry.extra_data['item']['title'] == 'Laptop SSD'
    assert entry.extra_data['state_after']['custody_state'] == 'in_storage'
    assert entry.extra_data['performer_name'] == users['Administrator'].name


def test_voided_item_keeps_its_number_and_blocks_further_custody(app, db, users, make_incident, make_evidence):
    from app.services.custody_ledger import CustodyError
    L = _ledger()
    inc = make_incident()
    first = make_evidence(inc)
    L.void(first, actor=users['Administrator'], reason='entered in error')
    db.session.commit()
    second = make_evidence(inc)
    assert first.voided_at is not None and second.evidence_number == 'EV-0002'
    with pytest.raises(CustodyError):
        L.check_out(first, actor=users['Administrator'], purpose='x', to_user=users['Analyst'])
    db.session.rollback()


def test_void_requires_reason_and_no_live_children(app, db, users, make_incident, make_evidence):
    from app.services.custody_ledger import CustodyError
    L = _ledger()
    inc = make_incident()
    parent = make_evidence(inc)
    child = make_evidence(inc, parent_id=parent.id, derivation_note='extracted $MFT')
    parent_actions = [e.action for e in _ledger().entries(item=parent)]
    assert parent_actions == ['register', 'derive']
    with pytest.raises(CustodyError) as exc:
        L.void(parent, actor=users['Administrator'], reason='oops')
    assert exc.value.status == 409
    db.session.rollback()
    with pytest.raises(CustodyError) as exc:
        L.void(child, actor=users['Administrator'], reason='  ')
    assert exc.value.status == 400
    db.session.rollback()
    L.void(child, actor=users['Administrator'], reason='duplicate')
    L.void(parent, actor=users['Administrator'], reason='duplicate')
    db.session.commit()


def test_parent_must_be_in_same_incident(app, db, users, make_incident, make_evidence):
    from app.models import EvidenceItem
    from app.services.custody_ledger import CustodyError
    inc, other = make_incident(), make_incident()
    foreign = make_evidence(other)
    item = EvidenceItem(incident_id=inc.id, evidence_type='other', title='x', parent_id=foreign.id,
                        created_by=users['Administrator'].id)
    with pytest.raises(CustodyError) as exc:
        _ledger().register_item(item, actor=users['Administrator'])
    assert exc.value.status == 404
    db.session.rollback()


def test_add_hash_validation_and_supersede(app, db, users, make_incident, make_evidence):
    from app.services.custody_ledger import CustodyError
    L = _ledger()
    admin = users['Administrator']
    item = make_evidence(make_incident())
    for alg, value in (('sha256', 'abc'), ('sha256', 'g' * 64), ('crc32', '0' * 8)):
        with pytest.raises(CustodyError) as exc:
            L.add_hash(item, actor=admin, algorithm=alg, value=value, source='tool_reported')
        assert exc.value.status == 400
        db.session.rollback()
    L.add_hash(item, actor=admin, algorithm='MD5', value='A' * 32, source='tool_reported')
    db.session.commit()
    assert item.weak_hashes_only is True
    with pytest.raises(CustodyError):
        L.add_hash(item, actor=admin, algorithm='md5', value='b' * 32, source='tool_reported')
    db.session.rollback()
    L.add_hash(item, actor=admin, algorithm='md5', value='b' * 32, source='computed_in_lab',
               supersedes='a' * 32, reason='typo in the lab sheet')
    L.add_hash(item, actor=admin, algorithm='sha256', value='c' * 64, source='tool_reported')
    db.session.commit()
    hashes = item.acquisition_hashes
    assert [h['value'] for h in hashes] == ['a' * 32, 'b' * 32, 'c' * 64]
    assert hashes[0]['superseded'] is True and item.weak_hashes_only is False
    assert L.verify(item=item)['status'] == 'intact'


# ── Chain integrity ─────────────────────────────────────────────────────────

def test_item_and_incident_chains_verify_intact(app, db, users, make_incident, make_evidence, make_artifact):
    L = _ledger()
    inc = make_incident()
    item = make_evidence(inc)
    art = make_artifact(inc)
    L.record_verification(item, actor=users['Administrator'], algorithm='sha256', expected='a' * 64,
                          observed='A' * 64, tool='FTK Imager 4.7')
    db.session.commit()
    assert item.last_verification_result == 'match'

    iv = L.verify(item=item)
    assert iv['status'] == 'intact' and iv['item_chain']['length'] == 2 and iv['item_chain']['genesis'] == 'genesis'
    assert iv['signatures']['valid'] == 2 and iv['projection_drift'] == []
    full = L.verify(incident=inc)
    assert full['status'] == 'intact' and full['incident_chain']['length'] == 4
    assert set(full['items']) == {str(item.id), str(art.evidence_item_id)}
    heads = L.heads(inc.id)
    assert heads['incident']['seq'] == 4 and heads['incident']['hash'] == full['incident_chain']['head_hash']
    # entry_hash links: each entry's prev is its predecessor's entry_hash in both chains.
    rows = L.entries(incident_id=inc.id)
    for prev, cur in zip(rows, rows[1:]):
        assert cur.incident_prev_hash == prev.entry_hash


def test_unchained_rows_are_refused(app, db, users, make_incident, make_artifact):
    from app.models import ChainOfCustody
    from app.models.artifact import CustodyLedgerError
    art = make_artifact(make_incident())
    db.session.add(ChainOfCustody(artifact_id=art.id, evidence_item_id=art.evidence_item_id,
                                  incident_id=art.incident_id, action='view',
                                  performed_by=users['Administrator'].id))
    with pytest.raises(CustodyLedgerError):
        db.session.flush()
    db.session.rollback()


def test_floats_in_extra_data_are_refused(app, db, users, make_incident, make_evidence):
    item = make_evidence(make_incident())
    with pytest.raises(ValueError):
        _ledger().append(item, 'view', performed_by=users['Administrator'], extra={'ratio': 0.5})
    db.session.rollback()


@pytest.mark.parametrize('sql', [
    "UPDATE chain_of_custody SET purpose='x' WHERE incident_id=:i",
    'DELETE FROM chain_of_custody WHERE incident_id=:i',
    'TRUNCATE chain_of_custody',
    "UPDATE custody_anchors SET error='x' WHERE incident_id=:i",
    'DELETE FROM custody_anchors WHERE incident_id=:i',
])
def test_append_only_triggers(app, db, users, make_incident, make_evidence, sql):
    from app.models import CustodyAnchor
    inc = make_incident()
    make_evidence(inc)
    head = _ledger().heads(inc.id)['incident']
    db.session.add(CustodyAnchor(incident_id=inc.id, incident_seq=head['seq'], head_hash=head['hash'],
                                 anchor_type='export_manifest', status='granted',
                                 created_by=users['Administrator'].id))
    db.session.commit()
    with pytest.raises(DBAPIError) as exc:
        db.session.execute(text(sql), {'i': inc.id})
        db.session.flush()
    assert getattr(exc.value.orig, 'pgcode', None) == '42501'
    db.session.rollback()


def test_purge_guc_only_unlocks_its_own_incident(app, db, make_incident, make_evidence):
    a, b = make_incident(), make_incident()
    make_evidence(a)
    make_evidence(b)
    db.session.execute(text("SELECT set_config('sheetstorm.custody_purge', :i, true)"), {'i': str(a.id)})
    with pytest.raises(DBAPIError):
        db.session.execute(text('DELETE FROM chain_of_custody WHERE incident_id=:i'), {'i': b.id})
    db.session.rollback()
    db.session.execute(text("SELECT set_config('sheetstorm.custody_purge', :i, true)"), {'i': str(a.id)})
    with pytest.raises(DBAPIError):  # UPDATE is never allowed, even under the GUC
        db.session.execute(text("UPDATE chain_of_custody SET purpose='x' WHERE incident_id=:i"), {'i': a.id})
    db.session.rollback()


def test_artifact_row_delete_no_longer_cascades_custody(app, db, make_incident, make_artifact):
    art = make_artifact(make_incident())
    with pytest.raises(DBAPIError) as exc:
        db.session.execute(text('DELETE FROM artifacts WHERE id=:i'), {'i': art.id})
    assert exc.value.orig.pgcode == '23503'  # NO ACTION FK from the ledger
    db.session.rollback()


def test_tamper_edit_payload_column(app, db, users, make_incident, make_artifact, ledger_tamper):
    L = _ledger()
    art = make_artifact(make_incident())
    target = L.entries(item=art.evidence_item)[-1]
    with ledger_tamper() as s:
        s.execute(text("UPDATE chain_of_custody SET purpose='rewritten' WHERE id=:i"), {'i': target.id})
    db.session.expire_all()
    res = L.verify(item=art.evidence_item)
    assert 'entry_hash_mismatch' in _reasons(res)
    assert res['signature_status_by_id'][str(target.id)] == 'invalid'
    assert res['status'] == 'compromised'


def test_tamper_recomputed_hash_still_caught_by_signature(app, db, users, make_incident, make_artifact,
                                                          ledger_tamper):
    """An attacker without the HMAC key who rewrites a row AND recomputes its
    hash (and the next links) still fails the signature check."""
    from app.models import ChainOfCustody
    from app.utils import verify_custody as vc
    L = _ledger()
    art = make_artifact(make_incident())
    item = art.evidence_item
    rows = L.entries(item=item)
    last = rows[-1]
    forged = {c.name: getattr(last, c.name) for c in ChainOfCustody.__table__.columns}
    forged['purpose'] = 'forged'
    new_hash = vc.compute_entry_hash(forged)
    with ledger_tamper() as s:
        s.execute(text("UPDATE chain_of_custody SET purpose='forged', entry_hash=:h WHERE id=:i"),
                  {'h': new_hash, 'i': last.id})
    db.session.expire_all()
    res = L.verify(item=item)
    assert 'entry_hash_mismatch' not in _reasons(res)
    assert res['signature_status_by_id'][str(last.id)] == 'invalid' and res['status'] == 'compromised'


def test_tamper_delete_middle_row(app, db, users, make_incident, make_evidence, ledger_tamper):
    L = _ledger()
    inc = make_incident()
    item = make_evidence(inc)
    for _ in range(3):
        L.append(item, 'view', performed_by=users['Administrator'])
    db.session.commit()
    middle = L.entries(item=item)[2]
    with ledger_tamper() as s:
        s.execute(text('DELETE FROM chain_of_custody WHERE id=:i'), {'i': middle.id})
    db.session.expire_all()
    res = L.verify(item=item)
    assert {'seq_gap', 'prev_hash_mismatch'} <= _reasons(res) and res['status'] == 'broken'
    assert {'seq_gap', 'prev_hash_mismatch'} <= _reasons(L.verify(incident=inc))


def test_tamper_swap_seq(app, db, users, make_incident, make_evidence, ledger_tamper):
    L = _ledger()
    item = make_evidence(make_incident())
    L.append(item, 'view', performed_by=users['Administrator'])
    L.append(item, 'export', performed_by=users['Administrator'])
    db.session.commit()
    rows = L.entries(item=item)
    a, b = rows[1], rows[2]
    with ledger_tamper() as s:
        s.execute(text('ALTER TABLE chain_of_custody DROP CONSTRAINT uq_custody_item_seq'))
        s.execute(text('UPDATE chain_of_custody SET seq = CASE WHEN id=:a THEN :sb ELSE :sa END '
                       'WHERE id IN (:a, :b)'), {'a': a.id, 'b': b.id, 'sa': a.seq, 'sb': b.seq})
        s.execute(text('ALTER TABLE chain_of_custody ADD CONSTRAINT uq_custody_item_seq '
                       'UNIQUE (evidence_item_id, seq)'))
    db.session.expire_all()
    res = L.verify(item=item)
    assert res['status'] in ('broken', 'compromised') and 'prev_hash_mismatch' in _reasons(res)


def test_tamper_delete_whole_item_chain_detected_by_incident_chain(app, db, users, make_incident,
                                                                   make_evidence, ledger_tamper):
    L = _ledger()
    inc = make_incident()
    keep = make_evidence(inc)
    gone = make_evidence(inc)
    L.append(keep, 'view', performed_by=users['Administrator'])
    db.session.commit()
    with ledger_tamper() as s:
        s.execute(text('DELETE FROM chain_of_custody WHERE evidence_item_id=:i'), {'i': gone.id})
    db.session.expire_all()
    assert L.verify(item=keep)['status'] == 'intact'
    res = L.verify(incident=inc)
    assert res['status'] == 'broken'
    assert any(b['chain'] == 'incident' and b['reason'] in ('seq_gap', 'prev_hash_mismatch') for b in res['breaks'])


def test_legacy_seal_detects_deleted_legacy_rows(app, db, users, make_incident, make_evidence, make_artifact,
                                                 insert_legacy_custody, ledger_tamper):
    L = _ledger()
    inc = make_incident()
    item = make_evidence(inc, register=False)
    art = make_artifact(inc, item=item, upload_entry=False)
    t0 = datetime.now(timezone.utc) - timedelta(days=30)
    legacy_ids = [insert_legacy_custody(art, action=act, created_at=t0 + timedelta(minutes=i))
                  for i, act in enumerate(('upload', 'view', 'download'))]
    first = L.append(item, 'view', performed_by=users['Administrator'])
    db.session.commit()
    assert first.extra_data['legacy_seal']['count'] == 3
    assert first.extra_data['incident_legacy_seal']['count'] == 3
    res = L.verify(item=item)
    assert res['status'] == 'intact_with_unsigned_legacy' and res['legacy'] == {'count': 3, 'sealed': True}
    assert res['item_chain']['genesis'] == 'legacy_seal' and res['notes']

    with ledger_tamper() as s:
        s.execute(text('DELETE FROM chain_of_custody WHERE id=:i'), {'i': legacy_ids[1]})
    db.session.expire_all()
    res = L.verify(item=item)
    assert 'prev_hash_mismatch' in _reasons(res) and res['status'] == 'broken'


def test_key_rotation_is_key_mismatch_not_broken(app, db, users, make_incident, make_artifact, monkeypatch):
    L = _ledger()
    art = make_artifact(make_incident())
    monkeypatch.setitem(app.config, 'CUSTODY_SIGNING_KEY', 'rotated-key')
    res = L.verify(item=art.evidence_item)
    assert res['status'] == 'unverifiable' and res['breaks'] == []
    assert res['signatures']['key_mismatch'] == 2


def test_projection_drift_is_reported(app, db, users, make_incident, make_evidence):
    L = _ledger()
    item = make_evidence(make_incident())
    db.session.execute(text("UPDATE evidence_items SET custody_state='disposed' WHERE id=:i"), {'i': item.id})
    db.session.commit()
    db.session.expire_all()
    drift = L.verify(item=item)['projection_drift']
    assert drift == [{'field': 'custody_state', 'item_value': 'disposed', 'ledger_value': 'in_storage'}]


def test_concurrent_appends_keep_chains_intact(app, db, users, make_incident, make_evidence):
    from app.models import EvidenceItem, User
    L = _ledger()
    inc = make_incident()
    items = [make_evidence(inc) for _ in range(3)]
    item_ids = [i.id for i in items]
    admin_id = users['Administrator'].id
    errors = []
    barrier = threading.Barrier(20)

    def worker(n):
        try:
            barrier.wait(timeout=30)
            with app.app_context():
                from app import db as tdb
                item = tdb.session.get(EvidenceItem, item_ids[n % 3])
                actor = tdb.session.get(User, admin_id)
                L.append(item, 'view', performed_by=actor, extra={'n': n})
                tdb.session.commit()
                tdb.session.remove()
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors
    db.session.expire_all()
    res = L.verify(incident=inc)
    assert res['status'] == 'intact', res['breaks']
    assert res['incident_chain']['length'] == 23
    seqs = sorted(r.incident_seq for r in L.entries(incident_id=inc.id))
    assert seqs == list(range(1, 24))


# ── Custody state machine ───────────────────────────────────────────────────

@pytest.fixture
def party(app, db, users, org_a):
    from app.models import CustodyParty
    p = CustodyParty(organization_id=org_a.id, name='Jane Counsel', organization_name='Law LLP', role='counsel',
                     email='jane@law.test', created_by=users['Administrator'].id)
    db.session.add(p)
    db.session.commit()
    return p


def test_custody_workflow_and_party_snapshot(app, db, users, make_incident, make_evidence, party):
    L = _ledger()
    admin = users['Administrator']
    inc = make_incident()
    item = make_evidence(inc, storage_location='Lab safe B/2')
    out = L.check_out(item, actor=admin, purpose='imaging', to_user=users['Analyst'], transfer_method='internal')
    db.session.commit()
    assert item.custody_state == 'checked_out' and item.current_holder_user_id == users['Analyst'].id
    assert out.extra_data['state_after']['holder']['type'] == 'user'
    L.check_in(item, actor=admin, storage_location='Lab safe B/3', seal_intact=True, seal_number='S-2')
    db.session.commit()
    assert item.custody_state == 'in_storage' and item.storage_location == 'Lab safe B/3'

    xfer = L.transfer(item, actor=admin, reason='expert review', transfer_method='courier', to_party=party,
                      extra={'tracking_number': 'TRACK-1'})
    db.session.commit()
    assert item.custody_state == 'transferred' and item.current_holder_party_id == party.id
    assert xfer.extra_data['party']['name'] == 'Jane Counsel' and xfer.external_party_id == party.id

    party.name = 'Renamed Later'
    db.session.commit()
    ack = L.acknowledge(item, xfer, actor=admin, typed_name='Jane Counsel', statement='received sealed')
    db.session.commit()
    assert ack.extra_data['acknowledges'] == str(xfer.id)
    db.session.expire_all()
    assert L.entries(item=item)[3].extra_data['party']['name'] == 'Jane Counsel'
    assert L.verify(item=item)['status'] == 'intact'
    assert L.verify(incident=inc)['status'] == 'intact'


@pytest.mark.parametrize('scenario', ['checkin_in_storage', 'transfer_after_dispose', 'double_ack',
                                      'checkout_twice', 'ack_wrong_entry', 'transfer_no_reason'])
def test_disallowed_transitions(app, db, users, make_incident, make_evidence, party, scenario):
    from app.services.custody_ledger import CustodyError
    L = _ledger()
    admin = users['Administrator']
    item = make_evidence(make_incident())
    with pytest.raises(CustodyError) as exc:
        if scenario == 'checkin_in_storage':
            L.check_in(item, actor=admin, storage_location='safe', seal_intact=True)
        elif scenario == 'transfer_after_dispose':
            L.dispose(item, actor=admin, method='destroyed', reason='retention', witness_name='W')
            db.session.commit()
            L.transfer(item, actor=admin, reason='x', transfer_method='courier', to_party=party)
        elif scenario == 'double_ack':
            x = L.transfer(item, actor=admin, reason='x', transfer_method='courier', to_party=party)
            L.acknowledge(item, x, actor=admin, typed_name='J')
            db.session.commit()
            L.acknowledge(item, x, actor=admin, typed_name='J')
        elif scenario == 'checkout_twice':
            L.check_out(item, actor=admin, purpose='p', to_party=party)
            L.check_out(item, actor=admin, purpose='p', to_party=party)
        elif scenario == 'ack_wrong_entry':
            reg = L.entries(item=item)[0]
            L.acknowledge(item, reg, actor=admin, typed_name='J')
        elif scenario == 'transfer_no_reason':
            L.transfer(item, actor=admin, reason='', transfer_method='courier', to_party=party)
    assert exc.value.status in (400, 404, 409)
    db.session.rollback()


def test_receipt_acknowledgment_rules(app, db, users, make_incident, make_evidence, make_artifact, party):
    from app.services.custody_ledger import CustodyError
    L = _ledger()
    admin = users['Administrator']
    inc, other = make_incident(), make_incident()
    item = make_evidence(inc)
    x = L.transfer(item, actor=admin, reason='lab', transfer_method='courier', to_party=party)
    db.session.commit()
    not_receipt = make_artifact(inc, item=item)
    foreign_receipt = make_artifact(other, purpose='custody_receipt')
    for bad in (not_receipt, foreign_receipt):
        with pytest.raises(CustodyError):
            L.acknowledge(item, x, actor=admin, typed_name='J', receipt_artifact=bad)
        db.session.rollback()
    receipt = make_artifact(inc, item=item, purpose='custody_receipt', sha256='f' * 64)
    ack = L.acknowledge(item, x, actor=admin, typed_name='J', receipt_artifact=receipt)
    db.session.commit()
    assert ack.extra_data['receipt']['sha256'] == 'f' * 64 and ack.artifact_id == receipt.id


# ── Artifact routes: one-transaction upload, tombstone, filters, aliases ────

def _upload(client, inc, data=None, content=b'evidence-bytes'):
    form = {'file': (io.BytesIO(content), 'disk.raw')}
    form.update(data or {})
    return client.post(f'/api/v1/incidents/{inc.id}/artifacts', data=form, content_type='multipart/form-data')


@pytest.fixture
def fake_storage(monkeypatch):
    from app.services.storage_service import storage_service
    stored, deleted = {}, []

    def store(file_obj, path, content_type=None):
        file_obj.seek(0)
        stored[path] = file_obj.read()
        return True, 'local'

    def retrieve(path, storage_type='local'):
        return io.BytesIO(stored[path]) if path in stored else None

    def delete(path, storage_type='local'):
        deleted.append(path)
        stored.pop(path, None)
        return True
    monkeypatch.setattr(storage_service, 'store_file', store)
    monkeypatch.setattr(storage_service, 'retrieve_file', retrieve)
    monkeypatch.setattr(storage_service, 'delete_file', delete)
    return {'stored': stored, 'deleted': deleted}


def test_upload_creates_item_register_and_upload_in_one_transaction(app, db, users, auth, make_incident,
                                                                    fake_storage):
    from app.models import Artifact, EvidenceItem
    inc = make_incident()
    resp = _upload(auth(users['Administrator']), inc, {'title': 'Memory capture', 'evidence_type': 'memory_capture',
                                                      'acquisition_tool': 'winpmem'})
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    item = db.session.get(EvidenceItem, uuid.UUID(body['evidence_item']['id']))
    assert item.title == 'Memory capture' and item.evidence_type == 'memory_capture'
    assert item.evidence_number == 'EV-0001' and item.acquisition_tool == 'winpmem'
    assert {h['algorithm'] for h in item.acquisition_hashes} == {'md5', 'sha256', 'sha512'}
    assert [e.action for e in _ledger().entries(item=item)] == ['register', 'upload']
    art = db.session.get(Artifact, uuid.UUID(body['id']))
    assert art.evidence_item_id == item.id and art.purpose == 'evidence'
    assert _ledger().verify(item=item)['status'] == 'intact'


def test_upload_failures_leave_no_orphan_item(app, db, users, auth, make_incident, fake_storage, monkeypatch):
    from app.models import Artifact, EvidenceItem
    from app.services.chain_of_custody_service import ChainOfCustodyService
    from app.services.storage_service import storage_service
    inc = make_incident()
    client = auth(users['Administrator'])
    monkeypatch.setattr(storage_service, 'store_file', lambda *a, **k: (False, 'local'))
    assert _upload(client, inc).status_code == 500
    monkeypatch.undo()

    def boom(*a, **k):
        raise RuntimeError('ledger down')
    stored = {}
    monkeypatch.setattr(storage_service, 'store_file',
                        lambda f, p, c=None: (stored.setdefault(p, True), (True, 'local'))[1])
    deleted = []
    monkeypatch.setattr(storage_service, 'delete_file', lambda p, t='local': deleted.append(p) or True)
    monkeypatch.setattr(ChainOfCustodyService, 'log_upload', staticmethod(boom))
    assert _upload(client, inc).status_code == 500
    db.session.expire_all()
    assert EvidenceItem.query.filter_by(incident_id=inc.id).count() == 0
    assert Artifact.query.filter_by(incident_id=inc.id).count() == 0
    assert deleted == list(stored)  # the stored bytes of the failed upload were removed


def test_upload_to_existing_item_and_receipt_rules(app, db, users, auth, make_incident, make_evidence,
                                                   fake_storage):
    inc, other = make_incident(), make_incident()
    item = make_evidence(inc)
    client = auth(users['Administrator'])
    r = _upload(client, inc, {'evidence_item_id': str(item.id)})
    assert r.status_code == 201 and r.get_json()['evidence_item']['id'] == str(item.id)
    assert _upload(client, inc, {'purpose': 'custody_receipt'}).status_code == 400
    assert _upload(client, inc, {'evidence_item_id': str(make_evidence(other).id)}).status_code == 404
    assert _upload(client, inc, {'evidence_item_id': 'nope'}).status_code == 400
    assert _upload(client, inc, {'evidence_type': 'spaceship'}).status_code == 400
    r = _upload(client, inc, {'evidence_item_id': str(item.id), 'purpose': 'custody_receipt'})
    assert r.status_code == 201 and r.get_json()['purpose'] == 'custody_receipt'
    actions = [e.action for e in _ledger().entries(item=item)]
    assert actions == ['register', 'upload', 'upload']

    listed = client.get(f'/api/v1/incidents/{inc.id}/artifacts').get_json()
    assert [a['purpose'] for a in listed['items']] == ['evidence']
    receipts = client.get(f'/api/v1/incidents/{inc.id}/artifacts?purpose=custody_receipt').get_json()
    assert len(receipts['items']) == 1


def test_delete_is_a_tombstone(app, db, users, auth, make_incident, fake_storage):
    from app.models import Artifact
    inc = make_incident()
    client = auth(users['Administrator'])
    body = _upload(client, inc).get_json()
    aid = body['id']
    stats_before = client.get('/api/v1/storage/stats').get_json()['total_artifacts']
    resp = client.delete(f'/api/v1/incidents/{inc.id}/artifacts/{aid}', json={'reason': 'duplicate upload'})
    assert resp.status_code == 200
    db.session.expire_all()
    art = db.session.get(Artifact, uuid.UUID(aid))
    assert art.deleted_at and art.deletion_reason == 'duplicate upload' and art.content_purged is True
    assert art.sha256 == body['sha256'] and fake_storage['deleted'] == [art.storage_path]
    entries = _ledger().entries(item=art.evidence_item)
    assert entries[-1].action == 'delete' and entries[-1].extra_data['hashes']['sha256'] == body['sha256']
    assert client.get('/api/v1/storage/stats').get_json()['total_artifacts'] == stats_before - 1
    from app.models import Incident
    assert db.session.get(Incident, inc.id).to_dict(include_counts=True)['counts']['artifacts'] == 0

    assert client.get(f'/api/v1/incidents/{inc.id}/artifacts').get_json()['items'] == []
    listed = client.get(f'/api/v1/incidents/{inc.id}/artifacts?include_deleted=true').get_json()['items']
    assert [a['id'] for a in listed] == [aid]
    assert client.get(f'/api/v1/incidents/{inc.id}/artifacts/{aid}/download').status_code == 410
    assert client.post(f'/api/v1/incidents/{inc.id}/artifacts/{aid}/verify').status_code == 410
    assert client.delete(f'/api/v1/incidents/{inc.id}/artifacts/{aid}').status_code == 404
    custody = client.get(f'/api/v1/incidents/{inc.id}/artifacts/{aid}/custody').get_json()
    assert [e['action'] for e in custody['chain_of_custody']] == ['upload', 'delete']
    exp = client.get(f'/api/v1/incidents/{inc.id}/artifacts/{aid}/custody/export').get_json()
    assert exp['chain_integrity_status'] == 'intact' and exp['deleted_at']


def test_storage_stats_disk_usage_uses_local_artifact_dir(app, users, auth, monkeypatch, tmp_path, platform_admin):
    monkeypatch.setitem(app.config, 'LOCAL_ARTIFACT_DIR', str(tmp_path))
    stats = auth(platform_admin).get('/api/v1/storage/stats').get_json()
    assert stats['disk_usage']['path'] == str(tmp_path)


def test_storage_stats_hides_the_server_path_from_org_admins(app, users, auth, monkeypatch, tmp_path):
    monkeypatch.setitem(app.config, 'LOCAL_ARTIFACT_DIR', str(tmp_path))
    stats = auth(users['Administrator']).get('/api/v1/storage/stats').get_json()
    assert stats['disk_usage']['total_bytes'] > 0
    assert 'path' not in stats['disk_usage'] and str(tmp_path) not in str(stats)


def test_storage_stats_requires_integrations_read(app, users, auth):
    for role in ('Viewer', 'Analyst', 'Incident Responder'):
        assert auth(users[role]).get('/api/v1/storage/stats').status_code == 403, role
    assert auth(users['Administrator']).get('/api/v1/storage/stats').status_code == 200


def test_download_and_verify_append_entries(app, db, users, auth, make_incident, fake_storage):
    inc = make_incident()
    client = auth(users['Administrator'])
    aid = _upload(client, inc).get_json()['id']
    assert client.get(f'/api/v1/incidents/{inc.id}/artifacts/{aid}').status_code == 200
    assert client.get(f'/api/v1/incidents/{inc.id}/artifacts/{aid}/download').status_code == 200
    v = client.post(f'/api/v1/incidents/{inc.id}/artifacts/{aid}/verify').get_json()
    assert v['result'] == 'match'
    custody = client.get(f'/api/v1/incidents/{inc.id}/artifacts/{aid}/custody').get_json()['chain_of_custody']
    assert [e['action'] for e in custody] == ['upload', 'view', 'download', 'verify']
    assert all(e['signature_status'] == 'valid' for e in custody)


def test_viewer_cannot_reach_artifact_custody(app, users, auth, make_incident, make_artifact):
    inc = make_incident()
    art = make_artifact(inc)
    viewer = auth(users['Viewer'])
    assert viewer.get(f'/api/v1/incidents/{inc.id}/artifacts/{art.id}/custody').status_code in (403, 404)


# ── Offline verifier ────────────────────────────────────────────────────────

def _manifest(inc_id, L):
    from app.utils import verify_custody as vc
    entries = []
    for r in L.entries(incident_id=inc_id):
        if r.is_chained:
            e = vc.entry_payload_v3(r)
            e.update({'entry_hash': r.entry_hash, 'signature': r.signature, 'signature_key_id': r.signature_key_id,
                      'chain_version': r.chain_version})
        else:
            e = {'id': str(r.id), 'signature': r.signature, 'created_at': vc.canon_ts(r.created_at),
                 'evidence_item_id': str(r.evidence_item_id), 'chain_version': None}
        entries.append(e)
    heads = L.heads(inc_id)
    return {'scope': 'incident', 'incident_id': str(inc_id), 'entries': entries, 'heads': heads}


def test_offline_verifier_subprocess(app, db, users, make_incident, make_evidence, make_artifact,
                                     insert_legacy_custody, tmp_path):
    L = _ledger()
    inc = make_incident()
    item = make_evidence(inc, register=False)
    art = make_artifact(inc, item=item, upload_entry=False)
    insert_legacy_custody(art, action='upload', created_at=datetime.now(timezone.utc) - timedelta(days=3))
    L.append(item, 'view', performed_by=users['Administrator'])
    db.session.commit()
    make_evidence(inc)
    for name in ('hash_chain.py', 'verify_custody.py'):
        shutil.copy(os.path.join(UTILS_DIR, name), tmp_path / name)
    manifest = _manifest(inc.id, L)
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    (tmp_path / 'key').write_text(app.config['CUSTODY_SIGNING_KEY'])

    def run(*extra):
        return subprocess.run([sys.executable, 'verify_custody.py', 'manifest.json', '--json', *extra],
                              cwd=tmp_path, capture_output=True, text=True, timeout=60,
                              env={'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': ''})

    r = run('--hmac-key-file', 'key')
    assert r.returncode == 0, r.stdout + r.stderr
    report = json.loads(r.stdout)
    assert report['status'] == 'intact_with_unsigned_legacy' and report['signatures']['valid'] == 2
    assert report['incident_chain']['length'] == 2

    manifest['entries'][1]['purpose'] = 'altered'
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    assert run().returncode == 1
    (tmp_path / 'manifest.json').write_text('{not json')
    assert run().returncode == 2


def test_verify_custody_is_stdlib_only():
    tree = ast.parse(open(os.path.join(UTILS_DIR, 'verify_custody.py'), encoding='utf-8').read())
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or '']
        for name in names:
            top = name.split('.')[0]
            assert top in sys.stdlib_module_names or name in ('app.utils.hash_chain', 'hash_chain'), name


# ── Registrations ───────────────────────────────────────────────────────────

def test_evidence_item_ref_type_and_realtime_entity(app, db, users, make_incident, make_evidence):
    from app.services import realtime
    from app.services.evidence_refs import EvidenceRefsError, resolve_refs, validate_refs
    inc, other = make_incident(), make_incident()
    item = make_evidence(inc, title='Phone')
    refs = [{'evidence_type': 'evidence_item', 'evidence_id': str(item.id)}]
    assert validate_refs(inc.id, refs) == refs
    assert resolve_refs(inc.id, refs)[0]['label'] == 'EV-0001 Phone'
    with pytest.raises(EvidenceRefsError):
        validate_refs(other.id, refs)
    spec = realtime.ENTITY_SCOPES['evidence_item']
    assert (spec.scope, spec.read_perm) == ('artifacts', 'artifacts:read') and spec.serializer is not None
    entry = _ledger().entries(item=item)[0]
    data = realtime.ENTITY_SCOPES['custody_entry'].serializer(entry)
    assert 'ip_address' not in data and 'signature' not in data and data['entry_hash'] == entry.entry_hash


def test_private_detail_keys_cover_custody_fields():
    from app.middleware.audit import public_activity_details
    details = {'acquisition_hashes': [1], 'observed_hash': 'x', 'expected_hash': 'y', 'entry_hash': 'z',
               'typed_name': 'J', 'email': 'e', 'phone': 'p', 'action': 'ok'}
    assert public_activity_details(details) == {'action': 'ok'}
