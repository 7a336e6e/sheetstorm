"""SheetStorm Backend Application Factory"""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_socketio import SocketIO
from flask_jwt_extended import JWTManager
import redis

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
socketio = SocketIO()

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def _get_rate_limit_key():
    """Get a per-user rate limit key.
    
    For authenticated requests, use the JWT user ID so each user has their own
    rate-limit bucket. For unauthenticated requests (login, register), fall back
    to the real client IP extracted from X-Forwarded-For / X-Real-IP headers
    (set by the nginx reverse proxy). This prevents the proxy's internal IP from
    being used as a shared key for all users.
    """
    from flask import request

    # For authenticated users, key by user ID
    try:
        from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity:
            return f"user:{identity}"
    except Exception:
        pass

    # Fall back to real client IP behind proxy
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    if forwarded_for:
        # X-Forwarded-For can be "client, proxy1, proxy2" — take the first
        return forwarded_for.split(',')[0].strip()

    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip

    return get_remote_address()


limiter = Limiter(
    key_func=_get_rate_limit_key,
    storage_uri=os.getenv('REDIS_URL', 'memory://'),
)

# Redis client (initialized in create_app)
redis_client = None


def create_app(config_name=None):
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load configuration
    config_name = config_name or os.getenv('FLASK_ENV', 'development')
    app.config.from_object(f'app.config.{config_name.capitalize()}Config')

    # Fix request.remote_addr when behind nginx reverse proxy.
    # This trusts 1 proxy (nginx) and uses X-Forwarded-For / X-Real-IP
    # headers to populate the real client IP into request.remote_addr.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,       # Trust X-Forwarded-For (1 proxy hop)
        x_proto=1,     # Trust X-Forwarded-Proto
        x_host=1,      # Trust X-Forwarded-Host
        x_prefix=0,    # Don't trust X-Forwarded-Prefix
    )

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # CORS configuration
    cors_origins_str = os.getenv('CORS_ORIGINS', '')
    if cors_origins_str:
        cors_origins = [o.strip() for o in cors_origins_str.split(',') if o.strip()]
    else:
        cors_origins = "*"
    
    CORS(app, resources={
        r"/api/*": {
            "origins": cors_origins,
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True
        }
    })

    # Initialize SocketIO with Redis message queue for scaling
    socketio.init_app(
        app,
        cors_allowed_origins=cors_origins,
        message_queue=app.config.get('REDIS_URL'),
        async_mode='eventlet'
    )

    # Initialize Redis client
    global redis_client
    redis_url = app.config.get('REDIS_URL')
    if redis_url:
        redis_client = redis.from_url(redis_url)

    # Initialize Rate Limiter
    limiter.init_app(app)
    
    # Initialize Security Headers
    
    # Initialize Security Headers
    from flask_talisman import Talisman
    Talisman(
        app,
        content_security_policy={
            'default-src': ["'self'"],
            'script-src': ["'self'"],
            'style-src': ["'self'", "'unsafe-inline'"],
            'img-src': ["'self'", "data:", "https:"],
            'connect-src': ["'self'"],
        },
        force_https=False,  # Handled by reverse proxy
        strict_transport_security=True,
        strict_transport_security_max_age=31536000,
        session_cookie_secure=True,
        session_cookie_http_only=True,
    )

    # Initialize Input Sanitization Middleware
    from app.middleware.sanitize import init_sanitization
    init_sanitization(app)

    # Register blueprints
    from app.api.v1 import api_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    # Register WebSocket handlers
    from app.api.websocket import register_handlers
    register_handlers(socketio)

    # JWT error handlers
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return {'error': 'token_expired', 'message': 'Token has expired'}, 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return {'error': 'invalid_token', 'message': 'Invalid token'}, 401

    @jwt.unauthorized_loader
    def unauthorized_callback(error):
        return {'error': 'unauthorized', 'message': 'Missing authorization header'}, 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return {'error': 'token_revoked', 'message': 'Token has been revoked'}, 401

    # Token blocklist check
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        jti = jwt_payload['jti']
        if redis_client:
            return redis_client.get(f'revoked_token:{jti}') is not None
        return False

    return app
