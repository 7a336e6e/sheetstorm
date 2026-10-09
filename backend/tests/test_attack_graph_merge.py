"""W3-DFIR-C: attack graph auto-generate merge / replace (surface-dfir §3.9).

Merge (default) adds what is missing and never moves, edits or deletes the
analyst's work; replace is destructive and needs an explicit confirm.
"""
import math
from datetime import datetime, timedelta, timezone

import pytest

API = '/api/v1'
T0 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


@pytest.fixture
def case(app, db, users, make_incident):
    from app.models import (CompromisedAccount, CompromisedHost, HostBasedIndicator, MalwareTool,
                            NetworkIndicator, TimelineEvent)
    uid = users['Administrator'].id
    inc = make_incident()
    h1 = CompromisedHost(incident_id=inc.id, hostname='H1', ip_address='10.0.0.1', first_seen=T0, created_by=uid)
    h2 = CompromisedHost(incident_id=inc.id, hostname='H2', ip_address='10.0.0.2', first_seen=T0 + timedelta(hours=1),
                         system_type='server', created_by=uid)
    db.session.add_all([h1, h2])
    db.session.flush()
    db.session.add_all([
        CompromisedAccount(incident_id=inc.id, datetime_seen=T0, account_name='alice', account_type='domain',
                           domain='CORP', host_id=h1.id, host_system='H1', created_by=uid),
        MalwareTool(incident_id=inc.id, file_name='beacon.exe', host_id=h1.id, host='H1', created_by=uid),
        HostBasedIndicator(incident_id=inc.id, artifact_type='file', artifact_value='C:\\evil.exe', host_id=h1.id,
                           host='H1', created_by=uid),
        NetworkIndicator(incident_id=inc.id, dns_ip='c2.example', host_id=h1.id, direction='outbound',
                         created_by=uid),
        TimelineEvent(incident_id=inc.id, timestamp=T0, activity='first', host_id=h1.id, created_by=uid),
        TimelineEvent(incident_id=inc.id, timestamp=T0 + timedelta(hours=2), activity='moved to H2',
                      host_id=h2.id, created_by=uid),
    ])
    db.session.commit()
    inc.hosts = {'H1': h1, 'H2': h2}
    return inc


def generate(client, inc, **body):
    return client.post(f'{API}/incidents/{inc.id}/attack-graph/auto-generate', json=body)


def nodes(inc):
    from app.models import AttackGraphNode
    from app import db
    db.session.expire_all()
    return AttackGraphNode.query.filter_by(incident_id=inc.id).all()


def edges(inc):
    from app.models import AttackGraphEdge
    from app import db
    db.session.expire_all()
    return AttackGraphEdge.query.filter_by(incident_id=inc.id).all()


def by_label(inc):
    return {n.label: n for n in nodes(inc)}


# ── first generation ──────────────────────────────────────────────────────

def test_first_generate_defaults_to_merge_and_tags_everything_auto(admin, case):
    resp = generate(admin, case)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body['mode'] == 'merge' and body['created'] == {'nodes': len(nodes(case)), 'edges': len(edges(case))}
    assert body['created']['nodes'] == 6   # 2 hosts, account, malware, host ioc, network ioc
    for node in nodes(case):
        assert node.extra_data['origin'] == 'auto' and node.extra_data['auto_key']
    for edge in edges(case):
        assert edge.extra_data['origin'] == 'auto' and '->' in edge.extra_data['auto_key']
    keys = {n.extra_data['auto_key'] for n in nodes(case)}
    h1 = case.hosts['H1']
    assert f'host:{h1.id}' in keys and 'nioc:c2.example' in keys
    assert any(k.startswith('account:') for k in keys) and any(k.startswith('malware:') for k in keys)
    assert any(k.startswith('hioc:') for k in keys)
    assert any(e.edge_type == 'lateral_movement' for e in edges(case))
    assert by_label(case)['H1'].is_initial_access is True


def test_second_run_is_a_noop(admin, case):
    generate(admin, case)
    before = {n.id for n in nodes(case)}, {e.id for e in edges(case)}
    resp = generate(admin, case)
    assert resp.status_code == 200 and resp.get_json()['created'] == {'nodes': 0, 'edges': 0}
    assert ({n.id for n in nodes(case)}, {e.id for e in edges(case)}) == before


