"""Record provenance endpoints: second-analyst verification and the live
normalization preview (decision-log-provenance §3.5).

The create / update paths of timeline events and IOCs apply provenance in
``timeline.py`` / ``iocs.py``; the host clock-skew routes live in
``compromised.py``. This module also owns the 400 mapping for
:class:`~app.services.provenance_service.ProvenanceError` on the whole API.
"""
import uuid

from flask import g, jsonify
from flask_jwt_extended import jwt_required

from app.services.rate_limit_settings import limited
from app import db
from app.api.v1 import api_bp
from app.middleware.audit import audit_log
from app.middleware.rbac import check_permission, get_current_user, require_incident_access
from app.models import CompromisedHost
from app.services import provenance_service as prov
from app.services import realtime
from app.utils.audit_diff import record_changes
from app.utils.concurrency import commit_or_conflict, precondition, set_etag
from app.utils.validation import json_body


@api_bp.errorhandler(prov.ProvenanceError)
def _provenance_error(e):
    db.session.rollback()
    return e.to_response()


def _load_record(incident, data):
    """(kind, record) from ``{record_type, record_id}``; 404 when absent."""
    kind = prov.resolve_kind(data.get('record_type'))
    model, perm, _entity = prov.RECORD_KINDS[kind]
    user = get_current_user()
    if not check_permission(user, perm):
        return kind, None, (jsonify({'error': 'forbidden', 'message': f'Permission denied. Required: {perm}'}), 403)
    try:
        record_id = uuid.UUID(str(data.get('record_id')))
    except ValueError:
        return kind, None, (jsonify({'error': 'bad_request', 'message': 'record_id must be a UUID'}), 400)
    record = model.query.filter_by(id=record_id, incident_id=incident.id).first()
    if not record:
        return kind, None, (jsonify({'error': 'not_found', 'message': 'Record not found'}), 404)
    return kind, record, None


@api_bp.route('/incidents/<uuid:incident_id>/provenance/verify', methods=['POST'])
@jwt_required()
@require_incident_access()
@audit_log('data_modification', 'verify_provenance', 'provenance')
def verify_provenance(incident_id):
    """Mark a record's provenance verified by a second analyst.

    Body ``{record_type: timeline_event|network_ioc|host_ioc|malware,
    record_id}`` (+ optional ``expected_version``/If-Match). Requires the
    record type's ``:update`` permission. 400 ``same_analyst`` when the caller
    created the record, 400 ``no_provenance``, 409 ``already_verified``.
    """
    incident = g.incident
    data = json_body()
    kind, record, error = _load_record(incident, data)
    if error:
        return error
    conflict = precondition(record)
    if conflict:
        return conflict, conflict.status_code

    user = get_current_user()
    prov.verify(record, user)
    record_changes({'provenance_verified_at': None, 'provenance_verified_by': None},
                   {'provenance_verified_at': record.provenance_verified_at,
                    'provenance_verified_by': user.id},
                   record_type=kind, record_id=str(record.id))
    conflict = commit_or_conflict(record)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, prov.RECORD_KINDS[kind][2], 'updated', obj=record)
    return set_etag(jsonify(record.to_dict()), record), 200


@api_bp.route('/incidents/<uuid:incident_id>/provenance/verify', methods=['DELETE'])
@jwt_required()
@require_incident_access()
@audit_log('data_modification', 'unverify_provenance', 'provenance')
def unverify_provenance(incident_id):
    """Withdraw a verification (same body as POST). Only the verifier, or an
    organization manager (``organizations:manage``), may do so."""
    incident = g.incident
    data = json_body()
    kind, record, error = _load_record(incident, data)
    if error:
        return error
    conflict = precondition(record)
    if conflict:
        return conflict, conflict.status_code

    user = get_current_user()
    previous_by, previous_at = record.provenance_verified_by, record.provenance_verified_at
    prov.unverify(record, user, may_override=check_permission(user, 'organizations:manage'))
    record_changes({'provenance_verified_at': previous_at, 'provenance_verified_by': previous_by},
                   {'provenance_verified_at': None, 'provenance_verified_by': None},
                   record_type=kind, record_id=str(record.id))
    conflict = commit_or_conflict(record)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, prov.RECORD_KINDS[kind][2], 'updated', obj=record)
    return set_etag(jsonify(record.to_dict()), record), 200


@api_bp.route('/incidents/<uuid:incident_id>/provenance/normalize-preview', methods=['POST'])
@jwt_required()
@limited('normalize_preview')
@require_incident_access('timeline:read')
def normalize_preview(incident_id):
    """Preview the UTC value for a raw timestamp (read-only; nothing stored).

    Body ``{raw_timestamp, source_timezone?, host_id?, fold?}`` ->
    ``{utc, skew_applied, timezone_used, offset_seconds}``. With ``host_id``
    the host's clock skew and default time zone apply.
    """
    incident = g.incident
    data = json_body()
    host = None
    if data.get('host_id'):
        try:
            host_id = uuid.UUID(str(data['host_id']))
        except ValueError:
            return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
        host = CompromisedHost.query.filter_by(id=host_id, incident_id=incident.id).first()
        if not host:
            return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
    cleaned = prov.validate({k: data[k] for k in ('source_timezone', 'fold', 'raw_timestamp') if k in data})
    if not cleaned.get('raw_timestamp'):
        return jsonify({'error': 'bad_request', 'message': 'raw_timestamp is required'}), 400
    return jsonify(prov.preview(cleaned['raw_timestamp'], cleaned.get('source_timezone'), host,
                                cleaned.get('fold'))), 200
