"""W3-QST-BE: case templates (built-in + org), apply, create-incident
integration, custom fields, and the playbook built-ins."""
import copy
import os
import subprocess
import sys
import uuid

import pytest

from app.services import realtime

API = '/api/v1'
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Recorder:
    def __init__(self):
        self.emits = []

    def emit(self, event, data=None, to=None, **kw):
        self.emits.append((event, data, to))

    def resyncs(self):
        return [d for e, d, _ in self.emits if e == 'incident:resync']


@pytest.fixture
def rec(app):
    r = Recorder()
    realtime.set_emitter(r)
    yield r
    realtime.set_emitter(None)


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


@pytest.fixture(autouse=True)
def _clean_templates(app, db):
    """The suite shares one database: start each test without org templates
    (applications keep their ledger snapshot, the link is set to NULL)."""
    from app.models import CaseTemplate
    CaseTemplate.query.delete()
    db.session.commit()
    yield


def _defn(**over):
    d = {
        'schema_version': 1,
        'defaults': {'severity': 'high', 'tlp': 'red', 'classification': 'custom_class'},
        'questions': [
            {'ref': 'ss:SSQ-001', 'priority': 'critical'},
            {'ref': 'ss:SSQ-006'},
            {'key': 'own-q', 'question': 'Did the finance team approve the transfer?', 'phase': 2, 'facet': 'Money'},
        ],
        'leads': [
            {'key': 'l1', 'title': 'Review VPN logs', 'phase': 2, 'answers': ['ss:SSQ-001', 'own-q']},
            {'key': 'l2', 'title': 'Interview the service owner', 'answers': ['ss:SSQ-006']},
        ],
        'playbook': {'builtin': 'picerl-generic'},
        'custom_fields': [
            {'key': 'ticket', 'label': 'Ticket', 'type': 'text'},
            {'key': 'loss', 'label': 'Loss', 'type': 'number'},
            {'key': 'paid', 'label': 'Paid', 'type': 'boolean'},
            {'key': 'seen', 'label': 'First seen', 'type': 'date'},
            {'key': 'stage', 'label': 'Stage', 'type': 'select', 'options': ['a', 'b'], 'required': True},
        ],
    }
    d.update(over)
    return d


def _body(key='my-tpl', **over):
    body = {'key': key, 'name': 'My template', 'description': 'd', 'incident_type': 'x', 'definition': _defn()}
    body.update(over)
    return body


def _create_tpl(client, **kw):
    r = client.post(f'{API}/case-templates', json=_body(**kw))
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _apply(client, inc, ref, **body):
    return client.post(f'{API}/incidents/{inc.id}/case-templates/{ref}/apply', json=body)


def _questions(db, inc):
    from app.models import InvestigativeQuestion
    return InvestigativeQuestion.query.filter_by(incident_id=inc.id).all()


def _tasks(db, inc):
    from app.models import Task
    return Task.query.filter_by(incident_id=inc.id).all()


# ── listing and detail ────────────────────────────────────────────────────

def test_list_has_builtins_and_only_own_org_rows(admin, users, auth):
    _create_tpl(admin, key='org-a-tpl')
    _create_tpl(auth(users['admin_b']), key='org-b-tpl')
    items = admin.get(f'{API}/case-templates').get_json()['items']
    ids = [i['id'] for i in items]
    assert {'builtin:generic-intrusion', 'builtin:ransomware'} <= set(ids)
    builtin = next(i for i in items if i['id'] == 'builtin:ransomware')
    assert builtin['is_builtin'] is True and builtin['summary']['questions'] == 20
    assert builtin['summary']['playbook'] == 'ransomware' and 'definition' not in builtin
    keys = {i.get('key') for i in items}
    assert 'org-a-tpl' in keys and 'org-b-tpl' not in keys
    full = admin.get(f'{API}/case-templates?include_definition=true').get_json()['items']
    assert all('definition' in i for i in full)


def test_detail_builtin_and_org_with_resolved_names(admin):
    r = admin.get(f'{API}/case-templates/builtin:ransomware')
    assert r.status_code == 200
    body = r.get_json()
    assert body['definition']['schema_version'] == 1
    assert body['resolved']['playbook']['name'] == 'Ransomware response'
    assert body['resolved']['questions'][0]['question']
    org = _create_tpl(admin)
    got = admin.get(f"{API}/case-templates/{org['id']}")
    assert got.status_code == 200 and got.headers['ETag'] == '"1"'
    assert got.get_json()['resolved']['questions'][2]['source'] == 'template'
    for bad in ('builtin:nope', 'builtin:../etc', str(uuid.uuid4()), 'garbage'):
        assert admin.get(f'{API}/case-templates/{bad}').status_code == 404


def test_org_isolation_of_detail(admin, users, auth):
    org = _create_tpl(admin)
    assert auth(users['admin_b']).get(f"{API}/case-templates/{org['id']}").status_code == 404
    assert auth(users['admin_b']).delete(f"{API}/case-templates/{org['id']}").status_code == 404


