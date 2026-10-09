"""Organization management endpoints"""
from datetime import datetime, timezone

from flask import jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import ValidationError

from app.api.v1 import api_bp
from app import db
from app.models import Organization
from app.middleware.rbac import require_permission, get_current_user
from app.middleware.audit import audit_log, log_security_event
from app.schemas.organization import (
    AI_POLICY_RANK, OrganizationUpdate, OrgSettings, PUBLIC_SETTING_KEYS, effective_ai_tlp_policy,
)
from app.utils.audit_diff import record_changes

DEFAULT_ORG_SLUG = 'default'  # where self-registration / SSO sign-ups land


def _org_payload(org, user):
    stored = org.settings or {}
    settings = {k: stored[k] for k in PUBLIC_SETTING_KEYS if k in stored}
    settings['ai_tlp_policy'] = effective_ai_tlp_policy(stored.get('ai_tlp_policy'))
    body = {
        'id': str(org.id),
        'name': org.name,
        'slug': org.slug,
        'is_default': org.slug == DEFAULT_ORG_SLUG,
        'settings': settings,
        'updated_at': org.updated_at.isoformat() if org.updated_at else None,
    }
    if body['is_default'] and user.has_permission('organizations:manage'):
        body['registration_enabled'] = bool(stored.get('registration_enabled', False))
    return body


def _audit_view(org):
    """Flat snapshot for the before/after diff of every writable key."""
    stored = org.settings or {}
    view = {'name': org.name}
    for key in OrgSettings.model_fields:
        if key == 'ai_tlp_policy':
            view['settings.ai_tlp_policy'] = effective_ai_tlp_policy(stored.get('ai_tlp_policy'))
        else:
            view[f'settings.{key}'] = stored.get(key)
    return view


@api_bp.route('/organization', methods=['GET'])
@jwt_required()
def get_organization():
    """Current user's organization with allow-listed settings only."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'unauthorized', 'message': 'Authentication required'}), 401
    org = db.session.get(Organization, user.organization_id)
    if not org:
        return jsonify({'error': 'not_found', 'message': 'Organization not found'}), 404
    return jsonify(_org_payload(org, user)), 200


@api_bp.route('/organization', methods=['PUT'])
@jwt_required()
@require_permission('organizations:manage')
@audit_log('admin_action', 'update', 'organization')
def update_organization():
    """Validate and merge organization settings (see schemas/organization.py)."""
    user = get_current_user()
    org = db.session.get(Organization, user.organization_id)
    if not org:
        return jsonify({'error': 'not_found', 'message': 'Organization not found'}), 404

    raw = request.get_json(silent=True)
    if not isinstance(raw, dict):
        return jsonify({'error': 'validation_error', 'message': 'JSON object required', 'fields': {}}), 400
    try:
        update = OrganizationUpdate.model_validate(raw)
    except ValidationError as e:
        fields = {'.'.join(str(p) for p in err['loc']): err['msg'] for err in e.errors()}
        return jsonify({'error': 'validation_error', 'message': 'Invalid organization settings',
                        'fields': fields}), 400

    new_settings = update.settings.model_dump(exclude_unset=True) if update.settings else {}
    if 'registration_enabled' in new_settings and org.slug != DEFAULT_ORG_SLUG:
        return jsonify({'error': 'not_applicable',
                        'message': 'Registration can only be configured on the default organization',
                        'fields': {'settings.registration_enabled': 'Only applies to the default organization'}}), 400

    before = _audit_view(org)
    if update.name is not None:
        org.name = update.name
    if new_settings:
        merged = dict(org.settings or {})
        if 'ai_tlp_policy' in new_settings:
            stored_policy = merged.get('ai_tlp_policy')
            policy = dict(stored_policy) if isinstance(stored_policy, dict) else {}
            policy.update(new_settings.pop('ai_tlp_policy') or {})
            merged['ai_tlp_policy'] = policy
        merged.update(new_settings)
        org.settings = merged
    org.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    after = _audit_view(org)
    record_changes(before, after)

    old_policy, new_policy = before['settings.ai_tlp_policy'], after['settings.ai_tlp_policy']
    loosened = {lvl: {'from': old_policy[lvl], 'to': new_policy[lvl]} for lvl in new_policy
                if AI_POLICY_RANK[new_policy[lvl]] > AI_POLICY_RANK[old_policy[lvl]]}
    if loosened:
        log_security_event('ai_tlp_policy_loosened', resource_type='organization', resource_id=org.id,
                           details={'levels': loosened})

    return jsonify(_org_payload(org, user)), 200
