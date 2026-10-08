"""WSGI entry point for the application."""
import os
os.environ['EVENTLET_NO_GREENDNS'] = 'yes'

import eventlet
eventlet.monkey_patch()

from app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    # Debug (Werkzeug debugger + reloader) is only enabled in development.
    # Never run with debug=True in production — it leaks stack traces and
    # exposes an interactive console.
    debug = os.environ.get('FLASK_ENV', 'production').lower() == 'development'
    socketio.run(app, host='0.0.0.0', port=5000, debug=debug)