# ── write permissions and built-in immutability ───────────────────────────

def test_manage_permission_required(users, auth, admin):
    for role in ('Analyst', 'Viewer', 'Operator'):
        c = auth(users[role])
        assert c.post(f'{API}/case-templates', json=_body()).status_code == 403, role
    org = _create_tpl(admin)
    analyst = auth(users['Analyst'])
    assert analyst.put(f"{API}/case-templates/{org['id']}", json={'name': 'x'}).status_code == 403
    assert analyst.delete(f"{API}/case-templates/{org['id']}").status_code == 403
    assert analyst.post(f"{API}/case-templates/{org['id']}/clone").status_code == 403
    # an Incident Responder holds templates:manage by default
    assert auth(users['Incident Responder']).post(f'{API}/case-templates', json=_body(key='ir-tpl')).status_code == 201


def test_builtins_are_read_only(admin):
    assert admin.put(f'{API}/case-templates/builtin:ransomware', json={'name': 'x'}).status_code == 403
    assert admin.delete(f'{API}/case-templates/builtin:ransomware').status_code == 403
    assert admin.put(f'{API}/case-templates/builtin:nope', json={'name': 'x'}).status_code == 404


def test_create_update_delete_and_versions(admin, db):
    from app.models import AuditLog
    t = _create_tpl(admin)
    assert t['version'] == 1 and t['is_builtin'] is False and t['definition']['schema_version'] == 1
    assert admin.post(f'{API}/case-templates', json=_body()).status_code == 409  # same key

    r = admin.put(f"{API}/case-templates/{t['id']}", json={'name': 'Renamed', 'expected_version': 1})
    assert r.status_code == 200 and r.get_json()['version'] == 2 and r.get_json()['name'] == 'Renamed'
    stale = admin.put(f"{API}/case-templates/{t['id']}", json={'name': 'Stale'}, headers={'If-Match': '"1"'})
    assert stale.status_code == 409 and stale.get_json()['current']['name'] == 'Renamed'
    new_def = _defn(questions=[{'ref': 'ss:SSQ-002'}], leads=[], custom_fields=[])
    r = admin.put(f"{API}/case-templates/{t['id']}", json={'definition': new_def, 'is_active': False})
    assert r.status_code == 200 and r.get_json()['version'] == 3 and r.get_json()['is_active'] is False
    assert r.get_json()['key'] == 'my-tpl'
    assert admin.put(f"{API}/case-templates/{t['id']}", json={'key': 'other'}).status_code == 400  # immutable
    # inactive templates leave the default list, managers can list them
    assert t['id'] not in [i['id'] for i in admin.get(f'{API}/case-templates').get_json()['items']]
    assert t['id'] in [i['id'] for i in admin.get(f'{API}/case-templates?include_inactive=true').get_json()['items']]
    assert admin.delete(f"{API}/case-templates/{t['id']}").status_code == 200
    assert admin.get(f"{API}/case-templates/{t['id']}").status_code == 404
    actions = {r.action for r in AuditLog.query.filter_by(resource_type='case_template').all()}
    assert {'create', 'update', 'delete'} <= actions


def test_clone_builtin_and_org(admin):
    c1 = admin.post(f'{API}/case-templates/builtin:ransomware/clone')
    assert c1.status_code == 201
    body = c1.get_json()
    assert body['key'] == 'ransomware-copy' and body['cloned_from'] == 'builtin:ransomware'
    assert body['is_builtin'] is False and body['name'] == 'Ransomware (copy)'
    assert body['definition']['playbook'] == {'builtin': 'ransomware'}
    assert admin.post(f'{API}/case-templates/builtin:ransomware/clone').get_json()['key'] == 'ransomware-copy-2'
    c3 = admin.post(f"{API}/case-templates/{body['id']}/clone", json={'name': 'Mine'})
    assert c3.status_code == 201 and c3.get_json()['cloned_from'] == body['id'] and c3.get_json()['name'] == 'Mine'
    assert admin.post(f'{API}/case-templates/builtin:nope/clone').status_code == 404
    assert admin.post(f'{API}/case-templates/builtin:ransomware/clone', json={'name': ''}).status_code == 400


