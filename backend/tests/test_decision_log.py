"""W4-DEC: decision & response-action log (decision-log plan §6; integration
plan C3, C8, C9, C24, C30, C34, §1 #7, #9, #22b)."""
import hashlib
import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services import decision_log_service as svc

API = '/api/v1'
SEEDED = ('Administrator', 'Incident Responder', 'Analyst', 'Manager', 'Operator', 'Viewer')


@pytest.fixture
def inc(make_incident, users):
    """An incident every seeded org-A user can see."""
    return make_incident(assign=[users[r] for r in SEEDED])


@pytest.fixture
def client(users, auth):
    """client(role) -> AuthClient for a seeded org-A user."""
    return lambda role: auth(users[role])


def dpath(inc, *parts):
    return '/'.join([f'{API}/incidents/{inc.id}/decisions', *[str(p) for p in parts]])


def apath(inc, *parts):
    return '/'.join([f'{API}/incidents/{inc.id}/response-actions', *[str(p) for p in parts]])


def if_match(version):
    return {'If-Match': f'"{version}"'}


def make_decision(c, inc, **body):
    body = {'title': 'Do not pay ransom', 'decision': 'We will not pay.', 'category': 'ransom_legal', **body}
    resp = c.post(dpath(inc), json=body)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def make_action(c, inc, **body):
    body = {'action_type': 'other', 'title': 'Notify insurer', 'target_type': 'external',
            'target_label': 'Insurer', **body}
    resp = c.post(apath(inc), json=body)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def make_host(db, inc, hostname='WS-01', status='active'):
    from app.models import CompromisedHost
    host = CompromisedHost(incident_id=inc.id, hostname=hostname, containment_status=status,
                           created_by=inc.created_by)
    db.session.add(host)
    db.session.commit()
    return host


# ── decisions: create / list / get / update ───────────────────────────────

def test_create_list_get_numbering(client, inc):
    ir = client('Incident Responder')
    d1 = make_decision(ir, inc, rationale='Policy', alternatives=[{'option': 'Pay', 'reason_not_chosen': 'Policy'}])
    d2 = make_decision(ir, inc, title='Isolate the DC')
    assert (d1['number'], d2['number']) == (1, 2)
    assert d1['display_id'] == 'D-001' and d1['status'] == 'proposed' and d1['version'] == 1
    assert d1['users']['decided_by_user_id']['name'] and d1['revision_count'] == 1

    listing = ir.get(dpath(inc)).get_json()
    assert [d['display_id'] for d in listing['items']] == ['D-001', 'D-002'] and listing['total'] == 2
    got = ir.get(dpath(inc, d1['id']))
    assert got.status_code == 200 and got.headers['ETag'] == '"1"'
    assert ir.get(dpath(inc), query_string={'q': 'isolate'}).get_json()['total'] == 1


def test_update_requires_if_match_reason_and_detects_conflicts(client, inc):
    ir = client('Incident Responder')
    d = make_decision(ir, inc)
    url = dpath(inc, d['id'])
    assert ir.put(url, json={'title': 'X', 'reason': 'typo'}).status_code == 428      # C8: required
    assert ir.put(url, json={'title': 'X'}, headers=if_match(1)).status_code == 400   # reason required
    resp = ir.put(url, json={'title': 'Do not pay (final)', 'reason': 'wording'}, headers=if_match(1))
    assert resp.status_code == 200 and resp.get_json()['version'] == 2
    stale = ir.put(url, json={'title': 'Y', 'reason': 'r'}, headers=if_match(1))
    assert stale.status_code == 409 and stale.get_json()['error'] == 'conflict'
    # The body key works too (MCP).
    resp = ir.put(url, json={'rationale': 'Board policy', 'reason': 'add', 'expected_version': 2})
    assert resp.status_code == 200
    assert ir.put(url, json={'rationale': 'Board policy', 'reason': 'noop'},
                  headers=if_match(3)).get_json()['error'] == 'no_changes'


def test_no_delete_route(client, inc):
    ir = client('Incident Responder')
    d = make_decision(ir, inc)
    assert ir.delete(dpath(inc, d['id'])).status_code == 405
    a = make_action(ir, inc)
    assert ir.delete(apath(inc, a['id'])).status_code == 405


