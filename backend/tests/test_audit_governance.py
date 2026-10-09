"""W1-AUD-BE: audit governance (admin-audit-governance plan §6).

Chain + tamper detection, append-only trigger, retention purge (GUC), export
safety and permission, search filters, settings, system status, overview,
`activity:new` scope filtering and the FK removal."""
import csv
import io
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import exc as sa_exc, text

API = '/api/v1'


def _admin(make_user, org):
    return make_user(org, roles=['Administrator'])


def _rows(db, org, **flt):
    from app.models import AuditLog
    db.session.expire_all()
    return (AuditLog.query.filter_by(organization_id=org.id, **flt)
            .order_by(AuditLog.chain_seq.asc().nullsfirst(), AuditLog.created_at.asc()).all())


# ---------------------------------------------------------------------------
# Hash chain + append-only
# ---------------------------------------------------------------------------

def test_sequential_inserts_are_chained_and_verify(app, db, audit_org, write_audit_rows):
    from app.services import ledger
    from app.services.audit_service import verify_chain
    org = audit_org()
    rows = write_audit_rows(org, 5, details={'nested': {'b': 1, 'a': [1, 2.5, 'ü']}, 'big': 1e20, 'f': 1.0})
    stored = _rows(db, org)
    assert [r.chain_seq for r in stored] == [1, 2, 3, 4, 5]
    assert stored[0].prev_hash == ledger.audit_genesis(org.id)
    for prev, cur in zip(stored, stored[1:]):
        assert cur.prev_hash == prev.row_hash
    assert len({r.row_hash for r in rows}) == 5
    assert stored[0].chain_key_id == ledger.ledger_key()[1]

    summary = verify_chain(org.id)
    assert summary['ok'] is True, summary
    assert summary['checked'] == 5 and summary['head_seq'] == 5 and summary['failure_count'] == 0
    head = ledger.get_head(ledger.audit_chain_key(org.id))
    db.session.refresh(head)
    assert head.last_verify_ok is True and head.last_verified_at is not None


def _pgcode(err):
    return getattr(getattr(err, 'orig', None), 'pgcode', None)


@pytest.mark.parametrize('sql', [
    "UPDATE audit_logs SET action = 'x' WHERE id = :id",
    'DELETE FROM audit_logs WHERE id = :id',
    'TRUNCATE audit_logs',
])
def test_audit_log_is_append_only(app, db, audit_org, write_audit_rows, sql):
    org = audit_org()
    row = write_audit_rows(org)[0]
    with pytest.raises(sa_exc.DBAPIError) as err:
        db.session.execute(text(sql), {'id': row.id})
        db.session.flush()
    assert _pgcode(err.value) == '42501'
    db.session.rollback()
    assert len(_rows(db, org)) == 1


def test_delete_allowed_only_with_purge_guc(app, db, audit_org, write_audit_rows):
    org = audit_org()
    row = write_audit_rows(org)[0]
    db.session.execute(text("SELECT set_config('sheetstorm.audit_purge', 'on', true)"))
    db.session.execute(text('DELETE FROM audit_logs WHERE id = :id'), {'id': row.id})
    db.session.commit()
    assert _rows(db, org) == []
    # The GUC is transaction-local: the next transaction is protected again.
    write_audit_rows(org)
    with pytest.raises(sa_exc.DBAPIError):
        db.session.execute(text('DELETE FROM audit_logs WHERE organization_id = :o'), {'o': org.id})
    db.session.rollback()


def test_tampered_details_reported_as_hash_mismatch(app, db, audit_org, write_audit_rows, audit_tamper):
    from app.services.audit_service import verify_chain
    org = audit_org()
    rows = write_audit_rows(org, 4)
    audit_tamper("UPDATE audit_logs SET details = '{\"i\": 99}' WHERE id = :id", {'id': rows[2].id})
    summary = verify_chain(org.id)
    assert summary['ok'] is False
    assert {'seq': 3, 'id': str(rows[2].id), 'reason': 'hash_mismatch'} in summary['failures']
    # One edit is reported once (no cascade into later rows).
    assert summary['failure_count'] == 1


