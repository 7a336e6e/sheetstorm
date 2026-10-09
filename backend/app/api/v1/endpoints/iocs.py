"""Indicator of Compromise (IOC) endpoints"""
from flask import jsonify, request, g, current_app
from flask_jwt_extended import jwt_required
from app.utils.validation import parse_datetime
from app.api.v1 import api_bp
from app import db, socketio
from app.models import NetworkIndicator, HostBasedIndicator, MalwareTool, CompromisedHost, TimelineEvent
from app.middleware.rbac import require_incident_access, get_current_user
from app.middleware.audit import audit_log
from app.utils.pagination import list_response
from app.services import realtime
from app.utils.concurrency import commit_or_conflict, precondition, set_etag


# =============================================================================
# Network Indicators
# =============================================================================

NETWORK_IOC_SORTABLE = {
    'timestamp': NetworkIndicator.timestamp,
    'dns_ip': NetworkIndicator.dns_ip,
    'protocol': NetworkIndicator.protocol,
    'port': NetworkIndicator.port,
    'direction': NetworkIndicator.direction,
    'created_at': NetworkIndicator.created_at,
}


@api_bp.route('/incidents/<uuid:incident_id>/network-iocs', methods=['GET'])
@jwt_required()
@require_incident_access('network_iocs:read')
def list_network_iocs(incident_id):
    """List network indicators (utils/pagination.py contract; q/search over
    dns_ip, source/destination host, description; filters protocol,
    direction, host_id)."""
    incident = g.incident
    query = NetworkIndicator.query.filter_by(incident_id=incident.id)
    return jsonify(list_response(
        query, sortable=NETWORK_IOC_SORTABLE, default_sort='-timestamp', id_col=NetworkIndicator.id,
        filters={
            'protocol': (NetworkIndicator.protocol, 'eq'),
            'direction': (NetworkIndicator.direction, 'eq'),
            'host_id': (NetworkIndicator.host_id, 'uuid'),
        },
        search_columns=(NetworkIndicator.dns_ip, NetworkIndicator.source_host,
                        NetworkIndicator.destination_host, NetworkIndicator.description),
        serialize=lambda i: i.to_dict(),
    )), 200


@api_bp.route('/incidents/<uuid:incident_id>/network-iocs', methods=['POST'])
@jwt_required()
@require_incident_access('network_iocs:create')
@audit_log('data_modification', 'create', 'network_indicator')
def create_network_ioc(incident_id):
    """Add a network indicator."""
    user = get_current_user()
    incident = g.incident
    data = request.get_json()

    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400

    dns_ip = data.get('dns_ip', '').strip()
    if not dns_ip:
        return jsonify({'error': 'bad_request', 'message': 'dns_ip is required'}), 400

    # Validate host_id if provided
    host_id = data.get('host_id')
    source_host = data.get('source_host')
    source_host_id = data.get('source_host_id')
    destination_host_id = data.get('destination_host_id')
    if host_id:
        host = CompromisedHost.query.filter_by(id=host_id, incident_id=incident.id).first()
        if not host:
            return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
        source_host = host.hostname  # Auto-fill source_host from host

    # Validate source_host_id if provided
    if source_host_id:
        src = CompromisedHost.query.filter_by(id=source_host_id, incident_id=incident.id).first()
        if not src:
            return jsonify({'error': 'bad_request', 'message': 'Invalid source_host_id'}), 400
        if not source_host:
            source_host = src.hostname

    # Validate destination_host_id if provided
    if destination_host_id:
        dst = CompromisedHost.query.filter_by(id=destination_host_id, incident_id=incident.id).first()
        if not dst:
            return jsonify({'error': 'bad_request', 'message': 'Invalid destination_host_id'}), 400

    # Validate timeline_event_id if provided
    timeline_event_id = data.get('timeline_event_id')
    if timeline_event_id:
        event = TimelineEvent.query.filter_by(id=timeline_event_id, incident_id=incident.id).first()
        if not event:
            return jsonify({'error': 'bad_request', 'message': 'Invalid timeline_event_id'}), 400

    ioc = NetworkIndicator(
        incident_id=incident.id,
        host_id=host_id,
        source_host_id=source_host_id,
        destination_host_id=destination_host_id,
        timeline_event_id=timeline_event_id,
        timestamp=parse_datetime(data.get('timestamp'), 'timestamp'),
        protocol=data.get('protocol'),
        port=data.get('port'),
        dns_ip=dns_ip,
        source_host=source_host,
        destination_host=data.get('destination_host'),
        direction=data.get('direction'),
        description=data.get('description'),
        is_malicious=data.get('is_malicious', True),
        threat_intel_source=data.get('threat_intel_source'),
        extra_data=data.get('extra_data', {}),
        created_by=user.id
    )

    db.session.add(ioc)

    # Auto-create attack graph node for the IOC if requested
    node = None
    if data.get('add_to_attack_graph', False):
        from app.models import AttackGraphNode
        node = AttackGraphNode(
            incident_id=incident.id,
            node_type='ip_address',
            label=dns_ip,
            extra_data={'ioc_id': str(ioc.id), 'direction': data.get('direction'), 'protocol': data.get('protocol'), 'description': data.get('description', '')},
            created_by=user.id,
        )
        db.session.add(node)

    db.session.commit()
    realtime.emit_change(incident.id, 'network_ioc', 'created', obj=ioc)
    if node is not None:
        realtime.emit_change(incident.id, 'graph_node', 'created', obj=node)

    # IR-augmenting automation: enrich the indicator on creation. Opt-in (org
    # setting `auto_enrich_iocs`, else the IOC_AUTO_ENRICH global default —
    # off) because it sends indicator values to third-party services; a
    # request may still opt out with auto_enrich=false. Runs in a background
    # task so slow/failing providers never block or fail the request.
    # TLP egress block: never for restricted incidents / values (egress_policy).
    if (dns_ip and data.get('auto_enrich', True) is not False and _auto_enrich_enabled(user)
            and _auto_enrich_tlp_allowed(incident, dns_ip.strip())):
        socketio.start_background_task(
            _enrich_network_ioc, current_app._get_current_object(), ioc.id,
            dns_ip.strip(), str(user.organization_id),
        )

    return jsonify(ioc.to_dict()), 201


