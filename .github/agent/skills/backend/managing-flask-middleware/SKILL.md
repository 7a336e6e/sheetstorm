---
name: Managing Flask Middleware
description: Configure Flask middleware for CORS, rate limiting, security headers, and request logging.
---

# Managing Flask Middleware

## Goal

Set up middleware in a Flask application to handle cross-origin requests, enforce rate limits, add security headers, and log requests with timing and traceability.

## When to Use

- Adding CORS support for a frontend on a different origin.
- Protecting endpoints from abuse with rate limiting.
- Hardening the application with security headers.
- Adding structured request logging with unique request IDs.
- Reviewing or auditing the middleware stack of an existing app.

## Instructions

### CORS Configuration

Use `flask-cors` to manage Cross-Origin Resource Sharing. Always whitelist specific origins rather than allowing all.

```python
from flask_cors import CORS


def configure_cors(app):
    """Set up CORS with explicit origin whitelist."""
    allowed_origins = app.config.get("CORS_ORIGINS", [
        "http://localhost:3000",
        "https://app.example.com",
    ])

    CORS(app, resources={
        r"/api/*": {
            "origins": allowed_origins,
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "expose_headers": ["X-Request-ID"],
            "supports_credentials": True,
            "max_age": 600,
        }
    })
```

Key points:
- Scope CORS to `/api/*` paths only.
- Explicitly list allowed methods and headers.
- Set `max_age` so browsers cache preflight responses.
- Use `supports_credentials` only if cookies or auth headers are sent cross-origin.

### Rate Limiting

Use `flask-limiter` to enforce per-endpoint and global rate limits.

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="redis://localhost:6379/0",
)


def configure_rate_limiting(app):
    """Attach the rate limiter to the app."""
    limiter.init_app(app)
```

Apply stricter limits to sensitive endpoints:

```python
from app.extensions import limiter


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    # ... authentication logic
    pass


@auth_bp.route("/password-reset", methods=["POST"])
@limiter.limit("3 per hour")
def password_reset():
    # ... password reset logic
    pass
```

### Security Headers

Add security headers via a `@app.after_request` hook:

```python
def configure_security_headers(app):
    """Add security headers to every response."""

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Remove the default Server header to avoid leaking info
        response.headers.pop("Server", None)

        return response
```

### Request Logging Middleware

Assign a unique request ID and log timing for every request:

```python
import uuid
import time
import logging
from flask import g, request

logger = logging.getLogger(__name__)


def configure_request_logging(app):
    """Log each request with a unique ID and response time."""

    @app.before_request
    def start_timer_and_set_request_id():
        g.start_time = time.perf_counter()
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    @app.after_request
    def log_request(response):
        duration_ms = (time.perf_counter() - g.start_time) * 1000
        response.headers["X-Request-ID"] = g.request_id

        logger.info(
            "request_completed",
            extra={
                "request_id": g.request_id,
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "remote_addr": request.remote_addr,
            },
        )

        return response
```

### Complete Middleware Setup in create_app()

Wire everything together inside the app factory:

```python
from flask import Flask
from app.middleware.cors import configure_cors
from app.middleware.rate_limiting import configure_rate_limiting
from app.middleware.security import configure_security_headers
from app.middleware.logging import configure_request_logging


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name or "development"])

    # Middleware (order matters)
    configure_request_logging(app)
    configure_cors(app)
    configure_rate_limiting(app)
    configure_security_headers(app)

    # Extensions and blueprints ...

    return app
```

## Constraints

### ✅ Do
- Whitelist specific origins for CORS instead of using a wildcard.
- Set rate limits on authentication and password-related endpoints.
- Add a unique request ID to every request for tracing.
- Log the method, path, status code, and duration for each request.
- Configure middleware inside `create_app()` so it respects the app factory pattern.
- Use Redis as the backend for rate limit storage in production.


### ❌ Don&#x27;t
- Do not set `CORS origins` to `"*"` in production.
- Do not skip rate limiting on authentication endpoints; these are the most targeted.
- Do not expose the `Server` header or framework version in responses.
- Do not log sensitive data (passwords, tokens, full request bodies) in request logs.
- Do not rely on in-memory rate limit storage in multi-worker or multi-process deployments.


## Output Format

Produce each middleware module as a separate file under `app/middleware/`. Show the updated `create_app()` function with all middleware calls included.

## Dependencies

- [Scaffolding Flask](../scaffolding-flask/SKILL.md) -- app factory where middleware is registered.
