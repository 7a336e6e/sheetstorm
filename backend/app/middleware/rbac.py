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


def require_incident_access(permission=None):
    """Decorator to check user has access to a specific incident.

    For Operators and Viewers, this checks if they are assigned to the incident.
    For other roles, it checks the specified permission.

    Usage:
        @require_incident_access('incidents:read')
        def view_incident(incident_id):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from app.models import Incident, IncidentAssignment

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

            # Check if user has the permission
            if permission and user.has_permission(permission):
                # For roles with full access, verify incident exists and is in user's org
                incident = Incident.query.filter_by(
                    id=incident_id,
                    organization_id=user.organization_id
                ).first()

                if not incident:
                    return jsonify({
                        'error': 'not_found',
                        'message': 'Incident not found'
                    }), 404

                g.incident = incident
                return f(*args, **kwargs)

            # For limited roles (Operator, Viewer), check assignment
            if user.has_role('Operator') or user.has_role('Viewer'):
                assignment = IncidentAssignment.query.filter_by(
                    incident_id=incident_id,
                    user_id=user.id,
                    removed_at=None
                ).first()

                if not assignment:
                    return jsonify({
                        'error': 'forbidden',
                        'message': 'You are not assigned to this incident'
                    }), 403

                g.incident = assignment.incident
                return f(*args, **kwargs)

            return jsonify({
                'error': 'forbidden',
                'message': 'Permission denied'
            }), 403

        return decorated_function
    return decorator


def check_permission(user, permission):
    """Helper function to check permission without decorator."""
    return user and user.has_permission(permission)


def check_any_permission(user, permissions):
    """Helper function to check any permission without decorator."""
    return user and user.has_any_permission(permissions)


def check_incident_access(user, incident_id):
    """Helper function to check incident access without decorator."""
    from app.models import Incident, IncidentAssignment

    if not user:
        return False, None

    # For most roles, check if incident exists in their organization
    incident = Incident.query.filter_by(
        id=incident_id,
        organization_id=user.organization_id
    ).first()

    if not incident:
        return False, None

    # If user has general read permission, they can access
    if user.has_permission('incidents:read'):
        return True, incident

    # For limited roles, check assignment
    if user.has_role('Operator') or user.has_role('Viewer'):
        assignment = IncidentAssignment.query.filter_by(
            incident_id=incident_id,
            user_id=user.id,
            removed_at=None
        ).first()
        if assignment:
            return True, incident

    return False, None
