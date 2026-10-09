"""W3-DFIR-C: STIX 2.1 export (surface-dfir §3.8) incl. injection attempts.

Never-cut security fix: values are escaped for STIX string literals and the
bundle is serialised from an object model, so an indicator value can never
break out of its pattern; TLP marking-definitions travel with the bundle.
"""
import json
import re
import uuid
from datetime import datetime, timezone

import pytest

from app.services import stix_export

API = '/api/v1'
T0 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)

# Matches exactly one quoted STIX literal with escapes, as a pattern comparison.
_LITERAL = r"'(?:[^'\\]|\\.)*'"
SINGLE_COMPARISON = re.compile(rf"^\[[a-z0-9-]+:[a-z_]+ = {_LITERAL}\]$")


def stix_for(client, inc):
    resp = client.get(f'{API}/incidents/{inc.id}/export/stix')
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    return resp, resp.get_json()


@pytest.fixture
def admin(users, auth):
    return auth(users['Administrator'])


def add_network(db, inc, user, *values):
    from app.models import NetworkIndicator
    for v in values:
        db.session.add(NetworkIndicator(incident_id=inc.id, dns_ip=v, created_by=user.id))
    db.session.commit()


# ── escaping / injection ─────────────────────────────────────────────────

@pytest.mark.parametrize('value,escaped', [
    ("o'brien.example", "o\\'brien.example"),
    ('back\\slash.example', 'back\\\\slash.example'),
    ("x\\' OR 1=1 --", "x\\\\\\' OR 1=1 --"),
])
def test_stix_escape(value, escaped):
    assert stix_export.stix_escape(value) == escaped


def test_pattern_cannot_be_broken_out_of(app, db, admin, users, make_incident):
    inc = make_incident()
    attacks = [
        "evil.example' OR [file:name = 'x",          # close literal, add a comparison
        "a' AND [process:name = 'cmd.exe'] OR [domain-name:value = 'b",
        "trailing\\",                                  # trailing backslash must not eat the closing quote
        "\\' ] OR [ipv4-addr:value = '1.1.1.1",
        "x' FOLLOWEDBY [url:value = 'http://c2'",
    ]
    add_network(db, inc, users['Administrator'], *attacks)
    from app.models import HostBasedIndicator
    for artifact_type, value in (('file', "C:\\evil' OR [file:name = 'y"), ('registry', "HKLM\\Run' ]--"),
                                 ('service', "svc' OR 1=1")):
        db.session.add(HostBasedIndicator(incident_id=inc.id, artifact_type=artifact_type, artifact_value=value,
                                          created_by=users['Administrator'].id))
    db.session.commit()

    resp, bundle = stix_for(admin, inc)
    indicators = [o for o in bundle['objects'] if o['type'] == 'indicator']
    assert len(indicators) == len(attacks) + 3
    for indicator in indicators:
        # exactly one comparison; the literal ends at the final quote
        assert SINGLE_COMPARISON.match(indicator['pattern']), indicator['pattern']
        assert indicator['pattern_type'] == 'stix'
    # Round-trip: unescaping the literal yields the original value verbatim.
    by_name = {i['name']: i['pattern'] for i in indicators}
    for value in attacks:
        literal = by_name[value][by_name[value].index(" = '") + 4:-2]
        assert re.sub(r'\\(.)', r'\1', literal) == value


def test_unsafe_object_paths_are_refused():
    with pytest.raises(ValueError):
        stix_export.pattern_eq("file:name = 'a'] OR [file:name", 'x')
    assert stix_export.pattern_eq('file:name', "a'b") == "[file:name = 'a\\'b']"


def test_control_characters_are_stripped_from_patterns():
    assert stix_export.stix_escape('a\x00b\x1fc') == 'abc'


