"""IR-aligned playbook endpoints (phase-gated runbooks + augmenting actions)."""
from datetime import datetime, timezone
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Playbook, IncidentPlaybook
from app.middleware.rbac import require_permission, require_incident_access, get_current_user
from app.middleware.audit import audit_log
from app.services.playbook_service import PlaybookService
from app.services import realtime
from app.utils.concurrency import commit_or_conflict, precondition, set_etag

# Scopes an auto/manual playbook action may change (refetched via resync).
_ACTION_SCOPES = {'enrich_iocs': ['network_iocs'], 'generate_summary': ['incident'],
                  'suggest_mitre': ['timeline'], 'create_task': ['tasks']}


def _validate_definition(definition):
    """Structurally validate a playbook definition (400 instead of a 500 later)."""
    if definition is None:
        return True, None
    if not isinstance(definition, dict):
        return False, 'definition must be an object'
    phases = definition.get('phases', [])
    if not isinstance(phases, list):
        return False, 'definition.phases must be a list'
    action_keys = set()
    for i, ph in enumerate(phases):
        if not isinstance(ph, dict):
            return False, f'definition.phases[{i}] must be an object'
        phase_no = ph.get('phase')
        if isinstance(phase_no, bool) or not isinstance(phase_no, int) or not 1 <= phase_no <= 6:
            return False, f'definition.phases[{i}].phase must be an integer 1-6'
        if ph.get('name') is not None and not isinstance(ph.get('name'), str):
            return False, f'definition.phases[{i}].name must be a string'
        tasks = ph.get('tasks') or []
        if not isinstance(tasks, list) or not all(isinstance(t, dict) for t in tasks):
            return False, f'definition.phases[{i}].tasks must be a list of objects'
        actions = ph.get('actions') or []
        if not isinstance(actions, list):
            return False, f'definition.phases[{i}].actions must be a list'
        for j, act in enumerate(actions):
            where = f'definition.phases[{i}].actions[{j}]'
            if not isinstance(act, dict):
                return False, f'{where} must be an object'
            if act.get('type') not in Playbook.ACTION_TYPES:
                return False, f"{where}: invalid action type {act.get('type')!r}. Allowed: {Playbook.ACTION_TYPES}"
            key = act.get('key')
            if not isinstance(key, str) or not key.strip():
                return False, f'{where}.key must be a non-empty string'
            if key in action_keys:
                return False, f'{where}.key {key!r} is duplicated'
            action_keys.add(key)
            if act.get('config') is not None and not isinstance(act['config'], dict):
                return False, f'{where}.config must be an object'
            if 'auto_run' in act and not isinstance(act['auto_run'], bool):
                return False, f'{where}.auto_run must be a boolean'
    return True, None


def _can_manage_template(user, pb):
    """Templates may be changed only by their creator or an org manager."""
    return pb.created_by == user.id or user.has_permission('organizations:manage')


def _phase_actions(definition, phase):
    for ph in (definition or {}).get('phases', []):
        if ph.get('phase') == phase:
            return ph.get('actions') or []
    return []


def _record_run(inst, action, result):
    state = dict(inst.state or {})
    runs = list(state.get('action_runs', []))
    runs.append({
        'key': action.get('key'), 'type': action.get('type'), 'name': action.get('name'),
        'result': result, 'run_at': datetime.now(timezone.utc).isoformat(),
    })
    state['action_runs'] = runs
    inst.state = state


def _run_auto_actions(inst, incident, phase, user):
    runs = []
    for act in _phase_actions(inst.definition, phase):
        if act.get('auto_run'):
            result = PlaybookService.execute_action(incident, act, user)
            _record_run(inst, act, result)
            # Commit per action so a later failing action (which rolls the
            # session back) cannot discard earlier run records.
            db.session.commit()
            runs.append({'key': act.get('key'), 'type': act.get('type'), 'result': result})
    scopes = [s for r in runs for s in _ACTION_SCOPES.get(r['type'], [])]
    if scopes:
        realtime.emit_resync(incident.id, scopes, 'playbook_action')
    return runs


# --------------------------------------------------------------------------
# Playbook templates (org-scoped)
# --------------------------------------------------------------------------

