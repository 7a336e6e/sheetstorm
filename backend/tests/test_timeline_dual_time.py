"""W2-DFIR-A: dual-time timeline list (surface-dfir §3.2): sort by event or
detection time / dwell / confidence, confidence and has_detection filters,
UTC handling of datetime inputs."""
import pytest

API = '/api/v1'


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


@pytest.fixture
def timeline(admin, make_incident):
    inc = make_incident()
    url = f'{API}/incidents/{inc.id}/timeline'
    rows = [
        # activity, timestamp, detection_time, confidence
        ('a', '2026-10-01T10:00:00Z', '2026-10-03T10:00:00Z', 'low'),      # dwell 2d
        ('b', '2026-10-02T10:00:00Z', None, 'certain'),
        ('c', '2026-10-03T10:00:00Z', '2026-10-03T11:00:00Z', 'high'),     # dwell 1h
        ('d', '2026-10-04T10:00:00Z', '2026-10-01T09:00:00Z', None),       # negative dwell
    ]
    for activity, ts, det, conf in rows:
        r = admin.post(url, json={'timestamp': ts, 'activity': activity, 'detection_time': det,
                                  'confidence_level': conf, 'mitre_mappings': []})
        assert r.status_code == 201, r.get_json()
    return url


def _order(admin, url, query):
    r = admin.get(f'{url}?{query}')
    assert r.status_code == 200, r.get_json()
    return [e['activity'] for e in r.get_json()['items']]


def test_default_sort_is_event_time(admin, timeline):
    assert _order(admin, timeline, '') == ['a', 'b', 'c', 'd']
    assert _order(admin, timeline, 'sort=-timestamp') == ['d', 'c', 'b', 'a']


def test_detection_time_sort_nulls_last_both_ways(admin, timeline):
    assert _order(admin, timeline, 'sort=detection_time') == ['d', 'a', 'c', 'b']
    assert _order(admin, timeline, 'sort=-detection_time') == ['c', 'a', 'd', 'b']
    # legacy order= on a bare field
    assert _order(admin, timeline, 'sort=detection_time&order=desc') == ['c', 'a', 'd', 'b']


def test_dwell_and_confidence_sort(admin, timeline):
    assert _order(admin, timeline, 'sort=-dwell') == ['a', 'c', 'd', 'b']
    assert _order(admin, timeline, 'sort=dwell') == ['d', 'c', 'a', 'b']
    assert _order(admin, timeline, 'sort=-confidence') == ['b', 'c', 'a', 'd']


def test_confidence_filter(admin, timeline):
    assert _order(admin, timeline, 'confidence=high') == ['c']
    assert _order(admin, timeline, 'confidence=high,certain') == ['b', 'c']
    r = admin.get(f'{timeline}?confidence=sure')
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_filter'


def test_has_detection_filter(admin, timeline):
    assert _order(admin, timeline, 'has_detection=true') == ['a', 'c', 'd']
    assert _order(admin, timeline, 'has_detection=false') == ['b']
    r = admin.get(f'{timeline}?has_detection=maybe')
    assert r.status_code == 400


def test_invalid_sort_rejected(admin, timeline):
    r = admin.get(f'{timeline}?sort=activity')
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_sort'


def test_naive_and_offset_inputs_are_stored_as_utc(admin, make_incident):
    inc = make_incident()
    url = f'{API}/incidents/{inc.id}/timeline'
    r = admin.post(url, json={'timestamp': '2026-10-01T10:00:00', 'detection_time': '2026-10-01T14:00:00+02:00',
                              'activity': 'x', 'mitre_mappings': []})
    assert r.status_code == 201
    body = r.get_json()
    assert body['timestamp'].startswith('2026-10-01T10:00:00') and body['timestamp'].endswith('+00:00')
    assert body['detection_time'].startswith('2026-10-01T12:00:00')
    r = admin.post(url, json={'timestamp': 'yesterday-ish', 'activity': 'x'})
    assert r.status_code == 400