# ── merge keeps the analyst's work ───────────────────────────────────────

def test_merge_keeps_manual_nodes_edges_and_moved_positions_and_adds_new_hosts(admin, db, users, case):
    from app.models import AttackGraphEdge, AttackGraphNode, CompromisedHost
    generate(admin, case)
    uid = users['Administrator'].id
    h1_node = by_label(case)['H1']
    h1_node.position_x, h1_node.position_y = 4321.0, -987.0
    manual = AttackGraphNode(incident_id=case.id, node_type='attacker', label='APT-X', position_x=7, position_y=9,
                             extra_data={'note': 'mine'}, created_by=uid)
    db.session.add(manual)
    db.session.flush()
    manual_edge = AttackGraphEdge(incident_id=case.id, source_node_id=manual.id, target_node_id=h1_node.id,
                                  edge_type='initial_access', label='phish', created_by=uid)
    db.session.add(manual_edge)
    db.session.add(CompromisedHost(incident_id=case.id, hostname='H3', ip_address='10.0.0.3',
                                   first_seen=T0 + timedelta(hours=3), created_by=uid))
    db.session.commit()
    manual_id, edge_id, h1_id = manual.id, manual_edge.id, h1_node.id

    resp = generate(admin, case, mode='merge')
    assert resp.status_code == 201 and resp.get_json()['created']['nodes'] == 1

    graph = by_label(case)
    assert 'H3' in graph and 'H3' != 'H1'
    assert graph['H1'].id == h1_id and (graph['H1'].position_x, graph['H1'].position_y) == (4321.0, -987.0)
    kept = graph['APT-X']
    assert kept.id == manual_id and (kept.position_x, kept.position_y) == (7, 9)
    assert kept.extra_data == {'note': 'mine'}, 'manual nodes are never touched'
    assert edge_id in {e.id for e in edges(case)}
    assert graph['H3'].extra_data['origin'] == 'auto'
    assert graph['H3'].is_initial_access is False


def test_merge_positions_new_sub_nodes_around_the_hosts_current_position(admin, db, users, case):
    from app.models import MalwareTool
    generate(admin, case)
    h1_node = by_label(case)['H1']
    h1_node.position_x, h1_node.position_y = 5000.0, 5000.0
    db.session.commit()
    db.session.add(MalwareTool(incident_id=case.id, file_name='second.exe', host_id=case.hosts['H1'].id,
                               host='H1', created_by=users['Administrator'].id))
    db.session.commit()
    generate(admin, case)
    new = by_label(case)['second.exe']
    distance = math.hypot(new.position_x - 5000.0, new.position_y - 5000.0)
    assert distance == pytest.approx(180.0, abs=0.5)
    existing = by_label(case)['beacon.exe']
    assert math.hypot(existing.position_x - 5000.0, existing.position_y - 5000.0) > 1000, 'existing nodes do not move'


def test_merge_refreshes_auto_nodes_only(admin, db, case):
    generate(admin, case)
    graph = by_label(case)
    auto_account = graph['CORP\\alice']
    auto_account.position_x = 111.0
    # a node the analyst took over: same FK, no origin -> hands off
    h2_node = graph['H2']
    h2_node.extra_data = {'my': 'edit'}
    h2_node.label = 'Domain Controller 2'
    db.session.commit()
    case.hosts['H1'].containment_status = 'contained'
    case.hosts['H2'].hostname = 'H2-renamed'
    from app.models import CompromisedAccount
    CompromisedAccount.query.filter_by(incident_id=case.id).one().status = 'disabled'
    db.session.commit()

    generate(admin, case)
    graph = by_label(case)
    assert graph['H1'].extra_data['containment_status'] == 'contained'          # auto node refreshed
    assert graph['CORP\\alice'].extra_data['status'] == 'disabled'
    assert graph['CORP\\alice'].position_x == 111.0                               # ... but never moved
    assert graph['Domain Controller 2'].extra_data == {'my': 'edit'}               # non-auto node untouched
    assert 'H2-renamed' not in graph and len(nodes(case)) == 6


