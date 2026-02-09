---
name: Testing Flask
description: Test Flask applications with pytest using fixtures, test client, factory data, and organized test structure.
---

# Testing Flask

## Goal

Set up a comprehensive testing strategy for a Flask application using pytest, with reusable fixtures, the Flask test client, factory-based test data, and a clear directory structure separating unit and integration tests.

## When to Use

- Setting up testing infrastructure for a new Flask project.
- Adding test coverage to an existing application.
- Writing tests for new API endpoints.
- Reviewing or improving an existing test suite.
- Establishing testing conventions for a team.

## Instructions

### Test Directory Structure

Organize tests to separate concerns:

```
tests/
    conftest.py           # Shared fixtures (app, client, db, auth)
    unit/
        test_user_service.py
        test_validators.py
    integration/
        test_users_api.py
        test_auth_api.py
    factories.py          # Factory Boy model factories
```

### Core Fixtures

Define fixtures in `tests/conftest.py`. The `app` fixture creates a fresh application with test configuration. The `client` fixture provides the test client. The `db_session` fixture wraps each test in a transaction that rolls back automatically.

```python
# tests/conftest.py

import pytest
from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    """Create the Flask application with test config."""
    app = create_app("testing")

    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture(scope="function")
def db_session(app):
    """Provide a transactional database session that rolls back after each test."""
    with app.app_context():
        connection = _db.engine.connect()
        transaction = connection.begin()

        options = dict(bind=connection, binds={})
        session = _db.create_scoped_session(options=options)
        _db.session = session

        yield session

        transaction.rollback()
        connection.close()
        session.remove()


@pytest.fixture(scope="function")
def client(app, db_session):
    """Flask test client with a clean database session."""
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def auth_headers(client):
    """Authenticate a test user and return headers with a valid token."""
    response = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "testpassword123",
    })
    token = response.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
```

### Test Data with Factory Boy

Use Factory Boy to create model instances with sensible defaults:

```python
# tests/factories.py

import factory
from app.extensions import db
from app.models.user import User


class UserFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    name = factory.Faker("name")
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    role = "member"
```

Use factories in tests:

```python
from tests.factories import UserFactory


def test_list_users_returns_all(client, db_session):
    UserFactory.create_batch(3)
    db_session.flush()

    response = client.get("/api/v1/users/")
    assert response.status_code == 200

    data = response.get_json()
    assert len(data["data"]) == 3
```

### Testing Endpoints with the Test Client

The test client sends HTTP requests to the app without starting a server.

```python
# tests/integration/test_users_api.py

import json


class TestCreateUser:
    """Tests for POST /api/v1/users/."""

    def test_create_user_success(self, client, db_session):
        payload = {
            "email": "new@example.com",
            "name": "New User",
            "role": "member",
        }

        response = client.post(
            "/api/v1/users/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["data"]["email"] == "new@example.com"
        assert data["data"]["name"] == "New User"

    def test_create_user_missing_email(self, client, db_session):
        payload = {"name": "No Email User"}

        response = client.post(
            "/api/v1/users/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 422
        error = response.get_json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert "email" in error["details"]

    def test_create_user_duplicate_email(self, client, db_session):
        UserFactory(email="dupe@example.com")
        db_session.flush()

        payload = {
            "email": "dupe@example.com",
            "name": "Duplicate",
        }

        response = client.post(
            "/api/v1/users/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 409
```

### Unit Testing Services

Test business logic independently of HTTP:

```python
# tests/unit/test_user_service.py

from app.services.user_service import create_user
from app.exceptions import ConflictError
import pytest


def test_create_user_with_valid_data(db_session):
    user = create_user({"email": "valid@example.com", "name": "Valid"})
    assert user["email"] == "valid@example.com"


def test_create_user_duplicate_raises_conflict(db_session):
    create_user({"email": "first@example.com", "name": "First"})
    with pytest.raises(ConflictError):
        create_user({"email": "first@example.com", "name": "Duplicate"})
```

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing

# Run only unit tests
pytest tests/unit/

# Run a specific test
pytest tests/integration/test_users_api.py::TestCreateUser::test_create_user_success -v
```

## Constraints

### ✅ Do
- Test both the happy path and error cases for every endpoint.
- Use fixtures for app creation, database sessions, and authentication.
- Isolate each test with a transaction rollback so tests do not affect each other.
- Use Factory Boy or similar for creating test data with sensible defaults.
- Separate unit tests (service logic) from integration tests (HTTP endpoints).
- Run tests with coverage reporting to track gaps.


### ❌ Don&#x27;t
- Do not test implementation details such as private methods or internal data structures.
- Do not share mutable state between tests; each test gets a fresh database session.
- Do not skip testing error cases (4xx responses, validation failures, edge cases).
- Do not make tests depend on execution order.
- Do not hardcode IDs or timestamps that may change between runs.
- Do not mock the database in integration tests; use a real test database with rollback.


## Output Format

Generate `tests/conftest.py`, `tests/factories.py`, and at least one test file. Include the pytest command to run the suite.

## Dependencies

- [Scaffolding Flask](../scaffolding-flask/SKILL.md) -- app factory used to create the test application.
- [Building API Routes](../building-api-routes/SKILL.md) -- routes under test.
