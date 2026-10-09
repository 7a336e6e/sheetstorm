"""Item 4: chain-of-custody signatures — valid / unsigned_legacy / invalid /
key_mismatch (rotation), v1 rows, canonical payload, CSV formula escaping and
PDF export.

W1-EVD-CORE: entries are written through the v3 ledger (CustodyLedger);
legacy (pre-v3) rows are inserted with raw SQL; tampering runs with the
append-only triggers disabled (``ledger_tamper``)."""
import csv
import io

import pytest
from sqlalchemy import text


@pytest.fixture
def artifact(app, make_incident, make_artifact):
    return make_artifact(make_incident())


@pytest.fixture
def bare_artifact(app, make_incident, make_evidence, make_artifact):
    """An artifact whose item has no ledger entries yet (room for legacy rows)."""
    inc = make_incident()
    item = make_evidence(inc, register=False, evidence_type='digital_file')
    return make_artifact(inc, item=item, upload_entry=False)


def _log(app, artifact, user, purpose=None, ip='10.0.0.5'):
    from app import db
    from app.services.custody_ledger import CustodyLedger
    with app.test_request_context(environ_base={'REMOTE_ADDR': ip}, headers={'User-Agent': 'pytest-agent'}):
        e = CustodyLedger.append(artifact.evidence_item, 'download', performed_by=user, artifact=artifact,
                                 purpose=purpose, verification_result='match', extra={'k': 1})
        db.session.commit()
        return e


def _export(auth, users, artifact, fmt='json'):
    return auth(users['Administrator']).get(
        f'/api/v1/incidents/{artifact.incident_id}/artifacts/{artifact.id}/custody/export?format={fmt}')


def test_new_entry_is_signed_with_key_id(app, db, users, artifact):
    from app.models.artifact import custody_key_id
    e = _log(app, artifact, users['Administrator'])
    db.session.refresh(e)
    assert e.signature and e.signature_key_id == custody_key_id(app.config['CUSTODY_SIGNING_KEY'])
    assert e.id is not None and e.created_at is not None
    assert e.signature_status(app.config['CUSTODY_SIGNING_KEY']) == 'valid'


def test_export_valid(app, users, auth, artifact):
    _log(app, artifact, users['Administrator'])
    body = _export(auth, users, artifact).get_json()
    assert body['chain_integrity'] is True and body['chain_integrity_status'] == 'intact'
    assert {r['signature_status'] for r in body['custody_entries']} == {'valid'}
    assert [r['action'] for r in body['custody_entries']] == ['upload', 'download']
    assert body['chain']['item_chain']['length'] == 3  # register + upload + download
    assert body['chain']['breaks'] == []


def test_legacy_unsigned_rows_are_not_tampered(app, db, users, auth, bare_artifact, insert_legacy_custody):
    artifact = bare_artifact
    insert_legacy_custody(artifact, action='upload')
    _log(app, artifact, users['Administrator'])  # first chained entry seals the legacy row
    body = _export(auth, users, artifact).get_json()
    assert [r['signature_status'] for r in body['custody_entries']] == ['unsigned_legacy', 'valid']
    assert body['chain_integrity'] is True
    assert body['chain_integrity_status'] == 'intact_with_unsigned_legacy'
    assert body['chain']['legacy'] == {'count': 1, 'sealed': True}
    assert body['chain']['notes']
    html_like = _export(auth, users, artifact, 'csv').get_data(as_text=True)
    assert 'unsigned (pre-dates signing)' in html_like and 'TAMPERED' not in html_like


def test_stripping_a_v3_signature_is_tampering(app, db, users, auth, artifact, ledger_tamper):
    e = _log(app, artifact, users['Administrator'])
    with ledger_tamper() as s:
        s.execute(text('UPDATE chain_of_custody SET signature=NULL, signature_key_id=NULL WHERE id=:i'),
                  {'i': e.id})
    body = _export(auth, users, artifact).get_json()
    assert body['custody_entries'][-1]['signature_status'] == 'invalid'
    assert body['chain_integrity_status'] == 'compromised'


