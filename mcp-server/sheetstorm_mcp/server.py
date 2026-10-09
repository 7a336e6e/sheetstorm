"""SheetStorm MCP Server — main server definition and tool registration.

Uses the FastMCP high-level API from the `mcp` SDK with OAuth 2.0
authentication delegated to the SheetStorm backend.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP

from sheetstorm_mcp import __version__
from sheetstorm_mcp.client import Grant, SheetStormClient, _request_grant
from sheetstorm_mcp.config import get_config
from sheetstorm_mcp.oauth_provider import SheetStormOAuthProvider

logger = logging.getLogger("sheetstorm_mcp.server")

# ---------------------------------------------------------------------------
# Lifespan — initialise / tear-down the API client and OAuth provider
# ---------------------------------------------------------------------------

_client: SheetStormClient | None = None
_provider: SheetStormOAuthProvider | None = None


def _current_mcp_token() -> str | None:
    """Bearer token of the MCP HTTP request currently being served.

    Read from the request's own ``scope["user"]`` (set by the SDK's bearer
    auth middleware on *every* HTTP request) rather than the auth ContextVar:
    on SSE and Streamable HTTP sessions tools run in the session task, whose
    ContextVar still holds the token used when the session was opened — which
    is revoked/expired after the client's hourly token refresh.
    """
    try:
        request = mcp.get_context().request_context.request
    except (LookupError, ValueError, AttributeError):
        request = None
    if request is not None:
        user = getattr(request, "scope", {}).get("user")
        access_token = getattr(user, "access_token", None)
        if access_token is not None:
            return access_token.token
    # Fallback for transports without a per-message request object.
    from mcp.server.auth.middleware.auth_context import get_access_token

    access_token = get_access_token()
    return access_token.token if access_token else None


def current_grant() -> Grant | None:
    """The OAuth grant (user session) of the current MCP request, if any."""
    if _provider is None:
        return None
    token = _current_mcp_token()
    return _provider.get_grant(token) if token else None


def get_client() -> SheetStormClient:
    """Return the shared API client bound to the current request's user.

    Called from every tool handler. Resolves the OAuth grant of the current
    MCP request and stores it in the ``_request_grant`` ContextVar that the
    HTTP client reads. The ContextVar is always reset so a grant can never
    leak from one request into the next.
    """
    if _client is None:
        raise RuntimeError("SheetStorm client not initialised — server not started yet.")
    _request_grant.set(current_grant())
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
    # but we store a reference here for cleanup.  Re-create its HTTP
    # client in case a previous lifespan cycle closed it.
    _oauth_provider._get_http()
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
    from sheetstorm_mcp.tools import (
        admin,  # noqa: F401
        advanced_analysis,  # noqa: F401
        artifacts,  # noqa: F401
        assets,  # noqa: F401
        assignments,  # noqa: F401
        attack_graph,  # noqa: F401
        auth,  # noqa: F401
        case_notes,  # noqa: F401
        case_templates,  # noqa: F401
        decisions,  # noqa: F401
        defang,  # noqa: F401
        evidence,  # noqa: F401
        incidents,  # noqa: F401
        iocs,  # noqa: F401
        knowledge_base,  # noqa: F401
        metrics,  # noqa: F401
        playbooks,  # noqa: F401
        prompts,  # noqa: F401
        questions,  # noqa: F401
        reports,  # noqa: F401
        resources,  # noqa: F401
        tasks,  # noqa: F401
        threat_intel,  # noqa: F401
        timeline,  # noqa: F401
    )


_register_all_tools()
