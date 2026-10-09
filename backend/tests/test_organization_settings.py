"""Organization settings: schema validation, merge semantics, registration
(not an org setting since W3-SEC), AI TLP policy validation, before/after
audit, loosening event."""
from rbac_helpers import default_org, last_audit, make_role, make_user, new_org, security_events  # noqa: F401


def _admin_client(auth, make_user, org):
    return auth(make_user(org, roles=['Administrator']))


def test_put_rejects_unknown_keys(app, auth, new_org, make_user):
    c = _admin_client(auth, make_user, new_org())
    resp = c.put('/api/v1/organization', json={'settings': {'audit_retention_days': 1, 'bogus': True}})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body['error'] == 'validation_error'
    assert {'settings.audit_retention_days', 'settings.bogus'} <= set(body['fields'])
    assert c.put('/api/v1/organization', json={'nope': 1}).status_code == 400


def test_put_validates_timezone_and_types(app, auth, new_org, make_user):
    c = _admin_client(auth, make_user, new_org())
    assert c.put('/api/v1/organization', json={'settings': {'timezone': 'Mars/Olympus'}}).status_code == 400
    assert c.put('/api/v1/organization', json={'settings': {'auto_enrich_iocs': 'yes'}}).status_code == 400
    assert c.put('/api/v1/organization', json={'name': ''}).status_code == 400
    resp = c.put('/api/v1/organization', json={'name': '  Acme  ', 'settings': {'timezone': 'Europe/Bucharest',
                                                                             'auto_enrich_iocs': True}})
    assert resp.status_code == 200
    body = c.get('/api/v1/organization').get_json()
    assert body['name'] == 'Acme' and body['settings']['timezone'] == 'Europe/Bucharest'
    assert body['settings']['auto_enrich_iocs'] is True


def test_put_merges_and_keeps_protected_keys(app, db, auth, new_org, make_user):
    from app.models import Organization
    org = new_org(settings={'audit_retention_days': 400, 'legal_hold': True, 'timezone': 'UTC'})
    c = _admin_client(auth, make_user, org)
    assert c.put('/api/v1/organization', json={'settings': {'auto_enrich_iocs': False}}).status_code == 200
    db.session.expire_all()
    stored = Organization.query.get(org.id).settings
    assert stored['audit_retention_days'] == 400 and stored['legal_hold'] is True
    assert stored['timezone'] == 'UTC' and stored['auto_enrich_iocs'] is False


def test_get_filters_unknown_settings(app, auth, new_org, make_user):
    org = new_org(settings={'timezone': 'UTC', 'audit_retention_days': 9, 'secret_thing': 'x',
                            'registration_enabled': True})
    viewer = auth(make_user(org, roles=['Viewer']))
    body = viewer.get('/api/v1/organization').get_json()
    assert set(body['settings']) == {'timezone', 'ai_tlp_policy'}
    assert 'registration_enabled' not in body and body['is_default'] is False
    assert body['settings']['ai_tlp_policy'] == {'white': 'allow', 'green': 'allow', 'amber': 'allow',
                                                 'amber_strict': 'local_only', 'red': 'local_only'}


def test_viewer_cannot_put_org(app, users, auth):
    assert auth(users['Viewer']).put('/api/v1/organization', json={'name': 'x'}).status_code == 403


def test_registration_is_not_an_org_setting(app, db, auth, new_org, make_user, default_org):
    """W3-SEC (C11): registration lives in the platform org's security policy
    (provisioning.registration_enabled); PUT /organization rejects the key
    everywhere and GET /organization no longer returns it."""
    for org in (new_org(), default_org):
        c = _admin_client(auth, make_user, org)
        resp = c.put('/api/v1/organization', json={'settings': {'registration_enabled': True}})
        assert resp.status_code == 400 and resp.get_json()['error'] == 'validation_error'
        assert 'settings.registration_enabled' in resp.get_json()['fields']
        assert c.put('/api/v1/organization', json={'security': {}}).status_code == 400
        assert 'registration_enabled' not in c.get('/api/v1/organization').get_json()


def test_registration_default_false_when_unset(app, db, default_org):
    from app.models import OrganizationSecurityPolicy
    row = OrganizationSecurityPolicy.query.filter_by(organization_id=default_org.id).first()
    saved = dict(row.policy) if row is not None else None
    if row is not None:
        db.session.delete(row)
        db.session.commit()
    try:
        client = app.test_client()
        assert client.get('/api/v1/auth/registration-status').get_json()['registration_enabled'] is False
        resp = client.post('/api/v1/auth/register', json={'email': 'x@reg.test', 'name': 'X',
                                                          'password': 'An0ther-Str0ng-Pass!'})
        assert resp.status_code == 403
    finally:
        if saved is not None:
            db.session.add(OrganizationSecurityPolicy(organization_id=default_org.id, policy=saved))
            db.session.commit()


def test_ai_tlp_policy_validation(app, auth, new_org, make_user):
    c = _admin_client(auth, make_user, new_org())
    bad_key = c.put('/api/v1/organization', json={'settings': {'ai_tlp_policy': {'purple': 'allow'}}})
    assert bad_key.status_code == 400 and bad_key.get_json()['error'] == 'validation_error'
    bad_value = c.put('/api/v1/organization', json={'settings': {'ai_tlp_policy': {'red': 'yolo'}}})
    assert bad_value.status_code == 400
    ok = c.put('/api/v1/organization', json={'settings': {'ai_tlp_policy': {'amber': 'block'}}})
    assert ok.status_code == 200
    policy = ok.get_json()['settings']['ai_tlp_policy']
    assert policy['amber'] == 'block' and policy['red'] == 'local_only'  # partial update merges


def test_org_update_records_diff(app, db, auth, new_org, make_user):
    org = new_org(settings={'timezone': 'UTC'})
    c = _admin_client(auth, make_user, org)
    assert c.put('/api/v1/organization', json={'name': 'Renamed', 'settings': {
        'timezone': 'Europe/Paris', 'ai_tlp_policy': {'green': 'block'}}}).status_code == 200
    row = last_audit(db, 'update', 'organization')
    changes = row.details['changes']
    assert changes['name'] == {'from': 't', 'to': 'Renamed'}
    assert changes['settings.timezone'] == {'from': 'UTC', 'to': 'Europe/Paris'}
    # utils/audit_diff diffs nested dicts one level deep (dotted keys).
    assert changes['settings.ai_tlp_policy.green'] == {'from': 'allow', 'to': 'block'}
    assert not any(k.startswith('settings.ai_tlp_policy.') and k != 'settings.ai_tlp_policy.green' for k in changes)
    assert 'settings.auto_enrich_iocs' not in changes


def test_loosening_ai_policy_emits_security_event(app, db, auth, new_org, make_user):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    c = auth(admin)
    assert c.put('/api/v1/organization', json={'settings': {'ai_tlp_policy': {'red': 'block'}}}).status_code == 200
    assert not [e for e in security_events(db, 'ai_tlp_policy_loosened') if e.user_id == admin.id]
    assert c.put('/api/v1/organization', json={'settings': {'ai_tlp_policy': {'red': 'allow'}}}).status_code == 200
    events = [e for e in security_events(db, 'ai_tlp_policy_loosened') if e.user_id == admin.id]
    assert events and events[0].details['levels'] == {'red': {'from': 'block', 'to': 'allow'}}