def test_deleted_middle_row_reported_as_gap(app, db, audit_org, write_audit_rows, audit_tamper):
    from app.services.audit_service import verify_chain
    org = audit_org()
    rows = write_audit_rows(org, 4)
    audit_tamper('DELETE FROM audit_logs WHERE id = :id', {'id': rows[1].id})
    summary = verify_chain(org.id)
    reasons = {(f['seq'], f['reason']) for f in summary['failures']}
    assert (3, 'gap') in reasons and (3, 'prev_hash_mismatch') in reasons


def test_tail_truncation_reported_as_head_mismatch(app, db, audit_org, write_audit_rows, audit_tamper):
    from app.services.audit_service import verify_chain
    org = audit_org()
    rows = write_audit_rows(org, 3)
    audit_tamper('DELETE FROM audit_logs WHERE id = :id', {'id': rows[-1].id})
    summary = verify_chain(org.id)
    assert summary['ok'] is False
    assert {'seq': 3, 'id': None, 'reason': 'head_mismatch'} in summary['failures']


def test_rotated_key_unverifiable_unless_previous_key_given(app, db, audit_org, write_audit_rows, monkeypatch):
    from app.services.audit_service import verify_chain
    org = audit_org()
    monkeypatch.setitem(app.config, 'AUDIT_CHAIN_KEY', 'old-test-only-key')
    write_audit_rows(org, 2)
    monkeypatch.setitem(app.config, 'AUDIT_CHAIN_KEY', 'new-test-only-key')
    write_audit_rows(org, 1)

    summary = verify_chain(org.id)
    assert summary['ok'] is True and summary['unverifiable_rotated_key'] == 2

    monkeypatch.setitem(app.config, 'AUDIT_CHAIN_PREVIOUS_KEYS', ['old-test-only-key'])
    summary = verify_chain(org.id)
    assert summary['ok'] is True and summary['unverifiable_rotated_key'] == 0 and summary['checked'] == 3


def test_concurrent_writers_get_unique_contiguous_seqs(app, db, audit_org):
    from app.middleware.audit import log_audit_event
    from app.services.audit_service import verify_chain
    org = audit_org()
    org_id = org.id
    errors = []

    def worker(n):
        try:
            with app.app_context():
                for i in range(20):
                    assert log_audit_event('system_event', f'concurrent_{n}', organization_id=org_id,
                                           actor_label='system:test', details={'i': i}) is not None
        except Exception as e:  # pragma: no cover - reported below
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not any(t.is_alive() for t in threads), 'writer thread hung'
    assert not errors, errors
    seqs = [r.chain_seq for r in _rows(db, org)]
    assert seqs == list(range(1, 41))
    assert verify_chain(org.id)['ok'] is True


def test_hard_deletes_keep_audit_ids(app, db, make_user, make_incident, org_a, write_audit_rows):
    from app.models import AuditLog
    user = make_user(org_a)
    inc = make_incident()
    row = write_audit_rows(org_a, user_id=user.id, user_email=user.email, incident_id=inc.id,
                           action=f'fk_{uuid.uuid4().hex[:8]}')[0]
    uid, iid, rid = user.id, inc.id, row.id
    db.session.delete(db.session.get(type(user), uid))
    db.session.delete(db.session.get(type(inc), iid))
    db.session.commit()
    db.session.expire_all()
    stored = db.session.get(AuditLog, rid)
    assert stored.user_id == uid and stored.incident_id == iid
    data = stored.to_dict()
    assert data['user'] is None and data['incident'] is None and data['user_id'] == str(uid)


