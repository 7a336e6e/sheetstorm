"""Incident management endpoints"""
import logging
from datetime import datetime, timezone
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Incident, IncidentAssignment, IncidentTeam, User
from app.middleware.rbac import (  # noqa: F401  (accessible_incidents_query re-exported for callers)
    require_permission, require_incident_access, get_current_user,
    accessible_incidents_query, user_can_access_incident,
)
from app.middleware.audit import audit_log
from app.services.notification_service import notify_incident_created, notify_user_assigned
from app.services.import_service import ImportService
from app.services import realtime
from app.utils.concurrency import commit_or_conflict, precondition, set_etag
from app.utils.pagination import in_list, list_response, parse_uuid, severity_rank

logger = logging.getLogger(__name__)


INCIDENT_SEVERITIES = ('critical', 'high', 'medium', 'low')
INCIDENT_STATUSES = ('open', 'investigating', 'contained', 'eradicated', 'recovered', 'closed')
INCIDENT_SORTABLE = {
    'created_at': Incident.created_at,
    'updated_at': Incident.updated_at,
    'incident_number': Incident.incident_number,
    'title': Incident.title,
    'severity': severity_rank(Incident.severity),
    'status': Incident.status,
    'phase': Incident.phase,
    'detected_at': Incident.detected_at,
}
ARCHIVED_SORTABLE = {**INCIDENT_SORTABLE, 'archived_at': Incident.archived_at}
INCIDENT_FILTERS = {
    'status': (Incident.status, in_list(INCIDENT_STATUSES)),
    'severity': (Incident.severity, in_list(INCIDENT_SEVERITIES)),
    'phase': (Incident.phase, 'int'),
    'classification': (Incident.classification, 'eq'),
}
INCIDENT_SEARCH = (Incident.title, Incident.description, Incident.incident_number)


@api_bp.route('/incidents', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def list_incidents():
    """List incidents (utils/pagination.py contract: page, per_page, sort,
    q/search, focus; filters status (comma list), severity (comma list),
    phase, classification, team_id).

    Visibility: accessible_incidents_query (assigned + the user's
    incidents:read_all / read_team / read_tlp_white scopes).
    """
    user = get_current_user()
    query = accessible_incidents_query(user)

    # Team filter is a subquery, so it stays outside the declarative FILTERS.
    team_id = request.args.get('team_id')
    if team_id:
        query = query.filter(Incident.id.in_(
            db.session.query(IncidentTeam.incident_id).filter(
                IncidentTeam.team_id == parse_uuid('team_id', team_id))))

    return jsonify(list_response(
        query, sortable=INCIDENT_SORTABLE, default_sort='-created_at', id_col=Incident.id,
        filters=INCIDENT_FILTERS, search_columns=INCIDENT_SEARCH,
        serialize=lambda i: i.to_dict(include_counts=True),
    )), 200


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
        tlp=data.tlp or 'amber',
        team_id=str(data.team_id) if data.team_id else None,
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
    realtime.emit_change(incident.id, 'incident', 'created', obj=incident,
                         data=incident.to_dict(include_counts=True))

    return jsonify(incident.to_dict(include_counts=True)), 201


@api_bp.route('/incidents/<uuid:incident_id>', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def get_incident(incident_id):
    """Get incident details."""
    incident = g.incident  # Set by require_incident_access
    return set_etag(jsonify(incident.to_dict(include_counts=True)), incident), 200


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
    conflict = precondition(incident)
    if conflict:
        return conflict, conflict.status_code
    access_before = (incident.tlp, incident.team_id)

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
        new_lead_id = update_data['lead_responder_id']
        lead = User.query.filter_by(id=new_lead_id, organization_id=user.organization_id).first() if new_lead_id else None
        if lead:
            incident.lead_responder_id = lead.id
            # Sync assignments: demote old Lead Responder(s)
            old_leads = IncidentAssignment.query.filter(
                IncidentAssignment.incident_id == incident.id,
                IncidentAssignment.role == 'Lead Responder',
                IncidentAssignment.user_id != lead.id,
                IncidentAssignment.removed_at.is_(None)
            ).all()
            for old_lead in old_leads:
                old_lead.role = None
            # Ensure new lead has an assignment with Lead Responder role
            new_assignment = IncidentAssignment.query.filter_by(
                incident_id=incident.id,
                user_id=lead.id
            ).first()
            if new_assignment:
                if new_assignment.removed_at is not None:
                    new_assignment.removed_at = None
                new_assignment.role = 'Lead Responder'
                new_assignment.assigned_by = user.id
                new_assignment.assigned_at = datetime.now(timezone.utc)
            else:
                new_assignment = IncidentAssignment(
                    incident_id=incident.id,
                    user_id=lead.id,
                    role='Lead Responder',
                    assigned_by=user.id,
                    assigned_at=datetime.now(timezone.utc)
                )
                db.session.add(new_assignment)
        elif new_lead_id is None:
            # Clearing lead responder — demote any Lead Responder assignments
            old_leads = IncidentAssignment.query.filter(
                IncidentAssignment.incident_id == incident.id,
                IncidentAssignment.role == 'Lead Responder',
                IncidentAssignment.removed_at.is_(None)
            ).all()
            for old_lead in old_leads:
                old_lead.role = None
            incident.lead_responder_id = None
    if 'tlp' in update_data:
        incident.tlp = update_data['tlp']
    if 'team_id' in update_data:
        incident.team_id = str(update_data['team_id']) if update_data['team_id'] else None

    conflict = commit_or_conflict(incident)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'incident', 'updated', obj=incident,
                         data=incident.to_dict(include_counts=True))
    if (incident.tlp, incident.team_id) != access_before:
        # TLP / team drive read_tlp_white / read_team visibility: evict
        # anyone present in the incident who lost access.
        _evict_lost_access(incident, [p['user_id'] for p in realtime.presence_list(incident.id)])

    return set_etag(jsonify(incident.to_dict(include_counts=True)), incident), 200


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
    conflict = precondition(incident)
    if conflict:
        return conflict, conflict.status_code

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

    conflict = commit_or_conflict(incident)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'incident', 'updated', obj=incident,
                         data=incident.to_dict(include_counts=True))

    return set_etag(jsonify(incident.to_dict()), incident), 200


