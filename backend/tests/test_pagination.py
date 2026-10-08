"""Shared list contract (app/utils/pagination.py) and the list endpoints
converted to it: paging, whitelisted sort with id tie-break, escaped q /
search alias, declared filters, focus deep links, org scoping."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.datastructures import MultiDict

from app.utils.pagination import (
    ListArgsError, apply_filters, enum, escape_like, in_list, parse_list_args, parse_q,
)

SORTABLE = {'created_at': object(), 'title': object(), 'severity': object()}


def _args(**kw):
    return MultiDict(kw)


# ---------------------------------------------------------------------------
# Pure parsing (table-driven)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('params, page, per_page', [
    ({}, 1, 50),
    ({'page': '3', 'per_page': '25'}, 3, 25),
    ({'per_page': '0'}, 1, 1),
    ({'per_page': '500'}, 1, 200),
    ({'per_page': '-4'}, 1, 1),
    ({'page': '0'}, 1, 50),
    ({'page': '-2'}, 1, 50),
    ({'page': '', 'per_page': ''}, 1, 50),
])
def test_page_and_per_page(params, page, per_page):
    la = parse_list_args(sortable=SORTABLE, default_sort='-created_at', args=_args(**params))
    assert (la.page, la.per_page) == (page, per_page)


def test_max_per_page_override():
    la = parse_list_args(sortable=SORTABLE, default_sort='title', max_per_page=50,
                         args=_args(per_page='120'))
    assert la.per_page == 50


@pytest.mark.parametrize('params', [{'page': 'abc'}, {'per_page': '1.5'}, {'page': '2x'}])
def test_non_integer_paging_is_400(params):
    with pytest.raises(ListArgsError) as ei:
        parse_list_args(sortable=SORTABLE, default_sort='title', args=_args(**params))
    assert ei.value.code == 400


@pytest.mark.parametrize('params, expected', [
    ({}, (('created_at', True),)),
    ({'sort': 'title'}, (('title', False),)),
    ({'sort': '-title'}, (('title', True),)),
    ({'sort': '+title'}, (('title', False),)),
    ({'sort': '-severity, created_at'}, (('severity', True), ('created_at', False))),
    ({'sort': 'title', 'order': 'desc'}, (('title', True),)),
    ({'sort': 'title', 'order': 'ASC'}, (('title', False),)),
    ({'order': 'asc'}, (('created_at', False),)),           # applies to a single default field
    ({'sort': '-title', 'order': 'asc'}, (('title', True),)),  # explicit direction wins
    ({'sort': 'title,created_at', 'order': 'desc'}, (('title', False), ('created_at', False))),
])
def test_sort_parsing(params, expected):
    la = parse_list_args(sortable=SORTABLE, default_sort='-created_at', args=_args(**params))
    assert la.sort == expected


@pytest.mark.parametrize('sort', ['nope', '-password_hash', 'title,created_at,severity',
                                  'title,-title', ',', 'id'])
def test_invalid_sort_is_400_invalid_sort(sort):
    with pytest.raises(ListArgsError) as ei:
        parse_list_args(sortable=SORTABLE, default_sort='title', args=_args(sort=sort))
    assert ei.value.code == 400 and ei.value.name == 'invalid sort'


def test_invalid_order_is_400():
    with pytest.raises(ListArgsError):
        parse_list_args(sortable=SORTABLE, default_sort='title', args=_args(order='sideways'))


def test_sort_string_round_trips():
    la = parse_list_args(sortable=SORTABLE, default_sort='-severity,created_at', args=_args())
    assert la.sort_string == '-severity,created_at'


@pytest.mark.parametrize('params, expected', [
    ({}, None),
    ({'q': '  '}, None),
    ({'q': '  host01 '}, 'host01'),
    ({'search': 'legacy'}, 'legacy'),
    ({'q': 'new', 'search': 'legacy'}, 'new'),
    ({'q': 'a\x00b\x1fc\x7f'}, 'abc'),
    ({'q': 'x' * 200}, 'x' * 200),
])
def test_q_parsing(params, expected):
    assert parse_q(_args(**params)) == expected


def test_q_too_long_is_400():
    with pytest.raises(ListArgsError):
        parse_q(_args(q='x' * 201))


def test_q_min_length():
    with pytest.raises(ListArgsError):
        parse_q(_args(q='a'), min_length=2)


@pytest.mark.parametrize('raw, escaped', [
    ('abc', 'abc'),
    ('50%', '50\\%'),
    ('a_b', 'a\\_b'),
    ('C:\\Windows', 'C:\\\\Windows'),
    ('%_\\', '\\%\\_\\\\'),
])
def test_escape_like(raw, escaped):
    assert escape_like(raw) == escaped


def test_focus_must_be_uuid():
    with pytest.raises(ListArgsError):
        parse_list_args(sortable=SORTABLE, default_sort='title', args=_args(focus='not-a-uuid'))
    fid = uuid.uuid4()
    la = parse_list_args(sortable=SORTABLE, default_sort='title', args=_args(focus=str(fid)))
    assert la.focus == fid


@pytest.mark.parametrize('kind, raw', [
    ('int', 'x'),
    ('uuid', 'nope'),
    ('bool', 'maybe'),
    ('flag', 'perhaps'),
    ('date_from', 'not-a-date'),
    (enum(['low', 'high']), 'medium'),
    (in_list(['open', 'closed']), 'open,bogus'),
    (in_list(), ','),
])
def test_invalid_filter_values_are_400(app, db, kind, raw):
    from app.models import Incident
    with pytest.raises(Exception) as ei:
        apply_filters(db.session.query(Incident), {'f': (Incident.title, kind)}, _args(f=raw))
    assert getattr(ei.value, 'code', None) == 400


def test_empty_filter_values_are_ignored(app, db):
    from app.models import Incident
    q = db.session.query(Incident)
    assert apply_filters(q, {'f': (Incident.phase, 'int')}, _args(f='')) is q


# ---------------------------------------------------------------------------
# Endpoint fixtures
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
def populated(app, db, users, make_incident):
    """One incident with one row of every incident-scoped entity."""
    from app.models import (Artifact, CaseNote, CompromisedAccount, CompromisedHost, HostBasedIndicator,
                            MalwareTool, NetworkIndicator, Notification, Report, Task, TimelineEvent)
    admin = users['Administrator']
    inc = make_incident(title=f'Populated {uuid.uuid4().hex[:6]}')
    host = CompromisedHost(incident_id=inc.id, hostname='ws-01', ip_address='10.1.2.3', created_by=admin.id,
                           first_seen=_now())
    db.session.add(host)
    db.session.flush()
    db.session.add_all([
        TimelineEvent(incident_id=inc.id, timestamp=_now(), activity='ran powershell', created_by=admin.id),
        CompromisedAccount(incident_id=inc.id, datetime_seen=_now(), account_name='svc', account_type='domain',
                           created_by=admin.id),
        NetworkIndicator(incident_id=inc.id, dns_ip='1.2.3.4', created_by=admin.id, timestamp=_now()),
        HostBasedIndicator(incident_id=inc.id, artifact_type='file', artifact_value='c:\\evil.exe',
                           created_by=admin.id, datetime=_now()),
        MalwareTool(incident_id=inc.id, file_name='evil.exe', created_by=admin.id),
        CaseNote(incident_id=inc.id, title='note', content='body', created_by=admin.id),
        Task(incident_id=inc.id, title='task', created_by=admin.id),
        Artifact(incident_id=inc.id, filename='f', original_filename='f.bin', storage_path='x', file_size=1,
                 md5='0' * 32, sha256='0' * 64, sha512='0' * 128, uploaded_by=admin.id),
        Report(incident_id=inc.id, title='r', report_type='full', generated_by=admin.id),
        Notification(user_id=admin.id, incident_id=inc.id, type='incident_assigned', title='n'),
    ])
    db.session.commit()
    return inc


ENDPOINTS = [
    # (path template, default sort)
    ('/api/v1/incidents', '-created_at'),
    ('/api/v1/incidents/archived', '-archived_at'),
    ('/api/v1/users', '-created_at'),
    ('/api/v1/notifications', '-created_at'),
    ('/api/v1/incidents/{iid}/timeline', 'timestamp'),
    ('/api/v1/incidents/{iid}/hosts', '-first_seen'),
    ('/api/v1/incidents/{iid}/accounts', '-datetime_seen'),
    ('/api/v1/incidents/{iid}/network-iocs', '-timestamp'),
    ('/api/v1/incidents/{iid}/host-iocs', '-datetime'),
    ('/api/v1/incidents/{iid}/malware', '-created_at'),
    ('/api/v1/incidents/{iid}/case-notes', '-is_pinned,-created_at'),
    ('/api/v1/incidents/{iid}/tasks', 'order_index,-created_at'),
    ('/api/v1/incidents/{iid}/artifacts', '-created_at'),
    ('/api/v1/incidents/{iid}/reports', '-created_at'),
]


@pytest.mark.parametrize('path, default_sort', ENDPOINTS)
def test_envelope_on_every_converted_endpoint(auth, users, populated, path, default_sort):
    c = auth(users['Administrator'])
    url = path.format(iid=populated.id)
    r = c.get(url)
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert {'items', 'total', 'page', 'per_page', 'pages', 'sort'} <= set(body)
    assert body['per_page'] == 50 and body['page'] == 1
    assert body['sort'] == default_sort
    if '{iid}' in path:
        assert body['total'] == 1 and len(body['items']) == 1

    r = c.get(url, query_string={'sort': 'definitely_not_a_column'})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_sort'
    r = c.get(url, query_string={'page': 'x'})
    assert r.status_code == 400
    r = c.get(url, query_string={'per_page': '1000'})
    assert r.status_code == 200 and r.get_json()['per_page'] == 200


def test_notifications_keep_unread_count_and_unread_only(auth, users, populated):
    body = auth(users['Administrator']).get('/api/v1/notifications?unread_only=true').get_json()
    assert body['unread_count'] >= 1
    assert all(not n['is_read'] for n in body['items'])
    r = auth(users['Administrator']).get('/api/v1/notifications?unread_only=sometimes')
    assert r.status_code == 400


def _hosts(db, inc, admin, names, **fields):
    from app.models import CompromisedHost
    rows = [CompromisedHost(incident_id=inc.id, hostname=n, created_by=admin.id, **fields) for n in names]
    db.session.add_all(rows)
    db.session.commit()
    return rows


def test_tie_break_gives_disjoint_complete_pages(app, db, auth, users, make_incident):
    admin = users['Administrator']
    inc = make_incident()
    same = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = _hosts(db, inc, admin, [f'tie-{i:03d}' for i in range(100)], first_seen=same)
    c = auth(admin)
    seen = []
    for page in range(1, 5):
        body = c.get(f'/api/v1/incidents/{inc.id}/hosts',
                     query_string={'sort': 'first_seen', 'per_page': 30, 'page': page}).get_json()
        assert body['pages'] == 4 and body['total'] == 100
        seen.extend(h['id'] for h in body['items'])
    assert len(seen) == 100 and set(seen) == {str(h.id) for h in rows}
    assert seen == sorted(seen)  # id is the tie-breaker


def test_sort_desc_and_nulls_last(app, db, auth, users, make_incident):
    admin = users['Administrator']
    inc = make_incident()
    _hosts(db, inc, admin, ['b-host', 'a-host', 'c-host'])
    _hosts(db, inc, admin, ['z-null'], first_seen=None)
    _hosts(db, inc, admin, ['dated'], first_seen=_now())
    c = auth(admin)
    names = [h['hostname'] for h in c.get(f'/api/v1/incidents/{inc.id}/hosts?sort=-hostname').get_json()['items']]
    assert names == sorted(names, reverse=True)
    names = [h['hostname'] for h in c.get(f'/api/v1/incidents/{inc.id}/hosts?sort=-first_seen').get_json()['items']]
    assert names[0] == 'dated'


def test_q_matches_wildcards_literally_and_search_alias(app, db, auth, users, make_incident):
    admin = users['Administrator']
    inc = make_incident()
    _hosts(db, inc, admin, ['a%b', 'aXb', 'a_c', 'abc', 'back\\slash', 'backXslash'])
    c = auth(admin)

    def names(**qs):
        body = c.get(f'/api/v1/incidents/{inc.id}/hosts', query_string=qs).get_json()
        return sorted(h['hostname'] for h in body['items'])

    assert names(q='a%b') == ['a%b']
    assert names(q='a_c') == ['a_c']
    assert names(q='k\\s') == ['back\\slash']
    assert names(search='a%b') == ['a%b']  # legacy alias
    assert names(q='A%B') == ['a%b']        # case-insensitive
    r = c.get(f'/api/v1/incidents/{inc.id}/hosts', query_string={'q': 'x' * 201})
    assert r.status_code == 400


def test_host_q_covers_ip(app, db, auth, users, make_incident):
    admin = users['Administrator']
    inc = make_incident()
    _hosts(db, inc, admin, ['ip-host'], ip_address='192.168.77.5')
    _hosts(db, inc, admin, ['other-host'])
    body = auth(admin).get(f'/api/v1/incidents/{inc.id}/hosts?q=168.77').get_json()
    assert [h['hostname'] for h in body['items']] == ['ip-host']


def test_focus_returns_the_page_containing_the_row(app, db, auth, users, make_incident):
    admin = users['Administrator']
    inc = make_incident()
    rows = _hosts(db, inc, admin, [f'f-{i:03d}' for i in range(120)], containment_status='active')
    target = next(h for h in rows if h.hostname == 'f-074')  # 75th by hostname
    c = auth(admin)
    url = f'/api/v1/incidents/{inc.id}/hosts'

    body = c.get(url, query_string={'sort': 'hostname', 'focus': str(target.id)}).get_json()
    assert body['focus_found'] is True and body['page'] == 2
    assert str(target.id) in [h['id'] for h in body['items']]

    body = c.get(url, query_string={'sort': '-hostname', 'per_page': 10, 'focus': str(target.id)}).get_json()
    assert body['focus_found'] is True and body['page'] == 5  # 46th descending

    # Filtered out -> requested page, focus_found false.
    body = c.get(url, query_string={'containment_status': 'isolated', 'focus': str(target.id),
                                    'page': 1}).get_json()
    assert body['focus_found'] is False and body['page'] == 1 and body['total'] == 0

    # No focus param -> no focus_found key.
    assert 'focus_found' not in c.get(url).get_json()


def test_focus_never_finds_rows_of_another_org(app, db, auth, users, org_b, make_incident):
    inc_a = make_incident()
    inc_b = make_incident(org=org_b)
    other = _hosts(db, inc_b, users['admin_b'], ['b-secret'])[0]
    _hosts(db, inc_a, users['Administrator'], ['a-host'])
    body = auth(users['Administrator']).get(
        f'/api/v1/incidents/{inc_a.id}/hosts', query_string={'focus': str(other.id)}).get_json()
    assert body['focus_found'] is False
    assert [h['hostname'] for h in body['items']] == ['a-host']
    # Incident-level focus across orgs.
    body = auth(users['Administrator']).get('/api/v1/incidents', query_string={'focus': str(inc_b.id)}).get_json()
    assert body['focus_found'] is False


def test_incidents_filters_sort_and_scoping(app, db, auth, users, org_b, make_incident):
    tag = uuid.uuid4().hex[:8]
    crit = make_incident(title=f'{tag} crit', severity='critical', status='investigating')
    make_incident(title=f'{tag} low', severity='low', status='open')
    make_incident(title=f'{tag} high', severity='high', status='closed')
    make_incident(org=org_b, title=f'{tag} other org', severity='critical')
    c = auth(users['Administrator'])

    body = c.get('/api/v1/incidents', query_string={'q': tag, 'sort': '-severity'}).get_json()
    assert [i['severity'] for i in body['items']] == ['critical', 'high', 'low']
    assert body['total'] == 3  # org B excluded

    body = c.get('/api/v1/incidents', query_string={'q': tag, 'status': 'open,investigating'}).get_json()
    assert {i['title'] for i in body['items']} == {f'{tag} crit', f'{tag} low'}

    body = c.get('/api/v1/incidents', query_string={'search': tag, 'severity': 'critical'}).get_json()
    assert [i['id'] for i in body['items']] == [str(crit.id)]

    r = c.get('/api/v1/incidents', query_string={'severity': 'catastrophic'})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_filter'
    r = c.get('/api/v1/incidents', query_string={'team_id': 'nope'})
    assert r.status_code == 400

    body = c.get('/api/v1/incidents', query_string={'q': tag, 'sort': 'title', 'order': 'desc'}).get_json()
    titles = [i['title'] for i in body['items']]
    assert titles == sorted(titles, reverse=True)


def test_incidents_list_respects_visibility(app, auth, users, make_incident):
    tag = uuid.uuid4().hex[:8]
    make_incident(title=f'{tag} amber')
    white = make_incident(title=f'{tag} white', tlp='white')
    body = auth(users['Viewer']).get('/api/v1/incidents', query_string={'q': tag}).get_json()
    assert [i['id'] for i in body['items']] == [str(white.id)]


def test_users_list_scoped_searchable_sortable(app, auth, users):
    c = auth(users['Administrator'])
    body = c.get('/api/v1/users', query_string={'q': 'admin', 'per_page': 200}).get_json()
    emails = {u['email'] for u in body['items']}
    assert 'administrator@a.test' in emails and 'admin@b.test' not in emails

    body = c.get('/api/v1/users', query_string={'sort': 'email', 'per_page': 200, 'q': '@a.test'}).get_json()
    emails = [u['email'] for u in body['items']]
    assert emails == sorted(emails)

    body = c.get('/api/v1/users', query_string={'role': 'Viewer', 'is_active': 'true'}).get_json()
    assert [u['email'] for u in body['items']] == ['viewer@a.test']

    # `_` is literal, not a single-char wildcard.
    body = c.get('/api/v1/users', query_string={'q': 'incident_responder'}).get_json()
    assert [u['email'] for u in body['items']] == ['incident_responder@a.test']
    body = c.get('/api/v1/users', query_string={'q': 'incidentXresponder'}).get_json()
    assert body['total'] == 0

    assert c.get('/api/v1/users?is_active=perhaps').status_code == 400


def test_timeline_filters(app, db, auth, users, make_incident):
    from app.models import TimelineEvent
    admin = users['Administrator']
    inc = make_incident()
    base = datetime(2026, 3, 1, tzinfo=timezone.utc)
    db.session.add_all([
        TimelineEvent(incident_id=inc.id, timestamp=base + timedelta(hours=i), activity=f'event {i}',
                      hostname='dc01' if i % 2 else 'ws_02', is_key_event=(i == 3), created_by=admin.id)
        for i in range(6)
    ])
    db.session.commit()
    c = auth(admin)
    url = f'/api/v1/incidents/{inc.id}/timeline'

    body = c.get(url).get_json()
    assert [e['activity'] for e in body['items']] == [f'event {i}' for i in range(6)]
    body = c.get(url, query_string={'start_date': (base + timedelta(hours=2)).isoformat(),
                                    'end_date': (base + timedelta(hours=4)).isoformat()}).get_json()
    assert body['total'] == 3
    assert c.get(url, query_string={'key_only': 'true'}).get_json()['total'] == 1
    assert c.get(url, query_string={'key_only': 'false'}).get_json()['total'] == 6
    assert c.get(url, query_string={'hostname': 'ws_0'}).get_json()['total'] == 3
    assert c.get(url, query_string={'hostname': 'wsX0'}).get_json()['total'] == 0
    assert c.get(url, query_string={'q': 'event 5'}).get_json()['total'] == 1
    assert c.get(url, query_string={'host_id': 'bad'}).status_code == 400
    assert c.get(url, query_string={'start_date': 'yesterday-ish'}).status_code == 400


def test_case_notes_pinned_first(app, db, auth, users, make_incident):
    from app.models import CaseNote
    admin = users['Administrator']
    inc = make_incident()
    db.session.add_all([
        CaseNote(incident_id=inc.id, title='old pinned', content='x', is_pinned=True, created_by=admin.id,
                 created_at=_now() - timedelta(days=2)),
        CaseNote(incident_id=inc.id, title='new', content='x', created_by=admin.id),
        CaseNote(incident_id=inc.id, title='archived', content='x', is_archived=True, created_by=admin.id),
    ])
    db.session.commit()
    body = auth(admin).get(f'/api/v1/incidents/{inc.id}/case-notes').get_json()
    assert [n['title'] for n in body['items']] == ['old pinned', 'new']
    assert body['pages'] == 1


def test_tasks_priority_sort(app, db, auth, users, make_incident):
    from app.models import Task
    admin = users['Administrator']
    inc = make_incident()
    for p in ['low', 'critical', 'medium', 'high']:
        db.session.add(Task(incident_id=inc.id, title=p, priority=p, created_by=admin.id))
    db.session.commit()
    body = auth(admin).get(f'/api/v1/incidents/{inc.id}/tasks?sort=-priority').get_json()
    assert [t['priority'] for t in body['items']] == ['critical', 'high', 'medium', 'low']


def test_reports_now_paginated(app, db, auth, users, make_incident):
    from app.models import Report
    admin = users['Administrator']
    inc = make_incident()
    db.session.add_all([Report(incident_id=inc.id, title=f'r{i}', report_type='full', generated_by=admin.id)
                        for i in range(7)])
    db.session.commit()
    body = auth(admin).get(f'/api/v1/incidents/{inc.id}/reports?per_page=5&page=2').get_json()
    assert body['total'] == 7 and body['pages'] == 2 and len(body['items']) == 2


def test_incident_scoped_lists_still_enforce_access(app, auth, users, make_incident, org_b):
    inc = make_incident()  # amber, not assigned to the viewer
    assert auth(users['Viewer']).get(f'/api/v1/incidents/{inc.id}/hosts').status_code == 403
    other = make_incident(org=org_b)
    assert auth(users['Administrator']).get(f'/api/v1/incidents/{other.id}/hosts').status_code == 404