def test_validation_errors(client, inc, make_incident):
    ir = client('Incident Responder')
    assert ir.post(dpath(inc), json={'decision': 'x'}).status_code == 400
    assert ir.post(dpath(inc), json={'title': 't', 'decision': 'x', 'category': 'bogus'}).status_code == 400
    other = make_incident()
    foreign = make_decision(client('Administrator'), other)
    resp = ir.post(dpath(inc), json={'title': 't', 'decision': 'x',
                                     'links': [{'evidence_type': 'decision', 'evidence_id': foreign['id']}]})
    assert resp.status_code == 400 and resp.get_json()['error'] == 'invalid_evidence_refs'
    d = make_decision(ir, inc)
    resp = ir.post(dpath(inc, d['id'], 'supersede'), json={'superseded_by_id': foreign['id']}, headers=if_match(1))
    assert resp.status_code == 400


# ── approve / reject / supersede ──────────────────────────────────────────

def test_approve_requires_permission_external_attestation_allowed(client, inc, users):
    analyst = client('Analyst')
    d = make_decision(analyst, inc)
    url = dpath(inc, d['id'], 'approve')
    assert analyst.post(url, json={}, headers=if_match(1)).status_code == 403          # no decisions:approve
    assert client('Viewer').post(url, json={'approved_by_name': 'GC'}, headers=if_match(1)).status_code == 403
    # External attestation needs only decisions:update.
    resp = analyst.post(url, json={'approved_by_name': 'General Counsel'}, headers=if_match(1))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'approved' and body['approved_by_name'] == 'General Counsel'
    assert body['approved_by_user_id'] is None and body['self_approved'] is False

    d2 = make_decision(analyst, inc)
    resp = client('Manager').post(dpath(inc, d2['id'], 'approve'), json={}, headers=if_match(1))
    assert resp.status_code == 200
    assert resp.get_json()['approved_by_user_id'] == str(users['Manager'].id)
    # approved -> approve again is an invalid transition
    again = client('Manager').post(dpath(inc, d2['id'], 'approve'), json={}, headers=if_match(2))
    assert again.status_code == 409 and again.get_json()['error'] == 'invalid_transition'


def test_self_approval_is_flagged_and_reject_reopen(client, inc):
    ir = client('Incident Responder')
    d = make_decision(ir, inc)
    assert ir.post(dpath(inc, d['id'], 'approve'), json={}, headers=if_match(1)).get_json()['self_approved'] is True
    d2 = make_decision(ir, inc)
    assert client('Analyst').post(dpath(inc, d2['id'], 'reject'), json={'reason': 'no'},
                                  headers=if_match(1)).status_code == 403
    assert ir.post(dpath(inc, d2['id'], 'reject'), json={}, headers=if_match(1)).status_code == 400
    assert ir.post(dpath(inc, d2['id'], 'reject'), json={'reason': 'too risky'},
                   headers=if_match(1)).get_json()['status'] == 'rejected'
    resp = ir.post(dpath(inc, d2['id'], 'reopen'), json={'reason': 'new facts'}, headers=if_match(2))
    assert resp.get_json()['status'] == 'proposed'
    resp = ir.post(dpath(inc, d2['id'], 'supersede'), json={'superseded_by_id': d['id']}, headers=if_match(3))
    assert resp.status_code == 200 and resp.get_json()['superseded_by']['display_id'] == 'D-001'


# ── privileged decisions (REST) ───────────────────────────────────────────

def test_privileged_decision_hidden_without_permission(client, inc):
    ir = client('Incident Responder')
    secret = make_decision(ir, inc, title='Counsel advice: SECRET-TITLE', is_privileged=True)
    make_decision(ir, inc, title='Public decision')

    for role in ('Analyst', 'Viewer', 'Operator'):
        c = client(role)
        assert c.get(dpath(inc, secret['id'])).status_code == 404
        listing = c.get(dpath(inc)).get_json()
        assert secret['id'] not in {d['id'] for d in listing['items']}
        assert 'SECRET-TITLE' not in json.dumps(listing)
        assert c.get(dpath(inc, secret['id'], 'revisions')).status_code == 404
        timeline = c.get(f'{API}/incidents/{inc.id}/response-timeline').get_json()
        assert 'SECRET-TITLE' not in json.dumps(timeline)
    # Analysts cannot create privileged decisions or flip the flag.
    assert client('Analyst').post(dpath(inc), json={'title': 't', 'decision': 'd',
                                                    'is_privileged': True}).status_code == 403
    assert client('Manager').get(dpath(inc, secret['id'])).status_code == 200