def test_hostile_text_stays_data_in_valid_json(app, db, admin, users, make_incident):
    """Titles / descriptions with quotes, braces and unicode survive as JSON strings."""
    title = 'Incident "quoted" </script>{"type":"bundle"} \u2028 \u00e9'
    inc = make_incident(title=title, description="line1\nline2 ' \\")
    resp, bundle = stix_for(admin, inc)
    assert json.loads(resp.get_data(as_text=True)) == bundle
    report = next(o for o in bundle['objects'] if o['type'] == 'report')
    assert report['name'] == title and report['description'] == "line1\nline2 ' \\"
    assert bundle['type'] == 'bundle' and bundle['id'].startswith('bundle--')


def test_indicator_pattern_type_follows_value(app, db, admin, users, make_incident):
    inc = make_incident()
    add_network(db, inc, users['Administrator'], '203.0.113.9', '2001:db8::1', 'http://x.example/p', 'host.example',
                '999.1.1.1')
    _, bundle = stix_for(admin, inc)
    patterns = {o['name']: o['pattern'] for o in bundle['objects'] if o['type'] == 'indicator'}
    assert patterns['203.0.113.9'] == "[ipv4-addr:value = '203.0.113.9']"
    assert patterns['2001:db8::1'] == "[ipv6-addr:value = '2001:db8::1']"
    assert patterns['http://x.example/p'] == "[url:value = 'http://x.example/p']"
    assert patterns['host.example'] == "[domain-name:value = 'host.example']"
    assert patterns['999.1.1.1'].startswith('[domain-name:value')  # not a valid IPv4


def test_attack_pattern_url_is_built_only_for_real_technique_ids(app, db, admin, users, make_incident):
    from app.models import TimelineEvent
    inc = make_incident()
    uid = users['Administrator'].id
    db.session.add_all([
        TimelineEvent(incident_id=inc.id, timestamp=T0, activity='a', created_by=uid,
                      mitre_mappings=[{'tactic': 'execution', 'technique': 'T1059.001'}]),
        TimelineEvent(incident_id=inc.id, timestamp=T0, activity='b', created_by=uid,
                      mitre_mappings=[{'tactic': 'x', 'technique': '../../evil?x=1'}]),
    ])
    db.session.commit()
    _, bundle = stix_for(admin, inc)
    aps = [o for o in bundle['objects'] if o['type'] == 'attack-pattern']
    good = next(o for o in aps if o['name'].endswith('T1059.001'))
    assert good['external_references'][0]['url'] == 'https://attack.mitre.org/techniques/T1059/001'
    bad = next(o for o in aps if 'evil' in o['name'])
    assert 'external_references' not in bad


# ── TLP markings ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('tlp,marking_id', [
    ('white', 'marking-definition--613f2e26-407d-48c7-9eca-b8e91df99dc9'),
    ('green', 'marking-definition--34098fce-860f-48ae-8e50-ebd3cc5e41da'),
    ('amber', 'marking-definition--f88d31f6-486f-44da-b317-01333bde0b82'),
    ('red', 'marking-definition--5e57c739-391a-4eb3-b6be-7d15ca92d5ed'),
])
def test_tlp_marking_present_for_each_level(app, db, admin, users, make_incident, tlp, marking_id):
    inc = make_incident(tlp=tlp)
    add_network(db, inc, users['Administrator'], 'tlp.example')
    resp, bundle = stix_for(admin, inc)
    definitions = [o for o in bundle['objects'] if o['type'] == 'marking-definition']
    assert [d['id'] for d in definitions] == [marking_id]
    assert definitions[0]['definition'] == {'tlp': tlp} and definitions[0]['definition_type'] == 'tlp'
    marked = [o for o in bundle['objects'] if o['type'] not in ('marking-definition',)]
    assert marked and all(o['object_marking_refs'] == [marking_id] for o in marked)
    assert f'TLP_{tlp.upper()}' in resp.headers['Content-Disposition']


