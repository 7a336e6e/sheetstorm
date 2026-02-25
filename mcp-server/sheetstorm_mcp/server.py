"""SheetStorm MCP Server — main server definition and tool registration.

Uses the FastMCP high-level API from the `mcp` SDK.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from sheetstorm_mcp import __version__
from sheetstorm_mcp.client import SheetStormClient
from sheetstorm_mcp.config import Config, get_config

logger = logging.getLogger("sheetstorm_mcp.server")

# ---------------------------------------------------------------------------
# Lifespan — initialise / tear-down the API client
# ---------------------------------------------------------------------------

_client: SheetStormClient | None = None


def get_client() -> SheetStormClient:
    """Return the shared API client (must be called after server start)."""
    if _client is None:
        raise RuntimeError("SheetStorm client not initialised — server not started yet.")
    return _client


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """Manage SheetStormClient lifecycle."""
    global _client
    cfg = get_config()
    _client = SheetStormClient(cfg)

    # Attempt auto-auth if credentials are configured
    if cfg.has_credentials:
        try:
            await _client.ensure_authenticated()
            logger.info("Auto-authenticated with SheetStorm backend at %s", cfg.api_url)
        except Exception as exc:
            logger.warning("Auto-auth failed (tools will require manual login): %s", exc)

    try:
        yield {"client": _client, "config": cfg}
    finally:
        await _client.close()
        _client = None
        logger.info("SheetStorm MCP server shut down")


# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "sheetstorm-mcp",
    instructions=f"SheetStorm MCP Server v{__version__} — Incident Response Platform tools",
    lifespan=server_lifespan,
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


_register_all_tools()
