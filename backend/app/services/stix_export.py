"""STIX 2.1 bundle builder for an incident (surface-dfir §3.8; never-cut security fix).

The bundle is built as plain dicts (no STIX library is installed and none is
added) and serialised once with ``json.dumps``; no JSON or pattern text is ever
assembled by string concatenation of user data. The only place where user data
enters a STIX *pattern* is ``pattern_eq`` / ``stix_escape``: the value is
escaped for a STIX string literal (``\\`` then ``'``), control characters are
rejected, and the object path is taken from a fixed allowlist, so a value such
as ``x' OR [file:name = 'y`` cannot terminate the literal or add a comparison.

TLP: every SDO / SRO carries ``object_marking_refs`` for the incident's TLP,
and the matching ``marking-definition`` objects are part of the bundle.
white / green / amber / red use the fixed TLP 1.0 ids from the STIX 2.1
specification. ``amber_strict`` (TLP 2.0) has no id in STIX 2.1 core, so it
is marked with the (more restrictive than needed, never less) TLP:AMBER
definition plus an ``amber_strict`` statement marking whose id is derived
deterministically here.
"""
from __future__ import annotations

import ipaddress
import json
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

STIX_NAMESPACE = uuid.UUID('6b3c9c52-4c89-4f0b-9c5c-5d2d64a3a1f1')  # sheetstorm
MAX_PATTERN_VALUE = 4096
_TECHNIQUE = re.compile(r'^T\d{4}(\.\d{3})?$')
_CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# STIX 2.1 spec, section 7.2.1.4 (TLP 1.0).
TLP_MARKINGS = {
    'white': ('marking-definition--613f2e26-407d-48c7-9eca-b8e91df99dc9', 'white'),
    'green': ('marking-definition--34098fce-860f-48ae-8e50-ebd3cc5e41da', 'green'),
    'amber': ('marking-definition--f88d31f6-486f-44da-b317-01333bde0b82', 'amber'),
    'red': ('marking-definition--5e57c739-391a-4eb3-b6be-7d15ca92d5ed', 'red'),
}
AMBER_STRICT_MARKING_ID = f"marking-definition--{uuid.uuid5(STIX_NAMESPACE, 'tlp:amber+strict')}"
TLP_CREATED = '2017-01-20T00:00:00.000Z'


# ── Primitives ──────────────────────────────────────────────────────────────

def stix_ts(value=None) -> str:
    """STIX timestamp: UTC, millisecond precision, ``Z``."""
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.strftime('%Y-%m-%dT%H:%M:%S.') + f'{value.microsecond // 1000:03d}Z'


def stix_escape(value) -> str:
    """Escape ``value`` for use inside a single-quoted STIX pattern string."""
    text = str(value)
    if _CONTROL.search(text):
        text = _CONTROL.sub('', text)
    return text.replace('\\', '\\\\').replace("'", "\\'")


# Object paths a pattern may use; the path is never client-controlled.
_PATTERN_PATHS = frozenset({
    'ipv4-addr:value', 'ipv6-addr:value', 'domain-name:value', 'url:value', 'file:name', 'process:name',
    'windows-registry-key:key', 'x-sheetstorm-artifact:value', 'email-addr:value',
})


def pattern_eq(path: str, value) -> str:
    """``[path = 'escaped value']`` for an allowlisted ``path``."""
    if path not in _PATTERN_PATHS:
        raise ValueError(f'object path not allowed in a pattern: {path!r}')
    return f"[{path} = '{stix_escape(str(value)[:MAX_PATTERN_VALUE])}']"


def classify_network_value(value: str) -> str:
    """Pattern path for a network IOC value (IPv4, IPv6, URL or domain name)."""
    text = (value or '').strip()
    try:
        ip = ipaddress.ip_address(text)
        return 'ipv6-addr:value' if ip.version == 6 else 'ipv4-addr:value'
    except ValueError:
        pass
    if re.match(r'^[a-z][a-z0-9+.-]*://', text, re.IGNORECASE):
        return 'url:value'
    return 'domain-name:value'


def host_artifact_path(artifact_type: str) -> str:
    if artifact_type == 'file':
        return 'file:name'
    if artifact_type == 'process':
        return 'process:name'
    if artifact_type in ('registry', 'asep'):
        return 'windows-registry-key:key'
    return 'x-sheetstorm-artifact:value'


def marking_definitions(tlp: str) -> list:
    """(marking ids to reference, marking-definition objects to include)."""
    if tlp == 'amber_strict':
        amber_id, _ = TLP_MARKINGS['amber']
        refs = [amber_id, AMBER_STRICT_MARKING_ID]
        objects = [_tlp_definition('amber'), {
            'type': 'marking-definition', 'spec_version': '2.1', 'id': AMBER_STRICT_MARKING_ID,
            'created': TLP_CREATED, 'name': 'TLP:AMBER+STRICT',
            'definition_type': 'statement',
            'definition': {'statement': 'TLP:AMBER+STRICT (TLP 2.0): limited to the recipient organization only.'},
        }]
        return refs, objects
    level = tlp if tlp in TLP_MARKINGS else 'amber'  # unknown -> restrictive default
    return [TLP_MARKINGS[level][0]], [_tlp_definition(level)]


def _tlp_definition(level: str) -> dict:
    marking_id, name = TLP_MARKINGS[level]
    return {'type': 'marking-definition', 'spec_version': '2.1', 'id': marking_id, 'created': TLP_CREATED,
            'name': f'TLP:{name.upper()}', 'definition_type': 'tlp', 'definition': {'tlp': name}}


def _sid(kind: str, uid) -> str:
    return f'{kind}--{uid}'