# ── validation ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('mutate', [
    lambda d: d.update(extra_key=1),
    lambda d: d.update(schema_version=2),
    lambda d: d['questions'].append({'ref': 'ss:SSQ-999'}),
    lambda d: d['questions'].append({'ref': 'nonsense'}),
    lambda d: d['questions'].append({'ref': 'ss:SSQ-001'}),                       # duplicate
    lambda d: d['questions'].append({'key': 'x', 'question': 'ab'}),              # too short
    lambda d: d['questions'].append({'ref': 'ss:SSQ-002', 'question': 'both?'}),
    lambda d: d['leads'][0].update(answers=['ss:SSQ-040']),                       # dangling answers
    lambda d: d['leads'].append({'key': 'l1', 'title': 'Duplicate key lead'}),
    lambda d: d.update(playbook={'builtin': 'does-not-exist'}),
    lambda d: d.update(playbook={'playbook_id': str(uuid.uuid4())}),              # not in this org
    lambda d: d.update(playbook={'builtin': 'ransomware', 'playbook_id': str(uuid.uuid4())}),
    lambda d: d['custom_fields'].append({'key': 'Bad Key', 'label': 'x', 'type': 'text'}),
    lambda d: d['custom_fields'].append({'key': 'sel', 'label': 'x', 'type': 'select'}),
    lambda d: d['custom_fields'].append({'key': 'txt', 'label': 'x', 'type': 'text', 'options': ['a']}),
    lambda d: d['custom_fields'].append({'key': 'ticket', 'label': 'dup', 'type': 'text'}),
    lambda d: d['defaults'].update(severity='urgent'),
    lambda d: d['defaults'].update(tlp='purple'),
    lambda d: d.update(questions=[{'ref': f'ss:SSQ-{i}'} for i in range(201)]),
    lambda d: d.update(leads=[{'key': f'k{i}', 'title': f'Lead number {i}'} for i in range(101)]),
])
def test_invalid_definitions_rejected(admin, mutate):
    d = _defn()
    mutate(d)
    r = admin.post(f'{API}/case-templates', json=_body(definition=d))
    assert r.status_code == 400, r.get_json()
    assert r.get_json()['error'] == 'validation_error' and r.get_json()['fields']


def test_foreign_org_playbook_rejected_but_own_accepted(admin, users, auth, db):
    other = auth(users['admin_b']).post(f'{API}/playbooks', json={'name': 'Theirs', 'definition': {'phases': []}})
    assert other.status_code == 201
    r = admin.post(f'{API}/case-templates', json=_body(definition=_defn(playbook={'playbook_id': other.get_json()['id']})))
    assert r.status_code == 400
    mine = admin.post(f'{API}/playbooks', json={'name': 'Mine', 'definition': {'phases': []}}).get_json()
    ok = admin.post(f'{API}/case-templates', json=_body(definition=_defn(playbook={'playbook_id': mine['id']})))
    assert ok.status_code == 201


def test_body_size_cap_and_shape(admin):
    huge = _defn(report_template='x' * 100)
    huge['questions'][2]['description'] = 'y' * 4000
    big = _body(definition=huge)
    big['description'] = 'z' * (300 * 1024)
    assert admin.post(f'{API}/case-templates', json=big).status_code == 400
    assert admin.post(f'{API}/case-templates', data='[]', content_type='application/json').status_code == 400
    assert admin.post(f'{API}/case-templates', json=_body(key='Bad Key!')).status_code == 400
    assert admin.post(f'{API}/case-templates', json={**_body(), 'unknown': 1}).status_code == 400


# ── apply ─────────────────────────────────────────────────────────────────

def test_apply_creates_questions_leads_links_playbook_ledger(admin, db, make_incident, rec):
    from app.models import IncidentCaseTemplate, IncidentPlaybook, QuestionLead
    inc = make_incident(severity='medium', tlp='amber')
    tpl = _create_tpl(admin)
    r = _apply(admin, inc, tpl['id'])
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['created'] == {'questions': 3, 'leads': 2, 'links': 3}
    assert body['playbook']['status'] == 'activated' and body['skipped'] == []
    assert body['defaults_applied'] == [] and body['dry_run'] is False
    assert body['custom_fields_added'] == 5 and body['template']['key'] == 'my-tpl'

    qs = {q.source_ref: q for q in _questions(db, inc)}
    assert set(qs) == {'ss:SSQ-001', 'ss:SSQ-006', 'tpl:my-tpl:own-q'}
    assert qs['ss:SSQ-001'].priority == 'critical' and qs['ss:SSQ-001'].source == 'core'
    assert qs['tpl:my-tpl:own-q'].source == 'template' and qs['tpl:my-tpl:own-q'].facet == 'Money'
    tasks = {t.title: t for t in _tasks(db, inc)}
    assert tasks['Review VPN logs'].task_type == 'investigative_lead'
    assert tasks['Review VPN logs'].extra_data['template_lead_key'] == 'my-tpl:l1'
    assert QuestionLead.query.count() >= 3
    inst = IncidentPlaybook.query.filter_by(incident_id=inc.id).one()
    assert inst.builtin_key == 'picerl-generic' and inst.playbook_id is None and inst.definition['phases']
    assert not inst.state['action_runs']  # nothing auto-ran
    ledger = IncidentCaseTemplate.query.filter_by(incident_id=inc.id).one()
    assert ledger.template_key == 'my-tpl' and ledger.template_version == 1
    assert len(ledger.custom_field_defs) == 5 and ledger.result['created']['questions'] == 3
    # defaults were not requested: the incident is untouched
    db.session.refresh(inc)
    assert (inc.severity, inc.tlp) == ('medium', 'amber')
    # one resync for questions/tasks/playbook
    assert {'questions'} in [set(r['scopes']) for r in rec.resyncs()]
    assert {'tasks'} in [set(r['scopes']) for r in rec.resyncs()]
    ledger_api = admin.get(f'{API}/incidents/{inc.id}/case-templates').get_json()
    assert ledger_api['total'] == 1 and ledger_api['items'][0]['template_name'] == 'My template'


