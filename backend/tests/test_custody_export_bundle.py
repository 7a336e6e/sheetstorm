"""W2-EVD-API: custody export bundles + the shipped offline verifier.

The bundle's ``verify_custody.py`` is run in a subprocess on the extracted
ZIP (no app on the path): exit 0 when intact, 1 after tampering with the
manifest, 2 on malformed input.
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UTILS_DIR = os.path.join(BACKEND_DIR, 'app', 'utils')
ITEM_BUNDLE_FILES = {'manifest.json', 'entries.csv', 'chain_of_custody.pdf', 'verify_custody.py', 'hash_chain.py',
                     'README.txt', 'SHA256SUMS'}


def _url(inc, path=''):
    return f'/api/v1/incidents/{inc.id}/evidence{path}'


def _extract(resp, dest):
    assert resp.status_code == 200, resp.get_data(as_text=True)[:500]
    assert resp.mimetype == 'application/zip'
    zf = zipfile.ZipFile(io.BytesIO(resp.get_data()))
    for name in zf.namelist():
        assert '/' not in name and not name.startswith('.'), name
    zf.extractall(dest)
    return set(zf.namelist())


def _check_sums(dest, names):
    lines = (dest / 'SHA256SUMS').read_text().splitlines()
    sums = dict(reversed(line.split('  ', 1)) for line in lines)
    assert set(sums) == names - {'SHA256SUMS'}
    for name, digest in sums.items():
        assert hashlib.sha256((dest / name).read_bytes()).hexdigest() == digest, name


def _run(dest, *extra):
    return subprocess.run([sys.executable, 'verify_custody.py', 'manifest.json', '--json', *extra],
                          cwd=dest, capture_output=True, text=True, timeout=60,
                          env={'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': ''})


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


def _register(client, inc, **fields):
    body = {'title': 'Laptop SSD', 'evidence_type': 'disk_image'}
    body.update(fields)
    resp = client.post(_url(inc), json=body)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_item_bundle_verifies_offline_and_detects_tampering(app, users, admin, make_incident, tmp_path):
    inc = make_incident()
    item = _register(admin, inc, acquisition_hashes=[{'algorithm': 'sha256', 'value': 'a' * 64}])
    iurl = _url(inc, f"/{item['id']}")
    admin.post(iurl + '/custody/check-out', json={'to_user_id': str(users['Analyst'].id), 'purpose': 'imaging'})
    admin.post(iurl + '/custody/check-in', json={'storage_location': 'Safe 2', 'seal_intact': True})
    _register(admin, inc, title='Unrelated')  # another item: not in this item's bundle

    names = _extract(admin.get(iurl + '/custody/export?format=bundle'), tmp_path)
    assert names == ITEM_BUNDLE_FILES
    _check_sums(tmp_path, names)
    for name in ('verify_custody.py', 'hash_chain.py'):
        with open(os.path.join(UTILS_DIR, name), 'rb') as fh:
            assert (tmp_path / name).read_bytes() == fh.read(), name
    assert (tmp_path / 'chain_of_custody.pdf').read_bytes().startswith(b'%PDF')
    assert 'python3 verify_custody.py manifest.json' in (tmp_path / 'README.txt').read_text()

    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    assert manifest['scope'] == 'item' and manifest['heads']['incident'] is None
    assert [e['action'] for e in manifest['entries']] == ['register', 'check_out', 'check_in', 'export']
    assert {e['evidence_item_id'] for e in manifest['entries']} == {item['id']}
    assert manifest['heads']['items'][item['id']]['seq'] == 4
    assert 'CUSTODY_SIGNING_KEY' not in (tmp_path / 'manifest.json').read_text()
    assert app.config['CUSTODY_SIGNING_KEY'] not in (tmp_path / 'manifest.json').read_text()

    (tmp_path / 'key').write_text(app.config['CUSTODY_SIGNING_KEY'])
    r = _run(tmp_path, '--hmac-key-file', 'key')
    assert r.returncode == 0, r.stdout + r.stderr
    report = json.loads(r.stdout)
    assert report['status'] == 'intact' and report['signatures'] == {'valid': 4}
    assert report['incident_chain'] is None
    plain = subprocess.run([sys.executable, 'verify_custody.py', 'manifest.json'], cwd=tmp_path,
                           capture_output=True, text=True, timeout=60,
                           env={'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': ''})
    assert plain.returncode == 0 and 'incident chain: not included' in plain.stdout

    # A different key is reported as a key mismatch (rotation), never as valid.
    (tmp_path / 'wrong').write_text('not-the-key')
    wrong = json.loads(_run(tmp_path, '--hmac-key-file', 'wrong').stdout)
    assert wrong['status'] == 'unverifiable' and wrong['signatures'] == {'key_mismatch': 4}

    tampered = json.loads(json.dumps(manifest))
    tampered['entries'][1]['purpose'] = 'something else'
    (tmp_path / 'manifest.json').write_text(json.dumps(tampered))
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert 'entry_hash_mismatch' in {b['reason'] for b in json.loads(r.stdout)['breaks']}

    dropped = json.loads(json.dumps(manifest))
    del dropped['entries'][2]
    (tmp_path / 'manifest.json').write_text(json.dumps(dropped))
    assert _run(tmp_path).returncode == 1

    (tmp_path / 'manifest.json').write_text('{"entries": 5}')
    assert _run(tmp_path).returncode == 2


def test_incident_bundle_with_legacy_rows_and_export_anchor(app, db, users, admin, make_incident, make_evidence,
                                                            make_artifact, insert_legacy_custody, tmp_path):
    from app.models import CustodyAnchor
    from app.services.custody_ledger import CustodyLedger
    inc = make_incident()
    legacy_item = make_evidence(inc, register=False)
    art = make_artifact(inc, item=legacy_item, upload_entry=False)
    insert_legacy_custody(art, action='upload', created_at=datetime.now(timezone.utc) - timedelta(days=30))
    CustodyLedger.append(legacy_item, 'view', performed_by=users['Administrator'])
    db.session.commit()
    second = _register(admin, inc, title='Phone', evidence_type='mobile_device')
    admin.post(_url(inc, f"/{second['id']}/custody/transfer"),
               json={'new_party': {'name': 'Det. Smith', 'role': 'law_enforcement'}, 'reason': 'warrant',
                     'transfer_method': 'hand_delivery'})

    names = _extract(admin.get(_url(inc, '/export?format=bundle')), tmp_path)
    assert names == ITEM_BUNDLE_FILES | {'register.csv'}
    _check_sums(tmp_path, names)
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    assert manifest['scope'] == 'incident' and len(manifest['items']) == 2
    assert sum(1 for e in manifest['entries'] if e['chain_version'] is None) == 1
    head = manifest['heads']['incident']
    anchor = CustodyAnchor.query.filter_by(incident_id=inc.id, anchor_type='export_manifest').one()
    assert (anchor.incident_seq, anchor.head_hash, anchor.status) == (head['seq'], head['hash'], 'granted')
    assert [a['head_hash'] for a in manifest['anchors']] == [head['hash']]
    register = (tmp_path / 'register.csv').read_text()
    assert 'EV-0001' in register and 'EV-0002' in register and 'Det. Smith' in register

    (tmp_path / 'key').write_text(app.config['CUSTODY_SIGNING_KEY'])
    r = _run(tmp_path, '--hmac-key-file', 'key')
    assert r.returncode == 0, r.stdout + r.stderr
    report = json.loads(r.stdout)
    assert report['status'] == 'intact_with_unsigned_legacy'
    assert report['incident_chain']['length'] == head['seq'] and len(report['items']) == 2

    # Removing one item's whole chain is caught by the incident chain.
    pruned = dict(manifest, entries=[e for e in manifest['entries'] if e['evidence_item_id'] != second['id']])
    (tmp_path / 'manifest.json').write_text(json.dumps(pruned))
    r = _run(tmp_path)
    assert r.returncode == 1 and json.loads(r.stdout)['incident_chain']['breaks']


def test_bundles_need_incidents_export(app, users, auth, make_incident, make_evidence):
    inc = make_incident()
    item = make_evidence(inc)
    analyst = auth(users['Analyst'])  # artifacts:read, no incidents:export
    assert analyst.get(_url(inc, f'/{item.id}/custody/export?format=bundle')).status_code == 403
    assert analyst.get(_url(inc, '/export?format=bundle')).status_code == 403
    responder = auth(users['Incident Responder'])
    assert responder.get(_url(inc, f'/{item.id}/custody/export?format=bundle')).status_code == 200


def test_export_formats_render(app, users, admin, make_incident):
    inc = make_incident()
    item = _register(admin, inc, serial_number='SN-1', acquisition_hashes=[{'algorithm': 'md5', 'value': 'b' * 32}])
    for fmt, mime in (('pdf', 'application/pdf'), ('form', 'application/pdf'), ('csv', 'text/csv')):
        resp = admin.get(_url(inc, f"/{item['id']}/custody/export?format={fmt}&blank_rows=0"))
        assert resp.status_code == 200 and resp.mimetype == mime, fmt
        assert 'attachment' in resp.headers['Content-Disposition']
    reg = admin.get(_url(inc, '/export?format=pdf'))
    assert reg.status_code == 200 and reg.get_data().startswith(b'%PDF')
    actions = [e['action'] for e in admin.get(_url(inc, f"/{item['id']}/custody")).get_json()['entries']]
    assert actions == ['register', 'export', 'export', 'export']
    assert uuid.UUID(item['id'])
