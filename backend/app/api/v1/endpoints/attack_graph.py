"""Attack graph visualization endpoints"""
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from dateutil.parser import parse as parse_date
from app.api.v1 import api_bp
from app import db, socketio
from app.models import AttackGraphNode, AttackGraphEdge, CompromisedHost, CompromisedAccount, TimelineEvent
from app.models.ioc import NetworkIndicator
from app.middleware.rbac import require_incident_access, get_current_user
from app.middleware.audit import audit_log


@api_bp.route('/incidents/<uuid:incident_id>/attack-graph', methods=['GET'])
@jwt_required()
@require_incident_access('attack_graph:read')
def get_attack_graph(incident_id):
    """Get complete attack graph data with correlation counts."""
    from app.models.ioc import NetworkIndicator, HostBasedIndicator, MalwareTool
    incident = g.incident

    nodes = AttackGraphNode.query.filter_by(incident_id=incident.id).all()
    edges = AttackGraphEdge.query.filter_by(incident_id=incident.id).all()

    # Enrich nodes with correlation counts
    enriched_nodes = []
    for n in nodes:
        node_data = n.to_dict()
        if n.compromised_host_id:
            node_data['correlation'] = {
                'accounts': CompromisedAccount.query.filter_by(host_id=n.compromised_host_id).count(),
                'malware': MalwareTool.query.filter_by(host_id=n.compromised_host_id).count(),
                'network_iocs': NetworkIndicator.query.filter_by(host_id=n.compromised_host_id).count(),
                'host_iocs': HostBasedIndicator.query.filter_by(host_id=n.compromised_host_id).count(),
                'timeline_events': TimelineEvent.query.filter_by(host_id=n.compromised_host_id).count(),
            }
        enriched_nodes.append(node_data)

    # Format for Cytoscape.js (backwards compat)
    cytoscape_data = {
        'nodes': [n.to_dict()['cytoscape'] for n in nodes],
        'edges': [e.to_dict()['cytoscape'] for e in edges]
    }

    return jsonify({
        'nodes': enriched_nodes,
        'edges': [e.to_dict() for e in edges],
        'cytoscape': cytoscape_data
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/attack-graph/auto-generate', methods=['POST'])
@jwt_required()
@require_incident_access('attack_graph:create')
@audit_log('data_modification', 'create', 'attack_graph_auto')
def auto_generate_attack_graph(incident_id):
    """
    Auto-generate attack graph from compromised hosts and timeline events.
    Delegates to GraphAutomationService for all generation logic.
    """
    from app.services.graph_automation_service import GraphAutomationService

    user = get_current_user()
    incident = g.incident

    nodes_created, edges_created = GraphAutomationService.auto_generate(incident, user.id)

    if not nodes_created and not edges_created:
        return jsonify({
            'message': 'No compromised hosts found to generate graph',
            'nodes': [],
            'edges': []
        }), 200

    return jsonify({
        'message': f'Generated {len(nodes_created)} nodes and {len(edges_created)} edges',
        'nodes': [n.to_dict() for n in nodes_created],
        'edges': [e.to_dict() for e in edges_created]
    }), 201


# =============================================================================
# Nodes
# =============================================================================

@api_bp.route('/incidents/<uuid:incident_id>/attack-graph/nodes', methods=['GET'])
@jwt_required()
@require_incident_access('attack_graph:read')
def list_graph_nodes(incident_id):
    """List attack graph nodes."""
    incident = g.incident

    node_type = request.args.get('node_type')
    query = AttackGraphNode.query.filter_by(incident_id=incident.id)

    if node_type:
        query = query.filter(AttackGraphNode.node_type == node_type)

    nodes = query.all()

    return jsonify({
        'items': [n.to_dict() for n in nodes]
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/attack-graph/nodes', methods=['POST'])
@jwt_required()
@require_incident_access('attack_graph:create')
@audit_log('data_modification', 'create', 'attack_graph_node')
def create_graph_node(incident_id):
    """Create an attack graph node."""
    user = get_current_user()
    incident = g.incident
    data = request.get_json()

    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400

    node_type = data.get('node_type', '').strip()
    if node_type not in AttackGraphNode.NODE_TYPES:
        return jsonify({'error': 'bad_request', 'message': 'Invalid node_type'}), 400

    label = data.get('label', '').strip()
    if not label:
        return jsonify({'error': 'bad_request', 'message': 'label is required'}), 400

    node = AttackGraphNode(
        incident_id=incident.id,
        node_type=node_type,
        label=label,
        compromised_host_id=data.get('compromised_host_id'),
        compromised_account_id=data.get('compromised_account_id'),
        position_x=data.get('position_x', 0),
        position_y=data.get('position_y', 0),
        is_initial_access=data.get('is_initial_access', False),
        is_objective=data.get('is_objective', False),
        extra_data=data.get('extra_data', {}),
        created_by=user.id
    )

    db.session.add(node)
    db.session.commit()

    socketio.emit('graph_node_added', node.to_dict(), room=f'incident_{incident_id}')

    return jsonify(node.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/attack-graph/nodes/<uuid:node_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('attack_graph:update')
@audit_log('data_modification', 'update', 'attack_graph_node')
def update_graph_node(incident_id, node_id):
    """Update an attack graph node."""
    incident = g.incident
    data = request.get_json()

    node = AttackGraphNode.query.filter_by(id=node_id, incident_id=incident.id).first()
    if not node:
        return jsonify({'error': 'not_found', 'message': 'Node not found'}), 404

    for field in ['node_type', 'label', 'compromised_host_id', 'compromised_account_id',
                  'position_x', 'position_y', 'is_initial_access', 'is_objective', 'extra_data']:
        if field in data:
            if field == 'node_type' and data[field] not in AttackGraphNode.NODE_TYPES:
                return jsonify({'error': 'bad_request', 'message': 'Invalid node_type'}), 400
            setattr(node, field, data[field])

    db.session.commit()

    socketio.emit('graph_node_updated', node.to_dict(), room=f'incident_{incident_id}')

    return jsonify(node.to_dict()), 200


@api_bp.route('/incidents/<uuid:incident_id>/attack-graph/nodes/<uuid:node_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('attack_graph:delete')
@audit_log('data_modification', 'delete', 'attack_graph_node')
def delete_graph_node(incident_id, node_id):
    """Delete an attack graph node."""
    incident = g.incident

    node = AttackGraphNode.query.filter_by(id=node_id, incident_id=incident.id).first()
    if not node:
        return jsonify({'error': 'not_found', 'message': 'Node not found'}), 404

    db.session.delete(node)
    db.session.commit()

    socketio.emit('graph_node_deleted', {'id': str(node_id)}, room=f'incident_{incident_id}')

    return jsonify({'message': 'Node deleted'}), 200


# =============================================================================
# Edges
# =============================================================================

@api_bp.route('/incidents/<uuid:incident_id>/attack-graph/edges', methods=['GET'])
@jwt_required()
@require_incident_access('attack_graph:read')
def list_graph_edges(incident_id):
    """List attack graph edges."""
    incident = g.incident

    edge_type = request.args.get('edge_type')
    query = AttackGraphEdge.query.filter_by(incident_id=incident.id)

    if edge_type:
        query = query.filter(AttackGraphEdge.edge_type == edge_type)

    edges = query.all()

    return jsonify({
        'items': [e.to_dict() for e in edges]
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/attack-graph/edges', methods=['POST'])
@jwt_required()
@require_incident_access('attack_graph:create')
@audit_log('data_modification', 'create', 'attack_graph_edge')
def create_graph_edge(incident_id):
    """Create an attack graph edge."""
    user = get_current_user()
    incident = g.incident
    data = request.get_json()

    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400

    source_node_id = data.get('source_node_id')
    target_node_id = data.get('target_node_id')
    if not source_node_id or not target_node_id:
        return jsonify({'error': 'bad_request', 'message': 'source_node_id and target_node_id are required'}), 400

    # Verify nodes exist
    source = AttackGraphNode.query.filter_by(id=source_node_id, incident_id=incident.id).first()
    target = AttackGraphNode.query.filter_by(id=target_node_id, incident_id=incident.id).first()
    if not source or not target:
        return jsonify({'error': 'not_found', 'message': 'Source or target node not found'}), 404

    edge_type = data.get('edge_type', '').strip()
    if edge_type not in AttackGraphEdge.EDGE_TYPES:
        return jsonify({'error': 'bad_request', 'message': 'Invalid edge_type'}), 400

    edge = AttackGraphEdge(
        incident_id=incident.id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        edge_type=edge_type,
        label=data.get('label'),
        mitre_tactic=data.get('mitre_tactic'),
        mitre_technique=data.get('mitre_technique'),
        timestamp=parse_date(data['timestamp']) if data.get('timestamp') else None,
        description=data.get('description'),
        extra_data=data.get('extra_data', {}),
        created_by=user.id
    )

    # If a timeline_event_id is provided, enrich the edge with event details
    timeline_event_id = data.get('timeline_event_id')
    if timeline_event_id:
        event = TimelineEvent.query.filter_by(id=timeline_event_id, incident_id=incident.id).first()
        if event:
            edge_extra = edge.extra_data or {}
            edge_extra['timeline_event_id'] = str(event.id)
            edge_extra['timeline_event_activity'] = event.activity[:200] if event.activity else None
            edge_extra['timeline_event_timestamp'] = event.timestamp.isoformat() if event.timestamp else None
            edge.extra_data = edge_extra
            if not edge.mitre_tactic and event.mitre_tactic:
                edge.mitre_tactic = event.mitre_tactic
            if not edge.mitre_technique and event.mitre_technique:
                edge.mitre_technique = event.mitre_technique
            if not edge.timestamp and event.timestamp:
                edge.timestamp = event.timestamp

    db.session.add(edge)
    db.session.commit()

    socketio.emit('graph_edge_added', edge.to_dict(), room=f'incident_{incident_id}')

    return jsonify(edge.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/attack-graph/edges/<uuid:edge_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('attack_graph:update')
@audit_log('data_modification', 'update', 'attack_graph_edge')
def update_graph_edge(incident_id, edge_id):
    """Update an attack graph edge."""
    incident = g.incident
    data = request.get_json()

    edge = AttackGraphEdge.query.filter_by(id=edge_id, incident_id=incident.id).first()
    if not edge:
        return jsonify({'error': 'not_found', 'message': 'Edge not found'}), 404

    for field in ['edge_type', 'label', 'mitre_tactic', 'mitre_technique', 'description', 'extra_data']:
        if field in data:
            if field == 'edge_type' and data[field] not in AttackGraphEdge.EDGE_TYPES:
                return jsonify({'error': 'bad_request', 'message': 'Invalid edge_type'}), 400
            setattr(edge, field, data[field])

    if 'timestamp' in data:
        edge.timestamp = parse_date(data['timestamp']) if data['timestamp'] else None

    db.session.commit()

    socketio.emit('graph_edge_updated', edge.to_dict(), room=f'incident_{incident_id}')

    return jsonify(edge.to_dict()), 200


@api_bp.route('/incidents/<uuid:incident_id>/attack-graph/edges/<uuid:edge_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('attack_graph:delete')
@audit_log('data_modification', 'delete', 'attack_graph_edge')
def delete_graph_edge(incident_id, edge_id):
    """Delete an attack graph edge."""
    incident = g.incident

    edge = AttackGraphEdge.query.filter_by(id=edge_id, incident_id=incident.id).first()
    if not edge:
        return jsonify({'error': 'not_found', 'message': 'Edge not found'}), 404

    db.session.delete(edge)
    db.session.commit()

    socketio.emit('graph_edge_deleted', {'id': str(edge_id)}, room=f'incident_{incident_id}')

    return jsonify({'message': 'Edge deleted'}), 200


# =============================================================================
# Node/Edge Types
# =============================================================================

@api_bp.route('/attack-graph/node-types', methods=['GET'])
@jwt_required()
def list_node_types():
    """List available node types."""
    return jsonify({'node_types': AttackGraphNode.NODE_TYPES}), 200


@api_bp.route('/attack-graph/edge-types', methods=['GET'])
@jwt_required()
def list_edge_types():
    """List available edge types."""
    return jsonify({'edge_types': AttackGraphEdge.EDGE_TYPES}), 200