def _auto_enrich_enabled(user):
    """Org setting `auto_enrich_iocs` overrides the IOC_AUTO_ENRICH default."""
    settings = (user.organization.settings if user.organization else None) or {}
    if 'auto_enrich_iocs' in settings:
        return bool(settings['auto_enrich_iocs'])
    return bool(current_app.config.get('IOC_AUTO_ENRICH', False))


def _auto_enrich_tlp_allowed(incident, value):
    """Auto-enrichment is skipped for TLP-restricted incidents and values."""
    from app.services.egress_policy import enrichment_allowed, filter_values_for_enrichment
    if not enrichment_allowed(incident):
        return False
    allowed, _ = filter_values_for_enrichment(incident.organization_id, [value])
    return bool(allowed)


def _enrich_network_ioc(app, ioc_id, value, organization_id):
    """Background enrichment of one network IOC (never raises)."""
    import re as _re
    with app.app_context():
        try:
            from app.services.enrichment_service import EnrichmentService
            ioc_type = 'ip-src' if _re.match(r'^\d{1,3}(\.\d{1,3}){3}$', value) else 'domain'
            enrichment = EnrichmentService.auto_enrich_ioc(ioc_type, value, organization_id)
            if enrichment:
                ioc = db.session.get(NetworkIndicator, ioc_id)
                if ioc:
                    ed = dict(ioc.extra_data or {})
                    ed['enrichment'] = enrichment
                    ioc.extra_data = ed
                    db.session.commit()
                    realtime.emit_change(ioc.incident_id, 'network_ioc', 'updated', obj=ioc)
        except Exception:
            db.session.rollback()
            app.logger.warning('IOC auto-enrichment failed for %s', ioc_id, exc_info=True)
        finally:
            db.session.remove()


