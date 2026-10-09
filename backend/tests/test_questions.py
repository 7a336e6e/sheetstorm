"""W3-QST-BE: investigative questions API (CRUD, transitions, evidence, leads,
library, cross-incident queue, report data, audit and realtime)."""
import uuid

import pytest

from app.services import realtime

API = '/api/v1'


class Recorder:
    def __init__(self):
        self.emits = []

    def emit(self, event, data=None, to=None, **kw):
        self.emits.append((event, data, to))

    def changes(self, entity=None):
        return [d for e, d, _ in self.emits if e == 'entity:changed' and (entity is None or d['entity'] == entity)]

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


@pytest.fixture
def inc(make_incident):
    return make_incident()


def _qs(inc):
    return f'{API}/incidents/{inc.id}/questions'


def _make(client, inc, **body):
    body.setdefault('question', 'Which accounts were used for lateral movement?')
    resp = client.post(_qs(inc), json=body)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _host(db, inc, users, name='WS-01'):
    from app.models import CompromisedHost
    h = CompromisedHost(incident_id=inc.id, hostname=name, created_by=users['Administrator'].id)
    db.session.add(h)
    db.session.commit()
    return h


def _task(db, inc, users, title='Review VPN logs'):
    from app.models import Task
    t = Task(incident_id=inc.id, title=title, task_type='investigative_lead', created_by=users['Administrator'].id)
    db.session.add(t)
    db.session.commit()
    return t


# ── CRUD and access ───────────────────────────────────────────────────────

def test_create_get_list_update_archive(admin, inc):
    q = _make(admin, inc, description='ctx', facet='Accounts', phase=2, priority='high')
    assert q['status'] == 'open' and q['source'] == 'manual' and q['lead_ids'] == [] and q['evidence'] == []
    assert q['version'] == 1 and q['phase'] == 2 and q['priority'] == 'high'

    got = admin.get(f"{_qs(inc)}/{q['id']}")
    assert got.status_code == 200 and got.headers['ETag'] == '"1"'

    body = admin.get(_qs(inc)).get_json()
    assert body['total'] == 1 and body['items'][0]['id'] == q['id']
    assert body['summary']['total'] == 1 and body['summary']['open'] == 1

    upd = admin.put(f"{_qs(inc)}/{q['id']}", json={'status': 'in_progress', 'priority': 'critical'})
    assert upd.status_code == 200 and upd.get_json()['version'] == 2
    assert admin.get(_qs(inc)).get_json()['summary']['in_progress'] == 1

    assert admin.delete(f"{_qs(inc)}/{q['id']}").status_code == 200
    assert admin.get(_qs(inc)).get_json()['total'] == 0
    assert admin.get(_qs(inc) + '?include_archived=true').get_json()['total'] == 1
    assert admin.get(f"{_qs(inc)}/{q['id']}").status_code == 200  # still addressable


def test_validation_errors(admin, inc):
    for body in ({}, {'question': ''}, {'question': 'x' * 1001}, {'question': 'ok question', 'priority': 'urgent'},
                 {'question': 'ok question', 'phase': 7}, {'question': 'ok question', 'phase': True},
                 {'question': 'ok question', 'library_ref': 'ss:NOPE'}):
        assert admin.post(_qs(inc), json=body).status_code == 400, body
    assert admin.post(_qs(inc), data='[]', content_type='application/json').status_code == 400
    q = _make(admin, inc)
    for body in ({'status': 'done'}, {'confidence': 'sure'}, {'bogus': 1}, {'answer': 'a' * 20001},
                 {'order_index': 'x'}, {'question': ''}):
        assert admin.put(f"{_qs(inc)}/{q['id']}", json=body).status_code == 400, body


