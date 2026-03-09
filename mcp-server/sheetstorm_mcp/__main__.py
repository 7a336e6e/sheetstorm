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
        _run_sse_with_oauth(cfg, logger)
    else:
        mcp.run(transport="stdio")


def _run_sse_with_oauth(cfg, logger) -> None:
    """Run SSE transport with OAuth authentication and login routes."""
    import uvicorn
    from starlette.routing import Mount

    from sheetstorm_mcp.login_routes import create_login_routes
    from sheetstorm_mcp.server import mcp, _oauth_provider

    # Get the Starlette SSE app from FastMCP (includes built-in OAuth routes)
    app = mcp.sse_app()

    # Mount the custom login routes alongside the SDK's OAuth routes
    login_routes = create_login_routes(_oauth_provider)
    app.routes.extend(login_routes)

    logger.info(
        "MCP OAuth authentication ENABLED — login page at %s/sheetstorm-login",
        cfg.mcp_issuer_url,
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=cfg.sse_port,
        log_level=cfg.log_level.lower(),
    )


if __name__ == "__main__":
    main()