def test_apply_twice_is_all_skipped(admin, db, make_incident):
    inc = make_incident()
    tpl = _create_tpl(admin)
    _apply(admin, inc, tpl['id'])
    second = _apply(admin, inc, tpl['id']).get_json()
    assert second['created'] == {'questions': 0, 'leads': 0, 'links': 0}
    assert {s['reason'] for s in second['skipped']} == {'exists', 'already_active'}
    assert len(second['skipped']) == 6 and second['custom_fields_added'] == 0
    assert len(_questions(db, inc)) == 3 and len(_tasks(db, inc)) == 2


def test_apply_skips_manual_duplicates_and_never_resurrects(admin, db, make_incident):
    inc = make_incident()
    admin.post(f'{API}/incidents/{inc.id}/questions',
               json={'question': 'which ACCOUNTS were used or compromised?'})
    tpl = _create_tpl(admin)
    body = _apply(admin, inc, tpl['id']).get_json()
    assert body['created']['questions'] == 2  # SSQ-006 matched the manual text
    assert {'kind': 'question', 'ref': 'ss:SSQ-006', 'reason': 'exists'} in body['skipped']
    # the lead for SSQ-006 is linked to the existing manual question
    from app.models import QuestionLead
    manual = next(q for q in _questions(db, inc) if q.source == 'manual')
    assert QuestionLead.query.filter_by(question_id=manual.id).count() == 1
    # archive one and re-apply: it stays archived and is not recreated
    first = next(q for q in _questions(db, inc) if q.source_ref == 'ss:SSQ-001')
    assert admin.delete(f'{API}/incidents/{inc.id}/questions/{first.id}').status_code == 200
    again = _apply(admin, inc, tpl['id']).get_json()
    assert again['created']['questions'] == 0
    assert len([q for q in _questions(db, inc) if q.source_ref == 'ss:SSQ-001']) == 1


def test_lead_dedupes_by_title_and_marker(admin, db, users, make_incident):
    inc = make_incident()
    admin.post(f'{API}/incidents/{inc.id}/tasks', json={'title': '  review vpn LOGS ', 'task_type': 'investigative_lead'})
    tpl = _create_tpl(admin)
    body = _apply(admin, inc, tpl['id']).get_json()
    assert body['created']['leads'] == 1
    assert {'kind': 'lead', 'ref': 'l1', 'reason': 'exists'} in body['skipped']


def test_analyst_apply_skips_leads_forbidden(users, auth, admin, make_incident, db):
    inc = make_incident(assign=[users['Analyst']])
    tpl = _create_tpl(admin)
    r = _apply(auth(users['Analyst']), inc, tpl['id'])
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['created']['leads'] == 0 and body['created']['questions'] == 3
    assert [s['reason'] for s in body['skipped'] if s['kind'] == 'lead'] == ['forbidden', 'forbidden']
    assert len(_tasks(db, inc)) == 0


def test_apply_requires_update_and_access(users, auth, admin, make_incident):
    inc = make_incident(assign=[users['Viewer']])
    tpl = _create_tpl(admin)
    assert _apply(auth(users['Viewer']), inc, tpl['id']).status_code == 403
    assert _apply(auth(users['admin_b']), inc, tpl['id']).status_code == 404
    # another org's template is a 404 for us
    theirs = _create_tpl(auth(users['admin_b']), key='theirs')
    assert _apply(admin, inc, theirs['id']).status_code == 404
    assert _apply(admin, inc, 'builtin:nope').status_code == 404
    assert _apply(admin, inc, str(uuid.uuid4())).status_code == 404
    assert _apply(admin, inc, tpl['id'], include=['bogus']).status_code == 400
    assert _apply(admin, inc, tpl['id'], nonsense=True).status_code == 400


def test_inactive_template_cannot_be_applied(admin, make_incident):
    inc = make_incident()
    tpl = _create_tpl(admin, is_active=False)
    r = _apply(admin, inc, tpl['id'])
    assert r.status_code == 409 and r.get_json()['error'] == 'template_inactive'