@api_bp.route('/playbooks', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def list_playbooks():
    user = get_current_user()
    pbs = Playbook.query.filter_by(organization_id=user.organization_id).order_by(Playbook.created_at.desc()).all()
    return jsonify({'items': [p.to_dict() for p in pbs], 'total': len(pbs)}), 200


@api_bp.route('/playbooks', methods=['POST'])
@jwt_required()
@require_permission('incidents:create')
@audit_log('admin_action', 'create_playbook', 'playbook')
def create_playbook():
    user = get_current_user()
    data = request.get_json() or {}
    if not isinstance(data.get('name'), str) or not data['name'].strip():
        return jsonify({'error': 'bad_request', 'message': 'name is required'}), 400
    if 'is_template' in data and not isinstance(data['is_template'], bool):
        return jsonify({'error': 'bad_request', 'message': 'is_template must be a boolean'}), 400
    valid, msg = _validate_definition(data.get('definition'))
    if not valid:
        return jsonify({'error': 'bad_request', 'message': msg}), 400
    pb = Playbook(
        organization_id=user.organization_id,
        name=data['name'].strip(),
        description=data.get('description'),
        incident_type=data.get('incident_type'),
        definition=data.get('definition') or {},
        is_template=data.get('is_template', True),
        created_by=user.id,
    )
    db.session.add(pb)
    db.session.commit()
    return jsonify(pb.to_dict()), 201


@api_bp.route('/playbooks/<uuid:playbook_id>', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def get_playbook(playbook_id):
    user = get_current_user()
    pb = Playbook.query.filter_by(id=playbook_id, organization_id=user.organization_id).first()
    if not pb:
        return jsonify({'error': 'not_found', 'message': 'Playbook not found'}), 404
    return jsonify(pb.to_dict()), 200


@api_bp.route('/playbooks/<uuid:playbook_id>', methods=['PUT'])
@jwt_required()
@require_permission('incidents:create')
@audit_log('admin_action', 'update_playbook', 'playbook')
def update_playbook(playbook_id):
    user = get_current_user()
    pb = Playbook.query.filter_by(id=playbook_id, organization_id=user.organization_id).first()
    if not pb:
        return jsonify({'error': 'not_found', 'message': 'Playbook not found'}), 404
    if not _can_manage_template(user, pb):
        return jsonify({'error': 'forbidden', 'message': 'Only the playbook creator or an organization manager can modify it'}), 403
    data = request.get_json(silent=True) or {}
    if 'name' in data and (not isinstance(data['name'], str) or not data['name'].strip()):
        return jsonify({'error': 'bad_request', 'message': 'name must be a non-empty string'}), 400
    if 'is_template' in data and not isinstance(data['is_template'], bool):
        return jsonify({'error': 'bad_request', 'message': 'is_template must be a boolean'}), 400
    if 'definition' in data:
        valid, msg = _validate_definition(data['definition'])
        if not valid:
            return jsonify({'error': 'bad_request', 'message': msg}), 400
    for field in ['name', 'description', 'incident_type', 'definition', 'is_template']:
        if field in data:
            setattr(pb, field, data[field])
    db.session.commit()
    return jsonify(pb.to_dict()), 200


@api_bp.route('/playbooks/<uuid:playbook_id>', methods=['DELETE'])
@jwt_required()
@require_permission('incidents:create')
@audit_log('admin_action', 'delete_playbook', 'playbook')
def delete_playbook(playbook_id):
    user = get_current_user()
    pb = Playbook.query.filter_by(id=playbook_id, organization_id=user.organization_id).first()
    if not pb:
        return jsonify({'error': 'not_found', 'message': 'Playbook not found'}), 404
    if not _can_manage_template(user, pb):
        return jsonify({'error': 'forbidden', 'message': 'Only the playbook creator or an organization manager can delete it'}), 403
    db.session.delete(pb)
    db.session.commit()
    return jsonify({'message': 'Playbook deleted'}), 200


# --------------------------------------------------------------------------
# Incident playbook instances
# --------------------------------------------------------------------------

@api_bp.route('/incidents/<uuid:incident_id>/playbooks/<uuid:playbook_id>/activate', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'activate_playbook', 'incident')
def activate_playbook(incident_id, playbook_id):
    incident = g.incident
    user = get_current_user()
    pb = Playbook.query.filter_by(id=playbook_id, organization_id=user.organization_id).first()
    if not pb:
        return jsonify({'error': 'not_found', 'message': 'Playbook not found'}), 404

    start_phase = incident.phase or 1
    inst = IncidentPlaybook(
        incident_id=incident.id,
        playbook_id=pb.id,
        name=pb.name,
        definition=pb.definition or {},
        current_phase=start_phase,
        state={'tasks': {}, 'action_runs': []},
        activated_at=datetime.now(timezone.utc),
        created_by=user.id,
    )
    db.session.add(inst)
    db.session.commit()

    runs = _run_auto_actions(inst, incident, start_phase, user)
    realtime.emit_change(incident.id, 'playbook', 'created', obj=inst)
    return jsonify({'incident_playbook': inst.to_dict(), 'actions_executed': runs}), 201


@api_bp.route('/incidents/<uuid:incident_id>/playbook', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def get_incident_playbook(incident_id):
    incident = g.incident
    inst = IncidentPlaybook.query.filter_by(incident_id=incident.id).order_by(IncidentPlaybook.created_at.desc()).first()
    return set_etag(jsonify({'incident_playbook': inst.to_dict() if inst else None}), inst), 200


@api_bp.route('/incidents/<uuid:incident_id>/playbook/advance', methods=['PUT'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'advance_playbook', 'incident')
def advance_playbook(incident_id):
    incident = g.incident
    user = get_current_user()
    inst = IncidentPlaybook.query.filter_by(incident_id=incident.id).order_by(IncidentPlaybook.created_at.desc()).first()
    if not inst:
        return jsonify({'error': 'not_found', 'message': 'No active playbook'}), 404
    conflict = precondition(inst)
    if conflict:
        return conflict, conflict.status_code
    inst.current_phase = min((inst.current_phase or 1) + 1, 6)
    conflict = commit_or_conflict(inst)
    if conflict:
        return conflict, conflict.status_code
    runs = _run_auto_actions(inst, incident, inst.current_phase, user)
    realtime.emit_change(incident.id, 'playbook', 'updated', obj=inst)
    return set_etag(jsonify({'incident_playbook': inst.to_dict(), 'actions_executed': runs}), inst), 200


@api_bp.route('/incidents/<uuid:incident_id>/playbook/execute', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'execute_playbook_action', 'incident')
def execute_playbook_action(incident_id):
    incident = g.incident
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    action_key = data.get('action_key')
    inst = IncidentPlaybook.query.filter_by(incident_id=incident.id).order_by(IncidentPlaybook.created_at.desc()).first()
    if not inst:
        return jsonify({'error': 'not_found', 'message': 'No active playbook'}), 404
    action = None
    for ph in (inst.definition or {}).get('phases', []):
        for act in (ph.get('actions') or []):
            if act.get('key') == action_key:
                action = act
                break
    if not action:
        return jsonify({'error': 'not_found', 'message': 'Action not found'}), 404
    result = PlaybookService.execute_action(incident, action, user)
    _record_run(inst, action, result)
    db.session.commit()
    realtime.emit_change(incident.id, 'playbook', 'updated', obj=inst)
    if _ACTION_SCOPES.get(action.get('type')):
        realtime.emit_resync(incident.id, _ACTION_SCOPES[action.get('type')], 'playbook_action')
    return set_etag(jsonify({'result': result, 'incident_playbook': inst.to_dict()}), inst), 200


@api_bp.route('/incidents/<uuid:incident_id>/playbook/task', methods=['PUT'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'toggle_playbook_task', 'incident')
def toggle_playbook_task(incident_id):
    incident = g.incident
    data = request.get_json(silent=True) or {}
    task_key = data.get('task_key')
    if not isinstance(task_key, str) or not task_key:
        return jsonify({'error': 'bad_request', 'message': 'task_key is required'}), 400
    if 'done' in data and not isinstance(data['done'], bool):
        return jsonify({'error': 'bad_request', 'message': 'done must be a boolean'}), 400
    inst = IncidentPlaybook.query.filter_by(incident_id=incident.id).order_by(IncidentPlaybook.created_at.desc()).first()
    if not inst:
        return jsonify({'error': 'not_found', 'message': 'No active playbook'}), 404
    conflict = precondition(inst)
    if conflict:
        return conflict, conflict.status_code
    state = dict(inst.state or {})
    tasks = dict(state.get('tasks', {}))
    tasks[task_key] = bool(data.get('done', True))
    state['tasks'] = tasks
    inst.state = state
    conflict = commit_or_conflict(inst)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'playbook', 'updated', obj=inst)
    return set_etag(jsonify({'incident_playbook': inst.to_dict()}), inst), 200
