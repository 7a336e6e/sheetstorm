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
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
