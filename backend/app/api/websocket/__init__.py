"""WebSocket handlers for real-time collaboration"""
from flask import request
from flask_socketio import emit, join_room, leave_room, rooms
from flask_jwt_extended import decode_token
from app import db
from app.models import User

# Track connected users per incident
connected_users = {}


def register_handlers(socketio):
    """Register all WebSocket event handlers."""

    @socketio.on('connect')
    def handle_connect():
        """Handle client connection."""
        # Try to authenticate
        auth_token = request.args.get('token')
        if auth_token:
            try:
                decoded = decode_token(auth_token)
                user_id = decoded.get('sub')
                user = User.query.get(user_id)
                if user:
                    # Join user's personal room for notifications
                    join_room(f'user_{user_id}')
                    emit('connected', {
                        'user_id': str(user.id),
                        'name': user.name
                    })
                    return
            except Exception:
                pass

        # Allow anonymous connection but limit functionality
        emit('connected', {'anonymous': True})

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
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
        """Join an incident room for real-time updates."""
        incident_id = data.get('incident_id')
        user_id = data.get('user_id')
        user_name = data.get('user_name')

        if not incident_id:
            emit('error', {'message': 'incident_id required'})
            return

        room = f'incident_{incident_id}'
        join_room(room)

        # Track connected user
        if incident_id not in connected_users:
            connected_users[incident_id] = []

        user_info = {
            'sid': request.sid,
            'user_id': user_id,
            'name': user_name
        }
        connected_users[incident_id].append(user_info)

        # Notify room of new user
        emit('user_joined', user_info, room=room)

        # Send current users list to joining user
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
        user_id = data.get('user_id')
        user_name = data.get('user_name')

        if not incident_id:
            return

        emit('cursor_moved', {
            'user_id': user_id,
            'user_name': user_name,
            'position': position
        }, room=f'incident_{incident_id}', include_self=False)

    @socketio.on('typing_start')
    def handle_typing_start(data):
        """Broadcast typing indicator."""
        incident_id = data.get('incident_id')
        field = data.get('field')
        user_id = data.get('user_id')
        user_name = data.get('user_name')

        if not incident_id:
            return

        emit('user_typing', {
            'user_id': user_id,
            'user_name': user_name,
            'field': field,
            'typing': True
        }, room=f'incident_{incident_id}', include_self=False)

    @socketio.on('typing_stop')
    def handle_typing_stop(data):
        """Broadcast typing stopped."""
        incident_id = data.get('incident_id')
        field = data.get('field')
        user_id = data.get('user_id')

        if not incident_id:
            return

        emit('user_typing', {
            'user_id': user_id,
            'field': field,
            'typing': False
        }, room=f'incident_{incident_id}', include_self=False)

    @socketio.on('graph_node_moved')
    def handle_graph_node_moved(data):
        """Broadcast graph node position change."""
        incident_id = data.get('incident_id')
        node_id = data.get('node_id')
        position = data.get('position')
        user_id = data.get('user_id')

        if not incident_id or not node_id:
            return

        emit('graph_node_position', {
            'node_id': node_id,
            'position': position,
            'user_id': user_id
        }, room=f'incident_{incident_id}', include_self=False)

    @socketio.on('ping')
    def handle_ping():
        """Handle ping for connection keep-alive."""
        emit('pong')
