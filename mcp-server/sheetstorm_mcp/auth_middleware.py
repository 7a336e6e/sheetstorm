"""Bearer-token authentication middleware for the MCP SSE transport.

When ``MCP_AUTH_TOKEN`` is set, every request to ``/sse`` and ``/messages/``
must carry a valid ``Authorization: Bearer <token>`` header. Requests without
a valid token receive a **401 Unauthorized** *before* the MCP protocol
handshake – so unauthenticated clients cannot even discover the tool list.

If ``MCP_AUTH_TOKEN`` is **not** set the middleware is a no-op pass-through
(useful for local development), but a warning is logged on startup.
"""

from __future__ import annotations

import hmac
import logging
from typing import Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("sheetstorm_mcp.auth")

# Paths that require authentication (prefix match)
_PROTECTED_PREFIXES = ("/sse", "/messages")


class BearerTokenMiddleware:
    """ASGI middleware that gates MCP endpoints behind a bearer token.

    Parameters
    ----------
    app:
        The next ASGI application in the stack.
    token:
        The expected bearer token.  If *None* or empty, the middleware
        lets all requests through (with a logged warning).
    """

    def __init__(self, app: ASGIApp, token: str | None = None) -> None:
        self.app = app
        self._token = token or ""
        if not self._token:
            logger.warning(
                "MCP_AUTH_TOKEN is not set — MCP server is running WITHOUT "
                "transport-level authentication.  Set MCP_AUTH_TOKEN to secure it."
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        # Only gate protected MCP endpoints
        if not any(path.startswith(prefix) for prefix in _PROTECTED_PREFIXES):
            await self.app(scope, receive, send)
            return

        # If no token configured, pass through (local dev mode)
        if not self._token:
            await self.app(scope, receive, send)
            return

        # Extract Authorization header
        headers = dict(scope.get("headers", []))
        auth_value = headers.get(b"authorization", b"").decode("latin-1")

        if not auth_value.startswith("Bearer "):
            response = JSONResponse(
                {"error": "Authentication required. Provide Authorization: Bearer <MCP_AUTH_TOKEN>."},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="sheetstorm-mcp"'},
            )
            await response(scope, receive, send)
            return

        provided_token = auth_value[7:]  # strip "Bearer "

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(provided_token, self._token):
            logger.warning("Rejected MCP connection with invalid bearer token from %s", scope.get("client", ("?",))[0])
            response = JSONResponse(
                {"error": "Invalid authentication token."},
                status_code=403,
            )
            await response(scope, receive, send)
            return

        # Token valid — proceed
        await self.app(scope, receive, send)
