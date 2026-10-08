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

    # Fall back to the real client IP. ProxyFix has already populated
    # request.remote_addr from the trusted proxy hop (the rightmost
    # X-Forwarded-For entry), which a client cannot spoof. Do NOT trust the
    # raw leftmost X-Forwarded-For value — it is attacker-controlled and was
    # previously usable to rotate rate-limit buckets and bypass the login
    # limiter via a forged header.
    return request.remote_addr or get_remote_address()


limiter = Limiter(
    key_func=_get_rate_limit_key,
    storage_uri=os.getenv('REDIS_URL', 'memory://'),
    # Generous per-key safety net against runaway abuse. Specific expensive
    # endpoints (auth, bulk enrichment, search, report generation) declare
    # their own stricter limits.
    default_limits=[os.getenv('RATE_LIMIT_DEFAULT', '600 per minute')],
)

# Redis client (initialized in create_app)
redis_client = None


def _resolve_cors_origins(app):
    """Build the explicit CORS / Socket.IO origin allowlist.

    CORS_ORIGINS (comma list) + FRONTEND_URL + local dev defaults. Never "*"
    (credentials are enabled). Returns (origins, explicitly_configured).
    """
    origins = list(app.config.get('CORS_ORIGINS') or [])
    frontend_url = (app.config.get('FRONTEND_URL') or '').strip().rstrip('/')
    if frontend_url:
        origins.append(frontend_url)
    explicit = bool(origins)
    origins.extend([
        'http://localhost:3000', 'http://127.0.0.1:3000',
        'http://localhost:8080', 'http://127.0.0.1:8080',
    ])
    seen = set()
    return [o for o in origins if not (o in seen or seen.add(o))], explicit


def _make_socketio_origin_check(allowed_origins):
    """Socket.IO origin validator: explicit allowlist OR same-origin.

    Same-origin (Origin host == request Host; ProxyFix-style trust of the
    proxy's X-Forwarded-Host) lets reverse-proxy deployments on any hostname
    work without listing it, while cross-site pages are still rejected
    (cross-site WebSocket hijacking via the httpOnly cookie).
    """
    from urllib.parse import urlparse

    allowed = set(allowed_origins)

    def check(origin, environ=None):
        if not origin:
            # Non-browser clients send no Origin; authentication still applies.
            return True
        if origin in allowed:
            return True
        if environ is None:
            return False
        try:
            netloc = urlparse(origin).netloc.lower()
        except ValueError:
            return False
        hosts = {
            (environ.get(h) or '').split(',')[0].strip().lower()
            for h in ('HTTP_X_FORWARDED_HOST', 'HTTP_HOST')
        }
        hosts.discard('')
        return bool(netloc) and netloc in hosts

    return check


def is_token_revoked(jwt_payload, consume_refresh_grace=False):
    """Shared revocation check (HTTP blocklist loader + WebSocket auth).

    Fails CLOSED when the blocklist store is unavailable. Rejects MFA-pending
    pre-auth tokens, blocklisted jtis and tokens minted before the user's
    current token epoch. A just-rotated refresh token is accepted exactly once
    during its short grace window when `consume_refresh_grace` is set.
    """
    from flask import current_app
    if jwt_payload.get('pre_auth') or jwt_payload.get('type') == 'pre_auth':
        return True
    jti = jwt_payload.get('jti')
    if redis_client is None:
        current_app.logger.error('Token blocklist store unavailable; rejecting token.')
        return True
    try:
        if redis_client.get(f'revoked_token:{jti}') is not None:
            if (consume_refresh_grace and jwt_payload.get('type') == 'refresh'
                    and redis_client.delete(f'refresh_grace:{jti}')):
                # Concurrent refresh inside the grace window: allow once.
                return False
            return True
        # Per-user token epoch: tokens minted before the user's current epoch
        # (bumped on password change / reset / disable) are revoked.
        sub = jwt_payload.get('sub')
        epoch_required = redis_client.get(f'token_epoch:{sub}') if sub else None
        if epoch_required is not None:
            try:
                if int(jwt_payload.get('token_epoch', 0)) < int(epoch_required):
                    return True
            except (TypeError, ValueError):
                return True
        return False
    except Exception:
        current_app.logger.error('Token blocklist lookup failed; rejecting token.')
        return True