def test_privileged_links_and_action_refs_do_not_leak(client, inc):
    ir = client('Incident Responder')
    secret = make_decision(ir, inc, title='SECRET-TITLE', is_privileged=True)
    a = make_action(ir, inc, decision_id=secret['id'],
                    links=[{'evidence_type': 'decision', 'evidence_id': secret['id']}])
    analyst = client('Analyst')
    got = analyst.get(apath(inc, a['id'])).get_json()
    assert got['decision_id'] is None and got['decision'] is None and got['decision_restricted'] is True
    assert 'SECRET-TITLE' not in json.dumps(got)
    # An analyst cannot link to (or probe) a privileged decision.
    resp = analyst.post(apath(inc), json={'action_type': 'other', 'title': 't', 'decision_id': secret['id']})
    assert resp.status_code == 400
    resp = analyst.post(dpath(inc), json={'title': 't', 'decision': 'd',
                                          'links': [{'evidence_type': 'decision', 'evidence_id': secret['id']}]})
    assert resp.status_code == 400


def test_org_isolation(client, inc, users, auth):
    d = make_decision(client('Administrator'), inc)
    other = auth(users['admin_b'])
    assert other.get(dpath(inc)).status_code == 404
    assert other.get(dpath(inc, d['id'])).status_code == 404


# ── response actions ──────────────────────────────────────────────────────

def test_action_lifecycle_isolate_host_applies_and_rolls_back(db, client, inc, users):
    host = make_host(db, inc)
    ir = client('Incident Responder')
    a = make_action(ir, inc, action_type='isolate_host', title='Isolate WS-01', target_type='host',
                    target_id=str(host.id), target_label='ignored')
    assert a['target_label'] == 'WS-01' and a['status'] == 'requested'
    url = lambda ev: apath(inc, a['id'], ev)  # noqa: E731
    assert client('Analyst').post(url('authorize'), json={}, headers=if_match(1)).status_code == 403
    resp = client('Manager').post(url('authorize'), json={}, headers=if_match(1))
    assert resp.status_code == 200 and resp.get_json()['authorized_by_user_id'] == str(users['Manager'].id)
    assert ir.post(url('verify'), json={'verification_result': 'success', 'verification_method': 'ping'},
                   headers=if_match(2)).status_code == 409                      # not executed yet
    resp = ir.post(url('execute'), json={'apply_target_state': True}, headers=if_match(2))
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['status'] == 'executed' and body['target_state_after'] == {'field': 'containment_status',
                                                                          'value': 'isolated'}
    db.session.expire_all()
    from app.models import AuditLog, CompromisedHost
    assert db.session.get(CompromisedHost, host.id).containment_status == 'isolated'
    assert AuditLog.query.filter_by(resource_type='compromised_host', resource_id=host.id).count() >= 1

    resp = client('Analyst').post(url('verify'), json={'verification_result': 'success',
                                                       'verification_method': 'EDR console'},
                                  headers=if_match(3))
    assert resp.status_code == 200 and resp.get_json()['self_verified'] is False
    assert ir.post(url('rollback'), json={}, headers=if_match(4)).status_code == 400       # reason
    resp = ir.post(url('rollback'), json={'reason': 'false positive'}, headers=if_match(4))
    assert resp.status_code == 200 and resp.get_json()['status'] == 'rolled_back'
    db.session.expire_all()
    assert db.session.get(CompromisedHost, host.id).containment_status == 'active'
    revs = ir.get(apath(inc, a['id'], 'revisions')).get_json()
    assert [r['event'] for r in revs['items']] == ['create', 'authorize', 'execute', 'verify', 'rollback']
    assert revs['verification']['status'] == 'intact'


