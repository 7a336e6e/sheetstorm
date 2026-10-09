"""Item 6: playbook actions (org-scoped MITRE suggest, persisted summary,
create_task permission, per-action commits), audit on task toggle, template
ownership and definition validation."""
import pytest


def _definition(*actions, phase=1):
    return {'phases': [{'phase': phase, 'name': 'Identification', 'tasks': [{'title': 't'}],
                        'actions': list(actions)}]}


def _make_template(client, definition):
    resp = client.post('/api/v1/playbooks', json={'name': 'PB', 'definition': definition})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()['id']


def _activate(client, inc, pb_id):
    return client.post(f'/api/v1/incidents/{inc.id}/playbooks/{pb_id}/activate')


def test_suggest_mitre_action_uses_org_patterns(app, db, users, auth, make_incident):
    from app.models import TimelineEvent
    inc = make_incident()
    ev = TimelineEvent(incident_id=inc.id, timestamp=inc.created_at, activity='Encoded powershell launched',
                       mitre_mappings=[], created_by=users['Administrator'].id)
    db.session.add(ev)
    db.session.commit()
    admin = auth(users['Administrator'])
    pb = _make_template(admin, _definition({'key': 'm', 'type': 'suggest_mitre', 'auto_run': True}))
    resp = _activate(admin, inc, pb)
    assert resp.status_code == 201
    assert resp.get_json()['actions_executed'][0]['result']['status'] == 'success'
    db.session.expire_all()
    ev = db.session.get(TimelineEvent, ev.id)
    assert ev.mitre_mappings and ev.mitre_mappings[0]['technique'] == 'T1059'


def test_generate_summary_is_persisted_as_report(app, db, users, auth, make_incident, monkeypatch):
    from app.services.ai_service import ai_service
    from app.models import Report
    seen = {}

    def fake_report(report_type, *a, provider=None, organization_id=None, **kw):
        seen['org'] = organization_id
        return '# Summary\nAll good.'
    monkeypatch.setattr(ai_service, 'get_available_providers', lambda organization_id=None: ['ollama'])
    monkeypatch.setattr(ai_service, 'generate_report', fake_report)
    inc = make_incident()
    admin = auth(users['Administrator'])
    pb = _make_template(admin, _definition({'key': 's', 'type': 'generate_summary', 'auto_run': True}))
    result = _activate(admin, inc, pb).get_json()['actions_executed'][0]['result']
    assert result['status'] == 'success'
    report = db.session.get(Report, result['report_id'])
    assert report.ai_summary.startswith('# Summary') and report.incident_id == inc.id
    assert seen['org'] == str(inc.organization_id)


def test_create_task_action_requires_tasks_create(app, db, users, auth, make_incident):
    from app.models import Task
    inc = make_incident()
    responder = auth(users['Incident Responder'])
    pb = _make_template(responder, _definition({'key': 'c', 'type': 'create_task',
                                                'config': {'title': 'Collect memory'}}))
    assert _activate(responder, inc, pb).status_code == 201
    analyst = auth(users['Analyst'])  # incidents:update but no tasks:create
    resp = analyst.post(f'/api/v1/incidents/{inc.id}/playbook/execute', json={'action_key': 'c'})
    assert resp.status_code == 200
    assert resp.get_json()['result']['status'] == 'forbidden'
    assert Task.query.filter_by(incident_id=inc.id, title='Collect memory').count() == 0
    ok = responder.post(f'/api/v1/incidents/{inc.id}/playbook/execute', json={'action_key': 'c'})
    assert ok.get_json()['result']['status'] == 'success'
    assert Task.query.filter_by(incident_id=inc.id, title='Collect memory').count() == 1