def test_graphs_from_before_auto_keys_are_not_duplicated(admin, db, case):
    """A graph built by the old generator has no origin / auto_key anywhere."""
    generate(admin, case)
    all_nodes, all_edges = nodes(case), edges(case)   # (each helper expires the session: load first, then edit)
    for node in all_nodes:
        node.extra_data = {k: v for k, v in node.extra_data.items() if k not in ('origin', 'auto_key')}
    for edge in all_edges:
        edge.extra_data = {}
    db.session.commit()
    n_nodes, n_edges = len(nodes(case)), len(edges(case))
    resp = generate(admin, case, mode='merge')
    assert resp.status_code == 200 and resp.get_json()['created'] == {'nodes': 0, 'edges': 0}
    assert len(nodes(case)) == n_nodes and len(edges(case)) == n_edges
    assert all('origin' not in (n.extra_data or {}) for n in nodes(case)), 'legacy nodes stay untouched'


def test_merge_does_not_delete_nodes_whose_source_row_is_gone(admin, db, case):
    from app.models import MalwareTool
    generate(admin, case)
    MalwareTool.query.filter_by(incident_id=case.id).delete()
    db.session.commit()
    generate(admin, case)
    assert 'beacon.exe' in by_label(case)


# ── replace ───────────────────────────────────────────────────────────────

def test_replace_requires_confirm_and_changes_nothing_without_it(admin, db, users, case):
    from app.models import AttackGraphNode
    generate(admin, case)
    db.session.add(AttackGraphNode(incident_id=case.id, node_type='attacker', label='manual',
                                   created_by=users['Administrator'].id))
    db.session.commit()
    before = {n.id for n in nodes(case)}
    for body in ({'mode': 'replace'}, {'mode': 'replace', 'confirm': False}, {'mode': 'replace', 'confirm': 'true'}):
        resp = generate(admin, case, **body)
        assert resp.status_code == 400 and resp.get_json()['error'] == 'confirmation_required'
    assert {n.id for n in nodes(case)} == before


def test_replace_with_confirm_rebuilds_from_scratch(admin, db, users, case):
    from app.models import AttackGraphNode
    generate(admin, case)
    db.session.add(AttackGraphNode(incident_id=case.id, node_type='attacker', label='manual',
                                   created_by=users['Administrator'].id))
    by_label(case)['H1'].position_x = 99999.0
    db.session.commit()
    resp = generate(admin, case, mode='replace', confirm=True)
    assert resp.status_code == 201 and resp.get_json()['mode'] == 'replace'
    graph = by_label(case)
    assert 'manual' not in graph and len(graph) == 6
    assert graph['H1'].position_x == 300


def test_invalid_mode_is_400(admin, case):
    assert generate(admin, case, mode='nuke').status_code == 400
    assert admin.post(f'{API}/incidents/{case.id}/attack-graph/auto-generate', json=['x']).status_code == 400


def test_empty_body_is_merge(admin, case):
    resp = admin.post(f'{API}/incidents/{case.id}/attack-graph/auto-generate')
    assert resp.status_code == 201 and resp.get_json()['mode'] == 'merge'


# ── permissions ───────────────────────────────────────────────────────────

def test_viewer_cannot_generate_and_other_org_is_404(app, users, auth, case, make_incident, org_b):
    viewer_case = case
    assert auth(users['Viewer']).post(f'{API}/incidents/{viewer_case.id}/attack-graph/auto-generate',
                                      json={}).status_code == 403
    foreign = make_incident(org=org_b)
    assert generate(auth(users['Administrator']), foreign).status_code == 404


def test_timeline_events_after_generation_reuse_the_keyed_host_node(admin, db, users, case):
    """process_event_for_graph (new event on a host) finds the auto host node by FK."""
    from app.models import TimelineEvent
    generate(admin, case)
    before = len(nodes(case))
    resp = admin.post(f'{API}/incidents/{case.id}/timeline', json={
        'timestamp': (T0 + timedelta(hours=5)).isoformat(), 'activity': 'x', 'host_id': str(case.hosts['H1'].id),
        'mitre_mappings': [{'tactic': 'impact', 'technique': 'T1486'}]})
    assert resp.status_code == 201, resp.get_json()
    assert len(nodes(case)) == before
    assert by_label(case)['H1'].is_objective is True
