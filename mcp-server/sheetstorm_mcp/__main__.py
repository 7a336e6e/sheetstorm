"""Entry point for `python -m sheetstorm_mcp`."""

from __future__ import annotations

import logging
import sys


def main() -> None:
    """Start the SheetStorm MCP server."""
    from sheetstorm_mcp.config import get_config
    from sheetstorm_mcp.server import mcp

    cfg = get_config()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    logger = logging.getLogger("sheetstorm_mcp")
    logger.info("Starting SheetStorm MCP server v%s (transport=%s)", "0.1.0", cfg.transport)

    if cfg.transport == "sse":
        _run_sse_with_auth(cfg, logger)
    else:
        mcp.run(transport="stdio")


def _run_sse_with_auth(cfg, logger) -> None:
    """Run SSE transport wrapped with bearer-token authentication middleware."""
    import uvicorn
    from sheetstorm_mcp.auth_middleware import BearerTokenMiddleware
    from sheetstorm_mcp.server import mcp

    # Get the raw Starlette SSE app from FastMCP
    app = mcp.sse_app()

    # Wrap with bearer-token auth gate
    secured_app = BearerTokenMiddleware(app, token=cfg.auth_token)

    if cfg.auth_token:
        logger.info("MCP transport authentication ENABLED (MCP_AUTH_TOKEN is set)")
    else:
        logger.warning(
            "MCP transport authentication DISABLED — set MCP_AUTH_TOKEN "
            "to require bearer token for SSE connections"
        )

    uvicorn.run(
        secured_app,
        host="0.0.0.0",
        port=cfg.sse_port,
        log_level=cfg.log_level.lower(),
    )


if __name__ == "__main__":
    main()
