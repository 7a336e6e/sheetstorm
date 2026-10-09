"""WebSocket handlers for real-time collaboration.

Event catalog: assets/docs/websocket-events.md. Room/scope model and the
server-side emit helpers live in app/services/realtime.py.

Security model:
* Identity is bound at connect time from a valid ACCESS JWT and never taken
  from client payloads. API-key tokens, refresh and MFA pre-auth tokens give an
  anonymous connection. Anonymous sockets can only ``ping``.
* Rooms are derived server-side: the client names an incident, the server
  checks access and joins the base room plus only the scope rooms whose read
  permission the user holds.
* Every client->server event is schema-validated, rate limited per socket
  (token bucket) and only acts on rooms the socket is actually in.
* Presence never carries socket ids; entries are keyed by an opaque pid.
"""
import math
import secrets
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone
from functools import wraps

from flask import request
from flask_jwt_extended import decode_token
from flask_socketio import disconnect, emit, join_room, leave_room, rooms

from app import db
from app.models import User
from app.services import realtime

# Map socket session id -> authenticated session (this worker only; a socket
# is pinned to one worker). Identity is established server-side at connect.
#   {'user_id', 'name', 'organization_id',
#    'incidents': OrderedDict(iid -> {'pid', 'scopes', 'can_drag', 'since'}),
#    'nodes': set(validated graph node ids), 'denied_log_at': float}
_sid_users = {}

MAX_ROOMS_PER_SOCKET = 5
MAX_COORD = 1e6
MAX_CACHED_NODES = 1000
PRESENCE_MODES = ('viewing', 'editing')
PRESENCE_BROADCAST_INTERVAL = 1.0      # seconds, per incident (updates only)
DENIED_LOG_INTERVAL = 60.0             # ws_join_denied: at most 1 per sid per minute

# event -> (bucket capacity, refill rate in tokens/second)
RATE_LIMITS = {
    'incident:join': (10, 10 / 60.0),
    'presence:update': (8, 4.0),
    'graph:node_drag': (15, 15.0),
    'default': (20, 20.0),
}
VIOLATION_WINDOW = 60.0
VIOLATION_LIMIT = 50

# sid -> {'buckets': {event: [tokens, last_ts]}, 'violations': deque[ts]}
_rate_state = {}

_presence_last = {}
_presence_pending = set()


# ---------------------------------------------------------------------------
# Rate limiting (in-process token bucket keyed by sid)
# ---------------------------------------------------------------------------

def _consume(sid, event, now=None):
    now = time.monotonic() if now is None else now
    capacity, rate = RATE_LIMITS.get(event, RATE_LIMITS['default'])
    state = _rate_state.setdefault(sid, {'buckets': {}, 'violations': deque()})
    bucket = state['buckets'].get(event)
    if bucket is None:
        bucket = state['buckets'][event] = [float(capacity), now]
    tokens = min(float(capacity), bucket[0] + (now - bucket[1]) * rate)
    bucket[1] = now
    if tokens >= 1.0:
        bucket[0] = tokens - 1.0
        return True
    bucket[0] = tokens
    return False


def _record_violation(sid, now=None):
    """Returns True when the socket exceeded VIOLATION_LIMIT in the window."""
    now = time.monotonic() if now is None else now
    state = _rate_state.setdefault(sid, {'buckets': {}, 'violations': deque()})
    v = state['violations']
    v.append(now)
    while v and now - v[0] > VIOLATION_WINDOW:
        v.popleft()
    return len(v) > VIOLATION_LIMIT


def _security_event(action, session, resource_id=None, details=None):
    """Audit a websocket security event (never raises, never logs payloads)."""
    try:
        from app.middleware.audit import log_audit_event
        user = db.session.get(User, session['user_id']) if session else None
        log_audit_event(event_type='security_event', action=action,
                        resource_type='incident' if resource_id else None,
                        resource_id=resource_id, details=details or {}, user=user)
    except Exception:  # pragma: no cover - audit must not break the socket
        pass


def _error(code, event):
    emit('rt:error', {'code': code, 'event': event})


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _incident_id(data):
    if not isinstance(data, dict):
        return None
    return realtime.canonical_incident_id(data.get('incident_id'))


def _uuid_str(value):
    return realtime.canonical_incident_id(value) if isinstance(value, str) else None