def test_amber_strict_is_at_least_amber_plus_a_strict_statement(app, db, admin, users, make_incident):
    inc = make_incident(tlp='amber_strict')
    _, bundle = stix_for(admin, inc)
    ids = {o['id']: o for o in bundle['objects'] if o['type'] == 'marking-definition'}
    amber = stix_export.TLP_MARKINGS['amber'][0]
    assert amber in ids and stix_export.AMBER_STRICT_MARKING_ID in ids
    assert ids[stix_export.AMBER_STRICT_MARKING_ID]['definition_type'] == 'statement'
    report = next(o for o in bundle['objects'] if o['type'] == 'report')
    assert report['object_marking_refs'] == [amber, stix_export.AMBER_STRICT_MARKING_ID]
    assert report['x_sheetstorm_incident']['tlp'] == 'amber_strict'


def test_bundle_shape_relationships_and_headers(app, db, admin, users, make_incident):
    from app.models import CompromisedHost, MalwareTool
    inc = make_incident()
    uid = users['Administrator'].id
    host = CompromisedHost(incident_id=inc.id, hostname='srv1', system_type='server', created_by=uid)
    db.session.add(host)
    db.session.flush()
    db.session.add(MalwareTool(incident_id=inc.id, file_name='m.exe', sha256='c' * 64, host_id=host.id,
                               created_by=uid))
    db.session.commit()
    resp, bundle = stix_for(admin, inc)
    assert resp.mimetype == 'application/stix+json'
    assert resp.headers['Content-Type'].endswith('version=2.1')
    assert resp.headers['Content-Disposition'].startswith('attachment; filename="incident-')
    types = [o['type'] for o in bundle['objects']]
    assert {'identity', 'report', 'malware', 'infrastructure', 'relationship'} <= set(types)
    ids = {o['id'] for o in bundle['objects']}
    report = next(o for o in bundle['objects'] if o['type'] == 'report')
    assert set(report['object_refs']) <= ids and report['object_refs']
    rel = next(o for o in bundle['objects'] if o['type'] == 'relationship')
    assert rel['relationship_type'] == 'targets' and {rel['source_ref'], rel['target_ref']} <= ids
    for obj in bundle['objects']:
        assert re.fullmatch(r'[a-z0-9-]+--[0-9a-f-]{36}', obj['id'])
        if obj['type'] != 'marking-definition':
            assert re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z', obj['created'])


# ── access / audit ───────────────────────────────────────────────────────

def test_inaccessible_incident_is_forbidden_and_cross_org_not_found(app, users, auth, make_incident, org_b):
    inc = make_incident(tlp='amber')
    # Viewer: no incidents:export (and no visibility of an unassigned amber incident)
    assert auth(users['Viewer']).get(f'{API}/incidents/{inc.id}/export/stix').status_code == 403
    # Analyst may see the incident but lacks incidents:export (C24)
    assert auth(users['Analyst']).get(f'{API}/incidents/{inc.id}/export/stix').status_code == 403
    foreign = make_incident(org=org_b)
    assert auth(users['Administrator']).get(f'{API}/incidents/{foreign.id}/export/stix').status_code == 404


def test_viewer_with_white_incident_still_cannot_export(app, users, auth, make_incident):
    white = make_incident(tlp='white', assign=[users['Viewer']])
    viewer = auth(users['Viewer'])
    assert viewer.get(f'{API}/incidents/{white.id}').status_code == 200
    resp = viewer.get(f'{API}/incidents/{white.id}/export/stix')
    assert resp.status_code == 403 and 'incidents:export' in resp.get_json()['message']


def test_stix_export_is_audited(app, db, admin, make_incident):
    from app.models import AuditLog
    inc = make_incident(tlp='green')
    stix_for(admin, inc)
    db.session.expire_all()
    row = (AuditLog.query.filter_by(event_type='data_access', action='export_stix', incident_id=inc.id)
           .order_by(AuditLog.created_at.desc()).first())
    assert row is not None and row.details['tlp'] == 'green' and row.details['objects'] >= 3
