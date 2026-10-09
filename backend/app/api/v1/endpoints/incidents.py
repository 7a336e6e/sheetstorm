"""Incident management endpoints"""
import logging
from datetime import datetime, timedelta, timezone
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
from app.services.incident_purge import register_purge_step
from app.utils.audit_diff import record_changes, snapshot
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


# --- IR milestones and lifecycle stamping (W2-DFIR-B, C20) ---

# Every milestone in the order it must occur. Columns that do not exist yet
# (first_malicious_at arrives with W3-RT-POST) are skipped automatically.
MILESTONE_ORDER = ('first_malicious_at', 'detected_at', 'contained_at',
                   'eradicated_at', 'recovered_at', 'closed_at')
# Clock-skew allowance for "not in the future".
MILESTONE_FUTURE_TOLERANCE = timedelta(minutes=5)

STATUS_PHASE_MAP = {
    'open': 1,
    'investigating': 2,
    'contained': 3,
    'eradicated': 4,
    'recovered': 5,
    'closed': 6,
}
PHASE_STATUS_MAP = {v: k for k, v in STATUS_PHASE_MAP.items()}
# Milestone stamped (if still empty) when the incident enters a status.
STATUS_MILESTONE = {
    'contained': 'contained_at',
    'eradicated': 'eradicated_at',
    'recovered': 'recovered_at',
    'closed': 'closed_at',
}
# Fields whose before/after goes into the audit row of PUT / PATCH status.
AUDITED_INCIDENT_FIELDS = (
    'title', 'description', 'severity', 'classification', 'status', 'phase', 'tlp',
    'team_id', 'lead_responder_id', 'executive_summary', 'lessons_learned',
) + MILESTONE_ORDER


def milestone_fields():
    """MILESTONE_ORDER restricted to columns the Incident model has."""
    return [f for f in MILESTONE_ORDER if hasattr(Incident, f)]


def _milestone_error(code, message, **details):
    return {'error': 'invalid_milestones', 'code': code, 'message': message, **details}


def validate_milestones(incident, changes, now=None):
    """Check milestone values about to be written. Returns an error body for a
    400, or None.

    ``changes`` maps milestone field -> aware datetime or None (cleared).
    - A value more than 5 minutes in the future is rejected.
    - Order first_malicious <= detected <= contained <= eradicated <=
      recovered <= closed: every *changed* value is compared with every other
      set value (stored or changed). Pairs where neither side changes are
      legacy data and are left alone (metrics report them as anomalies).
    """
    now = now or datetime.now(timezone.utc)
    for field, value in changes.items():
        if value is not None and value > now + MILESTONE_FUTURE_TOLERANCE:
            return _milestone_error('milestone_in_future',
                                    f'{field} cannot be more than 5 minutes in the future', field=field)

    order = milestone_fields()
    merged = {f: (changes[f] if f in changes else getattr(incident, f, None)) for f in order}
    for field in order:
        if field not in changes or merged[field] is None:
            continue
        pos = order.index(field)
        for other in order:
            other_value = merged[other]
            if other == field or other_value is None:
                continue
            earlier, later = (other, field) if order.index(other) < pos else (field, other)
            if merged[earlier] > merged[later]:
                return _milestone_error(
                    'milestone_order',
                    f'{earlier} must not be after {later}',
                    field=field, conflicts_with=other, pair=[earlier, later])
    return None


def apply_status_change(incident, status=None, phase=None, now=None):
    """Set status and/or phase on ``incident`` (each implies the other) and
    stamp lifecycle milestones. Shared by every status/phase write.

    - Entering contained / eradicated / recovered / closed stamps the matching
      ``*_at`` milestone if it is still empty (an edited value is kept).
    - Reopening (closed -> any other status) clears ``closed_at``.
    """
    now = now or datetime.now(timezone.utc)
    if status is not None:
        phase = STATUS_PHASE_MAP.get(status, phase)
    elif phase is not None:
        status = PHASE_STATUS_MAP.get(phase)
    if status is None and phase is None:
        return
    was_closed = incident.status == 'closed'
    if status is not None:
        incident.status = status
    if phase is not None:
        incident.phase = phase

    milestone = STATUS_MILESTONE.get(incident.status)
    if milestone and getattr(incident, milestone) is None:
        setattr(incident, milestone, now)
    if was_closed and incident.status != 'closed':
        incident.closed_at = None