def create_app(config_name=None):
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load configuration. An unset FLASK_ENV means production semantics
    # (secure cookies, fail-fast on default secrets), consistent with wsgi.py.
    config_name = (config_name or os.getenv('FLASK_ENV') or 'production').lower()
    app.config.from_object(f'app.config.{config_name.capitalize()}Config')

    # Fail fast on insecure default signing secrets outside development — a
    # predictable SECRET_KEY / JWT_SECRET_KEY allows token forgery and account
    # takeover.
    if config_name != 'development':
        _insecure_defaults = {
            'SECRET_KEY': 'dev-secret-key-change-in-production',
            'JWT_SECRET_KEY': 'jwt-secret-key-change-in-production',
        }
        for _key, _default in _insecure_defaults.items():
            _val = app.config.get(_key)
            if not _val or _val == _default:
                raise RuntimeError(
                    f'{_key} is unset or using the insecure built-in default in '
                    f'"{config_name}" mode. Provide a strong random {_key} via '
                    f'environment variable before starting.'
                )

    if not app.config.get('CUSTODY_SIGNING_KEY'):
        app.logger.warning(
            'CUSTODY_SIGNING_KEY is not set; chain-of-custody signatures fall back '
            'to SECRET_KEY. Set a dedicated CUSTODY_SIGNING_KEY so rotating '
            'SECRET_KEY does not invalidate existing custody signatures.'
        )

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

    # CORS configuration — never pair a "*" origin with credentials (that lets
    # any site make credentialed cross-origin requests).
    cors_origins, explicit_origins = _resolve_cors_origins(app)
    if config_name == 'production' and not explicit_origins:
        app.logger.warning(
            'Neither CORS_ORIGINS nor FRONTEND_URL is set; only localhost and '
            'same-origin (reverse-proxied) browser origins are allowed. Set '
            'CORS_ORIGINS / FRONTEND_URL to your public origin(s).'
        )

    CORS(app, resources={
        r"/api/*": {
            "origins": cors_origins,
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            # X-CSRF-TOKEN: double-submit header required by cookie (JWT) auth.
            "allow_headers": ["Content-Type", "Authorization", "X-CSRF-TOKEN"],
            "supports_credentials": True
        }
    })

    # Initialize SocketIO with Redis message queue for scaling (no queue in
    # tests: the in-process test client is used).
    socketio.init_app(
        app,
        cors_allowed_origins=_make_socketio_origin_check(cors_origins),
        message_queue=None if app.testing else app.config.get('REDIS_URL'),
        async_mode=app.config.get('SOCKETIO_ASYNC_MODE', 'eventlet'),
    )

    # Initialize Redis client
    global redis_client
    redis_url = app.config.get('REDIS_URL')
    if redis_url:
        redis_client = redis.from_url(redis_url)

    # Initialize Rate Limiter
    limiter.init_app(app)

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

    # Token blocklist check — fail CLOSED (see is_token_revoked). Pre-auth
    # (MFA-pending) tokens are only valid at /auth/mfa/complete, which decodes
    # them manually, so they are rejected on every @jwt_required route.
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        from flask import request
        return is_token_revoked(
            jwt_payload,
            consume_refresh_grace=(request.endpoint == 'api_v1.refresh'),
        )

    # Global error handler — never leak stack traces / internals to clients.
    # Returns a sanitized body; full detail is logged server-side only.
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        if isinstance(e, HTTPException):
            # Keep the exception's own response so headers such as Allow (405)
            # and Retry-After (429) survive; only the body is replaced.
            import json as _json
            resp = e.get_response()
            resp.set_data(_json.dumps({
                'error': (e.name or 'error').lower().replace(' ', '_'),
                'message': e.description,
            }))
            resp.content_type = 'application/json'
            return resp
        app.logger.exception('Unhandled exception while processing request')
        return {
            'error': 'internal_server_error',
            'message': 'An internal error occurred.',
        }, 500

    return app
