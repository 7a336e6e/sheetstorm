"""IR-aligned playbook endpoints (phase-gated runbooks + augmenting actions).

Templates are org rows plus code-resident built-ins (``builtin:<key>``,
read-only; clone one to edit). Creating, editing and deleting org playbooks
needs ``templates:manage``; activating one on an incident needs
``incidents:update``.
"""
import copy
import re

from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Playbook, IncidentPlaybook
from app.middleware.rbac import require_permission, require_incident_access, get_current_user
from app.middleware.audit import audit_log
from app.services import builtin_templates, realtime
from app.services.case_template_service import TemplateError, check_body_size
from app.services.playbook_service import ACTION_SCOPES, PlaybookService, validate_definition
from app.utils.audit_diff import record_changes, snapshot
from app.utils.concurrency import commit_or_conflict, precondition, set_etag

PLAYBOOK_AUDIT_FIELDS = ('name', 'description', 'incident_type', 'is_template', 'definition')
BUILTIN_KEY_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,63}$')


def _pb_item(pb):
    data = pb.to_dict()
    data['is_builtin'] = False
    data['builtin_key'] = None
    return data


def _text_error(data, *, creating):
    """First problem with the plain fields of a playbook body, or None."""
    name = data.get('name')
    if creating or 'name' in data:
        if not isinstance(name, str) or not name.strip():
            return 'name is required' if creating else 'name must be a non-empty string'
        if len(name) > 255:
            return 'name must be at most 255 characters'
    if data.get('description') is not None and (not isinstance(data['description'], str)
                                                or len(data['description']) > 5000):
        return 'description must be a string of at most 5000 characters'
    if data.get('incident_type') is not None and (not isinstance(data['incident_type'], str)
                                                  or len(data['incident_type']) > 100):
        return 'incident_type must be a string of at most 100 characters'
    if 'is_template' in data and not isinstance(data['is_template'], bool):
        return 'is_template must be a boolean'
    return None


def _json_body():
    """The request body as a dict (size-capped), or a 400 response tuple."""
    try:
        check_body_size(request)
    except TemplateError as exc:
        return None, (jsonify(exc.to_dict()), exc.status)
    data = request.get_json(silent=True)
    return (data if isinstance(data, dict) else {}), None


# --------------------------------------------------------------------------
# Playbook templates (org-scoped + built-in)
# --------------------------------------------------------------------------

