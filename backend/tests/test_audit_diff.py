"""W0-FND: utils/audit_diff.py + @audit_log / log_audit_event integration."""
import datetime
import uuid

import pytest
from flask import g

from app.utils.audit_diff import audit_changes, record_changes, snapshot


def test_scalar_changes_only_changed_keys():
    assert audit_changes({'name': 'a', 'x': 1}, {'name': 'b', 'x': 1}) == {'name': {'from': 'a', 'to': 'b'}}
    assert audit_changes({'a': None}, {}) == {}
    assert audit_changes({}, {'a': 1}) == {'a': {'from': None, 'to': 1}}


def test_sensitive_keys_redacted():
    out = audit_changes({'password': 'old', 'api_key': 'k1', 'name': 'n'},
                        {'password': 'new', 'api_key': 'k2', 'name': 'n'})
    assert out == {'password': {'changed': True}, 'api_key': {'changed': True}}
    assert 'old' not in repr(out) and 'k2' not in repr(out)


def test_lists_added_removed():
    out = audit_changes({'permissions': ['a:read', 'b:read']}, {'permissions': ['b:read', 'c:read']})
    assert out == {'permissions': {'added': ['c:read'], 'removed': ['a:read']}}
    assert audit_changes({'roles': None}, {'roles': ['Admin']}) == {'roles': {'added': ['Admin'], 'removed': []}}


def test_nested_dict_dotted_and_nested_sensitive():
    before = {'settings': {'timezone': 'UTC', 'auto_enrich_iocs': False}, 'config': {'url': 'a', 'token': 'x'}}
    after = {'settings': {'timezone': 'Europe/Paris', 'auto_enrich_iocs': False},
             'config': {'url': 'a', 'token': 'y'}, 'credentials': {'k': 'v'}}
    out = audit_changes(before, after)
    assert out == {'settings.timezone': {'from': 'UTC', 'to': 'Europe/Paris'},
                   'config.token': {'changed': True},
                   'credentials': {'changed': True}}


def test_truncation():
    out = audit_changes({'d': ''}, {'d': 'x' * 600})
    assert len(out['d']['to']) == 501 and out['d']['to'].endswith('…')
    many = audit_changes({}, {f'k{i:03d}': i for i in range(150)})
    assert many['_truncated'] is True and len(many) == 101


def test_snapshot_json_safe():
    uid = uuid.uuid4()
    ts = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)

    class Obj:
        id = uid
        created_at = ts
        blob = b'\x00\x01'
    snap = snapshot(Obj(), ['id', 'created_at', 'blob', 'missing'])
    assert snap['id'] == str(uid) and snap['created_at'] == ts.isoformat()
    assert snap['blob'].startswith('<binary sha256:') and snap['missing'] is None


def test_audit_log_decorator_merges_changes(app, db, users):
    from app.middleware.audit import audit_log
    from app.models import AuditLog
    marker = uuid.uuid4().hex

    @audit_log('admin_action', f'diff_test_{marker}', 'role')
    def handler():
        record_changes({'name': 'a', 'secret': 's1'}, {'name': 'b', 'secret': 's2'}, target_email='t@x.test')
        record_changes({'perms': ['x']}, {'perms': ['x', 'y']})
        return {'id': None}, 200

    with app.test_request_context('/api/v1/roles', method='PUT'):
        g.current_user = users['Administrator']
        handler()
        assert getattr(g, 'audit_changes', None) is None  # cleared
    row = AuditLog.query.filter_by(action=f'diff_test_{marker}').one()
    assert row.details['changes'] == {'name': {'from': 'a', 'to': 'b'}, 'secret': {'changed': True},
                                      'perms': {'added': ['y'], 'removed': []}}
    assert row.details['target_email'] == 't@x.test'


def test_changes_never_broadcast():
    from app.middleware.audit import public_activity_details
    assert public_activity_details({'changes': {'a': 1}, 'ok': 1}) == {'ok': 1}


def test_log_audit_event_system_kwargs(app, org_a):
    from app.models import AuditLog
    from app.middleware.audit import log_audit_event
    marker = uuid.uuid4().hex
    with app.app_context():
        log_audit_event('system_event', f'sys_{marker}', organization_id=org_a.id,
                        actor_label='system:purge', changes={'x': {'from': 1, 'to': 2}})
    row = AuditLog.query.filter_by(action=f'sys_{marker}').one()
    assert row.organization_id == org_a.id and row.user_email == 'system:purge' and row.user_id is None
    assert row.details['changes'] == {'x': {'from': 1, 'to': 2}}


def _status_probe_response(kind):
    from flask import jsonify, make_response
    if kind == 'tuple':
        return jsonify(ok=False), 409
    if kind == 'response':
        resp = jsonify(ok=False)
        resp.status_code = 403
        return resp
    if kind == 'response_headers':
        return make_response(jsonify(ok=True), 202), {'X-Probe': '1'}
    return jsonify(ok=True)


@pytest.mark.parametrize('kind,expected', [('tuple', 409), ('response', 403), ('response_headers', 202),
                                           ('plain', 200)])
def test_audit_log_records_the_real_status(app, users, kind, expected):
    """A view may return (body, status) or a Response carrying its own status."""
    from app.middleware.audit import audit_log
    from app.models import AuditLog
    marker = uuid.uuid4().hex

    @audit_log('data_modification', f'status_probe_{marker}', 'incident')
    def handler():
        return _status_probe_response(kind)

    with app.test_request_context('/api/v1/probe', method='POST'):
        g.current_user = users['Administrator']
        try:
            handler()
        finally:
            g.pop('current_user', None)
    assert AuditLog.query.filter_by(action=f'status_probe_{marker}').one().status_code == expected
