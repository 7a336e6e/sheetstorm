"""W2-DFIR-B: GET /dashboard/stats aggregates in SQL over the incidents the
caller can see (admin vs assigned-only operator vs TLP:WHITE viewer), MITRE
counts over mappings plus the legacy columns, and counts only (no ids or
titles)."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

API = '/api/v1'


@pytest.fixture
def world(app, db, make_user, make_incident):
    """A fresh org so counts are exact:
    inc1 critical/open/amber (operator assigned) - 3 events, 1 open lead, 1 host
    inc2 high/closed/white, created 20 days ago   - nothing
    inc3 medium/investigating/red                 - 1 event, 1 open + 1 resolved lead, 1 clean host
    inc4 archived (never counted)."""
    from app.models import CompromisedHost, Organization, Task, TimelineEvent

    org = Organization(name='dash', slug=f'dash-{uuid.uuid4().hex[:8]}', settings={})
    db.session.add(org)
    db.session.commit()
    admin = make_user(org, roles=['Administrator'])
    operator = make_user(org, roles=['Operator'])
    viewer = make_user(org, roles=['Viewer'])
    reader = make_user(org, perms=['incidents:read', 'incidents:read_all'])

    inc1 = make_incident(org=org, creator=admin, severity='critical', status='open', phase=1, tlp='amber',
                         assign=[operator], title='Secret title one')
    inc2 = make_incident(org=org, creator=admin, severity='high', status='closed', phase=6, tlp='white',
                         title='Secret title two')
    inc2.created_at = datetime.now(timezone.utc) - timedelta(days=20)
    inc3 = make_incident(org=org, creator=admin, severity='medium', status='investigating', phase=2, tlp='red',
                         title='Secret title three')
    inc4 = make_incident(org=org, creator=admin, severity='critical', is_archived=True, title='Archived')

    now = datetime.now(timezone.utc)

    def event(inc, **kw):
        db.session.add(TimelineEvent(incident_id=inc.id, timestamp=now, activity='x', created_by=admin.id, **kw))

    event(inc1, mitre_mappings=[{'tactic': 'execution', 'technique': 'T1059'},
                                {'tactic': 'Persistence', 'technique': 't1547'}])
    event(inc1, mitre_mappings=[], mitre_tactic='execution', mitre_technique='T1059')
    event(inc1, mitre_mappings=[])
    event(inc3, mitre_mappings=[{'tactic': 'discovery', 'technique': 'T1046'}])
    event(inc4, mitre_mappings=[{'tactic': 'impact', 'technique': 'T1486'}])
    for inc, outcome in ((inc1, None), (inc3, None), (inc3, 'resolved'), (inc4, None)):
        db.session.add(Task(incident_id=inc.id, title='lead', task_type='investigative_lead',
                            lead_outcome=outcome, created_by=admin.id))
    db.session.add(Task(incident_id=inc1.id, title='action', created_by=admin.id))
    db.session.add(CompromisedHost(incident_id=inc1.id, hostname='h1', triage_status='under_analysis',
                                   created_by=admin.id))
    db.session.add(CompromisedHost(incident_id=inc3.id, hostname='h3', triage_status='clean', created_by=admin.id))
    db.session.commit()
    return {'org': org, 'admin': admin, 'operator': operator, 'viewer': viewer, 'reader': reader,
            'incidents': [inc1, inc2, inc3, inc4]}


def _stats(auth, user):
    resp = auth(user).get(f'{API}/dashboard/stats')
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_admin_sees_every_accessible_incident(auth, world):
    data = _stats(auth, world['admin'])
    inc = data['incidents']
    assert (inc['total'], inc['active'], inc['closed'], inc['critical']) == (3, 2, 1, 1)
    assert (inc['created_7d'], inc['created_30d']) == (2, 3)
    assert inc['by_severity'] == {'critical': 1, 'high': 1, 'medium': 1, 'low': 0}
    assert inc['by_status'] == {'open': 1, 'closed': 1, 'investigating': 1}
    assert inc['by_phase_open'] == {'1': 1, '2': 1}
    assert inc['by_tlp'] == {'amber': 1, 'white': 1, 'red': 1}

    mitre = data['mitre']
    assert (mitre['events_total'], mitre['events_mapped']) == (4, 3)
    tactics = {t['tactic']: t for t in mitre['tactics']}
    assert tactics['execution'] == {'tactic': 'execution', 'count': 2, 'techniques': {'T1059': 2}}
    assert tactics['persistence'] == {'tactic': 'persistence', 'count': 1, 'techniques': {'T1547': 1}}
    assert tactics['discovery']['count'] == 1
    assert 'impact' not in tactics  # archived incident
    assert data['dfir'] == {'open_leads': 2, 'hosts_by_triage': {'under_analysis': 1, 'clean': 1}}


def test_operator_sees_only_assigned_incidents(auth, world):
    data = _stats(auth, world['operator'])
    assert data['incidents']['total'] == 1 and data['incidents']['critical'] == 1
    assert (data['mitre']['events_total'], data['mitre']['events_mapped']) == (3, 2)
    assert data['dfir'] == {'open_leads': 1, 'hosts_by_triage': {'under_analysis': 1}}


def test_viewer_sees_assigned_plus_tlp_white(auth, world):
    data = _stats(auth, world['viewer'])
    assert data['incidents']['total'] == 1
    assert data['incidents']['by_tlp'] == {'white': 1}
    assert data['incidents']['closed'] == 1
    assert data['mitre']['events_total'] == 0 and data['mitre']['tactics'] == []
    assert data['dfir'] == {'open_leads': 0, 'hosts_by_triage': {}}


def test_parts_need_their_read_permission(auth, world):
    data = _stats(auth, world['reader'])
    assert data['incidents']['total'] == 3
    assert data['mitre'] is None
    assert data['dfir'] == {'open_leads': None, 'hosts_by_triage': None}


def test_other_org_sees_none_of_it(auth, users, org_b, world):
    from app.models import Incident
    data = _stats(auth, users['admin_b'])
    assert data['incidents']['total'] == Incident.query.filter_by(
        organization_id=org_b.id, is_archived=False).count()
    for t in data['mitre']['tactics']:
        assert 'T1547' not in t['techniques']


def test_payload_has_counts_only(auth, world):
    raw = json.dumps(_stats(auth, world['admin']))
    for inc in world['incidents']:
        assert str(inc.id) not in raw
        assert inc.title not in raw


def test_requires_incidents_read(auth, make_user, world):
    nobody = make_user(world['org'], perms=[])
    assert auth(nobody).get(f'{API}/dashboard/stats').status_code == 403


def test_non_array_mappings_do_not_break_the_aggregate(db, auth, world):
    from sqlalchemy import text
    from app.models import TimelineEvent
    event = TimelineEvent(incident_id=world['incidents'][0].id, timestamp=datetime.now(timezone.utc),
                          activity='scalar', created_by=world['admin'].id)
    db.session.add(event)
    db.session.commit()
    # Legacy/bad data the ORM would not write: a JSON scalar instead of an array.
    db.session.execute(text("UPDATE timeline_events SET mitre_mappings = CAST('\"oops\"' AS jsonb) WHERE id = :id"),
                       {'id': str(event.id)})
    db.session.commit()
    data = _stats(auth, world['admin'])
    assert data['mitre']['events_total'] == 5 and data['mitre']['events_mapped'] == 3
