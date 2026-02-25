"""Configuration management for the SheetStorm MCP server.

Loads settings from environment variables with sensible defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from mcp-server directory
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


@dataclass(frozen=True)
class Config:
    """Immutable configuration for the MCP server."""

    # SheetStorm backend
    api_url: str = field(default_factory=lambda: os.getenv("SHEETSTORM_API_URL", "http://localhost:5000/api/v1"))
    api_token: str | None = field(default_factory=lambda: os.getenv("SHEETSTORM_API_TOKEN"))
    username: str | None = field(default_factory=lambda: os.getenv("SHEETSTORM_USERNAME"))
    password: str | None = field(default_factory=lambda: os.getenv("SHEETSTORM_PASSWORD"))

    # MCP transport
    transport: str = field(default_factory=lambda: os.getenv("MCP_TRANSPORT", "stdio"))
    sse_port: int = field(default_factory=lambda: int(os.getenv("MCP_SSE_PORT", "8080")))

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # HTTP client
    http_timeout: int = field(default_factory=lambda: int(os.getenv("HTTP_TIMEOUT", "30")))
    http_max_retries: int = field(default_factory=lambda: int(os.getenv("HTTP_MAX_RETRIES", "2")))

    @property
    def has_credentials(self) -> bool:
        """Whether we have credentials for auto-login."""
        return bool(self.api_token) or (bool(self.username) and bool(self.password))


def get_config() -> Config:
    """Return the global configuration instance."""
    return Config()
