"""Global search (/search, services/search_service.py): visibility and
per-type permission gates, escaping, facets/paging, relevance, deep links,
rate limit, and parity between the query and the pg_trgm indexes."""
import importlib.util
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tag():
    return 'tok' + uuid.uuid4().hex[:10]


def _search(client, **qs):
    r = client.get('/api/v1/search', query_string=qs)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _add(db, *objs):
    db.session.add_all(objs)
    db.session.commit()
    return objs


@pytest.fixture
def make_user(app, db, org_a):
    """make_user(permissions) -> User in org A holding a custom role with exactly those permissions."""
    from app.models import Role, User, UserRole

    def make(perms):
        role = Role(name=f'search-test-{uuid.uuid4().hex[:8]}', permissions=list(perms))
        user = User(email=f'{uuid.uuid4().hex[:8]}@a.test', name='custom', organization_id=org_a.id,
                    auth_provider='local', is_active=True, is_verified=True)
        user.set_password('Sup3r-Secret-Passw0rd!')
        db.session.add_all([role, user])
        db.session.flush()
        db.session.add(UserRole(user_id=user.id, role_id=role.id, organization_id=org_a.id))
        db.session.commit()
        return user
    return make


@pytest.fixture
def entities(app, db, users, make_incident):
    """One incident whose every entity type contains a fresh token."""
    from app.models import (CaseNote, CompromisedAccount, CompromisedHost, HostBasedIndicator, MalwareTool,
                            NetworkIndicator, TimelineEvent)
    from app.services.encryption_service import encryption_service
    tag = _tag()
    admin = users['Administrator']
    inc = make_incident(title=f'Incident {tag}')
    now = datetime.now(timezone.utc)
    host = CompromisedHost(incident_id=inc.id, hostname=f'host-{tag}', ip_address='10.9.8.7', created_by=admin.id)
    _add(db, host)
    _add(db,
         TimelineEvent(incident_id=inc.id, timestamp=now, activity=f'ran {tag}', hostname='dc01',
                       created_by=admin.id),
         CompromisedAccount(incident_id=inc.id, datetime_seen=now, account_name=f'svc-{tag}', domain='CORP',
                            account_type='domain', created_by=admin.id,
                            password_encrypted=encryption_service.encrypt('Hunter2!')),
         NetworkIndicator(incident_id=inc.id, dns_ip=f'{tag}.example.com', created_by=admin.id),
         HostBasedIndicator(incident_id=inc.id, artifact_type='file', artifact_value=f'C:\\{tag}.exe',
                            created_by=admin.id),
         MalwareTool(incident_id=inc.id, file_name=f'{tag}.dll', md5='a' * 32, created_by=admin.id),
         CaseNote(incident_id=inc.id, title=f'note {tag}', content='content', created_by=admin.id),
         CaseNote(incident_id=inc.id, title=f'archived {tag}', content='x', is_archived=True,
                  created_by=admin.id))
    return tag, inc


ALL_TYPES = {'incident', 'timeline_event', 'host', 'account', 'network_ioc', 'host_ioc', 'malware', 'case_note'}
TABS = {'incident': 'overview', 'timeline_event': 'events', 'host': 'hosts', 'account': 'accounts',
        'network_ioc': 'network', 'host_ioc': 'host-iocs', 'malware': 'malware', 'case_note': 'notes'}


def test_every_type_found_with_ids_links_and_facets(auth, users, entities):
    tag, inc = entities
    body = _search(auth(users['Administrator']), q=tag)
    assert {r['type'] for r in body['results']} == ALL_TYPES
    assert body['total'] == 8 == sum(body['facets'].values())  # archived note excluded
    assert body['facets'] == {t: 1 for t in ALL_TYPES}
    assert body['pages'] == 1 and body['sort'] == 'relevance'
    for r in body['results']:
        uuid.UUID(r['id'])
        assert r['incident_id'] == str(inc.id)
        assert r['incident_title'] == inc.title
        assert r['link'] == {'incident_id': str(inc.id), 'tab': TABS[r['type']],
                             'row': None if r['type'] == 'incident' else r['id']}
        assert not any('password' in k for k in r)
        assert 'Hunter2' not in str(r)
    by_type = {r['type']: r for r in body['results']}
    assert by_type['account']['title'] == f'CORP\\svc-{tag}'
    assert by_type['host']['title'] == f'host-{tag} (10.9.8.7)'
    assert by_type['timeline_event']['hostname'] == 'dc01'


def test_org_isolation(app, db, auth, users, org_b, make_incident):
    tag = _tag()
    make_incident(title=f'A {tag}')
    make_incident(org=org_b, title=f'B {tag}')
    body = _search(auth(users['Administrator']), q=tag)
    assert [r['title'] for r in body['results']] == [f'A {tag}']
    body = _search(auth(users['admin_b']), q=tag)
    assert [r['title'] for r in body['results']] == [f'B {tag}']