def test_target_state_needs_host_permission_and_rollback_conflict(db, client, inc):
    host = make_host(db, inc, 'WS-02')
    ir = client('Incident Responder')
    a = make_action(ir, inc, action_type='isolate_host', title='Isolate', target_type='host', target_id=str(host.id))
    operator = client('Operator')            # response_actions:update but not hosts:update
    ir.post(apath(inc, a['id'], 'authorize'), json={'authorized_by_name': 'CISO'}, headers=if_match(1))
    resp = operator.post(apath(inc, a['id'], 'execute'), json={'apply_target_state': True}, headers=if_match(2))
    assert resp.status_code == 403
    assert ir.post(apath(inc, a['id'], 'execute'), json={'apply_target_state': True},
                   headers=if_match(2)).status_code == 200
    host = db.session.get(type(host), host.id)
    host.containment_status = 'reimaged'
    db.session.commit()
    resp = ir.post(apath(inc, a['id'], 'rollback'), json={'reason': 'r'}, headers=if_match(3))
    assert resp.status_code == 409 and resp.get_json()['error'] == 'target_state_changed'
    resp = ir.post(apath(inc, a['id'], 'rollback'), json={'reason': 'r', 'restore_target_state': False},
                   headers=if_match(3))
    assert resp.status_code == 200


def test_retroactive_create_and_account_target(db, client, inc):
    from app.models import CompromisedAccount
    acct = CompromisedAccount(incident_id=inc.id, account_name='svc_backup', status='active',
                              account_type='domain', datetime_seen=datetime.now(timezone.utc),
                              created_by=inc.created_by)
    db.session.add(acct)
    db.session.commit()
    ir = client('Incident Responder')
    a = make_action(ir, inc, action_type='disable_account', title='Disable', target_type='account',
                    target_id=str(acct.id), authorized_by_name='IT lead', executed_at='2026-01-01T10:00:00Z',
                    executed_by_name='MSSP', verified_at='2026-01-01T11:00:00Z', verification_result='success')
    assert a['status'] == 'verified' and a['executed_by_name'] == 'MSSP' and a['revision_count'] == 1
    assert ir.post(apath(inc), json={'action_type': 'other', 'title': 't', 'target_type': 'host',
                                     'target_id': str(uuid.uuid4())}).status_code == 400
    b = make_action(ir, inc, action_type='disable_account', title='Disable 2', target_type='account',
                    target_id=str(acct.id))
    ir.post(apath(inc, b['id'], 'authorize'), json={'authorized_by_name': 'x'}, headers=if_match(1))
    resp = ir.post(apath(inc, b['id'], 'execute'), json={'apply_target_state': True}, headers=if_match(2))
    assert resp.status_code == 200
    db.session.expire_all()
    assert db.session.get(CompromisedAccount, acct.id).status == 'disabled'


def test_invalid_transitions_and_cancel(client, inc):
    ir = client('Incident Responder')
    a = make_action(ir, inc)
    assert ir.post(apath(inc, a['id'], 'start'), json={}, headers=if_match(1)).get_json()['error'] == \
        'invalid_transition'
    assert ir.post(apath(inc, a['id'], 'cancel'), json={}, headers=if_match(1)).status_code == 400
    assert ir.post(apath(inc, a['id'], 'cancel'), json={'reason': 'dup'},
                   headers=if_match(1)).get_json()['status'] == 'cancelled'
    assert ir.post(apath(inc, a['id'], 'authorize'), json={}, headers=if_match(2)).status_code == 409


# ── revision chain: verify, tamper, append-only trigger ───────────────────

def _decision_row(db, did):
    from app.models import IncidentDecision
    db.session.expire_all()
    return db.session.get(IncidentDecision, uuid.UUID(did))


def _without_trigger(db, sql, **params):
    db.session.execute(text('ALTER TABLE decision_log_revisions DISABLE TRIGGER decision_log_revisions_no_update'))
    try:
        db.session.execute(text(sql), params)
    finally:
        db.session.execute(text('ALTER TABLE decision_log_revisions ENABLE TRIGGER decision_log_revisions_no_update'))
    db.session.commit()


