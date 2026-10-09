"""Request-field validation helpers shared by endpoints.

They raise werkzeug's BadRequest, which the global error handler renders as
{"error": "bad_request", "message": ...} with status 400 — so malformed input
is reported to the client instead of surfacing as a 500.
"""
from datetime import datetime, timezone

from dateutil.parser import parse as _parse_date
from werkzeug.exceptions import BadRequest


def parse_datetime(value, field, required=False):
    """Parse an ISO-8601-ish datetime string into an aware datetime.

    None/'' -> None (unless required). A value without an offset (naive) is
    taken to be **UTC** and gets `timezone.utc` attached explicitly, instead
    of being left to the database session time zone. Naive values are still
    accepted because the MCP, imports and older clients send them; the web UI
    always sends ISO strings with `Z`. Offsets are preserved as given.
    """
    if value is None or value == '':
        if required:
            raise BadRequest(f'{field} is required')
        return None
    if isinstance(value, datetime):
        return as_utc(value)
    if not isinstance(value, str):
        raise BadRequest(f'{field} must be a datetime string')
    try:
        return as_utc(_parse_date(value))
    except (ValueError, OverflowError, TypeError):
        raise BadRequest(f'{field} must be a valid ISO-8601 datetime')


def as_utc(value):
    """Attach UTC to a naive datetime; aware datetimes are returned unchanged."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


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
