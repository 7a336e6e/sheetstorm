"""Audit log endpoints: search, export, retention / legal-hold settings,
chain integrity, and the activity feed."""
import re
from datetime import datetime, timezone

from flask import Response, current_app, jsonify, request, stream_with_context
from flask_jwt_extended import jwt_required
from sqlalchemy import func
from werkzeug.exceptions import BadRequest

from app import db, limiter
from app.api.v1 import api_bp
from app.middleware.audit import audit_log, log_audit_event, log_security_event
from app.middleware.rbac import get_current_user, require_permission
from app.models import AuditLog, Organization
from app.services import audit_service
from app.utils.audit_diff import record_changes
from app.utils.pagination import paginate_response, parse_list_args
from app.utils.validation import parse_datetime

FACET_LIMIT = 200
EXPORT_FORMATS = {
    'csv': ('text/csv; charset=utf-8', 'csv'),
    'jsonl': ('application/x-ndjson; charset=utf-8', 'jsonl'),
}


def _serialize(log):
    return log.to_dict()


@api_bp.route('/audit-logs', methods=['GET'])
@jwt_required()
@require_permission('audit_logs:read')
def list_audit_logs():
    """List audit logs (filters: see audit_service.build_audit_query; sort=-field)."""
    user = get_current_user()
    la = parse_list_args(sortable=audit_service.SORTABLE, default_sort=audit_service.DEFAULT_SORT)
    audit_service.check_page_depth(la.page, la.per_page)
    query = audit_service.build_audit_query(user.organization_id, request.args)
    body = paginate_response(query, la, serialize=_serialize, sortable=audit_service.SORTABLE,
                             id_col=AuditLog.id)
    return jsonify(body), 200


@api_bp.route('/audit-logs/<uuid:log_id>', methods=['GET'])
@jwt_required()
@require_permission('audit_logs:read')
def get_audit_log(log_id):
    """Get audit log details (including details.changes)."""
    user = get_current_user()

    log = AuditLog.query.filter_by(
        id=log_id,
        organization_id=user.organization_id
    ).first()

    if not log:
        return jsonify({'error': 'not_found', 'message': 'Audit log not found'}), 404

    return jsonify(log.to_dict()), 200


@api_bp.route('/audit-logs/event-types', methods=['GET'])
@jwt_required()
@require_permission('audit_logs:read')
def list_event_types():
    """List available event types."""
    return jsonify({'event_types': AuditLog.EVENT_TYPES}), 200


@api_bp.route('/audit-logs/facets', methods=['GET'])
@jwt_required()
@require_permission('audit_logs:read')
def get_audit_facets():
    """Distinct actions and resource types of the org (for filter dropdowns)."""
    user = get_current_user()
    base = AuditLog.query.filter(AuditLog.organization_id == user.organization_id)

    def distinct(column):
        rows = (base.with_entities(column).filter(column.isnot(None)).distinct()
                .order_by(column.asc()).limit(FACET_LIMIT).all())
        return [r[0] for r in rows]

    return jsonify({
        'actions': distinct(AuditLog.action),
        'resource_types': distinct(AuditLog.resource_type),
        'event_types': AuditLog.EVENT_TYPES,
    }), 200


@api_bp.route('/audit-logs/stats', methods=['GET'])
@jwt_required()
@require_permission('audit_logs:read')
def get_audit_stats():
    """Counts by event type and by day (last 30 days) for the filtered log."""
    user = get_current_user()
    query = audit_service.build_audit_query(user.organization_id, request.args).order_by(None)

    event_counts = (query.with_entities(AuditLog.event_type, func.count(AuditLog.id))
                    .group_by(AuditLog.event_type).all())

    from datetime import timedelta
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    day = func.date(AuditLog.created_at)
    daily_counts = (query.filter(AuditLog.created_at >= thirty_days_ago)
                    .with_entities(day, func.count(AuditLog.id)).group_by(day).all())

    return jsonify({
        'by_event_type': {et: count for et, count in event_counts},
        'by_day': {str(d): count for d, count in daily_counts},
        'total': sum(count for _, count in event_counts)
    }), 200