def _edit(c, inc, d, n):
    for i in range(n):
        resp = c.put(dpath(inc, d['id']), json={'rationale': f'r{i}', 'reason': f'edit {i}'},
                     headers=if_match(d['version'] + i))
        assert resp.status_code == 200


def test_chain_verifies_and_revisions_are_hash_linked(db, client, inc):
    ir = client('Incident Responder')
    d = make_decision(ir, inc)
    _edit(ir, inc, d, 2)
    row = _decision_row(db, d['id'])
    revs = svc.revisions(row)
    assert [r.seq for r in revs] == [1, 2, 3]
    assert revs[0].prev_hash == svc.genesis('decision', row.id)
    assert revs[1].prev_hash == revs[0].entry_hash and revs[2].prev_hash == revs[1].entry_hash
    assert revs[1].changes['rationale'] == {'from': None, 'to': 'r0'} and revs[1].reason == 'edit 0'
    result = svc.verify_record(row)
    assert result['status'] == 'intact' and result['signatures']['valid'] == 3


def test_tampered_snapshot_is_detected(db, client, inc):
    ir = client('Incident Responder')
    d = make_decision(ir, inc)
    _edit(ir, inc, d, 1)
    row = _decision_row(db, d['id'])
    rev = svc.revisions(row)[0]
    _without_trigger(db, "UPDATE decision_log_revisions SET snapshot = jsonb_set(snapshot, '{title}', "
                         "'\"We will pay\"') WHERE id = :id", id=rev.id)
    result = svc.verify_record(_decision_row(db, d['id']))
    assert result['status'] == 'compromised'
    assert result['signature_status_by_id'][str(rev.id)] == 'invalid'
    assert any(b['reason'] == 'entry_hash_mismatch' for b in result['breaks'])
    api = ir.get(dpath(inc, d['id'], 'revisions')).get_json()
    assert api['verification']['status'] == 'compromised'
    assert [r['signature_status'] for r in api['items']] == ['invalid', 'valid']


def test_deleted_middle_revision_breaks_chain(db, client, inc):
    ir = client('Incident Responder')
    d = make_decision(ir, inc)
    _edit(ir, inc, d, 2)
    row = _decision_row(db, d['id'])
    middle = svc.revisions(row)[1]
    _without_trigger(db, 'DELETE FROM decision_log_revisions WHERE id = :id', id=middle.id)
    result = svc.verify_record(_decision_row(db, d['id']))
    assert result['status'] == 'broken'
    assert {b['reason'] for b in result['breaks']} >= {'seq_gap', 'prev_hash_mismatch'}


def test_head_row_drift_is_detected(db, client, inc):
    d = make_decision(client('Incident Responder'), inc)
    db.session.execute(text('UPDATE incident_decisions SET title = :t WHERE id = :id'),
                       {'t': 'rewritten', 'id': uuid.UUID(d['id'])})
    db.session.commit()
    result = svc.verify_record(_decision_row(db, d['id']))
    assert result['status'] == 'broken' and result['breaks'][0]['reason'] == 'head_drift'


def test_revisions_are_append_only(db, client, inc):
    from sqlalchemy.exc import DBAPIError
    d = make_decision(client('Incident Responder'), inc)
    for sql in ("UPDATE decision_log_revisions SET reason = 'x' WHERE record_id = :id",
                'DELETE FROM decision_log_revisions WHERE record_id = :id'):
        with pytest.raises(DBAPIError) as exc:
            db.session.execute(text(sql), {'id': uuid.UUID(d['id'])})
            db.session.flush()
        db.session.rollback()
        assert 'append-only' in str(exc.value)
    with pytest.raises(DBAPIError):
        db.session.execute(text('TRUNCATE decision_log_revisions'))
    db.session.rollback()


def test_actor_fk_is_no_action(db):
    from sqlalchemy import inspect
    fks = {fk['constrained_columns'][0]: fk['options'].get('ondelete')
           for fk in inspect(db.engine).get_foreign_keys('decision_log_revisions')}
    assert fks['actor_id'] is None and fks['incident_id'] == 'CASCADE'


# ── realtime (C9) ─────────────────────────────────────────────────────────