def _coord(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or abs(value) >= MAX_COORD:
        return None
    return value


def _focus(value, scopes):
    """None, or {'entity', 'id'} for an entity in a scope the user can read."""
    if value is None:
        return None, True
    if not isinstance(value, dict):
        return None, False
    entity = value.get('entity')
    spec = realtime.ENTITY_SCOPES.get(entity) if isinstance(entity, str) else None
    entity_id = _uuid_str(value.get('id'))
    if spec is None or entity_id is None or spec.scope not in scopes:
        return None, False
    return {'entity': entity, 'id': entity_id}, True


# ---------------------------------------------------------------------------
# Session / room helpers
# ---------------------------------------------------------------------------

def _membership(session, iid):
    """The socket's join record for an incident, or None.

    Drops stale records when the socket was removed from the base room
    elsewhere (eviction / room close propagated through the message queue).
    """
    joined = session['incidents'].get(iid) if session else None
    if joined is None:
        return None
    if realtime.base_room(iid) not in rooms():
        session['incidents'].pop(iid, None)
        realtime.presence_remove(iid, joined['pid'])
        return None
    return joined


def _leave_rooms(iid):
    current = set(rooms())
    for room in realtime.all_rooms(iid):
        if room in current:
            leave_room(room)


def _broadcast_presence_now(socketio, iid):
    _presence_last[iid] = time.monotonic()
    realtime.broadcast_presence(iid, socketio)


def _broadcast_presence_throttled(socketio, iid):
    """At most one presence:state per incident per interval, with a trailing
    broadcast so the last update is never lost."""
    now = time.monotonic()
    elapsed = now - _presence_last.get(iid, 0.0)
    if elapsed >= PRESENCE_BROADCAST_INTERVAL:
        _broadcast_presence_now(socketio, iid)
        return
    if iid in _presence_pending:
        return
    _presence_pending.add(iid)

    def trailing():
        socketio.sleep(max(0.0, PRESENCE_BROADCAST_INTERVAL - elapsed))
        _presence_pending.discard(iid)
        _broadcast_presence_now(socketio, iid)

    socketio.start_background_task(trailing)


def _do_leave(socketio, session, iid, broadcast=True):
    joined = session['incidents'].pop(iid, None)
    if joined is None:
        return False
    _leave_rooms(iid)
    realtime.presence_remove(iid, joined['pid'])
    if broadcast:
        _broadcast_presence_now(socketio, iid)
    return True


def register_handlers(socketio):
    """Register all WebSocket event handlers."""

    def _candidate_tokens(auth):
        """Yield every token the client may have presented, in priority order:
        Socket.IO auth payload (preferred — not logged in URLs), query string,
        Authorization header, then the httpOnly access cookie."""
        if isinstance(auth, dict):
            yield auth.get('token')
        yield request.args.get('token')
        hdr = request.headers.get('Authorization', '')
        if hdr.startswith('Bearer '):
            yield hdr[7:]
        yield request.cookies.get('access_token_cookie')

    def _authenticate(auth):
        """Resolve the user for a connecting socket.

        Uses the first candidate token that is a valid, unrevoked interactive
        ACCESS token for an active user — a stale/garbage value in one location
        (e.g. an old query-string token) must not shadow a valid cookie.
        Refresh, MFA pre-auth and API-key tokens are never accepted for
        realtime access.
        """
        from app import is_token_revoked
        for token in _candidate_tokens(auth):
            if not token or not isinstance(token, str):
                continue
            try:
                decoded = decode_token(token)
            except Exception:
                continue
            if decoded.get('type') != 'access' or decoded.get('pre_auth'):
                continue
            if decoded.get('api_key_id'):
                continue
            if is_token_revoked(decoded):
                continue
            user = db.session.get(User, decoded.get('sub'))
            if not user or not user.is_active:
                continue
            # Restricted accounts (must change password, MFA enrollment) are anonymous.
            from app.middleware.account_state import restriction_for
            if restriction_for(user):
                continue
            return user
        return None

    def guarded(event, anonymous_ok=False):
        """Rate limit + require an authenticated session for a C->S event."""
        def decorator(fn):
            @wraps(fn)
            def wrapper(*args):
                sid = request.sid
                if not _consume(sid, event):
                    _error('rate_limited', event)
                    if _record_violation(sid):
                        session = _sid_users.get(sid)
                        _security_event('ws_rate_limited', session, details={'event': event})
                        disconnect()
                    return None
                session = _sid_users.get(sid)
                if session is None and not anonymous_ok:
                    _error('denied', event)
                    return None
                data = args[0] if args else None
                return fn(session, data)
            return wrapper
        return decorator

    @socketio.on('connect')
    def handle_connect(auth=None):
        """Authenticate the socket and bind it to a user before any rooms."""
        user = _authenticate(auth)
        if not user:
            # Connected but unauthenticated — cannot join incident rooms.
            emit('connected', {'anonymous': True})
            return

        _sid_users[request.sid] = {
            'user_id': str(user.id),
            'name': user.name,
            'organization_id': str(user.organization_id) if user.organization_id else None,
            'incidents': OrderedDict(),
            'nodes': set(),
            'denied_log_at': 0.0,
        }
        realtime.register_sid(str(user.id), request.sid)
        # Personal + organization rooms for notifications / activity feed.
        join_room(f'user_{user.id}')
        if user.organization_id:
            join_room(f'org_{user.organization_id}')
        emit('connected', {'user_id': str(user.id), 'name': user.name})

    @socketio.on('disconnect')
    def handle_disconnect(*_args):
        sid = request.sid
        _rate_state.pop(sid, None)
        session = _sid_users.pop(sid, None)
        if not session:
            return
        realtime.unregister_sid(session['user_id'], sid)
        for iid, joined in list(session['incidents'].items()):
            realtime.presence_remove(iid, joined['pid'])
            _broadcast_presence_now(socketio, iid)

    @socketio.on('incident:join')
    @guarded('incident:join')
    def handle_join(session, data):
        iid = _incident_id(data)
        if iid is None:
            _error('invalid', 'incident:join')
            return None

        from app.middleware.rbac import check_incident_access
        user = db.session.get(User, session['user_id'])
        allowed, incident = check_incident_access(user, iid)
        if not allowed or not user or not user.is_active:
            now = time.monotonic()
            if now - session.get('denied_log_at', 0.0) >= DENIED_LOG_INTERVAL:
                session['denied_log_at'] = now
                _security_event('ws_join_denied', session, resource_id=iid)
            _error('denied', 'incident:join')
            return None
        iid = str(incident.id)

        scopes = realtime.scopes_for_user(user)
        incidents = session['incidents']
        joined = incidents.get(iid)
        if joined is None:
            while len(incidents) >= MAX_ROOMS_PER_SOCKET:
                oldest = next(iter(incidents))
                _do_leave(socketio, session, oldest)
            joined = {
                'pid': secrets.token_urlsafe(8),
                'since': datetime.now(timezone.utc).isoformat(),
            }
            incidents[iid] = joined
        else:
            incidents.move_to_end(iid)
            # Re-join: drop scope rooms the user may no longer read.
            current = set(rooms())
            for scope in set(joined.get('scopes', ())) - set(scopes):
                room = realtime.scope_room(iid, scope)
                if room in current and room != realtime.base_room(iid):
                    leave_room(room)
        joined['scopes'] = scopes
        joined['can_drag'] = user.has_permission('attack_graph:update')

        join_room(realtime.base_room(iid))
        for scope in scopes:
            join_room(realtime.scope_room(iid, scope))

        realtime.presence_set(iid, joined['pid'], {
            'user_id': session['user_id'], 'name': session['name'],
            'focus': None, 'mode': 'viewing', 'since': joined['since'],
        })
        ack = {
            'incident_id': iid,
            'scopes': scopes,
            'seq': realtime.current_seqs(iid, scopes),
            'presence': realtime.presence_list(iid),
        }
        emit('incident:joined', ack)
        _broadcast_presence_now(socketio, iid)
        return ack

    @socketio.on('incident:leave')
    @guarded('incident:leave')
    def handle_leave(session, data):
        iid = _incident_id(data)
        if iid is None:
            _error('invalid', 'incident:leave')
            return
        # Only rooms this socket actually joined; a non-member (or anonymous
        # socket) can never make the server broadcast into a room.
        if _membership(session, iid) is None:
            return
        _do_leave(socketio, session, iid)

    @socketio.on('presence:update')
    @guarded('presence:update')
    def handle_presence_update(session, data):
        iid = _incident_id(data)
        if iid is None:
            _error('invalid', 'presence:update')
            return
        joined = _membership(session, iid)
        if joined is None:
            _error('denied', 'presence:update')
            return
        focus, ok = _focus(data.get('focus'), joined.get('scopes', ()))
        mode = data.get('mode', 'viewing')
        if not ok or mode not in PRESENCE_MODES:
            _error('invalid', 'presence:update')
            return
        realtime.presence_set(iid, joined['pid'], {
            'user_id': session['user_id'], 'name': session['name'],
            'focus': focus, 'mode': mode, 'since': joined['since'],
        })
        _broadcast_presence_throttled(socketio, iid)

    @socketio.on('graph:node_drag')
    @guarded('graph:node_drag')
    def handle_graph_node_drag(session, data):
        iid = _incident_id(data)
        if iid is None:
            _error('invalid', 'graph:node_drag')
            return
        node_id = _uuid_str(data.get('node_id'))
        x, y = _coord(data.get('x')), _coord(data.get('y'))
        if node_id is None or x is None or y is None:
            _error('invalid', 'graph:node_drag')
            return
        joined = _membership(session, iid)
        if (joined is None or 'attack_graph' not in joined.get('scopes', ())
                or not joined.get('can_drag')):
            _error('denied', 'graph:node_drag')
            return
        cache_key = (iid, node_id)
        if cache_key not in session['nodes']:
            from app.models import AttackGraphNode
            exists = db.session.query(AttackGraphNode.id).filter_by(
                id=node_id, incident_id=iid).first() is not None
            if not exists:
                _error('invalid', 'graph:node_drag')
                return
            if len(session['nodes']) >= MAX_CACHED_NODES:
                session['nodes'].clear()
            session['nodes'].add(cache_key)
        emit('graph:node_drag', {
            'incident_id': iid, 'node_id': node_id, 'x': x, 'y': y,
            'user_id': session['user_id'],
        }, to=realtime.scope_room(iid, 'attack_graph'), include_self=False)

    @socketio.on('ping')
    @guarded('ping', anonymous_ok=True)
    def handle_ping(_session, _data):
        """Handle ping for connection keep-alive."""
        emit('pong')
