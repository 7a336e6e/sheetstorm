---
name: Config Patterns
description: Reference for Flask configuration class hierarchy and environment-based config selection.
---

# Config Patterns

## Overview

Flask configuration is managed through a class hierarchy. A base class holds shared settings, and environment-specific subclasses override or extend as needed. The active configuration is selected at runtime via the `APP_ENV` environment variable.

## Base Config

The base class defines settings common to every environment:

```python
import os
from datetime import timedelta


class BaseConfig:
    """Shared configuration for all environments."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB upload limit
```

## DevelopmentConfig

Local development settings with verbose output:

```python
class DevelopmentConfig(BaseConfig):
    """Configuration for local development."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///dev.db"
    )
    SQLALCHEMY_ECHO = True  # Log all SQL statements
    LOG_LEVEL = "DEBUG"
```

Key characteristics:
- `DEBUG = True` enables the debugger and auto-reload.
- Uses a local SQLite or Postgres database.
- SQL echo is on for query visibility.
- Verbose logging at the DEBUG level.

## TestingConfig

Settings tuned for fast, isolated test runs:

```python
class TestingConfig(BaseConfig):
    """Configuration for the test suite."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    LOG_LEVEL = "WARNING"
    BCRYPT_LOG_ROUNDS = 4  # Faster hashing in tests
```

Key characteristics:
- `TESTING = True` changes error handling behavior for assertions.
- In-memory SQLite (or a dedicated test Postgres database) for speed.
- CSRF protection disabled to simplify test requests.
- Bcrypt rounds reduced to speed up password hashing in tests.

## ProductionConfig

Production never falls back to defaults for sensitive values:

```python
class ProductionConfig(BaseConfig):
    """Configuration for production. All secrets from env vars."""
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ["SECRET_KEY"]
    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
```

Key characteristics:
- `SECRET_KEY` and `DATABASE_URL` **must** be set or the app crashes on startup (intentional fail-fast).
- Connection pooling is configured for concurrent load.
- No debug mode, no testing mode.
- Log level defaults to INFO but is configurable.

## Config Selection

Map environment names to config classes and select using `APP_ENV`:

```python
config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config():
    """Return the config class matching APP_ENV."""
    env = os.environ.get("APP_ENV", "development")
    return config_by_name[env]
```

Usage in the app factory:

```python
def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("APP_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])
    return app
```

## Complete config.py Example

```python
import os
from datetime import timedelta


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
    SQLALCHEMY_ECHO = True
    LOG_LEVEL = "DEBUG"


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    LOG_LEVEL = "WARNING"
    BCRYPT_LOG_ROUNDS = 4


class ProductionConfig(BaseConfig):
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ["SECRET_KEY"]
    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
```

## Guidelines

- Never commit real secrets to `config.py`. Use environment variables or a `.env` file (excluded from version control).
- Production config should fail loudly if a required variable is missing. Use `os.environ["KEY"]` (not `.get()`).
- Keep the base class minimal: only settings truly shared across all environments belong there.
