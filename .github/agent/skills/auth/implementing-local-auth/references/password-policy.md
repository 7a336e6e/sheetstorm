---
name: password-policy
description: Reference document defining password strength requirements, lockout rules, and reset procedures.
---

# Password Policy

This document defines the password policy for local authentication. It follows NIST Special Publication 800-63B guidelines where applicable.

## Length Requirements

- **Minimum length**: 8 characters.
- **No maximum length enforced by the application**. However, bcrypt truncates input at 72 bytes. Passwords longer than 72 bytes are accepted but only the first 72 bytes influence the hash. This must be documented in user-facing help text.
- If support for passwords longer than 72 bytes is needed, pre-hash the password with SHA-256 before passing it to bcrypt.

## Complexity Requirements

At minimum, a valid password must contain:

- At least **1 uppercase letter** (A-Z).
- At least **1 lowercase letter** (a-z).
- At least **1 digit** (0-9).

Special characters are encouraged but not required.

## Allowed Characters

- All printable ASCII characters (codes 32-126) are permitted.
- Unicode characters are permitted. The application must handle UTF-8 encoding consistently when hashing.
- No characters are explicitly forbidden.

## Common Password Check

- Every password must be checked against a list of the **top 10,000 most common passwords**.
- If the password appears in this list, registration must be rejected with a message such as: "This password is too common. Please choose a different password."
- The common password list should be loaded once at application startup and stored in memory for fast lookups using a set.

```python
import pathlib

COMMON_PASSWORDS: set[str] = set()

def load_common_passwords():
    path = pathlib.Path(__file__).parent / "data" / "common-passwords.txt"
    with open(path) as f:
        COMMON_PASSWORDS.update(line.strip().lower() for line in f if line.strip())

def is_common_password(password: str) -> bool:
    return password.lower() in COMMON_PASSWORDS
```

## Password Rotation

- **No forced password rotation**. This follows NIST 800-63B section 5.1.1.2, which recommends against periodic password changes. Forced rotation leads to weaker passwords as users make predictable incremental changes.
- Passwords should only be changed when there is evidence of compromise.

## Account Lockout

- After **5 consecutive failed login attempts**, the account is locked for **15 minutes**.
- The lockout is per-account, not per-IP, to prevent attackers from cycling through IPs.
- Failed attempt counters reset after a successful login.
- Locked accounts return the same generic "Invalid credentials" error to avoid revealing lockout state to attackers.

```python
from datetime import datetime, timedelta

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)

def is_account_locked(user) -> bool:
    if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        if user.last_failed_login and datetime.utcnow() - user.last_failed_login < LOCKOUT_DURATION:
            return True
        # Lockout period has passed — reset counter
        user.failed_login_attempts = 0
        db.session.commit()
    return False

def record_failed_attempt(user):
    user.failed_login_attempts += 1
    user.last_failed_login = datetime.utcnow()
    db.session.commit()

def reset_failed_attempts(user):
    user.failed_login_attempts = 0
    user.last_failed_login = None
    db.session.commit()
```

## Password Reset

- Password reset is initiated via an email containing a one-time-use token.
- The reset token **expires after 1 hour**.
- Tokens are stored as hashed values in the database (using SHA-256), not in plaintext.
- The reset link format: `https://{domain}/reset-password?token={token}`
- After a successful reset, all existing sessions for that user must be invalidated.
- The reset endpoint must be rate-limited (3 requests per hour per email address).

```python
import secrets
import hashlib
from datetime import datetime, timedelta

def generate_reset_token() -> tuple[str, str]:
    """Return (raw_token, hashed_token). Send raw_token to user, store hashed_token."""
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed

RESET_TOKEN_EXPIRY = timedelta(hours=1)

def is_reset_token_valid(stored_hash: str, submitted_token: str, created_at: datetime) -> bool:
    submitted_hash = hashlib.sha256(submitted_token.encode()).hexdigest()
    if submitted_hash != stored_hash:
        return False
    if datetime.utcnow() - created_at > RESET_TOKEN_EXPIRY:
        return False
    return True
```

## Validation Helper

A combined validation function for use during registration:

```python
import re

def validate_password(password: str) -> list[str]:
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        errors.append("Password must contain at least one digit.")
    if is_common_password(password):
        errors.append("This password is too common. Please choose a different password.")
    return errors
```
