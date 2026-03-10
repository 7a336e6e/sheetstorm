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
    api_token: str | None = field(
        default_factory=lambda: os.getenv("SHEETSTORM_API_TOKEN")
    )
    username: str | None = field(
        default_factory=lambda: os.getenv("SHEETSTORM_USERNAME")
    )
    password: str | None = field(
        default_factory=lambda: os.getenv("SHEETSTORM_PASSWORD")
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
    def has_credentials(self) -> bool:
        return bool(self.api_token) or (bool(self.username) and bool(self.password))


def get_config() -> Config:
    return Config()