def _export_filename(org, ext):
    slug = re.sub(r'[^a-z0-9-]+', '-', (org.slug if org else 'org').lower()).strip('-')[:60] or 'org'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return f'audit-{slug}-{stamp}.{ext}'


@api_bp.route('/audit-logs/export', methods=['GET'])
@jwt_required()
@require_permission('audit_logs:export')
@limiter.limit("10 per hour")  # rl-group: audit_export
def export_audit_logs():
    """Export the filtered audit log as CSV or JSONL (format=csv|jsonl).

    Capped at AUDIT_EXPORT_MAX_ROWS: more rows is 422 export_too_large (never
    a silent partial dump). The export is audited before the first byte.
    """
    user = get_current_user()
    fmt = (request.args.get('format') or 'csv').strip().lower()
    if fmt not in EXPORT_FORMATS:
        return jsonify({'error': 'invalid_filter', 'message': 'format must be csv or jsonl'}), 400

    query = audit_service.build_audit_query(user.organization_id, request.args)
    cap = int(current_app.config.get('AUDIT_EXPORT_MAX_ROWS', 100000))
    row_count = audit_service.count_capped(query, cap)
    if row_count > cap:
        return jsonify({'error': 'export_too_large',
                        'message': f'More than {cap} rows match; narrow the filters (e.g. the date range)',
                        'max_rows': cap}), 422

    org = db.session.get(Organization, user.organization_id)
    chain = audit_service.chain_status(user.organization_id)
    filters = audit_service.filters_echo(request.args)
    entry = log_audit_event('data_access', 'export', 'audit_log',
                            details={'format': fmt, 'filters': filters, 'row_count': row_count})
    if entry is None:
        # Never hand out an unaudited export.
        return jsonify({'error': 'audit_unavailable', 'message': 'Could not record the export'}), 503

    ordered = (audit_service.build_audit_query(user.organization_id, request.args)
               .order_by(AuditLog.created_at.asc(), AuditLog.id.asc()).limit(row_count))
    mimetype, ext = EXPORT_FORMATS[fmt]
    resp = Response(stream_with_context(audit_service.export_chunks(ordered, fmt)), mimetype=mimetype)
    resp.headers['Content-Disposition'] = f'attachment; filename="{_export_filename(org, ext)}"'
    resp.headers['Cache-Control'] = 'no-store'
    resp.headers['X-Audit-Chain-Head'] = f"{chain['head_seq']}:{chain['head_hash'] or ''}"
    resp.headers['X-Audit-Row-Count'] = str(row_count)
    return resp


# ---------------------------------------------------------------------------
# Retention / legal hold
# ---------------------------------------------------------------------------

_SETTINGS_FIELDS = ('audit_retention_days', 'legal_hold', 'legal_hold_reason', 'confirm')


def _settings_error(fields, message='Invalid audit settings'):
    return jsonify({'error': 'validation_error', 'message': message, 'fields': fields}), 400


def _settings_view(org):
    s = audit_service.get_audit_settings(org)
    return {k: s[k] for k in audit_service.AUDIT_SETTINGS_KEYS}


@api_bp.route('/admin/audit-settings', methods=['GET'])
@jwt_required()
@require_permission('organizations:manage')
def get_audit_settings():
    """Audit retention and legal hold of the caller's organization."""
    user = get_current_user()
    org = db.session.get(Organization, user.organization_id)
    if not org:
        return jsonify({'error': 'not_found', 'message': 'Organization not found'}), 404
    return jsonify(audit_service.get_audit_settings(org)), 200


