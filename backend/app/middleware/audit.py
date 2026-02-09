"""Audit logging middleware"""
from functools import wraps
from flask import request, g
from app import db
from app.models import AuditLog


def audit_log(event_type, action, resource_type=None):
    """Decorator to log actions to audit trail.

    Usage:
        @audit_log('data_modification', 'create', 'incident')
        def create_incident():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Execute the wrapped function
            result = f(*args, **kwargs)

            # Log after successful execution
            try:
                user = getattr(g, 'current_user', None)
                incident = getattr(g, 'incident', None)

                # Get resource_id from kwargs or result
                resource_id = kwargs.get('id') or kwargs.get(f'{resource_type}_id')
                if not resource_id and isinstance(result, tuple) and len(result) >= 1:
                    response_data = result[0]
                    if hasattr(response_data, 'get_json'):
                        json_data = response_data.get_json()
                        if json_data and isinstance(json_data, dict):
                            resource_id = json_data.get('id')

                log_entry = AuditLog(
                    organization_id=user.organization_id if user else None,
                    user_id=user.id if user else None,
                    user_email=user.email if user else None,
                    event_type=event_type,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    incident_id=incident.id if incident else kwargs.get('incident_id'),
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent', '')[:500],
                    request_method=request.method,
                    request_path=request.path,
                    status_code=result[1] if isinstance(result, tuple) and len(result) >= 2 else 200,
                    details={
                        'args': {k: str(v) for k, v in kwargs.items() if k != 'password'},
                    }
                )
                db.session.add(log_entry)
                db.session.commit()
            except Exception as e:
                # Don't fail the request if audit logging fails
                db.session.rollback()
                print(f"Audit logging error: {e}")

            return result
        return decorated_function
    return decorator


def log_audit_event(
    event_type,
    action,
    resource_type=None,
    resource_id=None,
    incident_id=None,
    details=None,
    user=None
):
    """Helper function to log audit events manually.

    Usage:
        log_audit_event(
            event_type='security_event',
            action='password_reveal',
            resource_type='compromised_account',
            resource_id=account.id,
            details={'account_name': account.account_name}
        )
    """
    try:
        if user is None:
            user = getattr(g, 'current_user', None)

        log_entry = AuditLog(
            organization_id=user.organization_id if user else None,
            user_id=user.id if user else None,
            user_email=user.email if user else None,
            event_type=event_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            incident_id=incident_id,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent', '')[:500] if request else None,
            request_method=request.method if request else None,
            request_path=request.path if request else None,
            details=details or {}
        )
        db.session.add(log_entry)
        db.session.commit()
        return log_entry
    except Exception as e:
        db.session.rollback()
        print(f"Audit logging error: {e}")
        return None


def log_auth_event(action, user=None, success=True, details=None):
    """Log authentication events."""
    return log_audit_event(
        event_type='authentication',
        action=action,
        details={
            **(details or {}),
            'success': success,
            'email': user.email if user else details.get('email') if details else None
        },
        user=user
    )


def log_security_event(action, resource_type=None, resource_id=None, incident_id=None, details=None):
    """Log security-sensitive events."""
    return log_audit_event(
        event_type='security_event',
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        incident_id=incident_id,
        details=details
    )