def test_viewer_sees_only_assigned_and_tlp_white(app, auth, users, make_incident):
    tag = _tag()
    make_incident(title=f'amber {tag}')
    white = make_incident(title=f'white {tag}', tlp='white')
    assigned = make_incident(title=f'assigned {tag}', assign=[users['Viewer']])
    body = _search(auth(users['Viewer']), q=tag)
    assert {r['incident_id'] for r in body['results']} == {str(white.id), str(assigned.id)}


def test_types_without_read_permission_are_dropped(auth, entities, make_user):
    tag, _ = entities
    user = make_user(['incidents:read', 'hosts:read'])
    body = _search(auth(user), q=tag)
    # case notes ride on incidents:read, like the case-notes tab.
    assert {r['type'] for r in body['results']} == {'incident', 'host', 'case_note'}
    assert set(body['facets']) == {'incident', 'host', 'case_note'}
    # Asking explicitly for a forbidden type returns nothing, not a leak.
    body = _search(auth(user), q=tag, types='accounts,malware')
    assert body['results'] == [] and body['total'] == 0 and body['facets'] == {}


def test_search_requires_incidents_read(auth, make_user):
    user = make_user(['hosts:read'])
    assert auth(user).get('/api/v1/search?q=anything').status_code == 403


def test_types_param_accepts_plural_and_result_names(auth, users, entities):
    tag, _ = entities
    c = auth(users['Administrator'])
    assert {r['type'] for r in _search(c, q=tag, types='hosts,malware')['results']} == {'host', 'malware'}
    assert {r['type'] for r in _search(c, q=tag, types='host_ioc,case_note')['results']} == {'host_ioc', 'case_note'}
    assert _search(c, q=tag, types='bogus')['total'] == 0


def test_incident_id_scope_and_404(app, auth, users, entities, org_b, make_incident):
    tag, inc = entities
    other = make_incident(title=f'other {tag}')
    c = auth(users['Administrator'])
    body = _search(c, q=tag, incident_id=str(inc.id))
    assert {r['incident_id'] for r in body['results']} == {str(inc.id)}
    assert _search(c, q=tag, incident_id=str(other.id))['total'] == 1

    foreign = make_incident(org=org_b)
    assert c.get('/api/v1/search', query_string={'q': tag, 'incident_id': str(foreign.id)}).status_code == 404
    hidden = make_incident()  # amber, viewer not assigned
    r = auth(users['Viewer']).get('/api/v1/search', query_string={'q': tag, 'incident_id': str(hidden.id)})
    assert r.status_code == 404
    assert c.get('/api/v1/search', query_string={'q': tag, 'incident_id': 'nope'}).status_code == 400


def test_like_wildcards_are_literal(app, db, auth, users, make_incident):
    from app.models import CompromisedHost
    tag = _tag()
    admin = users['Administrator']
    inc = make_incident()
    _add(db, *[CompromisedHost(incident_id=inc.id, hostname=f'{tag}{s}', created_by=admin.id)
               for s in ['-50%_off', '-50xyoff', '-a\\b', '-aXb']])
    c = auth(admin)

    def titles(q):
        return sorted(r['title'] for r in _search(c, q=q)['results'])

    assert titles(f'{tag}-50%_off') == [f'{tag}-50%_off']
    assert titles(f'{tag}-a\\b') == [f'{tag}-a\\b']
    assert titles(f'{tag}-50') == [f'{tag}-50%_off', f'{tag}-50xyoff']
    assert all('%_' in t for t in titles('%_'))


def test_paging_across_types_is_complete(auth, users, entities):
    tag, _ = entities
    c = auth(users['Administrator'])
    seen = []
    for page in range(1, 5):
        body = _search(c, q=tag, per_page=2, page=page)
        assert body['total'] == 8 and body['pages'] == 4 and body['facets']['host'] == 1
        seen.extend((r['type'], r['id']) for r in body['results'])
    assert len(seen) == 8 and len(set(seen)) == 8
    beyond = _search(c, q=tag, per_page=2, page=9)
    assert beyond['results'] == [] and beyond['total'] == 8 and sum(beyond['facets'].values()) == 8


def test_per_page_capped_at_50(auth, users):
    body = _search(auth(users['Administrator']), q='zz-nothing-matches', per_page=500)
    assert body['per_page'] == 50 and body['total'] == 0 and body['facets'] == {}


def test_relevance_exact_then_prefix_then_recent(app, db, auth, users, make_incident):
    tag = _tag()
    contains = make_incident(title=f'old contains {tag}')
    prefix = make_incident(title=f'{tag} prefix')
    exact = make_incident(title=tag.upper())  # exact, case-insensitive
    body = _search(auth(users['Administrator']), q=tag, types='incidents')
    assert [r['id'] for r in body['results']] == [str(exact.id), str(prefix.id), str(contains.id)]


