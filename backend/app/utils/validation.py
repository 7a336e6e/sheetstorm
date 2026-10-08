"""Request-field validation helpers shared by endpoints.

They raise werkzeug's BadRequest, which the global error handler renders as
{"error": "bad_request", "message": ...} with status 400 — so malformed input
is reported to the client instead of surfacing as a 500.
"""
from datetime import datetime

from dateutil.parser import parse as _parse_date
from werkzeug.exceptions import BadRequest


def parse_datetime(value, field, required=False):
    """Parse an ISO-8601-ish datetime string; None/'' -> None (unless required)."""
    if value is None or value == '':
        if required:
            raise BadRequest(f'{field} is required')
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise BadRequest(f'{field} must be a datetime string')
    try:
        return _parse_date(value)
    except (ValueError, OverflowError, TypeError):
        raise BadRequest(f'{field} must be a valid ISO-8601 datetime')


def check_choice(value, choices, field, allow_none=False):
    """Ensure value is one of `choices` (None allowed only when allow_none)."""
    if value is None and allow_none:
        return None
    if value not in choices:
        raise BadRequest(f'Invalid {field}: {value!r}. Valid values: {list(choices)}')
    return value


def json_body():
    """The request JSON object, or a 400 if the body is not a JSON object."""
    from flask import request
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise BadRequest('Request body must be a JSON object')
    return data
