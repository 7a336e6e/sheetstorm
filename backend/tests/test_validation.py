"""Item 8: malformed DFIR fields are 400s (not 500s); explicit nulls on NOT
NULL fields fall back to defaults; model nullability matches the DB."""
import pytest


@pytest.fixture
def inc(make_incident):
    return make_incident()


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


@pytest.mark.parametrize('body', [
    {'title': 't', 'task_type': 'bogus'},
    {'title': 't', 'lead_outcome': 'bogus'},
    {'title': 't', 'due_date': 'not-a-date'},
    {'title': 't', 'due_date': 42},
    {'title': 't', 'priority': 'urgent'},
    {'title': 7},
])
def test_task_create_rejects_bad_fields(admin, inc, body):
    assert admin.post(f'/api/v1/incidents/{inc.id}/tasks', json=body).status_code == 400


def test_task_body_must_be_object(admin, inc):
    assert admin.post(f'/api/v1/incidents/{inc.id}/tasks', json=['x']).status_code == 400


def test_task_update_validation_and_null_defaults(admin, inc):
    task = admin.post(f'/api/v1/incidents/{inc.id}/tasks', json={
        'title': 't', 'task_type': 'investigative_lead', 'lead_outcome': 'inconclusive'}).get_json()
    url = f'/api/v1/incidents/{inc.id}/tasks/{task["id"]}'
    assert admin.put(url, json={'task_type': 'bogus'}).status_code == 400
    assert admin.put(url, json={'lead_outcome': 'bogus'}).status_code == 400
    assert admin.put(url, json={'due_date': 'garbage'}).status_code == 400
    ok = admin.put(url, json={'task_type': None, 'lead_outcome': None, 'due_date': None})
    assert ok.status_code == 200
    assert ok.get_json()['task_type'] == 'action_item' and ok.get_json()['lead_outcome'] is None


def test_host_triage_validation(admin, inc):
    base = f'/api/v1/incidents/{inc.id}/hosts'
    assert admin.post(base, json={'hostname': 'h', 'triage_status': 'bogus'}).status_code == 400
    assert admin.post(base, json={'hostname': 'h', 'first_seen': 'yesterday-ish'}).status_code == 400
    host = admin.post(base, json={'hostname': 'h', 'triage_status': None}).get_json()
    assert host['triage_status'] == 'under_analysis'
    url = f'{base}/{host["id"]}'
    assert admin.put(url, json={'triage_status': 'bogus'}).status_code == 400
    assert admin.put(url, json={'last_seen': 'garbage'}).status_code == 400
    assert admin.put(url, json={'triage_status': None}).get_json()['triage_status'] == 'under_analysis'
    assert admin.put(url, json={'triage_status': 'compromised'}).get_json()['triage_status'] == 'compromised'


@pytest.mark.parametrize('body', [
    {'activity': 'a', 'timestamp': 'garbage'},
    {'activity': 'a'},
    {'activity': 'a', 'timestamp': '2026-01-01T00:00:00Z', 'detection_time': 'garbage'},
    {'activity': 'a', 'timestamp': '2026-01-01T00:00:00Z', 'confidence_level': 'very'},
    {'activity': 'a', 'timestamp': '2026-01-01T00:00:00Z', 'mitre_mappings': 'T1059'},
])
def test_timeline_create_rejects_bad_fields(admin, inc, body):
    assert admin.post(f'/api/v1/incidents/{inc.id}/timeline', json=body).status_code == 400


def test_timeline_update_validation(admin, inc):
    ev = admin.post(f'/api/v1/incidents/{inc.id}/timeline', json={
        'activity': 'a', 'timestamp': '2026-01-01T00:00:00Z', 'confidence_level': 'high',
        'detection_time': '2026-01-02T00:00:00Z'}).get_json()
    url = f'/api/v1/incidents/{inc.id}/timeline/{ev["id"]}'
    assert admin.put(url, json={'detection_time': 'garbage'}).status_code == 400
    assert admin.put(url, json={'confidence_level': 'very'}).status_code == 400
    assert admin.put(url, json={'timestamp': None}).status_code == 400
    ok = admin.put(url, json={'detection_time': None, 'confidence_level': None})
    assert ok.status_code == 200 and ok.get_json()['confidence_level'] is None


def test_timeline_list_bad_date_filter(admin, inc):
    assert admin.get(f'/api/v1/incidents/{inc.id}/timeline?start_date=garbage').status_code == 400


def test_account_datetime_seen_null_is_400(admin, inc):
    acct = admin.post(f'/api/v1/incidents/{inc.id}/accounts', json={
        'account_name': 'svc', 'account_type': 'service', 'datetime_seen': '2026-01-01T00:00:00Z'})
    assert acct.status_code == 201
    url = f'/api/v1/incidents/{inc.id}/accounts/{acct.get_json()["id"]}'
    assert admin.put(url, json={'datetime_seen': None}).status_code == 400


def test_model_nullability_matches_db(app):
    from app.models import Task, CompromisedHost
    assert Task.__table__.c.task_type.nullable is False
    assert CompromisedHost.__table__.c.triage_status.nullable is False