# ---------------------------------------------------------------------------
# Search / filters / isolation / permissions
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded(app, org_a, write_audit_rows):
    """Rows in org A tagged with a unique email marker."""
    m = uuid.uuid4().hex[:8]
    email = f'{m}@filters.test'
    inc = uuid.uuid4()
    write_audit_rows(org_a, user_email=email, action=f'lit%{m}', event_type='admin_action',
                     status_code=200, ip_address='10.1.2.3', details={'changes': {'a': {'from': 1, 'to': 2}}})
    write_audit_rows(org_a, user_email=email, action=f'litx{m}', event_type='data_access',
                     status_code=403, ip_address='192.168.5.5', incident_id=inc, resource_type='artifact')
    write_audit_rows(org_a, user_email=email, action=f'zzz{m}', event_type='data_modification',
                     status_code=500, ip_address='10.9.9.9')
    return {'m': m, 'email': email, 'incident': inc}


def _list(client, **params):
    resp = client.get(f'{API}/audit-logs', query_string=params)
    return resp


def test_filters_narrow(app, users, auth, seeded):
    admin = auth(users['Administrator'])
    m, email = seeded['m'], seeded['email']

    def actions(**params):
        r = _list(admin, user_email=email.upper(), per_page=200, **params)
        assert r.status_code == 200, r.get_json()
        return {i['action'] for i in r.get_json()['items']}

    assert actions() == {f'lit%{m}', f'litx{m}', f'zzz{m}'}
    assert actions(action=f'litx{m}') == {f'litx{m}'}
    assert actions(action_contains='%') == {f'lit%{m}'}  # LIKE wildcard escaped
    assert actions(action_contains='lit') == {f'lit%{m}', f'litx{m}'}
    assert actions(event_type='admin_action,data_access') == {f'lit%{m}', f'litx{m}'}
    assert actions(status='denied') == {f'litx{m}'}
    assert actions(status='server_error') == {f'zzz{m}'}
    assert actions(status='success') == {f'lit%{m}'}
    assert actions(status_code='500') == {f'zzz{m}'}
    assert actions(ip='10.0.0.0/8') == {f'lit%{m}', f'zzz{m}'}
    assert actions(ip='192.168.5.5') == {f'litx{m}'}
    assert actions(incident_id=str(seeded['incident'])) == {f'litx{m}'}
    assert actions(resource_type='artifact') == {f'litx{m}'}
    assert actions(has_changes='true') == {f'lit%{m}'}
    assert actions(start_date='2000-01-01T00:00:00Z', end_date='2999-01-01T00:00:00Z') == actions()
    assert actions(end_date='2000-01-01T00:00:00Z') == set()


def test_sort_and_pagination_are_stable(app, users, auth, seeded):
    admin = auth(users['Administrator'])
    body = _list(admin, user_email=seeded['email'], sort='action', per_page=2).get_json()
    assert body['total'] == 3 and body['pages'] == 2 and body['sort'] == 'action'
    first = [i['action'] for i in body['items']]
    second = [i['action'] for i in _list(admin, user_email=seeded['email'], sort='action', per_page=2,
                                         page=2).get_json()['items']]
    assert first + second == sorted(first + second)
    desc = _list(admin, user_email=seeded['email'], sort='status_code', order='desc').get_json()['items']
    assert [i['status_code'] for i in desc] == [500, 403, 200]
    assert _list(admin, user_email=seeded['email'], sort='-chain_seq').status_code == 200


@pytest.mark.parametrize('params', [
    {'user_id': 'nope'}, {'resource_id': 'x'}, {'incident_id': '1'}, {'start_date': 'garbage'},
    {'start_date': '2026-02-01T00:00:00Z', 'end_date': '2026-01-01T00:00:00Z'},
    {'ip': '10.0.0.0/33'}, {'sort': 'details'}, {'event_type': 'bogus'}, {'status': 'weird'},
    {'has_changes': 'maybe'}, {'page': '501', 'per_page': '200'},
])
def test_invalid_filters_are_400(app, users, auth, params):
    r = _list(auth(users['Administrator']), **params)
    assert r.status_code == 400, (params, r.get_json())