def test_existing_playbook_is_never_replaced(admin, db, make_incident):
    from app.models import IncidentPlaybook
    inc = make_incident()
    assert admin.post(f'{API}/incidents/{inc.id}/playbooks/builtin/ransomware/activate').status_code == 201
    tpl = _create_tpl(admin)
    body = _apply(admin, inc, tpl['id']).get_json()
    assert body['playbook']['status'] == 'existing_playbook'
    assert {'kind': 'playbook', 'ref': 'builtin:picerl-generic', 'reason': 'existing_playbook'} in body['skipped']
    assert IncidentPlaybook.query.filter_by(incident_id=inc.id).count() == 1
    # applying a template whose playbook is the active one reports already_active
    same = _create_tpl(admin, key='same', definition=_defn(playbook={'builtin': 'ransomware'}))
    assert _apply(admin, inc, same['id']).get_json()['playbook']['status'] == 'already_active'


def test_apply_defaults_only_raise(admin, db, make_incident):
    inc = make_incident(severity='critical', tlp='red', classification=None)
    tpl = _create_tpl(admin, definition=_defn(defaults={'severity': 'low', 'tlp': 'white', 'classification': 'cls'}))
    body = _apply(admin, inc, tpl['id'], apply_defaults=True).get_json()
    db.session.refresh(inc)
    assert (inc.severity, inc.tlp) == ('critical', 'red')  # never lowered
    assert inc.classification == 'cls' and [d['field'] for d in body['defaults_applied']] == ['classification']
    # an existing classification is kept; a raise is applied
    inc2 = make_incident(severity='low', tlp='green', classification='existing')
    tpl2 = _create_tpl(admin, key='raise', definition=_defn(defaults={'severity': 'high', 'tlp': 'amber_strict',
                                                                       'classification': 'new'}))
    r = _apply(admin, inc2, tpl2['id'], apply_defaults=True).get_json()
    db.session.refresh(inc2)
    assert (inc2.severity, inc2.tlp, inc2.classification) == ('high', 'amber_strict', 'existing')
    assert {d['field'] for d in r['defaults_applied']} == {'severity', 'tlp'}


def test_dry_run_writes_nothing(admin, db, make_incident, rec):
    from app.models import IncidentCaseTemplate, IncidentPlaybook
    inc = make_incident(severity='low')
    tpl = _create_tpl(admin)
    before = len(rec.emits)
    r = _apply(admin, inc, tpl['id'], dry_run=True, apply_defaults=True)
    assert r.status_code == 200
    body = r.get_json()
    assert body['dry_run'] is True and body['created']['questions'] == 3 and body['created']['leads'] == 2
    assert body['playbook']['status'] == 'activated' and body['defaults_applied']
    assert not _questions(db, inc) and not _tasks(db, inc)
    assert IncidentCaseTemplate.query.filter_by(incident_id=inc.id).count() == 0
    assert IncidentPlaybook.query.filter_by(incident_id=inc.id).count() == 0
    db.session.refresh(inc)
    assert inc.severity == 'low'
    assert len(rec.emits) == before  # no realtime noise for a preview


def test_include_subset(admin, db, make_incident):
    inc = make_incident()
    tpl = _create_tpl(admin)
    body = _apply(admin, inc, tpl['id'], include=['questions']).get_json()
    assert body['created'] == {'questions': 3, 'leads': 0, 'links': 0} and body['playbook'] is None
    assert body['custom_fields_added'] == 0
    assert not _tasks(db, inc)


def test_run_auto_actions_only_when_asked(admin, db, make_incident, monkeypatch):
    from app.services.playbook_service import PlaybookService
    calls = []
    monkeypatch.setattr(PlaybookService, 'execute_action',
                        staticmethod(lambda incident, action, user: calls.append(action['key']) or {'status': 'success'}))
    pb = admin.post(f'{API}/playbooks', json={'name': 'Auto', 'definition': {'phases': [
        {'phase': 1, 'tasks': [{'title': 't'}], 'actions': [{'key': 'a1', 'type': 'suggest_mitre', 'auto_run': True}]}]}})
    pid = pb.get_json()['id']
    tpl = _create_tpl(admin, definition=_defn(playbook={'playbook_id': pid}))
    inc = make_incident()
    _apply(admin, inc, tpl['id'])
    assert calls == []
    inc2 = make_incident()
    r = _apply(admin, inc2, tpl['id'], run_auto_actions=True)
    assert calls == ['a1'] and r.get_json()['actions_executed'][0]['key'] == 'a1'


# ── create incident with a template ───────────────────────────────────────

def _create_incident(client, **body):
    body.setdefault('title', 'Ransomware at HQ')
    return client.post(f'{API}/incidents', json=body)