@api_bp.route('/admin/audit-settings', methods=['PUT'])
@jwt_required()
@require_permission('organizations:manage')
@audit_log('admin_action', 'update_audit_settings', 'organization')
def update_audit_settings():
    """Set retention (null = keep forever, else >= AUDIT_RETENTION_MIN_DAYS)
    and the legal hold. Shortening retention needs ``confirm: true``
    (otherwise 409 with ``would_purge``)."""
    user = get_current_user()
    raw = request.get_json(silent=True)
    if not isinstance(raw, dict):
        return _settings_error({}, 'JSON object required')
    unknown = sorted(set(raw) - set(_SETTINGS_FIELDS))
    if unknown:
        return _settings_error({k: 'Unknown field' for k in unknown})

    org = Organization.query.filter_by(id=user.organization_id).with_for_update().first()
    if not org:
        return jsonify({'error': 'not_found', 'message': 'Organization not found'}), 404
    current = audit_service.get_audit_settings(org)
    min_days, max_days = current['min_retention_days'], current['max_retention_days']
    new = dict(current)
    errors = {}

    if 'audit_retention_days' in raw:
        days = raw['audit_retention_days']
        if days is not None and (isinstance(days, bool) or not isinstance(days, int)
                                 or not min_days <= days <= max_days):
            errors['audit_retention_days'] = f'Must be null (keep forever) or an integer {min_days}..{max_days}'
        else:
            new['audit_retention_days'] = days

    if 'legal_hold' in raw and not isinstance(raw['legal_hold'], bool):
        errors['legal_hold'] = 'Must be true or false'
    reason = raw.get('legal_hold_reason')
    if reason is not None:
        if not isinstance(reason, str):
            errors['legal_hold_reason'] = 'Must be a string'
        else:
            reason = reason.strip()
            if len(reason) > audit_service.LEGAL_HOLD_REASON_MAX:
                errors['legal_hold_reason'] = f'At most {audit_service.LEGAL_HOLD_REASON_MAX} characters'
    if 'confirm' in raw and not isinstance(raw['confirm'], bool):
        errors['confirm'] = 'Must be true or false'
    if errors:
        db.session.rollback()
        return _settings_error(errors)

    hold = raw.get('legal_hold', current['legal_hold'])
    enabling = hold and not current['legal_hold']
    releasing = current['legal_hold'] and not hold
    if hold:
        if enabling and not reason:
            db.session.rollback()
            return _settings_error({'legal_hold_reason': 'A reason is required to place a legal hold'})
        if enabling:
            new.update(legal_hold=True, legal_hold_reason=reason, legal_hold_set_by=str(user.id),
                       legal_hold_set_at=datetime.now(timezone.utc).isoformat())
        elif reason:
            new['legal_hold_reason'] = reason
    elif releasing:
        new.update(legal_hold=False, legal_hold_reason=None, legal_hold_set_by=None, legal_hold_set_at=None)

    old_days, new_days = current['audit_retention_days'], new['audit_retention_days']
    shortening = new_days is not None and (old_days is None or new_days < old_days)
    if shortening and raw.get('confirm') is not True:
        cutoff = audit_service.retention_cutoff(new_days)
        would_purge = (AuditLog.query.filter(AuditLog.organization_id == org.id,
                                             AuditLog.created_at < cutoff).count())
        db.session.rollback()
        return jsonify({'error': 'confirmation_required',
                        'message': 'Shortening retention deletes older audit rows at the next purge; '
                                   'resend with confirm: true',
                        'would_purge': would_purge, 'cutoff': cutoff.isoformat()}), 409

    before = _settings_view(org)
    stored = dict(org.settings or {})
    for key in audit_service.AUDIT_SETTINGS_KEYS:
        if new[key] is None or new[key] is False:
            stored.pop(key, None)
        else:
            stored[key] = new[key]
    org.settings = stored
    db.session.commit()
    after = _settings_view(org)
    record_changes(before, after)

    if enabling:
        log_security_event('legal_hold_enabled', resource_type='organization', resource_id=org.id,
                           details={'scope': 'audit_log', 'reason': reason})
    elif releasing:
        log_security_event('legal_hold_released', resource_type='organization', resource_id=org.id,
                           details={'scope': 'audit_log'})

    return jsonify(audit_service.get_audit_settings(org)), 200


