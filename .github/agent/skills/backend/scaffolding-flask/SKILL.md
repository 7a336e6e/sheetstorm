---
name: Scaffolding Flask
description: Set up a Flask application using the app factory pattern with blueprints, extensions, and environment-specific configuration.
---

# Scaffolding Flask

## Goal

Create a well-structured Flask application using the app factory pattern, with modular blueprints, proper extension initialization, and environment-specific configuration classes.

## When to Use

- Starting a new Flask project from scratch.
- Refactoring a single-file Flask app into a production-ready structure.
- Adding new blueprints or extensions to an existing factory-based app.
- Setting up configuration management for multiple environments.

## Instructions

### Project Structure

Organize the project with clear separation of concerns:

```
project/
  config.py
  run.py
  app/
    __init__.py        # App factory lives here
    extensions.py      # Extension instances
    models/
      __init__.py
      user.py
    routes/
      __init__.py
      auth.py
      users.py
    services/
      __init__.py
      user_service.py
  tests/
    conftest.py
  migrations/
```

### App Factory

Define `create_app()` in `app/__init__.py`. This function builds and configures the application instance, registers extensions, and attaches blueprints.

```python
from flask import Flask
from app.extensions import db, migrate, cors, login_manager
from config import config_by_name


def create_app(config_name=None):
    """Application factory for creating the Flask app."""
    if config_name is None:
        config_name = os.environ.get("APP_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app)
    login_manager.init_app(app)

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.users import users_bp

    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(users_bp, url_prefix="/api/v1/users")

    return app
```

### Extension Initialization

Declare extension instances in a dedicated `app/extensions.py` file. Do not bind them to an app at import time; instead, call `init_app()` inside the factory.

```python
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
login_manager = LoginManager()
```

### Configuration Classes

Create a `config.py` at the project root with a base class and per-environment subclasses. See the full pattern in the config-patterns reference.

```python
import os


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///dev.db"


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ProductionConfig(BaseConfig):
    DEBUG = False
    SECRET_KEY = os.environ["SECRET_KEY"]
    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
```

### Blueprint Registration

Each domain gets its own blueprint. Register all blueprints inside `create_app()` with a versioned URL prefix. See the blueprint-patterns reference for conventions on when to split and how to organize blueprint internals.

### Running the App

Create a thin `run.py` entry point:

```python
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
```

## Constraints

### ✅ Do
- Use the app factory pattern with a `create_app()` function.
- Separate configuration into per-environment classes (Development, Testing, Production).
- Register all extensions inside the factory via `init_app()`.
- Use one blueprint per domain area.
- Keep `run.py` as a thin entry point that only calls `create_app()`.
- Store extension instances in a dedicated `extensions.py` module.


### ❌ Don&#x27;t
- Do not use a global `app = Flask(__name__)` at module level.
- Do not hardcode configuration values; use environment variables for secrets.
- Do not mix route logic with model definitions.
- Do not import the app instance directly in blueprints; use `current_app` if needed.
- Do not initialize extensions with an app instance at declaration time.


## Output Format

When generating scaffolding, produce each file with its full relative path as a heading, followed by the complete file content. List all files created at the end as a summary.

## Dependencies

- [Environment Config](../../shared/environment-config/SKILL.md) -- conventions for managing environment variables and `.env` files.
- [Blueprint Patterns](references/blueprint-patterns.md) -- reference for blueprint organization and naming.
- [Config Patterns](references/config-patterns.md) -- reference for configuration class hierarchy.
