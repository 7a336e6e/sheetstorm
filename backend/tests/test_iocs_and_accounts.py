"""Item 15 (IOC auto-enrichment opt-in, non-blocking) and the single-account
GET with ?reveal=true."""
import pytest


@pytest.fixture
def bg_tasks(monkeypatch):
    """Capture background tasks instead of spawning them."""
    from app import socketio
    tasks = []
    monkeypatch.setattr(socketio, 'start_background_task', lambda fn, *a, **k: tasks.append((fn, a, k)))
    return tasks


def _create_ioc(client, inc, **extra):
    return client.post(f'/api/v1/incidents/{inc.id}/network-iocs', json={'dns_ip': '203.0.113.7', **extra})


def test_auto_enrich_off_by_default(app, users, auth, make_incident, bg_tasks):
    resp = _create_ioc(auth(users['Analyst']), make_incident())
    assert resp.status_code == 201
    assert bg_tasks == []


def test_auto_enrich_org_setting_and_failure_is_non_blocking(app, db, users, auth, make_incident,
                                                            bg_tasks, org_a, monkeypatch):
    from app.services.enrichment_service import EnrichmentService
    org_a.settings = {**(org_a.settings or {}), 'auto_enrich_iocs': True}
    db.session.commit()
    try:
        inc = make_incident()
        resp = _create_ioc(auth(users['Analyst']), inc)
        assert resp.status_code == 201
        assert len(bg_tasks) == 1
        # Per-request opt-out still honoured
        _create_ioc(auth(users['Analyst']), inc, auto_enrich=False)
        assert len(bg_tasks) == 1

        # Run the task inline with a failing provider: must not raise.
        def boom(*a, **k):
            raise RuntimeError('provider down')
        monkeypatch.setattr(EnrichmentService, 'auto_enrich_ioc', staticmethod(boom))
        fn, args, kwargs = bg_tasks[0]
        fn(*args, **kwargs)
    finally:
        org_a.settings = {k: v for k, v in (org_a.settings or {}).items() if k != 'auto_enrich_iocs'}
        db.session.commit()


def test_auto_enrich_global_default(app, users, auth, make_incident, bg_tasks, monkeypatch):
    monkeypatch.setitem(app.config, 'IOC_AUTO_ENRICH', True)
    assert _create_ioc(auth(users['Analyst']), make_incident()).status_code == 201
    assert len(bg_tasks) == 1


@pytest.fixture
def account(app, users, auth, make_incident):
    inc = make_incident()
    resp = auth(users['Administrator']).post(f'/api/v1/incidents/{inc.id}/accounts', json={
        'account_name': 'svc_backup', 'account_type': 'service', 'password': 'Hunter2!',
        'datetime_seen': '2026-01-01T00:00:00Z'})
    assert resp.status_code == 201
    return inc, resp.get_json()


def test_single_account_reveal(app, users, auth, account):
    from app.models import AuditLog
    inc, acct = account
    url = f'/api/v1/incidents/{inc.id}/accounts/{acct["id"]}'
    before = AuditLog.query.filter_by(action='password_reveal', resource_id=acct['id']).count()

    masked = auth(users['Analyst']).get(url)
    assert masked.status_code == 200 and masked.get_json()['password'] == '********'
    assert masked.get_json()['account_name'] == 'svc_backup'

    # Analyst lacks compromised_accounts:reveal
    assert auth(users['Analyst']).get(url + '?reveal=true').status_code == 403

    shown = auth(users['Administrator']).get(url + '?reveal=true')
    assert shown.status_code == 200 and shown.get_json()['password'] == 'Hunter2!'
    after = AuditLog.query.filter_by(action='password_reveal', resource_id=acct['id']).count()
    assert after - before == 1


def test_single_account_other_org_not_found(app, users, auth, account):
    inc, acct = account
    assert auth(users['admin_b']).get(
        f'/api/v1/incidents/{inc.id}/accounts/{acct["id"]}?reveal=true').status_code == 404


def _stored_password(inc, acct):
    from app.models import CompromisedAccount
    from app.services.encryption_service import encryption_service
    row = CompromisedAccount.query.filter_by(id=acct['id'], incident_id=inc.id).first()
    return encryption_service.decrypt(row.password_encrypted) if row.password_encrypted else None


def _put(client, inc, acct, **payload):
    return client.put(f'/api/v1/incidents/{inc.id}/accounts/{acct["id"]}', json=payload)


def test_update_account_mask_sentinel_keeps_password(app, users, auth, account):
    inc, acct = account
    resp = _put(auth(users['Administrator']), inc, acct, notes='edited', password='********')
    assert resp.status_code == 200 and resp.get_json()['notes'] == 'edited'
    assert _stored_password(inc, acct) == 'Hunter2!'


def test_update_account_absent_or_empty_password_keeps_password(app, users, auth, account):
    inc, acct = account
    client = auth(users['Administrator'])
    assert _put(client, inc, acct, notes='a').status_code == 200
    assert _put(client, inc, acct, notes='b', password='').status_code == 200
    assert _put(client, inc, acct, notes='c', password=None).status_code == 200
    assert _stored_password(inc, acct) == 'Hunter2!'


def test_update_account_new_password_reencrypts(app, users, auth, account):
    inc, acct = account
    resp = _put(auth(users['Administrator']), inc, acct, password='N3w-Secret')
    assert resp.status_code == 200 and resp.get_json()['password'] == '********'
    assert _stored_password(inc, acct) == 'N3w-Secret'


def test_update_account_clear_password(app, users, auth, account):
    inc, acct = account
    resp = _put(auth(users['Administrator']), inc, acct, clear_password=True)
    assert resp.status_code == 200
    assert resp.get_json()['has_password'] is False
    assert _stored_password(inc, acct) is None


def test_update_account_permission_and_org_scoping(app, users, auth, account):
    inc, acct = account
    # Cross-org user cannot update (404) and the password survives
    assert _put(auth(users['admin_b']), inc, acct, clear_password=True).status_code == 404
    # Viewer cannot update
    assert _put(auth(users['Viewer']), inc, acct, clear_password=True).status_code == 403
    assert _stored_password(inc, acct) == 'Hunter2!'


def test_legacy_stored_mask_is_reported_as_no_password(app, db, users, auth, account):
    """Pre-PR0 edits could store the literal mask as the password: revealing it
    must report "no stored password", never hand out the mask as a password."""
    from app.models import CompromisedAccount
    from app.services.encryption_service import encryption_service
    inc, acct = account
    row = CompromisedAccount.query.filter_by(id=acct['id'], incident_id=inc.id).first()
    row.password_encrypted = encryption_service.encrypt('********')
    db.session.commit()
    client = auth(users['Administrator'])

    one = client.get(f'/api/v1/incidents/{inc.id}/accounts/{acct["id"]}?reveal=true').get_json()
    assert one['password'] is None and one['has_password'] is False

    items = client.get(f'/api/v1/incidents/{inc.id}/accounts?reveal=true').get_json()['items']
    listed = next(a for a in items if a['id'] == acct['id'])
    assert listed['password'] is None and listed['has_password'] is False
