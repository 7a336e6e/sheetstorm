"""Optimistic concurrency (lost-update protection).

Model pattern (user-editable tables)::

    version = Column(Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}

SQLAlchemy then bumps ``version`` on every ORM UPDATE and raises
``StaleDataError`` when another writer committed first. ``query.update()``
bypasses the bump — never use it on versioned tables; load the objects.

Endpoint pattern::

    conflict = precondition(task)          # If-Match / body expected_version
    if conflict:
        return conflict
    ... mutate ...
    conflict = commit_or_conflict(task)     # StaleDataError -> 409
    if conflict:
        return conflict
    return set_etag(jsonify(task.to_dict()), task)

Clients that send neither ``If-Match`` nor the body key keep last-write-wins
(MCP, bridge, old clients) unless the endpoint passes ``required=True``.
"""
import re

from flask import jsonify, make_response, request
from sqlalchemy.orm.exc import StaleDataError

_ETAG_RE = re.compile(r'^\s*(?:W/)?"?\s*(\d{1,18})\s*"?\s*$')


class _Invalid:
    pass


INVALID = _Invalid()


def parse_version(value):
    """Parse ``7``, ``"7"``, ``W/"7"`` (or an int) into an int.

    Returns None when absent/empty, ``'*'`` for the wildcard and INVALID for
    anything else. A comma-separated list returns a tuple of versions.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return INVALID
    if isinstance(value, int):
        return value if value >= 0 else INVALID
    if not isinstance(value, str):
        return INVALID
    value = value.strip()
    if not value:
        return None
    if value == '*':
        return '*'
    parts = [p for p in value.split(',') if p.strip()]
    versions = []
    for part in parts:
        m = _ETAG_RE.match(part)
        if not m:
            return INVALID
        versions.append(int(m.group(1)))
    return versions[0] if len(versions) == 1 else tuple(versions)


def _expected_version(body_key):
    header = request.headers.get('If-Match')
    if header is not None and header.strip():
        return parse_version(header)
    if body_key:
        body = request.get_json(silent=True)
        if isinstance(body, dict) and body.get(body_key) is not None:
            return parse_version(body.get(body_key))
    return None


def conflict_response(obj, serializer=None, message=None):
    """409 ``{error:'conflict', message, current, current_version}``."""
    current = None
    version = None
    if obj is not None:
        current = serializer(obj) if serializer else obj.to_dict()
        version = getattr(obj, 'version', None)
    body = {
        'error': 'conflict',
        'message': message or 'This item was changed by someone else. Review the current version and retry.',
        'current': current,
        'current_version': version,
    }
    resp = make_response(jsonify(body), 409)
    if version is not None:
        resp.headers['ETag'] = f'"{version}"'
    return resp


def precondition(obj, *, required=False, body_key='expected_version', serializer=None):
    """Check the client's expected version against ``obj.version``.

    Reads ``If-Match`` first, then the JSON body key. Returns None when the
    write may proceed, otherwise a response to return:
    409 ``conflict`` on mismatch, 428 ``precondition_required`` when
    ``required`` and nothing was sent, 400 ``invalid_precondition`` for a
    malformed value.
    """
    expected = _expected_version(body_key)
    if expected is None:
        if required:
            return make_response(jsonify({
                'error': 'precondition_required',
                'message': f'Send If-Match: "<version>" (or "{body_key}") with this request.',
            }), 428)
        return None
    if expected is INVALID:
        return make_response(jsonify({
            'error': 'invalid_precondition',
            'message': 'If-Match must be a version number such as "7".',
        }), 400)
    if expected == '*':
        return None
    current = getattr(obj, 'version', None)
    candidates = expected if isinstance(expected, tuple) else (expected,)
    if current in candidates:
        return None
    return conflict_response(obj, serializer)


def commit_or_conflict(obj, serializer=None):
    """Commit; turn a concurrent-update ``StaleDataError`` into a 409 with the
    refetched current row (None if it was deleted). Returns None on success."""
    from app import db
    try:
        db.session.commit()
        return None
    except StaleDataError:
        db.session.rollback()
        current = None
        try:
            current = db.session.get(type(obj), obj.id, populate_existing=True)
        except Exception:
            current = None
        return conflict_response(current, serializer)


def set_etag(resp, obj):
    """Attach ``ETag: "<version>"`` to a response (or (body, status) tuple)."""
    resp = make_response(resp)
    version = getattr(obj, 'version', None)
    if version is not None:
        resp.headers['ETag'] = f'"{version}"'
    return resp


def register_conflict_handler(app):
    """Safety net: a StaleDataError from a plain ``db.session.commit()`` is a
    409 conflict, not a 500."""
    @app.errorhandler(StaleDataError)
    def _stale_data(_e):
        from app import db
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({
            'error': 'conflict',
            'message': 'This item was changed by someone else. Reload and retry.',
            'current': None,
            'current_version': None,
        }), 409
