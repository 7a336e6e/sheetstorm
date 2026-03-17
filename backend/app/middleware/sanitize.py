"""
Input sanitization middleware.
Strips potentially dangerous HTML/script content from all incoming JSON request bodies.
Enforces maximum string length to prevent abuse.
Defense-in-depth measure alongside frontend sanitization.
"""
import re
from html import escape as html_escape
from flask import request, g


# Pattern to match HTML tags (including script, iframe, etc.)
HTML_TAG_RE = re.compile(r'<[^>]+>', re.IGNORECASE)
# Pattern to match javascript: protocol URIs
JS_PROTOCOL_RE = re.compile(r'javascript\s*:', re.IGNORECASE)
# Pattern to match data: URIs with script types
DATA_SCRIPT_RE = re.compile(r'data\s*:\s*text/html', re.IGNORECASE)
# Pattern for event handlers in attributes
EVENT_HANDLER_RE = re.compile(r'\bon\w+\s*=', re.IGNORECASE)

# Maximum string length for any single field (1MB)
MAX_STRING_LENGTH = 1_000_000


def sanitize_string(value: str) -> str:
    """Sanitize a single string value by removing dangerous HTML content."""
    if not value:
        return value
    # Truncate excessively long strings
    if len(value) > MAX_STRING_LENGTH:
        value = value[:MAX_STRING_LENGTH]
    # Remove HTML tags
    cleaned = HTML_TAG_RE.sub('', value)
    # Remove javascript: protocol
    cleaned = JS_PROTOCOL_RE.sub('', cleaned)
    # Remove data:text/html
    cleaned = DATA_SCRIPT_RE.sub('', cleaned)
    # Remove event handlers
    cleaned = EVENT_HANDLER_RE.sub('', cleaned)
    return cleaned.strip()


def sanitize_value(value, depth=0):
    """Recursively sanitize values in request data."""
    if depth > 20:
        return None  # Prevent excessively nested payloads
    if isinstance(value, str):
        return sanitize_string(value)
    elif isinstance(value, dict):
        return {k: sanitize_value(v, depth + 1) for k, v in value.items()}
    elif isinstance(value, list):
        return [sanitize_value(item, depth + 1) for item in value[:10000]]
    return value


def init_sanitization(app):
    """Register the sanitization middleware with the Flask app."""

    @app.before_request
    def sanitize_input():
        """Sanitize all incoming JSON request bodies."""
        if request.is_json and request.content_length and request.content_length > 0:
            try:
                data = request.get_json(silent=True)
                if data and isinstance(data, dict):
                    sanitized = sanitize_value(data)
                    # Store sanitized data in g so endpoints can access it
                    g.sanitized_json = sanitized
            except Exception:
                pass  # Don't block request if sanitization fails
