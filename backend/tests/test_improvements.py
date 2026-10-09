"""W3-RT-POST: after-action review and improvement actions (CRUD, RBAC,
org-wide listing, survival of a permanent incident delete, realtime)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services import realtime

API = '/api/v1'


class Recorder:
    server = None

    def __init__(self):
        self.emits = []

    def emit(self, event, data=None, to=None, **kw):
        self.emits.append((event, data, to))

    def changes(self, entity):
        return [d for e, d, _ in self.emits if e == 'entity:changed' and d['entity'] == entity]


@pytest.fixture
def rt(app):
    rec = Recorder()
    realtime.set_emitter(rec)
    yield rec
    realtime.set_emitter(None)


@pytest.fixture
def team(app, db, make_user, make_incident):
    """A fresh org with one user per relevant role and an incident everyone on the team may open."""
    from app.models import Organization
    org = Organization(name='aar', slug=f'aar-{uuid.uuid4().hex[:8]}', settings={})
    db.session.add(org)
    db.session.commit()
    u = {r: make_user(org, roles=[r]) for r in ('Administrator', 'Incident Responder', 'Analyst', 'Manager',
                                                'Operator', 'Viewer')}
    inc = make_incident(org=org, creator=u['Administrator'], title='Ransom case',
                        assign=[u['Analyst'], u['Operator']], incident_number=77)
    return {'org': org, 'u': u, 'inc': inc}


def _put_review(c, inc, **body):
    return c.put(f'{API}/incidents/{inc.id}/review', json=body)


def _post_action(c, inc, **body):
    body.setdefault('title', 'Enable MFA on VPN')
    return c.post(f'{API}/incidents/{inc.id}/improvement-actions', json=body)


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

def test_review_is_null_until_created_and_exposes_legacy_notes(auth, db, team):
    team['inc'].lessons_learned = 'old free text'
    db.session.commit()
    body = auth(team['u']['Analyst']).get(f"{API}/incidents/{team['inc'].id}/review").get_json()
    assert body['review'] is None and body['legacy_lessons_learned'] == 'old free text'
    assert body['can_manage'] is False
    assert auth(team['u']['Manager']).get(f"{API}/incidents/{team['inc'].id}/review").get_json()['can_manage'] is True


def test_review_upsert_and_partial_update(auth, team, rt):
    inc, c = team['inc'], auth(team['u']['Analyst'])
    resp = _put_review(c, inc, what_went_well='fast triage', root_cause='no MFA',
                       contributing_factors=[{'category': 'technology', 'description': ' VPN had no MFA '}],
                       detection_source='threat_hunt', review_date='2026-03-20',
                       participants=[str(team['u']['Analyst'].id)])
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body['status'] == 'draft' and body['version'] == 1
    assert body['contributing_factors'] == [{'category': 'technology', 'description': 'VPN had no MFA'}]
    assert body['review_date'] == '2026-03-20' and body['detection_source'] == 'threat_hunt'
    assert [p['id'] for p in body['participant_users']] == [str(team['u']['Analyst'].id)]
    assert resp.headers['ETag'] == '"1"'
    [env] = rt.changes('review')
    assert env['op'] == 'created' and env['scope'] == 'review' and env['data']['root_cause'] == 'no MFA'

    resp = _put_review(c, inc, what_went_wrong='slow containment')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['what_went_well'] == 'fast triage' and body['what_went_wrong'] == 'slow containment'  # untouched kept
    assert body['version'] == 2 and rt.changes('review')[-1]['op'] == 'updated'
    got = c.get(f'{API}/incidents/{inc.id}/review').get_json()['review']
    assert got['version'] == 2 and got['root_cause'] == 'no MFA'


@pytest.mark.parametrize('body', [
    {'contributing_factors': [{'category': 'weather', 'description': 'x'}]},
    {'contributing_factors': [{'category': 'people', 'description': ''}]},
    {'detection_source': 'psychic'},
    {'review_date': 'not-a-date'},
    {'status': 'archived'},
    {'what_went_well': 'x' * 20001},
])
def test_review_validation(auth, team, body):
    resp = _put_review(auth(team['u']['Analyst']), team['inc'], **body)
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()['error'] == 'validation_error'


def test_review_participants_must_be_same_org(auth, team, users):
    resp = _put_review(auth(team['u']['Analyst']), team['inc'], participants=[str(users['admin_b'].id)])
    assert resp.status_code == 400 and resp.get_json()['error'] == 'invalid_participants'


def test_review_stale_if_match_is_409(auth, team):
    c, inc = auth(team['u']['Analyst']), team['inc']
    _put_review(c, inc, root_cause='a')
    stale = c.put(f'{API}/incidents/{inc.id}/review', json={'root_cause': 'b'}, headers={'If-Match': '"7"'})
    assert stale.status_code == 409
    assert stale.get_json()['error'] == 'conflict' and stale.get_json()['current_version'] == 1
    assert stale.get_json()['current']['root_cause'] == 'a'
    ok = c.put(f'{API}/incidents/{inc.id}/review', json={'root_cause': 'b', 'expected_version': 1})
    assert ok.status_code == 200 and ok.get_json()['root_cause'] == 'b'


def test_finalize_requires_the_manager_tier_and_locks_the_review(auth, team):
    inc = team['inc']
    analyst, responder = auth(team['u']['Analyst']), auth(team['u']['Incident Responder'])
    _put_review(analyst, inc, root_cause='draft')
    resp = _put_review(analyst, inc, status='final')
    assert resp.status_code == 403 and resp.get_json()['error'] == 'forbidden'
    resp = _put_review(responder, inc, status='final')
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['status'] == 'final' and body['finalized_at'] and body['finalized_by'] == str(team['u']['Incident Responder'].id)
    # an analyst can no longer edit it
    locked = _put_review(analyst, inc, root_cause='tamper')
    assert locked.status_code == 403 and locked.get_json()['error'] == 'review_finalized'
    # the responder can edit and reopen it
    assert _put_review(responder, inc, root_cause='fixed').status_code == 200
    reopened = _put_review(responder, inc, status='draft').get_json()
    assert reopened['status'] == 'draft' and reopened['finalized_at'] is None and reopened['finalized_by'] is None


def test_review_cannot_be_created_final_without_the_manager_tier(auth, team):
    assert _put_review(auth(team['u']['Analyst']), team['inc'], status='final').status_code == 403
    resp = _put_review(auth(team['u']['Incident Responder']), team['inc'], status='final', root_cause='done')
    assert resp.status_code == 201 and resp.get_json()['status'] == 'final'


def test_review_authorization(auth, team, users, make_incident):
    inc = team['inc']
    assert _put_review(auth(team['u']['Viewer']), inc, root_cause='x').status_code == 403
    assert _put_review(auth(team['u']['Operator']), inc, root_cause='x').status_code == 403   # no incidents:update
    assert _put_review(auth(users['admin_b']), inc, root_cause='x').status_code == 404        # other org
    assert auth(users['admin_b']).get(f'{API}/incidents/{inc.id}/review').status_code == 404
    unassigned = make_incident(org=team['org'], creator=team['u']['Administrator'])
    assert auth(team['u']['Operator']).get(f'{API}/incidents/{unassigned.id}/review').status_code == 403


def test_review_audit_row_records_the_diff(auth, db, team):
    from app.models import AuditLog
    c, inc = auth(team['u']['Analyst']), team['inc']
    _put_review(c, inc, root_cause='first')
    _put_review(c, inc, root_cause='second')
    rows = AuditLog.query.filter_by(resource_type='incident_review', incident_id=inc.id).order_by(AuditLog.created_at).all()
    assert len(rows) == 2
    assert rows[-1].details['changes']['root_cause'] == {'from': 'first', 'to': 'second'}


# ---------------------------------------------------------------------------
# Improvement actions
# ---------------------------------------------------------------------------

def test_create_action_rbac(auth, team):
    inc = team['inc']
    for role in ('Administrator', 'Incident Responder'):
        assert _post_action(auth(team['u'][role]), inc).status_code == 201, role
    # Manager holds improvements:create but cannot see... team['inc'] is org-wide readable (read_all)
    assert _post_action(auth(team['u']['Manager']), inc).status_code == 201
    for role in ('Analyst', 'Operator', 'Viewer'):
        assert _post_action(auth(team['u'][role]), inc).status_code == 403, role


def test_create_action_shape_snapshot_and_realtime(auth, team, rt):
    owner = team['u']['Analyst']
    due = datetime.now(timezone.utc) + timedelta(days=7)
    resp = _post_action(auth(team['u']['Incident Responder']), team['inc'], description='Roll out', owner_id=str(owner.id),
                        due_date=due.isoformat(), priority='high', category='technology',
                        control_framework='d3fend', control_ref='D3-MFA')
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body['status'] == 'open' and body['incident_ref'] == '#77 Ransom case'
    assert body['owner']['id'] == str(owner.id) and body['incident']['id'] == str(team['inc'].id)
    assert body['version'] == 1 and body['completed_at'] is None
    [env] = rt.changes('improvement_action')
    assert env['op'] == 'created' and env['scope'] == 'improvements' and env['incident_id'] == str(team['inc'].id)


def test_create_action_links_the_existing_review(auth, team):
    review = _put_review(auth(team['u']['Analyst']), team['inc'], root_cause='x').get_json()
    body = _post_action(auth(team['u']['Administrator']), team['inc']).get_json()
    assert body['review_id'] == review['id']


@pytest.mark.parametrize('body', [
    {'title': ''},
    {'priority': 'urgent'},
    {'status': 'finished'},
    {'category': 'weather'},
    {'control_framework': 'd3fend', 'control_ref': 'D3-NOPE'},
    {'control_framework': 'd3fend', 'control_ref': 'mfa'},
    {'control_framework': 'nist_csf', 'control_ref': 'bogus'},
    {'control_ref': 'RS.MA-01'},                       # a ref needs a framework
    {'control_framework': 'sox'},
])
def test_create_action_validation(auth, team, body):
    resp = _post_action(auth(team['u']['Administrator']), team['inc'], **body)
    assert resp.status_code == 400, resp.get_json()


def test_valid_control_references(auth, team):
    c = auth(team['u']['Administrator'])
    for fw, ref in (('nist_csf', 'RS.MA-01'), ('nist_csf', 'ID.IM'), ('d3fend', 'D3-MFA'),
                    ('cis', 'CIS 5.2'), ('iso27001', 'A.8.5'), ('other', 'anything')):
        resp = _post_action(c, team['inc'], control_framework=fw, control_ref=ref)
        assert resp.status_code == 201, (fw, ref, resp.get_json())


def test_owner_and_team_must_belong_to_the_org(auth, db, team, users, make_user, org_b):
    c = auth(team['u']['Administrator'])
    resp = _post_action(c, team['inc'], owner_id=str(users['admin_b'].id))
    assert resp.status_code == 400 and resp.get_json()['error'] == 'invalid_owner'
    inactive = make_user(team['org'], roles=['Analyst'], is_active=False)
    assert _post_action(c, team['inc'], owner_id=str(inactive.id)).status_code == 400
    assert _post_action(c, team['inc'], team_id=str(uuid.uuid4())).get_json()['error'] == 'invalid_team'


def test_update_status_sets_and_clears_completion(auth, team):
    c = auth(team['u']['Incident Responder'])
    aid = _post_action(c, team['inc']).get_json()['id']
    done = c.put(f'{API}/improvement-actions/{aid}', json={'status': 'done'}).get_json()
    assert done['completed_at'] and done['completed_by'] == str(team['u']['Incident Responder'].id)
    reopened = c.put(f'{API}/improvement-actions/{aid}', json={'status': 'in_progress'}).get_json()
    assert reopened['completed_at'] is None and reopened['completed_by'] is None
    assert reopened['version'] == 3


def test_update_validation_and_null_rules(auth, team):
    c = auth(team['u']['Administrator'])
    aid = _post_action(c, team['inc'], control_framework='d3fend', control_ref='D3-MFA').get_json()['id']
    for body in ({'title': None}, {'status': None}, {'priority': None}, {'status': 'nope'},
                 {'control_ref': 'D3-NOPE'}, {'control_framework': 'nist_csf'}):
        assert c.put(f'{API}/improvement-actions/{aid}', json=body).status_code == 400, body
    # clearing the framework clears the ref with it
    body = c.put(f'{API}/improvement-actions/{aid}', json={'control_framework': None}).get_json()
    assert body['control_framework'] is None and body['control_ref'] is None


def test_analyst_and_operator_update_only_their_own_actions(auth, team):
    admin = auth(team['u']['Administrator'])
    mine = _post_action(admin, team['inc'], owner_id=str(team['u']['Analyst'].id)).get_json()['id']
    others = _post_action(admin, team['inc'], owner_id=str(team['u']['Operator'].id)).get_json()['id']
    analyst = auth(team['u']['Analyst'])
    assert analyst.put(f'{API}/improvement-actions/{mine}', json={'status': 'in_progress'}).status_code == 200
    resp = analyst.put(f'{API}/improvement-actions/{others}', json={'status': 'done'})
    assert resp.status_code == 403 and resp.get_json()['error'] == 'forbidden'
    assert auth(team['u']['Operator']).put(f'{API}/improvement-actions/{others}',
                                           json={'status': 'blocked'}).status_code == 200
    assert auth(team['u']['Viewer']).put(f'{API}/improvement-actions/{mine}', json={'status': 'done'}).status_code == 403
    # the manager tier may change any visible action
    assert auth(team['u']['Manager']).put(f'{API}/improvement-actions/{others}', json={'priority': 'low'}).status_code == 200


def test_giving_away_ownership_loses_write_access(auth, team):
    ir = auth(team['u']['Incident Responder'])
    aid = _post_action(ir, team['inc'], owner_id=str(team['u']['Analyst'].id)).get_json()['id']
    assert auth(team['u']['Analyst']).put(f'{API}/improvement-actions/{aid}', json={'owner_id': str(team['u']['Operator'].id)}).status_code == 200
    assert auth(team['u']['Analyst']).put(f'{API}/improvement-actions/{aid}', json={'status': 'done'}).status_code == 403


def test_update_stale_if_match_is_409_and_fresh_succeeds(auth, team, rt):
    c = auth(team['u']['Administrator'])
    aid = _post_action(c, team['inc']).get_json()['id']
    c.put(f'{API}/improvement-actions/{aid}', json={'priority': 'high'})
    stale = c.put(f'{API}/improvement-actions/{aid}', json={'priority': 'low'}, headers={'If-Match': '"1"'})
    assert stale.status_code == 409 and stale.get_json()['current']['priority'] == 'high'
    fresh = c.put(f'{API}/improvement-actions/{aid}', json={'priority': 'low'}, headers={'If-Match': '"2"'})
    assert fresh.status_code == 200 and fresh.headers['ETag'] == '"3"'
    assert [e['op'] for e in rt.changes('improvement_action')] == ['created', 'updated', 'updated']


def test_delete_requires_improvements_delete(auth, team, rt):
    aid = _post_action(auth(team['u']['Incident Responder']), team['inc']).get_json()['id']
    assert auth(team['u']['Incident Responder']).delete(f'{API}/improvement-actions/{aid}').status_code == 403
    assert auth(team['u']['Manager']).delete(f'{API}/improvement-actions/{aid}').status_code == 403
    stale = auth(team['u']['Administrator']).delete(f'{API}/improvement-actions/{aid}', headers={'If-Match': '"9"'})
    assert stale.status_code == 409
    assert auth(team['u']['Administrator']).delete(f'{API}/improvement-actions/{aid}').status_code == 200
    assert auth(team['u']['Administrator']).delete(f'{API}/improvement-actions/{aid}').status_code == 404
    assert rt.changes('improvement_action')[-1]['op'] == 'deleted'


def test_actions_are_org_scoped(auth, team, users):
    aid = _post_action(auth(team['u']['Administrator']), team['inc']).get_json()['id']
    c = auth(users['admin_b'])
    assert c.put(f'{API}/improvement-actions/{aid}', json={'status': 'done'}).status_code == 404
    assert c.delete(f'{API}/improvement-actions/{aid}').status_code == 404
    assert _post_action(c, team['inc']).status_code == 404
    assert c.get(f"{API}/incidents/{team['inc'].id}/improvement-actions").status_code == 404
    assert aid not in [a['id'] for a in c.get(f'{API}/improvement-actions').get_json()['items']]


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

def test_incident_action_list_requires_improvements_read(auth, team, make_user):
    _post_action(auth(team['u']['Administrator']), team['inc'])
    body = auth(team['u']['Viewer']).get(f"{API}/incidents/{team['inc'].id}/improvement-actions")
    # Viewer reads improvements but this incident is amber and Viewer is not assigned.
    assert body.status_code == 403
    body = auth(team['u']['Analyst']).get(f"{API}/incidents/{team['inc'].id}/improvement-actions").get_json()
    assert body['total'] == 1 and body['items'][0]['title'] == 'Enable MFA on VPN'
    nope = make_user(team['org'], perms=['incidents:read', 'incidents:read_all'])
    assert auth(nope).get(f"{API}/incidents/{team['inc'].id}/improvement-actions").status_code == 403


def test_org_list_scoping_and_filters(auth, db, team, make_incident, make_user):
    admin, u = auth(team['u']['Administrator']), team['u']
    hidden = make_incident(org=team['org'], creator=u['Administrator'], tlp='red', title='Hidden case', incident_number=5)
    visible = team['inc']
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    a_visible = _post_action(admin, visible, title='visible one', due_date=past).get_json()
    a_hidden = _post_action(admin, hidden, title='hidden one', owner_id=str(u['Operator'].id)).get_json()
    a_other = _post_action(admin, hidden, title='hidden two').get_json()

    def ids(c, **params):
        return [a['id'] for a in c.get(f'{API}/improvement-actions', query_string=params).get_json()['items']]

    # Admin reads everything in the org
    assert {a_visible['id'], a_hidden['id'], a_other['id']} <= set(ids(admin))
    # Operator: assigned to `visible` only, but owns one action on the hidden incident
    op = auth(u['Operator'])
    got = ids(op)
    assert a_visible['id'] in got and a_hidden['id'] in got and a_other['id'] not in got
    row = next(a for a in op.get(f'{API}/improvement-actions').get_json()['items'] if a['id'] == a_hidden['id'])
    assert row['incident'] is None and row['incident_ref'] == '#5 Hidden case'   # owner-visible, incident hidden
    assert next(a for a in op.get(f'{API}/improvement-actions').get_json()['items']
                if a['id'] == a_visible['id'])['incident']['title'] == 'Ransom case'

    assert a_visible['id'] in ids(admin, overdue='true') and a_hidden['id'] not in ids(admin, overdue='true')
    assert ids(admin, owner_id=str(u['Operator'].id)) == [a_hidden['id']]
    assert ids(op, owner_id='me') == [a_hidden['id']]
    assert ids(admin, incident_id=str(visible.id)) == [a_visible['id']]
    assert ids(admin, q='hidden two') == [a_other['id']]
    assert ids(admin, status='done') == []
    assert admin.get(f'{API}/improvement-actions', query_string={'status': 'bogus'}).status_code == 400
    assert admin.get(f'{API}/improvement-actions', query_string={'owner_id': 'zzz'}).status_code == 400


def test_org_list_sorted_by_due_date_nulls_last(auth, team):
    admin = auth(team['u']['Administrator'])
    now = datetime.now(timezone.utc)
    late = _post_action(admin, team['inc'], title='late', due_date=(now + timedelta(days=9)).isoformat()).get_json()
    none = _post_action(admin, team['inc'], title='none').get_json()
    soon = _post_action(admin, team['inc'], title='soon', due_date=(now + timedelta(days=1)).isoformat()).get_json()
    items = admin.get(f'{API}/improvement-actions', query_string={'incident_id': str(team['inc'].id)}).get_json()['items']
    assert [a['id'] for a in items] == [soon['id'], late['id'], none['id']]


def test_org_list_requires_improvements_read(auth, team, make_user):
    assert auth(make_user(team['org'], perms=['incidents:read'])).get(f'{API}/improvement-actions').status_code == 403
    assert auth(team['u']['Viewer']).get(f'{API}/improvement-actions').status_code == 200


# ---------------------------------------------------------------------------
# Survival of a permanent incident delete
# ---------------------------------------------------------------------------

def test_actions_survive_permanent_incident_delete(auth, db, team):
    from app.models import ImprovementAction, IncidentReview
    admin = auth(team['u']['Administrator'])
    inc = team['inc']
    inc.title = 'Renamed before purge'
    db.session.commit()
    _put_review(auth(team['u']['Analyst']), inc, root_cause='r')
    owner = team['u']['Analyst']
    aid = _post_action(admin, inc, owner_id=str(owner.id)).get_json()['id']
    iid = inc.id
    assert admin.post(f'{API}/incidents/{iid}/archive').status_code == 200
    assert admin.delete(f'{API}/incidents/{iid}/permanent').status_code == 200

    db.session.expire_all()
    action = db.session.get(ImprovementAction, uuid.UUID(aid))
    assert action is not None and action.incident_id is None
    assert action.incident_ref == '#77 Renamed before purge'                 # label refreshed by the purge step
    assert IncidentReview.query.filter_by(incident_id=iid).count() == 0      # the review goes with the incident

    # still listed (org-wide) and editable by its owner; incident object is gone
    row = next(a for a in auth(owner).get(f'{API}/improvement-actions').get_json()['items'] if a['id'] == aid)
    assert row['incident'] is None and row['incident_ref'] == '#77 Renamed before purge'
    assert auth(owner).put(f'{API}/improvement-actions/{aid}', json={'status': 'done'}).status_code == 200
    # an orphan is visible to the org's responders but not changeable by a non-owner Analyst
    ir = auth(team['u']['Incident Responder'])
    assert ir.put(f'{API}/improvement-actions/{aid}', json={'priority': 'low'}).status_code == 200
    assert auth(team['u']['Operator']).put(f'{API}/improvement-actions/{aid}', json={'priority': 'high'}).status_code == 403
    assert admin.delete(f'{API}/improvement-actions/{aid}').status_code == 200