@pytest.fixture
def sock(app, auth):
    from app import socketio
    clients = []

    def make(user):
        c = socketio.test_client(app, auth={'token': auth(user).access_token})
        c.get_received()
        clients.append(c)
        return c
    yield make
    for c in clients:
        if c.is_connected():
            c.disconnect()


def _received(c):
    return [(e['name'], e['args'][0] if e['args'] else None) for e in c.get_received()]


def test_privileged_decision_events_reach_only_privileged_scope(sock, client, inc, users):
    analyst, manager = sock(users['Analyst']), sock(users['Manager'])
    for c in (analyst, manager):
        ack = c.emit('incident:join', {'incident_id': str(inc.id)}, callback=True)
        assert 'decisions' in ack['scopes']
    assert 'decisions_privileged' not in analyst.emit('incident:join', {'incident_id': str(inc.id)},
                                                      callback=True)['scopes']
    analyst.get_received()
    manager.get_received()

    ir = client('Incident Responder')
    secret = make_decision(ir, inc, title='SECRET-TITLE', is_privileged=True)
    ir.put(dpath(inc, secret['id']), json={'rationale': 'x', 'reason': 'r'}, headers=if_match(1))
    got_analyst = _received(analyst)
    assert secret['id'] not in json.dumps(got_analyst) and 'SECRET-TITLE' not in json.dumps(got_analyst)
    changes = [p for name, p in _received(manager) if name == 'entity:changed']
    assert [(p['entity'], p['op']) for p in changes] == [('decision_privileged', 'created'),
                                                         ('decision_privileged', 'updated')]
    assert changes[0]['data']['title'] == 'SECRET-TITLE'

    public = make_decision(ir, inc, title='Public')
    events = [p for name, p in _received(analyst) if name == 'entity:changed']
    assert [(p['entity'], p['id']) for p in events] == [('decision', public['id'])]
    # Flagging it privileged: the public scope only hears that it is gone.
    _received(manager)
    resp = ir.put(dpath(inc, public['id']), json={'is_privileged': True, 'reason': 'counsel'},
                  headers=if_match(1))
    assert resp.status_code == 200
    events = [p for name, p in _received(analyst) if name == 'entity:changed']
    assert [(p['entity'], p['op']) for p in events] == [('decision', 'deleted')] and 'data' not in events[0]
    events = [p for name, p in _received(manager) if name == 'entity:changed']
    assert [(p['entity'], p['op']) for p in events] == [('decision', 'deleted'),
                                                        ('decision_privileged', 'created')]


# ── API keys (C30) ────────────────────────────────────────────────────────

def test_api_keys_cannot_hold_or_use_approval_permissions(app, db, client, inc, fresh_user, make_api_key,
                                                          key_client):
    from app.models import IncidentAssignment
    from app.services.api_key_service import ApiKeyError
    owner = fresh_user('Incident Responder')
    db.session.add(IncidentAssignment(incident_id=inc.id, user_id=owner.id, assigned_by=inc.created_by))
    db.session.commit()
    for perm in ('decisions:approve', 'response_actions:authorize', 'decisions:read_privileged'):
        with pytest.raises(ApiKeyError):
            make_api_key(owner, ['decisions:read', perm])
        db.session.rollback()
    _key, full = make_api_key(owner, ['incidents:read', 'incidents:read_team', 'decisions:read', 'decisions:create',
                                      'decisions:update', 'response_actions:read', 'response_actions:update'])
    kc = key_client(full)
    d = make_decision(kc, inc)
    resp = kc.post(dpath(inc, d['id'], 'approve'), json={}, headers=if_match(1))
    assert resp.status_code == 403            # the owner may approve; the key may not
    secret = make_decision(client('Incident Responder'), inc, is_privileged=True)
    assert kc.get(dpath(inc, secret['id'])).status_code == 404
    a = make_action(client('Incident Responder'), inc)
    assert kc.post(apath(inc, a['id'], 'authorize'), json={}, headers=if_match(1)).status_code == 403
    assert kc.post(apath(inc, a['id'], 'authorize'), json={'authorized_by_name': 'CISO'},
                   headers=if_match(1)).status_code == 200


# ── export (C24) ──────────────────────────────────────────────────────────

