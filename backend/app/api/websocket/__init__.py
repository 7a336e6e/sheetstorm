"""WebSocket handlers for real-time collaboration"""
from flask import request
from flask_socketio import emit, join_room, leave_room, rooms
from flask_jwt_extended import decode_token
from app import db
from app.models import User

# Track connected users per incident
connected_users = {}

# Map socket session id -> authenticated user info. Identity is established
# server-side at connect time from the JWT and is never taken from client
# event payloads (which are spoofable).
_sid_users = {}


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

        Uses the first candidate token that is a valid, unrevoked ACCESS token
        for an active user — a stale/garbage value in one location (e.g. an
        old query-string token) must not shadow a valid cookie. Refresh and
        MFA pre-auth tokens are never accepted for realtime access.
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
            if is_token_revoked(decoded):
                continue
            user = db.session.get(User, decoded.get('sub'))
            if not user or not user.is_active:
                continue
            return user
        return None

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
        }
        # Personal + organization rooms for notifications / activity feed.
        join_room(f'user_{user.id}')
        if user.organization_id:
            join_room(f'org_{user.organization_id}')
        emit('connected', {'user_id': str(user.id), 'name': user.name})

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        _sid_users.pop(request.sid, None)
        # Clean up from all incident rooms
        for room in list(rooms()):
            if room.startswith('incident_'):
                incident_id = room.replace('incident_', '')
                if incident_id in connected_users:
                    # Remove user from tracking
                    connected_users[incident_id] = [
                        u for u in connected_users.get(incident_id, [])
                        if u.get('sid') != request.sid
                    ]
                    # Notify others
                    emit('user_left', {'sid': request.sid}, room=room)

    @socketio.on('join_incident')
    def handle_join_incident(data):
        """Join an incident room after verifying server-side access."""
        incident_id = (data or {}).get('incident_id') if isinstance(data, dict) else None
        if not incident_id:
            emit('error', {'message': 'incident_id required'})
            return

        session = _sid_users.get(request.sid)
        if not session:
            emit('error', {'message': 'authentication required'})
            return

        # Authorization is enforced server-side against the authenticated user;
        # the client cannot supply its own identity or bypass incident scoping.
        from app.middleware.rbac import check_incident_access
        user = db.session.get(User, session['user_id'])
        allowed, _incident = check_incident_access(user, incident_id)
        if not allowed or not user or not user.is_active:
            emit('error', {'message': 'access denied'})
            return
        incident_id = str(_incident.id)  # canonical form used by server emits

        room = f'incident_{incident_id}'
        join_room(room)

        if incident_id not in connected_users:
            connected_users[incident_id] = []
        user_info = {
            'sid': request.sid,
            'user_id': session['user_id'],
            'name': session['name'],
        }
        connected_users[incident_id].append(user_info)

        emit('user_joined', user_info, room=room)
        emit('users_in_room', {'users': connected_users[incident_id]})

    @socketio.on('leave_incident')
    def handle_leave_incident(data):
        """Leave an incident room."""
        incident_id = data.get('incident_id')

        if not incident_id:
            return

        room = f'incident_{incident_id}'
        leave_room(room)

        # Remove from tracking
        if incident_id in connected_users:
            connected_users[incident_id] = [
                u for u in connected_users[incident_id]
                if u.get('sid') != request.sid
            ]

        # Notify room
        emit('user_left', {'sid': request.sid}, room=room)

    @socketio.on('cursor_move')
    def handle_cursor_move(data):
        """Broadcast cursor position to incident room."""
        incident_id = data.get('incident_id')
        position = data.get('position')
        session = _sid_users.get(request.sid) or {}

        if not incident_id or f'incident_{incident_id}' not in rooms():
            return

        emit('cursor_moved', {
            'user_id': session.get('user_id'),
            'user_name': session.get('name'),
            'position': position
        }, room=f'incident_{incident_id}', include_self=False)

    @socketio.on('typing_start')
    def handle_typing_start(data):
        """Broadcast typing indicator."""
        incident_id = data.get('incident_id')
        field = data.get('field')
        session = _sid_users.get(request.sid) or {}

        if not incident_id or f'incident_{incident_id}' not in rooms():
            return

        emit('user_typing', {
            'user_id': session.get('user_id'),
            'user_name': session.get('name'),
            'field': field,
            'typing': True
        }, room=f'incident_{incident_id}', include_self=False)

    @socketio.on('typing_stop')
    def handle_typing_stop(data):
        """Broadcast typing stopped."""
        incident_id = data.get('incident_id')
        field = data.get('field')
        session = _sid_users.get(request.sid) or {}

        if not incident_id or f'incident_{incident_id}' not in rooms():
            return

        emit('user_typing', {
            'user_id': session.get('user_id'),
            'field': field,
            'typing': False
        }, room=f'incident_{incident_id}', include_self=False)

    @socketio.on('graph_node_moved')
    def handle_graph_node_moved(data):
        """Broadcast graph node position change."""
        incident_id = data.get('incident_id')
        node_id = data.get('node_id')
        position = data.get('position')
        session = _sid_users.get(request.sid) or {}

        if not incident_id or not node_id or f'incident_{incident_id}' not in rooms():
            return

        emit('graph_node_position', {
            'node_id': node_id,
            'position': position,
            'user_id': session.get('user_id')
        }, room=f'incident_{incident_id}', include_self=False)

    @socketio.on('ping')
    def handle_ping():
        """Handle ping for connection keep-alive."""
        emit('pong')
