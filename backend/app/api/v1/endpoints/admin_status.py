"""Admin landing data: system status and the admin overview."""
from flask import jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func

from app import db, limiter
from app.api.v1 import api_bp
from app.middleware.rbac import get_current_user, is_platform_admin, require_permission
from app.models import AuditLog, Organization, Role, User, UserRole
from app.services.system_status_service import collect_system_status

RECENT_ADMIN_ACTIONS = 10


@api_bp.route('/admin/system-status', methods=['GET'])
@jwt_required()
@require_permission('organizations:manage')
@limiter.limit("30 per minute")  # rl-group: admin_status
def get_system_status():
    """Organization status sections; deployment-global infra sections
    (database, migrations, disk, Redis, rate limiter, version) only for
    platform admins."""
    user = get_current_user()
    org = db.session.get(Organization, user.organization_id)
    if not org:
        return jsonify({'error': 'not_found', 'message': 'Organization not found'}), 404
    return jsonify(collect_system_status(org, include_infra=is_platform_admin(user))), 200


def _user_overview(org):
    from app.services.rbac_guard import admin_holders
    from app.services.user_lifecycle import overview_counts

    base = User.query.filter(User.organization_id == org.id)
    total = base.count()
    active = base.filter(User.is_active.is_(True)).count()
    mfa_enabled = base.filter(User.is_active.is_(True), User.mfa_enabled.is_(True)).count()

    by_role = dict(
        db.session.query(Role.name, func.count(func.distinct(User.id)))
        .join(UserRole, UserRole.role_id == Role.id)
        .join(User, User.id == UserRole.user_id)
        .filter(User.organization_id == org.id, User.is_active.is_(True),
                db.or_(db.and_(Role.organization_id.is_(None), Role.is_system.is_(True)),
                       Role.organization_id == org.id))
        .group_by(Role.name).all())

    admin_ids = admin_holders(org.id)
    admins_without_mfa = 0
    if admin_ids:
        admins_without_mfa = (base.filter(User.id.in_(list(admin_ids)),
                                          User.mfa_enabled.isnot(True)).count())
    return {
        'total': total,
        'active': active,
        'disabled': total - active,
        'by_role': by_role,
        'mfa_enabled': mfa_enabled,
        'mfa_adoption_pct': round(100 * mfa_enabled / active, 1) if active else None,
        'admins_without_mfa': admins_without_mfa,
        **overview_counts(org.id),  # {locked, pending_invites}
    }, len(admin_ids)


def _recent_admin_actions(org):
    rows = (AuditLog.query
            .filter(AuditLog.organization_id == org.id, AuditLog.event_type == 'admin_action')
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(RECENT_ADMIN_ACTIONS).all())
    return [{
        'id': str(r.id),
        'action': r.action,
        'resource_type': r.resource_type,
        'resource_id': str(r.resource_id) if r.resource_id else None,
        'user_email': r.user_email,
        'created_at': r.created_at.isoformat() if r.created_at else None,
        'has_changes': bool(isinstance(r.details, dict) and r.details.get('changes')),
    } for r in rows]


@api_bp.route('/admin/overview', methods=['GET'])
@jwt_required()
@require_permission('organizations:manage')
def get_admin_overview():
    """Users by role, MFA adoption, last-admin warning, recent admin actions."""
    from app.api.v1.endpoints.auth import _is_registration_enabled

    user = get_current_user()
    org = db.session.get(Organization, user.organization_id)
    if not org:
        return jsonify({'error': 'not_found', 'message': 'Organization not found'}), 404
    users, admin_count = _user_overview(org)
    return jsonify({
        'users': users,
        'active_admin_count': admin_count,
        'last_admin_warning': admin_count == 1,
        'recent_admin_actions': _recent_admin_actions(org),
        'registration_enabled': _is_registration_enabled(),
    }), 200