def incident_summary(incident_id, permissions):
    """Overview aggregates for one incident (single GET only), computed with
    grouped queries so they are never limited by list pagination. Each part
    is null unless the caller may read the underlying entity."""
    from sqlalchemy import func
    from app.models import CompromisedHost, Task, TimelineEvent

    iso = lambda v: v.isoformat() if v else None  # noqa: E731
    summary = {'first_event_at': None, 'last_event_at': None, 'earliest_detection_at': None,
               'leads': None, 'hosts_by_triage': None, 'acquisition': None}

    if 'timeline:read' in permissions:
        first_event, last_event, earliest_detection = db.session.query(
            func.min(TimelineEvent.timestamp), func.max(TimelineEvent.timestamp),
            func.min(TimelineEvent.detection_time),
        ).filter(TimelineEvent.incident_id == incident_id).one()
        summary.update(first_event_at=iso(first_event), last_event_at=iso(last_event),
                       earliest_detection_at=iso(earliest_detection))

    if 'tasks:read' in permissions:
        by_outcome = {}
        for outcome, count in db.session.query(Task.lead_outcome, func.count(Task.id)).filter(
                Task.incident_id == incident_id, Task.task_type == 'investigative_lead',
        ).group_by(Task.lead_outcome):
            by_outcome[outcome or 'open'] = by_outcome.get(outcome or 'open', 0) + count
        summary['leads'] = {
            'total': sum(by_outcome.values()),
            'open': by_outcome.get('open', 0),
            'by_outcome': by_outcome,
        }

    if 'hosts:read' in permissions:
        acq_keys = ('disk_imaged', 'memory_captured', 'logs_collected', 'forensically_sound')
        acq_cols = [func.count(CompromisedHost.id).filter(
            CompromisedHost.acquisition_status[k].astext == 'true') for k in acq_keys]
        hosts_by_triage = {}
        acquisition = dict.fromkeys(acq_keys, 0)
        for row in db.session.query(CompromisedHost.triage_status, func.count(CompromisedHost.id),
                                    *acq_cols).filter(
                CompromisedHost.incident_id == incident_id).group_by(CompromisedHost.triage_status):
            triage = row[0] or 'under_analysis'
            hosts_by_triage[triage] = hosts_by_triage.get(triage, 0) + row[1]
            for key, n in zip(acq_keys, row[2:]):
                acquisition[key] += n
        summary.update(hosts_by_triage=hosts_by_triage, acquisition=acquisition)

    return summary


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
    """Create a new incident.

    The owning team (`team_id`), access teams (`team_ids`) and the lead
    responder must belong to the caller's organization (400 otherwise; they
    were silently dropped before). `detected_at` defaults to now and may not
    be more than 5 minutes in the future. A lead gets the "Lead Responder"
    assignment, exactly like a lead change through PUT. One transaction.
    """
    from app.models import Team
    user = get_current_user()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'bad_request', 'message': 'A JSON object body is required'}), 400
    try:
        from app.schemas.incident import IncidentCreate
        data = IncidentCreate(**payload)
    except ValueError as e:
        return jsonify({'error': 'bad_request', 'message': str(e)}), 400

    now = datetime.now(timezone.utc)
    if data.detected_at and data.detected_at > now + MILESTONE_FUTURE_TOLERANCE:
        return jsonify(_milestone_error('milestone_in_future',
                                        'detected_at cannot be more than 5 minutes in the future',
                                        field='detected_at')), 400

    def org_team(team_id):
        return Team.query.filter_by(id=team_id, organization_id=user.organization_id).first()

    if data.team_id and not org_team(data.team_id):
        return jsonify({'error': 'invalid_team', 'message': 'team_id is not a team of your organization'}), 400
    access_teams = []
    for tid in dict.fromkeys(data.team_ids or []):
        team = org_team(tid)
        if not team:
            return jsonify({'error': 'invalid_team', 'message': 'team_ids contains a team outside your organization',
                            'team_id': str(tid)}), 400
        access_teams.append(team)

    lead = None
    if data.lead_responder_id:
        lead = User.query.filter_by(id=data.lead_responder_id, organization_id=user.organization_id,
                                    is_active=True).first()
        if not lead:
            return jsonify({'error': 'invalid_lead_responder',
                            'message': 'lead_responder_id is not an active user of your organization'}), 400

    incident = Incident(
        organization_id=user.organization_id,
        title=data.title,
        description=data.description,
        severity=data.severity,
        classification=data.classification,
        phase=1,  # Start in Preparation phase
        status='open',
        tlp=data.tlp or 'amber',
        team_id=data.team_id,
        lead_responder_id=lead.id if lead else None,
        detected_at=data.detected_at or now,
        created_by=user.id
    )
    db.session.add(incident)
    db.session.flush()  # incident.id for the rows below

    for team in access_teams:
        db.session.add(IncidentTeam(incident_id=incident.id, team_id=team.id))

    # Creator assignment; a creator who is also the lead gets the lead role.
    db.session.add(IncidentAssignment(
        incident_id=incident.id, user_id=user.id,
        role='Lead Responder' if lead and lead.id == user.id else 'Creator',
        assigned_by=user.id, assigned_at=now,
    ))
    if lead and lead.id != user.id:
        db.session.add(IncidentAssignment(
            incident_id=incident.id, user_id=lead.id, role='Lead Responder',
            assigned_by=user.id, assigned_at=now,
        ))
    db.session.commit()

    # Send notifications
    notify_incident_created(incident)
    if lead and lead.id != user.id:
        notify_user_assigned(str(lead.id), incident)
    realtime.emit_change(incident.id, 'incident', 'created', obj=incident,
                         data=incident.to_dict(include_counts=True))

    return jsonify(incident.to_dict(include_counts=True)), 201


