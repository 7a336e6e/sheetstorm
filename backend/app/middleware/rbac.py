"""Role-Based Access Control (RBAC) middleware"""
from functools import wraps
from flask import jsonify, g, current_app
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


def require_interactive_session(f):
    """Decorator: refuse API-key tokens (403 `interactive_session_required`).

    For credential, MFA, profile and API-key management routes: a key can
    never change its owner's password or MFA, nor mint or manage keys. Place
    it below `@jwt_required()`.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.utils.token_scopes import is_api_key_request
        if is_api_key_request():
            return jsonify({
                'error': 'interactive_session_required',
                'message': 'This action requires an interactive sign-in; API keys cannot use it.',
            }), 403
        return f(*args, **kwargs)
    return decorated_function


def is_platform_admin(user):
    """Instance-wide admin: holds `system:manage` AND belongs to the platform
    organization (`config.PLATFORM_ORG_SLUG`). `system:manage` alone is
    meaningless in any other org."""
    if not user or not user.has_permission('system:manage') or not user.organization:
        return False
    return user.organization.slug == current_app.config.get('PLATFORM_ORG_SLUG', 'default')


def require_platform_admin(f):
    """Decorator: only platform admins (see is_platform_admin)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'unauthorized', 'message': 'Authentication required'}), 401
        if not is_platform_admin(user):
            return jsonify({'error': 'forbidden', 'message': 'Platform administrator required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def incident_scopes(user):
    """Incident visibility scopes granted by the user's permissions.

    Returns {'all'} for `incidents:read_all`, otherwise a subset of
    {'team', 'tlp_white'}. Directly assigned incidents are always visible.
    Scopes are additive across roles (a Viewer+Analyst user gets team +
    TLP:WHITE); no role ever narrows another. Derived from the owner's role
    permissions: an API key's scopes restrict actions, not visibility.
    """
    perms = set(user.role_permissions)
    if 'incidents:read_all' in perms:
        return {'all'}
    scopes = set()
    if 'incidents:read_team' in perms:
        scopes.add('team')
    if 'incidents:read_tlp_white' in perms:
        scopes.add('tlp_white')
    return scopes


def accessible_incidents_query(user, archived=False):
    """Base query of incidents the user may see (org + visibility scopes).

    The single source of truth for list / search / feed / correlation and
    (through user_can_access_incident) per-incident checks:
        assigned
        + team scope:      in one of my teams, or not team-restricted
        + tlp_white scope: TLP:WHITE
    `incidents:read_all` sees everything in the org.
    """
    from app.models import Incident, IncidentAssignment, IncidentTeam, TeamMember

    query = Incident.query.filter_by(organization_id=user.organization_id, is_archived=archived)
    scopes = incident_scopes(user)
    if 'all' in scopes:
        return query

    clauses = [Incident.id.in_(
        db.session.query(IncidentAssignment.incident_id).filter(
            IncidentAssignment.user_id == user.id,
            IncidentAssignment.removed_at.is_(None),
        )
    )]
    if 'team' in scopes:
        user_team_ids = db.session.query(TeamMember.team_id).filter(TeamMember.user_id == user.id)
        clauses.append(Incident.id.in_(
            db.session.query(IncidentTeam.incident_id).filter(IncidentTeam.team_id.in_(user_team_ids))
        ))
        clauses.append(~db.session.query(IncidentTeam).filter(IncidentTeam.incident_id == Incident.id).exists())
    if 'tlp_white' in scopes:
        clauses.append(Incident.tlp == 'white')
    return query.filter(db.or_(*clauses))


def user_can_access_incident(user, incident):
    """Whether `user` may see `incident` (already known to be in their org).
    Same rules as accessible_incidents_query."""
    from app.models import IncidentAssignment, IncidentTeam, TeamMember

    scopes = incident_scopes(user)
    if 'all' in scopes:
        return True
    if 'tlp_white' in scopes and incident.tlp == 'white':
        return True

    assigned = db.session.query(IncidentAssignment.id).filter_by(
        incident_id=incident.id, user_id=user.id, removed_at=None
    ).first() is not None
    if assigned:
        return True
    if 'team' not in scopes:
        return False

    # Team scope: unscoped (no team restriction) incidents are org-wide.
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
    (user_can_access_incident: assigned, or within one of the user's
    incident_scopes()).

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
