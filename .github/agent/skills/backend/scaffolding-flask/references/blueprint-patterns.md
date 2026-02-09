---
name: Blueprint Patterns
description: Reference for Flask blueprint organization, naming conventions, and splitting guidelines.
---

# Blueprint Patterns

## One Blueprint Per Domain

Each distinct domain in the application gets its own blueprint. Common domains include:

| Blueprint | Prefix               | Responsibility                |
|-----------|----------------------|-------------------------------|
| auth      | /api/v1/auth         | Login, logout, token refresh  |
| users     | /api/v1/users        | User CRUD, profile management |
| tasks     | /api/v1/tasks        | Task CRUD, assignment         |
| admin     | /api/v1/admin        | Admin-only operations         |

## Blueprint File Structure

Each blueprint lives in its own package under `app/routes/`:

```
app/routes/users/
    __init__.py      # Blueprint instance and route imports
    routes.py        # Route handlers
    schemas.py       # Marshmallow or pydantic schemas for this domain
    services.py      # Business logic called by route handlers
```

For simple blueprints, a single file is acceptable:

```
app/routes/auth.py   # Blueprint + routes in one file
```

## URL Prefix Convention

Always version the API and name the prefix after the resource (plural noun):

```
/api/v1/{blueprint_name}
```

Examples:
- `/api/v1/users`
- `/api/v1/tasks`
- `/api/v1/auth`

Nested resources use the parent prefix:

```
/api/v1/users/<user_id>/tasks
```

## Blueprint Registration

Define the blueprint in the package `__init__.py` and register it in `create_app()`:

```python
# app/routes/users/__init__.py
from flask import Blueprint

users_bp = Blueprint("users", __name__)

from app.routes.users.routes import *  # noqa: F401, F403
```

```python
# app/__init__.py (inside create_app)
from app.routes.users import users_bp
app.register_blueprint(users_bp, url_prefix="/api/v1/users")
```

## Route Definition Inside a Blueprint

```python
# app/routes/users/routes.py
from flask import jsonify, request
from app.routes.users import users_bp
from app.routes.users.services import get_all_users, create_user


@users_bp.route("/", methods=["GET"])
def list_users():
    users = get_all_users()
    return jsonify({"data": users}), 200


@users_bp.route("/", methods=["POST"])
def add_user():
    payload = request.get_json()
    user = create_user(payload)
    return jsonify({"data": user}), 201
```

## When to Split a Blueprint

Split a blueprint into its own package (directory with multiple files) when any of the following apply:

- The blueprint has **more than 10 routes**.
- The blueprint handles **more than 2 distinct sub-domains** (e.g., a "users" blueprint that also manages teams and invitations).
- The route file exceeds **300 lines**.
- Multiple developers frequently work on the same blueprint file.

When splitting, move business logic into `services.py` and validation into `schemas.py` so that `routes.py` stays focused on HTTP concerns.

## Naming Conventions

- Blueprint variable: `{domain}_bp` (e.g., `users_bp`, `auth_bp`).
- Blueprint name string: matches the domain (`"users"`, `"auth"`).
- Route function names: use verbs describing the action (`list_users`, `create_user`, `get_user`, `update_user`, `delete_user`).
