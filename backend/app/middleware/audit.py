"""Audit logging middleware"""
import logging
import re
import time
from functools import wraps
from flask import request, g
from app import db
from app.models import AuditLog

logger = logging.getLogger(__name__)

# Fields to always strip from logged request bodies
_SENSITIVE_KEYS = re.compile(
    r'(password|secret|token|api_key|authorization|credit_card|ssn|fernet)',
    re.IGNORECASE,
)

# Event types worth broadcasting to the activity feed
_BROADCAST_EVENT_TYPES = {
    'data_modification', 'data_access', 'admin_action', 'security_event',
}


def _broadcast_activity(log_entry):
    """Emit a WebSocket event for the activity feed."""
    if not log_entry or not log_entry.organization_id:
        return
    if log_entry.event_type not in _BROADCAST_EVENT_TYPES:
        return
    try:
        from app import socketio
        payload = {
            'id': str(log_entry.id),
            'event_type': log_entry.event_type,
            'action': log_entry.action,
            'resource_type': log_entry.resource_type,
            'resource_id': str(log_entry.resource_id) if log_entry.resource_id else None,
            'incident_id': str(log_entry.incident_id) if log_entry.incident_id else None,
            'user_email': log_entry.user_email,
            'user_id': str(log_entry.user_id) if log_entry.user_id else None,
            'created_at': log_entry.created_at.isoformat() if log_entry.created_at else None,
            'details': log_entry.details,
        }
        room = f'org_{log_entry.organization_id}'
        socketio.emit('activity:new', payload, room=room)
    except Exception:
        logger.debug('Activity broadcast skipped', exc_info=True)


def _parse_user_agent(ua_string: str) -> dict:
    """Extract browser, OS, and device type from a User-Agent string."""
    if not ua_string:
        return {}

    browser = None
    os_name = None
    device_type = 'Desktop'

    # --- OS detection ---
    if 'iPhone' in ua_string or 'iPad' in ua_string:
        os_name = 'iOS'
        device_type = 'Tablet' if 'iPad' in ua_string else 'Mobile'
    elif 'Android' in ua_string:
        os_name = 'Android'
        device_type = 'Mobile' if 'Mobile' in ua_string else 'Tablet'
    elif 'Windows' in ua_string:
        os_name = 'Windows'
    elif 'Mac OS X' in ua_string or 'Macintosh' in ua_string:
        os_name = 'macOS'
    elif 'Linux' in ua_string:
        os_name = 'Linux'
    elif 'CrOS' in ua_string:
        os_name = 'Chrome OS'

    # --- Browser detection (order matters) ---
    if 'Edg/' in ua_string:
        m = re.search(r'Edg/([\d.]+)', ua_string)
        browser = f'Edge {m.group(1)}' if m else 'Edge'
    elif 'OPR/' in ua_string or 'Opera' in ua_string:
        m = re.search(r'OPR/([\d.]+)', ua_string)
        browser = f'Opera {m.group(1)}' if m else 'Opera'
    elif 'Firefox/' in ua_string:
        m = re.search(r'Firefox/([\d.]+)', ua_string)
        browser = f'Firefox {m.group(1)}' if m else 'Firefox'
    elif 'Chrome/' in ua_string and 'Safari/' in ua_string:
        m = re.search(r'Chrome/([\d.]+)', ua_string)
        browser = f'Chrome {m.group(1)}' if m else 'Chrome'
    elif 'Safari/' in ua_string and 'Version/' in ua_string:
        m = re.search(r'Version/([\d.]+)', ua_string)
        browser = f'Safari {m.group(1)}' if m else 'Safari'
    elif 'curl/' in ua_string:
        browser = 'curl'
        device_type = 'CLI'
    elif 'python' in ua_string.lower():
        browser = 'Python HTTP Client'
        device_type = 'API'
    else:
        # Fallback: first product token
        m = re.match(r'^([A-Za-z]+)/([\d.]+)', ua_string)
        if m:
            browser = f'{m.group(1)} {m.group(2)}'

    # Bot detection
    if re.search(r'bot|crawl|spider|slurp', ua_string, re.IGNORECASE):
        device_type = 'Bot'

    return {
        'browser': browser,
        'os': os_name,
        'device_type': device_type,
    }


