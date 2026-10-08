"""Item 13: incident access ordering (Viewers: assigned or TLP:WHITE only;
Operators: assigned only; permission always required) and STIX export with
hosts."""


def test_viewer_unassigned_amber_forbidden(app, users, auth, make_incident):
    inc = make_incident(tlp='amber')
    viewer = auth(users['Viewer'])
    assert viewer.get(f'/api/v1/incidents/{inc.id}').status_code == 403
    assert viewer.get(f'/api/v1/incidents/{inc.id}/export/stix').status_code == 403
    assert viewer.get(f'/api/v1/incidents/{inc.id}/timeline').status_code == 403


def test_viewer_tlp_white_and_assigned_allowed(app, users, auth, make_incident):
    viewer = auth(users['Viewer'])
    white = make_incident(tlp='white')
    assigned = make_incident(tlp='red', assign=[users['Viewer']])
    for inc in (white, assigned):
        assert viewer.get(f'/api/v1/incidents/{inc.id}').status_code == 200
        assert viewer.get(f'/api/v1/incidents/{inc.id}/export/stix').status_code == 200
    ids = {i['id'] for i in viewer.get('/api/v1/incidents?per_page=100').get_json()['items']}
    assert str(white.id) in ids and str(assigned.id) in ids


def test_viewer_permission_enforced_even_when_assigned(app, users, auth, make_incident):
    # Viewer lacks artifacts:read — assignment must not bypass the permission.
    inc = make_incident(assign=[users['Viewer']])
    assert auth(users['Viewer']).get(f'/api/v1/incidents/{inc.id}/artifacts').status_code == 403


def test_operator_only_assigned(app, users, auth, make_incident):
    op = auth(users['Operator'])
    other = make_incident(tlp='white')
    mine = make_incident(assign=[users['Operator']])
    assert op.get(f'/api/v1/incidents/{other.id}').status_code == 403
    assert op.get(f'/api/v1/incidents/{mine.id}').status_code == 200
    # Operator lacks incidents:update even on an assigned incident.
    assert op.post(f'/api/v1/incidents/{mine.id}/playbook/execute', json={}).status_code == 403


def test_analyst_sees_unscoped_incident(app, users, auth, make_incident):
    inc = make_incident(tlp='amber')
    assert auth(users['Analyst']).get(f'/api/v1/incidents/{inc.id}').status_code == 200


def test_cross_org_is_not_found(app, users, auth, make_incident, org_b):
    inc = make_incident(org=org_b)
    admin_a = auth(users['Administrator'])
    assert admin_a.get(f'/api/v1/incidents/{inc.id}').status_code == 404
    assert admin_a.get(f'/api/v1/incidents/{inc.id}/export/stix').status_code == 404


def test_stix_export_with_hosts(app, db, users, auth, make_incident):
    from app.models import CompromisedHost
    inc = make_incident()
    db.session.add(CompromisedHost(incident_id=inc.id, hostname='ws01', os_version='Windows 11',
                                   system_type='workstation', created_by=users['Administrator'].id))
    db.session.commit()
    resp = auth(users['Administrator']).get(f'/api/v1/incidents/{inc.id}/export/stix')
    assert resp.status_code == 200
    infra = [o for o in resp.get_json()['objects'] if o['type'] == 'infrastructure']
    assert infra and 'Windows 11' in infra[0]['description']


def test_check_incident_access_rejects_malformed_id(app, users):
    from app.middleware.rbac import check_incident_access
    assert check_incident_access(users['Administrator'], 'not-a-uuid') == (False, None)
