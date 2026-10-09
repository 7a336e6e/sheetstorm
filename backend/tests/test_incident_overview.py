"""W2-DFIR-B: incident Overview summary, IR milestone validation (C20),
status/phase stamping, create-form fixes, and two lead-responder bugs
(assign endpoint leaves a stale lead_responder_id; a lead change through PUT
did not notify the new lead)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

API = '/api/v1'


def _ok(resp, *codes):
    assert resp.status_code in (codes or (200, 201)), (resp.status_code, resp.get_json())
    return resp.get_json()


def _iso(dt):
    return dt.isoformat()


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


@pytest.fixture
def now():
    return datetime.now(timezone.utc).replace(microsecond=0)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def test_summary_counts(db, admin, users, make_incident, now):
    from app.models import CompromisedHost, Task, TimelineEvent
    inc = make_incident()
    creator = users['Administrator'].id
    t0 = now - timedelta(days=3)
    for i, (ts, det) in enumerate([(t0, t0 + timedelta(hours=5)), (t0 + timedelta(days=1), None),
                                    (t0 + timedelta(days=2), t0 + timedelta(hours=2))]):
        db.session.add(TimelineEvent(incident_id=inc.id, timestamp=ts, detection_time=det,
                                     activity=f'event {i}', created_by=creator))
    for outcome in (None, None, 'false_positive'):
        db.session.add(Task(incident_id=inc.id, title='lead', task_type='investigative_lead',
                            lead_outcome=outcome, created_by=creator))
    db.session.add(Task(incident_id=inc.id, title='action', created_by=creator))
    db.session.add(CompromisedHost(incident_id=inc.id, hostname='ws1', triage_status='under_analysis',
                                   acquisition_status={'memory_captured': True}, created_by=creator))
    db.session.add(CompromisedHost(incident_id=inc.id, hostname='ws2', triage_status='under_analysis',
                                   acquisition_status={}, created_by=creator))
    db.session.add(CompromisedHost(incident_id=inc.id, hostname='srv1', triage_status='clean',
                                   acquisition_status={'disk_imaged': True, 'memory_captured': True,
                                                       'forensically_sound': False},
                                   created_by=creator))
    db.session.commit()

    summary = _ok(admin.get(f'{API}/incidents/{inc.id}'))['summary']
    assert datetime.fromisoformat(summary['first_event_at']) == t0
    assert datetime.fromisoformat(summary['last_event_at']) == t0 + timedelta(days=2)
    assert datetime.fromisoformat(summary['earliest_detection_at']) == t0 + timedelta(hours=2)
    assert summary['leads'] == {'total': 3, 'open': 2, 'by_outcome': {'open': 2, 'false_positive': 1}}
    assert summary['hosts_by_triage'] == {'under_analysis': 2, 'clean': 1}
    assert summary['acquisition'] == {'disk_imaged': 1, 'memory_captured': 2, 'logs_collected': 0,
                                      'forensically_sound': 0}


def test_summary_empty_incident(admin, make_incident):
    summary = _ok(admin.get(f'{API}/incidents/{make_incident().id}'))['summary']
    assert summary['first_event_at'] is None and summary['last_event_at'] is None
    assert summary['leads'] == {'total': 0, 'open': 0, 'by_outcome': {}}
    assert summary['hosts_by_triage'] == {}


def test_summary_parts_need_their_read_permission(auth, make_user, org_a, make_incident):
    reader = make_user(org_a, perms=['incidents:read'])
    inc = make_incident(assign=[reader])
    summary = _ok(auth(reader).get(f'{API}/incidents/{inc.id}'))['summary']
    assert summary == {'first_event_at': None, 'last_event_at': None, 'earliest_detection_at': None,
                       'leads': None, 'hosts_by_triage': None, 'acquisition': None}


def test_summary_only_on_single_get(admin, make_incident):
    make_incident()
    items = _ok(admin.get(f'{API}/incidents?per_page=5'))['items']
    assert items and all('summary' not in i for i in items)


# ---------------------------------------------------------------------------
# Milestones (PUT /incidents/<id>)
# ---------------------------------------------------------------------------

def test_milestones_round_trip_in_order(admin, make_incident, now):
    inc = make_incident()
    body = {'detected_at': _iso(now - timedelta(days=2)), 'contained_at': _iso(now - timedelta(days=1)),
            'eradicated_at': _iso(now - timedelta(hours=10)), 'recovered_at': _iso(now - timedelta(hours=2)),
            'closed_at': _iso(now - timedelta(hours=1))}
    data = _ok(admin.put(f'{API}/incidents/{inc.id}', json=body))
    for field, value in body.items():
        assert datetime.fromisoformat(data[field]) == datetime.fromisoformat(value), field


def test_naive_milestone_is_utc(admin, make_incident, now):
    inc = make_incident()
    naive = (now - timedelta(hours=3)).replace(tzinfo=None).isoformat()
    data = _ok(admin.put(f'{API}/incidents/{inc.id}', json={'contained_at': naive}))
    assert datetime.fromisoformat(data['contained_at']) == now - timedelta(hours=3)


def test_future_milestone_is_400(admin, make_incident, now):
    inc = make_incident()
    resp = admin.put(f'{API}/incidents/{inc.id}', json={'contained_at': _iso(now + timedelta(minutes=10))})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body['error'] == 'invalid_milestones' and body['code'] == 'milestone_in_future'
    assert body['field'] == 'contained_at'
    # Within the 5-minute clock-skew allowance.
    _ok(admin.put(f'{API}/incidents/{inc.id}', json={'contained_at': _iso(now + timedelta(minutes=2))}))


def test_out_of_order_milestones_are_400_and_nothing_is_written(db, admin, make_incident, now):
    from app.models import Incident
    inc = make_incident(detected_at=now - timedelta(days=1))
    resp = admin.put(f'{API}/incidents/{inc.id}', json={
        'title': 'should not be saved', 'contained_at': _iso(now - timedelta(days=2))})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body['code'] == 'milestone_order'
    assert body['pair'] == ['detected_at', 'contained_at']
    db.session.expire_all()
    stored = db.session.get(Incident, inc.id)
    assert stored.contained_at is None and stored.title != 'should not be saved'

    # Two changed values out of order with each other.
    resp = admin.put(f'{API}/incidents/{inc.id}', json={
        'eradicated_at': _iso(now - timedelta(hours=1)), 'recovered_at': _iso(now - timedelta(hours=5))})
    assert resp.status_code == 400 and resp.get_json()['code'] == 'milestone_order'

    # Non-adjacent: closed before detected even with nothing in between.
    resp = admin.put(f'{API}/incidents/{inc.id}', json={'closed_at': _iso(now - timedelta(days=3))})
    assert resp.status_code == 400 and resp.get_json()['pair'] == ['detected_at', 'closed_at']


def test_equal_milestones_are_allowed(admin, make_incident, now):
    inc = make_incident(detected_at=now - timedelta(hours=1))
    _ok(admin.put(f'{API}/incidents/{inc.id}', json={'contained_at': _iso(now - timedelta(hours=1))}))


def test_legacy_out_of_order_pair_does_not_block_other_edits(admin, make_incident, now):
    # Legacy data (written before validation): contained after eradicated.
    inc = make_incident(detected_at=now - timedelta(days=5), contained_at=now - timedelta(days=1),
                        eradicated_at=now - timedelta(days=2))
    _ok(admin.put(f'{API}/incidents/{inc.id}', json={'recovered_at': _iso(now - timedelta(hours=1))}))
    _ok(admin.put(f'{API}/incidents/{inc.id}', json={'executive_summary': 'unrelated edit'}))
    # ... but a changed value is still checked against every set milestone.
    resp = admin.put(f'{API}/incidents/{inc.id}', json={'closed_at': _iso(now - timedelta(days=3))})
    assert resp.status_code == 400


def test_milestone_can_be_cleared(admin, make_incident, now):
    inc = make_incident(contained_at=now - timedelta(hours=1))
    data = _ok(admin.put(f'{API}/incidents/{inc.id}', json={'contained_at': None}))
    assert data['contained_at'] is None


def test_narrative_length_caps(admin, make_incident):
    inc = make_incident()
    _ok(admin.put(f'{API}/incidents/{inc.id}', json={'executive_summary': 'x' * 20000}))
    assert admin.put(f'{API}/incidents/{inc.id}', json={'lessons_learned': 'x' * 20001}).status_code == 400
    assert admin.put(f'{API}/incidents/{inc.id}', json={'description': 'x' * 10001}).status_code == 400


def test_viewer_cannot_edit_milestones(auth, users, make_incident, now):
    inc = make_incident(tlp='white', assign=[users['Viewer']])
    resp = auth(users['Viewer']).put(f'{API}/incidents/{inc.id}', json={'contained_at': _iso(now)})
    assert resp.status_code == 403


def test_milestone_edit_is_audited_with_a_diff(db, admin, make_incident, now):
    from app.models import AuditLog
    inc = make_incident()
    _ok(admin.put(f'{API}/incidents/{inc.id}', json={'contained_at': _iso(now - timedelta(hours=1))}))
    row = AuditLog.query.filter_by(action='update', resource_type='incident',
                                   resource_id=str(inc.id)).order_by(AuditLog.created_at.desc()).first()
    assert row is not None
    assert 'contained_at' in (row.details or {}).get('changes', {})


def test_put_rejects_cross_org_team(admin, make_incident, org_b, db):
    from app.models import Team
    foreign = Team(organization_id=org_b.id, name=f'b-team-{uuid.uuid4().hex[:6]}')
    db.session.add(foreign)
    db.session.commit()
    inc = make_incident()
    resp = admin.put(f'{API}/incidents/{inc.id}', json={'team_id': str(foreign.id)})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'invalid_team'


# ---------------------------------------------------------------------------
# Status / phase stamping (PATCH /incidents/<id>/status)
# ---------------------------------------------------------------------------

def test_phase_only_change_stamps_the_milestone(admin, make_incident):
    inc = make_incident()
    data = _ok(admin.patch(f'{API}/incidents/{inc.id}/status', json={'phase': 3}))
    assert data['status'] == 'contained' and data['phase'] == 3
    assert data['contained_at'] is not None


def test_status_change_stamps_and_keeps_an_existing_value(admin, make_incident, now):
    earlier = now - timedelta(days=1)
    inc = make_incident(contained_at=earlier)
    data = _ok(admin.patch(f'{API}/incidents/{inc.id}/status', json={'status': 'contained'}))
    assert datetime.fromisoformat(data['contained_at']) == earlier
    data = _ok(admin.patch(f'{API}/incidents/{inc.id}/status', json={'status': 'eradicated'}))
    assert data['phase'] == 4 and data['eradicated_at'] is not None


def test_close_then_reopen_clears_closed_at(admin, make_incident):
    inc = make_incident()
    data = _ok(admin.patch(f'{API}/incidents/{inc.id}/status', json={'status': 'closed'}))
    assert data['closed_at'] is not None and data['phase'] == 6
    data = _ok(admin.patch(f'{API}/incidents/{inc.id}/status', json={'status': 'investigating'}))
    assert data['status'] == 'investigating' and data['closed_at'] is None
    # Reopen through a phase change as well.
    _ok(admin.patch(f'{API}/incidents/{inc.id}/status', json={'phase': 6}))
    data = _ok(admin.patch(f'{API}/incidents/{inc.id}/status', json={'phase': 5}))
    assert data['status'] == 'recovered' and data['closed_at'] is None


def test_apply_status_change_helper(make_incident):
    from app.api.v1.endpoints.incidents import apply_status_change
    from app.models import Incident
    inc = Incident(status='open', phase=1)
    stamp = datetime(2026, 1, 2, tzinfo=timezone.utc)
    apply_status_change(inc, phase=6, now=stamp)
    assert (inc.status, inc.phase, inc.closed_at) == ('closed', 6, stamp)
    apply_status_change(inc, status='open', now=stamp)
    assert (inc.status, inc.phase, inc.closed_at) == ('open', 1, None)
    apply_status_change(inc)  # nothing to do
    assert inc.status == 'open'


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def _create(client, **body):
    return client.post(f'{API}/incidents', json={'title': f'Create {uuid.uuid4().hex[:8]}', **body})


def test_create_with_tlp_detected_and_lead(db, admin, users, fresh_user, now):
    from app.models import IncidentAssignment, Notification
    lead = fresh_user('Analyst')
    detected = now - timedelta(hours=6)
    data = _ok(_create(admin, tlp='red', detected_at=_iso(detected), lead_responder_id=str(lead.id)), 201)
    assert data['tlp'] == 'red'
    assert datetime.fromisoformat(data['detected_at']) == detected
    assert data['lead_responder']['id'] == str(lead.id)
    roles = {str(a.user_id): a.role for a in IncidentAssignment.query.filter_by(incident_id=data['id'])}
    assert roles == {str(users['Administrator'].id): 'Creator', str(lead.id): 'Lead Responder'}
    assert Notification.query.filter_by(user_id=lead.id, incident_id=data['id'],
                                        type='incident_assigned').count() == 1


def test_create_creator_as_lead_gets_one_assignment(admin, users):
    from app.models import IncidentAssignment
    me = users['Administrator']
    data = _ok(_create(admin, lead_responder_id=str(me.id)), 201)
    rows = IncidentAssignment.query.filter_by(incident_id=data['id']).all()
    assert [(r.user_id, r.role) for r in rows] == [(me.id, 'Lead Responder')]


def test_create_defaults_detected_at_to_now(admin, now):
    data = _ok(_create(admin), 201)
    assert abs(datetime.fromisoformat(data['detected_at']) - now) < timedelta(minutes=1)
    assert data['tlp'] == 'amber'


@pytest.mark.parametrize('case', ['future_detected', 'foreign_team', 'foreign_access_team', 'foreign_lead',
                                  'inactive_lead', 'short_title', 'bad_tlp'])
def test_create_rejects_bad_input_and_writes_nothing(db, admin, org_b, users, fresh_user, now, case):
    from app.models import Incident, Team
    foreign_team = Team(organization_id=org_b.id, name=f'b-team-{uuid.uuid4().hex[:6]}')
    db.session.add(foreign_team)
    db.session.commit()
    title = f'Rejected {uuid.uuid4().hex[:8]}'
    body = {
        'future_detected': {'detected_at': _iso(now + timedelta(hours=1))},
        'foreign_team': {'team_id': str(foreign_team.id)},
        'foreign_access_team': {'team_ids': [str(foreign_team.id)]},
        'foreign_lead': {'lead_responder_id': str(users['admin_b'].id)},
        'inactive_lead': {'lead_responder_id': str(fresh_user('Analyst', is_active=False).id)},
        'short_title': {'title': 'ab'},
        'bad_tlp': {'tlp': 'purple'},
    }[case]
    resp = admin.post(f'{API}/incidents', json={'title': title, **body})
    assert resp.status_code == 400, resp.get_json()
    assert Incident.query.filter_by(title=title).count() == 0


def test_create_with_access_teams(db, admin, org_a):
    from app.models import Team
    team = Team(organization_id=org_a.id, name=f'a-team-{uuid.uuid4().hex[:6]}')
    db.session.add(team)
    db.session.commit()
    data = _ok(_create(admin, team_ids=[str(team.id), str(team.id)]), 201)
    assert [t['id'] for t in data['teams']] == [str(team.id)]


def test_create_requires_a_json_object(admin):
    assert admin.post(f'{API}/incidents', data='nope', content_type='application/json').status_code == 400
    assert admin.post(f'{API}/incidents', json=['x']).status_code == 400


# ---------------------------------------------------------------------------
# Lead responder bugs
# ---------------------------------------------------------------------------

def test_reassigning_the_lead_with_another_role_clears_lead_responder(db, admin, make_incident, fresh_user):
    from app.models import Incident
    analyst = fresh_user('Analyst')
    inc = make_incident()
    _ok(admin.post(f'{API}/incidents/{inc.id}/assignments',
                   json={'user_id': str(analyst.id), 'role': 'Lead Responder'}))
    assert _ok(admin.get(f'{API}/incidents/{inc.id}'))['lead_responder']['id'] == str(analyst.id)

    _ok(admin.post(f'{API}/incidents/{inc.id}/assignments', json={'user_id': str(analyst.id), 'role': 'Analyst'}))
    db.session.expire_all()
    assert db.session.get(Incident, inc.id).lead_responder_id is None
    assert _ok(admin.get(f'{API}/incidents/{inc.id}'))['lead_responder'] is None


def test_assigning_someone_else_keeps_the_lead(db, admin, make_incident, fresh_user):
    from app.models import Incident
    lead, other = fresh_user('Analyst'), fresh_user('Analyst')
    inc = make_incident()
    _ok(admin.post(f'{API}/incidents/{inc.id}/assignments', json={'user_id': str(lead.id), 'role': 'Lead Responder'}))
    _ok(admin.post(f'{API}/incidents/{inc.id}/assignments', json={'user_id': str(other.id), 'role': 'Analyst'}))
    db.session.expire_all()
    assert db.session.get(Incident, inc.id).lead_responder_id == lead.id


def test_lead_change_via_put_notifies_the_new_lead(admin, make_incident, fresh_user):
    from app.models import Notification
    lead = fresh_user('Analyst')
    inc = make_incident()
    _ok(admin.put(f'{API}/incidents/{inc.id}', json={'lead_responder_id': str(lead.id)}))
    query = Notification.query.filter_by(user_id=lead.id, incident_id=inc.id, type='incident_assigned')
    assert query.count() == 1
    # Re-sending the same lead is not a change: no second notification.
    _ok(admin.put(f'{API}/incidents/{inc.id}', json={'lead_responder_id': str(lead.id)}))
    assert query.count() == 1


def test_lead_change_via_put_rejects_foreign_or_inactive_user(admin, users, make_incident, fresh_user):
    inc = make_incident()
    for user in (users['admin_b'], fresh_user('Analyst', is_active=False)):
        resp = admin.put(f'{API}/incidents/{inc.id}', json={'lead_responder_id': str(user.id)})
        assert resp.status_code == 400 and resp.get_json()['error'] == 'invalid_lead_responder'