@api_bp.route('/incidents/<uuid:incident_id>/network-iocs/<uuid:ioc_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('network_iocs:update')
@audit_log('data_modification', 'update', 'network_indicator')
def update_network_ioc(incident_id, ioc_id):
    """Update a network indicator."""
    incident = g.incident
    data = request.get_json()

    ioc = NetworkIndicator.query.filter_by(id=ioc_id, incident_id=incident.id).first()
    if not ioc:
        return jsonify({'error': 'not_found', 'message': 'Network indicator not found'}), 404
    conflict = precondition(ioc)
    if conflict:
        return conflict, conflict.status_code

    for field in ['protocol', 'port', 'dns_ip', 'source_host', 'destination_host',
                  'direction', 'description', 'is_malicious', 'threat_intel_source', 'extra_data']:
        if field in data:
            setattr(ioc, field, data[field])

    if 'timestamp' in data:
        ioc.timestamp = parse_datetime(data['timestamp'], 'timestamp')

    # Handle host_id
    if 'host_id' in data:
        if data['host_id']:
            host = CompromisedHost.query.filter_by(id=data['host_id'], incident_id=incident.id).first()
            if not host:
                return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
            ioc.host_id = data['host_id']
            ioc.source_host = host.hostname
        else:
            ioc.host_id = None

    # Handle source_host_id
    if 'source_host_id' in data:
        if data['source_host_id']:
            src = CompromisedHost.query.filter_by(id=data['source_host_id'], incident_id=incident.id).first()
            if not src:
                return jsonify({'error': 'bad_request', 'message': 'Invalid source_host_id'}), 400
            ioc.source_host_id = data['source_host_id']
        else:
            ioc.source_host_id = None

    # Handle destination_host_id
    if 'destination_host_id' in data:
        if data['destination_host_id']:
            dst = CompromisedHost.query.filter_by(id=data['destination_host_id'], incident_id=incident.id).first()
            if not dst:
                return jsonify({'error': 'bad_request', 'message': 'Invalid destination_host_id'}), 400
            ioc.destination_host_id = data['destination_host_id']
        else:
            ioc.destination_host_id = None

    conflict = commit_or_conflict(ioc)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'network_ioc', 'updated', obj=ioc)

    return set_etag(jsonify(ioc.to_dict()), ioc), 200


@api_bp.route('/incidents/<uuid:incident_id>/network-iocs/<uuid:ioc_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('network_iocs:delete')
@audit_log('data_modification', 'delete', 'network_indicator')
def delete_network_ioc(incident_id, ioc_id):
    """Delete a network indicator."""
    incident = g.incident

    ioc = NetworkIndicator.query.filter_by(id=ioc_id, incident_id=incident.id).first()
    if not ioc:
        return jsonify({'error': 'not_found', 'message': 'Network indicator not found'}), 404
    conflict = precondition(ioc)
    if conflict:
        return conflict, conflict.status_code

    db.session.delete(ioc)
    conflict = commit_or_conflict(ioc)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'network_ioc', 'deleted', id=ioc_id)

    return jsonify({'message': 'Network indicator deleted'}), 200


# =============================================================================
# Host-Based Indicators
# =============================================================================

HOST_IOC_SORTABLE = {
    'datetime': HostBasedIndicator.datetime,
    'artifact_type': HostBasedIndicator.artifact_type,
    'host': HostBasedIndicator.host,
    'created_at': HostBasedIndicator.created_at,
}


@api_bp.route('/incidents/<uuid:incident_id>/host-iocs', methods=['GET'])
@jwt_required()
@require_incident_access('host_iocs:read')
def list_host_iocs(incident_id):
    """List host-based indicators (utils/pagination.py contract; q/search
    over value, host, notes; filters artifact_type, host_id, host,
    from_timeline)."""
    incident = g.incident
    query = HostBasedIndicator.query.filter_by(incident_id=incident.id)
    return jsonify(list_response(
        query, sortable=HOST_IOC_SORTABLE, default_sort='-datetime', id_col=HostBasedIndicator.id,
        filters={
            'artifact_type': (HostBasedIndicator.artifact_type, 'eq'),
            'host_id': (HostBasedIndicator.host_id, 'uuid'),
            'host': (HostBasedIndicator.host, 'ilike'),
            # Only those linked to timeline events
            'from_timeline': (HostBasedIndicator.timeline_event_id.isnot(None), 'flag'),
        },
        search_columns=(HostBasedIndicator.artifact_value, HostBasedIndicator.host, HostBasedIndicator.notes),
        serialize=lambda i: i.to_dict(),
    )), 200