def test_create_incident_with_builtin_template(admin, db, rec):
    from app.models import IncidentCaseTemplate, IncidentPlaybook, Incident
    r = _create_incident(admin, case_template='builtin:ransomware')
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    assert body['severity'] == 'critical' and body['tlp'] == 'amber' and body['classification'] == 'ransomware'
    res = body['case_template_result']
    assert res['created']['questions'] == 20 and res['created']['leads'] == 6 and res['created']['links'] > 6
    assert res['playbook']['status'] == 'activated'
    assert {d['field'] for d in res['defaults_applied']} == {'severity', 'classification'}  # tlp already amber
    inc = db.session.get(Incident, uuid.UUID(body['id']))
    assert len(_questions(db, inc)) == 20 and len(_tasks(db, inc)) == 6
    assert IncidentPlaybook.query.filter_by(incident_id=inc.id).one().builtin_key == 'ransomware'
    assert IncidentCaseTemplate.query.filter_by(incident_id=inc.id).one().builtin_key == 'ransomware'
    defs = admin.get(f"{API}/incidents/{body['id']}/custom-fields").get_json()['definitions']
    assert [d['key'] for d in defs] == ['ransomware_family', 'ransom_note_observed', 'backups_impacted',
                                        'leak_site_listing']
    created = [e for e in rec.emits if e[0] == 'entity:changed' and e[1]['entity'] == 'incident']
    assert created and created[0][1]['op'] == 'created'
    assert {'questions'} in [set(r['scopes']) for r in rec.resyncs()]


def test_create_incident_explicit_fields_win(admin, db):
    r = _create_incident(admin, case_template='builtin:ransomware', severity='low', classification='mine', tlp='green')
    body = r.get_json()
    assert (body['severity'], body['tlp'], body['classification']) == ('low', 'green', 'mine')
    assert body['case_template_result']['defaults_applied'] == []
    assert body['case_template_result']['created']['questions'] == 20


def test_create_incident_with_org_template_and_viewer_lacking_tasks(admin, users, auth, db):
    tpl = _create_tpl(admin, definition=_defn(defaults={'severity': 'critical'}))
    r = _create_incident(admin, case_template=tpl['id'])
    assert r.status_code == 201 and r.get_json()['severity'] == 'critical'
    assert r.get_json()['case_template_result']['created']['leads'] == 2


def test_create_incident_bad_template_creates_nothing(admin, db):
    from app.models import Incident
    before = Incident.query.count()
    for ref in ('builtin:nope', str(uuid.uuid4()), 'garbage', 'builtin:../x'):
        r = _create_incident(admin, case_template=ref, title=f'Should not exist {ref[:8]}')
        assert r.status_code == 400, (ref, r.get_json())
    inactive = _create_tpl(admin, key='inactive-tpl', is_active=False)
    assert _create_incident(admin, case_template=inactive['id']).status_code == 400
    assert Incident.query.count() == before


def test_create_incident_rolls_back_on_failure(admin, db, monkeypatch):
    from app.models import Incident
    from app.services import case_template_service
    before = Incident.query.count()

    def boom(*a, **k):
        raise RuntimeError('boom')
    monkeypatch.setattr(case_template_service, 'apply', boom)
    r = _create_incident(admin, case_template='builtin:ransomware', title='Rolled back incident')
    assert r.status_code == 500
    db.session.rollback()
    assert Incident.query.count() == before


def test_create_incident_without_template_unchanged(admin):
    r = _create_incident(admin)
    assert r.status_code == 201 and 'case_template_result' not in r.get_json()
    assert r.get_json()['custom_fields'] == {}


# ── custom fields ─────────────────────────────────────────────────────────

def test_custom_fields_put_validation(admin, db, make_incident):
    inc = make_incident()
    url = f'{API}/incidents/{inc.id}/custom-fields'
    assert admin.get(url).get_json() == {'definitions': [], 'values': {}}
    assert admin.put(url, json={'values': {'ticket': 'x'}}).status_code == 400  # no definitions yet
    _apply(admin, inc, _create_tpl(admin)['id'])
    ok = admin.put(url, json={'values': {'ticket': 'INC-1', 'loss': 12.5, 'paid': False, 'seen': '2026-10-01',
                                         'stage': 'a'}})
    assert ok.status_code == 200
    assert ok.get_json()['values'] == {'ticket': 'INC-1', 'loss': 12.5, 'paid': False, 'seen': '2026-10-01',
                                       'stage': 'a'}
    assert len(ok.get_json()['definitions']) == 5
    for bad in ({'unknown': 1}, {'ticket': 5}, {'ticket': 'x' * 2001}, {'loss': 'many'}, {'loss': True},
                {'loss': []}, {'paid': 'yes'}, {'seen': '01/10/2026'},
                {'seen': '2026-13-45'}, {'stage': 'zzz'}, {'stage': None}):
        assert admin.put(url, json={'values': bad}).status_code == 400, bad
    assert admin.put(url, json={'values': 'x'}).status_code == 400
    assert admin.put(url, json={'nope': {}}).status_code == 400
    # null clears an optional key
    cleared = admin.put(url, json={'values': {'ticket': None}}).get_json()
    assert 'ticket' not in cleared['values'] and cleared['values']['loss'] == 12.5
    assert admin.get(f'{API}/incidents/{inc.id}').get_json()['custom_fields']['stage'] == 'a'