def test_org_isolation(app, users, auth, seeded, org_a):
    from app.models import AuditLog
    other = auth(users['admin_b'])
    m = seeded['m']
    body = _list(other, user_email=seeded['email']).get_json()
    assert body['total'] == 0
    row = AuditLog.query.filter_by(organization_id=org_a.id, action=f'zzz{m}').one()
    assert other.get(f'{API}/audit-logs/{row.id}').status_code == 404
    facets = other.get(f'{API}/audit-logs/facets').get_json()
    assert f'zzz{m}' not in facets['actions']
    stats = other.get(f'{API}/audit-logs/stats', query_string={'user_email': seeded['email']}).get_json()
    assert stats['total'] == 0
    export = other.get(f'{API}/audit-logs/export', query_string={'user_email': seeded['email']})
    assert export.status_code == 200
    assert len(list(csv.reader(io.StringIO(export.get_data(as_text=True))))) == 1  # header only


def test_permissions(app, users, auth):
    assert _list(auth(users['Manager'])).status_code == 200
    assert auth(users['Manager']).get(f'{API}/audit-logs/export').status_code == 403
    assert _list(auth(users['Analyst'])).status_code == 403
    manager = auth(users['Manager'])
    for path in ('/admin/system-status', '/admin/overview', '/admin/audit-settings', '/admin/audit-integrity'):
        assert manager.get(f'{API}{path}').status_code == 403, path
    assert manager.put(f'{API}/admin/audit-settings', json={'legal_hold': False}).status_code == 403


def test_stats_accept_filters(app, users, auth, seeded):
    body = auth(users['Administrator']).get(f'{API}/audit-logs/stats',
                                            query_string={'user_email': seeded['email']}).get_json()
    assert body['total'] == 3
    assert body['by_event_type'] == {'admin_action': 1, 'data_access': 1, 'data_modification': 1}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_export_csv_is_formula_safe_and_audited(app, db, users, auth, org_a, write_audit_rows):
    from app.models import AuditLog
    m = uuid.uuid4().hex[:8]
    email = f'{m}@export.test'
    write_audit_rows(org_a, user_email=email, action=f'csv_{m}',
                     resource_type="=cmd|' /C calc'!A0", details={'note': '+SUM(1)'})
    r = auth(users['Administrator']).get(f'{API}/audit-logs/export',
                                         query_string={'user_email': email, 'format': 'csv'})
    assert r.status_code == 200
    assert r.headers['Cache-Control'] == 'no-store'
    assert 'attachment; filename="audit-test-org-a-' in r.headers['Content-Disposition']
    seq, _, digest = r.headers['X-Audit-Chain-Head'].partition(':')
    assert int(seq) > 0 and len(digest) == 64
    rows = list(csv.reader(io.StringIO(r.get_data(as_text=True))))
    header, data = rows[0], rows[1:]
    assert header == AuditLog.CSV_COLUMNS and len(data) == 1
    rec = dict(zip(header, data[0]))
    assert rec['resource_type'] == "'=cmd|' /C calc'!A0"
    assert json.loads(rec['details']) == {'note': '+SUM(1)'}

    entry = (AuditLog.query.filter_by(organization_id=org_a.id, event_type='data_access', action='export',
                                      resource_type='audit_log')
             .order_by(AuditLog.created_at.desc()).first())
    assert entry.details['row_count'] == 1 and entry.details['format'] == 'csv'
    assert entry.details['filters'] == {'user_email': email}


def test_export_jsonl_and_cap(app, users, auth, org_a, write_audit_rows, monkeypatch):
    m = uuid.uuid4().hex[:8]
    email = f'{m}@jsonl.test'
    write_audit_rows(org_a, 4, user_email=email, action=f'jsonl_{m}')
    admin = auth(users['Administrator'])
    r = admin.get(f'{API}/audit-logs/export', query_string={'user_email': email, 'format': 'jsonl'})
    assert r.status_code == 200 and r.mimetype == 'application/x-ndjson'
    lines = [json.loads(ln) for ln in r.get_data(as_text=True).splitlines()]
    assert len(lines) == 4 and all(ln['action'] == f'jsonl_{m}' for ln in lines)
    assert [ln['chain_seq'] for ln in lines] == sorted(ln['chain_seq'] for ln in lines)

    monkeypatch.setitem(app.config, 'AUDIT_EXPORT_MAX_ROWS', 3)
    r = admin.get(f'{API}/audit-logs/export', query_string={'user_email': email})
    assert r.status_code == 422 and r.get_json()['error'] == 'export_too_large'
    assert admin.get(f'{API}/audit-logs/export', query_string={'format': 'xml'}).status_code == 400


