"""SheetStorm MCP Bridge — local stdio MCP server.

Creates a FastMCP server with no OAuth, no Redis, no SSE.
Authenticates directly to the SheetStorm backend via username/password.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from sheetstorm_bridge import __version__
from sheetstorm_bridge.client import SheetStormClient
from sheetstorm_bridge.config import Config, get_config

logger = logging.getLogger("sheetstorm_bridge.server")

# ---------------------------------------------------------------------------
# Shared client instance
# ---------------------------------------------------------------------------

_client: SheetStormClient | None = None


def get_client() -> SheetStormClient:
    """Return the shared API client. Called from every tool handler."""
    if _client is None:
        raise RuntimeError("SheetStorm client not initialised — server not started yet.")
    return _client


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    global _client
    cfg = get_config()
    _client = SheetStormClient(cfg)

    # Pre-authenticate so tool calls don't fail on first use
    try:
        await _client.ensure_authenticated()
        logger.info("Pre-authenticated to SheetStorm backend at %s", cfg.api_url)
    except Exception as exc:
        logger.warning("Pre-authentication failed (will retry on first tool call): %s", exc)

    logger.info(
        "SheetStorm MCP Bridge v%s started — backend at %s",
        __version__,
        cfg.api_url,
    )

    try:
        yield {"client": _client, "config": cfg}
    finally:
        await _client.close()
        _client = None
        logger.info("SheetStorm MCP Bridge shut down")


# ---------------------------------------------------------------------------
# MCP Server instance — stdio only, no OAuth
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "sheetstorm-bridge",
    instructions=(
        f"SheetStorm MCP Bridge v{__version__} — "
        "Local stdio bridge to the SheetStorm Incident Response Platform. "
        "Provides tools for managing incidents, timeline events, IOCs, hosts, "
        "accounts, tasks, case notes, reports, attack graphs, threat intelligence, "
        "and more."
    ),
    lifespan=server_lifespan,
)


# ---------------------------------------------------------------------------
# Import tool modules — each registers tools on `mcp` at import time
# ---------------------------------------------------------------------------

import sheetstorm_bridge.tools.auth  # noqa: E402, F401
import sheetstorm_bridge.tools.incidents  # noqa: E402, F401
import sheetstorm_bridge.tools.timeline  # noqa: E402, F401
import sheetstorm_bridge.tools.tasks  # noqa: E402, F401
import sheetstorm_bridge.tools.assets  # noqa: E402, F401
import sheetstorm_bridge.tools.iocs  # noqa: E402, F401
import sheetstorm_bridge.tools.artifacts  # noqa: E402, F401
import sheetstorm_bridge.tools.attack_graph  # noqa: E402, F401
import sheetstorm_bridge.tools.case_notes  # noqa: E402, F401
import sheetstorm_bridge.tools.reports  # noqa: E402, F401
import sheetstorm_bridge.tools.admin  # noqa: E402, F401
import sheetstorm_bridge.tools.threat_intel  # noqa: E402, F401
import sheetstorm_bridge.tools.knowledge_base  # noqa: E402, F401
import sheetstorm_bridge.tools.advanced_analysis  # noqa: E402, F401
import sheetstorm_bridge.tools.defang  # noqa: E402, F401
import sheetstorm_bridge.tools.resources  # noqa: E402, F401
import sheetstorm_bridge.tools.prompts  # noqa: E402, F401