@api_bp.route('/incidents/<uuid:incident_id>/archive', methods=['POST'])
@jwt_required()
@require_permission('incidents:archive')
@audit_log('data_modification', 'archive', 'incident')
def archive_incident(incident_id):
    """Archive an incident (soft-delete) you can see."""
    user = get_current_user()
    incident = Incident.query.filter_by(id=incident_id, organization_id=user.organization_id, is_archived=False).first()

    if not incident:
        return jsonify({'error': 'not_found', 'message': 'Incident not found'}), 404
    if not user_can_access_incident(user, incident):
        return jsonify({'error': 'forbidden', 'message': 'You do not have access to this incident'}), 403

    incident.is_archived = True
    incident.archived_at = datetime.now(timezone.utc)
    incident.archived_by = user.id
    incident.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    revoke_incident_rooms(incident.id, 'archived')

    return jsonify({'message': 'Incident archived successfully'}), 200


@api_bp.route('/incidents/archived', methods=['GET'])
@jwt_required()
@require_permission('incidents:archive')
def list_archived_incidents():
    """List archived incidents the user can see."""
    user = get_current_user()
    query = accessible_incidents_query(user, archived=True)
    return jsonify(list_response(
        query, sortable=ARCHIVED_SORTABLE, default_sort='-archived_at', id_col=Incident.id,
        filters=INCIDENT_FILTERS, search_columns=INCIDENT_SEARCH,
        serialize=lambda i: i.to_dict(include_counts=True),
    )), 200


