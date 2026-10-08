"""Role-Based Access Control (RBAC) middleware"""
from functools import wraps
from flask import jsonify, g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

from app import db
from app.models import User


def get_current_user():
    """Get the current authenticated user from JWT."""
    verify_jwt_in_request()
    user_id = get_jwt_identity()

    if hasattr(g, 'current_user') and g.current_user and str(g.current_user.id) == user_id:
        return g.current_user

    user = User.query.get(user_id)
    if user and user.is_active:
        g.current_user = user
        return user
    return None


def require_permission(permission):
    """Decorator to require a specific permission.

    Usage:
        @require_permission('incidents:create')
        def create_incident():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()

            if not user:
                return jsonify({
                    'error': 'unauthorized',
                    'message': 'Authentication required'
                }), 401

            if not user.has_permission(permission):
                return jsonify({
                    'error': 'forbidden',
                    'message': f'Permission denied. Required: {permission}'
                }), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_any_permission(permissions):
    """Decorator to require any of the specified permissions.

    Usage:
        @require_any_permission(['incidents:read', 'incidents:update'])
        def view_incident():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()

            if not user:
                return jsonify({
                    'error': 'unauthorized',
                    'message': 'Authentication required'
                }), 401

            if not user.has_any_permission(permissions):
                return jsonify({
                    'error': 'forbidden',
                    'message': f'Permission denied. Required one of: {", ".join(permissions)}'
                }), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_all_permissions(permissions):
    """Decorator to require all specified permissions.

    Usage:
        @require_all_permissions(['incidents:read', 'artifacts:download'])
        def download_artifact():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()

            if not user:
                return jsonify({
                    'error': 'unauthorized',
                    'message': 'Authentication required'
                }), 401

            if not user.has_all_permissions(permissions):
                return jsonify({
                    'error': 'forbidden',
                    'message': f'Permission denied. Required all: {", ".join(permissions)}'
                }), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_role(role_name):
    """Decorator to require a specific role.

    Usage:
        @require_role('Administrator')
        def admin_only():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()

            if not user:
                return jsonify({
                    'error': 'unauthorized',
                    'message': 'Authentication required'
                }), 401

            if not user.has_role(role_name):
                return jsonify({
                    'error': 'forbidden',
                    'message': f'Role required: {role_name}'
                }), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def incident_access_tier(user):
    """Classify how far a user's incident visibility extends.

    - 'full':     Administrator / Manager — every incident in the org
    - 'viewer':   Viewer — directly assigned + TLP:WHITE incidents
    - 'operator': Operator — directly assigned incidents only
    - 'team':     everyone else (Responder/Analyst) — assigned, in one of
                  their teams, or not team-restricted

    Single source of truth for list/search (accessible_incidents_query) and
    per-incident checks, so the rules cannot diverge.
    """
    if user.has_role('Administrator') or user.has_role('Manager'):
        return 'full'
    if user.has_role('Viewer'):
        return 'viewer'
    if user.has_role('Operator'):
        return 'operator'
    return 'team'


def user_can_access_incident(user, incident):
    """Whether `user` may see `incident` (already known to be in their org)."""
    from app.models import IncidentAssignment, IncidentTeam, TeamMember

    tier = incident_access_tier(user)
    if tier == 'full':
        return True

    assigned = db.session.query(IncidentAssignment.id).filter_by(
        incident_id=incident.id, user_id=user.id, removed_at=None
    ).first() is not None
    if assigned:
        return True
    if tier == 'operator':
        return False
    if tier == 'viewer':
        return incident.tlp == 'white'

    # Team tier: unscoped (no team restriction) incidents are org-wide.
    if IncidentTeam.query.filter_by(incident_id=incident.id).count() == 0:
        return True
    user_team_ids = db.session.query(TeamMember.team_id).filter(TeamMember.user_id == user.id)
    return IncidentTeam.query.filter(
        IncidentTeam.incident_id == incident.id,
        IncidentTeam.team_id.in_(user_team_ids),
    ).first() is not None


def require_incident_access(permission=None):
    """Decorator to check user has access to a specific incident.

    Access requires BOTH the permission (when given) AND incident visibility
    per incident_access_tier():
    - Administrator/Manager: full org access
    - Responder/Analyst: assigned, team member, or incident not team-scoped
    - Operator: directly assigned only
    - Viewer: directly assigned or TLP:WHITE

    Usage:
        @require_incident_access('incidents:read')
        def view_incident(incident_id):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from app.models import Incident

            user = get_current_user()

            if not user:
                return jsonify({
                    'error': 'unauthorized',
                    'message': 'Authentication required'
                }), 401

            # Get incident_id from kwargs or args
            incident_id = kwargs.get('incident_id') or (args[0] if args else None)

            if not incident_id:
                return jsonify({
                    'error': 'bad_request',
                    'message': 'Incident ID required'
                }), 400

            # Verify incident exists in user's org
            incident = Incident.query.filter_by(
                id=incident_id,
                organization_id=user.organization_id
            ).first()

            if not incident:
                return jsonify({
                    'error': 'not_found',
                    'message': 'Incident not found'
                }), 404

            if permission and not user.has_permission(permission):
                return jsonify({
                    'error': 'forbidden',
                    'message': f'Permission denied. Required: {permission}'
                }), 403

            if not user_can_access_incident(user, incident):
                return jsonify({
                    'error': 'forbidden',
                    'message': 'You do not have access to this incident'
                }), 403

            g.incident = incident
            return f(*args, **kwargs)

        return decorated_function
    return decorator


def check_permission(user, permission):
    """Helper function to check permission without decorator."""
    return user and user.has_permission(permission)


def check_any_permission(user, permissions):
    """Helper function to check any permission without decorator."""
    return user and user.has_any_permission(permissions)


def check_incident_access(user, incident_id):
    """Helper to check incident read access without the decorator.

    Returns (allowed, incident). `incident` is None when the id is malformed
    or the incident is not in the user's organization (callers answer 404);
    it is set with allowed=False when the incident exists but the user may
    not see it (callers answer 403).
    """
    from uuid import UUID
    from app.models import Incident

    if not user or not user.is_active:
        return False, None
    try:
        incident_uuid = incident_id if isinstance(incident_id, UUID) else UUID(str(incident_id))
    except (ValueError, TypeError, AttributeError):
        return False, None

    incident = Incident.query.filter_by(
        id=incident_uuid,
        organization_id=user.organization_id
    ).first()
    if not incident:
        return False, None

    if not user.has_permission('incidents:read') or not user_can_access_incident(user, incident):
        return False, incident
    return True, incident
