"""Organization management endpoints (settings + security policy)"""
from datetime import datetime, timezone
from types import SimpleNamespace

from flask import g, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.v1 import api_bp
from app import db
from app.models import Organization
from app.middleware.rbac import require_permission, get_current_user
from app.middleware.audit import audit_log, log_security_event
from app.schemas.organization import (
    AI_POLICY_RANK, OrganizationUpdate, OrgSettings, PUBLIC_SETTING_KEYS, effective_ai_tlp_policy,
)
from app.services import security_policy
from app.utils.audit_diff import record_changes
from app.utils.concurrency import commit_or_conflict, conflict_response, precondition, set_etag

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


# ── Security policy (services/security_policy.py) ──────────────────────

def _policy_payload(org):
    from app.models import User
    row = security_policy.policy_row(org.id)
    policy = security_policy.get_policy(org.id)
    updated_by = None
    if row is not None and row.updated_by:
        actor = db.session.get(User, row.updated_by)
        updated_by = {'id': str(row.updated_by), 'name': actor.name if actor else None}
    return {
        'id': str(row.id) if row is not None else None,
        'organization_id': str(org.id),
        'policy': security_policy.serialize(policy),
        'version': row.version if row is not None else 0,
        'defaults': security_policy.serialize(security_policy.default_policy()),
        'bounds': security_policy.BOUNDS,
        'stats': security_policy.stats(org.id),
        'is_platform_org': security_policy.is_platform_org(org),
        'updated_by': updated_by,
        'updated_at': row.updated_at.isoformat() if row is not None and row.updated_at else None,
    }


def _current_org():
    user = get_current_user()
    return user, (db.session.get(Organization, user.organization_id) if user else None)


@api_bp.route('/organization/security-policy', methods=['GET'])
@jwt_required()
@require_permission('organizations:manage')
def get_security_policy():
    """The caller's org security policy with defaults, bounds and MFA stats."""
    _, org = _current_org()
    if not org:
        return jsonify({'error': 'not_found', 'message': 'Organization not found'}), 404
    payload = _policy_payload(org)
    return set_etag(jsonify(payload), SimpleNamespace(version=payload['version'])), 200


@api_bp.route('/organization/security-policy', methods=['PUT'])
@jwt_required()
@require_permission('organizations:manage')
@audit_log('admin_action', 'security_policy_update', 'organization_security_policy')
def update_security_policy():
    """Body ``{policy: {<section>: {...}}, version}`` (or If-Match). Sections
    and fields not sent keep their value. 400 validation_error {fields},
    409 conflict on a stale version, 428 without a version."""
    user, org = _current_org()
    if not org:
        return jsonify({'error': 'not_found', 'message': 'Organization not found'}), 404
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'error': 'validation_error', 'message': 'JSON object required', 'fields': {}}), 400

    row = security_policy.policy_row(org.id)
    serializer = lambda _obj: _policy_payload(org)  # noqa: E731
    conflict = precondition(row if row is not None else SimpleNamespace(version=0), required=True,
                            body_key='version', serializer=serializer)
    if conflict:
        return conflict

    try:
        row, before, after = security_policy.update_policy(org, body.get('policy'), user)
    except security_policy.PolicyValidationError as e:
        db.session.rollback()
        return jsonify({'error': 'validation_error', 'message': e.message, 'fields': e.fields}), 400
    try:
        conflict = commit_or_conflict(row, serializer=serializer)
    except IntegrityError:  # concurrent first save of this org's row
        db.session.rollback()
        return conflict_response(None)
    if conflict:
        return conflict
    security_policy.invalidate_cache()

    changes = security_policy.policy_changes(before, after)
    g.audit_changes = {**(getattr(g, 'audit_changes', None) or {}), **changes}
    return set_etag(jsonify(_policy_payload(org)), row), 200
