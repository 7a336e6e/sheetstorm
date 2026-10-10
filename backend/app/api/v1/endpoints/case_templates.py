"""Case templates: built-in + org templates, apply to an incident, custom fields.

Reads need ``incidents:read``. Writing org templates needs ``templates:manage``;
built-ins are read-only by construction (no write path exists; a PUT / DELETE
on one is a 403). Applying a template to an incident needs ``incidents:update``
and is a rate-limited, idempotent merge (see services/case_template_service).
"""
from datetime import datetime, timezone

from flask import g, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.services.rate_limit_settings import limited
from app import db
from app.api.v1 import api_bp
from app.middleware.audit import audit_log
from app.middleware.rbac import get_current_user, require_incident_access, require_permission
from app.models import CaseTemplate, IncidentCaseTemplate
from app.schemas.case_template import ApplyOptions, CaseTemplateUpdate, CaseTemplateWrite
from app.services import builtin_templates, case_template_service as cts, realtime
from app.services.case_template_service import TemplateError
from app.services.playbook_service import PlaybookService
from app.utils.audit_diff import record_changes, snapshot
from app.utils.concurrency import commit_or_conflict, precondition, set_etag

TEMPLATE_AUDIT_FIELDS = ('name', 'description', 'incident_type', 'is_active', 'definition')


def _fail(exc):
    return jsonify(exc.to_dict()), exc.status


def _not_found():
    return jsonify({'error': 'not_found', 'message': 'Case template not found'}), 404


def _item(data, *, with_definition):
    """List/detail shape shared by built-in dicts and org rows."""
    item = dict(data)
    item['summary'] = cts.summary_counts(item.get('definition'))
    if not with_definition:
        item.pop('definition', None)
    return item


def _org_item(row, *, with_definition=True):
    return _item(row.to_dict(), with_definition=with_definition)


def _body():
    cts.check_body_size(request)
    return request.get_json(silent=True)


def _org_row(org_id, template_ref):
    parsed = cts.parse_ref(template_ref)
    if parsed is None:
        return None, None
    kind, ident = parsed
    if kind == 'builtin':
        return 'builtin', ident
    return 'org', CaseTemplate.query.filter_by(id=ident, organization_id=org_id).first()


# ── Templates ────────────────────────────────────────────────────────────

@api_bp.route('/case-templates', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def list_case_templates():
    """Built-in templates (``id: "builtin:<key>"``, ``is_builtin: true``) and
    the organization's. Deactivated org templates are listed only with
    ``include_inactive=true`` and only for ``templates:manage`` holders.
    ``include_definition=true`` embeds the definitions (the list otherwise
    carries a ``summary`` of counts)."""
    user = get_current_user()
    with_def = (request.args.get('include_definition') or '').lower() in ('true', '1')
    include_inactive = ((request.args.get('include_inactive') or '').lower() in ('true', '1')
                        and user.has_permission('templates:manage'))
    disabled = cts.disabled_builtins(user.organization_id)
    items = []
    for t in sorted(builtin_templates.load_case_templates().values(), key=lambda t: t['name'].casefold()):
        active = t['key'] not in disabled
        if active or include_inactive:
            items.append({**_item(t, with_definition=with_def), 'is_active': active})
    query = CaseTemplate.query.filter_by(organization_id=user.organization_id)
    if not include_inactive:
        query = query.filter_by(is_active=True)
    items += [_org_item(r, with_definition=with_def) for r in query.order_by(CaseTemplate.name.asc()).all()]
    return jsonify({'items': items, 'total': len(items)}), 200


@api_bp.route('/case-templates/<string:template_ref>', methods=['GET'])
@jwt_required()
@require_permission('incidents:read')
def get_case_template(template_ref):
    """One template with its definition and ``resolved`` names behind the refs.
    Org templates are returned with an ``ETag`` (their version)."""
    user = get_current_user()
    kind, found = _org_row(user.organization_id, template_ref)
    if kind is None or (kind == 'org' and found is None):
        return _not_found()
    if kind == 'builtin':
        data = builtin_templates.get_case_template(found)
        if data is None:
            return _not_found()
        item = {**_item(data, with_definition=True),
                'is_active': found not in cts.disabled_builtins(user.organization_id)}
        row = None
    else:
        if not found.is_active and not user.has_permission('templates:manage'):
            return _not_found()
        item = _org_item(found)
        row = found
    item['resolved'] = cts.describe(item.get('definition'), user.organization_id)
    resp = jsonify(item)
    return (set_etag(resp, row) if row is not None else resp), 200


@api_bp.route('/case-templates', methods=['POST'])
@jwt_required()
@require_permission('templates:manage')
@audit_log('admin_action', 'create', 'case_template')
def create_case_template():
    """Create an org template. ``definition`` is validated against the
    schema; library refs, built-in playbooks and ``playbook_id`` ownership are
    checked. 409 ``duplicate_key`` when the key exists in the organization."""
    user = get_current_user()
    try:
        body = cts.validate_body(_body(), CaseTemplateWrite, user.organization_id)
    except TemplateError as exc:
        return _fail(exc)
    if CaseTemplate.query.filter_by(organization_id=user.organization_id, key=body.key).first():
        return jsonify({'error': 'duplicate_key', 'message': 'A template with this key already exists'}), 409
    row = CaseTemplate(
        organization_id=user.organization_id, key=body.key, name=body.name, description=body.description,
        incident_type=body.incident_type, is_active=body.is_active,
        definition=cts.definition_json(body.definition), created_by=user.id, updated_by=user.id)
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'duplicate_key', 'message': 'A template with this key already exists'}), 409
    return set_etag(jsonify(_org_item(row)), row), 201