@pytest.mark.parametrize('column,value', [
    ('purpose', 'altered'),
    ('ip_address', '192.0.2.1'),
    ('user_agent', 'evil'),
    ('created_at', '2001-01-01T00:00:00Z'),
])
def test_tampering_is_detected(app, db, users, auth, artifact, ledger_tamper, column, value):
    e = _log(app, artifact, users['Administrator'], purpose='original')
    with ledger_tamper() as s:
        s.execute(text(f'UPDATE chain_of_custody SET {column}=:v WHERE id=:i'), {'v': value, 'i': e.id})
    body = _export(auth, users, artifact).get_json()
    by_id = {r['id']: r for r in body['custody_entries']}
    assert by_id[str(e.id)]['signature_status'] == 'invalid'
    assert body['chain_integrity'] is False
    assert 'entry_hash_mismatch' in {b['reason'] for b in body['chain']['breaks']}


def test_rotated_key_is_reported_as_key_mismatch(app, users, auth, artifact, monkeypatch):
    _log(app, artifact, users['Administrator'])
    monkeypatch.setitem(app.config, 'CUSTODY_SIGNING_KEY', 'a-brand-new-key')
    body = _export(auth, users, artifact).get_json()
    assert {r['signature_status'] for r in body['custody_entries']} == {'key_mismatch'}
    assert body['chain_integrity_status'] == 'unverifiable'
    assert body['chain']['breaks'] == []  # rotation is not a chain break


@pytest.mark.parametrize('version', ['v1', 'v2'])
def test_legacy_signed_rows_still_verify(app, db, users, auth, bare_artifact, insert_legacy_custody, version):
    from datetime import datetime, timezone
    from app.models import ChainOfCustody
    from app.models.artifact import custody_key_id
    artifact = bare_artifact
    admin = users['Administrator']
    ts = datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc)
    row = ChainOfCustody(id=__import__('uuid').uuid4(), artifact_id=artifact.id, action='download',
                         performed_by=admin.id, ip_address='10.0.0.5', user_agent='pytest-agent', purpose='p',
                         verification_result='match', extra_data={}, created_at=ts)
    if version == 'v1':
        sig, kid = ChainOfCustody._hmac(app.config['SECRET_KEY'], row._payload_v1()), None
    else:
        key = app.config['CUSTODY_SIGNING_KEY']
        sig, kid = ChainOfCustody._hmac(key, row._payload_v2()), custody_key_id(key)
    insert_legacy_custody(artifact, created_at=ts, signature=sig, signature_key_id=kid, purpose='p',
                          verification_result='match', id=row.id)
    body = _export(auth, users, artifact).get_json()
    assert body['custody_entries'][0]['signature_status'] == 'valid'
    assert body['chain_integrity_status'] == 'intact'


def test_signing_failure_is_logged(app, db, users, auth, artifact, monkeypatch, caplog):
    import app.models.artifact as art
    monkeypatch.setattr(art.ChainOfCustody, 'sign', lambda self, secret: (_ for _ in ()).throw(ValueError('boom')))
    e = _log(app, artifact, users['Administrator'])
    assert e.signature is None and e.entry_hash  # still chained, never blocks logging
    assert any('signing failed' in r.getMessage() for r in caplog.records)
    monkeypatch.undo()
    body = _export(auth, users, artifact).get_json()
    assert body['custody_entries'][-1]['signature_status'] == 'invalid'


def test_csv_export_escapes_formulas(app, users, auth, artifact):
    _log(app, artifact, users['Administrator'], purpose='=HYPERLINK("http://evil","x")')
    data = _export(auth, users, artifact, 'csv').get_data(as_text=True)
    rows = list(csv.reader(io.StringIO(data)))
    purpose_cells = [r[4] for r in rows[1:]]
    assert len(rows) == 3  # header + upload + download
    assert any(c.startswith("'=HYPERLINK") for c in purpose_cells)
    assert not any(c.startswith('=') for r in rows for c in r)


def test_pdf_export(app, users, auth, artifact):
    _log(app, artifact, users['Administrator'], purpose='<b>pdf</b>')
    resp = _export(auth, users, artifact, 'pdf')
    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf' and resp.data[:4] == b'%PDF'


def test_custody_chain_endpoint_reports_status(app, users, auth, artifact):
    _log(app, artifact, users['Administrator'])
    resp = auth(users['Administrator']).get(
        f'/api/v1/incidents/{artifact.incident_id}/artifacts/{artifact.id}/custody')
    body = resp.get_json()
    assert [e['signature_status'] for e in body['chain_of_custody']] == ['valid', 'valid']
    assert body['evidence_number'] == 'EV-0001'
