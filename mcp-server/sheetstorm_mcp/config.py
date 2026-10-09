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
    # Credentials (stdio transport only). Preferred: a scoped API key
    # (SHEETSTORM_API_KEY, `ssk_...`), exchanged for short-lived tokens. The
    # pre-issued JWT and username/password (no MFA support) are legacy.
    # repr=False keeps secrets out of logs and tracebacks.
    api_key: str | None = field(default_factory=lambda: os.getenv("SHEETSTORM_API_KEY") or None, repr=False)
    api_token: str | None = field(default_factory=lambda: os.getenv("SHEETSTORM_API_TOKEN"), repr=False)
    username: str | None = field(default_factory=lambda: os.getenv("SHEETSTORM_USERNAME"))
    password: str | None = field(default_factory=lambda: os.getenv("SHEETSTORM_PASSWORD"), repr=False)

    # MCP transport
    transport: str = field(default_factory=lambda: os.getenv("MCP_TRANSPORT", "stdio"))
    sse_port: int = field(default_factory=lambda: int(os.getenv("SSE_PORT", os.getenv("MCP_SSE_PORT", "8811"))))

    # OAuth — issuer URL that the MCP server advertises in its metadata
    mcp_issuer_url: str = field(
        default_factory=lambda: os.getenv("MCP_ISSUER_URL", "http://localhost:8811")
    )

    # Redis — used for persistent OAuth client registrations
    redis_url: str | None = field(
        default_factory=lambda: os.getenv("REDIS_URL")
    )

    # Local sandbox directory for artifact upload/download paths on the remote
    # server (ignored for the stdio bridge, which runs on the user's machine).
    artifact_dir: str = field(default_factory=lambda: os.getenv("ARTIFACT_DIR", "/tmp/sheetstorm-artifacts"))

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # HTTP client
    http_timeout: int = field(default_factory=lambda: int(os.getenv("HTTP_TIMEOUT", "30")))
    http_max_retries: int = field(default_factory=lambda: int(os.getenv("HTTP_MAX_RETRIES", "2")))

    @property
    def auth_mode(self) -> str | None:
        """Static credential in use on stdio: api_key > api_token > password."""
        if self.api_key:
            return "api_key"
        if self.api_token:
            return "api_token"
        if self.username and self.password:
            return "password"
        return None

    @property
    def has_credentials(self) -> bool:
        """Whether static (stdio) credentials are configured."""
        return self.auth_mode is not None


def get_config() -> Config:
    """Return the global configuration instance."""
    return Config()