def test_permissions_viewer_read_only(users, auth, make_incident):
    inc = make_incident(assign=[users['Viewer'], users['Analyst']])
    admin = auth(users['Administrator'])
    q = _make(admin, inc)
    viewer = auth(users['Viewer'])
    assert viewer.get(_qs(inc)).status_code == 200
    assert viewer.get(f"{_qs(inc)}/{q['id']}").status_code == 200
    assert viewer.post(_qs(inc), json={'question': 'Anything new here?'}).status_code == 403
    assert viewer.put(f"{_qs(inc)}/{q['id']}", json={'status': 'in_progress'}).status_code == 403
    assert viewer.delete(f"{_qs(inc)}/{q['id']}").status_code == 403
    assert viewer.put(f"{_qs(inc)}/{q['id']}/leads", json={'task_ids': []}).status_code == 403
    assert viewer.post(f'{_qs(inc)}/bulk', json={'refs': ['ss:SSQ-001']}).status_code == 403
    assert auth(users['Analyst']).put(f"{_qs(inc)}/{q['id']}", json={'status': 'in_progress'}).status_code == 200


def test_other_org_gets_404(users, auth, inc, admin):
    q = _make(admin, inc)
    other = auth(users['admin_b'])
    assert other.get(_qs(inc)).status_code == 404
    assert other.get(f"{_qs(inc)}/{q['id']}").status_code == 404
    assert other.post(_qs(inc), json={'question': 'Smuggled in from org B?'}).status_code == 404
    assert other.put(f"{_qs(inc)}/{q['id']}", json={'status': 'in_progress'}).status_code == 404
    assert other.get(f'{_qs(inc)}/report-data').status_code == 404


def test_question_of_another_incident_is_404(admin, make_incident):
    a, b = make_incident(), make_incident()
    q = _make(admin, a)
    assert admin.get(f"{_qs(b)}/{q['id']}").status_code == 404
    assert admin.put(f"{_qs(b)}/{q['id']}", json={'status': 'in_progress'}).status_code == 404
    assert admin.delete(f"{_qs(b)}/{q['id']}").status_code == 404


def test_filters_sort_and_search(admin, inc):
    _make(admin, inc, question='Alpha question about persistence?', phase=2, priority='low')
    b = _make(admin, inc, question='Beta question about exfiltration?', phase=3, priority='critical')
    admin.put(f"{_qs(inc)}/{b['id']}", json={'status': 'in_progress'})
    assert admin.get(_qs(inc) + '?status=in_progress').get_json()['total'] == 1
    assert admin.get(_qs(inc) + '?status=open,in_progress').get_json()['total'] == 2
    assert admin.get(_qs(inc) + '?status=bogus').status_code == 400
    assert admin.get(_qs(inc) + '?phase=3').get_json()['total'] == 1
    assert admin.get(_qs(inc) + '?q=exfiltration').get_json()['total'] == 1
    assert [i['priority'] for i in admin.get(_qs(inc) + '?sort=-priority').get_json()['items']] == ['critical', 'low']
    assert admin.get(_qs(inc) + '?sort=nonsense').status_code == 400
    assert admin.get(_qs(inc) + '?owner=me').get_json()['total'] == 0
    assert admin.get(_qs(inc) + '?owner=someone').status_code == 400


# ── transitions ───────────────────────────────────────────────────────────

def test_answer_transitions(admin, inc, users):
    q = _make(admin, inc)
    url = f"{_qs(inc)}/{q['id']}"
    r = admin.put(url, json={'status': 'answered'})
    assert r.status_code == 400 and r.get_json()['error'] == 'answer_required'
    r = admin.put(url, json={'status': 'answered', 'answer': 'svc_backup via RDP'})
    assert r.status_code == 400 and r.get_json()['error'] == 'confidence_required'
    ok = admin.put(url, json={'status': 'answered', 'answer': 'svc_backup via RDP', 'confidence': 'high'})
    assert ok.status_code == 200
    body = ok.get_json()
    assert body['answered_at'] and body['answered_by_user']['id'] == str(users['Administrator'].id)
    assert body['answer'] == 'svc_backup via RDP'

    # confirmed needs evidence
    r = admin.put(url, json={'confidence': 'confirmed'})
    assert r.status_code == 400 and r.get_json()['error'] == 'evidence_required'

    # reopening keeps the text, clears who/when
    re_open = admin.put(url, json={'status': 'open'}).get_json()
    assert re_open['answered_at'] is None and re_open['answered_by'] is None
    assert re_open['answer'] == 'svc_backup via RDP' and re_open['status'] == 'open'

    # unanswerable needs a rationale
    q2 = _make(admin, inc, question='Was the VPN logged by the appliance?')
    u2 = f"{_qs(inc)}/{q2['id']}"
    assert admin.put(u2, json={'status': 'unanswerable'}).get_json()['error'] == 'answer_required'
    done = admin.put(u2, json={'status': 'unanswerable', 'answer': 'Logs were rotated after 7 days.'})
    assert done.status_code == 200 and done.get_json()['answered_at']
    s = admin.get(_qs(inc)).get_json()['summary']
    assert s['unanswerable'] == 1 and s['resolved'] == 1 and s['open'] == 1 and s['progress'] == 0.5


