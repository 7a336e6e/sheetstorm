"""W3-RT-POST: incident / organization response metrics, lifecycle timestamps
(`first_malicious_at`, `responded_at`) and their validation."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

API = '/api/v1'
BASE = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def at(**delta):
    return BASE + timedelta(**delta)


# ---------------------------------------------------------------------------
# Pure computation
# ---------------------------------------------------------------------------

def test_compute_durations_from_fixed_timestamps():
    from app.services.metrics_service import compute_durations
    ts = {'first_malicious': at(), 'detected': at(hours=10), 'responded': at(hours=11), 'contained': at(hours=14),
          'eradicated': at(hours=20), 'recovered': at(hours=30), 'closed': at(hours=31)}
    durations, anomalies = compute_durations(ts, now=at(days=30))
    assert durations == {
        'dwell_time': 10 * 3600, 'time_to_respond': 3600, 'time_to_contain': 4 * 3600,
        'contain_to_eradicate': 6 * 3600, 'eradicate_to_recover': 10 * 3600, 'recover_to_close': 3600,
        'total_open': 21 * 3600,
    }
    assert anomalies == []


def test_compute_durations_missing_endpoints_are_null_and_open_incident_uses_now():
    from app.services.metrics_service import compute_durations
    durations, anomalies = compute_durations({'detected': at(hours=1), 'contained': at(hours=3)}, now=at(hours=9))
    assert durations['time_to_contain'] == 2 * 3600
    assert durations['dwell_time'] is None and durations['time_to_respond'] is None
    assert durations['contain_to_eradicate'] is None and durations['recover_to_close'] is None
    assert durations['total_open'] == 8 * 3600  # (now - detected), not closed
    assert anomalies == []


def test_compute_durations_negative_is_null_plus_anomaly():
    from app.services.metrics_service import compute_durations
    ts = {'detected': at(hours=5), 'contained': at(hours=2), 'eradicated': at(hours=8)}
    durations, anomalies = compute_durations(ts, now=at(days=1))
    assert durations['time_to_contain'] is None
    assert durations['contain_to_eradicate'] == 6 * 3600
    assert anomalies == [{'metric': 'time_to_contain', 'reason': 'negative', 'seconds': -3 * 3600}]


# ---------------------------------------------------------------------------
# GET /incidents/<id>/metrics
# ---------------------------------------------------------------------------

def _event(db, inc, user, ts, **fields):
    from app.models import TimelineEvent
    db.session.add(TimelineEvent(incident_id=inc.id, timestamp=ts, activity='x', created_by=user.id, **fields))
    db.session.commit()


def test_incident_metrics_first_malicious_derived_from_timeline(auth, db, users, make_incident):
    inc = make_incident(detected_at=at(hours=10), contained_at=at(hours=14), closed_at=at(hours=40))
    _event(db, inc, users['Administrator'], at(hours=-5))                       # benign: ignored
    _event(db, inc, users['Administrator'], at(hours=2), is_ioc=True)
    _event(db, inc, users['Administrator'], at(hours=1), mitre_tactic='execution')
    _event(db, inc, users['Administrator'], at(hours=3), mitre_mappings=[{'tactic': 'impact', 'technique': 'T1486'}])
    resp = auth(users['Administrator']).get(f'{API}/incidents/{inc.id}/metrics')
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['incident_id'] == str(inc.id)
    assert body['sources'] == {'first_malicious': 'timeline'}
    assert body['timestamps']['first_malicious'] == at(hours=1).isoformat()
    assert body['durations']['dwell_time'] == 9 * 3600
    assert body['durations']['time_to_contain'] == 4 * 3600
    assert body['durations']['time_to_respond'] is None
    assert body['anomalies'] == []


def test_incident_metrics_override_beats_timeline_and_negative_is_anomaly(auth, db, users, make_incident):
    inc = make_incident(detected_at=at(hours=10), first_malicious_at=at(hours=12))  # detected BEFORE the malicious start
    _event(db, inc, users['Administrator'], at(hours=1), is_ioc=True)
    body = auth(users['Administrator']).get(f'{API}/incidents/{inc.id}/metrics').get_json()
    assert body['sources']['first_malicious'] == 'override'
    assert body['durations']['dwell_time'] is None
    assert body['anomalies'][0]['metric'] == 'dwell_time' and body['anomalies'][0]['reason'] == 'negative'


def test_incident_metrics_without_timeline_read_never_consults_the_timeline(auth, db, users, make_user, make_incident, org_a):
    inc = make_incident(detected_at=at(hours=10))
    _event(db, inc, users['Administrator'], at(hours=1), is_ioc=True)
    reader = make_user(org_a, perms=['incidents:read', 'incidents:read_all'])
    body = auth(reader).get(f'{API}/incidents/{inc.id}/metrics').get_json()
    assert body['sources'] == {'first_malicious': 'restricted'}
    assert body['timestamps']['first_malicious'] is None and body['durations']['dwell_time'] is None


def test_incident_metrics_access_rules(auth, users, make_incident, org_b):
    inc = make_incident(tlp='red')
    assert auth(users['Viewer']).get(f'{API}/incidents/{inc.id}/metrics').status_code == 403   # TLP red, not assigned
    assert auth(users['admin_b']).get(f'{API}/incidents/{inc.id}/metrics').status_code == 404  # other org
    assert auth(users['Operator']).get(f'{API}/incidents/{inc.id}/metrics').status_code == 403  # not assigned
    inc2 = make_incident(assign=[users['Operator']])
    assert auth(users['Operator']).get(f'{API}/incidents/{inc2.id}/metrics').status_code == 200


# ---------------------------------------------------------------------------
# Lifecycle timestamps: edit validation, auto-stamping
# ---------------------------------------------------------------------------

def test_edit_new_lifecycle_fields_and_audit_diff(auth, db, users, make_incident):
    inc = make_incident(detected_at=at(hours=10))
    c = auth(users['Administrator'])
    resp = c.put(f'{API}/incidents/{inc.id}', json={
        'first_malicious_at': at(hours=2).isoformat(), 'responded_at': at(hours=11).isoformat()})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['first_malicious_at'] == at(hours=2).isoformat()
    assert body['responded_at'] == at(hours=11).isoformat()
    # null clears
    resp = c.put(f'{API}/incidents/{inc.id}', json={'first_malicious_at': None})
    assert resp.status_code == 200 and resp.get_json()['first_malicious_at'] is None


@pytest.mark.parametrize('payload,code', [
    ({'responded_at': 'FUTURE'}, 'milestone_in_future'),
    ({'first_malicious_at': 'FUTURE'}, 'milestone_in_future'),
    ({'first_malicious_at': at(hours=20).isoformat()}, 'milestone_order'),   # after detected_at (+10h)
    ({'responded_at': at(hours=5).isoformat()}, 'milestone_order'),          # before detected_at
])
def test_new_lifecycle_fields_validation(auth, users, make_incident, payload, code):
    inc = make_incident(detected_at=at(hours=10))
    payload = {k: (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat() if v == 'FUTURE' else v
               for k, v in payload.items()}
    resp = auth(users['Administrator']).put(f'{API}/incidents/{inc.id}', json=payload)
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()['code'] == code


def test_responded_at_is_set_by_first_status_change_and_kept(auth, db, users, make_incident):
    inc = make_incident()
    c = auth(users['Administrator'])
    assert c.get(f'{API}/incidents/{inc.id}').get_json()['responded_at'] is None
    body = c.patch(f'{API}/incidents/{inc.id}/status', json={'status': 'investigating'}).get_json()
    first = body['responded_at']
    assert first is not None
    body = c.patch(f'{API}/incidents/{inc.id}/status', json={'status': 'contained'}).get_json()
    assert body['responded_at'] == first                      # not overwritten
    assert body['contained_at'] is not None


def test_responded_at_is_set_by_first_explicit_assignment_only(auth, db, users, make_incident, fresh_user):
    inc = make_incident(assign=[users['Administrator']])        # the creator's own assignment does not count
    c = auth(users['Administrator'])
    assert c.get(f'{API}/incidents/{inc.id}').get_json()['responded_at'] is None
    other = fresh_user('Analyst')
    resp = c.post(f'{API}/incidents/{inc.id}/assignments', json={'user_id': str(other.id), 'role': 'Analyst'})
    assert resp.status_code == 201, resp.get_json()
    first = c.get(f'{API}/incidents/{inc.id}').get_json()['responded_at']
    assert first is not None
    third = fresh_user('Analyst')
    c.post(f'{API}/incidents/{inc.id}/assignments', json={'user_id': str(third.id), 'role': 'Analyst'})
    assert c.get(f'{API}/incidents/{inc.id}').get_json()['responded_at'] == first


def test_create_does_not_set_responded_at(auth, users):
    resp = auth(users['Administrator']).post(f'{API}/incidents', json={'title': 'Fresh incident', 'severity': 'low'})
    assert resp.status_code == 201
    assert resp.get_json()['responded_at'] is None and resp.get_json()['first_malicious_at'] is None


def test_reopen_clears_closed_at(auth, users, make_incident):
    inc = make_incident()
    c = auth(users['Administrator'])
    assert c.patch(f'{API}/incidents/{inc.id}/status', json={'status': 'closed'}).get_json()['closed_at']
    assert c.patch(f'{API}/incidents/{inc.id}/status', json={'status': 'investigating'}).get_json()['closed_at'] is None


# ---------------------------------------------------------------------------
# GET /metrics/incidents (organization aggregates)
# ---------------------------------------------------------------------------

@pytest.fixture
def world(app, db, make_user, make_incident):
    """A fresh org with 5 critical/high incidents of known contain times.

    time_to_contain (h): critical 1, 2, 3, 4 and high 10 -> n=5, sorted
    [1,2,3,4,10]: median 3h, p90 (linear interpolation, position 3.6) 4h+0.6*6h = 7.6h.
    """
    from app.models import Organization
    org = Organization(name='metrics', slug=f'metrics-{uuid.uuid4().hex[:8]}', settings={})
    db.session.add(org)
    db.session.commit()
    admin = make_user(org, roles=['Administrator'])
    manager = make_user(org, roles=['Manager'])
    scoped = make_user(org, perms=['metrics:read', 'incidents:read'])   # no read_all: assigned incidents only
    viewer = make_user(org, roles=['Viewer'])
    start = datetime(2026, 3, 10, tzinfo=timezone.utc)
    tag = f'cls-{uuid.uuid4().hex[:8]}'     # unique classification: the database is shared
    incidents = []
    for hours, severity in ((1, 'critical'), (2, 'critical'), (3, 'critical'), (4, 'critical'), (10, 'high')):
        detected = start + timedelta(days=len(incidents))
        incidents.append(make_incident(
            org=org, creator=admin, severity=severity, detected_at=detected,
            contained_at=detected + timedelta(hours=hours), classification=tag if hours < 4 else None))
    archived = make_incident(org=org, creator=admin, severity='critical', is_archived=True, detected_at=start,
                             contained_at=start + timedelta(hours=100))
    # an incident with a legacy negative interval
    negative = make_incident(org=org, creator=admin, severity='low', detected_at=start + timedelta(days=6),
                             contained_at=start + timedelta(days=6) - timedelta(hours=1))
    return {'tag': tag, 'org': org, 'admin': admin, 'manager': manager, 'scoped': scoped, 'viewer': viewer,
            'incidents': incidents, 'archived': archived, 'negative': negative}


def _range(**extra):
    return {'from': '2026-03-01', 'to': '2026-03-31', **extra}


def test_org_metrics_median_and_p90_match_hand_computed_values(auth, world):
    resp = auth(world['admin']).get(f'{API}/metrics/incidents', query_string=_range())
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['group_by'] == 'none' and body['groups'] == []
    assert body['range']['date_field'] == 'detected_at'
    contain = body['overall']['metrics']['time_to_contain']
    assert contain['n'] == 5                       # archived incident excluded; negative one is not a value
    assert contain['median'] == 3 * 3600
    assert contain['p90'] == round(7.6 * 3600)
    assert contain['anomalies'] == 1               # the legacy negative interval is reported
    assert body['overall']['n'] == 6               # 5 + the negative one; archived excluded
    # no data -> n only, no noise
    assert body['overall']['metrics']['time_to_respond'] == {'median': None, 'p90': None, 'n': 0, 'anomalies': 0}


def test_org_metrics_group_by_severity_hides_small_groups(auth, world):
    body = auth(world['manager']).get(f'{API}/metrics/incidents', query_string=_range(group_by='severity')).get_json()
    groups = {g['key']: g for g in body['groups']}
    assert groups['critical']['n'] == 4
    assert groups['critical']['metrics']['time_to_contain']['median'] == round(2.5 * 3600)  # [1,2,3,4]
    assert groups['high']['n'] == 1
    assert groups['high']['metrics']['time_to_contain'] == {'median': None, 'p90': None, 'n': 1, 'anomalies': 0}
    assert groups['low']['n'] == 1
    assert groups['low']['metrics']['time_to_contain']['anomalies'] == 1


def test_org_metrics_group_by_classification_and_detection_source(auth, db, world):
    from app.models import IncidentReview
    c = auth(world['admin'])
    body = c.get(f'{API}/metrics/incidents', query_string=_range(group_by='classification')).get_json()
    assert {g['key']: g['n'] for g in body['groups']} == {world['tag']: 3, None: 3}
    inc = world['incidents'][0]
    db.session.add(IncidentReview(incident_id=inc.id, organization_id=world['org'].id, detection_source='threat_hunt'))
    db.session.commit()
    body = c.get(f'{API}/metrics/incidents', query_string=_range(group_by='detection_source')).get_json()
    assert {g['key']: g['n'] for g in body['groups']} == {'threat_hunt': 1, None: 5}


def test_org_metrics_date_field_and_range_filters(auth, world):
    c = auth(world['admin'])
    narrow = c.get(f'{API}/metrics/incidents', query_string={'from': '2026-03-10', 'to': '2026-03-11'}).get_json()
    assert narrow['overall']['n'] == 2          # a date-only `to` includes that whole day (days 10 and 11)
    assert narrow['range']['to'].startswith('2026-03-12')
    by_closed = c.get(f'{API}/metrics/incidents', query_string=_range(date_field='closed_at')).get_json()
    assert by_closed['overall']['n'] == 0       # nothing was closed


@pytest.mark.parametrize('params', [
    {},                                                           # from/to required
    {'from': '2026-03-01'},
    {'from': 'nope', 'to': '2026-03-31'},
    {'from': '2026-03-31', 'to': '2026-03-01'},
    {'from': '2024-01-01', 'to': '2026-03-31'},                   # > 731 days
    {'from': '2026-03-01', 'to': '2026-03-31', 'group_by': 'x'},
    {'from': '2026-03-01', 'to': '2026-03-31', 'date_field': 'created_at'},
])
def test_org_metrics_validates_parameters(auth, world, params):
    resp = auth(world['admin']).get(f'{API}/metrics/incidents', query_string=params)
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()['error'] == 'invalid_range'


def test_org_metrics_range_of_731_days_is_allowed(auth, world):
    resp = auth(world['admin']).get(f'{API}/metrics/incidents', query_string={'from': '2024-03-31', 'to': '2026-03-30'})
    assert resp.status_code == 200, resp.get_json()


def test_org_metrics_permission_and_visibility(auth, db, world, users, make_incident):
    assert auth(world['viewer']).get(f'{API}/metrics/incidents', query_string=_range()).status_code == 403
    assert auth(users['Analyst']).get(f'{API}/metrics/incidents', query_string=_range()).status_code == 403
    # metrics:read without incidents:read_all sees only incidents it is assigned to
    assert auth(world['scoped']).get(
        f'{API}/metrics/incidents', query_string=_range()).get_json()['overall']['n'] == 0
    from app.models import IncidentAssignment
    db.session.add(IncidentAssignment(incident_id=world['incidents'][0].id, user_id=world['scoped'].id))
    db.session.commit()
    body = auth(world['scoped']).get(f'{API}/metrics/incidents', query_string=_range()).get_json()
    assert body['overall']['n'] == 1
    assert body['overall']['metrics']['time_to_contain']['n'] == 1


def test_org_metrics_never_include_other_organizations(auth, world, users, make_incident, org_b):
    make_incident(org=org_b, creator=users['admin_b'], detected_at=datetime(2026, 3, 12, tzinfo=timezone.utc),
                  contained_at=datetime(2026, 3, 12, 5, tzinfo=timezone.utc), classification='org-b-only')
    theirs = auth(users['admin_b']).get(f'{API}/metrics/incidents',
                                        query_string=_range(group_by='classification')).get_json()
    keys = {g['key'] for g in theirs['groups']}
    assert 'org-b-only' in keys and world['tag'] not in keys
    mine = auth(world['admin']).get(f'{API}/metrics/incidents',
                                    query_string=_range(group_by='classification')).get_json()
    assert 'org-b-only' not in {g['key'] for g in mine['groups']}
    assert mine['overall']['n'] == 6


def test_org_metrics_dwell_uses_override_or_timeline(auth, db, world):
    inc = world['incidents'][0]
    _event(db, inc, world['admin'], inc.detected_at - timedelta(hours=7), is_ioc=True)
    inc2 = world['incidents'][1]
    inc2.first_malicious_at = inc2.detected_at - timedelta(hours=3)
    inc3 = world['incidents'][2]
    inc3.first_malicious_at = inc3.detected_at - timedelta(hours=5)
    db.session.commit()
    body = auth(world['admin']).get(f'{API}/metrics/incidents', query_string=_range()).get_json()
    dwell = body['overall']['metrics']['dwell_time']
    assert dwell['n'] == 3 and dwell['median'] == 5 * 3600     # [3h, 5h (overrides), 7h (timeline)]
    by_severity = auth(world['admin']).get(f'{API}/metrics/incidents',
                                           query_string=_range(group_by='severity')).get_json()
    critical = next(g for g in by_severity['groups'] if g['key'] == 'critical')
    assert critical['metrics']['dwell_time']['n'] == 3
