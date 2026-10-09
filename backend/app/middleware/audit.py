"""Audit logging middleware"""
import logging
import re
import time
from functools import wraps
from flask import request, g, has_request_context
from app import db
from app.models import AuditLog

logger = logging.getLogger(__name__)

# Fields to always strip from logged request bodies / query params.
# Substring match (no anchors), so e.g. "secret" also covers client_secret,
# api_secret, secret_key, mfa_secret; "token" covers refresh_token/access_token.
_SENSITIVE_KEYS = re.compile(
    r'(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|'
    r'private[_-]?key|authorization|credential|credit_card|card_number|'
    r'cvv|ssn|fernet|mfa_secret|backup_code|otp_secret)',
    re.IGNORECASE,
)

# Event types worth broadcasting to the activity feed
_BROADCAST_EVENT_TYPES = {
    'data_modification', 'data_access', 'admin_action', 'security_event',
}


# Detail keys never broadcast over WebSocket (evidence hashes, legal-hold
# reasons, raw request args). The full record stays in the audit log.
_PRIVATE_DETAIL_KEYS = {
    'hashes', 'computed_hashes', 'stored_hashes', 'md5', 'sha1', 'sha256', 'sha512',
    'reason', 'args', 'purpose',
    # Before/after diffs (utils/audit_diff.py): admins fetch the full row.
    'changes',
    # Evidence register / custody ledger (hashes, acknowledgment names, party PII).
    'acquisition_hashes', 'observed_hash', 'expected_hash', 'entry_hash', 'typed_name', 'email', 'phone',
}


def public_activity_details(details):
    """Strip sensitive keys from audit details before they leave the server."""
    if not isinstance(details, dict):
        return {}
    return {k: v for k, v in details.items() if k not in _PRIVATE_DETAIL_KEYS}


def _broadcast_activity(log_entry):
    """Emit a WebSocket event for the activity feed.

    Incident-scoped events go only to that incident's room (whose members
    passed an incident access check on join). Org-wide events go to the org
    room, except admin actions which go only to holders of audit_logs:read.
    Sensitive detail keys are never broadcast.
    """
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
            'details': public_activity_details(log_entry.details),
        }
        if log_entry.incident_id:
            socketio.emit('activity:new', payload, room=f'incident_{log_entry.incident_id}')
        elif log_entry.event_type == 'admin_action':
            # Admin actions go only to users who may read the audit log.
            from app.models import User, UserRole, Role
            admin_ids = [
                uid for (uid,) in db.session.query(User.id).distinct()
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .filter(User.organization_id == log_entry.organization_id,
                        Role.permissions.contains(['audit_logs:read']),
                        db.or_(db.and_(Role.organization_id.is_(None), Role.is_system.is_(True)),
                               Role.organization_id == log_entry.organization_id),
                        User.is_active.is_(True))
                .all()
            ]
            for uid in admin_ids:
                socketio.emit('activity:new', payload, room=f'user_{uid}')
        else:
            socketio.emit('activity:new', payload, room=f'org_{log_entry.organization_id}')
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
            # Diff slots filled by the endpoint via utils.audit_diff.record_changes.
            g.pop('audit_changes', None)
            g.pop('audit_extra', None)

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

                details = {
                    'args': {k: str(v) for k, v in kwargs.items() if k != 'password'},
                }
                # Diff / extra context recorded by the handler via
                # utils.audit_diff.record_changes().
                audit_extra = g.pop('audit_extra', None)
                audit_changes = g.pop('audit_changes', None)
                if audit_extra:
                    details.update({k: v for k, v in audit_extra.items() if k not in ('args', 'changes')})
                if audit_changes:
                    details['changes'] = audit_changes

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
                    details=details,
                    **ctx,
                )
                db.session.add(log_entry)
                db.session.commit()
                _broadcast_activity(log_entry)
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass
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
    user=None,
    changes=None,
    organization_id=None,
    actor_label=None,
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

    changes: a diff from utils.audit_diff.audit_changes(), stored as
        details['changes'].
    organization_id: explicit org for CLI / system events without a user.
    actor_label: stored as user_email when there is no user (e.g. 'system:purge').
    """
    try:
        if user is None:
            user = getattr(g, 'current_user', None)

        ctx = _collect_request_context() if has_request_context() else {}

        details = dict(details or {})
        if changes:
            details['changes'] = changes

        log_entry = AuditLog(
            organization_id=organization_id or (user.organization_id if user else None),
            user_id=user.id if user else None,
            user_email=user.email if user else actor_label,
            event_type=event_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            incident_id=incident_id,
            details=details,
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


def log_security_event(action, resource_type=None, resource_id=None, incident_id=None, details=None,
                       **kwargs):
    """Log security-sensitive events (kwargs: user, changes, organization_id, actor_label)."""
    return log_audit_event(
        event_type='security_event',
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        incident_id=incident_id,
        details=details,
        **kwargs,
    )
