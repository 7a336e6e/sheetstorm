"""Server-side CSV exports of incident entities (surface-dfir §3.8; C23/C24).

One registry maps ``entity`` to its read permission, an explicit column
allowlist (never ``to_dict()``), and the same sort / filter / search
declarations as the entity's list endpoint, so "export what I filtered" yields
exactly the rows the table shows. Everything is streamed:

* every cell goes through ``utils.csv_safe.csv_safe`` (CWE-1236);
* datetimes are UTC ISO 8601 with a ``Z`` suffix;
* accounts never expose a password, only ``Has Password``;
* ``defang=true`` defangs IOC value columns (``evil[.]com``, ``hxxp://``).

The route lives in ``api/v1/endpoints/exports.py``.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Iterator, Optional

from app.utils.csv_safe import csv_safe

BOM = '﻿'
CHUNK = 500
MAX_EXPORT_ROWS = 100_000


def iso_utc(value) -> str:
    """UTC ISO 8601 with a ``Z`` suffix (naive values are taken as UTC)."""
    if value is None:
        return ''
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return str(value)


def _bool(value) -> str:
    return '' if value is None else ('true' if value else 'false')


_IPV4 = re.compile(r'^\d{1,3}(\.\d{1,3}){3}$')


def defang_ioc(value, *, domains: bool = True) -> str:
    """Defang an indicator value for sharing (type is auto-detected: IPv4,
    URL, e-mail, bare domain). Anything else (hashes, paths, registry keys,
    free text) is returned verbatim; ``domains=False`` also leaves bare
    domain-shaped strings alone (file names such as ``evil.exe``)."""
    from app.api.v1.endpoints.defang import defang_value
    if value is None or value == '':
        return ''
    text = str(value)
    if _IPV4.match(text):
        kind = 'ip'
    elif re.match(r'^[a-z][a-z0-9+.-]*://', text, re.IGNORECASE):
        kind = 'url'
    elif '@' in text and ' ' not in text:
        kind = 'email'
    elif domains and re.match(r'^[A-Za-z0-9._-]+\.[A-Za-z]{2,}$', text):
        kind = 'domain'
    else:
        return text
    return defang_value(text, kind)


@dataclass(frozen=True)
class ExportEntity:
    key: str
    label: str
    permission: str
    columns: tuple          # ((header, getter(row, ctx) -> cell), ...)
    default_sort: str
    sortable: Callable[[], dict]
    filters: Callable[[], dict]
    search_columns: Callable[[], tuple]
    model: Callable[[], Any]
    scope: Callable[[Any, Any], Any] = field(default=lambda query, incident: query)
    refine: Optional[Callable[[Any, Any], Any]] = None   # (query, request.args) -> query
    # headers whose cells hold indicator values (defanged on request)
    ioc_columns: tuple = ()
    defang_domains: bool = True
    # per-chunk preparation: (rows, incident, user) -> ctx dict handed to getters
    prepare: Optional[Callable[[list, Any, Any], dict]] = None


# ── Getters ─────────────────────────────────────────────────────────────────

def _mitre(e, ctx):
    pairs = []
    for m in (e.mitre_mappings or []):
        if isinstance(m, dict) and m.get('technique'):
            pairs.append(f"{m.get('tactic') or ''}:{m['technique']}".lstrip(':'))
    if not pairs and e.mitre_technique:
        pairs.append(f"{e.mitre_tactic or ''}:{e.mitre_technique}".lstrip(':'))
    return '; '.join(pairs)


def _dwell(e, ctx):
    if e.detection_time is None or e.timestamp is None:
        return ''
    return int((e.detection_time - e.timestamp).total_seconds())


def _acq(flag):
    def get(h, ctx):
        value = (h.acquisition_status or {}).get(flag)
        return _bool(value) if isinstance(value, bool) else ''
    return get


def _acq_at(h, ctx):
    return iso_utc(_parse_iso((h.acquisition_status or {}).get('acquired_at')))


def _parse_iso(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def _prepare_tasks(rows, incident, user):
    from app.models import User
    from app.services.evidence_refs import normalize_refs, resolve_refs

    assignee_ids = {r.assignee_id for r in rows if r.assignee_id}
    names = {}
    if assignee_ids:
        names = {u.id: u.name for u in User.query.filter(
            User.id.in_(assignee_ids), User.organization_id == incident.organization_id).all()}
    refs = [ref for r in rows for ref in (r.evidence_refs or [])]
    resolved = {}
    if refs:
        resolved = {(x['evidence_type'], x['evidence_id']): x
                    for x in resolve_refs(incident.id, refs, user=user)}
    return {'assignees': names, 'resolved': resolved, 'normalize': normalize_refs}


def _task_evidence(t, ctx):
    labels = []
    for ref in ctx['normalize'](t.evidence_refs or []):
        item = ctx['resolved'].get((ref['evidence_type'], ref['evidence_id']))
        if item is None or item.get('missing'):
            labels.append(f"{ref['evidence_type']}: [deleted]")
        elif item.get('restricted'):
            labels.append(f"{ref['evidence_type']}: [restricted]")
        else:
            labels.append(f"{ref['evidence_type']}: {item.get('label') or ref['evidence_id']}")
    return '; '.join(labels)


# ── Entity registry (built lazily: models and endpoint modules import app) ──

def _timeline_refine(query, args):
    from app.models import TimelineEvent
    from sqlalchemy import or_
    tactic = args.get('mitre_tactic')
    if not tactic:
        return query
    if len(tactic) > 64 or not re.fullmatch(r'[a-z0-9-]+', tactic):
        from app.utils.pagination import ListArgsError
        raise ListArgsError('invalid mitre_tactic value', 'invalid_filter')
    return query.filter(or_(TimelineEvent.mitre_tactic == tactic,
                            TimelineEvent.mitre_mappings.contains([{'tactic': tactic}])))


def _hosts_refine(query, args):
    from app.api.v1.endpoints.compromised import _acquisition_filter
    if args.get('acquisition'):
        query = _acquisition_filter(query, args['acquisition'])
    return query


def _tasks_refine(query, args):
    from app.api.v1.endpoints.tasks import _lead_outcome_filter
    if args.get('lead_outcome'):
        query = _lead_outcome_filter(query, args['lead_outcome'])
    return query


def _registry() -> dict:
    from app.models import (CompromisedAccount, CompromisedHost, HostBasedIndicator, MalwareTool,
                            NetworkIndicator, Task, TimelineEvent)

    def timeline_sortable():
        from app.api.v1.endpoints.timeline import TIMELINE_SORTABLE
        return TIMELINE_SORTABLE

    def timeline_filters():
        from app.api.v1.endpoints.timeline import TIMELINE_FILTERS
        return TIMELINE_FILTERS

    def host_sortable():
        from app.api.v1.endpoints.compromised import HOST_SORTABLE
        return HOST_SORTABLE

    def host_filters():
        from app.api.v1.endpoints.compromised import HOST_FILTERS
        return HOST_FILTERS

    def account_sortable():
        from app.api.v1.endpoints.compromised import ACCOUNT_SORTABLE
        return ACCOUNT_SORTABLE

    def account_filters():
        from app.api.v1.endpoints.compromised import ACCOUNT_FILTERS
        return ACCOUNT_FILTERS

    def task_sortable():
        from app.api.v1.endpoints.tasks import TASK_SORTABLE
        return TASK_SORTABLE

    def task_filters():
        from app.api.v1.endpoints.tasks import TASK_FILTERS
        return TASK_FILTERS

    def network_sortable():
        from app.api.v1.endpoints.iocs import NETWORK_IOC_SORTABLE
        return NETWORK_IOC_SORTABLE

    def host_ioc_sortable():
        from app.api.v1.endpoints.iocs import HOST_IOC_SORTABLE
        return HOST_IOC_SORTABLE

    def malware_sortable():
        from app.api.v1.endpoints.iocs import MALWARE_SORTABLE
        return MALWARE_SORTABLE

    entities = [
        ExportEntity(
            key='timeline', label='Timeline', permission='timeline:read',
            model=lambda: TimelineEvent, default_sort='timestamp',
            sortable=timeline_sortable, filters=timeline_filters,
            search_columns=lambda: (TimelineEvent.activity, TimelineEvent.hostname),
            refine=_timeline_refine,
            columns=(
                ('Timestamp (UTC)', lambda e, c: iso_utc(e.timestamp)),
                ('Detection Time (UTC)', lambda e, c: iso_utc(e.detection_time)),
                ('Dwell (seconds)', _dwell),
                ('Hostname', lambda e, c: e.hostname),
                ('Activity', lambda e, c: e.activity),
                ('Source', lambda e, c: e.source),
                ('Phase', lambda e, c: e.phase),
                ('MITRE', _mitre),
                ('Confidence', lambda e, c: e.confidence_level),
                ('Key Event', lambda e, c: _bool(e.is_key_event)),
                ('IOC', lambda e, c: _bool(e.is_ioc)),
                ('Kill Chain Phase', lambda e, c: e.kill_chain_phase),
            )),
        ExportEntity(
            key='hosts', label='Hosts', permission='hosts:read',
            model=lambda: CompromisedHost, default_sort='-first_seen',
            sortable=host_sortable, filters=host_filters,
            search_columns=lambda: (CompromisedHost.hostname, CompromisedHost.ip_address,
                                    CompromisedHost.system_type, CompromisedHost.notes),
            refine=_hosts_refine,
            columns=(
                ('Hostname', lambda h, c: h.hostname),
                ('IP Address', lambda h, c: str(h.ip_address) if h.ip_address else ''),
                ('MAC Address', lambda h, c: h.mac_address),
                ('System Type', lambda h, c: h.system_type),
                ('OS Version', lambda h, c: h.os_version),
                ('First Seen (UTC)', lambda h, c: iso_utc(h.first_seen)),
                ('Last Seen (UTC)', lambda h, c: iso_utc(h.last_seen)),
                ('Containment Status', lambda h, c: h.containment_status),
                ('Triage Status', lambda h, c: h.triage_status),
                ('Disk Imaged', _acq('disk_imaged')),
                ('Memory Captured', _acq('memory_captured')),
                ('Logs Collected', _acq('logs_collected')),
                ('Forensically Sound', _acq('forensically_sound')),
                ('Acquired At (UTC)', _acq_at),
                ('Evidence of Compromise', lambda h, c: h.evidence),
                ('Notes', lambda h, c: h.notes),
            )),
        ExportEntity(
            key='accounts', label='Compromised accounts', permission='accounts:read',
            model=lambda: CompromisedAccount, default_sort='-datetime_seen',
            sortable=account_sortable, filters=account_filters,
            search_columns=lambda: (CompromisedAccount.account_name, CompromisedAccount.domain,
                                    CompromisedAccount.host_system, CompromisedAccount.notes),
            columns=(
                ('Account Name', lambda a, c: a.account_name),
                ('Domain', lambda a, c: a.domain),
                ('SID', lambda a, c: a.sid),
                ('Account Type', lambda a, c: a.account_type),
                ('Privileged', lambda a, c: _bool(a.is_privileged)),
                ('Status', lambda a, c: a.status),
                ('Host', lambda a, c: a.host_system),
                ('First Seen (UTC)', lambda a, c: iso_utc(a.datetime_seen)),
                ('Has Password', lambda a, c: _bool(bool(a.password_encrypted))),
                ('Notes', lambda a, c: a.notes),
            )),
        ExportEntity(
            key='network-iocs', label='Network IOCs', permission='network_iocs:read',
            model=lambda: NetworkIndicator, default_sort='-timestamp',
            sortable=network_sortable,
            filters=lambda: {
                'protocol': (NetworkIndicator.protocol, 'eq'),
                'direction': (NetworkIndicator.direction, 'eq'),
                'host_id': (NetworkIndicator.host_id, 'uuid'),
            },
            search_columns=lambda: (NetworkIndicator.dns_ip, NetworkIndicator.source_host,
                                    NetworkIndicator.destination_host, NetworkIndicator.description),
            ioc_columns=('DNS / IP',),
            columns=(
                ('Timestamp (UTC)', lambda i, c: iso_utc(i.timestamp)),
                ('DNS / IP', lambda i, c: i.dns_ip),
                ('Protocol', lambda i, c: i.protocol),
                ('Port', lambda i, c: i.port),
                ('Direction', lambda i, c: i.direction),
                ('Source Host', lambda i, c: i.source_host),
                ('Destination Host', lambda i, c: i.destination_host),
                ('Malicious', lambda i, c: _bool(i.is_malicious)),
                ('Threat Intel Source', lambda i, c: i.threat_intel_source),
                ('Description', lambda i, c: i.description),
            )),
        ExportEntity(
            key='host-iocs', label='Host IOCs', permission='host_iocs:read',
            model=lambda: HostBasedIndicator, default_sort='-datetime',
            sortable=host_ioc_sortable,
            filters=lambda: {
                'artifact_type': (HostBasedIndicator.artifact_type, 'eq'),
                'host_id': (HostBasedIndicator.host_id, 'uuid'),
                'host': (HostBasedIndicator.host, 'ilike'),
                'from_timeline': (HostBasedIndicator.timeline_event_id.isnot(None), 'flag'),
            },
            search_columns=lambda: (HostBasedIndicator.artifact_value, HostBasedIndicator.host,
                                    HostBasedIndicator.notes),
            ioc_columns=('Artifact Value',), defang_domains=False,
            columns=(
                ('Date / Time (UTC)', lambda i, c: iso_utc(i.datetime)),
                ('Artifact Type', lambda i, c: i.artifact_type),
                ('Artifact Value', lambda i, c: i.artifact_value),
                ('Host', lambda i, c: i.host),
                ('Malicious', lambda i, c: _bool(i.is_malicious)),
                ('Remediated', lambda i, c: _bool(i.remediated)),
                ('Notes', lambda i, c: i.notes),
            )),
        ExportEntity(
            key='malware', label='Malware and tools', permission='malware:read',
            model=lambda: MalwareTool, default_sort='-created_at',
            sortable=malware_sortable,
            filters=lambda: {
                'is_tool': (MalwareTool.is_tool, 'bool'),
                'host_id': (MalwareTool.host_id, 'uuid'),
            },
            search_columns=lambda: (MalwareTool.file_name, MalwareTool.file_path, MalwareTool.sha256,
                                    MalwareTool.md5, MalwareTool.malware_family),
            ioc_columns=('Sandbox Report URL',),
            columns=(
                ('File Name', lambda m, c: m.file_name),
                ('File Path', lambda m, c: m.file_path),
                ('MD5', lambda m, c: m.md5),
                ('SHA-256', lambda m, c: m.sha256),
                ('SHA-512', lambda m, c: m.sha512),
                ('File Size (bytes)', lambda m, c: m.file_size),
                ('Malware Family', lambda m, c: m.malware_family),
                ('Threat Actor', lambda m, c: m.threat_actor),
                ('Tool', lambda m, c: _bool(m.is_tool)),
                ('Host', lambda m, c: m.host),
                ('Created (UTC)', lambda m, c: iso_utc(m.creation_time)),
                ('Modified (UTC)', lambda m, c: iso_utc(m.modification_time)),
                ('Accessed (UTC)', lambda m, c: iso_utc(m.access_time)),
                ('Sandbox Report URL', lambda m, c: m.sandbox_report_url),
                ('Description', lambda m, c: m.description),
            )),
        ExportEntity(
            key='tasks', label='Tasks and leads', permission='tasks:read',
            model=lambda: Task, default_sort='order_index,-created_at',
            scope=lambda query, incident: query.filter(Task.parent_task_id.is_(None)),
            sortable=task_sortable, filters=task_filters,
            search_columns=lambda: (Task.title, Task.description),
            refine=_tasks_refine, prepare=_prepare_tasks,
            columns=(
                ('Title', lambda t, c: t.title),
                ('Type', lambda t, c: t.task_type),
                ('Status', lambda t, c: t.status),
                ('Priority', lambda t, c: t.priority),
                ('Assignee', lambda t, c: c['assignees'].get(t.assignee_id, '')),
                ('Due (UTC)', lambda t, c: iso_utc(t.due_date)),
                ('Completed (UTC)', lambda t, c: iso_utc(t.completed_at)),
                ('Phase', lambda t, c: t.phase),
                ('Lead Outcome', lambda t, c: t.lead_outcome),
                ('Investigation Direction', lambda t, c: t.investigation_direction),
                ('Evidence', _task_evidence),
                ('Description', lambda t, c: t.description),
            )),
    ]
    return {e.key: e for e in entities}


_REGISTRY: Optional[dict] = None


def entities() -> dict:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _registry()
    return _REGISTRY


def get_entity(key: str) -> Optional[ExportEntity]:
    return entities().get(key)


# ── Query + streaming ───────────────────────────────────────────────────────

def build_query(entity: ExportEntity, incident, args):
    """Scoped, filtered, searched and sorted query (``ListArgsError`` -> 400).

    Same params as the entity's list endpoint (``q``/``search``, ``sort``, its
    filters); paging params are ignored.
    """
    from app.utils.pagination import (apply_filters, apply_search, apply_sort, parse_list_args)

    model = entity.model()
    sortable = entity.sortable()
    la = parse_list_args(sortable=sortable, default_sort=entity.default_sort, args=args)
    query = entity.scope(model.query.filter_by(incident_id=incident.id), incident)
    if entity.refine:
        query = entity.refine(query, args)
    query = apply_filters(query, entity.filters(), args)
    query = apply_search(query, entity.search_columns(), la.q)
    return apply_sort(query, la, sortable, model.id)


def _truthy(raw) -> bool:
    return str(raw or '').strip().lower() in ('1', 'true', 'yes', 'on')


def iter_csv(entity: ExportEntity, query, incident, user, *, defang: bool = False) -> Iterator[bytes]:
    """UTF-8 CSV (BOM first), one encoded chunk per ``CHUNK`` rows."""
    headers = [h for h, _ in entity.columns]
    defang_cols = set(entity.ioc_columns) if defang else set()

    def render(rows: Iterable) -> bytes:
        buf = io.StringIO(newline='')
        writer = csv.writer(buf, lineterminator='\r\n')
        for row in rows:
            writer.writerow(row)
        return buf.getvalue().encode('utf-8')

    def cells(obj, ctx) -> list:
        out = []
        for header, getter in entity.columns:
            value = getter(obj, ctx)
            if header in defang_cols and value not in (None, ''):
                value = defang_ioc(value, domains=entity.defang_domains)
            out.append(csv_safe(value))
        return out

    yield (BOM).encode('utf-8') + render([[csv_safe(h) for h in headers]])
    chunk: list = []

    def flush():
        ctx = entity.prepare(chunk, incident, user) if entity.prepare else {}
        return render(cells(obj, ctx) for obj in chunk)

    for obj in query.yield_per(CHUNK):
        chunk.append(obj)
        if len(chunk) >= CHUNK:
            yield flush()
            chunk.clear()
    if chunk:
        yield flush()