def test_confirmed_with_evidence_and_foreign_evidence(admin, db, users, inc, make_incident):
    host = _host(db, inc, users)
    foreign = _host(db, make_incident(), users, 'OTHER')
    q = _make(admin, inc)
    url = f"{_qs(inc)}/{q['id']}"
    bad = admin.put(url, json={'evidence_refs': [{'evidence_type': 'host', 'evidence_id': str(foreign.id)}]})
    assert bad.status_code == 400 and bad.get_json()['error'] == 'invalid_evidence_refs'
    assert bad.get_json()['invalid'][0]['reason'] == 'not_found'
    unknown = admin.put(url, json={'evidence_refs': [{'evidence_type': 'unicorn', 'evidence_id': str(host.id)}]})
    assert unknown.status_code == 400
    not_allowed = admin.put(url, json={'evidence_refs': [{'evidence_type': 'question', 'evidence_id': q['id']}]})
    assert not_allowed.status_code == 400  # a question cannot cite questions
    ok = admin.put(url, json={'status': 'answered', 'answer': 'Patient zero was WS-01', 'confidence': 'confirmed',
                              'evidence_refs': [{'evidence_type': 'host', 'evidence_id': str(host.id)},
                                                {'evidence_type': 'host', 'evidence_id': str(host.id)}]})
    assert ok.status_code == 200, ok.get_json()
    body = ok.get_json()
    assert body['evidence_refs'] == [{'evidence_type': 'host', 'evidence_id': str(host.id)}]
    assert body['evidence'][0]['label'] == 'WS-01' and body['evidence'][0]['missing'] is False
    # a cited record that is deleted later does not block editing the question
    db.session.delete(host)
    db.session.commit()
    again = admin.put(url, json={'priority': 'low', 'evidence_refs': body['evidence_refs']})
    assert again.status_code == 200
    assert again.get_json()['evidence'][0]['missing'] is True


def test_evidence_labels_respect_read_permissions(admin, db, users, auth, make_incident):
    inc = make_incident(assign=[users['Analyst']])
    host = _host(db, inc, users)
    q = _make(admin, inc)
    admin.put(f"{_qs(inc)}/{q['id']}", json={'evidence_refs': [{'evidence_type': 'host', 'evidence_id': str(host.id)}]})
    ok = auth(users['Analyst']).get(f"{_qs(inc)}/{q['id']}").get_json()
    assert ok['evidence'][0]['label'] == 'WS-01'


def test_owner_validation(admin, db, users, org_b, inc, make_user):
    q = _make(admin, inc)
    url = f"{_qs(inc)}/{q['id']}"
    r = admin.put(url, json={'owner_id': str(users['admin_b'].id)})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_owner'
    assert admin.put(url, json={'owner_id': 'nope'}).status_code == 400
    # operator is in the org but cannot see an unassigned incident
    assert admin.put(url, json={'owner_id': str(users['Operator'].id)}).status_code == 400
    ok = admin.put(url, json={'owner_id': str(users['Analyst'].id)})
    assert ok.status_code == 200 and ok.get_json()['owner']['id'] == str(users['Analyst'].id)
    assert admin.get(_qs(inc) + f"?owner_id={users['Analyst'].id}").get_json()['total'] == 1
    assert admin.put(url, json={'owner_id': None}).get_json()['owner'] is None