@api_bp.route('/incidents/<uuid:incident_id>/unarchive', methods=['POST'])
@jwt_required()
@require_permission('incidents:archive')
@audit_log('data_modification', 'unarchive', 'incident')
def unarchive_incident(incident_id):
    """Restore an archived incident you can see."""
    user = get_current_user()
    incident = Incident.query.filter_by(id=incident_id, organization_id=user.organization_id, is_archived=True).first()

    if not incident:
        return jsonify({'error': 'not_found', 'message': 'Archived incident not found'}), 404
    if not user_can_access_incident(user, incident):
        return jsonify({'error': 'forbidden', 'message': 'You do not have access to this incident'}), 403

    incident.is_archived = False
    incident.archived_at = None
    incident.archived_by = None
    incident.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    realtime.emit_change(incident.id, 'incident', 'updated', obj=incident,
                         data=incident.to_dict(include_counts=True))

    return jsonify({'message': 'Incident restored successfully', 'incident': incident.to_dict()}), 200


@api_bp.route('/incidents/<uuid:incident_id>/permanent', methods=['DELETE'])
@jwt_required()
@require_permission('incidents:purge')
@audit_log('data_modification', 'permanent_delete', 'incident')
def permanent_delete_incident(incident_id):
    """Permanently delete an archived incident you can see. Irreversible."""
    user = get_current_user()
    incident = Incident.query.filter_by(id=incident_id, organization_id=user.organization_id, is_archived=True).first()

    if not incident:
        return jsonify({'error': 'not_found', 'message': 'Archived incident not found'}), 404
    if not user_can_access_incident(user, incident):
        return jsonify({'error': 'forbidden', 'message': 'You do not have access to this incident'}), 403

    # Forensic preservation: never purge evidence that is under legal hold
    # (the artifacts would cascade-delete with the incident).
    from app.models import Artifact
    held = [a for a in Artifact.query.filter_by(incident_id=incident.id).all() if a.under_legal_hold]
    if held:
        return jsonify({
            'error': 'conflict',
            'message': f'{len(held)} artifact(s) are under legal hold; release the hold(s) before permanently deleting this incident',
            'held_artifact_ids': [str(a.id) for a in held],
        }), 409

    db.session.delete(incident)
    db.session.commit()

    return jsonify({'message': 'Incident permanently deleted'}), 200


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

    new_role = data.get('role')

    # Check for ANY existing assignment (including soft-deleted)
    existing = IncidentAssignment.query.filter_by(
        incident_id=incident.id,
        user_id=target_user.id
    ).first()

    if existing:
        if existing.removed_at is not None:
            # Reactivate soft-deleted assignment
            existing.removed_at = None
            existing.role = new_role
            existing.assigned_by = user.id
            existing.assigned_at = datetime.now(timezone.utc)
            assignment = existing
        elif existing.role == new_role:
            return jsonify({'error': 'conflict', 'message': 'User already assigned with this role'}), 409
        else:
            # User is already assigned with a different role — update the role
            existing.role = new_role
            existing.assigned_by = user.id
            existing.assigned_at = datetime.now(timezone.utc)
            assignment = existing
    else:
        assignment = IncidentAssignment(
            incident_id=incident.id,
            user_id=target_user.id,
            role=new_role,
            assigned_by=user.id,
            assigned_at=datetime.now(timezone.utc)
        )
        db.session.add(assignment)

    # If the role is Lead Responder, demote any existing Lead Responder and update incident
    if new_role == 'Lead Responder':
        old_leads = IncidentAssignment.query.filter(
            IncidentAssignment.incident_id == incident.id,
            IncidentAssignment.role == 'Lead Responder',
            IncidentAssignment.user_id != target_user.id,
            IncidentAssignment.removed_at.is_(None)
        ).all()
        for old_lead in old_leads:
            old_lead.role = None
        incident.lead_responder_id = target_user.id

    db.session.commit()

    # Notify assigned user
    notify_user_assigned(str(target_user.id), incident)
    realtime.emit_change(incident.id, 'assignment', 'updated' if existing else 'created', obj=assignment)
    if new_role == 'Lead Responder':
        realtime.emit_change(incident.id, 'incident', 'updated', obj=incident,
                             data=incident.to_dict(include_counts=True))

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

    # If this was the Lead Responder, clear the incident's lead_responder_id
    if assignment.role == 'Lead Responder' and incident.lead_responder_id == assignment.user_id:
        incident.lead_responder_id = None

    db.session.commit()
    realtime.emit_change(incident.id, 'assignment', 'deleted', id=assignment.id)
    _evict_lost_access(incident, [assignment.user_id])

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
        realtime.emit_resync(incident_id, None, 'import')
        return jsonify({
            'message': 'Import completed successfully',
            'results': results
        }), 200
    except ValueError as e:
        return jsonify({'error': 'bad_request', 'message': str(e)}), 400
    except Exception as e:
        logger.exception('Excel import failed for incident %s', incident_id)
        return jsonify({'error': 'server_error', 'message': 'Import failed'}), 500


