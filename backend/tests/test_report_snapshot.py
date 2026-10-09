"""W3-DFIR-C: immutable report snapshots (surface-dfir §3.10; C34).

A report is what was issued: stored once with its SHA-256, served byte-for-byte
(hash re-checked on every download), never regenerated in place, kept on soft
delete and removed only by the incident purge step.
"""
import hashlib
import os
from datetime import datetime, timezone

import pytest

API = '/api/v1'


@pytest.fixture
def store(app, tmp_path, monkeypatch):
    """Report files go to a throwaway directory."""
    monkeypatch.setitem(app.config, 'LOCAL_ARTIFACT_DIR', str(tmp_path))
    return tmp_path


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


def generate(client, inc, **body):
    return client.post(f'{API}/incidents/{inc.id}/reports/generate-pdf', json=body)


def stored_file(store, report):
    return store / report.storage_path


# ── generate ──────────────────────────────────────────────────────────────

def test_generate_stores_the_exact_bytes_and_sha(app, db, store, admin, make_incident):
    from app.models import Report
    inc = make_incident()
    resp = generate(admin, inc, report_type='full')
    assert resp.status_code == 200 and resp.data.startswith(b'%PDF')
    report = Report.query.filter_by(incident_id=inc.id).one()
    assert report.sha256 == hashlib.sha256(resp.data).hexdigest() == resp.headers['X-Report-SHA256']
    assert report.size_bytes == len(resp.data)
    assert report.storage_path == f'incidents/{inc.id}/reports/{report.id}.pdf'
    assert report.storage_type == 'local'
    assert stored_file(store, report).read_bytes() == resp.data
    assert resp.headers['X-Report-Id'] == str(report.id)


def test_generate_fails_closed_when_storage_fails(app, db, store, admin, make_incident, monkeypatch):
    from app.models import Report
    from app.services.storage_service import storage_service
    monkeypatch.setattr(storage_service, 'store_file', lambda *a, **k: (False, 'local'))
    inc = make_incident()
    resp = generate(admin, inc)
    assert resp.status_code == 500 and 'X-Report-SHA256' not in resp.headers
    db.session.expire_all()
    assert Report.query.filter_by(incident_id=inc.id).count() == 0, 'no non-snapshot record may exist'
    assert list(store.rglob('*.pdf')) == []


# ── download / immutability ──────────────────────────────────────────────

def test_download_returns_identical_bytes_after_data_changes(app, db, store, admin, users, make_incident):
    from app.models import Report, TimelineEvent
    inc = make_incident()
    issued = generate(admin, inc, report_type='full')
    report = Report.query.filter_by(incident_id=inc.id).one()
    # the incident changes after issuing: a re-render would differ
    db.session.add(TimelineEvent(incident_id=inc.id, timestamp=datetime.now(timezone.utc),
                                 activity='Added after the report was issued',
                                 created_by=users['Administrator'].id))
    inc.title = 'Renamed after issue'
    db.session.commit()
    url = f'{API}/incidents/{inc.id}/reports/{report.id}/download'
    first, second = admin.get(url), admin.get(url)
    assert first.status_code == 200 and first.mimetype == 'application/pdf'
    assert first.data == issued.data == second.data
    assert first.headers['X-Report-SHA256'] == report.sha256
    assert first.headers['X-Report-Snapshot'] == 'stored'
    assert Report.query.filter_by(incident_id=inc.id).count() == 1, 'download must not create a new report'


def test_tampered_file_is_409_and_a_security_event(app, db, store, admin, make_incident):
    from app.models import AuditLog, Report
    inc = make_incident()
    generate(admin, inc)
    report = Report.query.filter_by(incident_id=inc.id).one()
    path = stored_file(store, report)
    path.write_bytes(path.read_bytes() + b'\n%tampered')
    resp = admin.get(f'{API}/incidents/{inc.id}/reports/{report.id}/download')
    assert resp.status_code == 409
    body = resp.get_json()
    assert body['error'] == 'integrity_error' and body['expected_sha256'] == report.sha256
    assert b'tampered' not in resp.data
    db.session.expire_all()
    event = (AuditLog.query.filter_by(event_type='security_event', action='report_integrity_failure',
                                      resource_id=report.id).first())
    assert event is not None and event.details['expected_sha256'] == report.sha256
    assert event.details['actual_sha256'] != report.sha256


def test_missing_file_is_409(app, store, admin, make_incident):
    from app.models import Report
    inc = make_incident()
    generate(admin, inc)
    report = Report.query.filter_by(incident_id=inc.id).one()
    os.remove(stored_file(store, report))
    resp = admin.get(f'{API}/incidents/{inc.id}/reports/{report.id}/download')
    assert resp.status_code == 409 and resp.get_json()['error'] == 'integrity_error'