def test_timestamp_sorts_and_since_until(app, db, auth, users, make_incident):
    from app.models import TimelineEvent
    tag = _tag()
    admin = users['Administrator']
    inc = make_incident()
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    _add(db, *[TimelineEvent(incident_id=inc.id, timestamp=base + timedelta(days=i), activity=f'{tag} {i}',
                             created_by=admin.id) for i in range(4)])
    c = auth(admin)
    asc = [r['title'] for r in _search(c, q=tag, sort='timestamp')['results']]
    assert asc == [f'{tag} {i}' for i in range(4)]
    desc = [r['title'] for r in _search(c, q=tag, sort='-timestamp')['results']]
    assert desc == list(reversed(asc))
    body = _search(c, q=tag, since=(base + timedelta(days=1)).isoformat(),
                   until=(base + timedelta(days=2)).isoformat())
    assert sorted(r['title'] for r in body['results']) == [f'{tag} 1', f'{tag} 2']


@pytest.mark.parametrize('qs, code', [
    ({'q': 'a'}, 'bad_request'),
    ({}, 'bad_request'),
    ({'q': 'x' * 201}, 'bad_request'),
    ({'q': 'valid', 'sort': 'title'}, 'invalid_sort'),
    ({'q': 'valid', 'page': 'two'}, 'bad_request'),
    ({'q': 'valid', 'since': 'whenever'}, 'bad_request'),
])
def test_bad_params_are_400(auth, users, qs, code):
    r = auth(users['Administrator']).get('/api/v1/search', query_string=qs)
    assert r.status_code == 400 and r.get_json()['error'] == code


def test_control_chars_are_stripped(app, db, auth, users, make_incident):
    tag = _tag()
    make_incident(title=f'ctl {tag}')
    assert _search(auth(users['Administrator']), q=f'\x00{tag}\x07')['total'] == 1


_RATE_LIMIT_SCRIPT = """
import sys
import app.config as config
config.TestingConfig.RATELIMIT_ENABLED = True
from app import create_app, limiter
from app.models import User
application = create_app('testing')
with application.app_context():
    from app.api.v1.endpoints.auth import issue_tokens
    user = User.query.filter_by(email='analyst@a.test').one()
    token, _ = issue_tokens(user)
    limiter.reset()
    client = application.test_client()
    codes = [client.get('/api/v1/search?q=ratelimit', headers={'Authorization': 'Bearer ' + token}).status_code
             for _ in range(61)]
    limiter.reset()
print(','.join(map(str, codes)))
"""


def test_rate_limit_61st_call_is_429(app):
    # The suite runs with the limiter disabled and Flask-Limiter is a
    # process-wide singleton, so exercise it in a separate interpreter.
    import subprocess
    import sys
    r = subprocess.run([sys.executable, '-c', _RATE_LIMIT_SCRIPT], cwd=BACKEND_DIR, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-3000:]
    codes = r.stdout.strip().splitlines()[-1].split(',')
    assert codes[:60] == ['200'] * 60
    assert codes[60] == '429'


# ---------------------------------------------------------------------------
# Index parity: the query expression is the indexed expression
# ---------------------------------------------------------------------------

def _migration():
    path = os.path.join(BACKEND_DIR, 'migrations', 'versions', 'add_search_trgm_indexes.py')
    spec = importlib.util.spec_from_file_location('add_search_trgm_indexes', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_sql_matches_search_docs(app):
    from app.services.search_service import SEARCH_TYPES, index_expression_sql
    indexes = _migration().INDEXES
    assert set(indexes) == {st.table for st in SEARCH_TYPES}
    for st in SEARCH_TYPES:
        assert index_expression_sql(st) == indexes[st.table], st.table


def test_pg_trgm_and_indexes_installed(app, db):
    assert db.session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")).scalar() == 1
    names = set(db.session.execute(text(
        "SELECT indexname FROM pg_indexes WHERE indexname LIKE 'ix_%_search_trgm'")).scalars())
    assert names == {f'ix_{t}_search_trgm' for t in _migration().INDEXES}


@pytest.mark.parametrize('type_key', ['incidents', 'timeline', 'hosts', 'accounts', 'network_iocs',
                                      'host_iocs', 'malware', 'notes'])
def test_explain_uses_trigram_index(app, db, users, type_key):
    from app.api.v1.endpoints.incidents import accessible_incidents_query
    from app.models import Incident
    from app.services import search_service
    st = search_service.TYPES_BY_NAME[type_key]
    accessible = select(accessible_incidents_query(users['Administrator']).with_entities(Incident.id)
                        .subquery().c.id)
    stmt = search_service.build_search_statement(
        [st], accessible, search_service.SearchParams(q='powershell', page=1, per_page=20))
    compiled = stmt.compile(dialect=db.engine.dialect)
    conn = db.session.connection()
    try:
        # Leave the trigram bitmap scan as the only cheap way to read the
        # table, so the plan names the index iff the expressions match.
        for setting in ('enable_seqscan', 'enable_indexscan', 'enable_indexonlyscan', 'enable_nestloop'):
            conn.exec_driver_sql(f'SET LOCAL {setting} = off')
        plan = '\n'.join(r[0] for r in conn.exec_driver_sql('EXPLAIN ' + str(compiled), compiled.params))
    finally:
        db.session.rollback()
    assert f'ix_{st.table}_search_trgm' in plan, plan