@api_bp.route('/incidents/<uuid:incident_id>/import/parse', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'parse_import_file', 'incident')
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
    except Exception:
        logger.exception('Excel parse failed')
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
        realtime.emit_resync(incident_id, None, 'import')
        return jsonify({
            'message': 'Import completed successfully',
            'results': results
        }), 200
    except ValueError as e:
        return jsonify({'error': 'bad_request', 'message': str(e)}), 400
    except Exception:
        logger.exception('Bulk import failed for incident %s', incident_id)
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
    realtime.emit_change(incident.id, 'incident', 'updated', obj=incident,
                         data=incident.to_dict(include_counts=True))
    # The first linked team turns an org-wide (team scope) incident team-only.
    _evict_lost_access(incident, [p['user_id'] for p in realtime.presence_list(incident.id)])

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

    member_ids = [m.user_id for m in it.team.members] if it.team else []
    db.session.delete(it)
    db.session.commit()
    realtime.emit_change(incident.id, 'incident', 'updated', obj=incident,
                         data=incident.to_dict(include_counts=True))
    _evict_lost_access(incident, member_ids)

    return jsonify({'message': 'Team removed from incident'}), 200


# --- Realtime revocation (W1-RT-EMIT) ---

def _evict_lost_access(incident, user_ids):
    """After commit: drop users who can no longer see the incident from its
    socket rooms (assignment/team removal, TLP or team change)."""
    for uid in dict.fromkeys(str(u) for u in user_ids if u):
        try:
            target = db.session.get(User, uid)
            if target is None or not user_can_access_incident(target, incident):
                realtime.evict_user_from_incident(uid, incident.id, reason='access_removed')
        except Exception:
            logger.exception('realtime: access re-check failed for user %s', uid)


def revoke_incident_rooms(incident_id, reason):
    """After commit: tell everyone in the incident's rooms that access is gone
    (archive / purge), then close the base and scope rooms."""
    try:
        iid = realtime.canonical_incident_id(incident_id)
        realtime.get_emitter().emit('incident:access_revoked', {'incident_id': iid, 'reason': reason},
                                    to=realtime.base_room(iid))
    except Exception:
        logger.exception('realtime: access_revoked broadcast failed')
    realtime.close_incident_rooms(incident_id)


def _purge_access_revoked(incident=None, *args, incident_id=None, **ctx):
    """incident_purge post-commit step `access_revoked`. The row is gone, so
    only the primary key is used (from the instance identity, which survives
    the delete + commit)."""
    if incident_id is None and isinstance(incident, dict):    # a context dict
        incident_id = incident.get('incident_id') or incident.get('id')
    elif incident_id is None and incident is not None:
        try:
            from sqlalchemy import inspect as sa_inspect
            identity = sa_inspect(incident).identity
            incident_id = identity[0] if identity else None
        except Exception:  # not a mapped instance: a context object
            incident_id = getattr(incident, 'incident_id', None)
    if incident_id is None:
        logger.warning('realtime: purge step access_revoked got no incident id')
        return
    revoke_incident_rooms(incident_id, 'purged')


try:  # incident_purge ships with W1-EVD-CORE; without it there is nothing to hook.
    from app.services.incident_purge import register_purge_step
except ImportError:  # pragma: no cover - depends on merge order
    register_purge_step = None
if register_purge_step is not None:
    register_purge_step('access_revoked', _purge_access_revoked, phase='post_commit')
