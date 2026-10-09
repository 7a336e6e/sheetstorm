"""Post-incident response metrics (W3-RT-POST, realtime-collab-metrics §3.5).

Per incident (``incident_metrics``) and per organization over the incidents a
user may see (``org_metrics``; computed in SQL over
``accessible_incidents_query``, so visibility is exactly the incident list's).

Definitions (seconds; ``None`` when an endpoint is missing)::

    first_malicious = incidents.first_malicious_at (override)
                      or MIN(timeline_events.timestamp) of events that are
                      IOCs / have a MITRE tactic or mapping / a kill-chain phase
    dwell_time            = detected  - first_malicious      (CSF DE)
    time_to_respond       = responded - detected             (RS.MA)
    time_to_contain       = contained - detected             (RS.MI)
    contain_to_eradicate  = eradicated - contained           (RS.MI)
    eradicate_to_recover  = recovered - eradicated           (RC.RP)
    recover_to_close      = closed - recovered
    total_open            = (closed or now) - detected

A negative interval (legacy data edited out of order) is reported as ``None``
plus an anomaly, never as a negative duration.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import Float, case, cast, extract, func, literal, or_, select

from app import db

# (metric, from-timestamp, to-timestamp); order is the display order.
DURATION_METRICS = (
    ('dwell_time', 'first_malicious', 'detected'),
    ('time_to_respond', 'detected', 'responded'),
    ('time_to_contain', 'detected', 'contained'),
    ('contain_to_eradicate', 'contained', 'eradicated'),
    ('eradicate_to_recover', 'eradicated', 'recovered'),
    ('recover_to_close', 'recovered', 'closed'),
)
METRIC_NAMES = tuple(m for m, _, _ in DURATION_METRICS) + ('total_open',)
TIMESTAMP_NAMES = ('first_malicious', 'detected', 'responded', 'contained', 'eradicated', 'recovered', 'closed')

GROUP_BYS = ('none', 'severity', 'classification', 'detection_source')
DATE_FIELDS = ('detected_at', 'closed_at')
MAX_RANGE_DAYS = 731
MIN_GROUP_SIZE = 3  # no medians/p90 over fewer values than this (small-n noise)


class MetricsRangeError(ValueError):
    """Bad ``from``/``to``/``group_by``/``date_field`` (400 ``invalid_range``)."""


# ---------------------------------------------------------------------------
# Pure computation
# ---------------------------------------------------------------------------

def compute_durations(timestamps, now=None):
    """``timestamps``: {first_malicious, detected, responded, contained,
    eradicated, recovered, closed} -> aware datetimes or None.

    Returns ``(durations, anomalies)``: seconds-or-None per metric and
    ``[{metric, reason:'negative', seconds}]`` for negative intervals.
    """
    now = now or datetime.now(timezone.utc)
    durations, anomalies = {}, []
    for metric, start, end in DURATION_METRICS:
        a, b = timestamps.get(start), timestamps.get(end)
        if a is None or b is None:
            durations[metric] = None
            continue
        seconds = (b - a).total_seconds()
        if seconds < 0:
            durations[metric] = None
            anomalies.append({'metric': metric, 'reason': 'negative', 'seconds': round(seconds)})
        else:
            durations[metric] = round(seconds)
    detected = timestamps.get('detected')
    if detected is None:
        durations['total_open'] = None
    else:
        seconds = ((timestamps.get('closed') or now) - detected).total_seconds()
        if seconds < 0:
            durations['total_open'] = None
            anomalies.append({'metric': 'total_open', 'reason': 'negative', 'seconds': round(seconds)})
        else:
            durations['total_open'] = round(seconds)
    return durations, anomalies


def _iso(value):
    return value.isoformat() if value else None


# ---------------------------------------------------------------------------
# Timeline-derived first malicious activity
# ---------------------------------------------------------------------------

def malicious_event_clause():
    """SQL clause: a timeline event that evidences adversary activity (IOC,
    MITRE tactic / mapping, or kill-chain phase). Same array guard as the
    dashboard: ``jsonb_array_length`` raises on a scalar, and Postgres does not
    short-circuit ``AND``."""
    from app.models import TimelineEvent as TE
    is_array = func.coalesce(func.jsonb_typeof(TE.mitre_mappings), '') == 'array'
    has_mappings = case((is_array, func.jsonb_array_length(TE.mitre_mappings)), else_=0) > 0
    return or_(
        TE.is_ioc.is_(True),
        func.nullif(func.trim(TE.mitre_tactic), '').isnot(None),
        has_mappings,
        func.nullif(func.trim(TE.kill_chain_phase), '').isnot(None),
    )


def derived_first_malicious(incident_id):
    from app.models import TimelineEvent as TE
    return db.session.query(func.min(TE.timestamp)).filter(
        TE.incident_id == incident_id, malicious_event_clause()).scalar()


def incident_metrics(incident, *, derive_first_malicious=True, now=None):
    """Metrics for one incident.

    ``derive_first_malicious=False`` (caller lacks ``timeline:read``) skips
    the timeline lookup so the endpoint never discloses a timeline timestamp;
    an override stored on the incident is still used.
    """
    now = now or datetime.now(timezone.utc)
    override = incident.first_malicious_at
    if override is not None:
        first, source = override, 'override'
    elif derive_first_malicious:
        first = derived_first_malicious(incident.id)
        source = 'timeline' if first is not None else None
    else:
        first, source = None, 'restricted'

    timestamps = {
        'first_malicious': first,
        'detected': incident.detected_at,
        'responded': incident.responded_at,
        'contained': incident.contained_at,
        'eradicated': incident.eradicated_at,
        'recovered': incident.recovered_at,
        'closed': incident.closed_at,
    }
    durations, anomalies = compute_durations(timestamps, now)
    return {
        'incident_id': str(incident.id),
        'timestamps': {k: _iso(v) for k, v in timestamps.items()},
        'durations': durations,
        'anomalies': anomalies,
        'sources': {'first_malicious': source},
    }


# ---------------------------------------------------------------------------
# Organization aggregates (SQL)
# ---------------------------------------------------------------------------

def parse_range(raw_from, raw_to, date_field='detected_at', group_by='none'):
    """Validate the query parameters; returns ``(start, end, date_field, group_by)``
    with ``end`` exclusive. A date-only ``to`` includes that whole day."""
    from werkzeug.exceptions import BadRequest
    from app.utils.validation import parse_datetime
    if date_field not in DATE_FIELDS:
        raise MetricsRangeError(f'date_field must be one of: {", ".join(DATE_FIELDS)}')
    if group_by not in GROUP_BYS:
        raise MetricsRangeError(f'group_by must be one of: {", ".join(GROUP_BYS)}')
    if not raw_from or not raw_to:
        raise MetricsRangeError('from and to are required')
    try:
        start = parse_datetime(raw_from, 'from', required=True)
        end = parse_datetime(raw_to, 'to', required=True)
    except BadRequest as exc:
        raise MetricsRangeError(exc.description)
    if len(raw_to.strip()) <= 10:  # YYYY-MM-DD
        end = end + timedelta(days=1)
    if end <= start:
        raise MetricsRangeError('to must be after from')
    if end - start > timedelta(days=MAX_RANGE_DAYS):
        raise MetricsRangeError(f'The range may not exceed {MAX_RANGE_DAYS} days')
    return start, end, date_field, group_by


def _epoch(later, earlier):
    return cast(extract('epoch', later - earlier), Float)


def _per_incident_cte(user, start, end, date_field, group_by):
    from app.middleware.rbac import accessible_incidents_query
    from app.models import Incident, IncidentReview, TimelineEvent as TE

    date_col = getattr(Incident, date_field)
    visible = accessible_incidents_query(user).with_entities(Incident.id).filter(
        date_col >= start, date_col < end)

    derived = select(func.min(TE.timestamp)).where(
        TE.incident_id == Incident.id, malicious_event_clause()).correlate(Incident).scalar_subquery()
    first = func.coalesce(Incident.first_malicious_at, derived)
    ts = {
        'first_malicious': first,
        'detected': Incident.detected_at,
        'responded': Incident.responded_at,
        'contained': Incident.contained_at,
        'eradicated': Incident.eradicated_at,
        'recovered': Incident.recovered_at,
        'closed': Incident.closed_at,
    }

    if group_by == 'severity':
        group = Incident.severity
    elif group_by == 'classification':
        group = Incident.classification
    elif group_by == 'detection_source':
        group = select(IncidentReview.detection_source).where(
            IncidentReview.incident_id == Incident.id).correlate(Incident).scalar_subquery()
    else:
        group = literal('all')

    columns = [Incident.id.label('id'), group.label('grp')]
    for metric, start_name, end_name in DURATION_METRICS:
        delta = _epoch(ts[end_name], ts[start_name])
        columns.append(case((delta >= 0, delta), else_=None).label(f'm_{metric}'))
        columns.append(case((delta < 0, 1), else_=0).label(f'neg_{metric}'))
    total = _epoch(func.coalesce(Incident.closed_at, func.now()), Incident.detected_at)
    columns.append(case((total >= 0, total), else_=None).label('m_total_open'))
    columns.append(case((total < 0, 1), else_=0).label('neg_total_open'))

    return select(*columns).where(Incident.id.in_(visible.scalar_subquery())).cte('incident_ts')


def _aggregate(cte, grouped):
    cols = []
    for metric in METRIC_NAMES:
        values = cte.c[f'm_{metric}']
        cols += [
            func.percentile_cont(0.5).within_group(values).label(f'med_{metric}'),
            func.percentile_cont(0.9).within_group(values).label(f'p90_{metric}'),
            func.count(values).label(f'n_{metric}'),
            func.coalesce(func.sum(cte.c[f'neg_{metric}']), 0).label(f'neg_{metric}'),
        ]
    stmt = select(*( [cte.c.grp] if grouped else [] ), func.count().label('n'), *cols)
    if grouped:
        stmt = stmt.group_by(cte.c.grp)
    return stmt


def _row_metrics(row):
    out = {}
    for metric in METRIC_NAMES:
        n = row._mapping[f'n_{metric}']
        enough = n >= MIN_GROUP_SIZE
        median, p90 = row._mapping[f'med_{metric}'], row._mapping[f'p90_{metric}']
        out[metric] = {
            'median': round(median) if enough and median is not None else None,
            'p90': round(p90) if enough and p90 is not None else None,
            'n': n,
            'anomalies': int(row._mapping[f'neg_{metric}']),
        }
    return out


def org_metrics(user, start, end, date_field='detected_at', group_by='none'):
    """Median / p90 of every metric over the incidents ``user`` can see whose
    ``date_field`` falls in ``[start, end)`` (archived incidents excluded).
    A metric with fewer than ``MIN_GROUP_SIZE`` values reports ``n`` only."""
    cte = _per_incident_cte(user, start, end, date_field, group_by)
    overall_row = db.session.execute(_aggregate(cte, grouped=False)).one()
    result = {
        'range': {'from': start.isoformat(), 'to': end.isoformat(), 'date_field': date_field},
        'group_by': group_by,
        'metrics': list(METRIC_NAMES),
        'min_group_size': MIN_GROUP_SIZE,
        'overall': {'n': overall_row.n, 'metrics': _row_metrics(overall_row)},
        'groups': [],
    }
    if group_by != 'none':
        groups = []
        for row in db.session.execute(_aggregate(cte, grouped=True)).all():
            groups.append({'key': row.grp, 'n': row.n, 'metrics': _row_metrics(row)})
        groups.sort(key=lambda g: (-g['n'], str(g['key'])))
        result['groups'] = groups
    return result
