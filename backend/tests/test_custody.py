"""Item 4: chain-of-custody signatures — valid / unsigned_legacy / invalid /
key_mismatch (rotation), v1 rows, canonical payload, CSV formula escaping and
PDF export."""
import csv
import io

import pytest
from sqlalchemy import text


@pytest.fixture
def artifact(app, db, users, make_incident):
    from app.models import Artifact
    inc = make_incident()
    a = Artifact(incident_id=inc.id, filename='f.bin', original_filename='evidence.bin',
                 storage_path='x', storage_type='local', file_size=3, md5='0' * 32,
                 sha256='0' * 64, sha512='0' * 128, uploaded_by=users['Administrator'].id)
    db.session.add(a)
    db.session.commit()
    return a


def _log(app, artifact, user, purpose=None, ip='10.0.0.5'):
    from app.models import ChainOfCustody
    from app import db
    with app.test_request_context(environ_base={'REMOTE_ADDR': ip}, headers={'User-Agent': 'pytest-agent'}):
        e = ChainOfCustody(artifact_id=artifact.id, action='download', performed_by=user.id,
                           ip_address=ip, user_agent='pytest-agent', purpose=purpose,
                           verification_result='match', extra_data={'k': 1})
        db.session.add(e)
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


def test_legacy_unsigned_rows_are_not_tampered(app, db, users, auth, artifact):
    e = _log(app, artifact, users['Administrator'])
    db.session.execute(text('UPDATE chain_of_custody SET signature=NULL, signature_key_id=NULL WHERE id=:i'),
                       {'i': e.id})
    db.session.commit()
    body = _export(auth, users, artifact).get_json()
    assert body['custody_entries'][0]['signature_status'] == 'unsigned_legacy'
    assert body['chain_integrity'] is True
    assert body['chain_integrity_status'] == 'intact_with_unsigned_legacy'
    html_like = _export(auth, users, artifact, 'csv').get_data(as_text=True)
    assert 'unsigned (pre-dates signing)' in html_like and 'TAMPERED' not in html_like


@pytest.mark.parametrize('column,value', [
    ('purpose', 'altered'),
    ('ip_address', '192.0.2.1'),
    ('user_agent', 'evil'),
    ('created_at', '2001-01-01T00:00:00Z'),
])
def test_tampering_is_detected(app, db, users, auth, artifact, column, value):
    e = _log(app, artifact, users['Administrator'], purpose='original')
    db.session.execute(text(f'UPDATE chain_of_custody SET {column}=:v WHERE id=:i'), {'v': value, 'i': e.id})
    db.session.commit()
    body = _export(auth, users, artifact).get_json()
    assert body['custody_entries'][0]['signature_status'] == 'invalid'
    assert body['chain_integrity'] is False


def test_rotated_key_is_reported_as_key_mismatch(app, users, auth, artifact, monkeypatch):
    _log(app, artifact, users['Administrator'])
    monkeypatch.setitem(app.config, 'CUSTODY_SIGNING_KEY', 'a-brand-new-key')
    body = _export(auth, users, artifact).get_json()
    assert body['custody_entries'][0]['signature_status'] == 'key_mismatch'
    assert body['chain_integrity_status'] == 'unverifiable'


def test_v1_signed_rows_still_verify(app, db, users, auth, artifact):
    from app.models import ChainOfCustody
    e = _log(app, artifact, users['Administrator'])
    db.session.refresh(e)
    v1 = ChainOfCustody._hmac(app.config['SECRET_KEY'], e._payload_v1())
    db.session.execute(text('UPDATE chain_of_custody SET signature=:s, signature_key_id=NULL WHERE id=:i'),
                       {'s': v1, 'i': e.id})
    db.session.commit()
    body = _export(auth, users, artifact).get_json()
    assert body['custody_entries'][0]['signature_status'] == 'valid'


def test_signing_failure_is_logged(app, db, users, artifact, monkeypatch, caplog):
    import app.models.artifact as art
    monkeypatch.setattr(art.ChainOfCustody, 'sign', lambda self, secret: (_ for _ in ()).throw(ValueError('boom')))
    e = _log(app, artifact, users['Administrator'])
    assert e.signature is None
    assert any('signing failed' in r.getMessage() for r in caplog.records)


def test_csv_export_escapes_formulas(app, users, auth, artifact):
    _log(app, artifact, users['Administrator'], purpose='=HYPERLINK("http://evil","x")')
    data = _export(auth, users, artifact, 'csv').get_data(as_text=True)
    rows = list(csv.reader(io.StringIO(data)))
    purpose_cells = [r[4] for r in rows[1:]]
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
    assert resp.get_json()['chain_of_custody'][0]['signature_status'] == 'valid'