@api_bp.route('/case-templates/<string:template_ref>', methods=['PUT'])
@jwt_required()
@require_permission('templates:manage')
@audit_log('admin_action', 'update', 'case_template')
def update_case_template(template_ref):
    """Edit an org template (key is immutable). Every update bumps
    ``version``; ``If-Match`` / ``expected_version`` guard against lost
    updates. Built-ins are read-only (403)."""
    user = get_current_user()
    kind, row = _org_row(user.organization_id, template_ref)
    if kind is None or (kind == 'org' and row is None):
        return _not_found()
    if kind == 'builtin':
        return _update_builtin(user, row)
    try:
        body = cts.validate_body(_body(), CaseTemplateUpdate, user.organization_id)
    except TemplateError as exc:
        return _fail(exc)
    conflict = precondition(row)
    if conflict:
        return conflict, conflict.status_code
    before = snapshot(row, TEMPLATE_AUDIT_FIELDS)
    for field in ('name', 'description', 'incident_type', 'is_active'):
        if field in body.model_fields_set and getattr(body, field) is not None:
            setattr(row, field, getattr(body, field))
    if 'description' in body.model_fields_set and body.description is None:
        row.description = None
    if 'incident_type' in body.model_fields_set and body.incident_type is None:
        row.incident_type = None
    if body.definition is not None:
        row.definition = cts.definition_json(body.definition)
    row.updated_by = user.id
    row.updated_at = datetime.now(timezone.utc)
    record_changes(before, snapshot(row, TEMPLATE_AUDIT_FIELDS))
    conflict = commit_or_conflict(row)
    if conflict:
        return conflict, conflict.status_code
    return set_etag(jsonify(_org_item(row)), row), 200


def _update_builtin(user, key):
    """Built-ins are read-only except ``{is_active}``: an organization can
    switch one off (e.g. after customizing a copy). Anything else is 403."""
    from app.models import Organization
    data = builtin_templates.get_case_template(key)
    if data is None:
        return _not_found()
    body = _body()
    if not isinstance(body, dict) or set(body) - {'is_active', 'expected_version'} \
            or not isinstance(body.get('is_active'), bool):
        return jsonify({'error': 'forbidden',
                        'message': 'Built-in templates are read-only; customize a copy instead. '
                                   'Only is_active can be changed.'}), 403
    org = db.session.get(Organization, user.organization_id)
    was_active = cts.set_builtin_active(org, key, body['is_active'])
    record_changes({'is_active': was_active}, {'is_active': body['is_active']}, template=f'builtin:{key}')
    db.session.commit()
    return jsonify({**_item(data, with_definition=False), 'is_active': body['is_active']}), 200