# ---------------------------------------------------------------------------
# Diffs
# ---------------------------------------------------------------------------

def test_integration_credentials_diff_never_stores_values(app, db, users, auth, org_a):
    from app.models import AuditLog
    admin = auth(users['Administrator'])
    secret = f'sk-{uuid.uuid4().hex}'
    r = admin.post(f'{API}/integrations', json={'type': 'webhook', 'name': f'wh-{uuid.uuid4().hex[:6]}',
                                                'config': {'url': 'https://example.org/a'},
                                                'credentials': {'token': secret}})
    assert r.status_code == 201, r.get_json()
    iid = r.get_json()['id']
    new_secret = f'sk-{uuid.uuid4().hex}'
    r = admin.put(f'{API}/integrations/{iid}', json={'credentials': {'token': new_secret},
                                                      'config': {'url': 'https://example.org/b'},
                                                      'is_enabled': False})
    assert r.status_code == 200
    row = (AuditLog.query.filter_by(organization_id=org_a.id, action='update', resource_type='integration',
                                    resource_id=uuid.UUID(iid)).one())
    changes = row.details['changes']
    assert changes['credentials'] == {'changed': True}
    assert changes['config.url'] == {'from': 'https://example.org/a', 'to': 'https://example.org/b'}
    assert changes['is_enabled'] == {'from': True, 'to': False}
    blob = json.dumps(row.to_dict(), default=str)
    assert secret not in blob and new_secret not in blob

    created = AuditLog.query.filter_by(action='create', resource_type='integration',
                                       resource_id=uuid.UUID(iid)).one()
    assert created.details['changes']['credentials'] == {'changed': True}
    assert secret not in json.dumps(created.to_dict(), default=str)


def test_integration_test_is_audited_and_persisted(app, db, users, auth, org_a):
    from app.models import AuditLog, Integration
    admin = auth(users['Administrator'])
    r = admin.post(f'{API}/integrations', json={'type': 'oauth_github', 'name': f'gh-{uuid.uuid4().hex[:6]}'})
    iid = r.get_json()['id']
    r = admin.post(f'{API}/integrations/{iid}/test')
    assert r.status_code == 400 and r.get_json()['success'] is False  # no client id configured
    db.session.expire_all()
    integ = db.session.get(Integration, uuid.UUID(iid))
    assert integ.last_tested_at is not None and integ.last_test_ok is False
    row = AuditLog.query.filter_by(action='test', resource_type='integration', resource_id=integ.id).one()
    assert row.event_type == 'admin_action' and row.status_code == 400
    assert row.details['changes'] == {'last_test_ok': {'from': None, 'to': False}}


def test_team_update_diff(app, users, auth, org_a):
    from app.models import AuditLog
    admin = auth(users['Administrator'])
    name = f'team-{uuid.uuid4().hex[:6]}'
    tid = admin.post(f'{API}/teams', json={'name': name}).get_json()['id']
    assert admin.put(f'{API}/teams/{tid}', json={'description': 'blue'}).status_code == 200
    r = admin.post(f'{API}/teams/{tid}/members', json={'user_id': str(users['Analyst'].id)})
    assert r.status_code == 201
    upd = AuditLog.query.filter_by(action='update_team', resource_id=uuid.UUID(tid)).one()
    assert upd.details['changes'] == {'description': {'from': None, 'to': 'blue'}}
    add = AuditLog.query.filter_by(action='add_team_member', resource_id=uuid.UUID(tid)).one()
    assert add.details['changes'] == {'members': {'added': [str(users['Analyst'].id)], 'removed': []}}


def test_org_put_cannot_write_audit_keys(app, users, auth):
    r = auth(users['Administrator']).put(f'{API}/organization', json={'settings': {'legal_hold': True}})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Retention / legal hold settings
