"""Timeline event endpoints"""
from datetime import datetime
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from dateutil.parser import parse as parse_date
from app.api.v1 import api_bp
from app import db, socketio
from app.models import TimelineEvent, CompromisedHost, HostBasedIndicator
from app.middleware.rbac import require_permission, require_incident_access, get_current_user
from app.middleware.audit import audit_log
from app.services.graph_automation_service import GraphAutomationService


@api_bp.route('/incidents/<uuid:incident_id>/timeline', methods=['GET'])
@jwt_required()
@require_incident_access('timeline:read')
def list_timeline_events(incident_id):
    """List timeline events for an incident."""
    incident = g.incident
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    query = TimelineEvent.query.filter_by(incident_id=incident.id)

    # Filters
    phase = request.args.get('phase', type=int)
    if phase:
        query = query.filter(TimelineEvent.phase == phase)

    hostname = request.args.get('hostname')
    if hostname:
        query = query.filter(TimelineEvent.hostname.ilike(f'%{hostname}%'))

    host_id = request.args.get('host_id')
    if host_id:
        query = query.filter(TimelineEvent.host_id == host_id)

    mitre_tactic = request.args.get('mitre_tactic')
    if mitre_tactic:
        query = query.filter(TimelineEvent.mitre_tactic == mitre_tactic)

    start_date = request.args.get('start_date')
    if start_date:
        query = query.filter(TimelineEvent.timestamp >= parse_date(start_date))

    end_date = request.args.get('end_date')
    if end_date:
        query = query.filter(TimelineEvent.timestamp <= parse_date(end_date))

    key_only = request.args.get('key_only')
    if key_only and key_only.lower() == 'true':
        query = query.filter(TimelineEvent.is_key_event == True)

    ioc_only = request.args.get('ioc_only')
    if ioc_only and ioc_only.lower() == 'true':
        query = query.filter(TimelineEvent.is_ioc == True)

    pagination = query.order_by(TimelineEvent.timestamp.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [e.to_dict() for e in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/timeline', methods=['POST'])
@jwt_required()
@require_incident_access('timeline:create')
@audit_log('data_modification', 'create', 'timeline_event')
def create_timeline_event(incident_id):
    """Add a timeline event."""
    user = get_current_user()
    incident = g.incident
    data = request.get_json()

    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400

    timestamp = data.get('timestamp')
    if not timestamp:
        return jsonify({'error': 'bad_request', 'message': 'timestamp is required'}), 400

    activity = data.get('activity', '').strip()
    if not activity:
        return jsonify({'error': 'bad_request', 'message': 'activity is required'}), 400

    # Validate MITRE tactic if provided
    mitre_tactic = data.get('mitre_tactic')
    if mitre_tactic and mitre_tactic not in TimelineEvent.MITRE_TACTICS:
        return jsonify({'error': 'bad_request', 'message': 'Invalid MITRE tactic'}), 400

    # Validate MITRE technique if provided
    mitre_technique = data.get('mitre_technique')
    if mitre_technique and mitre_tactic:
        valid_techniques = [t[0] for t in TimelineEvent.MITRE_TECHNIQUES.get(mitre_tactic, [])]
        if mitre_technique not in valid_techniques:
            return jsonify({'error': 'bad_request', 'message': 'Invalid MITRE technique for this tactic'}), 400

    # Validate host_id if provided
    host_id = data.get('host_id')
    hostname = data.get('hostname')
    if host_id:
        host = CompromisedHost.query.filter_by(id=host_id, incident_id=incident.id).first()
        if not host:
            return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
        hostname = host.hostname  # Auto-fill hostname from host

    event = TimelineEvent(
        incident_id=incident.id,
        timestamp=parse_date(timestamp) if isinstance(timestamp, str) else timestamp,
        host_id=host_id,
        hostname=hostname,
        activity=activity,
        source=data.get('source'),
        mitre_tactic=mitre_tactic,
        mitre_technique=mitre_technique,
        phase=data.get('phase'),
        is_key_event=data.get('is_key_event', False),
        is_ioc=data.get('is_ioc', False),
        extra_data=data.get('extra_data', {}),
        created_by=user.id
    )

    db.session.add(event)
    db.session.commit()

    # Auto-update Attack Graph
    try:
        GraphAutomationService.process_event_for_graph(event)
    except Exception as e:
        # Don't fail the request if graph update fails, just log it
        print(f"Error updating attack graph: {e}")

    # Broadcast to incident room
    socketio.emit('timeline_event_added', event.to_dict(), room=f'incident_{incident_id}')

    return jsonify(event.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/timeline/<uuid:event_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('timeline:update')
@audit_log('data_modification', 'update', 'timeline_event')
def update_timeline_event(incident_id, event_id):
    """Update a timeline event."""
    incident = g.incident
    data = request.get_json()

    event = TimelineEvent.query.filter_by(id=event_id, incident_id=incident.id).first()
    if not event:
        return jsonify({'error': 'not_found', 'message': 'Timeline event not found'}), 404

    # Update fields
    if 'timestamp' in data:
        event.timestamp = parse_date(data['timestamp']) if isinstance(data['timestamp'], str) else data['timestamp']
    if 'host_id' in data:
        if data['host_id']:
            host = CompromisedHost.query.filter_by(id=data['host_id'], incident_id=incident.id).first()
            if not host:
                return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
            event.host_id = data['host_id']
            event.hostname = host.hostname
        else:
            event.host_id = None
    if 'hostname' in data:
        event.hostname = data['hostname']
    if 'activity' in data:
        event.activity = data['activity']
    if 'source' in data:
        event.source = data['source']
    if 'mitre_tactic' in data:
        if data['mitre_tactic'] and data['mitre_tactic'] not in TimelineEvent.MITRE_TACTICS:
            return jsonify({'error': 'bad_request', 'message': 'Invalid MITRE tactic'}), 400
        event.mitre_tactic = data['mitre_tactic']
    if 'mitre_technique' in data:
        event.mitre_technique = data['mitre_technique']
    if 'phase' in data:
        event.phase = data['phase']
    if 'is_key_event' in data:
        event.is_key_event = data['is_key_event']
    if 'is_ioc' in data:
        event.is_ioc = data['is_ioc']
    if 'extra_data' in data:
        event.extra_data = data['extra_data']

    db.session.commit()

    # Broadcast update
    socketio.emit('timeline_event_updated', event.to_dict(), room=f'incident_{incident_id}')

    return jsonify(event.to_dict()), 200


@api_bp.route('/incidents/<uuid:incident_id>/timeline/<uuid:event_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('timeline:delete')
@audit_log('data_modification', 'delete', 'timeline_event')
def delete_timeline_event(incident_id, event_id):
    """Delete a timeline event."""
    incident = g.incident

    event = TimelineEvent.query.filter_by(id=event_id, incident_id=incident.id).first()
    if not event:
        return jsonify({'error': 'not_found', 'message': 'Timeline event not found'}), 404

    db.session.delete(event)
    db.session.commit()

    # Broadcast deletion
    socketio.emit('timeline_event_deleted', {'id': str(event_id)}, room=f'incident_{incident_id}')

    return jsonify({'message': 'Timeline event deleted'}), 200


@api_bp.route('/incidents/<uuid:incident_id>/timeline/<uuid:event_id>/mark-as-ioc', methods=['POST'])
@jwt_required()
@require_incident_access('timeline:update')
@audit_log('data_modification', 'create', 'host_based_indicator')
def mark_event_as_ioc(incident_id, event_id):
    """Mark a timeline event as an IOC and create a HostBasedIndicator."""
    user = get_current_user()
    incident = g.incident
    data = request.get_json() or {}

    event = TimelineEvent.query.filter_by(id=event_id, incident_id=incident.id).first()
    if not event:
        return jsonify({'error': 'not_found', 'message': 'Timeline event not found'}), 404

    artifact_type = data.get('artifact_type', 'other')
    if artifact_type not in HostBasedIndicator.ARTIFACT_TYPES:
        return jsonify({'error': 'bad_request', 'message': 'Invalid artifact_type'}), 400

    # Mark event as IOC
    event.is_ioc = True

    # Create HostBasedIndicator linked to this event
    ioc = HostBasedIndicator(
        incident_id=incident.id,
        host_id=event.host_id,
        timeline_event_id=event.id,
        artifact_type=artifact_type,
        datetime=event.timestamp,
        artifact_value=event.activity,
        host=event.hostname,
        notes=data.get('notes', ''),
        is_malicious=data.get('is_malicious', True),
        created_by=user.id
    )

    db.session.add(ioc)
    db.session.commit()

    return jsonify({
        'message': 'Event marked as IOC',
        'ioc': ioc.to_dict(),
        'event': event.to_dict()
    }), 201


@api_bp.route('/mitre/tactics', methods=['GET'])
@jwt_required()
def list_mitre_tactics():
    """List available MITRE ATT&CK tactics."""
    return jsonify({'tactics': TimelineEvent.MITRE_TACTICS}), 200


@api_bp.route('/mitre/techniques', methods=['GET'])
@jwt_required()
def list_mitre_techniques():
    """List available MITRE ATT&CK techniques, optionally filtered by tactic."""
    tactic = request.args.get('tactic')
    
    if tactic:
        if tactic not in TimelineEvent.MITRE_TACTICS:
            return jsonify({'error': 'bad_request', 'message': 'Invalid tactic'}), 400
        techniques = TimelineEvent.MITRE_TECHNIQUES.get(tactic, [])
        return jsonify({
            'tactic': tactic,
            'techniques': [{'id': t[0], 'name': t[1]} for t in techniques]
        }), 200
    
    # Return all techniques organized by tactic
    all_techniques = {}
    for tactic, techniques in TimelineEvent.MITRE_TECHNIQUES.items():
        all_techniques[tactic] = [{'id': t[0], 'name': t[1]} for t in techniques]
    
    return jsonify({'techniques': all_techniques}), 200
