"""Item 5: legal hold semantics (indefinite lock vs. expiring hold), artifact
delete + incident purge enforcement, input validation."""
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def held_setup(app, db, users, make_incident, make_artifact):
    inc = make_incident()
    a = make_artifact(inc, filename='f', original_filename='disk.e01', storage_path='none',
                      storage_type='google_drive', file_size=1, md5='1' * 32, sha256='1' * 64,
                      sha512='1' * 128)
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

    # Let the hold lapse: deletion is allowed again (a tombstone).
    art = db.session.get(Artifact, a.id)
    art.legal_hold_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.session.commit()
    assert admin.delete(f'/api/v1/incidents/{inc.id}/artifacts/{a.id}').status_code == 200
    db.session.expire_all()
    art = db.session.get(Artifact, a.id)
    assert art is not None and art.deleted_at is not None and art.content_purged is True


@pytest.mark.parametrize('body', [
    {'hold': True, 'until': 'not-a-date'},
    {'hold': True, 'until': '2001-01-01T00:00:00Z'},
    {'hold': True, 'until': 12345},
    {'hold': 'yes'},
])
def test_invalid_hold_input(app, users, auth, held_setup, body):
    inc, a = held_setup
    assert _hold(auth(users['Administrator']), inc, a, **body).status_code == 400


# ── W1-EVD-CORE: holds on evidence items; audited purge ─────────────────────

def _item_hold(app, item, actor, **kw):
    from app import db
    from app.services.custody_ledger import CustodyLedger
    CustodyLedger.set_legal_hold(item, actor=actor, **kw)
    db.session.commit()


def test_item_hold_blocks_artifact_delete_and_purge(app, db, users, auth, held_setup):
    inc, a = held_setup
    admin = auth(users['Administrator'])
    item = a.evidence_item
    _item_hold(app, item, users['Administrator'], hold=True, reason='litigation')
    assert a.under_legal_hold is True
    assert admin.delete(f'/api/v1/incidents/{inc.id}/artifacts/{a.id}').status_code == 403

    assert admin.post(f'/api/v1/incidents/{inc.id}/archive').status_code == 200
    purge = admin.delete(f'/api/v1/incidents/{inc.id}/permanent')
    assert purge.status_code == 409
    body = purge.get_json()
    assert body['held_evidence_item_ids'] == [str(item.id)] and body['held_artifact_ids'] == []

    _item_hold(app, item, users['Administrator'], hold=False)
    assert admin.delete(f'/api/v1/incidents/{inc.id}/permanent').status_code == 200


def test_parent_item_hold_covers_children(app, db, users, make_incident, make_evidence):
    from app.services.custody_ledger import CustodyError, CustodyLedger
    inc = make_incident()
    parent = make_evidence(inc, title='laptop SSD image')
    child = make_evidence(inc, title='$MFT', parent_id=parent.id)
    _item_hold(app, parent, users['Administrator'], hold=True, reason='hold')
    assert child.under_legal_hold is True
    with pytest.raises(CustodyError) as exc:
        CustodyLedger.dispose(child, actor=users['Administrator'], method='destroyed', reason='cleanup')
    assert exc.value.status == 409 and exc.value.code == 'legal_hold'
    db.session.rollback()


def test_purge_removes_ledger_and_logs_heads(app, db, users, auth, make_incident, make_evidence, make_artifact):
    from sqlalchemy import text
    from app.models import AuditLog, ChainOfCustody, EvidenceItem
    from app.services.custody_ledger import CustodyLedger
    inc = make_incident()
    item = make_evidence(inc)
    make_artifact(inc)
    heads = CustodyLedger.heads(inc.id)
    admin = auth(users['Administrator'])
    assert admin.post(f'/api/v1/incidents/{inc.id}/archive').status_code == 200
    iid, item_id = inc.id, str(item.id)
    assert admin.delete(f'/api/v1/incidents/{iid}/permanent').status_code == 200

    db.session.expire_all()
    assert ChainOfCustody.query.filter_by(incident_id=iid).count() == 0
    assert EvidenceItem.query.filter_by(incident_id=iid).count() == 0
    event = (AuditLog.query.filter_by(action='incident_ledger_purged', resource_id=iid)
             .order_by(AuditLog.created_at.desc()).first())
    assert event is not None
    assert event.details['incident_head_seq'] == heads['incident']['seq'] == 3
    assert event.details['incident_head_hash'] == heads['incident']['hash']
    assert event.details['item_heads'][item_id]['seq'] == 1
    assert event.details['entry_count'] == 3 and event.details['item_count'] == 2
    # The purge GUC was transaction-local: the ledger is append-only again.
    assert db.session.execute(text("SELECT current_setting('sheetstorm.custody_purge', true)")).scalar() in (None, '')
