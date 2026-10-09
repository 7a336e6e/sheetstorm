"""Optimistic concurrency foundation (W0-RT-CORE): version columns,
app/utils/concurrency.py helpers and the BaseModel updated_at listener."""
import json

import pytest
from sqlalchemy import text

from app.utils.concurrency import (INVALID, commit_or_conflict, parse_version,
                                   precondition, set_etag)

VERSIONED = [
    ('Incident', 'incidents'), ('TimelineEvent', 'timeline_events'), ('Task', 'tasks'),
    ('CaseNote', 'case_notes'), ('CompromisedHost', 'compromised_hosts'),
    ('CompromisedAccount', 'compromised_accounts'), ('NetworkIndicator', 'network_indicators'),
    ('HostBasedIndicator', 'host_based_indicators'), ('MalwareTool', 'malware_tools'),
    ('AttackGraphNode', 'attack_graph_nodes'), ('AttackGraphEdge', 'attack_graph_edges'),
    ('IncidentPlaybook', 'incident_playbooks'),
]


@pytest.mark.parametrize('model_name,table', VERSIONED)
def test_models_are_versioned(app, db, model_name, table):
    import app.models as models
    model = getattr(models, model_name)
    assert model.__table__.name == table
    assert model.__mapper__.version_id_col is model.__table__.c.version
    col = db.session.execute(text(
        "SELECT is_nullable, column_default FROM information_schema.columns "
        "WHERE table_name=:t AND column_name='version'"), {'t': table}).one()
    assert col[0] == 'NO' and '1' in col[1]


@pytest.mark.parametrize('raw,expected', [
    (None, None), ('', None), ('7', 7), ('"7"', 7), ('W/"7"', 7), (7, 7), ('*', '*'),
    ('"3", "4"', (3, 4)), ('abc', INVALID), ('"-1"', INVALID), (True, INVALID), (-2, INVALID),
])
def test_parse_version(raw, expected):
    assert parse_version(raw) == expected


def _task(db, incident, user, **kw):
    from app.models import Task
    t = Task(incident_id=incident.id, title=kw.pop('title', 'task'), created_by=user.id, **kw)
    db.session.add(t)
    db.session.commit()
    return t


def test_version_bumps_and_updated_at_set(db, users, make_incident):
    t = _task(db, make_incident(), users['Administrator'])
    assert t.version == 1 and t.updated_at is None
    t.title = 'changed'
    db.session.commit()
    assert t.version == 2 and t.updated_at is not None
    first = t.updated_at
    t.status = 'in_progress'
    db.session.commit()
    assert t.version == 3 and t.updated_at >= first


def test_precondition_variants(app, db, users, make_incident):
    t = _task(db, make_incident(), users['Administrator'])
    t.title = 'v2'
    db.session.commit()                          # version 2

    def check(headers=None, body=None, **kw):
        with app.test_request_context('/', method='PUT', headers=headers or {},
                                      data=json.dumps(body) if body is not None else None,
                                      content_type='application/json'):
            return precondition(t, **kw)

    assert check() is None                                      # absent: last-write-wins
    assert check({'If-Match': '"2"'}) is None
    assert check({'If-Match': 'W/"2"'}) is None
    assert check({'If-Match': '*'}) is None
    assert check(body={'expected_version': 2}) is None
    stale = check({'If-Match': '"1"'})
    assert stale.status_code == 409
    payload = stale.get_json()
    assert payload['error'] == 'conflict' and payload['current_version'] == 2
    assert payload['current']['title'] == 'v2' and stale.headers['ETag'] == '"2"'
    assert check(body={'expected_version': 1}).status_code == 409
    # If-Match wins over the body key.
    assert check({'If-Match': '2'}, body={'expected_version': 1}) is None
    assert check({'If-Match': 'garbage'}).status_code == 400
    assert check(required=True).status_code == 428
    assert check(body={'version': 2}, required=True, body_key='version') is None


def _end_read_transaction(db):
    """Commit the scoped session's open (read) transaction without expiring
    the loaded objects, so it holds no transaction and no locks while another
    connection writes, yet `t.version` stays the value this session read."""
    sess = db.session()
    previous = sess.expire_on_commit
    sess.expire_on_commit = False
    try:
        sess.commit()
    finally:
        sess.expire_on_commit = previous
    assert not sess.in_transaction()


def _bounded(conn_or_session):
    """Fail fast (instead of hanging) if a statement ever waits on a lock:
    both connections are driven by this one thread, so a lock wait between
    them is a self-deadlock Postgres cannot detect."""
    conn_or_session.execute(text("SET LOCAL lock_timeout = '5s'"))
    conn_or_session.execute(text("SET LOCAL statement_timeout = '15s'"))


def test_commit_or_conflict_on_concurrent_writer(app, db, users, make_incident):
    t = _task(db, make_incident(), users['Administrator'])
    tid = t.id                      # loads the row (version 1) in the session ...
    assert t.version == 1
    _end_read_transaction(db)       # ... then leaves the session idle.

    # Another session/worker commits first.
    with db.engine.begin() as conn:
        _bounded(conn)
        conn.execute(text("UPDATE tasks SET version = version + 1, title='theirs' WHERE id=:i"),
                     {'i': tid})
    _bounded(db.session)            # (before the change: execute() autoflushes)
    t.title = 'mine'                # still based on version 1
    with app.test_request_context('/'):
        resp = commit_or_conflict(t)
    assert resp.status_code == 409
    body = resp.get_json()
    assert body['current_version'] == 2 and body['current']['title'] == 'theirs'


def test_commit_or_conflict_success_and_etag(app, db, users, make_incident):
    t = _task(db, make_incident(), users['Administrator'])
    t.title = 'ok'
    with app.test_request_context('/'):
        assert commit_or_conflict(t) is None
        resp = set_etag(({'id': str(t.id)}, 200), t)
    assert resp.headers['ETag'] == '"2"'


def test_stale_data_error_is_409_not_500(app):
    from sqlalchemy.orm.exc import StaleDataError
    with app.test_request_context('/'):
        resp = app.make_response(app.handle_user_exception(StaleDataError('x')))
    assert resp.status_code == 409 and resp.get_json()['error'] == 'conflict'


def test_api_update_bumps_version(db, users, auth, make_incident):
    inc = make_incident()
    client = auth(users['Administrator'])
    r = client.put(f'/api/v1/incidents/{inc.id}', json={'title': 'Renamed'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['version'] == 2
