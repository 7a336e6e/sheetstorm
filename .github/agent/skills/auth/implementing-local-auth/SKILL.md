---
name: implementing-local-auth
description: User registration, login, and password hashing with bcrypt for local authentication flows.
---

# Implementing Local Auth

## Goal

Implement a secure local authentication system with user registration, login, and password hashing using bcrypt. The system must validate inputs, enforce password policy, and return JWTs on successful authentication.

## When to Use

- Building a new application that needs email/password authentication.
- Adding local auth alongside existing OAuth providers.
- Replacing an insecure or legacy authentication system.
- Any time users need to create accounts and log in with credentials they control.

## Instructions

### Registration Flow

The registration flow follows these steps: validate input, check uniqueness, hash password, create user, return token.

```python
import bcrypt
from flask import Blueprint, request, jsonify
from marshmallow import Schema, fields, validate, ValidationError

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


class RegisterSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(
        required=True,
        validate=validate.Length(min=8),
    )
    name = fields.Str(required=True, validate=validate.Length(min=1, max=255))


def hash_password(plain: str) -> str:
    """Hash a password with bcrypt using a work factor of 12."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


@auth_bp.route("/register", methods=["POST"])
def register():
    schema = RegisterSchema()
    try:
        data = schema.load(request.get_json())
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": err.messages}), 400

    # Check uniqueness
    existing = User.query.filter_by(email=data["email"]).first()
    if existing:
        # Return generic message to avoid revealing registered emails
        return jsonify({"error": "Registration failed. Please try again."}), 400

    # Hash password and create user
    hashed = hash_password(data["password"])
    user = User(email=data["email"], password_hash=hashed, name=data["name"])
    db.session.add(user)
    db.session.commit()

    token = generate_access_token(user)
    return jsonify({"access_token": token}), 201
```

### Login Flow

The login flow follows these steps: find user by email, verify password, generate token, return token.

```python
class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


@auth_bp.route("/login", methods=["POST"])
def login():
    schema = LoginSchema()
    try:
        data = schema.load(request.get_json())
    except ValidationError as err:
        return jsonify({"error": "Invalid credentials"}), 401

    user = User.query.filter_by(email=data["email"]).first()
    if not user or not verify_password(data["password"], user.password_hash):
        return jsonify({"error": "Invalid credentials"}), 401

    token = generate_access_token(user)
    return jsonify({"access_token": token}), 200
```

### Input Validation

- **Email format**: Use a schema validator to enforce RFC-compliant email addresses.
- **Password strength**: Minimum 8 characters with complexity requirements. See [password-policy.md](references/password-policy.md) for full policy.
- **Name**: Non-empty string, max 255 characters.

### Password Hashing with bcrypt

Always use bcrypt with a work factor of 12. This provides a good balance between security and performance. The work factor doubles the computation for each increment, so 12 results in 2^12 (4096) iterations of the key derivation.

```python
# Work factor 12 is the recommended default
salt = bcrypt.gensalt(rounds=12)
hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
```

## Constraints

### ✅ Do
- Hash passwords with bcrypt using a work factor of 12.
- Validate email format before processing registration.
- Rate limit registration endpoints to prevent abuse.
- Return consistent, generic error messages for both login and registration failures.
- Enforce password complexity requirements as defined in the password policy.
- Store only the bcrypt hash, never the plaintext password.


### ❌ Don&#x27;t
- Store plaintext passwords under any circumstances.
- Reveal whether an email address is already registered on login failure.
- Use MD5 or SHA family hashes for password storage.
- Allow unlimited registration attempts from a single IP.
- Return different error messages for "user not found" vs "wrong password".
- Log plaintext passwords in any application or server logs.


## Output Format

**Registration success** (201):
```json
{ "access_token": "<jwt>" }
```

**Login success** (200):
```json
{ "access_token": "<jwt>" }
```

**Validation error** (400):
```json
{ "error": "Validation failed", "details": { "email": ["Not a valid email address."] } }
```

**Auth failure** (401):
```json
{ "error": "Invalid credentials" }
```

## Dependencies

- [Building API Routes](../../backend/building-api-routes/SKILL.md) -- route structure and request handling.
- [Designing Schemas](../../database/designing-schemas/SKILL.md) -- user table schema design.
- [Password Policy](references/password-policy.md) -- password strength and lockout rules.
