"""Platform settings: admin-configurable rate limits (W4-RL).

    GET  /system/rate-limits         organizations:manage or platform admin
    PUT  /system/rate-limits         platform admin; {enabled, groups, version, confirm_weakening?}
    POST /system/rate-limits/reset   platform admin; optional {groups: [...]}

Rate limits protect every tenant (sign-in is limited before any organization
is known), so only platform administrators may change them. These three
routes use a fixed limit that no setting can change, so a bad configuration
can never lock the administrator out of fixing it.
"""
from types import SimpleNamespace

from flask import jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError

from app import db, limiter
from app.api.v1 import api_bp
from app.middleware.audit import audit_log, log_security_event
from app.middleware.rbac import get_current_user, is_platform_admin, require_platform_admin
from app.models.system_setting import SystemSetting
from app.services import rate_limit_settings as rls
from app.utils.audit_diff import record_changes
from app.utils.concurrency import commit_or_conflict, conflict_response, precondition, set_etag

# Fixed on purpose: not a group, not configurable (see module docstring).
SETTINGS_ROUTE_LIMIT = '30 per minute'


def _row():
    return SystemSetting.query.filter_by(key=rls.SETTINGS_KEY).first()


def _payload(user):
    row = _row()
    locked = rls.is_locked()
    return {
        'enabled': rls.global_enabled(),
        'locked': locked,
        'hard_disabled': rls.hard_disabled(),
        'can_edit': bool(user and is_platform_admin(user)) and not locked,
        'version': row.version if row is not None else 0,
        'updated_at': row.updated_at.isoformat() if row is not None and row.updated_at else None,
        'cache_ttl_seconds': rls.CACHE_TTL,
        'groups': rls.describe(),
    }


def _snapshot(doc):
    """Flat view for the audit diff: {enabled, <group>.limit, <group>.enabled}."""
    flat = {'enabled': doc.get('enabled', True)}
    for key, ov in (doc.get('groups') or {}).items():
        if 'limit' in ov:
            flat[f'{key}.limit'] = ov['limit']
        if 'enabled' in ov:
            flat[f'{key}.enabled'] = ov['enabled']
    return flat


@api_bp.route('/system/rate-limits', methods=['GET'])
@jwt_required()
@limiter.limit(SETTINGS_ROUTE_LIMIT, override_defaults=True)
def get_rate_limits():
    user = get_current_user()
    if not user or not (user.has_permission('organizations:manage') or is_platform_admin(user)):
        return jsonify({'error': 'forbidden', 'message': 'Permission denied. Required: organizations:manage'}), 403
    rls.invalidate()  # always show what is in force now, not a 5-second-old snapshot
    return jsonify(_payload(user)), 200


@api_bp.route('/system/rate-limits', methods=['PUT'])
@jwt_required()
@require_platform_admin
@limiter.limit(SETTINGS_ROUTE_LIMIT, override_defaults=True)
@audit_log('admin_action', 'rate_limits_update', 'system_setting')
def update_rate_limits():
    """Replace the override document. 400 validation_error {fields};
    409 settings_locked; 409 confirmation_required {warnings} when the change
    weakens protection and ``confirm_weakening`` is not true; 409 conflict on
    a stale version; 428 without a version."""
    user = get_current_user()
    if rls.is_locked():
        return jsonify({'error': 'settings_locked',
                        'message': 'Rate limits are managed by the environment (RATE_LIMIT_SETTINGS_LOCKED).'}), 409
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'error': 'validation_error', 'message': 'JSON object required', 'fields': {}}), 400
    row = _row()
    conflict = precondition(row if row is not None else SimpleNamespace(version=0), required=True,
                            body_key='version', serializer=lambda _o: _payload(user))
    if conflict:
        return conflict
    try:
        doc, warnings = rls.validate({'enabled': body.get('enabled', True), 'groups': body.get('groups') or {}})
    except rls.RateLimitSettingsError as e:
        return jsonify({'error': 'validation_error', 'message': str(e), 'fields': e.fields}), 400
    confirmed = body.get('confirm_weakening') is True
    if warnings and not confirmed:
        return jsonify({'error': 'confirmation_required',
                        'message': 'This change weakens rate limiting. Confirm to apply it.',
                        'warnings': warnings}), 409

    before = dict(row.value) if row is not None else {}
    if row is None:
        row = SystemSetting(key=rls.SETTINGS_KEY, value=doc, updated_by=user.id, updated_at=db.func.now())
        db.session.add(row)
    else:
        row.value, row.updated_by, row.updated_at = doc, user.id, db.func.now()
    try:
        conflict = commit_or_conflict(row, serializer=lambda _o: _payload(user))
    except IntegrityError:  # concurrent first save
        db.session.rollback()
        return conflict_response(None)
    if conflict:
        return conflict
    rls.invalidate(doc)
    record_changes(_snapshot(before), _snapshot(doc), warnings=warnings, confirmed=confirmed)
    if warnings:
        log_security_event('rate_limits_weakened', resource_type='system_setting', resource_id=row.id,
                           details={'warnings': warnings})
    return set_etag(jsonify(_payload(user)), row), 200


@api_bp.route('/system/rate-limits/reset', methods=['POST'])
@jwt_required()
@require_platform_admin
@limiter.limit(SETTINGS_ROUTE_LIMIT, override_defaults=True)
@audit_log('admin_action', 'rate_limits_reset', 'system_setting')
def reset_rate_limits():
    """Remove all overrides, or only those of ``{groups: [...]}``."""
    user = get_current_user()
    if rls.is_locked():
        return jsonify({'error': 'settings_locked',
                        'message': 'Rate limits are managed by the environment (RATE_LIMIT_SETTINGS_LOCKED).'}), 409
    body = request.get_json(silent=True) or {}
    only = body.get('groups')
    if only is not None and (not isinstance(only, list) or any(g not in rls.GROUPS for g in only)):
        return jsonify({'error': 'validation_error', 'message': 'groups must list known groups',
                        'fields': {'groups': 'Unknown group'}}), 400
    row = _row()
    if row is None:
        return jsonify(_payload(user)), 200
    before = dict(row.value or {})
    if only is None:
        doc = {'enabled': True, 'groups': {}}
    else:
        doc = {'enabled': before.get('enabled', True),
               'groups': {k: v for k, v in (before.get('groups') or {}).items() if k not in only}}
    row.value, row.updated_by, row.updated_at = doc, user.id, db.func.now()
    conflict = commit_or_conflict(row, serializer=lambda _o: _payload(user))
    if conflict:
        return conflict
    rls.invalidate(doc)
    record_changes(_snapshot(before), _snapshot(doc), reset=only or 'all')
    return set_etag(jsonify(_payload(user)), row), 200
