"""Incident management endpoints"""
from datetime import datetime, timezone
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db, socketio
from app.models import Incident, IncidentAssignment, IncidentTeam, User, TeamMember
from app.middleware.rbac import require_permission, require_incident_access, get_current_user
from app.middleware.audit import audit_log
from app.services.notification_service import notify_incident_created, notify_user_assigned
from app.services.import_service import ImportService



@api_bp.route('/incidents', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def list_incidents():
    """List incidents with filtering and pagination.
    
    Access rules:
    - Administrators/Managers: see all org incidents
    - Incident Responders/Analysts: see incidents assigned to their teams OR directly to them
    - Operators/Viewers: see only directly assigned incidents
    """
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = Incident.query.filter_by(organization_id=user.organization_id)

    # For Operators/Viewers, only show directly assigned incidents
    if user.has_role('Operator') or user.has_role('Viewer'):
        query = query.join(IncidentAssignment).filter(
            IncidentAssignment.user_id == user.id,
            IncidentAssignment.removed_at.is_(None)
        )
    # For Incident Responders/Analysts, show team-scoped + directly assigned
    elif not user.has_role('Administrator') and not user.has_role('Manager'):
        # Get user's team IDs
        user_team_ids = db.session.query(TeamMember.team_id).filter(
            TeamMember.user_id == user.id
        ).subquery()

        # Show incidents that are:
        # 1. Assigned to the user directly, OR
        # 2. Associated with one of the user's teams, OR
        # 3. Not associated with any team (org-wide incidents)
        has_assignment = db.session.query(IncidentAssignment.incident_id).filter(
            IncidentAssignment.user_id == user.id,
            IncidentAssignment.removed_at.is_(None)
        ).subquery()

        has_team = db.session.query(IncidentTeam.incident_id).filter(
            IncidentTeam.team_id.in_(db.session.query(user_team_ids))
        ).subquery()

        no_teams = ~db.session.query(IncidentTeam).filter(
            IncidentTeam.incident_id == Incident.id
        ).exists()

        query = query.filter(
            db.or_(
                Incident.id.in_(db.session.query(has_assignment)),
                Incident.id.in_(db.session.query(has_team)),
                no_teams
            )
        )

    # Filter by team_id if provided
    team_id = request.args.get('team_id')
    if team_id:
        query = query.join(IncidentTeam).filter(IncidentTeam.team_id == team_id)

    # Filters
    status = request.args.get('status')
    if status:
        query = query.filter(Incident.status == status)

    severity = request.args.get('severity')
    if severity:
        query = query.filter(Incident.severity == severity)

    phase = request.args.get('phase', type=int)
    if phase:
        query = query.filter(Incident.phase == phase)

    classification = request.args.get('classification')
    if classification:
        query = query.filter(Incident.classification == classification)

    # Search
    search = request.args.get('search')
    if search:
        query = query.filter(
            db.or_(
                Incident.title.ilike(f'%{search}%'),
                Incident.description.ilike(f'%{search}%')
            )
        )

    pagination = query.order_by(Incident.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [i.to_dict(include_counts=True) for i in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    }), 200


@api_bp.route('/incidents', methods=['POST'])
@jwt_required()
@require_permission('incidents:create')
@audit_log('data_modification', 'create', 'incident')
def create_incident():
    """Create a new incident."""
    user = get_current_user()
    try:
        from app.schemas.incident import IncidentCreate
        data = IncidentCreate(**request.get_json())
    except ValueError as e:
        return jsonify({'error': 'bad_request', 'message': str(e)}), 400

    incident = Incident(
        organization_id=user.organization_id,
        title=data.title,
        description=data.description,
        severity=data.severity,
        classification=data.classification,
        phase=1,  # Start in Preparation phase
        status='open',
        detected_at=data.detected_at or datetime.now(timezone.utc),
        created_by=user.id
    )

    # Assign lead responder if provided
    if data.lead_responder_id:
        lead = User.query.filter_by(id=data.lead_responder_id, organization_id=user.organization_id).first()
        if lead:
            incident.lead_responder_id = lead.id

    db.session.add(incident)
    db.session.commit()

    # Associate teams with incident
    team_ids = request.get_json().get('team_ids', [])
    if team_ids:
        from app.models import Team
        for tid in team_ids:
            team = Team.query.filter_by(id=tid, organization_id=user.organization_id).first()
            if team:
                it = IncidentTeam(incident_id=incident.id, team_id=team.id)
                db.session.add(it)

    # Assign creator to incident
    assignment = IncidentAssignment(
        incident_id=incident.id,
        user_id=user.id,
        role='Creator',
        assigned_by=user.id,
        assigned_at=datetime.now(timezone.utc)
    )
    db.session.add(assignment)
    db.session.commit()

    # Send notifications
    notify_incident_created(incident)

    return jsonify(incident.to_dict(include_counts=True)), 201


@api_bp.route('/incidents/<uuid:incident_id>', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def get_incident(incident_id):
    """Get incident details."""
    incident = g.incident  # Set by require_incident_access
    return jsonify(incident.to_dict(include_counts=True)), 200


@api_bp.route('/incidents/<uuid:incident_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'update', 'incident')
def update_incident(incident_id):
    """Update an incident."""
    incident = g.incident
    try:
        from app.schemas.incident import IncidentUpdate
        # Exclude unset fields (None) to treat them as "not updated"
        data = IncidentUpdate(**request.get_json())
        update_data = data.model_dump(exclude_unset=True)
    except ValueError as e:
        return jsonify({'error': 'bad_request', 'message': str(e)}), 400

    # Update fields
    if 'title' in update_data and update_data['title']:
        incident.title = update_data['title']
    if 'description' in update_data:
        incident.description = update_data['description']
    if 'severity' in update_data:
        incident.severity = update_data['severity']
    if 'classification' in update_data:
        incident.classification = update_data['classification']
    if 'executive_summary' in update_data:
        incident.executive_summary = update_data['executive_summary']
    if 'lessons_learned' in update_data:
        incident.lessons_learned = update_data['lessons_learned']
    if 'lead_responder_id' in update_data:
        user = get_current_user()
        lead = User.query.filter_by(id=update_data['lead_responder_id'], organization_id=user.organization_id).first()
        if lead:
            incident.lead_responder_id = lead.id

    db.session.commit()

    # Broadcast update via WebSocket
    socketio.emit('incident_updated', incident.to_dict(), room=f'incident_{incident_id}')

    return jsonify(incident.to_dict(include_counts=True)), 200


@api_bp.route('/incidents/<uuid:incident_id>/status', methods=['PATCH'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'update_status', 'incident')
def update_incident_status(incident_id):
    """Update incident status and/or phase."""
    incident = g.incident
    try:
        from app.schemas.incident import IncidentStatusUpdate
        data = IncidentStatusUpdate(**request.get_json())
        update_data = data.model_dump(exclude_unset=True)
    except ValueError as e:
        return jsonify({'error': 'bad_request', 'message': str(e)}), 400

    STATUS_PHASE_MAP = {
        'open': 1,
        'investigating': 2,
        'contained': 3,
        'eradicated': 4,
        'recovered': 5,
        'closed': 6,
    }

    now = datetime.now(timezone.utc)

    # Update status and sync phase
    if 'status' in update_data:
        new_status = update_data['status']
        incident.status = new_status

        # Auto-sync phase from status
        if new_status in STATUS_PHASE_MAP:
            incident.phase = STATUS_PHASE_MAP[new_status]

        # Set timestamp for status change
        if new_status == 'contained' and not incident.contained_at:
            incident.contained_at = now
        elif new_status == 'eradicated' and not incident.eradicated_at:
            incident.eradicated_at = now
        elif new_status == 'recovered' and not incident.recovered_at:
            incident.recovered_at = now
        elif new_status == 'closed' and not incident.closed_at:
            incident.closed_at = now

    # Update phase (and sync status from phase)
    elif 'phase' in update_data:
        incident.phase = update_data['phase']
        # Reverse-map phase to status
        phase_status_map = {v: k for k, v in STATUS_PHASE_MAP.items()}
        if update_data['phase'] in phase_status_map:
            incident.status = phase_status_map[update_data['phase']]

    db.session.commit()

    # Broadcast update
    socketio.emit('incident_updated', incident.to_dict(), room=f'incident_{incident_id}')

    return jsonify(incident.to_dict()), 200


@api_bp.route('/incidents/<uuid:incident_id>', methods=['DELETE'])
@jwt_required()
@require_permission('incidents:delete')
@audit_log('data_modification', 'delete', 'incident')
def delete_incident(incident_id):
    """Delete an incident."""
    user = get_current_user()
    incident = Incident.query.filter_by(id=incident_id, organization_id=user.organization_id).first()

    if not incident:
        return jsonify({'error': 'not_found', 'message': 'Incident not found'}), 404

    db.session.delete(incident)
    db.session.commit()

    return jsonify({'message': 'Incident deleted successfully'}), 200


@api_bp.route('/incidents/<uuid:incident_id>/assignments', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def list_assignments(incident_id):
    """List personnel assigned to incident."""
    incident = g.incident

    assignments = IncidentAssignment.query.filter_by(
        incident_id=incident.id,
        removed_at=None
    ).all()

    return jsonify({
        'items': [a.to_dict() for a in assignments]
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/assignments', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'assign_user', 'incident')
def assign_user(incident_id):
    """Assign a user to the incident."""
    user = get_current_user()
    incident = g.incident
    data = request.get_json()

    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'bad_request', 'message': 'user_id is required'}), 400

    target_user = User.query.filter_by(id=user_id, organization_id=user.organization_id).first()
    if not target_user:
        return jsonify({'error': 'not_found', 'message': 'User not found'}), 404

    # Check if already assigned
    existing = IncidentAssignment.query.filter_by(
        incident_id=incident.id,
        user_id=target_user.id,
        removed_at=None
    ).first()

    if existing:
        return jsonify({'error': 'conflict', 'message': 'User already assigned'}), 409

    assignment = IncidentAssignment(
        incident_id=incident.id,
        user_id=target_user.id,
        role=data.get('role'),
        assigned_by=user.id,
        assigned_at=datetime.now(timezone.utc)
    )
    db.session.add(assignment)
    db.session.commit()

    # Notify assigned user
    notify_user_assigned(str(target_user.id), incident)

    return jsonify(assignment.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/assignments/<uuid:assignment_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'unassign_user', 'incident')
def remove_assignment(incident_id, assignment_id):
    """Remove user from incident."""
    incident = g.incident

    assignment = IncidentAssignment.query.filter_by(
        id=assignment_id,
        incident_id=incident.id,
        removed_at=None
    ).first()

    if not assignment:
        return jsonify({'error': 'not_found', 'message': 'Assignment not found'}), 404

    assignment.removed_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'message': 'Assignment removed'}), 200


@api_bp.route('/incidents/<uuid:incident_id>/import', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'import_data', 'incident')
def import_incident_data(incident_id):
    """Import data from Excel file."""
    user = get_current_user()
    
    if 'file' not in request.files:
        return jsonify({'error': 'bad_request', 'message': 'No file provided'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'bad_request', 'message': 'No file selected'}), 400
        
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'bad_request', 'message': 'Invalid file type. Please upload an Excel file.'}), 400
        
    try:
        results = ImportService.process_excel_import(incident_id, file, user.id)
        return jsonify({
            'message': 'Import completed successfully',
            'results': results
        }), 200
    except ValueError as e:
        return jsonify({'error': 'bad_request', 'message': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'server_error', 'message': 'Import failed'}), 500


@api_bp.route('/incidents/<uuid:incident_id>/import/parse', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
def parse_import_file(incident_id):
    """Parse Excel file and return raw structure."""
    if 'file' not in request.files:
        return jsonify({'error': 'bad_request', 'message': 'No file provided'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'bad_request', 'message': 'No file selected'}), 400
        
    try:
        data = ImportService.parse_excel(file)
        return jsonify(data), 200
    except ValueError as e:
        return jsonify({'error': 'bad_request', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'server_error', 'message': 'Parse failed'}), 500


@api_bp.route('/incidents/<uuid:incident_id>/import/submit', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'import_data', 'incident')
def submit_import_data(incident_id):
    """Submit validated data for import."""
    user = get_current_user()
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400
        
    try:
        results = ImportService.bulk_create_entities(incident_id, data, user.id)
        return jsonify({
            'message': 'Import completed successfully',
            'results': results
        }), 200
    except ValueError as e:
        return jsonify({'error': 'bad_request', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'server_error', 'message': 'Import failed'}), 500


# --- Incident-Team management ---

@api_bp.route('/incidents/<uuid:incident_id>/teams', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def list_incident_teams(incident_id):
    """List teams associated with an incident."""
    incident = g.incident
    return jsonify({
        'items': [it.to_dict() for it in incident.incident_teams]
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/teams', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'add_team', 'incident')
def add_incident_team(incident_id):
    """Associate a team with an incident."""
    from app.models import Team
    user = get_current_user()
    incident = g.incident
    data = request.get_json()

    team_id = data.get('team_id')
    if not team_id:
        return jsonify({'error': 'bad_request', 'message': 'team_id is required'}), 400

    team = Team.query.filter_by(id=team_id, organization_id=user.organization_id).first()
    if not team:
        return jsonify({'error': 'not_found', 'message': 'Team not found'}), 404

    existing = IncidentTeam.query.filter_by(incident_id=incident.id, team_id=team.id).first()
    if existing:
        return jsonify({'error': 'conflict', 'message': 'Team already associated'}), 409

    it = IncidentTeam(incident_id=incident.id, team_id=team.id)
    db.session.add(it)
    db.session.commit()

    socketio.emit('incident_updated', incident.to_dict(), room=f'incident_{incident_id}')

    return jsonify(it.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/teams/<uuid:team_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'remove_team', 'incident')
def remove_incident_team(incident_id, team_id):
    """Remove a team from an incident."""
    incident = g.incident

    it = IncidentTeam.query.filter_by(incident_id=incident.id, team_id=team_id).first()
    if not it:
        return jsonify({'error': 'not_found', 'message': 'Team association not found'}), 404

    db.session.delete(it)
    db.session.commit()

    socketio.emit('incident_updated', incident.to_dict(), room=f'incident_{incident_id}')

    return jsonify({'message': 'Team removed from incident'}), 200