"""Configuration for the SheetStorm MCP Bridge.

Loads settings from environment variables / .env file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the bridge directory (where the user runs it)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)
# Also load from CWD in case the user runs from a different directory
load_dotenv(Path.cwd() / ".env")


@dataclass(frozen=True)
class Config:
    """Immutable configuration for the bridge."""

    # SheetStorm backend
    api_url: str = field(
        default_factory=lambda: os.getenv(
            "SHEETSTORM_API_URL", "http://localhost:5000/api/v1"
        )
    )
    # Credentials. Preferred: a scoped API key (SHEETSTORM_API_KEY,
    # `ssk_...`), exchanged for short-lived tokens; works with MFA-enabled
    # accounts. The pre-issued JWT and username/password (no MFA support)
    # are legacy. repr=False keeps secrets out of logs and tracebacks.
    api_key: str | None = field(
        default_factory=lambda: os.getenv("SHEETSTORM_API_KEY") or None, repr=False
    )
    api_token: str | None = field(
        default_factory=lambda: os.getenv("SHEETSTORM_API_TOKEN"), repr=False
    )
    username: str | None = field(
        default_factory=lambda: os.getenv("SHEETSTORM_USERNAME")
    )
    password: str | None = field(
        default_factory=lambda: os.getenv("SHEETSTORM_PASSWORD"), repr=False
    )

    # Logging
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )

    # HTTP client
    http_timeout: int = field(
        default_factory=lambda: int(os.getenv("HTTP_TIMEOUT", "30"))
    )
    http_max_retries: int = field(
        default_factory=lambda: int(os.getenv("HTTP_MAX_RETRIES", "2"))
    )

    @property
    def auth_mode(self) -> str | None:
        """Credential in use: api_key > api_token > password."""
        if self.api_key:
            return "api_key"
        if self.api_token:
            return "api_token"
        if self.username and self.password:
            return "password"
        return None

    @property
    def has_credentials(self) -> bool:
        return self.auth_mode is not None


def get_config() -> Config:
    return Config()