def test_custom_fields_permissions_and_first_definition_wins(users, auth, admin, make_incident):
    inc = make_incident(assign=[users['Viewer']])
    first = _create_tpl(admin, key='first', definition=_defn(custom_fields=[
        {'key': 'shared', 'label': 'First label', 'type': 'text'}]))
    second = _create_tpl(admin, key='second', definition=_defn(custom_fields=[
        {'key': 'shared', 'label': 'Second label', 'type': 'number'},
        {'key': 'extra', 'label': 'Extra', 'type': 'text'}]))
    _apply(admin, inc, first['id'])
    r = _apply(admin, inc, second['id']).get_json()
    assert r['custom_fields_added'] == 1
    url = f'{API}/incidents/{inc.id}/custom-fields'
    defs = admin.get(url).get_json()['definitions']
    assert [(d['key'], d['label']) for d in defs] == [('shared', 'First label'), ('extra', 'Extra')]
    viewer = auth(users['Viewer'])
    assert viewer.get(url).status_code == 200
    assert viewer.put(url, json={'values': {'shared': 'x'}}).status_code == 403
    assert auth(users['admin_b']).get(url).status_code == 404


def test_custom_fields_not_writable_through_incident_put(admin, make_incident):
    inc = make_incident()
    r = admin.put(f'{API}/incidents/{inc.id}', json={'custom_fields': {'x': 1}, 'title': 'Renamed incident'})
    assert r.status_code == 200
    assert admin.get(f'{API}/incidents/{inc.id}').get_json()['custom_fields'] == {}


# ── rate limit ────────────────────────────────────────────────────────────

_RATE_SCRIPT = """
import sys
import app.config as config
config.TestingConfig.RATELIMIT_ENABLED = True
from app import create_app, limiter
from app.models import User
application = create_app('testing')
with application.app_context():
    from app.api.v1.endpoints.auth import issue_tokens
    user = User.query.filter_by(email='administrator@a.test').one()
    token, _ = issue_tokens(user)
    limiter.reset()
    client = application.test_client()
    codes = [client.post('/api/v1/incidents/%s/case-templates/builtin:ransomware/apply' % sys.argv[1],
                         json={'dry_run': True}, headers={'Authorization': 'Bearer ' + token}).status_code
             for _ in range(21)]
    limiter.reset()
print(','.join(map(str, codes)))
"""


def test_apply_rate_limit_is_20_per_minute(app, make_incident):
    inc = make_incident()
    r = subprocess.run([sys.executable, '-c', _RATE_SCRIPT, str(inc.id)], cwd=BACKEND_DIR, capture_output=True,
                       text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-3000:]
    codes = r.stdout.strip().splitlines()[-1].split(',')
    assert codes[:20] == ['200'] * 20 and codes[20] == '429'


def test_apply_rate_limit_uses_its_group():
    # W4-RL: the literal limit became the configurable `template_apply` group.
    src = open(os.path.join(BACKEND_DIR, 'app', 'api', 'v1', 'endpoints', 'case_templates.py')).read()
    assert "@limited('template_apply')" in src


# ── built-in playbooks ────────────────────────────────────────────────────

def test_playbook_list_includes_builtins(admin):
    items = admin.get(f'{API}/playbooks').get_json()['items']
    ids = {i['id'] for i in items}
    assert {'builtin:picerl-generic', 'builtin:ransomware'} <= ids
    b = next(i for i in items if i['id'] == 'builtin:ransomware')
    assert b['is_builtin'] is True and b['builtin_key'] == 'ransomware' and b['definition']['phases']
    org_only = admin.get(f'{API}/playbooks?include_builtin=false').get_json()['items']
    assert not [i for i in org_only if i.get('is_builtin')]


def test_builtin_playbook_detail_clone_activate(admin, users, auth, db, make_incident):
    from app.models import IncidentPlaybook, Playbook
    d = admin.get(f'{API}/playbooks/builtin/ransomware')
    assert d.status_code == 200 and d.get_json()['metadata']['framework']
    assert admin.get(f'{API}/playbooks/builtin/nope').status_code == 404
    assert admin.get(f'{API}/playbooks/builtin/..%2Fx').status_code == 404

    clone = admin.post(f'{API}/playbooks/builtin/ransomware/clone')
    assert clone.status_code == 201
    cb = clone.get_json()
    assert cb['cloned_from'] == 'builtin:ransomware' and cb['is_builtin'] is False and cb['definition']['phases']
    assert admin.put(f"{API}/playbooks/{cb['id']}", json={'name': 'Edited'}).status_code == 200
    assert auth(users['Analyst']).post(f'{API}/playbooks/builtin/ransomware/clone').status_code == 403

    inc = make_incident(assign=[users['Analyst']])
    r = auth(users['Analyst']).post(f'{API}/incidents/{inc.id}/playbooks/builtin/ransomware/activate')
    assert r.status_code == 201
    inst = r.get_json()['incident_playbook']
    assert inst['builtin_key'] == 'ransomware' and inst['playbook_id'] is None and inst['name'] == 'Ransomware response'
    assert r.get_json()['actions_executed'] == []
    assert IncidentPlaybook.query.filter_by(incident_id=inc.id).count() == 1
    assert admin.get(f'{API}/incidents/{inc.id}/playbook').get_json()['incident_playbook']['builtin_key'] == 'ransomware'
    assert auth(users['Viewer']).post(f'{API}/incidents/{inc.id}/playbooks/builtin/ransomware/activate').status_code == 403
    assert admin.post(f'{API}/incidents/{inc.id}/playbooks/builtin/nope/activate').status_code == 404
    assert Playbook.query.filter_by(cloned_from='builtin:ransomware').count() >= 1