def _sanitize_body(body: dict, max_depth: int = 2, depth: int = 0) -> dict:
    """Return a sanitised summary of a request body (no secrets, bounded depth)."""
    if depth >= max_depth or not isinstance(body, dict):
        return {}
    out = {}
    for key, value in body.items():
        if _SENSITIVE_KEYS.search(key):
            out[key] = '***REDACTED***'
        elif isinstance(value, dict):
            out[key] = _sanitize_body(value, max_depth, depth + 1)
        elif isinstance(value, list):
            out[key] = f'[{len(value)} items]'
        elif isinstance(value, str) and len(value) > 200:
            out[key] = value[:200] + '…'
        else:
            out[key] = value
    return out


def _collect_request_context() -> dict:
    """Gather rich context from the current Flask request."""
    ua_string = request.headers.get('User-Agent', '')[:500]
    ua_info = _parse_user_agent(ua_string)

    # Sanitised request body summary
    body_summary = {}
    try:
        if request.is_json and request.content_length and request.content_length < 50_000:
            raw = request.get_json(silent=True)
            if isinstance(raw, dict):
                body_summary = _sanitize_body(raw)
    except Exception:
        pass

    # Query params (strip sensitive keys)
    query_params = {}
    for k, v in request.args.items():
        if _SENSITIVE_KEYS.search(k):
            query_params[k] = '***REDACTED***'
        else:
            query_params[k] = v

    return {
        'ip_address': request.remote_addr,
        'user_agent': ua_string,
        'request_method': request.method,
        'request_path': request.path,
        'request_query_params': query_params or None,
        'request_body_summary': body_summary or None,
        'content_type': request.content_type,
        'referrer': request.referrer,
        'origin': request.headers.get('Origin'),
        # Cloudflare geo headers
        'geo_country': request.headers.get('CF-IPCountry'),
        'geo_city': request.headers.get('CF-IPCity'),
        'geo_region': request.headers.get('CF-Region'),
        'cf_ray': request.headers.get('CF-Ray'),
        # Parsed UA
        'browser': ua_info.get('browser'),
        'os': ua_info.get('os'),
        'device_type': ua_info.get('device_type'),
    }


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
            start_time = time.monotonic()

            # Execute the wrapped function
            result = f(*args, **kwargs)

            duration_ms = round((time.monotonic() - start_time) * 1000, 2)

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

                ctx = _collect_request_context()

                log_entry = AuditLog(
                    organization_id=user.organization_id if user else None,
                    user_id=user.id if user else None,
                    user_email=user.email if user else None,
                    event_type=event_type,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    incident_id=incident.id if incident else kwargs.get('incident_id'),
                    status_code=result[1] if isinstance(result, tuple) and len(result) >= 2 else 200,
                    duration_ms=duration_ms,
                    details={
                        'args': {k: str(v) for k, v in kwargs.items() if k != 'password'},
                    },
                    **ctx,
                )
                db.session.add(log_entry)
                db.session.commit()
                _broadcast_activity(log_entry)
            except Exception:
                logger.exception('Audit logging error')

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

        ctx = _collect_request_context() if request else {}

        log_entry = AuditLog(
            organization_id=user.organization_id if user else None,
            user_id=user.id if user else None,
            user_email=user.email if user else None,
            event_type=event_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            incident_id=incident_id,
            details=details or {},
            **ctx,
        )
        db.session.add(log_entry)
        db.session.commit()
        _broadcast_activity(log_entry)
        return log_entry
    except Exception:
        db.session.rollback()
        logger.exception('Audit logging error')
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