def _det_id(kind: str, key: str) -> str:
    return f'{kind}--{uuid.uuid5(STIX_NAMESPACE, key)}'


# ── Bundle ──────────────────────────────────────────────────────────────────

def build_bundle(incident, organization_id) -> dict:
    """STIX 2.1 bundle for ``incident`` (caller has checked access/permissions)."""
    now = stix_ts()
    marking_refs, marking_objects = marking_definitions(incident.tlp)

    def sdo(kind: str, obj_id: str, **props) -> dict:
        base = {'type': kind, 'spec_version': '2.1', 'id': obj_id, 'created': now, 'modified': now,
                'object_marking_refs': list(marking_refs)}
        base.update(props)
        return base

    identity_id = _det_id('identity', f'sheetstorm:{organization_id}')
    objects = list(marking_objects)
    objects.append(sdo('identity', identity_id, name='SheetStorm Organization', identity_class='organization'))

    report_id = _sid('report', incident.id)
    report = sdo(
        'report', report_id,
        name=incident.title, description=incident.description or '', report_types=['incident'],
        published=stix_ts(incident.created_at) if incident.created_at else now,
        created_by_ref=identity_id,
        labels=[incident.severity or 'medium', incident.status or 'open'],
        object_refs=[],
        x_sheetstorm_incident={
            'phase': incident.phase, 'phase_name': incident.phase_name,
            'classification': incident.classification, 'severity': incident.severity,
            'status': incident.status, 'tlp': incident.tlp,
        })
    objects.append(report)
    refs = []

    for ioc in incident.network_indicators.all():
        ind_id = _sid('indicator', ioc.id)
        objects.append(sdo(
            'indicator', ind_id, name=ioc.dns_ip, description=ioc.description or f'Network IOC: {ioc.dns_ip}',
            pattern=pattern_eq(classify_network_value(ioc.dns_ip), ioc.dns_ip), pattern_type='stix',
            valid_from=stix_ts(ioc.timestamp) if ioc.timestamp else now,
            indicator_types=['malicious-activity'] if ioc.is_malicious else ['anomalous-activity'],
            labels=[ioc.protocol or 'unknown', ioc.direction or 'unknown'],
            created_by_ref=identity_id))
        refs.append(ind_id)

    for ioc in incident.host_indicators.all():
        ind_id = _sid('indicator', ioc.id)
        objects.append(sdo(
            'indicator', ind_id, name=f'{ioc.artifact_type}: {ioc.artifact_value[:80]}',
            description=ioc.notes or f'Host IOC ({ioc.artifact_type})',
            pattern=pattern_eq(host_artifact_path(ioc.artifact_type), ioc.artifact_value), pattern_type='stix',
            valid_from=stix_ts(ioc.datetime) if ioc.datetime else now,
            indicator_types=['malicious-activity'] if ioc.is_malicious else ['anomalous-activity'],
            labels=[ioc.artifact_type], created_by_ref=identity_id))
        refs.append(ind_id)

    infra_by_host = {}
    for host in incident.compromised_hosts.all():
        infra_id = _sid('infrastructure', host.id)
        infra_by_host[host.id] = infra_id
        objects.append(sdo(
            'infrastructure', infra_id, name=host.hostname,
            description=f"IP: {host.ip_address or 'N/A'} | OS: {host.os_version or 'N/A'}",
            infrastructure_types=['workstation'] if host.system_type == 'workstation' else ['server'],
            created_by_ref=identity_id))
        refs.append(infra_id)

    relationships = []
    for m in incident.malware_tools.all():
        malware_id = _sid('malware', m.id)
        objects.append(sdo(
            'malware', malware_id, name=m.file_name, description=m.description or f'Malware: {m.file_name}',
            malware_types=['tool'] if m.is_tool else ['trojan'], is_family=bool(m.malware_family),
            hashes={k: v for k, v in {'MD5': m.md5, 'SHA-256': m.sha256, 'SHA-512': m.sha512}.items() if v},
            created_by_ref=identity_id))
        refs.append(malware_id)
        if m.host_id in infra_by_host:
            relationships.append(sdo(
                'relationship', _det_id('relationship', f'targets:{m.id}:{m.host_id}'),
                relationship_type='targets', source_ref=malware_id, target_ref=infra_by_host[m.host_id],
                created_by_ref=identity_id))

    seen = set()
    for event in incident.timeline_events.all():
        mappings = event.mitre_mappings or []
        if not mappings and event.mitre_technique:
            mappings = [{'tactic': event.mitre_tactic or '', 'technique': event.mitre_technique}]
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            tech = str(mapping.get('technique') or '').strip()[:20]
            tactic = str(mapping.get('tactic') or '').strip()[:100]
            if not tech or tech in seen:
                continue
            seen.add(tech)
            ap_id = _det_id('attack-pattern', tech)
            props = {'name': f'{tactic}: {tech}' if tactic else tech, 'created_by_ref': identity_id}
            if _TECHNIQUE.match(tech):
                props['external_references'] = [{
                    'source_name': 'mitre-attack', 'external_id': tech,
                    'url': 'https://attack.mitre.org/techniques/' + quote(tech.replace('.', '/'), safe='/')}]
            objects.append(sdo('attack-pattern', ap_id, **props))
            refs.append(ap_id)

    objects.extend(relationships)
    refs.extend(r['id'] for r in relationships)
    report['object_refs'] = refs or [identity_id]  # a STIX report needs at least one ref
    return {'type': 'bundle', 'id': f'bundle--{uuid.uuid4()}', 'objects': objects}


def dumps(bundle: dict) -> str:
    return json.dumps(bundle, ensure_ascii=False, separators=(',', ':'))