@api_bp.route('/admin/audit-integrity', methods=['GET'])
@jwt_required()
@require_permission('organizations:manage')
@limiter.limit("6 per hour")  # rl-group: audit_integrity
def verify_audit_integrity():
    """Verify the organization's audit hash chain (first <= 50 failures)."""
    user = get_current_user()
    summary = audit_service.verify_chain(user.organization_id, max_failures=50)
    return jsonify(summary), 200


# ---------------------------------------------------------------------------
# Activity feed
# ---------------------------------------------------------------------------

def _visible_incident_resource_types(user):
    """Resource types of incident activity the user may see (same rule as the
    ``activity:new`` broadcast: the resource's realtime scope must be one the
    user can read). Rows without a resource type are always visible."""
    from app.services import realtime
    scopes = set(realtime.scopes_for_user(user))
    names = set(realtime.ENTITY_SCOPES) | set(getattr(realtime, '_RESOURCE_TYPE_ALIASES', {}))
    return sorted(n for n in names if realtime.scope_for_resource_type(n) in scopes)


@api_bp.route('/activity-feed', methods=['GET'])
@jwt_required()
def get_activity_feed():
    """Get recent activity for the current user's organization.

    Returns human-readable activity items (excludes raw auth/system noise).
    Query params: limit (int, default 30, max 100), before (ISO datetime cursor).
    """
    user = get_current_user()
    if not user:
        return jsonify({'error': 'unauthorized', 'message': 'Authentication required'}), 401
    limit = max(1, min(request.args.get('limit', 30, type=int), 100))
    # Admin actions and full details are for audit-log readers.
    is_admin = user.has_permission('audit_logs:read')

    # Only show user-facing event types; admin actions are admin-only.
    feed_event_types = ['data_modification', 'data_access', 'security_event']
    if is_admin:
        feed_event_types.append('admin_action')

    # Only activity on incidents the user can access (same rules as the
    # incident list), plus org-level events not tied to any incident.
    from app.models import Incident
    from app.middleware.rbac import accessible_incidents_query
    accessible_ids = accessible_incidents_query(user).with_entities(Incident.id)

    incident_rows = AuditLog.incident_id.in_(accessible_ids)
    if not is_admin:
        # Within an incident, only resources whose read permission the user holds.
        incident_rows = db.and_(incident_rows, db.or_(
            AuditLog.resource_type.is_(None),
            AuditLog.resource_type.in_(_visible_incident_resource_types(user))))

    query = AuditLog.query.filter(
        AuditLog.organization_id == user.organization_id,
        AuditLog.event_type.in_(feed_event_types),
        db.or_(AuditLog.incident_id.is_(None), incident_rows),
    )

    before = request.args.get('before')
    if before:
        try:
            query = query.filter(AuditLog.created_at < parse_datetime(before, 'before'))
        except BadRequest:
            pass

    incident_id = request.args.get('incident_id')
    if incident_id:
        try:
            from uuid import UUID
            query = query.filter(AuditLog.incident_id == UUID(incident_id))
        except ValueError:
            return jsonify({'error': 'bad_request', 'message': 'invalid incident_id'}), 400

    logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    from app.middleware.audit import public_activity_details
    items = []
    for log in logs:
        items.append({
            'id': str(log.id),
            'event_type': log.event_type,
            'action': log.action,
            'resource_type': log.resource_type,
            'resource_id': str(log.resource_id) if log.resource_id else None,
            'incident_id': str(log.incident_id) if log.incident_id else None,
            'user_email': log.user_email,
            'user_id': str(log.user_id) if log.user_id else None,
            'created_at': log.created_at.isoformat() if log.created_at else None,
            'details': log.details if is_admin else public_activity_details(log.details),
        })

    return jsonify({
        'items': items,
        'has_more': len(items) == limit,
    }), 200
