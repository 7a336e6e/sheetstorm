"""Dashboard aggregates (W2-DFIR-B, surface-dfir §3.7).

`GET /dashboard/stats` replaces the dashboard's client-side fan-out (first
page of incidents + one timeline request per incident), whose numbers were
wrong past 20 incidents / 50 events. Everything is counted in SQL over
`accessible_incidents_query(user)`, so the numbers cover every incident the
caller can see and nothing else. The response holds counts only: never an
incident id or title.
"""
from datetime import datetime, timedelta, timezone

from flask import jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import case, column, func, or_, true
from sqlalchemy.dialects.postgresql import JSONB

from app import db, limiter
from app.api.v1 import api_bp
from app.middleware.rbac import accessible_incidents_query, get_current_user, require_permission
from app.models import CompromisedHost, Incident, Task, TimelineEvent

SEVERITIES = ('critical', 'high', 'medium', 'low')


def _incident_stats(incident_ids):
    now = datetime.now(timezone.utc)
    week_ago, month_ago = now - timedelta(days=7), now - timedelta(days=30)
    rows = db.session.query(
        Incident.severity, Incident.status, Incident.phase, Incident.tlp,
        func.count(Incident.id),
        func.count(Incident.id).filter(Incident.created_at >= week_ago),
        func.count(Incident.id).filter(Incident.created_at >= month_ago),
    ).filter(Incident.id.in_(incident_ids)).group_by(
        Incident.severity, Incident.status, Incident.phase, Incident.tlp,
    ).all()

    stats = {'total': 0, 'active': 0, 'closed': 0, 'critical': 0, 'created_7d': 0, 'created_30d': 0,
             'by_severity': dict.fromkeys(SEVERITIES, 0), 'by_status': {}, 'by_phase_open': {}, 'by_tlp': {}}
    for severity, status, phase, tlp, n, n7, n30 in rows:
        stats['total'] += n
        stats['created_7d'] += n7
        stats['created_30d'] += n30
        stats['by_severity'][severity] = stats['by_severity'].get(severity, 0) + n
        stats['by_status'][status] = stats['by_status'].get(status, 0) + n
        stats['by_tlp'][tlp] = stats['by_tlp'].get(tlp, 0) + n
        if status == 'closed':
            stats['closed'] += n
        else:
            stats['active'] += n
            key = str(phase)
            stats['by_phase_open'][key] = stats['by_phase_open'].get(key, 0) + n
        if severity == 'critical':
            stats['critical'] += n
    return stats


def _mitre_stats(incident_ids):
    """Tactic/technique counts over timeline events: one count per mapping in
    `mitre_mappings`; events without mappings fall back to the legacy
    `mitre_tactic` / `mitre_technique` columns (same rule as the UI)."""
    mappings = TimelineEvent.mitre_mappings
    # CASE, not AND: Postgres does not short-circuit, and jsonb_array_length
    # raises on a scalar. SQL NULL counts as "no mappings".
    is_array = func.coalesce(func.jsonb_typeof(mappings), '') == 'array'
    has_mappings = case((is_array, func.jsonb_array_length(mappings)), else_=0) > 0
    legacy_tactic = func.nullif(func.trim(TimelineEvent.mitre_tactic), '')
    in_scope = TimelineEvent.incident_id.in_(incident_ids)

    events_total, events_mapped = db.session.query(
        func.count(TimelineEvent.id),
        func.count(TimelineEvent.id).filter(or_(has_mappings, legacy_tactic.isnot(None))),
    ).filter(in_scope).one()

    tactics = {}

    def add(tactic, technique, n):
        tactic = (tactic or '').strip().lower()
        if not tactic:
            return
        entry = tactics.setdefault(tactic, {'tactic': tactic, 'count': 0, 'techniques': {}})
        entry['count'] += n
        technique = (technique or '').strip().upper()
        if technique:
            entry['techniques'][technique] = entry['techniques'].get(technique, 0) + n

    # Guard: a row whose JSON is not an array expands to nothing.
    safe = case((is_array, mappings), else_=func.jsonb_build_array())
    elem = func.jsonb_array_elements(safe).table_valued(column('value', JSONB)).lateral('m')
    tactic_expr = elem.c.value['tactic'].astext
    technique_expr = elem.c.value['technique'].astext
    for tactic, technique, n in db.session.query(tactic_expr, technique_expr, func.count()).select_from(
            TimelineEvent).join(elem, true()).filter(in_scope).group_by(tactic_expr, technique_expr):
        add(tactic, technique, n)

    for tactic, technique, n in db.session.query(
            TimelineEvent.mitre_tactic, TimelineEvent.mitre_technique, func.count(TimelineEvent.id),
    ).filter(in_scope, ~has_mappings, legacy_tactic.isnot(None)).group_by(
            TimelineEvent.mitre_tactic, TimelineEvent.mitre_technique):
        add(tactic, technique, n)

    return {
        'events_total': events_total,
        'events_mapped': events_mapped,
        'tactics': sorted(tactics.values(), key=lambda t: (-t['count'], t['tactic'])),
    }


@api_bp.route('/dashboard/stats', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
@limiter.limit("30 per minute")  # rl-group: metrics
def get_dashboard_stats():
    """Aggregated counts over every non-archived incident the caller can see.

    `mitre` needs `timeline:read`; `dfir.open_leads` needs `tasks:read` and
    `dfir.hosts_by_triage` needs `hosts:read` (null otherwise).
    """
    user = get_current_user()
    perms = set(user.permissions)
    incident_ids = accessible_incidents_query(user).with_entities(Incident.id)

    dfir = {'open_leads': None, 'hosts_by_triage': None}
    if 'tasks:read' in perms:
        dfir['open_leads'] = db.session.query(func.count(Task.id)).filter(
            Task.incident_id.in_(incident_ids),
            Task.task_type == 'investigative_lead',
            Task.lead_outcome.is_(None),
        ).scalar()
    if 'hosts:read' in perms:
        by_triage = {}
        for triage, n in db.session.query(CompromisedHost.triage_status, func.count(CompromisedHost.id)).filter(
                CompromisedHost.incident_id.in_(incident_ids)).group_by(CompromisedHost.triage_status):
            key = triage or 'under_analysis'
            by_triage[key] = by_triage.get(key, 0) + n
        dfir['hosts_by_triage'] = by_triage

    return jsonify({
        'incidents': _incident_stats(incident_ids),
        'mitre': _mitre_stats(incident_ids) if 'timeline:read' in perms else None,
        'dfir': dfir,
    }), 200
