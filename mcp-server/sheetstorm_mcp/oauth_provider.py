"""OAuth 2.0 Authorization Server Provider for the SheetStorm MCP Server.

Implements the full MCP OAuth flow so that VS Code / Claude Desktop users
are redirected to a login page, authenticate with their SheetStorm
credentials, and receive an access token scoped to *their* identity.

Flow
----
1.  MCP client connects → gets 401 with ``WWW-Authenticate``
2.  Client opens browser to ``/authorize``
3.  Provider redirects to ``/sheetstorm-login`` (login page served by this module)
4.  User submits credentials → MCP server calls SheetStorm ``/auth/login``
5.  On success an authorization code is generated and the user is redirected
    back to the client's ``redirect_uri``
6.  Client exchanges auth code for an access token via ``/token``
7.  Subsequent MCP requests carry ``Authorization: Bearer <jwt>``
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import AnyUrl

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

logger = logging.getLogger("sheetstorm_mcp.oauth")

# Redis key prefix for OAuth client registrations
_REDIS_CLIENT_PREFIX = "mcp:oauth:client:"

# ---------------------------------------------------------------------------
# In-memory stores (replaced by Redis/DB in production scale-out)
# ---------------------------------------------------------------------------


@dataclass
class StoredAuthCode:
    """Transient authorization code issued after successful login."""

    code: str
    client_id: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    code_challenge: str
    scopes: list[str]
    issued_at: float
    expires_at: float
    # SheetStorm tokens received from backend on login
    sheetstorm_access_token: str
    sheetstorm_refresh_token: str | None = None
    sheetstorm_user: dict = field(default_factory=dict)
    resource: str | None = None


@dataclass
class StoredRefreshToken:
    """Opaque refresh-token record."""

    token: str
    client_id: str
    scopes: list[str]
    sheetstorm_refresh_token: str | None = None
    sheetstorm_access_token: str = ""


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------


class SheetStormOAuthProvider(
    OAuthAuthorizationServerProvider[StoredAuthCode, StoredRefreshToken, AccessToken]
):
    """MCP OAuth provider that delegates credential verification to the
    SheetStorm backend (``/auth/login``, ``/auth/me``, ``/auth/refresh``).
    """

    def __init__(self, *, api_url: str, mcp_issuer_url: str, redis_url: str | None = None) -> None:
        self._api_url = api_url.rstrip("/")
        self._mcp_issuer_url = mcp_issuer_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(20))

        # Redis for persistent client storage (survives container restarts)
        self._redis = None
        if redis_url:
            try:
                import redis
                self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
                logger.info("Connected to Redis for OAuth client persistence")
            except Exception:
                logger.exception("Failed to connect to Redis — client registrations will be in-memory only")
                self._redis = None

        # In-memory cache (populated from Redis on get_client)
        self._clients: dict[str, OAuthClientInformationFull] = {}

        # In-memory stores – keyed by the relevant identifier
        self._auth_codes: dict[str, StoredAuthCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, StoredRefreshToken] = {}
        # Map SheetStorm JWTs ↔ MCP opaque tokens
        self._jwt_by_mcp_token: dict[str, str] = {}  # mcp_token → jwt
        # Pending auth params (keyed by random state) awaiting login form
        self._pending_auth: dict[str, dict] = {}

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _new_token(nbytes: int = 32) -> str:
        return secrets.token_urlsafe(nbytes)

    async def close(self) -> None:
        await self._http.aclose()
        if self._redis:
            self._redis.close()

    # -----------------------------------------------------------------------
    # Client registration (RFC 7591 — persisted in Redis)
    # -----------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        # Check in-memory cache first
        cached = self._clients.get(client_id)
        if cached:
            return cached

        # Fall back to Redis
        if self._redis:
            try:
                raw = self._redis.get(f"{_REDIS_CLIENT_PREFIX}{client_id}")
                if raw:
                    info = OAuthClientInformationFull.model_validate(json.loads(raw))
                    self._clients[client_id] = info  # warm cache
                    return info
            except Exception:
                logger.exception("Failed to load OAuth client %s from Redis", client_id)

        return None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info

        # Persist to Redis (no expiry — clients live until explicitly deleted)
        if self._redis:
            try:
                self._redis.set(
                    f"{_REDIS_CLIENT_PREFIX}{client_info.client_id}",
                    json.dumps(client_info.model_dump(mode="json")),
                )
            except Exception:
                logger.exception("Failed to persist OAuth client to Redis")

        logger.info("Registered OAuth client %s", client_info.client_id)

    # -----------------------------------------------------------------------
    # Authorization
    # -----------------------------------------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Redirect to our own login page, stashing params."""
        pending_id = self._new_token(24)
        self._pending_auth[pending_id] = {
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "state": params.state,
            "code_challenge": params.code_challenge,
            "scopes": params.scopes or [],
            "resource": params.resource,
        }
        return f"{self._mcp_issuer_url}/sheetstorm-login?pid={pending_id}"

    # -----------------------------------------------------------------------
    # Authorization code exchange
    # -----------------------------------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> StoredAuthCode | None:
        code_obj = self._auth_codes.get(authorization_code)
        if code_obj is None:
            return None
        if code_obj.client_id != client.client_id:
            return None
        if time.time() > code_obj.expires_at:
            self._auth_codes.pop(authorization_code, None)
            return None
        return code_obj

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: StoredAuthCode
    ) -> OAuthToken:
        # Consume the code (one-time use)
        self._auth_codes.pop(authorization_code.code, None)

        # Issue MCP opaque tokens backed by the real SheetStorm JWTs
        mcp_access = self._new_token()
        mcp_refresh = self._new_token()

        self._jwt_by_mcp_token[mcp_access] = authorization_code.sheetstorm_access_token
        self._jwt_by_mcp_token[mcp_refresh] = authorization_code.sheetstorm_refresh_token or ""

        self._access_tokens[mcp_access] = AccessToken(
            token=mcp_access,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + 3600,
            resource=authorization_code.resource,
        )
        self._refresh_tokens[mcp_refresh] = StoredRefreshToken(
            token=mcp_refresh,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            sheetstorm_refresh_token=authorization_code.sheetstorm_refresh_token,
            sheetstorm_access_token=authorization_code.sheetstorm_access_token,
        )

        logger.info("Issued MCP tokens for client=%s", client.client_id)
        return OAuthToken(
            access_token=mcp_access,
            token_type="Bearer",
            expires_in=3600,
            refresh_token=mcp_refresh,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    # -----------------------------------------------------------------------
    # Refresh token exchange
    # -----------------------------------------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> StoredRefreshToken | None:
        rt = self._refresh_tokens.get(refresh_token)
        if rt and rt.client_id == client.client_id:
            return rt
        return None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: StoredRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Try to refresh the SheetStorm JWT
        ss_refresh = refresh_token.sheetstorm_refresh_token
        new_ss_access = refresh_token.sheetstorm_access_token

        if ss_refresh:
            try:
                resp = await self._http.post(
                    f"{self._api_url}/auth/refresh",
                    headers={"Authorization": f"Bearer {ss_refresh}"},
                )
                if resp.status_code < 400:
                    data = resp.json()
                    new_ss_access = data.get("access_token", new_ss_access)
            except Exception as exc:
                logger.warning("SheetStorm token refresh failed: %s", exc)

        # Rotate MCP tokens
        old_mcp_access = [k for k, v in self._access_tokens.items() if v.client_id == client.client_id]
        for k in old_mcp_access:
            self._jwt_by_mcp_token.pop(k, None)
            self._access_tokens.pop(k, None)

        old_refresh_token_str = refresh_token.token
        self._jwt_by_mcp_token.pop(old_refresh_token_str, None)
        self._refresh_tokens.pop(old_refresh_token_str, None)

        new_mcp_access = self._new_token()
        new_mcp_refresh = self._new_token()

        self._jwt_by_mcp_token[new_mcp_access] = new_ss_access
        self._jwt_by_mcp_token[new_mcp_refresh] = ss_refresh or ""

        self._access_tokens[new_mcp_access] = AccessToken(
            token=new_mcp_access,
            client_id=client.client_id,
            scopes=scopes or refresh_token.scopes,
            expires_at=int(time.time()) + 3600,
        )
        self._refresh_tokens[new_mcp_refresh] = StoredRefreshToken(
            token=new_mcp_refresh,
            client_id=client.client_id,
            scopes=scopes or refresh_token.scopes,
            sheetstorm_refresh_token=ss_refresh,
            sheetstorm_access_token=new_ss_access,
        )

        return OAuthToken(
            access_token=new_mcp_access,
            token_type="Bearer",
            expires_in=3600,
            refresh_token=new_mcp_refresh,
        )

    # -----------------------------------------------------------------------
    # Access token verification (called on EVERY MCP request)
    # -----------------------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        at = self._access_tokens.get(token)
        if at is None:
            return None
        if at.expires_at and time.time() > at.expires_at:
            self._access_tokens.pop(token, None)
            self._jwt_by_mcp_token.pop(token, None)
            return None
        return at

    # -----------------------------------------------------------------------
    # Revocation
    # -----------------------------------------------------------------------

    async def revoke_token(self, token: AccessToken | StoredRefreshToken) -> None:
        tok_str = token.token
        self._access_tokens.pop(tok_str, None)
        self._refresh_tokens.pop(tok_str, None)
        self._jwt_by_mcp_token.pop(tok_str, None)
        logger.info("Revoked token %s…", tok_str[:8])

    # -----------------------------------------------------------------------
    # Login flow helpers (called from Starlette routes, not MCP SDK)
    # -----------------------------------------------------------------------

    def get_pending_auth(self, pending_id: str) -> dict | None:
        return self._pending_auth.get(pending_id)

    async def handle_login(
        self, pending_id: str, email: str, password: str, mfa_code: str | None = None
    ) -> str:
        """Validate credentials against SheetStorm backend, issue auth code,
        and return the redirect URL for the client.

        Raises ``AuthorizeError`` on failure.
        """
        pending = self._pending_auth.pop(pending_id, None)
        if not pending:
            raise AuthorizeError(
                error="invalid_request",
                error_description="Login session expired. Please try again.",
            )

        # Authenticate against SheetStorm backend
        payload: dict[str, Any] = {"email": email, "password": password}
        if mfa_code:
            payload["mfa_code"] = mfa_code

        try:
            resp = await self._http.post(f"{self._api_url}/auth/login", json=payload)
        except Exception as exc:
            # Put pending auth back so user can retry
            self._pending_auth[pending_id] = pending
            raise AuthorizeError(
                error="server_error",
                error_description=f"Failed to reach SheetStorm backend: {exc}",
            )

        if resp.status_code >= 400:
            data = resp.json() if resp.content else {}
            # MFA required – put pending back
            if resp.status_code == 403 and data.get("mfa_required"):
                self._pending_auth[pending_id] = pending
                raise AuthorizeError(
                    error="invalid_request",
                    error_description="MFA code required.",
                )
            # Put pending back for retry
            self._pending_auth[pending_id] = pending
            msg = data.get("message") or data.get("error") or "Invalid credentials"
            raise AuthorizeError(
                error="access_denied",
                error_description=msg,
            )

        data = resp.json()
        ss_access = data.get("access_token", "")
        ss_refresh = data.get("refresh_token")
        ss_user = data.get("user", {})

        # Generate authorization code
        code = self._new_token(32)
        now = time.time()

        self._auth_codes[code] = StoredAuthCode(
            code=code,
            client_id=pending["client_id"],
            redirect_uri=pending["redirect_uri"],
            redirect_uri_provided_explicitly=pending["redirect_uri_provided_explicitly"],
            code_challenge=pending["code_challenge"],
            scopes=pending["scopes"],
            issued_at=now,
            expires_at=now + 300,  # 5 minute validity
            sheetstorm_access_token=ss_access,
            sheetstorm_refresh_token=ss_refresh,
            sheetstorm_user=ss_user,
            resource=pending.get("resource"),
        )

        # Build redirect URI with code + state
        redirect_uri = pending["redirect_uri"]
        sep = "&" if "?" in redirect_uri else "?"
        url = f"{redirect_uri}{sep}code={code}"
        if pending.get("state"):
            url += f"&state={pending['state']}"

        logger.info(
            "User %s authenticated, issuing auth code for client=%s",
            email,
            pending["client_id"],
        )
        return url

    def get_sheetstorm_jwt(self, mcp_token: str) -> str | None:
        """Look up the real SheetStorm JWT for a given MCP opaque token."""
        return self._jwt_by_mcp_token.get(mcp_token)
