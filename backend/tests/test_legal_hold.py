"""Item 5: legal hold semantics (indefinite lock vs. expiring hold), artifact
delete + incident purge enforcement, input validation."""
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def held_setup(app, db, users, make_incident):
    from app.models import Artifact
    inc = make_incident()
    a = Artifact(incident_id=inc.id, filename='f', original_filename='disk.e01', storage_path='none',
                 storage_type='google_drive', file_size=1, md5='1' * 32, sha256='1' * 64,
                 sha512='1' * 128, uploaded_by=users['Administrator'].id)
    db.session.add(a)
    db.session.commit()
    return inc, a


def _hold(client, inc, a, **body):
    return client.post(f'/api/v1/incidents/{inc.id}/artifacts/{a.id}/legal-hold', json=body)


def test_indefinite_hold_blocks_delete_and_purge(app, db, users, auth, held_setup):
    inc, a = held_setup
    admin = auth(users['Administrator'])
    resp = _hold(admin, inc, a, hold=True, reason='litigation')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['is_locked'] is True and body['legal_hold_until'] is None and body['under_legal_hold']

    assert admin.delete(f'/api/v1/incidents/{inc.id}/artifacts/{a.id}').status_code == 403
    assert admin.post(f'/api/v1/incidents/{inc.id}/archive').status_code == 200
    purge = admin.delete(f'/api/v1/incidents/{inc.id}/permanent')
    assert purge.status_code == 409
    assert str(a.id) in purge.get_json()['held_artifact_ids']

    assert _hold(admin, inc, a, hold=False).status_code == 200
    assert admin.delete(f'/api/v1/incidents/{inc.id}/permanent').status_code == 200


def test_hold_with_until_expires(app, db, users, auth, held_setup):
    from app.models import Artifact
    inc, a = held_setup
    admin = auth(users['Administrator'])
    until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    body = _hold(admin, inc, a, hold=True, until=until).get_json()
    assert body['is_locked'] is False and body['under_legal_hold'] is True
    assert admin.delete(f'/api/v1/incidents/{inc.id}/artifacts/{a.id}').status_code == 403

    # Let the hold lapse: deletion is allowed again.
    art = db.session.get(Artifact, a.id)
    art.legal_hold_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.session.commit()
    assert admin.delete(f'/api/v1/incidents/{inc.id}/artifacts/{a.id}').status_code == 200


@pytest.mark.parametrize('body', [
    {'hold': True, 'until': 'not-a-date'},
    {'hold': True, 'until': '2001-01-01T00:00:00Z'},
    {'hold': True, 'until': 12345},
    {'hold': 'yes'},
])
def test_invalid_hold_input(app, users, auth, held_setup, body):
    inc, a = held_setup
    assert _hold(auth(users['Administrator']), inc, a, **body).status_code == 400
