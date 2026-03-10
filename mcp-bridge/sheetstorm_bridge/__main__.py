"""Entry point for `python -m sheetstorm_bridge`."""

from __future__ import annotations

import logging
import sys


def main() -> None:
    """Start the SheetStorm MCP Bridge (stdio transport)."""
    from sheetstorm_bridge.config import get_config
    from sheetstorm_bridge.server import mcp

    cfg = get_config()

    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,  # MCP uses stdout for protocol — logs go to stderr
    )

    logger = logging.getLogger("sheetstorm_bridge")

    if not cfg.has_credentials:
        logger.error(
            "No credentials configured! Set SHEETSTORM_USERNAME/SHEETSTORM_PASSWORD "
            "or SHEETSTORM_API_TOKEN in your .env file.\n"
            "See .env.example for details."
        )
        sys.exit(1)

    logger.info(
        "Starting SheetStorm MCP Bridge v0.1.0 (stdio) → %s",
        cfg.api_url,
    )

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