@api_bp.route('/incidents/<uuid:incident_id>', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def get_incident(incident_id):
    """Get incident details, plus the Overview `summary` block (timeline
    span, lead and host triage counts; single GET only, never in lists)."""
    incident = g.incident  # Set by require_incident_access
    data = incident.to_dict(include_counts=True)
    data['summary'] = incident_summary(incident.id, set(get_current_user().permissions))
    return set_etag(jsonify(data), incident), 200


@api_bp.route('/incidents/<uuid:incident_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'update', 'incident')
def update_incident(incident_id):
    """Update an incident.

    IR milestones (`detected_at` … `closed_at`; null clears one) are rejected
    with 400 `invalid_milestones` when more than 5 minutes in the future or
    out of order (see validate_milestones). A new lead responder must be an
    active user of the organization and is notified after commit.
    """
    from app.models import Team
    from app.schemas.incident import IncidentUpdate
    incident = g.incident
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'bad_request', 'message': 'A JSON object body is required'}), 400
    try:
        # Exclude unset fields (None) to treat them as "not updated"
        data = IncidentUpdate(**payload)
        update_data = data.model_dump(exclude_unset=True)
    except ValueError as e:
        return jsonify({'error': 'bad_request', 'message': str(e)}), 400
    conflict = precondition(incident)
    if conflict:
        return conflict, conflict.status_code

    milestone_changes = {f: update_data[f] for f in milestone_fields() if f in update_data}
    if milestone_changes:
        error = validate_milestones(incident, milestone_changes)
        if error:
            return jsonify(error), 400
    if update_data.get('team_id') and not Team.query.filter_by(
            id=update_data['team_id'], organization_id=incident.organization_id).first():
        return jsonify({'error': 'invalid_team', 'message': 'team_id is not a team of your organization'}), 400

    previous_lead_id = incident.lead_responder_id
    new_lead = None
    if update_data.get('lead_responder_id'):
        new_lead = User.query.filter_by(id=update_data['lead_responder_id'],
                                        organization_id=incident.organization_id).first()
        if new_lead is None or (not new_lead.is_active and new_lead.id != previous_lead_id):
            return jsonify({'error': 'invalid_lead_responder',
                            'message': 'lead_responder_id is not an active user of your organization'}), 400

    # Validation is complete: nothing below returns before the commit.
    before = snapshot(incident, AUDITED_INCIDENT_FIELDS)
    access_before = (incident.tlp, incident.team_id)
    notify_lead = None
    # Lead changes rewrite assignments: (op, assignment) to emit after commit,
    # and users whose access must be re-checked then.
    assignment_changes = []
    access_recheck = []

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
        lead = new_lead
        if lead and lead.id != previous_lead_id:
            notify_lead = lead
        if lead or new_lead_id is None:
            access_recheck.append(incident.lead_responder_id)
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
                assignment_changes.append(('updated', old_lead))
                access_recheck.append(old_lead.user_id)
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
                assignment_changes.append(('updated', new_assignment))
            else:
                new_assignment = IncidentAssignment(
                    incident_id=incident.id,
                    user_id=lead.id,
                    role='Lead Responder',
                    assigned_by=user.id,
                    assigned_at=datetime.now(timezone.utc)
                )
                db.session.add(new_assignment)
                assignment_changes.append(('created', new_assignment))
        elif new_lead_id is None:
            # Clearing lead responder — demote any Lead Responder assignments
            old_leads = IncidentAssignment.query.filter(
                IncidentAssignment.incident_id == incident.id,
                IncidentAssignment.role == 'Lead Responder',
                IncidentAssignment.removed_at.is_(None)
            ).all()
            for old_lead in old_leads:
                old_lead.role = None
                assignment_changes.append(('updated', old_lead))
                access_recheck.append(old_lead.user_id)
            incident.lead_responder_id = None
    if 'tlp' in update_data:
        incident.tlp = update_data['tlp']
    if 'team_id' in update_data:
        incident.team_id = update_data['team_id']
    for field, value in milestone_changes.items():
        setattr(incident, field, value)
    record_changes(before, snapshot(incident, AUDITED_INCIDENT_FIELDS))

    conflict = commit_or_conflict(incident)
    if conflict:
        return conflict, conflict.status_code
    if notify_lead is not None:
        # Same "you were assigned" notification as POST /assignments.
        notify_user_assigned(str(notify_lead.id), incident)
    realtime.emit_change(incident.id, 'incident', 'updated', obj=incident,
                         data=incident.to_dict(include_counts=True))
    for op, assignment in assignment_changes:
        realtime.emit_change(incident.id, 'assignment', op, obj=assignment)
    if (incident.tlp, incident.team_id) != access_before:
        # TLP / team drive read_tlp_white / read_team visibility: evict
        # anyone present in the incident who lost access.
        access_recheck += [p['user_id'] for p in realtime.presence_list(incident.id)]
    if access_recheck:
        _evict_lost_access(incident, access_recheck)

    return set_etag(jsonify(incident.to_dict(include_counts=True)), incident), 200


