"""CSV exports of incident entities (surface-dfir §3.8; _integration C23/C24/C35).

``GET /incidents/<id>/export/<entity>`` streams a CSV of what the matching
list endpoint shows (same filter / sort / search params, no paging).

Authorization (all required):
* ``@require_incident_access('incidents:read')``: org scope + incident visibility;
* the entity's own read permission (``timeline:read``, ``hosts:read``, ...);
* ``incidents:export`` (C24).

The STIX export (``search.py``) shares the ``incidents:export`` rule.
"""
import re
from datetime import datetime, timezone

from flask import Response, g, jsonify, request, stream_with_context
from flask_jwt_extended import jwt_required

from app import limiter
from app.api.v1 import api_bp
from app.middleware.audit import audit_log
from app.middleware.rbac import get_current_user, require_incident_access
from app.services import csv_export
from app.utils.audit_diff import record_changes

EXPORT_PERMISSION = 'incidents:export'
_IGNORED_ARGS = ('page', 'per_page', 'focus', 'defang')


def export_filename(incident, label: str, extension: str) -> str:
    """``incident-<n>-TLP_<LEVEL>-<label>-<YYYYMMDDTHHMMZ>.<ext>`` (ASCII only)."""
    tlp = re.sub(r'[^A-Za-z0-9]+', '_', str(incident.tlp or 'unset')).strip('_').upper() or 'UNSET'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%MZ')
    number = incident.incident_number if incident.incident_number is not None else str(incident.id)[:8]
    return f'incident-{number}-TLP_{tlp}-{label}-{stamp}.{extension}'


def forbidden(permission: str):
    return jsonify({'error': 'forbidden', 'message': f'Permission denied. Required: {permission}'}), 403


@api_bp.route('/incidents/<uuid:incident_id>/export/<string:entity>', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
@limiter.limit('30 per minute')  # rl-group: exports
@audit_log('data_access', 'export_csv', 'incident')
def export_incident_csv(incident_id, entity):
    """CSV export of one entity (``timeline``, ``hosts``, ``accounts``,
    ``network-iocs``, ``host-iocs``, ``malware``, ``tasks``).

    Query: the list endpoint's filters, ``q``/``search`` and ``sort``;
    ``defang=true`` defangs indicator-value columns. 404 for an unknown
    entity, 403 without the entity read permission or ``incidents:export``.
    """
    spec = csv_export.get_entity(entity)
    if spec is None:
        return jsonify({'error': 'not_found', 'message': f'Unknown export entity: {entity[:40]}'}), 404
    user, incident = get_current_user(), g.incident
    for permission in (spec.permission, EXPORT_PERMISSION):
        if not user.has_permission(permission):
            return forbidden(permission)

    query = csv_export.build_query(spec, incident, request.args)  # ListArgsError -> 400
    total = query.order_by(None).count()
    if total > csv_export.MAX_EXPORT_ROWS:
        return jsonify({'error': 'export_too_large',
                        'message': f'Export is limited to {csv_export.MAX_EXPORT_ROWS} rows; narrow the filters',
                        'rows': total}), 400

    defang = csv_export._truthy(request.args.get('defang'))
    filters = {k: v[:200] for k, v in request.args.items() if k not in _IGNORED_ARGS}
    record_changes({}, {}, entity=spec.key, rows=total, defang=defang, filters=filters)

    response = Response(stream_with_context(csv_export.iter_csv(spec, query, incident, user, defang=defang)),
                        mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename="{export_filename(incident, spec.key, "csv")}"'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Export-Rows'] = str(total)
    return response