def test_concurrency_if_match(admin, inc):
    q = _make(admin, inc)
    url = f"{_qs(inc)}/{q['id']}"
    assert admin.put(url, json={'priority': 'low'}, headers={'If-Match': '"1"'}).status_code == 200
    stale = admin.put(url, json={'priority': 'high'}, headers={'If-Match': '"1"'})
    assert stale.status_code == 409 and stale.get_json()['error'] == 'conflict'
    assert stale.get_json()['current']['priority'] == 'low'
    assert admin.put(url, json={'priority': 'high', 'expected_version': 2}).status_code == 200


# ── library ───────────────────────────────────────────────────────────────

def test_library_endpoints(admin):
    tree = admin.get(f'{API}/questions/library').get_json()
    assert tree['total'] >= 37 and tree['sources'][0]['key'] == 'core'
    core = tree['groups'][0]
    assert core['facets'][0]['questions'][0]['ref'].startswith('ss:SSQ-')
    one = admin.get(f'{API}/questions/library/ss:SSQ-001')
    assert one.status_code == 200 and one.get_json()['ref'] == 'ss:SSQ-001' and 'guidance' in one.get_json()
    assert admin.get(f'{API}/questions/library/ss:SSQ-999').status_code == 404


def test_add_from_library_and_duplicate(admin, inc):
    q = _make(admin, inc, library_ref='ss:SSQ-006', priority='critical')
    assert q['source'] == 'core' and q['source_ref'] == q['dedupe_key'] == 'ss:SSQ-006'
    assert q['question'].startswith('Which accounts') and q['priority'] == 'critical'
    dup = admin.post(_qs(inc), json={'library_ref': 'ss:SSQ-006'})
    assert dup.status_code == 409 and dup.get_json()['error'] == 'duplicate_question'
    assert dup.get_json()['existing_id'] == q['id']
    # same text typed by hand is a duplicate too (case and spaces ignored)
    same_text = admin.post(_qs(inc), json={'question': '  WHICH accounts   were used or compromised? '})
    assert same_text.status_code == 409
    # an archived library question is not resurrected
    admin.delete(f"{_qs(inc)}/{q['id']}")
    assert admin.post(_qs(inc), json={'library_ref': 'ss:SSQ-006'}).status_code == 409


def test_bulk_merge(admin, inc):
    _make(admin, inc, library_ref='ss:SSQ-001')
    r = admin.post(f'{_qs(inc)}/bulk', json={'refs': ['ss:SSQ-001', 'ss:SSQ-002', 'ss:SSQ-003', 'ss:SSQ-002']})
    assert r.status_code == 201
    body = r.get_json()
    assert [q['source_ref'] for q in body['created']] == ['ss:SSQ-002', 'ss:SSQ-003']
    assert body['skipped'] == [{'ref': 'ss:SSQ-001', 'reason': 'exists', 'existing_id': body['skipped'][0]['existing_id']}]
    assert admin.get(_qs(inc)).get_json()['total'] == 3
    again = admin.post(f'{_qs(inc)}/bulk', json={'refs': ['ss:SSQ-001', 'ss:SSQ-002']}).get_json()
    assert again['created'] == [] and len(again['skipped']) == 2
    assert admin.post(f'{_qs(inc)}/bulk', json={'refs': ['ss:SSQ-001', 'ss:BAD']}).status_code == 400
    assert admin.post(f'{_qs(inc)}/bulk', json={'refs': []}).status_code == 400
    assert admin.post(f'{_qs(inc)}/bulk', json={'refs': ['ss:SSQ-001'] * 2 + [f'ss:SSQ-{i:03d}' for i in range(1, 38)] * 3}
                      ).status_code == 400  # >100 refs


# ── leads ─────────────────────────────────────────────────────────────────

