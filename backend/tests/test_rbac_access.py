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


# ── Permission-driven visibility & actions (admin guardrails §3.5) ──

from rbac_helpers import make_role, make_user, new_org  # noqa: E402,F401


def _team_restricted(db, org, inc):
    from app.models import IncidentTeam, Team
    team = Team(organization_id=org.id, name=f'team-{inc.id.hex[:8]}')
    db.session.add(team)
    db.session.flush()
    db.session.add(IncidentTeam(incident_id=inc.id, team_id=team.id))
    db.session.commit()
    return inc


def test_viewer_plus_analyst_gets_union(app, db, auth, new_org, make_user, make_incident):
    org = new_org()
    both = make_user(org, roles=['Viewer', 'Analyst'])
    viewer_only = make_user(org, roles=['Viewer'])
    unscoped = make_incident(org=org, creator=both, tlp='amber')
    white_team = _team_restricted(db, org, make_incident(org=org, creator=both, tlp='white'))
    restricted = _team_restricted(db, org, make_incident(org=org, creator=both, tlp='amber'))
    assigned = _team_restricted(db, org, make_incident(org=org, creator=both, tlp='red', assign=[both]))
    ids = {i['id'] for i in auth(both).get('/api/v1/incidents?per_page=100').get_json()['items']}
    assert {str(unscoped.id), str(white_team.id), str(assigned.id)} <= ids
    assert str(restricted.id) not in ids
    assert auth(both).get(f'/api/v1/incidents/{unscoped.id}').status_code == 200
    # Viewer alone: assigned + TLP:WHITE only (no team scope).
    assert auth(viewer_only).get(f'/api/v1/incidents/{unscoped.id}').status_code == 403
    assert auth(viewer_only).get(f'/api/v1/incidents/{white_team.id}').status_code == 200


def test_custom_role_without_scope_sees_assigned_only(app, auth, new_org, make_user, make_incident):
    org = new_org()
    u = make_user(org, perms=['incidents:read'])
    other = make_incident(org=org, creator=u, tlp='white')
    mine = make_incident(org=org, creator=u, assign=[u])
    assert auth(u).get(f'/api/v1/incidents/{other.id}').status_code == 403
    assert auth(u).get(f'/api/v1/incidents/{mine.id}').status_code == 200
    assert [i['id'] for i in auth(u).get('/api/v1/incidents').get_json()['items']] == [str(mine.id)]


def test_manager_sees_all_via_read_all(app, db, users, auth, make_incident, org_a, make_user):
    inc = _team_restricted(db, org_a, make_incident(tlp='red'))
    assert auth(users['Manager']).get(f'/api/v1/incidents/{inc.id}').status_code == 200
    custom = make_user(org_a, perms=['incidents:read', 'incidents:read_all'])
    assert auth(custom).get(f'/api/v1/incidents/{inc.id}').status_code == 200


def test_archive_requires_incidents_archive(app, auth, new_org, make_user, make_incident):
    org = new_org()
    manager = make_user(org, roles=['Manager'])
    admin = make_user(org, roles=['Administrator'])
    archiver = make_user(org, perms=['incidents:read', 'incidents:read_all', 'incidents:archive'])
    a, b = make_incident(org=org, creator=admin), make_incident(org=org, creator=admin)
    assert auth(manager).post(f'/api/v1/incidents/{a.id}/archive').status_code == 403
    assert auth(admin).post(f'/api/v1/incidents/{a.id}/archive').status_code == 200
    assert auth(archiver).post(f'/api/v1/incidents/{b.id}/archive').status_code == 200
    listed = {i['id'] for i in auth(archiver).get('/api/v1/incidents/archived').get_json()['items']}
    assert {str(a.id), str(b.id)} <= listed
    assert auth(manager).get('/api/v1/incidents/archived').status_code == 403
    assert auth(archiver).post(f'/api/v1/incidents/{a.id}/unarchive').status_code == 200


def test_archive_respects_visibility(app, auth, new_org, make_user, make_incident):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    archiver = make_user(org, perms=['incidents:read', 'incidents:archive'])  # assigned-only scope
    inc = make_incident(org=org, creator=admin)
    assert auth(archiver).post(f'/api/v1/incidents/{inc.id}/archive').status_code == 403


def test_purge_requires_incidents_purge(app, auth, new_org, make_user, make_incident):
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    archiver = make_user(org, perms=['incidents:read', 'incidents:read_all', 'incidents:archive'])
    inc = make_incident(org=org, creator=admin)
    assert auth(admin).post(f'/api/v1/incidents/{inc.id}/archive').status_code == 200
    assert auth(archiver).delete(f'/api/v1/incidents/{inc.id}/permanent').status_code == 403
    assert auth(admin).delete(f'/api/v1/incidents/{inc.id}/permanent').status_code == 200


def test_task_delete_by_permission_not_name(app, auth, new_org, make_user, make_incident):
    org = new_org()
    deleter = make_user(org, perms=['incidents:read', 'incidents:read_all', 'tasks:create', 'tasks:delete'])
    responder = make_user(org, roles=['Incident Responder'])
    inc = make_incident(org=org, creator=deleter)
    tid = auth(deleter).post(f'/api/v1/incidents/{inc.id}/tasks', json={'title': 'T'}).get_json()['id']
    assert auth(responder).delete(f'/api/v1/incidents/{inc.id}/tasks/{tid}').status_code == 403
    assert auth(deleter).delete(f'/api/v1/incidents/{inc.id}/tasks/{tid}').status_code == 200


def test_case_note_delete_requires_case_notes_delete(app, auth, new_org, make_user, make_incident):
    org = new_org()
    writer = make_user(org, perms=['incidents:read', 'incidents:read_all', 'incidents:update'])
    deleter = make_user(org, perms=['incidents:read', 'incidents:read_all', 'case_notes:delete'])
    inc = make_incident(org=org, creator=writer)
    nid = auth(writer).post(f'/api/v1/incidents/{inc.id}/case-notes',
                            json={'title': 'N', 'content': 'c'}).get_json()['id']
    assert auth(writer).delete(f'/api/v1/incidents/{inc.id}/case-notes/{nid}').status_code == 403
    assert auth(deleter).delete(f'/api/v1/incidents/{inc.id}/case-notes/{nid}').status_code == 200


def test_activity_feed_admin_actions_by_audit_logs_read(app, auth, new_org, make_user):
    from app.middleware.audit import log_audit_event
    org = new_org()
    admin = make_user(org, roles=['Administrator'])
    reader = make_user(org, perms=['audit_logs:read'])
    plain = make_user(org, perms=['incidents:read'])
    with app.test_request_context():
        log_audit_event('admin_action', 'feed_perm_check', user=admin)
    for user, visible in ((reader, True), (plain, False)):
        actions = {i['action'] for i in auth(user).get('/api/v1/activity-feed?limit=100').get_json()['items']}
        assert ('feed_perm_check' in actions) is visible