@api_bp.route('/incidents/<uuid:incident_id>/host-iocs', methods=['POST'])
@jwt_required()
@require_incident_access('host_iocs:create')
@audit_log('data_modification', 'create', 'host_indicator')
def create_host_ioc(incident_id):
    """Add a host-based indicator."""
    user = get_current_user()
    incident = g.incident
    data = request.get_json()

    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400

    artifact_type = data.get('artifact_type', '').strip()
    if artifact_type not in HostBasedIndicator.ARTIFACT_TYPES:
        return jsonify({'error': 'bad_request', 'message': 'Invalid artifact_type'}), 400

    artifact_value = data.get('artifact_value', '').strip()
    if not artifact_value:
        return jsonify({'error': 'bad_request', 'message': 'artifact_value is required'}), 400

    # Validate host_id if provided
    host_id = data.get('host_id')
    host = data.get('host')
    if host_id:
        host_obj = CompromisedHost.query.filter_by(id=host_id, incident_id=incident.id).first()
        if not host_obj:
            return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
        host = host_obj.hostname  # Auto-fill host from host_id

    # Validate timeline_event_id if provided
    timeline_event_id = data.get('timeline_event_id')
    if timeline_event_id:
        event = TimelineEvent.query.filter_by(id=timeline_event_id, incident_id=incident.id).first()
        if not event:
            return jsonify({'error': 'bad_request', 'message': 'Invalid timeline_event_id'}), 400

    ioc = HostBasedIndicator(
        incident_id=incident.id,
        host_id=host_id,
        timeline_event_id=timeline_event_id,
        artifact_type=artifact_type,
        datetime=parse_datetime(data.get('datetime'), 'datetime'),
        artifact_value=artifact_value,
        host=host,
        notes=data.get('notes'),
        is_malicious=data.get('is_malicious', True),
        remediated=data.get('remediated', False),
        extra_data=data.get('extra_data', {}),
        created_by=user.id
    )

    db.session.add(ioc)
    db.session.commit()
    realtime.emit_change(incident.id, 'host_ioc', 'created', obj=ioc)

    return jsonify(ioc.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/host-iocs/<uuid:ioc_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('host_iocs:update')
@audit_log('data_modification', 'update', 'host_indicator')
def update_host_ioc(incident_id, ioc_id):
    """Update a host-based indicator."""
    incident = g.incident
    data = request.get_json()

    ioc = HostBasedIndicator.query.filter_by(id=ioc_id, incident_id=incident.id).first()
    if not ioc:
        return jsonify({'error': 'not_found', 'message': 'Host indicator not found'}), 404
    conflict = precondition(ioc)
    if conflict:
        return conflict, conflict.status_code

    for field in ['artifact_type', 'artifact_value', 'host', 'notes',
                  'is_malicious', 'remediated', 'extra_data']:
        if field in data:
            setattr(ioc, field, data[field])

    if 'datetime' in data:
        ioc.datetime = parse_datetime(data['datetime'], 'datetime')

    # Handle host_id
    if 'host_id' in data:
        if data['host_id']:
            host_obj = CompromisedHost.query.filter_by(id=data['host_id'], incident_id=incident.id).first()
            if not host_obj:
                return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
            ioc.host_id = data['host_id']
            ioc.host = host_obj.hostname
        else:
            ioc.host_id = None

    conflict = commit_or_conflict(ioc)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'host_ioc', 'updated', obj=ioc)

    return set_etag(jsonify(ioc.to_dict()), ioc), 200


@api_bp.route('/incidents/<uuid:incident_id>/host-iocs/<uuid:ioc_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('host_iocs:delete')
@audit_log('data_modification', 'delete', 'host_indicator')
def delete_host_ioc(incident_id, ioc_id):
    """Delete a host-based indicator."""
    incident = g.incident

    ioc = HostBasedIndicator.query.filter_by(id=ioc_id, incident_id=incident.id).first()
    if not ioc:
        return jsonify({'error': 'not_found', 'message': 'Host indicator not found'}), 404
    conflict = precondition(ioc)
    if conflict:
        return conflict, conflict.status_code

    db.session.delete(ioc)
    conflict = commit_or_conflict(ioc)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'host_ioc', 'deleted', id=ioc_id)

    return jsonify({'message': 'Host indicator deleted'}), 200


# =============================================================================
# Malware & Tools
# =============================================================================

MALWARE_SORTABLE = {
    'created_at': MalwareTool.created_at,
    'file_name': MalwareTool.file_name,
    'malware_family': MalwareTool.malware_family,
    'host': MalwareTool.host,
}


@api_bp.route('/incidents/<uuid:incident_id>/malware', methods=['GET'])
@jwt_required()
@require_incident_access('malware:read')
def list_malware(incident_id):
    """List malware and tools (utils/pagination.py contract; q/search over
    file name/path, hashes, family; filters is_tool, host_id)."""
    incident = g.incident
    query = MalwareTool.query.filter_by(incident_id=incident.id)
    return jsonify(list_response(
        query, sortable=MALWARE_SORTABLE, default_sort='-created_at', id_col=MalwareTool.id,
        filters={
            'is_tool': (MalwareTool.is_tool, 'bool'),
            'host_id': (MalwareTool.host_id, 'uuid'),
        },
        search_columns=(MalwareTool.file_name, MalwareTool.file_path, MalwareTool.sha256,
                        MalwareTool.md5, MalwareTool.malware_family),
        serialize=lambda m: m.to_dict(),
    )), 200