def test_playbook_definition_caps(admin):
    def post(definition):
        return admin.post(f'{API}/playbooks', json={'name': 'x', 'definition': definition})

    ok = {'phases': [{'phase': 1, 'tasks': [{'title': 't'}] * 50}]}
    assert post(ok).status_code == 201
    assert post({'phases': [{'phase': 1, 'tasks': [{'title': 't'}] * 51}]}).status_code == 400
    assert post({'phases': [{'phase': 1, 'actions': [
        {'key': f'k{i}', 'type': 'suggest_mitre'} for i in range(21)]}]}).status_code == 400
    assert post({'phases': [{'phase': 1}, {'phase': 1}]}).status_code == 400            # duplicate phase
    assert post({'phases': [{'phase': 1, 'tasks': [{'owner_role': 'x'}]}]}).status_code == 400  # no title
    assert post({'phases': [{'phase': 1, 'tasks': [{'title': 'x' * 501}]}]}).status_code == 400
    for cfg in (None, {}, {'title': ''}, {'title': 't', 'priority': 'urgent'}, {'title': 't', 'phase': 9},
                {'title': 't', 'task_type': 'nope'}):
        action = {'key': 'c', 'type': 'create_task'}
        if cfg is not None:
            action['config'] = cfg
        assert post({'phases': [{'phase': 1, 'actions': [action]}]}).status_code == 400, cfg
    good = {'phases': [{'phase': 1, 'actions': [{'key': 'c', 'type': 'create_task',
                                                 'config': {'title': 'Collect memory', 'priority': 'high'}}]}]}
    assert post(good).status_code == 201
    big = {'name': 'x', 'description': 'd' * (300 * 1024), 'definition': {}}
    assert admin.post(f'{API}/playbooks', json=big).status_code == 400
    assert admin.post(f'{API}/playbooks', json={'name': 'n' * 256}).status_code == 400


# ── built-in activation per organization ───────────────────────────────────

@pytest.fixture
def _restore_builtins(app, db, users):
    yield
    from app.models import Organization
    org = db.session.get(Organization, users['Administrator'].organization_id)
    settings = dict(org.settings or {})
    settings.pop('disabled_builtin_templates', None)
    org.settings = settings
    db.session.commit()


def test_builtin_can_be_deactivated_per_org_only(admin, users, auth, make_incident, _restore_builtins):
    url = f'{API}/case-templates/builtin:ransomware'
    assert admin.put(url, json={'name': 'Renamed'}).status_code == 403  # still read-only
    assert auth(users['Analyst']).put(url, json={'is_active': False}).status_code == 403

    r = admin.put(url, json={'is_active': False})
    assert r.status_code == 200 and r.get_json()['is_active'] is False
    keys = [t['id'] for t in admin.get(f'{API}/case-templates').get_json()['items']]
    assert 'builtin:ransomware' not in keys and 'builtin:generic-intrusion' in keys
    listed = admin.get(f'{API}/case-templates?include_inactive=true').get_json()['items']
    assert next(t for t in listed if t['id'] == 'builtin:ransomware')['is_active'] is False

    inc = make_incident()
    r = _apply(admin, inc, 'builtin:ransomware')
    assert r.status_code == 409 and r.get_json()['error'] == 'template_inactive'

    assert admin.put(url, json={'is_active': True}).get_json()['is_active'] is True
    assert _apply(admin, inc, 'builtin:ransomware', dry_run=True).status_code == 200


def test_builtin_deactivation_is_audited_and_survives_org_update(admin, users, db, _restore_builtins):
    from app.models import AuditLog, Organization
    assert admin.put(f'{API}/case-templates/builtin:generic-intrusion', json={'is_active': False}).status_code == 200
    row = AuditLog.query.filter_by(action='update', resource_type='case_template').order_by(
        AuditLog.created_at.desc()).first()
    assert row.details['changes']['is_active'] == {'from': True, 'to': False}
    # A normal organization settings update keeps the list.
    assert admin.put(f'{API}/organization', json={'settings': {'auto_enrich_iocs': False}}).status_code == 200
    org = db.session.get(Organization, users['Administrator'].organization_id)
    db.session.refresh(org)
    assert 'generic-intrusion' in org.settings['disabled_builtin_templates']
