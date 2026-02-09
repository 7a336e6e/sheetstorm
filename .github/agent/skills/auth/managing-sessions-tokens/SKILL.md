---
name: managing-sessions-tokens
description: JWT access tokens, refresh tokens, cookie management, token rotation, and revocation strategies.
---

# Managing Sessions and Tokens

## Goal

Implement a JWT-based authentication token system with short-lived access tokens, long-lived refresh tokens stored in httpOnly cookies, token rotation on refresh, and a revocation mechanism for logout.

## When to Use

- After implementing local auth or OAuth, to manage authenticated sessions.
- When transitioning from server-side sessions to stateless JWT-based auth.
- When building an API that needs to support both browser clients (cookies) and mobile clients (bearer tokens).
- When adding logout or "sign out everywhere" functionality.

## Instructions

### JWT Structure

A JWT consists of three parts: header, payload, and signature.

**Header:**
```json
{ "alg": "HS256", "typ": "JWT" }
```

**Payload (claims):**
```json
{
  "sub": "user-uuid",
  "exp": 1700000000,
  "iat": 1699999100,
  "role": "user"
}
```

- `sub` -- Subject, the user's unique identifier.
- `exp` -- Expiration time as a Unix timestamp.
- `iat` -- Issued-at time as a Unix timestamp.
- `role` -- The user's role for authorization checks.

### Access Token

Access tokens are short-lived (15 minutes) and sent in the `Authorization` header.

```python
import jwt
from datetime import datetime, timedelta, timezone

SECRET_KEY = app.config["JWT_SECRET_KEY"]
ACCESS_TOKEN_EXPIRY = timedelta(minutes=15)


def generate_access_token(user) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + ACCESS_TOKEN_EXPIRY,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
```

### Refresh Token

Refresh tokens are long-lived (7 days) and stored in an httpOnly, Secure, SameSite cookie. They are used to obtain new access tokens without requiring the user to log in again.

```python
import secrets

REFRESH_TOKEN_EXPIRY = timedelta(days=7)


def generate_refresh_token(user) -> str:
    """Generate an opaque refresh token and store it in the database."""
    raw_token = secrets.token_urlsafe(32)
    refresh = RefreshToken(
        user_id=user.id,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + REFRESH_TOKEN_EXPIRY,
    )
    db.session.add(refresh)
    db.session.commit()
    return raw_token


def set_refresh_cookie(response, token: str):
    response.set_cookie(
        "refresh_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="Strict",
        max_age=int(REFRESH_TOKEN_EXPIRY.total_seconds()),
        path="/api/v1/auth/refresh",
    )
```

### Token Rotation

Each time a refresh token is used, issue a new refresh token and invalidate the old one. This limits the window of exposure if a refresh token is compromised.

```python
@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    raw_token = request.cookies.get("refresh_token")
    if not raw_token:
        return jsonify({"error": "Missing refresh token"}), 401

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    stored = RefreshToken.query.filter_by(token_hash=token_hash, revoked=False).first()

    if not stored or stored.expires_at < datetime.now(timezone.utc):
        return jsonify({"error": "Invalid or expired refresh token"}), 401

    # Revoke the old token
    stored.revoked = True
    db.session.commit()

    user = User.query.get(stored.user_id)

    # Issue new tokens
    access_token = generate_access_token(user)
    new_refresh = generate_refresh_token(user)

    response = jsonify({"access_token": access_token})
    set_refresh_cookie(response, new_refresh)
    return response, 200
```

### Token Revocation

Maintain a blocklist for logged-out access tokens. On logout, revoke the refresh token and add the access token's `jti` (or the token itself) to the blocklist until it expires.

```python
@auth_bp.route("/logout", methods=["POST"])
def logout():
    # Revoke refresh token
    raw_token = request.cookies.get("refresh_token")
    if raw_token:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        stored = RefreshToken.query.filter_by(token_hash=token_hash).first()
        if stored:
            stored.revoked = True
            db.session.commit()

    # Blocklist the access token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header.split(" ", 1)[1]
        try:
            payload = decode_access_token(access_token)
            ttl = payload["exp"] - int(datetime.now(timezone.utc).timestamp())
            if ttl > 0:
                redis_client.setex(f"blocklist:{access_token}", ttl, "1")
        except jwt.InvalidTokenError:
            pass

    response = jsonify({"message": "Logged out"})
    response.delete_cookie("refresh_token", path="/api/v1/auth/refresh")
    return response, 200
```

### Token Verification Decorator

```python
from functools import wraps

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing token"}), 401

        token = auth_header.split(" ", 1)[1]

        # Check blocklist
        if redis_client.get(f"blocklist:{token}"):
            return jsonify({"error": "Token revoked"}), 401

        try:
            payload = decode_access_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        request.current_user = payload
        return f(*args, **kwargs)
    return decorated
```

## Constraints

### ✅ Do
- Use short expiry (15 minutes) for access tokens.
- Set httpOnly, Secure, and SameSite=Strict flags on refresh token cookies.
- Rotate refresh tokens on every use, invalidating the previous token.
- Revoke both access and refresh tokens on logout.
- Scope the refresh cookie path to the refresh endpoint only.
- Store refresh tokens as hashed values in the database.


### ❌ Don&#x27;t
- Store tokens in localStorage or sessionStorage; use httpOnly cookies for refresh tokens.
- Use long-lived access tokens (more than 30 minutes).
- Skip token revocation on logout; users expect logout to be immediate.
- Embed sensitive data (passwords, PII) in the JWT payload.
- Use the same secret key for access tokens and other application secrets.
- Skip blocklist checks when verifying access tokens.


## Output Format

**Refresh success** (200):
```json
{ "access_token": "<new-jwt>" }
```
Set-Cookie header with new refresh token.

**Logout success** (200):
```json
{ "message": "Logged out" }
```

**Token error** (401):
```json
{ "error": "Token expired" }
```

## Dependencies

- [Implementing Local Auth](../implementing-local-auth/SKILL.md) -- user model and login flow that issues tokens.
- [Scaffolding Flask](../../backend/scaffolding-flask/SKILL.md) -- Flask application and configuration setup.