# ---------------------------------------------------------------------------

def test_audit_settings_validation_and_confirmation(app, db, auth, make_user, audit_org, write_audit_rows):
    from app.models import AuditLog
    org = audit_org()
    admin = auth(_admin(make_user, org))
    url = f'{API}/admin/audit-settings'
    body = admin.get(url).get_json()
    assert body['audit_retention_days'] is None and body['legal_hold'] is False
    assert body['min_retention_days'] == 365

    assert admin.put(url, json={'audit_retention_days': 364}).status_code == 400
    assert admin.put(url, json={'audit_retention_days': True}).status_code == 400
    assert admin.put(url, json={'bogus': 1}).status_code == 400

    write_audit_rows(org, 2, at=datetime.now(timezone.utc) - timedelta(days=800))
    r = admin.put(url, json={'audit_retention_days': 730})
    assert r.status_code == 409 and r.get_json()['would_purge'] == 2
    r = admin.put(url, json={'audit_retention_days': 730, 'confirm': True})
    assert r.status_code == 200 and r.get_json()['audit_retention_days'] == 730
    # Lengthening needs no confirmation; null = keep forever.
    assert admin.put(url, json={'audit_retention_days': 1000}).status_code == 200
    assert admin.put(url, json={'audit_retention_days': None}).status_code == 200

    row = (AuditLog.query.filter_by(organization_id=org.id, action='update_audit_settings', status_code=200)
           .order_by(AuditLog.chain_seq.desc()).first())
    assert row.details['changes'] == {'audit_retention_days': {'from': 1000, 'to': None}}


