"""An update that ends in a 4xx must leave the row untouched.

Handlers set fields and only then hit a validation error (e.g. an unknown
host_id); @audit_log's audit-row commit used to flush that half-applied
change. The decorator now rolls the session back on any error status."""
import uuid

import pytest

API = '/api/v1'


def _ok(resp, *codes):
    assert resp.status_code in (codes or (200, 201)), (resp.status_code, resp.get_json())
    return resp.get_json()


def _reload(db, model, oid):
    db.session.rollback()
    db.session.expire_all()
    return db.session.get(model, oid)


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


CASES = [
    # (name, create path, create body, model name, update body, field, original value)
    ('network_ioc', 'network-iocs', {'dns_ip': '203.0.113.9', 'auto_enrich': False, 'description': 'orig'},
     'NetworkIndicator', {'description': 'changed', 'host_id': str(uuid.uuid4())}, 'description', 'orig'),
    ('host_ioc', 'host-iocs', {'artifact_type': 'file', 'artifact_value': 'x.exe', 'notes': 'orig'},
     'HostBasedIndicator', {'notes': 'changed', 'host_id': str(uuid.uuid4())}, 'notes', 'orig'),
    ('account', 'accounts', {'account_name': 'svc', 'datetime_seen': '2026-01-01T00:00:00Z', 'notes': 'orig'},
     'CompromisedAccount', {'notes': 'changed', 'host_id': str(uuid.uuid4())}, 'notes', 'orig'),
    ('account_event', 'accounts', {'account_name': 'svc2', 'datetime_seen': '2026-01-01T00:00:00Z', 'notes': 'orig'},
     'CompromisedAccount', {'notes': 'changed', 'timeline_event_id': str(uuid.uuid4())}, 'notes', 'orig'),
    ('case_note', 'case-notes', {'title': 'orig', 'content': 'body'},
     'CaseNote', {'title': 'changed', 'content': '   '}, 'title', 'orig'),
]


@pytest.mark.parametrize('case', CASES, ids=[c[0] for c in CASES])
def test_update_400_leaves_row_unchanged(app, db, admin, make_incident, case):
    import app.models as models
    from app.models import AuditLog
    _, path, create_body, model_name, update_body, field, original = case
    model = getattr(models, model_name)
    inc = make_incident()
    obj = _ok(admin.post(f'{API}/incidents/{inc.id}/{path}', json=create_body))
    version = _reload(db, model, obj['id']).version

    resp = admin.put(f"{API}/incidents/{inc.id}/{path}/{obj['id']}", json=update_body)
    assert resp.status_code == 400, resp.get_json()

    row = _reload(db, model, obj['id'])
    assert getattr(row, field) == original
    assert row.version == version
    # The failed attempt is still audited, with its real status.
    statuses = [a.status_code for a in AuditLog.query.filter_by(action='update', incident_id=inc.id)]
    assert statuses == [400]