def test_leads_link_unlink_and_cross_incident(admin, db, users, inc, make_incident):
    q = _make(admin, inc)
    t1, t2 = _task(db, inc, users, 'Lead one'), _task(db, inc, users, 'Lead two')
    foreign = _task(db, make_incident(), users, 'Foreign lead')
    url = f"{_qs(inc)}/{q['id']}/leads"
    r = admin.put(url, json={'task_ids': [str(t1.id), str(t2.id), str(t1.id)]})
    assert r.status_code == 200 and sorted(r.get_json()['lead_ids']) == sorted([str(t1.id), str(t2.id)])
    bad = admin.put(url, json={'task_ids': [str(foreign.id)]})
    assert bad.status_code == 400 and bad.get_json()['error'] == 'invalid_leads'
    assert admin.put(url, json={'task_ids': ['nope']}).status_code == 400
    assert admin.put(url, json={'task_ids': 'x'}).status_code == 400
    # failed attempts changed nothing
    assert len(admin.get(f"{_qs(inc)}/{q['id']}").get_json()['lead_ids']) == 2
    links = admin.get(f'{API}/incidents/{inc.id}/question-links').get_json()
    assert links['total'] == 2 and {l['task_id'] for l in links['items']} == {str(t1.id), str(t2.id)}
    assert admin.get(_qs(inc) + f'?task_id={t1.id}').get_json()['total'] == 1
    assert admin.get(_qs(inc) + f'?task_id={foreign.id}').get_json()['total'] == 0
    only = admin.put(url, json={'task_ids': [str(t2.id)]}).get_json()
    assert only['lead_ids'] == [str(t2.id)]
    # deleting the task removes the link
    from app.models import QuestionLead
    db.session.delete(t2)
    db.session.commit()
    assert QuestionLead.query.filter_by(question_id=uuid.UUID(q['id'])).count() == 0


# ── cross-incident queue ──────────────────────────────────────────────────

def test_cross_incident_queue_respects_visibility(users, auth, make_incident, db):
    admin = auth(users['Administrator'])
    visible = make_incident(assign=[users['Operator']])
    hidden = make_incident()  # Operator is not assigned and has no read scope
    mine = _make(admin, visible, question='Visible question for the operator?')
    _make(admin, hidden, question='Hidden question for the operator?')
    admin.put(f"{_qs(visible)}/{mine['id']}", json={'owner_id': str(users['Operator'].id)})

    op = auth(users['Operator'])
    items = op.get(f'{API}/questions?q=for the operator').get_json()['items']
    texts = {i['question'] for i in items}
    assert 'Visible question for the operator?' in texts and 'Hidden question for the operator?' not in texts
    assert all(i['incident']['id'] for i in items)
    assert op.get(f'{API}/questions?owner=me').get_json()['total'] == 1
    assert op.get(f'{API}/questions?incident_id={hidden.id}').get_json()['total'] == 0

    all_items = admin.get(f'{API}/questions?status=open&q=for the operator').get_json()
    assert {'Visible question for the operator?', 'Hidden question for the operator?'} <= {i['question'] for i in all_items['items']}
    # org B sees none of org A's questions
    assert auth(users['admin_b']).get(f'{API}/questions?q=for the operator').get_json()['total'] == 0


# ── report data ───────────────────────────────────────────────────────────

