"""Indicator of Compromise (IOC) endpoints"""
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from dateutil.parser import parse as parse_date
from app.api.v1 import api_bp
from app import db, socketio
from app.models import NetworkIndicator, HostBasedIndicator, MalwareTool, CompromisedHost, TimelineEvent
from app.middleware.rbac import require_incident_access, get_current_user
from app.middleware.audit import audit_log


# =============================================================================
# Network Indicators
# =============================================================================

@api_bp.route('/incidents/<uuid:incident_id>/network-iocs', methods=['GET'])
@jwt_required()
@require_incident_access('network_iocs:read')
def list_network_iocs(incident_id):
    """List network indicators for an incident."""
    incident = g.incident
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    query = NetworkIndicator.query.filter_by(incident_id=incident.id)

    protocol = request.args.get('protocol')
    if protocol:
        query = query.filter(NetworkIndicator.protocol == protocol)

    host_id = request.args.get('host_id')
    if host_id:
        query = query.filter(NetworkIndicator.host_id == host_id)

    search = request.args.get('search')
    if search:
        query = query.filter(NetworkIndicator.dns_ip.ilike(f'%{search}%'))

    pagination = query.order_by(NetworkIndicator.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [i.to_dict() for i in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    }), 200


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
    if host_id:
        host = CompromisedHost.query.filter_by(id=host_id, incident_id=incident.id).first()
        if not host:
            return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
        source_host = host.hostname  # Auto-fill source_host from host

    # Validate timeline_event_id if provided
    timeline_event_id = data.get('timeline_event_id')
    if timeline_event_id:
        event = TimelineEvent.query.filter_by(id=timeline_event_id, incident_id=incident.id).first()
        if not event:
            return jsonify({'error': 'bad_request', 'message': 'Invalid timeline_event_id'}), 400

    ioc = NetworkIndicator(
        incident_id=incident.id,
        host_id=host_id,
        timeline_event_id=timeline_event_id,
        timestamp=parse_date(data['timestamp']) if data.get('timestamp') else None,
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
    db.session.commit()

    return jsonify(ioc.to_dict()), 201


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

    for field in ['protocol', 'port', 'dns_ip', 'source_host', 'destination_host',
                  'direction', 'description', 'is_malicious', 'threat_intel_source', 'extra_data']:
        if field in data:
            setattr(ioc, field, data[field])

    if 'timestamp' in data:
        ioc.timestamp = parse_date(data['timestamp']) if data['timestamp'] else None

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

    db.session.commit()

    return jsonify(ioc.to_dict()), 200


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

    db.session.delete(ioc)
    db.session.commit()

    return jsonify({'message': 'Network indicator deleted'}), 200


# =============================================================================
# Host-Based Indicators
# =============================================================================

@api_bp.route('/incidents/<uuid:incident_id>/host-iocs', methods=['GET'])
@jwt_required()
@require_incident_access('host_iocs:read')
def list_host_iocs(incident_id):
    """List host-based indicators for an incident."""
    incident = g.incident
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    query = HostBasedIndicator.query.filter_by(incident_id=incident.id)

    artifact_type = request.args.get('artifact_type')
    if artifact_type:
        query = query.filter(HostBasedIndicator.artifact_type == artifact_type)

    host_id = request.args.get('host_id')
    if host_id:
        query = query.filter(HostBasedIndicator.host_id == host_id)

    # Filter by those linked to timeline events
    from_timeline = request.args.get('from_timeline')
    if from_timeline and from_timeline.lower() == 'true':
        query = query.filter(HostBasedIndicator.timeline_event_id != None)

    host = request.args.get('host')
    if host:
        query = query.filter(HostBasedIndicator.host.ilike(f'%{host}%'))

    pagination = query.order_by(HostBasedIndicator.datetime.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [i.to_dict() for i in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    }), 200


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
        datetime=parse_date(data['datetime']) if data.get('datetime') else None,
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

    for field in ['artifact_type', 'artifact_value', 'host', 'notes',
                  'is_malicious', 'remediated', 'extra_data']:
        if field in data:
            setattr(ioc, field, data[field])

    if 'datetime' in data:
        ioc.datetime = parse_date(data['datetime']) if data['datetime'] else None

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

    db.session.commit()

    return jsonify(ioc.to_dict()), 200


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

    db.session.delete(ioc)
    db.session.commit()

    return jsonify({'message': 'Host indicator deleted'}), 200


# =============================================================================
# Malware & Tools
# =============================================================================

@api_bp.route('/incidents/<uuid:incident_id>/malware', methods=['GET'])
@jwt_required()
@require_incident_access('malware:read')
def list_malware(incident_id):
    """List malware and tools for an incident."""
    incident = g.incident
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    query = MalwareTool.query.filter_by(incident_id=incident.id)

    is_tool = request.args.get('is_tool')
    if is_tool is not None:
        query = query.filter(MalwareTool.is_tool == (is_tool.lower() == 'true'))

    host_id = request.args.get('host_id')
    if host_id:
        query = query.filter(MalwareTool.host_id == host_id)

    search = request.args.get('search')
    if search:
        query = query.filter(
            db.or_(
                MalwareTool.file_name.ilike(f'%{search}%'),
                MalwareTool.sha256.ilike(f'%{search}%'),
                MalwareTool.md5.ilike(f'%{search}%')
            )
        )

    pagination = query.order_by(MalwareTool.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [m.to_dict() for m in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    }), 200


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
        creation_time=parse_date(data['creation_time']) if data.get('creation_time') else None,
        modification_time=parse_date(data['modification_time']) if data.get('modification_time') else None,
        access_time=parse_date(data['access_time']) if data.get('access_time') else None,
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

    for field in ['file_name', 'file_path', 'md5', 'sha256', 'sha512', 'file_size',
                  'host', 'description', 'malware_family', 'threat_actor',
                  'is_tool', 'sandbox_report_url', 'extra_data']:
        if field in data:
            setattr(malware, field, data[field])

    for time_field in ['creation_time', 'modification_time', 'access_time']:
        if time_field in data:
            setattr(malware, time_field, parse_date(data[time_field]) if data[time_field] else None)

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

    db.session.commit()

    return jsonify(malware.to_dict()), 200


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

    db.session.delete(malware)
    db.session.commit()

    return jsonify({'message': 'Malware entry deleted'}), 200