def test_failed_action_keeps_earlier_run_records(app, db, users, auth, make_incident, monkeypatch):
    from app.services.playbook_service import PlaybookService
    from app.models import IncidentPlaybook

    def boom(incident, config, user):
        raise RuntimeError('provider down')
    monkeypatch.setattr(PlaybookService, '_create_task', staticmethod(boom))
    inc = make_incident()
    admin = auth(users['Administrator'])
    pb = _make_template(admin, _definition(
        {'key': 'a', 'type': 'suggest_mitre', 'auto_run': True},
        {'key': 'b', 'type': 'create_task', 'auto_run': True, 'config': {'title': 'x'}},
    ))
    runs = _activate(admin, inc, pb).get_json()['actions_executed']
    assert [r['result']['status'] for r in runs] == ['success', 'error']
    db.session.expire_all()
    inst = IncidentPlaybook.query.filter_by(incident_id=inc.id).one()
    assert [r['key'] for r in inst.state['action_runs']] == ['a', 'b']


def test_toggle_task_is_audited(app, db, users, auth, make_incident):
    from app.models import AuditLog
    inc = make_incident()
    admin = auth(users['Administrator'])
    _activate(admin, inc, _make_template(admin, _definition()))
    resp = admin.put(f'/api/v1/incidents/{inc.id}/playbook/task', json={'task_key': 'p1-t0', 'done': True})
    assert resp.status_code == 200
    assert AuditLog.query.filter_by(incident_id=inc.id, action='toggle_playbook_task').count() == 1
    assert admin.put(f'/api/v1/incidents/{inc.id}/playbook/task',
                     json={'task_key': 'k', 'done': 'yes'}).status_code == 400


def test_template_crud_requires_templates_manage(app, users, auth):
    """C22: playbook CRUD needs templates:manage (Administrator + Incident
    Responder); it no longer depends on being the creator."""
    admin = auth(users['Administrator'])
    responder = auth(users['Incident Responder'])
    analyst = auth(users['Analyst'])
    pb = _make_template(admin, _definition())
    # No templates:manage: every write is a 403, reads stay open.
    assert analyst.post('/api/v1/playbooks', json={'name': 'x', 'definition': _definition()}).status_code == 403
    assert analyst.put(f'/api/v1/playbooks/{pb}', json={'name': 'hijack'}).status_code == 403
    assert analyst.delete(f'/api/v1/playbooks/{pb}').status_code == 403
    assert analyst.get(f'/api/v1/playbooks/{pb}').status_code == 200
    # A holder may edit and delete a template somebody else created.
    assert responder.put(f'/api/v1/playbooks/{pb}', json={'name': 'shared edit'}).status_code == 200
    own = _make_template(responder, _definition())
    assert admin.delete(f'/api/v1/playbooks/{own}').status_code == 200
    assert responder.delete(f'/api/v1/playbooks/{pb}').status_code == 200


def test_template_is_org_scoped(app, users, auth):
    admin = auth(users['Administrator'])
    pb = _make_template(admin, _definition())
    other = auth(users['admin_b'])
    assert other.get(f'/api/v1/playbooks/{pb}').status_code == 404
    assert other.put(f'/api/v1/playbooks/{pb}', json={'name': 'x'}).status_code == 404
    assert other.delete(f'/api/v1/playbooks/{pb}').status_code == 404


@pytest.mark.parametrize('definition', [
    'nope',
    {'phases': 'x'},
    {'phases': ['x']},
    {'phases': [{'phase': 9}]},
    {'phases': [{'phase': 1, 'actions': 'x'}]},
    {'phases': [{'phase': 1, 'actions': [{'key': 'a', 'type': 'rm_rf'}]}]},
    {'phases': [{'phase': 1, 'actions': [{'type': 'suggest_mitre'}]}]},
    {'phases': [{'phase': 1, 'actions': [{'key': 'a', 'type': 'suggest_mitre', 'config': []}]}]},
    {'phases': [{'phase': 1, 'actions': [{'key': 'a', 'type': 'suggest_mitre'},
                                         {'key': 'a', 'type': 'enrich_iocs'}]}]},
    {'phases': [{'phase': 1, 'tasks': 'x'}]},
])
def test_invalid_definitions_rejected(app, users, auth, definition):
    resp = auth(users['Administrator']).post('/api/v1/playbooks', json={'name': 'x', 'definition': definition})
    assert resp.status_code == 400