@api_bp.route('/incidents/<uuid:incident_id>/status', methods=['PATCH'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'update_status', 'incident')
def update_incident_status(incident_id):
    """Update incident status and/or phase (each implies the other).

    Entering contained / eradicated / recovered / closed stamps that
    milestone if it is empty; reopening a closed incident clears `closed_at`
    (apply_status_change).
    """
    incident = g.incident
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'bad_request', 'message': 'A JSON object body is required'}), 400
    try:
        from app.schemas.incident import IncidentStatusUpdate
        data = IncidentStatusUpdate(**payload)
        update_data = data.model_dump(exclude_unset=True)
    except ValueError as e:
        return jsonify({'error': 'bad_request', 'message': str(e)}), 400
    conflict = precondition(incident)
    if conflict:
        return conflict, conflict.status_code

    before = snapshot(incident, AUDITED_INCIDENT_FIELDS)
    if update_data.get('status') is not None:
        apply_status_change(incident, status=update_data['status'])
    elif update_data.get('phase') is not None:
        apply_status_change(incident, phase=update_data['phase'])
    record_changes(before, snapshot(incident, AUDITED_INCIDENT_FIELDS))

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

    # Audited purge (services/incident_purge.py): legal-hold check on
    # artifacts and evidence items, ledger heads logged before deletion,
    # registered purge steps, custody purge GUC, DB cascade.
    from app.services.incident_purge import PurgeBlocked, PurgeError, purge_incident
    try:
        purge_incident(incident, user)
    except PurgeBlocked as exc:
        return jsonify(exc.to_dict()), 409
    except PurgeError as exc:
        return jsonify(exc.to_dict()), exc.status

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
            return jsonify({'error': 'already_assigned', 'message': 'User already assigned with this role'}), 409
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
        lead_changed = incident.lead_responder_id != target_user.id
        incident.lead_responder_id = target_user.id
    else:
        old_leads = []
        # Re-assigning the current lead with another role ends their lead
        # role: keep incident.lead_responder_id consistent with assignments.
        lead_changed = incident.lead_responder_id == target_user.id
        if lead_changed:
            incident.lead_responder_id = None

    db.session.commit()

    # Notify assigned user
    notify_user_assigned(str(target_user.id), incident)
    realtime.emit_change(incident.id, 'assignment', 'updated' if existing else 'created', obj=assignment)
    for old_lead in old_leads:
        realtime.emit_change(incident.id, 'assignment', 'updated', obj=old_lead)
    if new_role == 'Lead Responder' or lead_changed:
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


def _purge_access_revoked(ctx):
    """incident_purge post-commit step `access_revoked` (ctx: PurgeContext).
    The row is gone by then, so only ``ctx.incident_id`` is used."""
    revoke_incident_rooms(ctx.incident_id, 'purged')


register_purge_step('access_revoked', _purge_access_revoked, phase='post_commit')