def _export(c, inc, **params):
    return c.get(f'{API}/incidents/{inc.id}/decision-log/export', query_string=params)


def test_export_requires_incidents_export_and_escapes_csv(db, client, inc):
    ir = client('Incident Responder')
    make_decision(ir, inc, title='=cmd|calc', rationale='+SUM(A1)')
    make_decision(ir, inc, title='PRIV-TITLE', is_privileged=True)
    make_action(ir, inc, title='@notify')
    assert _export(client('Analyst'), inc).status_code == 403          # no incidents:export
    assert _export(client('Viewer'), inc, format='csv').status_code == 403

    resp = _export(ir, inc, format='csv')
    assert resp.status_code == 200 and 'attachment' in resp.headers['Content-Disposition']
    body = resp.data.decode()
    assert "'=cmd|calc" in body and "'+SUM(A1)" in body and "'@notify" in body
    assert 'PRIV-TITLE' not in body                                    # not without include_privileged

    data = _export(ir, inc, format='json', include_revisions='1').get_json()
    assert {d['title'] for d in data['decisions']} == {'=cmd|calc'}
    assert data['decisions'][0]['revisions'][0]['signature_status'] == 'valid'
    assert len(data['response_actions']) == 1
    priv = _export(client('Manager'), inc, format='json', include_privileged='1').get_json()
    assert 'PRIV-TITLE' in {d['title'] for d in priv['decisions']}
    assert _export(ir, inc, format='xml').status_code == 400
    assert _export(ir, inc, format='json', kind='actions').get_json()['decisions'] == []

    from app.models import AuditLog
    row = (AuditLog.query.filter_by(action='export', resource_type='decision_log', incident_id=inc.id)
           .order_by(AuditLog.created_at.desc()).first())
    assert row is not None and row.details['kind'] == 'actions'


def test_export_pdf_renders(client, inc):
    ir = client('Incident Responder')
    make_decision(ir, inc, title='<script>alert(1)</script>')
    resp = _export(ir, inc, format='pdf')
    assert resp.status_code == 200 and resp.data.startswith(b'%PDF')


def test_response_timeline_rows(client, inc):
    ir = client('Incident Responder')
    make_decision(ir, inc, title='Decide')
    make_action(ir, inc, title='Act', executed_at='2026-01-01T00:00:00Z')
    rows = ir.get(f'{API}/incidents/{inc.id}/response-timeline').get_json()['items']
    assert {r['kind'] for r in rows} == {'decision', 'response'}
    assert client('Viewer').get(f'{API}/incidents/{inc.id}/response-timeline').status_code == 200


# ── report appendix (C34) and AI exclusion (§1 #22b) ──────────────────────

@pytest.fixture
def report_store(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, 'LOCAL_ARTIFACT_DIR', str(tmp_path))
    return tmp_path


def test_report_appendix_is_inside_the_snapshot_and_never_sent_to_ai(db, client, inc, report_store,
                                                                     monkeypatch):
    from app.api.v1.endpoints import reports as reports_mod
    from app.models import Report
    from app.services.ai_service import ai_service
    ir = client('Incident Responder')
    make_decision(ir, inc, title='Engage outside counsel <b>now</b>')
    make_decision(ir, inc, title='PRIV-TITLE', is_privileged=True)
    make_action(ir, inc, title='Block C2 domain', action_type='block_ioc')
    seen = {}

    def fake_report(**kwargs):
        seen.update(kwargs)
        return '# AI analysis\n\nNarrative.'
    monkeypatch.setattr(ai_service, 'select_provider', lambda *a, **k: 'openai')
    monkeypatch.setattr(ai_service, 'generate_report', fake_report)
    monkeypatch.setattr(reports_mod, 'html_to_pdf', lambda html: b'%PDF-test\n' + html.encode('utf-8'))

    resp = client('Administrator').post(f'{API}/incidents/{inc.id}/reports/generate-pdf',
                                        json={'report_type': 'full'})
    assert resp.status_code == 200
    report = Report.query.filter_by(incident_id=inc.id).one()
    stored = (report_store / report.storage_path).read_bytes()
    assert hashlib.sha256(stored).hexdigest() == report.sha256 == resp.headers['X-Report-SHA256']
    html = stored.decode('utf-8')
    assert 'Decisions &amp; Response Actions' in html and 'D-001' in html and 'A-001' in html
    assert 'Engage outside counsel &lt;b&gt;now&lt;/b&gt;' in html             # escaped
    assert 'PRIV-TITLE' not in html                                             # never in a report
    assert html.index('Decisions &amp; Response Actions') < html.index('<div class="report-footer">')
    # The AI provider got the incident data but no decision-log data.
    sent = json.dumps(seen, default=str)
    assert seen and 'outside counsel' not in sent and 'Block C2' not in sent and 'PRIV-TITLE' not in sent


