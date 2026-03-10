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
    """Run HTTP transport with OAuth authentication and login routes.

    Mounts both SSE (/sse, /messages/) and Streamable HTTP (/mcp)
    endpoints so that clients using either transport can connect.

    The Streamable HTTP app is used as the primary Starlette application
    because its lifespan initialises the session manager task group that
    the /mcp endpoint requires.  The SSE endpoints (/sse, /messages) are
    then grafted in — they manage their own per-connection lifecycle and
    do not need the session manager.
    """
    import uvicorn

    from sheetstorm_mcp.login_routes import create_login_routes
    from sheetstorm_mcp.server import mcp, _oauth_provider

    # Use the Streamable HTTP app as the primary — its lifespan runs
    # session_manager.run() which creates the required task group.
    app = mcp.streamable_http_app()

    # Grab /sse and /messages routes from the SSE app and add them
    # to the primary app so legacy SSE clients still work.
    sse_app = mcp.sse_app()
    for route in sse_app.routes:
        path = getattr(route, "path", "")
        if path in ("/sse", "/messages"):
            app.routes.insert(-1, route)
            logger.info("Mounted SSE endpoint at %s", path)

    # Mount the custom login routes alongside the SDK's OAuth routes
    login_routes = create_login_routes(_oauth_provider)
    app.routes.extend(login_routes)

    logger.info(
        "MCP dual-transport server ready — SSE at /sse, Streamable HTTP at /mcp",
    )
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