def test_legacy_report_is_rerendered_and_marked(app, db, store, admin, users, make_incident):
    from app.models import Report
    inc = make_incident()
    legacy = Report(incident_id=inc.id, title='Old report', report_type='executive', format='pdf',
                    sections=['summary'], generated_by=users['Administrator'].id)
    db.session.add(legacy)
    db.session.commit()
    resp = admin.get(f'{API}/incidents/{inc.id}/reports/{legacy.id}/download')
    assert resp.status_code == 200 and resp.data.startswith(b'%PDF')
    assert resp.headers['X-Report-Snapshot'] == 'legacy' and 'X-Report-SHA256' not in resp.headers
    assert legacy.to_dict()['is_snapshot'] is False


def test_render_error_does_not_leak_exception_text(app, db, store, admin, users, make_incident, monkeypatch):
    from app.api.v1.endpoints import reports
    from app.models import Report
    inc = make_incident()
    legacy = Report(incident_id=inc.id, title='Old', report_type='executive', format='pdf',
                    generated_by=users['Administrator'].id)
    db.session.add(legacy)
    db.session.commit()

    def boom(html):
        raise RuntimeError('secret-internal-path /srv/x')
    monkeypatch.setattr(reports, 'html_to_pdf', boom)
    resp = admin.get(f'{API}/incidents/{inc.id}/reports/{legacy.id}/download')
    assert resp.status_code == 500 and b'secret-internal-path' not in resp.data


# ── archive / list / serialization ───────────────────────────────────────

def test_archived_reports_are_hidden_but_the_file_is_kept(app, db, store, admin, make_incident):
    from app.models import Report
    inc = make_incident()
    generate(admin, inc)
    kept = generate(admin, inc)
    reports = Report.query.filter_by(incident_id=inc.id).order_by(Report.created_at).all()
    assert len(reports) == 2
    gone = reports[0]
    assert admin.delete(f'{API}/incidents/{inc.id}/reports/{gone.id}').status_code == 200
    listed = admin.get(f'{API}/incidents/{inc.id}/reports').get_json()['items']
    assert [r['id'] for r in listed] == [str(reports[1].id)]
    assert admin.get(f'{API}/incidents/{inc.id}/reports/{gone.id}/download').status_code == 404
    assert stored_file(store, gone).exists(), 'soft delete keeps the issued file (C34)'
    assert kept.status_code == 200


def test_to_dict_hides_storage_and_exposes_snapshot_fields(app, db, store, admin, make_incident):
    inc = make_incident()
    resp = generate(admin, inc)
    item = admin.get(f'{API}/incidents/{inc.id}/reports').get_json()['items'][0]
    assert 'storage_path' not in item and 'storage_type' not in item
    assert item['is_snapshot'] is True
    assert item['sha256'] == hashlib.sha256(resp.data).hexdigest() and item['size_bytes'] == len(resp.data)


def test_download_needs_reports_read(app, store, auth, admin, make_user, org_a, make_incident):
    from app.models import Report
    inc = make_incident()
    generate(admin, inc)
    report = Report.query.filter_by(incident_id=inc.id).one()
    url = f'{API}/incidents/{inc.id}/reports/{report.id}/download'
    no_reports = make_user(org_a, perms=['incidents:read', 'incidents:read_all'])
    with_reports = make_user(org_a, perms=['incidents:read', 'incidents:read_all', 'reports:read'])
    assert auth(no_reports).get(url).status_code == 403
    assert auth(with_reports).get(url).status_code == 200


# ── purge step ───────────────────────────────────────────────────────────

def test_purge_step_is_registered_pre_and_post_commit():
    from app.api.v1.endpoints import reports  # noqa: F401  (registers on import)
    from app.services import incident_purge
    assert 'report_files_collect' in incident_purge.registered_steps('pre')
    assert 'report_files' in incident_purge.registered_steps('post_commit')


def test_incident_purge_deletes_report_files_including_soft_deleted_ones(app, db, store, admin, users, make_incident):
    from app.models import Report
    from app.services import incident_purge
    inc = make_incident()
    generate(admin, inc)
    generate(admin, inc)
    reports = Report.query.filter_by(incident_id=inc.id).all()
    admin.delete(f'{API}/incidents/{inc.id}/reports/{reports[0].id}')
    paths = [stored_file(store, r) for r in reports]
    assert all(p.exists() for p in paths)
    other = make_incident()
    generate(admin, other)
    other_report = Report.query.filter_by(incident_id=other.id).one()

    incident_purge.purge_incident(db.session.get(type(inc), inc.id), users['Administrator'])

    assert not any(p.exists() for p in paths)
    assert stored_file(store, other_report).exists(), 'other incidents keep their files'
    assert Report.query.filter_by(incident_id=inc.id).count() == 0


def test_failed_purge_keeps_the_report_files(app, db, store, admin, users, make_incident, monkeypatch):
    from app.models import Report
    from app.services import incident_purge
    inc = make_incident()
    generate(admin, inc)
    report = Report.query.filter_by(incident_id=inc.id).one()
    path = stored_file(store, report)
    monkeypatch.setattr(db.session, 'delete', lambda obj: (_ for _ in ()).throw(RuntimeError('db down')))
    with pytest.raises(incident_purge.PurgeError):
        incident_purge.purge_incident(db.session.get(type(inc), inc.id), users['Administrator'])
    assert path.exists(), 'files are deleted only after the purge committed'
