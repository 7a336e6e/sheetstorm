"""W0-TIME: naive timestamps are UTC everywhere, offsets round-trip, and
users.preferences is an allowlisted, self-only, audited preference store."""
from datetime import datetime, timedelta, timezone

import pytest
from dateutil.parser import isoparse
from werkzeug.exceptions import BadRequest

from app.utils.validation import as_utc, parse_datetime

UTC_10 = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- parse_datetime

@pytest.mark.parametrize('value', [
    '2026-01-15T10:00:00',          # naive ISO -> UTC (not the DB session zone)
    '2026-01-15 10:00:00',
    '2026-01-15T10:00:00Z',
    '2026-01-15T10:00:00+00:00',
    '2026-01-15T12:00:00+02:00',    # offset is honoured
    '2026-01-15T05:00:00-05:00',
    datetime(2026, 1, 15, 10, 0),   # naive datetime object -> UTC
    datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
])
def test_parse_datetime_is_aware_and_utc_for_naive(value):
    parsed = parse_datetime(value, 'ts')
    assert parsed.tzinfo is not None
    assert parsed == UTC_10


def test_parse_datetime_keeps_the_given_offset():
    parsed = parse_datetime('2026-01-15T12:00:00+02:00', 'ts')
    assert parsed.utcoffset() == timedelta(hours=2)


@pytest.mark.parametrize('value', [None, ''])
def test_parse_datetime_empty(value):
    assert parse_datetime(value, 'ts') is None
    with pytest.raises(BadRequest):
        parse_datetime(value, 'ts', required=True)


@pytest.mark.parametrize('value', ['garbage', '2026-13-45T99:99', 42, ['2026-01-01']])
def test_parse_datetime_rejects_bad_input(value):
    with pytest.raises(BadRequest):
        parse_datetime(value, 'ts')


def test_as_utc():
    assert as_utc(None) is None
    assert as_utc(datetime(2026, 1, 15, 10)) == UTC_10
    aware = datetime(2026, 1, 15, 12, tzinfo=timezone(timedelta(hours=2)))
    assert as_utc(aware) is aware


def test_import_service_dates_are_utc():
    from app.services.import_service import ImportService
    assert ImportService._parse_date('2026-01-15 10:00:00') == UTC_10
    assert ImportService._parse_date(datetime(2026, 1, 15, 10)) == UTC_10
    assert ImportService._parse_date(None).tzinfo is not None


# ---------------------------------------------------------------- endpoints

@pytest.fixture
def inc(make_incident):
    return make_incident()


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


def _instant(iso):
    return isoparse(iso).astimezone(timezone.utc)


@pytest.mark.parametrize('sent', [
    '2026-01-15T10:00:00',
    '2026-01-15T10:00:00Z',
    '2026-01-15T12:00:00+02:00',
])
def test_timeline_event_time_is_stored_as_the_utc_instant(admin, inc, db, sent):
    from app.models import TimelineEvent
    resp = admin.post(f'/api/v1/incidents/{inc.id}/timeline', json={
        'activity': 'tz check', 'timestamp': sent, 'detection_time': sent})
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    # The API always answers with an explicit offset.
    assert body['timestamp'].endswith('+00:00')
    assert _instant(body['timestamp']) == UTC_10
    assert _instant(body['detection_time']) == UTC_10
    db.session.expire_all()
    stored = db.session.get(TimelineEvent, body['id'])
    assert stored.timestamp == UTC_10

    # Update round-trips the offset form the UI now sends (ISO with Z).
    url = f'/api/v1/incidents/{inc.id}/timeline/{body["id"]}'
    upd = admin.put(url, json={'timestamp': '2026-01-15T11:30:00.000Z'})
    assert upd.status_code == 200
    assert _instant(upd.get_json()['timestamp']) == UTC_10 + timedelta(minutes=90)


def test_host_first_seen_and_task_due_date_naive_are_utc(admin, inc):
    host = admin.post(f'/api/v1/incidents/{inc.id}/hosts', json={
        'hostname': 'tz-host', 'first_seen': '2026-01-15T10:00:00'}).get_json()
    assert _instant(host['first_seen']) == UTC_10
    task = admin.post(f'/api/v1/incidents/{inc.id}/tasks', json={
        'title': 'tz task', 'due_date': '2026-01-15T10:00:00'}).get_json()
    assert _instant(task['due_date']) == UTC_10
    # Re-sending the value exactly as the API returned it keeps it (no clearing).
    url = f'/api/v1/incidents/{inc.id}/hosts/{host["id"]}'
    again = admin.put(url, json={'first_seen': host['first_seen']}).get_json()
    assert _instant(again['first_seen']) == UTC_10