@api_bp.route('/case-templates/<string:template_ref>', methods=['DELETE'])
@jwt_required()
@require_permission('templates:manage')
@audit_log('admin_action', 'delete', 'case_template')
def delete_case_template(template_ref):
    """Delete an org template. Incidents it was applied to keep their ledger
    snapshot (the link is set to NULL). Built-ins cannot be deleted (403)."""
    user = get_current_user()
    kind, row = _org_row(user.organization_id, template_ref)
    if kind is None or (kind == 'org' and row is None):
        return _not_found()
    if kind == 'builtin':
        if builtin_templates.get_case_template(row) is None:
            return _not_found()
        return jsonify({'error': 'forbidden', 'message': 'Built-in templates cannot be deleted'}), 403
    conflict = precondition(row)
    if conflict:
        return conflict, conflict.status_code
    template_id = str(row.id)
    db.session.delete(row)
    conflict = commit_or_conflict(row)
    if conflict:
        return conflict, conflict.status_code
    return jsonify({'message': 'Case template deleted', 'id': template_id}), 200


@api_bp.route('/case-templates/<string:template_ref>/clone', methods=['POST'])
@jwt_required()
@require_permission('templates:manage')
@audit_log('admin_action', 'clone', 'case_template')
def clone_case_template(template_ref):
    """Copy a built-in or org template into a new org template
    (``<key>-copy[-n]``; optional body ``{name}``)."""
    user = get_current_user()
    tpl = None
    try:
        tpl = cts.resolve(user.organization_id, template_ref, require_active=False)
    except TemplateError as exc:
        return _fail(exc)
    if tpl is None:
        return _not_found()
    payload = request.get_json(silent=True)
    name = payload.get('name') if isinstance(payload, dict) else None
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 255):
        return jsonify({'error': 'validation_error', 'message': 'name must be a non-empty string of at most 255 characters'}), 400
    source = builtin_templates.get_case_template(tpl.key) if tpl.kind == 'builtin' else None
    row = CaseTemplate(
        organization_id=user.organization_id, key=cts.clone_key(user.organization_id, tpl.key),
        name=(name or f'{tpl.name} (copy)').strip()[:255],
        description=(source['description'] if source else tpl.row.description),
        incident_type=(source['incident_type'] if source else tpl.row.incident_type),
        definition=cts.definition_json(tpl.definition), is_active=True,
        cloned_from=tpl.ref, created_by=user.id, updated_by=user.id)
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'duplicate_key', 'message': 'Could not allocate a free key; retry'}), 409
    return set_etag(jsonify(_org_item(row)), row), 201


# ── Apply to an incident ─────────────────────────────────────────────────