@api_bp.route('/incidents/<uuid:incident_id>/malware', methods=['POST'])
@jwt_required()
@require_incident_access('malware:create')
@audit_log('data_modification', 'create', 'malware')
def create_malware(incident_id):
    """Add a malware or tool entry."""
    user = get_current_user()
    incident = g.incident
    data = request.get_json()

    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400

    file_name = data.get('file_name', '').strip()
    if not file_name:
        return jsonify({'error': 'bad_request', 'message': 'file_name is required'}), 400

    # Validate host_id if provided
    host_id = data.get('host_id')
    host = data.get('host')
    if host_id:
        host_obj = CompromisedHost.query.filter_by(id=host_id, incident_id=incident.id).first()
        if not host_obj:
            return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
        host = host_obj.hostname  # Auto-fill host from host_id

    malware = MalwareTool(
        incident_id=incident.id,
        host_id=host_id,
        file_name=file_name,
        file_path=data.get('file_path'),
        md5=data.get('md5'),
        sha256=data.get('sha256'),
        sha512=data.get('sha512'),
        file_size=data.get('file_size'),
        creation_time=parse_datetime(data.get('creation_time'), 'creation_time'),
        modification_time=parse_datetime(data.get('modification_time'), 'modification_time'),
        access_time=parse_datetime(data.get('access_time'), 'access_time'),
        host=host,
        description=data.get('description'),
        malware_family=data.get('malware_family'),
        threat_actor=data.get('threat_actor'),
        is_tool=data.get('is_tool', False),
        sandbox_report_url=data.get('sandbox_report_url'),
        extra_data=data.get('extra_data', {}),
        created_by=user.id
    )

    db.session.add(malware)
    db.session.commit()
    realtime.emit_change(incident.id, 'malware', 'created', obj=malware)

    return jsonify(malware.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/malware/<uuid:malware_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('malware:update')
@audit_log('data_modification', 'update', 'malware')
def update_malware(incident_id, malware_id):
    """Update a malware entry."""
    incident = g.incident
    data = request.get_json()

    malware = MalwareTool.query.filter_by(id=malware_id, incident_id=incident.id).first()
    if not malware:
        return jsonify({'error': 'not_found', 'message': 'Malware entry not found'}), 404
    conflict = precondition(malware)
    if conflict:
        return conflict, conflict.status_code

    for field in ['file_name', 'file_path', 'md5', 'sha256', 'sha512', 'file_size',
                  'host', 'description', 'malware_family', 'threat_actor',
                  'is_tool', 'sandbox_report_url', 'extra_data']:
        if field in data:
            setattr(malware, field, data[field])

    for time_field in ['creation_time', 'modification_time', 'access_time']:
        if time_field in data:
            setattr(malware, time_field, parse_datetime(data[time_field], time_field))

    # Handle host_id
    if 'host_id' in data:
        if data['host_id']:
            host_obj = CompromisedHost.query.filter_by(id=data['host_id'], incident_id=incident.id).first()
            if not host_obj:
                return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
            malware.host_id = data['host_id']
            malware.host = host_obj.hostname
        else:
            malware.host_id = None

    conflict = commit_or_conflict(malware)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'malware', 'updated', obj=malware)

    return set_etag(jsonify(malware.to_dict()), malware), 200


@api_bp.route('/incidents/<uuid:incident_id>/malware/<uuid:malware_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('malware:delete')
@audit_log('data_modification', 'delete', 'malware')
def delete_malware(incident_id, malware_id):
    """Delete a malware entry."""
    incident = g.incident

    malware = MalwareTool.query.filter_by(id=malware_id, incident_id=incident.id).first()
    if not malware:
        return jsonify({'error': 'not_found', 'message': 'Malware entry not found'}), 404
    conflict = precondition(malware)
    if conflict:
        return conflict, conflict.status_code

    db.session.delete(malware)
    conflict = commit_or_conflict(malware)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'malware', 'deleted', id=malware_id)

    return jsonify({'message': 'Malware entry deleted'}), 200