@api_bp.route('/playbooks', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def list_playbooks():
    """Org playbooks (newest first) followed by the built-ins
    (``id: "builtin:<key>"``, ``is_builtin: true``); ``include_builtin=false``
    returns the org rows only."""
    user = get_current_user()
    pbs = Playbook.query.filter_by(organization_id=user.organization_id).order_by(Playbook.created_at.desc()).all()
    items = [_pb_item(p) for p in pbs]
    if (request.args.get('include_builtin') or 'true').lower() not in ('false', '0', 'no'):
        items += sorted(builtin_templates.load_playbooks().values(), key=lambda p: p['name'].casefold())
    return jsonify({'items': items, 'total': len(items)}), 200


@api_bp.route('/playbooks/builtin/<string:key>', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def get_builtin_playbook(key):
    data = builtin_templates.get_playbook(key) if BUILTIN_KEY_RE.match(key) else None
    if data is None:
        return jsonify({'error': 'not_found', 'message': 'Built-in playbook not found'}), 404
    return jsonify(data), 200


@api_bp.route('/playbooks/builtin/<string:key>/clone', methods=['POST'])
@jwt_required()
@require_permission('templates:manage')
@audit_log('admin_action', 'clone_playbook', 'playbook')
def clone_builtin_playbook(key):
    """Copy a built-in playbook into an editable org playbook
    (``cloned_from: "builtin:<key>"``; optional body ``{name}``)."""
    user = get_current_user()
    source = builtin_templates.get_playbook(key) if BUILTIN_KEY_RE.match(key) else None
    if source is None:
        return jsonify({'error': 'not_found', 'message': 'Built-in playbook not found'}), 404
    data, err = _json_body()
    if err:
        return err
    name = data.get('name') or f"{source['name']} (copy)"
    problem = _text_error({'name': name}, creating=True)
    if problem:
        return jsonify({'error': 'bad_request', 'message': problem}), 400
    pb = Playbook(
        organization_id=user.organization_id, name=name.strip(), description=source['description'],
        incident_type=source['incident_type'], definition=copy.deepcopy(source['definition']),
        is_template=True, cloned_from=f'builtin:{key}', created_by=user.id)
    db.session.add(pb)
    db.session.commit()
    return jsonify(_pb_item(pb)), 201


@api_bp.route('/playbooks', methods=['POST'])
@jwt_required()
@require_permission('templates:manage')
@audit_log('admin_action', 'create_playbook', 'playbook')
def create_playbook():
    user = get_current_user()
    data, err = _json_body()
    if err:
        return err
    problem = _text_error(data, creating=True)
    if problem:
        return jsonify({'error': 'bad_request', 'message': problem}), 400
    valid, msg = validate_definition(data.get('definition'))
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
    return jsonify(_pb_item(pb)), 201


@api_bp.route('/playbooks/<uuid:playbook_id>', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def get_playbook(playbook_id):
    user = get_current_user()
    pb = Playbook.query.filter_by(id=playbook_id, organization_id=user.organization_id).first()
    if not pb:
        return jsonify({'error': 'not_found', 'message': 'Playbook not found'}), 404
    return jsonify(_pb_item(pb)), 200


@api_bp.route('/playbooks/<uuid:playbook_id>', methods=['PUT'])
@jwt_required()
@require_permission('templates:manage')
@audit_log('admin_action', 'update_playbook', 'playbook')
def update_playbook(playbook_id):
    user = get_current_user()
    pb = Playbook.query.filter_by(id=playbook_id, organization_id=user.organization_id).first()
    if not pb:
        return jsonify({'error': 'not_found', 'message': 'Playbook not found'}), 404
    data, err = _json_body()
    if err:
        return err
    problem = _text_error(data, creating=False)
    if problem:
        return jsonify({'error': 'bad_request', 'message': problem}), 400
    if 'definition' in data:
        valid, msg = validate_definition(data['definition'])
        if not valid:
            return jsonify({'error': 'bad_request', 'message': msg}), 400
    before = snapshot(pb, PLAYBOOK_AUDIT_FIELDS)
    for field in ['name', 'description', 'incident_type', 'definition', 'is_template']:
        if field in data:
            setattr(pb, field, data[field].strip() if field == 'name' else data[field])
    record_changes(before, snapshot(pb, PLAYBOOK_AUDIT_FIELDS))
    db.session.commit()
    return jsonify(_pb_item(pb)), 200


@api_bp.route('/playbooks/<uuid:playbook_id>', methods=['DELETE'])
@jwt_required()
@require_permission('templates:manage')
@audit_log('admin_action', 'delete_playbook', 'playbook')
def delete_playbook(playbook_id):
    user = get_current_user()
    pb = Playbook.query.filter_by(id=playbook_id, organization_id=user.organization_id).first()
    if not pb:
        return jsonify({'error': 'not_found', 'message': 'Playbook not found'}), 404
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

    inst, runs = PlaybookService.activate(incident, name=pb.name, definition=pb.definition or {}, user=user,
                                          playbook_id=pb.id)
    realtime.emit_change(incident.id, 'playbook', 'created', obj=inst)
    return jsonify({'incident_playbook': inst.to_dict(), 'actions_executed': runs}), 201


@api_bp.route('/incidents/<uuid:incident_id>/playbooks/builtin/<string:key>/activate', methods=['POST'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'activate_playbook', 'incident')
def activate_builtin_playbook(incident_id, key):
    """Activate a built-in playbook (snapshotted on the incident; ``builtin_key``
    is recorded and ``playbook_id`` stays null). Built-ins have no auto-run
    actions."""
    incident = g.incident
    user = get_current_user()
    data = builtin_templates.get_playbook(key) if BUILTIN_KEY_RE.match(key) else None
    if data is None:
        return jsonify({'error': 'not_found', 'message': 'Built-in playbook not found'}), 404
    inst, runs = PlaybookService.activate(incident, name=data['name'], definition=copy.deepcopy(data['definition']),
                                          user=user, builtin_key=key)
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
    runs = PlaybookService.run_auto_actions(inst, incident, inst.current_phase, user)
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
    PlaybookService.record_run(inst, action, result)
    db.session.commit()
    realtime.emit_change(incident.id, 'playbook', 'updated', obj=inst)
    if ACTION_SCOPES.get(action.get('type')):
        realtime.emit_resync(incident.id, ACTION_SCOPES[action.get('type')], 'playbook_action')
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
