---
name: Building API Routes
description: Build RESTful Flask routes with input validation, consistent response formatting, and pagination.
---

# Building API Routes

## Goal

Create RESTful API endpoints in Flask that follow consistent URL conventions, validate all input, return uniform JSON responses, and support pagination for list endpoints.

## When to Use

- Adding a new resource endpoint (CRUD) to an existing Flask app.
- Designing the API contract for a new feature.
- Refactoring existing routes to follow RESTful conventions.
- Adding pagination, filtering, or sorting to list endpoints.

## Instructions

### RESTful Conventions

Map HTTP methods to operations on resources:

| Method | URL Pattern                   | Action       | Status Code |
|--------|-------------------------------|--------------|-------------|
| GET    | /api/v1/resources             | List all     | 200         |
| GET    | /api/v1/resources/\<id\>      | Get one      | 200         |
| POST   | /api/v1/resources             | Create       | 201         |
| PUT    | /api/v1/resources/\<id\>      | Full update  | 200         |
| PATCH  | /api/v1/resources/\<id\>      | Partial update | 200       |
| DELETE | /api/v1/resources/\<id\>      | Delete       | 204         |

### URL Patterns

Use plural nouns for resource names. Never put verbs in URLs.

```
/api/v1/users
/api/v1/users/<int:user_id>
/api/v1/users/<int:user_id>/tasks
```

### Request Validation

Validate incoming data before it reaches business logic. Use marshmallow schemas or pydantic models.

```python
from marshmallow import Schema, fields, validate, ValidationError


class CreateUserSchema(Schema):
    email = fields.Email(required=True)
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    role = fields.String(validate=validate.OneOf(["admin", "member", "viewer"]))
```

Apply validation in the route handler:

```python
@users_bp.route("/", methods=["POST"])
def create_user():
    schema = CreateUserSchema()
    try:
        data = schema.load(request.get_json())
    except ValidationError as err:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Invalid input", "details": err.messages}}), 422

    user = user_service.create(data)
    return jsonify({"data": user}), 201
```

### Response Format

Every endpoint returns a consistent JSON envelope:

```json
{
  "data": {},
  "error": null,
  "meta": {}
}
```

- **Success responses** populate `data` and optionally `meta` (pagination info, counts).
- **Error responses** populate `error` with `code`, `message`, and optional `details`.
- Never mix shapes: a response is either a success or an error, not both.

### Pagination

For list endpoints, support offset/limit pagination:

```python
@users_bp.route("/", methods=["GET"])
def list_users():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(per_page, 100)  # Cap maximum

    pagination = User.query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "data": [user.to_dict() for user in pagination.items],
        "meta": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        }
    }), 200
```

For cursor-based pagination (better for large or frequently changing datasets):

```python
@users_bp.route("/", methods=["GET"])
def list_users():
    cursor = request.args.get("cursor", None)
    limit = request.args.get("limit", 20, type=int)
    limit = min(limit, 100)

    query = User.query.order_by(User.id)
    if cursor:
        query = query.filter(User.id > cursor)

    users = query.limit(limit + 1).all()
    has_next = len(users) > limit
    users = users[:limit]

    next_cursor = users[-1].id if has_next and users else None

    return jsonify({
        "data": [u.to_dict() for u in users],
        "meta": {
            "next_cursor": next_cursor,
            "has_next": has_next,
        }
    }), 200
```

### Complete CRUD Example

```python
from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.routes.users.schemas import CreateUserSchema, UpdateUserSchema
from app.routes.users.services import user_service

users_bp = Blueprint("users", __name__)


@users_bp.route("/", methods=["GET"])
def list_users():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    result = user_service.list_paginated(page, per_page)
    return jsonify({"data": result["items"], "meta": result["meta"]}), 200


@users_bp.route("/<int:user_id>", methods=["GET"])
def get_user(user_id):
    user = user_service.get_or_404(user_id)
    return jsonify({"data": user}), 200


@users_bp.route("/", methods=["POST"])
def create_user():
    schema = CreateUserSchema()
    try:
        data = schema.load(request.get_json())
    except ValidationError as err:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Invalid input", "details": err.messages}}), 422
    user = user_service.create(data)
    return jsonify({"data": user}), 201


@users_bp.route("/<int:user_id>", methods=["PUT"])
def replace_user(user_id):
    schema = CreateUserSchema()
    try:
        data = schema.load(request.get_json())
    except ValidationError as err:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Invalid input", "details": err.messages}}), 422
    user = user_service.update(user_id, data)
    return jsonify({"data": user}), 200


@users_bp.route("/<int:user_id>", methods=["PATCH"])
def update_user(user_id):
    schema = UpdateUserSchema()
    try:
        data = schema.load(request.get_json())
    except ValidationError as err:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Invalid input", "details": err.messages}}), 422
    user = user_service.partial_update(user_id, data)
    return jsonify({"data": user}), 200


@users_bp.route("/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    user_service.delete(user_id)
    return "", 204
```

## Constraints

### ✅ Do
- Validate all incoming request data with a schema before processing.
- Use a consistent JSON response envelope (`data`, `error`, `meta`).
- Return proper HTTP status codes: 200, 201, 204, 400, 404, 422, 500.
- Use plural nouns for resource URLs.
- Cap pagination limits to prevent abuse (e.g., max 100 per page).
- Include pagination metadata in list responses.


### ❌ Don&#x27;t
- Do not use verbs in URLs (no `/api/v1/getUsers` or `/api/v1/createUser`).
- Do not return different response shapes from different endpoints.
- Do not expose internal database IDs without a clear reason.
- Do not allow unbounded queries -- always paginate list endpoints.
- Do not put business logic directly in route handlers; delegate to service functions.


## Output Format

When generating routes, produce the route file, the schema file, and the service file as separate code blocks. Include the blueprint registration line for `create_app()`.

## Dependencies

- [Scaffolding Flask](../scaffolding-flask/SKILL.md) -- app factory and blueprint registration.
- [Task Tracking](../../shared/task-tracking/SKILL.md) -- track progress when building multiple endpoints.
