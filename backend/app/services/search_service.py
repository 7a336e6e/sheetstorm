"""Global cross-incident search.

One bounded SQL statement: a UNION ALL of one normalized select per entity
type (type, id, incident_id, title, snippet, ts, match_key), each restricted
to the caller's accessible incidents and to `<search doc> ILIKE '%q%'`; a
`facets` aggregate (count per type) and the requested page come out of the
same CTE. Nothing is merged or sliced in Python.

Each type's search doc is `coalesce(c1, '') || ' ' || coalesce(c2, '') ...`
over SEARCH_TYPES[...].doc_columns. Migration `add_search_trgm_indexes`
creates a pg_trgm GIN index on exactly that expression (same SQL text, see
`index_expression_sql`; test_search asserts parity and index use), so
`ILIKE '%x%'` is served by the index.

Extension point: a new searchable entity adds a SearchType here (doc
columns, read permission, deep-link tab) plus a trigram index in a
migration built from `index_expression_sql`.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from sqlalchemy import (
    String, Text, case, cast, func, literal_column, null, select, true, union_all,
)

from app import db
from app.models import (
    CaseNote, CompromisedAccount, CompromisedHost, HostBasedIndicator, Incident,
    MalwareTool, NetworkIndicator, TimelineEvent,
)
from app.utils.pagination import escape_like

SNIPPET_LEN = 200
SORTS = ('relevance', '-timestamp', 'timestamp')

_EMPTY = literal_column("''")
_SPACE = literal_column("' '")


@dataclass(frozen=True)
class SearchType:
    key: str                 # `types` param value (legacy plural names)
    result_type: str         # `type` of each result and facet key
    model: type
    table: str
    permission: str          # read permission required to see this type
    tab: str                 # incident page tab for the deep link
    doc_columns: Callable    # () -> [column expressions] in index order
    title: Callable          # () -> expression
    snippet: Callable        # () -> expression
    ts: Callable             # () -> timestamp expression
    match_key: Callable      # () -> expression ranked by relevance
    incident_col: Callable   # () -> incident id expression
    extra_where: Callable = lambda: ()


def _left(expr, n=SNIPPET_LEN):
    return func.left(expr, n)


SEARCH_TYPES: Sequence[SearchType] = (
    SearchType(
        key='incidents', result_type='incident', model=Incident, table='incidents',
        permission='incidents:read', tab='overview',
        doc_columns=lambda: [Incident.title, Incident.description,
                             Incident.executive_summary, Incident.classification],
        title=lambda: Incident.title,
        snippet=lambda: _left(func.coalesce(Incident.description, _EMPTY)),
        ts=lambda: Incident.created_at,
        match_key=lambda: Incident.title,
        incident_col=lambda: Incident.id,
    ),
    SearchType(
        key='timeline', result_type='timeline_event', model=TimelineEvent, table='timeline_events',
        permission='timeline:read', tab='events',
        doc_columns=lambda: [TimelineEvent.activity, TimelineEvent.hostname,
                             TimelineEvent.mitre_tactic, cast(TimelineEvent.mitre_mappings, Text)],
        title=lambda: _left(TimelineEvent.activity, 100),
        snippet=lambda: _left(TimelineEvent.activity),
        ts=lambda: TimelineEvent.timestamp,
        match_key=lambda: TimelineEvent.activity,
        incident_col=lambda: TimelineEvent.incident_id,
    ),
    SearchType(
        key='hosts', result_type='host', model=CompromisedHost, table='compromised_hosts',
        permission='hosts:read', tab='hosts',
        doc_columns=lambda: [CompromisedHost.hostname, func.host(CompromisedHost.ip_address),
                             CompromisedHost.system_type, CompromisedHost.notes],
        title=lambda: case(
            (CompromisedHost.ip_address.isnot(None),
             CompromisedHost.hostname + literal_column("' ('") + func.host(CompromisedHost.ip_address)
             + literal_column("')'")),
            else_=CompromisedHost.hostname),
        snippet=lambda: _left(func.coalesce(CompromisedHost.notes, _EMPTY)),
        ts=lambda: CompromisedHost.created_at,
        match_key=lambda: CompromisedHost.hostname,
        incident_col=lambda: CompromisedHost.incident_id,
    ),
    SearchType(
        # Never selects password_encrypted.
        key='accounts', result_type='account', model=CompromisedAccount, table='compromised_accounts',
        permission='accounts:read', tab='accounts',
        doc_columns=lambda: [CompromisedAccount.account_name, CompromisedAccount.domain,
                             CompromisedAccount.notes],
        title=lambda: case(
            (func.coalesce(CompromisedAccount.domain, _EMPTY) != _EMPTY,
             CompromisedAccount.domain + literal_column("'\\'") + CompromisedAccount.account_name),
            else_=CompromisedAccount.account_name),
        snippet=lambda: _left(func.coalesce(CompromisedAccount.notes, _EMPTY)),
        ts=lambda: CompromisedAccount.created_at,
        match_key=lambda: CompromisedAccount.account_name,
        incident_col=lambda: CompromisedAccount.incident_id,
    ),
    SearchType(
        key='network_iocs', result_type='network_ioc', model=NetworkIndicator, table='network_indicators',
        permission='network_iocs:read', tab='network',
        doc_columns=lambda: [NetworkIndicator.dns_ip, NetworkIndicator.source_host,
                             NetworkIndicator.destination_host, NetworkIndicator.description],
        title=lambda: NetworkIndicator.dns_ip,
        snippet=lambda: _left(func.coalesce(NetworkIndicator.description, _EMPTY)),
        ts=lambda: NetworkIndicator.created_at,
        match_key=lambda: NetworkIndicator.dns_ip,
        incident_col=lambda: NetworkIndicator.incident_id,
    ),
    SearchType(
        key='host_iocs', result_type='host_ioc', model=HostBasedIndicator, table='host_based_indicators',
        permission='host_iocs:read', tab='host-iocs',
        doc_columns=lambda: [HostBasedIndicator.artifact_value, HostBasedIndicator.notes,
                             HostBasedIndicator.host],
        title=lambda: (literal_column("'['") + HostBasedIndicator.artifact_type + literal_column("'] '")
                       + func.left(HostBasedIndicator.artifact_value, 80)),
        snippet=lambda: _left(func.coalesce(HostBasedIndicator.notes, _EMPTY)),
        ts=lambda: HostBasedIndicator.created_at,
        match_key=lambda: HostBasedIndicator.artifact_value,
        incident_col=lambda: HostBasedIndicator.incident_id,
    ),
    SearchType(
        key='malware', result_type='malware', model=MalwareTool, table='malware_tools',
        permission='malware:read', tab='malware',
        doc_columns=lambda: [MalwareTool.file_name, MalwareTool.file_path, MalwareTool.md5,
                             MalwareTool.sha256, MalwareTool.malware_family, MalwareTool.description],
        title=lambda: MalwareTool.file_name,
        snippet=lambda: (literal_column("'MD5: '") + func.coalesce(MalwareTool.md5, literal_column("'N/A'"))
                         + literal_column("' | SHA256: '")
                         + func.coalesce(MalwareTool.sha256, literal_column("'N/A'"))),
        ts=lambda: MalwareTool.created_at,
        match_key=lambda: MalwareTool.file_name,
        incident_col=lambda: MalwareTool.incident_id,
    ),
    SearchType(
        # Case notes are gated on incidents:read, like the case-notes tab.
        key='notes', result_type='case_note', model=CaseNote, table='case_notes',
        permission='incidents:read', tab='notes',
        doc_columns=lambda: [CaseNote.title, CaseNote.content],
        title=lambda: CaseNote.title,
        snippet=lambda: _left(CaseNote.content),
        ts=lambda: CaseNote.created_at,
        match_key=lambda: CaseNote.title,
        incident_col=lambda: CaseNote.incident_id,
        extra_where=lambda: (CaseNote.is_archived.isnot(True),),
    ),
)

TYPES_BY_NAME = {**{t.key: t for t in SEARCH_TYPES}, **{t.result_type: t for t in SEARCH_TYPES}}
TAB_BY_RESULT_TYPE = {t.result_type: t.tab for t in SEARCH_TYPES}


def search_doc(st: SearchType):
    """`coalesce(c1, '') || ' ' || coalesce(c2, '') ...` (the indexed expression)."""
    expr = None
    for col in st.doc_columns():
        part = func.coalesce(col, _EMPTY, type_=String)
        expr = part if expr is None else expr + _SPACE + part
    return expr


def index_expression_sql(st: SearchType) -> str:
    """The search doc as unqualified SQL text (what the migration indexes)."""
    from sqlalchemy.dialects import postgresql
    sql = str(search_doc(st).compile(dialect=postgresql.dialect()))
    return sql.replace(f'{st.table}.', '')


def allowed_types(user, requested: Optional[Sequence[str]]):
    """Requested (or all) types the user holds the read permission for."""
    if requested:
        wanted = {TYPES_BY_NAME[n].key for n in requested if n in TYPES_BY_NAME}
    else:
        wanted = {t.key for t in SEARCH_TYPES}
    return [t for t in SEARCH_TYPES if t.key in wanted and user.has_permission(t.permission)]


@dataclass(frozen=True)
class SearchParams:
    q: str
    page: int
    per_page: int
    sort: str = 'relevance'
    incident_id: Optional[uuid.UUID] = None
    since: Optional[object] = None
    until: Optional[object] = None


def _type_select(st: SearchType, accessible, pattern: str, p: SearchParams):
    inc = st.incident_col()
    ts = st.ts()
    where = [inc.in_(accessible), search_doc(st).ilike(pattern, escape='\\'), *st.extra_where()]
    if p.incident_id is not None:
        where.append(inc == p.incident_id)
    if p.since is not None:
        where.append(ts >= p.since)
    if p.until is not None:
        where.append(ts <= p.until)
    hostname = TimelineEvent.hostname if st.model is TimelineEvent else cast(null(), String)
    return select(
        literal_column(f"'{st.result_type}'", String).label('type'),
        st.model.id.label('id'),
        inc.label('incident_id'),
        cast(st.title(), Text).label('title'),
        cast(st.snippet(), Text).label('snippet'),
        ts.label('ts'),
        cast(st.match_key(), Text).label('match_key'),
        cast(hostname, Text).label('hostname'),
    ).where(*where)


def _order(cols, p: SearchParams):
    tie = [cols.type.asc(), cols.id.asc()]
    if p.sort == 'timestamp':
        return [cols.ts.asc().nullslast(), *tie]
    if p.sort == '-timestamp':
        return [cols.ts.desc().nullslast(), *tie]
    return [cols.rank.asc(), cols.ts.desc().nullslast(), *tie]


def build_search_statement(types: Sequence[SearchType], accessible, p: SearchParams):
    """The single search statement: one row per result on the page, each
    carrying the per-type `facets` JSON (one all-NULL row when the page is
    empty, so facets are always returned)."""
    pattern = f'%{escape_like(p.q)}%'
    hits = union_all(*[_type_select(st, accessible, pattern, p) for st in types]).cte('hits')

    rank = case(
        (func.lower(hits.c.match_key) == func.lower(p.q), 0),
        (hits.c.match_key.ilike(f'{escape_like(p.q)}%', escape='\\'), 1),
        else_=2,
    ).label('rank')
    ranked = select(hits, rank).subquery('ranked')
    page_sq = (
        select(ranked, Incident.title.label('incident_title'))
        .join(Incident, Incident.id == ranked.c.incident_id)
        .order_by(*_order(ranked.c, p))
        .limit(p.per_page).offset((p.page - 1) * p.per_page)
        .subquery('page')
    )
    counts = select(hits.c.type, func.count().label('n')).group_by(hits.c.type).subquery('counts')
    facets_sq = select(func.json_object_agg(counts.c.type, counts.c.n).label('facets')).subquery('facets')

    return (
        select(facets_sq.c.facets, page_sq)
        .select_from(facets_sq.outerjoin(page_sq, true()))
        .order_by(*_order(page_sq.c, p))
    )


def run_search(types: Sequence[SearchType], accessible, p: SearchParams) -> dict:
    """Execute the search statement; returns the response body."""
    empty = {'results': [], 'total': 0, 'page': p.page, 'per_page': p.per_page,
             'pages': 0, 'facets': {}, 'sort': p.sort}
    if not types:
        return empty

    stmt = build_search_statement(types, accessible, p)
    rows = db.session.execute(stmt).mappings().all()

    facets = (rows[0]['facets'] if rows else None) or {}
    total = sum(facets.values())
    results = []
    for r in rows:
        if r['id'] is None:
            continue
        item = {
            'type': r['type'],
            'id': str(r['id']),
            'incident_id': str(r['incident_id']),
            'incident_title': r['incident_title'],
            'title': r['title'],
            'snippet': r['snippet'] or '',
            'timestamp': r['ts'].isoformat() if r['ts'] else None,
            'link': {
                'incident_id': str(r['incident_id']),
                'tab': TAB_BY_RESULT_TYPE[r['type']],
                'row': None if r['type'] == 'incident' else str(r['id']),
            },
        }
        if r['type'] == 'timeline_event':
            item['hostname'] = r['hostname']
        results.append(item)

    return {
        'results': results,
        'total': total,
        'page': p.page,
        'per_page': p.per_page,
        'pages': math.ceil(total / p.per_page) if total else 0,
        'facets': facets,
        'sort': p.sort,
    }
