---
name: securing-auth-routes
description: Securing authentication routes with CSRF protection, rate limiting, HTTPS enforcement, and brute force mitigation.
---

# Securing Auth Routes

## Goal

Harden all authentication-related endpoints against common attacks by implementing CSRF protection, rate limiting, HTTPS enforcement, security headers, and brute force mitigation.

## When to Use

- After implementing auth routes (login, registration, password reset, OAuth callbacks).
- When preparing an application for production deployment.
- During a security review or hardening pass.
- When adding new auth-related endpoints to an existing application.

## Instructions

### CSRF Protection

For browser-based forms that are not purely API-driven, use SameSite cookies combined with a CSRF token.

```python
import secrets
from flask import session, request, abort

def generate_csrf_token() -> str:
    """Generate a CSRF token and store it in the session."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def validate_csrf_token():
    """Validate the CSRF token from the request against the session."""
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not token or token != session.get("csrf_token"):
        abort(403, description="CSRF validation failed")
```

For API endpoints that use `Authorization: Bearer` headers (not cookies), CSRF protection is typically unnecessary because the token must be explicitly attached by the client. SameSite=Strict cookies provide an additional layer of protection for cookie-based auth.

### Rate Limiting Auth Endpoints

Apply strict rate limits to all authentication endpoints to prevent brute force and credential stuffing attacks.

```python
from functools import wraps
from datetime import datetime, timedelta, timezone

# In-memory store for demonstration; use Redis in production
rate_limit_store: dict[str, list[datetime]] = {}


def rate_limit(max_requests: int, window: timedelta):
    """Decorator to rate limit an endpoint by client IP."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ip = request.remote_addr
            key = f"{f.__name__}:{ip}"
            now = datetime.now(timezone.utc)

            # Clean old entries
            entries = rate_limit_store.get(key, [])
            entries = [t for t in entries if now - t < window]

            if len(entries) >= max_requests:
                return jsonify({"error": "Too many requests. Try again later."}), 429

            entries.append(now)
            rate_limit_store[key] = entries
            return f(*args, **kwargs)
        return wrapped
    return decorator
```

**Recommended limits:**

| Endpoint       | Limit                        |
|----------------|------------------------------|
| Login          | 5 attempts per minute per IP |
| Registration   | 3 attempts per hour per IP   |
| Password reset | 3 attempts per hour per IP   |
| Token refresh  | 10 per minute per IP         |

```python
@auth_bp.route("/login", methods=["POST"])
@rate_limit(max_requests=5, window=timedelta(minutes=1))
def login():
    # ... login logic
    pass


@auth_bp.route("/register", methods=["POST"])
@rate_limit(max_requests=3, window=timedelta(hours=1))
def register():
    # ... registration logic
    pass
```

### HTTPS Enforcement

Redirect all HTTP requests to HTTPS and set the HSTS header to instruct browsers to always use HTTPS.

```python
from flask import redirect, request

@app.before_request
def enforce_https():
    if not request.is_secure and not app.debug:
        url = request.url.replace("http://", "https://", 1)
        return redirect(url, code=301)


@app.after_request
def set_security_headers(response):
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response
```

### Security Headers

Apply these headers to every response:

| Header                       | Value                                  | Purpose                                 |
|------------------------------|----------------------------------------|-----------------------------------------|
| Strict-Transport-Security    | `max-age=31536000; includeSubDomains`  | Enforce HTTPS for 1 year                |
| X-Content-Type-Options       | `nosniff`                              | Prevent MIME type sniffing              |
| X-Frame-Options              | `DENY`                                 | Prevent clickjacking                    |
| Referrer-Policy              | `strict-origin-when-cross-origin`      | Limit referrer information leakage      |

### Brute Force Protection

Combine rate limiting per IP with per-account lockout and exponential backoff.

```python
import math

BASE_DELAY_SECONDS = 1
MAX_DELAY_SECONDS = 900  # 15 minutes


def get_lockout_delay(failed_attempts: int) -> int:
    """Calculate exponential backoff delay based on failed attempts."""
    if failed_attempts < 3:
        return 0
    delay = min(BASE_DELAY_SECONDS * (2 ** (failed_attempts - 3)), MAX_DELAY_SECONDS)
    return int(delay)


def check_brute_force(user) -> bool:
    """Return True if the user is currently locked out."""
    if user.failed_login_attempts < 3:
        return False

    delay = get_lockout_delay(user.failed_login_attempts)
    if user.last_failed_login:
        unlock_time = user.last_failed_login + timedelta(seconds=delay)
        if datetime.now(timezone.utc) < unlock_time:
            return True
    return False
```

### Logging Failed Attempts

Log all failed authentication attempts for security monitoring and incident response.

```python
import logging

security_logger = logging.getLogger("security")


def log_failed_login(email: str, ip: str, reason: str):
    security_logger.warning(
        "Failed login attempt",
        extra={
            "email": email,
            "ip": ip,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
```

## Constraints

### ✅ Do
- Rate limit all authentication endpoints with appropriate thresholds.
- Enforce HTTPS in production with automatic HTTP-to-HTTPS redirects.
- Use SameSite=Strict on all authentication cookies.
- Log all failed authentication attempts with IP address and timestamp.
- Set security headers (HSTS, X-Content-Type-Options, X-Frame-Options) on every response.
- Implement per-account lockout with exponential backoff alongside per-IP rate limiting.


### ❌ Don&#x27;t
- Rely only on client-side validation for any security control.
- Allow HTTP connections in production environments.
- Expose token contents, internal error details, or stack traces in error responses.
- Skip logging for failed authentication attempts.
- Use a single rate limit strategy in isolation; combine IP-based and account-based protections.
- Hard-code rate limit values; make them configurable via environment variables.


## Output Format

**Rate limit exceeded** (429):
```json
{ "error": "Too many requests. Try again later." }
```

**CSRF failure** (403):
```json
{ "error": "CSRF validation failed" }
```

**Successful request with security headers:**
```
HTTP/1.1 200 OK
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
```

## Dependencies

- [Managing Sessions and Tokens](../managing-sessions-tokens/SKILL.md) -- cookie configuration and token handling that these protections wrap around.
- [Managing Flask Middleware](../../backend/managing-flask-middleware/SKILL.md) -- middleware patterns for applying security headers and rate limiting globally.