def test_legal_hold_requires_reason_and_emits_security_events(app, db, auth, make_user, audit_org):
    from app.models import AuditLog
    org = audit_org()
    admin = auth(_admin(make_user, org))
    url = f'{API}/admin/audit-settings'
    assert admin.put(url, json={'legal_hold': True}).status_code == 400
    r = admin.put(url, json={'legal_hold': True, 'legal_hold_reason': 'Litigation 42'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['legal_hold'] is True and body['legal_hold_reason'] == 'Litigation 42'
    assert body['legal_hold_set_by'] and body['legal_hold_set_at']
    assert admin.put(url, json={'legal_hold': False}).status_code == 200
    actions = [r.action for r in _rows(db, org, event_type='security_event')]
    assert actions == ['legal_hold_enabled', 'legal_hold_released']


# ---------------------------------------------------------------------------
# Purge (CLI) + verify (CLI)
# ---------------------------------------------------------------------------

def _locked_artifact_incident(db, make_incident, org, user):
    from app.models import Artifact
    inc = make_incident(org=org, creator=user)
    db.session.add(Artifact(incident_id=inc.id, filename='a.bin', original_filename='a.bin',
                            storage_path='x/a.bin', file_size=1, md5='0' * 32, sha256='0' * 64,
                            sha512='0' * 128, uploaded_by=user.id, is_locked=True))
    db.session.commit()
    return inc


def _cli(app, *args):
    return app.test_cli_runner().invoke(args=['sheetstorm', *args])


def test_purge_deletes_old_prefix_and_keeps_chain_verifiable(app, db, make_user, make_incident, audit_org,
                                                             write_audit_rows):
    from app.services import ledger
    from app.services.audit_service import verify_chain
    org = audit_org(audit_retention_days=365)
    user = _admin(make_user, org)
    held = _locked_artifact_incident(db, make_incident, org, user)
    old = datetime.now(timezone.utc) - timedelta(days=400)
    db.session.execute(text(
        "INSERT INTO audit_logs (id, organization_id, event_type, action, created_at) "
        "VALUES (:i, :o, 'system_event', 'legacy_old', :t), (:j, :o, 'system_event', 'legacy_new', now())"),
        {'i': uuid.uuid4(), 'j': uuid.uuid4(), 'o': org.id, 't': old})
    db.session.commit()
    before = _rows(db, org)  # the two legacy rows
    assert len(before) == 2
    first_seq = 0
    write_audit_rows(org, 3, at=old, action='old')
    write_audit_rows(org, 1, at=old, action='old_held', incident_id=held.id)
    write_audit_rows(org, 2, at=old, action='old_after_held')
    write_audit_rows(org, 2, action='recent')

    dry = _cli(app, 'purge-audit-logs', '--org', org.slug, '--dry-run')
    assert dry.exit_code == 0, dry.output
    summary = json.loads(dry.output.strip().splitlines()[-1])
    assert summary['legacy_deleted'] == 1 and summary['chained_deleted'] == first_seq + 3
    assert len(_rows(db, org)) == len(before) + 8  # dry run wrote nothing

    res = _cli(app, 'purge-audit-logs', '--org', org.slug, '--batch-size', '2')
    assert res.exit_code == 0, res.output
    remaining = _rows(db, org)
    actions = [r.action for r in remaining]
    assert 'legacy_old' not in actions and 'legacy_new' in actions
    assert actions.count('old') == 0 and 'old_held' in actions and actions.count('old_after_held') == 2
    head = ledger.get_head(ledger.audit_chain_key(org.id))
    db.session.refresh(head)
    held_row = next(r for r in remaining if r.action == 'old_held')
    assert head.purged_through_seq == held_row.chain_seq - 1
    assert head.anchor_hash == held_row.prev_hash
    purge_row = next(r for r in remaining if r.action == 'audit_purge')
    assert purge_row.user_email == 'system:purge' and purge_row.details['legacy_deleted'] == 1
    assert purge_row.details['chained_deleted'] == first_seq + 3

    assert verify_chain(org.id)['ok'] is True
    res = _cli(app, 'verify-audit-chain', '--org', org.slug)
    assert res.exit_code == 0, res.output


def test_purge_skips_under_legal_hold(app, db, audit_org, write_audit_rows):
    org = audit_org(audit_retention_days=365, legal_hold=True, legal_hold_reason='case')
    write_audit_rows(org, 2, at=datetime.now(timezone.utc) - timedelta(days=500))
    res = _cli(app, 'purge-audit-logs', '--org', org.slug)
    assert res.exit_code == 0, res.output
    rows = _rows(db, org)
    assert [r.action for r in rows] == ['test_row', 'test_row', 'audit_purge_skipped']
    assert rows[-1].details == {'reason': 'legal_hold'}


def test_purge_without_retention_keeps_everything(app, db, audit_org, write_audit_rows):
    org = audit_org()
    write_audit_rows(org, 1, at=datetime.now(timezone.utc) - timedelta(days=5000))
    res = _cli(app, 'purge-audit-logs', '--org', org.slug)
    assert res.exit_code == 0 and json.loads(res.output)['status'] == 'no_retention'
    assert len(_rows(db, org)) == 1


def test_verify_cli_fails_on_tamper(app, db, audit_org, write_audit_rows, audit_tamper):
    org = audit_org()
    rows = write_audit_rows(org, 2)
    audit_tamper("UPDATE audit_logs SET action = 'forged' WHERE id = :id", {'id': rows[0].id})
    res = _cli(app, 'verify-audit-chain', '--org', org.slug)
    assert res.exit_code == 1
    assert json.loads(res.output)['ok'] is False


def test_audit_jobs_registered(app):
    from app import cli
    assert cli.JOBS['purge-audit-logs'].every_seconds == 86400
    assert cli.JOBS['verify-audit-chain'].every_seconds == 86400


def test_integrity_endpoint(app, auth, make_user, audit_org, write_audit_rows):
    org = audit_org()
    admin = auth(_admin(make_user, org))
    write_audit_rows(org, 2)
    body = admin.get(f'{API}/admin/audit-integrity').get_json()
    assert body['ok'] is True and body['organization_id'] == str(org.id) and body['checked'] >= 2


# ---------------------------------------------------------------------------
# System status / overview
# ---------------------------------------------------------------------------

_INFRA = ('app', 'database', 'alembic', 'redis', 'rate_limiting')


def test_system_status_org_admin_has_no_infra(app, users, auth):
    body = auth(users['Administrator']).get(f'{API}/admin/system-status').get_json()
    assert body['infra_visible'] is False
    assert not set(_INFRA) & set(body)
    assert {'storage', 'ai_providers', 'integrations', 'counts', 'audit'} <= set(body)
    assert set(body['storage']) == {'backend'}
    assert {'head_seq', 'head_hash', 'legacy_unchained'} <= set(body['audit']['chain'])


def test_system_status_platform_admin_sees_infra_without_secrets(app, auth, platform_admin):
    r = auth(platform_admin).get(f'{API}/admin/system-status')
    assert r.status_code == 200
    body = r.get_json()
    assert body['infra_visible'] is True and set(_INFRA) <= set(body)
    assert body['database']['ok'] is True and body['redis']['ok'] is True
    assert body['alembic']['up_to_date'] is True and body['alembic']['head'] == body['alembic']['current']
    assert len(body['alembic']['head']) == 1
    raw = r.get_data(as_text=True)
    for key in ('SECRET_KEY', 'JWT_SECRET_KEY', 'FERNET_KEY', 'AUDIT_CHAIN_KEY', 'CUSTODY_SIGNING_KEY'):
        value = app.config.get(key)
        if value:
            assert value not in raw, key


def test_overview_counts_and_last_admin_warning(app, auth, make_user, audit_org):
    org = audit_org()
    admin = _admin(make_user, org)
    make_user(org, roles=['Analyst'])
    client = auth(admin)
    body = client.get(f'{API}/admin/overview').get_json()
    users = body['users']
    assert users['total'] == 2 and users['active'] == 2 and users['disabled'] == 0
    assert users['by_role'] == {'Administrator': 1, 'Analyst': 1}
    assert users['locked'] is None and users['pending_invites'] is None
    assert users['admins_without_mfa'] == 1
    assert body['active_admin_count'] == 1 and body['last_admin_warning'] is True

    _admin(make_user, org)
    body = client.get(f'{API}/admin/overview').get_json()
    assert body['active_admin_count'] == 2 and body['last_admin_warning'] is False


def test_overview_recent_admin_actions(app, auth, make_user, audit_org):
    org = audit_org()
    admin = auth(_admin(make_user, org))
    admin.put(f'{API}/admin/audit-settings', json={'audit_retention_days': 400, 'confirm': True})
    recent = admin.get(f'{API}/admin/overview').get_json()['recent_admin_actions']
    assert recent[0]['action'] == 'update_audit_settings' and recent[0]['has_changes'] is True


# ---------------------------------------------------------------------------
# activity:new scope filtering
# ---------------------------------------------------------------------------

@pytest.fixture
def emitted(monkeypatch):
    from app import socketio
    calls = []
    monkeypatch.setattr(socketio, 'emit', lambda event, payload, room=None, **kw: calls.append((event, payload, room)))
    return calls


@pytest.mark.parametrize('resource_type,suffix', [
    ('compromised_account', ':accounts'),
    ('timeline_event', ':timeline'),
    ('incident', ''),
    (None, ''),
    ('report', None),  # unknown scope: dropped
])
def test_activity_new_goes_to_scope_room(app, users, make_incident, emitted, resource_type, suffix):
    from app.middleware.audit import log_audit_event
    inc = make_incident()
    with app.test_request_context():
        log_audit_event('data_modification', 'update', resource_type=resource_type, incident_id=inc.id,
                        user=users['Administrator'], details={'changes': {'x': {'from': 1, 'to': 2}}})
    if suffix is None:
        assert emitted == []
        return
    (event, payload, room), = emitted
    assert event == 'activity:new' and room == f'incident_{inc.id}{suffix}'
    assert 'changes' not in payload['details']


def test_admin_action_broadcast_has_no_changes(app, users, emitted):
    from app.middleware.audit import log_audit_event
    with app.test_request_context():
        log_audit_event('admin_action', 'update', resource_type='integration', user=users['Administrator'],
                        changes={'name': {'from': 'a', 'to': 'b'}})
    assert emitted and all('changes' not in p['details'] for _, p, _ in emitted)
