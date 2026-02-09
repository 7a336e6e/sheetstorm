---
name: Handling Errors
description: Implement centralized error handling in Flask with custom exceptions, global handlers, and structured error responses.
---

# Handling Errors

## Goal

Build a centralized error handling system for a Flask API that uses custom exception classes, registers global error handlers, returns consistent JSON error responses, and logs errors with full request context.

## When to Use

- Setting up error handling in a new Flask API.
- Replacing ad-hoc try/except blocks with a centralized pattern.
- Adding structured error responses to an existing application.
- Improving error logging and observability.
- Onboarding to a codebase that needs consistent error treatment.

## Instructions

### Custom Exception Hierarchy

Define a base API exception and specific subclasses. Each exception carries a status code, an error code string, and an optional details payload.

```python
# app/exceptions.py


class APIError(Exception):
    """Base exception for all API errors."""
    status_code = 500
    error_code = "INTERNAL_ERROR"
    message = "An unexpected error occurred."

    def __init__(self, message=None, details=None):
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details

    def to_dict(self):
        payload = {
            "code": self.error_code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class NotFoundError(APIError):
    status_code = 404
    error_code = "NOT_FOUND"
    message = "The requested resource was not found."


class ValidationError(APIError):
    status_code = 422
    error_code = "VALIDATION_ERROR"
    message = "The request data is invalid."


class AuthError(APIError):
    status_code = 401
    error_code = "AUTH_ERROR"
    message = "Authentication is required."


class ForbiddenError(APIError):
    status_code = 403
    error_code = "FORBIDDEN"
    message = "You do not have permission to perform this action."


class ConflictError(APIError):
    status_code = 409
    error_code = "CONFLICT"
    message = "The request conflicts with the current state of the resource."
```

### Global Error Handler Registration

Register handlers in `create_app()` so every unhandled exception gets a consistent JSON response.

```python
# app/error_handlers.py

import logging
from flask import jsonify, request, g
from app.exceptions import APIError

logger = logging.getLogger(__name__)


def register_error_handlers(app):
    """Register global error handlers on the Flask app."""

    @app.errorhandler(APIError)
    def handle_api_error(error):
        response = jsonify({"error": error.to_dict()})
        response.status_code = error.status_code

        logger.warning(
            "api_error",
            extra={
                "error_code": error.error_code,
                "status_code": error.status_code,
                "message": error.message,
                "path": request.path,
                "request_id": getattr(g, "request_id", None),
            },
        )

        return response

    @app.errorhandler(404)
    def handle_not_found(error):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Resource not found."}}), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        return jsonify({"error": {"code": "METHOD_NOT_ALLOWED", "message": "Method not allowed."}}), 405

    @app.errorhandler(500)
    def handle_internal_error(error):
        logger.exception(
            "unhandled_exception",
            extra={
                "path": request.path,
                "method": request.method,
                "request_id": getattr(g, "request_id", None),
            },
        )
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}}), 500
```

### Error Response Format

All error responses follow this structure:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request data is invalid.",
    "details": {
      "email": ["Not a valid email address."],
      "name": ["Missing data for required field."]
    }
  }
}
```

- `code` is a machine-readable string that clients can switch on.
- `message` is a human-readable summary.
- `details` is optional and holds field-level or context-specific information.

### Raising Exceptions in Application Code

Raise custom exceptions anywhere in the application. The global handler catches them.

```python
from app.exceptions import NotFoundError, ValidationError


def get_user_or_404(user_id):
    user = User.query.get(user_id)
    if user is None:
        raise NotFoundError(f"User with id {user_id} not found.")
    return user


def create_user(data):
    if User.query.filter_by(email=data["email"]).first():
        raise ConflictError("A user with this email already exists.")
    user = User(**data)
    db.session.add(user)
    db.session.commit()
    return user
```

### Logging Errors with Context

Always include the request ID, user identity (if available), and endpoint in error logs. For 500-level errors, use `logger.exception()` to capture the stack trace in logs without exposing it to the client.

```python
logger.exception(
    "unhandled_exception",
    extra={
        "request_id": getattr(g, "request_id", None),
        "user_id": getattr(g, "current_user_id", None),
        "endpoint": request.endpoint,
        "method": request.method,
        "path": request.path,
    },
)
```

### Wiring It Into create_app()

```python
from app.error_handlers import register_error_handlers


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name or "development"])

    register_error_handlers(app)

    # ... extensions, blueprints, middleware

    return app
```

## Constraints

### ✅ Do
- Use custom exception classes that inherit from a common `APIError` base.
- Register global error handlers for `APIError`, 404, 405, and 500.
- Return consistent JSON error responses with `code`, `message`, and optional `details`.
- Log all 500-level errors with `logger.exception()` to capture stack traces.
- Include the request ID and endpoint in error log context.
- Use specific exception subclasses (`NotFoundError`, `ValidationError`) instead of generic exceptions.


### ❌ Don&#x27;t
- Do not catch bare `Exception` in route handlers; let errors propagate to the global handler.
- Do not expose stack traces or internal error details to API clients.
- Do not return HTML error pages from an API; always return JSON.
- Do not silently swallow exceptions without logging.
- Do not return 200 status codes for errors.
- Do not use generic error messages that give no indication of what went wrong.


## Output Format

Generate `app/exceptions.py` and `app/error_handlers.py` as separate files. Show the updated `create_app()` with `register_error_handlers(app)` called.

## Dependencies

- [Scaffolding Flask](../scaffolding-flask/SKILL.md) -- app factory where error handlers are registered.
- [Building API Routes](../building-api-routes/SKILL.md) -- routes that raise these custom exceptions.