def test_report_data_shape_and_attribution(admin, db, users, inc):
    from app.models import InvestigativeQuestion
    host = _host(db, inc, users)
    t = _task(db, inc, users, 'Hunt WS-01')
    a = _make(admin, inc, library_ref='ss:SSQ-008')
    b = _make(admin, inc, question='Was a decryptor available for this strain?', phase=5)
    _make(admin, inc, question='Anything else we should chase today?', phase=3)
    admin.put(f"{_qs(inc)}/{a['id']}", json={'status': 'answered', 'answer': 'WS-01 only', 'confidence': 'high',
                                              'evidence_refs': [{'evidence_type': 'host', 'evidence_id': str(host.id)}]})
    admin.put(f"{_qs(inc)}/{a['id']}/leads", json={'task_ids': [str(t.id)]})
    admin.put(f"{_qs(inc)}/{b['id']}", json={'status': 'unanswerable', 'answer': 'No public decryptor.'})
    data = admin.get(f'{_qs(inc)}/report-data').get_json()
    assert data['incident_id'] == str(inc.id) and data['summary']['total'] == 3
    assert [q['id'] for q in data['answered']] == [a['id']] and [q['id'] for q in data['unanswerable']] == [b['id']]
    assert len(data['open']) == 1
    ans = data['answered'][0]
    assert ans['evidence'][0]['label'] == 'WS-01' and ans['leads'][0]['title'] == 'Hunt WS-01'
    assert ans['answered_by']['name'] and 'attribution' not in data
    # phase order: 2 (answered, ss:SSQ-008 default phase 2), 3, 5
    assert [q['phase'] for q in data['questions']] == [2, 3, 5]
    # a DFIQ-sourced question adds the attribution line
    row = InvestigativeQuestion(incident_id=inc.id, question='Was data uploaded to personal cloud storage?',
                                source='dfiq', source_ref='dfiq:Q1001', dedupe_key='dfiq:Q1001',
                                created_by=users['Administrator'].id)
    db.session.add(row)
    db.session.commit()
    assert 'DFIQ' in admin.get(f'{_qs(inc)}/report-data').get_json()['attribution']


# ── audit and realtime ────────────────────────────────────────────────────

def test_audit_rows_and_changes(admin, db, inc):
    from app.models import AuditLog
    q = _make(admin, inc)
    admin.put(f"{_qs(inc)}/{q['id']}", json={'priority': 'critical'})
    admin.put(f"{_qs(inc)}/{q['id']}/leads", json={'task_ids': []})
    admin.delete(f"{_qs(inc)}/{q['id']}")
    rows = AuditLog.query.filter_by(incident_id=inc.id, resource_type='question').all()
    assert {r.action for r in rows} >= {'create', 'update', 'set_leads', 'archive'}
    update = next(r for r in rows if r.action == 'update')
    assert update.details['changes']['priority'] == {'from': 'medium', 'to': 'critical'}


def test_realtime_emits_after_commit(admin, rec, inc):
    q = _make(admin, inc)
    admin.put(f"{_qs(inc)}/{q['id']}", json={'status': 'in_progress'})
    admin.delete(f"{_qs(inc)}/{q['id']}")
    ops = [(c['op'], c['scope']) for c in rec.changes('question')]
    assert ops == [('created', 'questions'), ('updated', 'questions'), ('deleted', 'questions')]
    created = rec.changes('question')[0]
    assert created['data']['question'] and all(e['label'] is None for e in created['data']['evidence'])
    admin.post(f'{_qs(inc)}/bulk', json={'refs': ['ss:SSQ-001']})
    assert any(r['scopes'] == ['questions'] for r in rec.resyncs())
    # failed writes emit nothing
    before = len(rec.emits)
    assert admin.put(f"{_qs(inc)}/{q['id']}", json={'status': 'done'}).status_code == 400
    assert len(rec.emits) == before


def test_question_ref_type_is_registered(admin, inc):
    from app.services.evidence_refs import canonical_type, validate_refs
    q = _make(admin, inc)
    assert canonical_type('question') == 'question'
    assert validate_refs(inc.id, [{'evidence_type': 'question', 'evidence_id': q['id']}]) == [
        {'evidence_type': 'question', 'evidence_id': q['id']}]
    other = inc.__class__.query.filter(inc.__class__.id != inc.id).first()
    from app.services.evidence_refs import EvidenceRefsError
    with pytest.raises(EvidenceRefsError):
        validate_refs(other.id, [{'evidence_type': 'question', 'evidence_id': q['id']}])
    assert realtime.scope_for_entity('question') == 'questions'


def test_incident_delete_cascades(admin, db, inc):
    from app.models import InvestigativeQuestion
    q = _make(admin, inc)
    assert InvestigativeQuestion.query.filter_by(incident_id=inc.id).count() == 1
    db.session.delete(db.session.get(inc.__class__, inc.id))
    db.session.commit()
    assert db.session.get(InvestigativeQuestion, uuid.UUID(q['id'])) is None