def test_ioc_and_malware_naive_times_are_utc_and_bad_values_400(admin, inc):
    base = f'/api/v1/incidents/{inc.id}'
    nioc = admin.post(f'{base}/network-iocs', json={
        'dns_ip': '203.0.113.9', 'timestamp': '2026-01-15T10:00:00'})
    assert nioc.status_code == 201
    assert _instant(nioc.get_json()['timestamp']) == UTC_10
    mal = admin.post(f'{base}/malware', json={
        'file_name': 'x.exe', 'creation_time': '2026-01-15T12:00:00+02:00'})
    assert mal.status_code == 201
    assert _instant(mal.get_json()['creation_time']) == UTC_10
    # Malformed timestamps are 400s now, not 500s.
    assert admin.post(f'{base}/network-iocs', json={
        'dns_ip': '203.0.113.10', 'timestamp': 'yesterday-ish'}).status_code == 400
    assert admin.put(f'{base}/malware/{mal.get_json()["id"]}', json={
        'modification_time': 'garbage'}).status_code == 400


def test_audit_log_date_filter_rejects_garbage(admin):
    assert admin.get('/api/v1/audit-logs?start_date=garbage').status_code == 400
    assert admin.get('/api/v1/audit-logs?start_date=2026-01-01T00:00:00').status_code == 200


# ---------------------------------------------------------------- preferences

PREFS_URL = '/api/v1/auth/me/preferences'


@pytest.fixture
def reset_prefs(app, db, users):
    yield
    from app.models import User
    db.session.rollback()
    for u in User.query.filter(User.id.in_([u.id for u in users.values()])):
        u.preferences = {}
    db.session.commit()


def test_me_returns_default_preferences(admin, reset_prefs):
    body = admin.get('/api/v1/auth/me').get_json()
    assert body['preferences'] == {}


@pytest.mark.parametrize('role', ['Administrator', 'Analyst', 'Viewer'])
def test_any_authenticated_user_can_set_own_display_timezone(users, auth, role, reset_prefs):
    client = auth(users[role])
    resp = client.patch(PREFS_URL, json={'display_timezone': 'utc'})
    assert resp.status_code == 200
    assert resp.get_json()['preferences'] == {'display_timezone': 'utc'}
    assert client.get('/api/v1/auth/me').get_json()['preferences'] == {'display_timezone': 'utc'}
    resp = client.patch(PREFS_URL, json={'display_timezone': 'local'})
    assert resp.get_json()['preferences'] == {'display_timezone': 'local'}


def test_preferences_only_touch_the_caller(users, auth, reset_prefs):
    auth(users['Analyst']).patch(PREFS_URL, json={'display_timezone': 'utc'})
    other = auth(users['admin_b']).get('/api/v1/auth/me').get_json()
    assert other['preferences'] == {}
    # No way to address another user: an id in the body is just an unknown key.
    resp = auth(users['Analyst']).patch(PREFS_URL, json={
        'display_timezone': 'local', 'user_id': str(users['admin_b'].id)})
    assert resp.status_code == 400


@pytest.mark.parametrize('body', [
    {'theme': 'dark'},                         # unknown key
    {'display_timezone': 'Europe/Berlin'},     # not in the allowlist
    {'display_timezone': None},
    {'display_timezone': 'UTC'},
    {},
    ['display_timezone'],
    'utc',
])
def test_preferences_validation(admin, body, reset_prefs):
    resp = admin.patch(PREFS_URL, json=body)
    assert resp.status_code == 400
    assert admin.get('/api/v1/auth/me').get_json()['preferences'] == {}


def test_preferences_require_authentication(app):
    resp = app.test_client().patch(PREFS_URL, json={'display_timezone': 'utc'})
    assert resp.status_code == 401


def test_preferences_cookie_auth_requires_csrf(app, users, auth, reset_prefs):
    client = auth(users['Viewer'], mode='cookie')
    ok = client.patch(PREFS_URL, json={'display_timezone': 'utc'})
    assert ok.status_code == 200
    # Same cookies, no CSRF header -> rejected.
    bare = client.client.open(PREFS_URL, method='PATCH', json={'display_timezone': 'local'})
    assert bare.status_code in (401, 422)


def test_disabled_user_cannot_set_preferences(users, auth, db, reset_prefs):
    user = users['Operator']
    client = auth(user)
    user.is_active = False
    db.session.commit()
    try:
        assert client.patch(PREFS_URL, json={'display_timezone': 'utc'}).status_code == 401
    finally:
        user.is_active = True
        db.session.commit()


def test_preferences_change_is_audited(admin, users, reset_prefs):
    from app.models import AuditLog
    uid = users['Administrator'].id
    before = AuditLog.query.filter_by(action='update_preferences', resource_id=uid).count()
    assert admin.patch(PREFS_URL, json={'display_timezone': 'utc'}).status_code == 200
    after = AuditLog.query.filter_by(action='update_preferences', resource_id=uid).count()
    assert after == before + 1
    row = AuditLog.query.filter_by(action='update_preferences', resource_id=uid) \
        .order_by(AuditLog.created_at.desc()).first()
    assert row.event_type == 'data_modification' and row.resource_type == 'user'
    assert row.user_id == uid