def test_executive_report_has_no_appendix(db, client, inc, report_store, monkeypatch):
    from app.api.v1.endpoints import reports as reports_mod
    monkeypatch.setattr(reports_mod, 'html_to_pdf', lambda html: b'%PDF-test\n' + html.encode('utf-8'))
    make_decision(client('Incident Responder'), inc)
    resp = client('Administrator').post(f'{API}/incidents/{inc.id}/reports/generate-pdf',
                                        json={'report_type': 'executive'})
    assert resp.status_code == 200 and b'Decisions &amp; Response Actions' not in resp.data


# ── custody export referenced_by, purge, registrations ────────────────────

def test_custody_export_lists_referencing_records(db, client, inc, make_evidence, make_artifact, users):
    from app.models import TimelineEvent
    item = make_evidence(inc)
    art = make_artifact(inc, item=item)
    ev = TimelineEvent(incident_id=inc.id, timestamp=datetime.now(timezone.utc), activity='4624 logon',
                       created_by=users['Administrator'].id, source_evidence_id=item.id)
    db.session.add(ev)
    db.session.commit()
    ir = client('Incident Responder')
    d = make_decision(ir, inc, title='Image the DC',
                      links=[{'evidence_type': 'evidence_item', 'evidence_id': str(item.id)}])
    make_decision(ir, inc, title='PRIV-TITLE', is_privileged=True,
                  links=[{'evidence_type': 'evidence_item', 'evidence_id': str(item.id)}])
    a = make_action(ir, inc, title='Quarantine', links=[{'evidence_type': 'artifact', 'evidence_id': str(art.id)}])
    make_decision(ir, inc, title='Unrelated')

    url = f'{API}/incidents/{inc.id}/evidence/{item.id}/custody/export'
    body = ir.get(url, query_string={'format': 'json'}).get_json()
    refs = body['referenced_by']
    assert d['id'] in {r['id'] for r in refs['decision']} and len(refs['decision']) == 2   # IR: privileged too
    assert [r['id'] for r in refs['response_action']] == [a['id']]
    assert [r['id'] for r in refs['timeline_event']] == [str(ev.id)]
    analyst_refs = client('Analyst').get(url, query_string={'format': 'json'}).get_json()['referenced_by']
    assert 'PRIV-TITLE' not in json.dumps(analyst_refs) and [r['id'] for r in analyst_refs['decision']] == [d['id']]


def test_refs_registered_and_privileged_label_redacted(db, client, inc):
    from app.services.evidence_refs import resolve_refs
    secret = make_decision(client('Incident Responder'), inc, title='PRIV-TITLE', is_privileged=True)
    out = resolve_refs(inc.id, [{'evidence_type': 'decision', 'evidence_id': secret['id']}])
    assert out[0]['label'] == 'D-001 [privileged]'


def test_purge_removes_the_decision_log(db, client, inc, users, auth):
    from app.models import DecisionLogRevision, IncidentDecision
    ir = client('Incident Responder')
    make_decision(ir, inc)
    make_action(ir, inc)
    admin = auth(users['Administrator'])
    assert admin.post(f'{API}/incidents/{inc.id}/archive').status_code == 200
    assert admin.delete(f'{API}/incidents/{inc.id}/permanent').status_code == 200
    db.session.expire_all()
    assert IncidentDecision.query.filter_by(incident_id=inc.id).count() == 0
    assert DecisionLogRevision.query.filter_by(incident_id=inc.id).count() == 0
