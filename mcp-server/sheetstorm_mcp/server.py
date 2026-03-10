"""SheetStorm MCP Server — main server definition and tool registration.

Uses the FastMCP high-level API from the `mcp` SDK with OAuth 2.0
authentication delegated to the SheetStorm backend.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP

from sheetstorm_mcp import __version__
from sheetstorm_mcp.client import SheetStormClient, _request_jwt
from sheetstorm_mcp.config import Config, get_config
from sheetstorm_mcp.oauth_provider import SheetStormOAuthProvider

logger = logging.getLogger("sheetstorm_mcp.server")

# ---------------------------------------------------------------------------
# Lifespan — initialise / tear-down the API client and OAuth provider
# ---------------------------------------------------------------------------

_client: SheetStormClient | None = None
_provider: SheetStormOAuthProvider | None = None


def get_client() -> SheetStormClient:
    """Return the shared API client, injecting the per-request JWT from OAuth context.

    This is called from every tool handler.  When OAuth is active the SDK
    populates ``auth_context_var`` before invoking the tool, so we can pull
    the MCP opaque token, look up the real SheetStorm JWT, and set the
    ``_request_jwt`` ContextVar that the HTTP client reads.
    """
    if _client is None:
        raise RuntimeError("SheetStorm client not initialised — server not started yet.")

    # Inject the per-user JWT into the request-scoped ContextVar
    access_token = get_access_token()
    if access_token and _provider:
        jwt = _provider.get_sheetstorm_jwt(access_token.token)
        if jwt:
            _request_jwt.set(jwt)

    return _client


def get_provider() -> SheetStormOAuthProvider:
    """Return the OAuth provider (available after server start)."""
    if _provider is None:
        raise RuntimeError("OAuth provider not initialised.")
    return _provider


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """Manage SheetStormClient and OAuth provider lifecycle."""
    global _client, _provider
    cfg = get_config()
    _client = SheetStormClient(cfg)
    # Provider is created in module scope for FastMCP constructor,
    # but we store a reference here for cleanup.
    _provider = _oauth_provider

    logger.info(
        "SheetStorm MCP server v%s started — OAuth flow enabled, backend at %s",
        __version__, cfg.api_url,
    )

    try:
        yield {"client": _client, "config": cfg}
    finally:
        await _client.close()
        _client = None
        await _oauth_provider.close()
        _provider = None
        logger.info("SheetStorm MCP server shut down")


# ---------------------------------------------------------------------------
# MCP Server instance with OAuth
# ---------------------------------------------------------------------------

_cfg = get_config()

_oauth_provider = SheetStormOAuthProvider(
    api_url=_cfg.api_url,
    mcp_issuer_url=_cfg.mcp_issuer_url,
    redis_url=_cfg.redis_url,
)

mcp = FastMCP(
    "sheetstorm-mcp",
    instructions=f"SheetStorm MCP Server v{__version__} — Incident Response Platform tools",
    lifespan=server_lifespan,
    host="0.0.0.0",
    port=_cfg.sse_port,
    auth_server_provider=_oauth_provider,
    auth=AuthSettings(
        issuer_url=_cfg.mcp_issuer_url,
        resource_server_url=_cfg.mcp_issuer_url.rstrip("/") + "/mcp",
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["sheetstorm"],
            default_scopes=["sheetstorm"],
        ),
        revocation_options=RevocationOptions(enabled=True),
    ),
)


# ---------------------------------------------------------------------------
# Import tool modules — each module registers tools on `mcp` at import time
# ---------------------------------------------------------------------------

def _register_all_tools() -> None:
    """Import every tool module so their @mcp.tool decorators execute."""
    from sheetstorm_mcp.tools import auth  # noqa: F401
    from sheetstorm_mcp.tools import incidents  # noqa: F401
    from sheetstorm_mcp.tools import timeline  # noqa: F401
    from sheetstorm_mcp.tools import tasks  # noqa: F401
    from sheetstorm_mcp.tools import assets  # noqa: F401
    from sheetstorm_mcp.tools import iocs  # noqa: F401
    from sheetstorm_mcp.tools import artifacts  # noqa: F401
    from sheetstorm_mcp.tools import attack_graph  # noqa: F401
    from sheetstorm_mcp.tools import reports  # noqa: F401
    from sheetstorm_mcp.tools import admin  # noqa: F401
    from sheetstorm_mcp.tools import resources  # noqa: F401
    from sheetstorm_mcp.tools import case_notes  # noqa: F401
    from sheetstorm_mcp.tools import threat_intel  # noqa: F401
    from sheetstorm_mcp.tools import knowledge_base  # noqa: F401
    from sheetstorm_mcp.tools import defang  # noqa: F401
    from sheetstorm_mcp.tools import prompts  # noqa: F401
    from sheetstorm_mcp.tools import advanced_analysis  # noqa: F401


_register_all_tools()