@api_bp.route('/incidents/<uuid:incident_id>/case-templates/<string:template_ref>/apply', methods=['POST'])
@limited('template_apply')
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'apply_case_template', 'incident')
def apply_case_template(incident_id, template_ref):
    """Apply a template to the incident (idempotent merge).

    Body (all optional): ``apply_defaults`` (raise TLP / severity, set an
    empty classification), ``include`` (any of questions, leads, playbook,
    custom_fields), ``dry_run`` (compute and roll back), ``run_auto_actions``
    (run ``auto_run`` actions of the activated playbook; never by default).
    Leads are skipped (``forbidden``) without ``tasks:create``; an incident
    that already has an active playbook keeps it.
    """
    user = get_current_user()
    incident = g.incident
    raw = _body()
    try:
        options = ApplyOptions.model_validate(raw if raw is not None else {})
    except ValidationError as exc:
        return jsonify({'error': 'validation_error', 'message': 'Invalid options',
                        'fields': {'.'.join(str(p) for p in e['loc']): e['msg'] for e in exc.errors()}}), 400
    try:
        tpl = cts.resolve(user.organization_id, template_ref)
    except TemplateError as exc:
        return _fail(exc)
    if tpl is None:
        return _not_found()

    fields = ('severity', 'tlp', 'classification')
    before = snapshot(incident, fields)
    result = cts.apply(incident, tpl, user, apply_defaults=options.apply_defaults, include=options.include,
                       dry_run=options.dry_run)
    body = cts.public_result(result)
    body['template'] = {'ref': tpl.ref, 'key': tpl.key, 'name': tpl.name, 'version': tpl.version}
    if options.dry_run:
        return jsonify(body), 200

    record_changes(before, snapshot(incident, fields), template=tpl.ref, created=result['created'])
    instance = result['playbook_instance']
    db.session.commit()

    runs = []
    if instance is not None:
        if options.run_auto_actions:
            runs = PlaybookService.run_auto_actions(instance, incident, instance.current_phase, user)
        realtime.emit_change(incident.id, 'playbook', 'created', obj=instance)
    body['actions_executed'] = runs
    realtime.emit_resync(incident.id, ['questions', 'tasks', 'playbook'], 'case_template_applied')
    if result['defaults_applied'] or result['custom_fields_added']:
        realtime.emit_change(incident.id, 'incident', 'updated', obj=incident,
                             data=incident.to_dict(include_counts=True))
    return jsonify(body), 200


@api_bp.route('/incidents/<uuid:incident_id>/case-templates', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def list_incident_case_templates(incident_id):
    """The incident's template application ledger (newest first)."""
    rows = (IncidentCaseTemplate.query.filter_by(incident_id=g.incident.id)
            .order_by(IncidentCaseTemplate.applied_at.desc()).all())
    return jsonify({'items': [r.to_dict() for r in rows], 'total': len(rows)}), 200


# ── Custom fields ────────────────────────────────────────────────────────

@api_bp.route('/incidents/<uuid:incident_id>/custom-fields', methods=['GET'])
@jwt_required()
@require_incident_access('incidents:read')
def get_custom_fields(incident_id):
    """``{definitions, values}``: the field definitions snapshotted by the
    applied templates and the values stored on the incident."""
    incident = g.incident
    return set_etag(jsonify({'definitions': cts.custom_field_definitions(incident.id),
                             'values': incident.custom_fields or {}}), incident), 200


@api_bp.route('/incidents/<uuid:incident_id>/custom-fields', methods=['PUT'])
@jwt_required()
@require_incident_access('incidents:update')
@audit_log('data_modification', 'update_custom_fields', 'incident')
def put_custom_fields(incident_id):
    """Set custom-field values: ``{values: {key: value}}``. Keys not defined
    by an applied template are rejected; a ``null`` value clears the key.
    Types and select options are validated; text is capped at 2000 chars."""
    incident = g.incident
    raw = request.get_json(silent=True)
    if not isinstance(raw, dict) or set(raw) - {'values', 'expected_version'}:
        return jsonify({'error': 'validation_error',
                        'message': 'Body must be {"values": {...}} (optionally expected_version)'}), 400
    try:
        values = cts.validate_custom_values(cts.custom_field_definitions(incident.id), raw.get('values'))
    except TemplateError as exc:
        return _fail(exc)
    conflict = precondition(incident)
    if conflict:
        return conflict, conflict.status_code
    current = dict(incident.custom_fields or {})
    merged = dict(current)
    for key, value in values.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    record_changes({'custom_fields': current}, {'custom_fields': merged})
    incident.custom_fields = merged
    conflict = commit_or_conflict(incident)
    if conflict:
        return conflict, conflict.status_code
    realtime.emit_change(incident.id, 'incident', 'updated', obj=incident,
                         data=incident.to_dict(include_counts=True))
    return set_etag(jsonify({'definitions': cts.custom_field_definitions(incident.id),
                             'values': incident.custom_fields or {}}), incident), 200
