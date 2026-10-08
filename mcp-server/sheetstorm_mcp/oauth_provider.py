"""OAuth 2.0 Authorization Server Provider for the SheetStorm MCP Server.

Implements the full MCP OAuth flow so that VS Code / Claude Desktop users
are redirected to a login page, authenticate with their SheetStorm
credentials, and receive an access token scoped to *their* identity.

Flow
----
1.  MCP client connects → gets 401 with ``WWW-Authenticate``
2.  Client registers dynamically (redirect URIs restricted to loopback or
    ``MCP_ALLOWED_REDIRECT_HOSTS``) and opens the browser at ``/authorize``
3.  Provider redirects to ``/sheetstorm-login`` which shows the requesting
    client and redirect host and requires explicit consent
4.  User submits credentials → MCP server calls SheetStorm ``/auth/login``
5.  On success an authorization code is generated and the user is redirected
    back to the client's ``redirect_uri``
6.  Client exchanges auth code for opaque MCP tokens via ``/token``
7.  Each MCP request's bearer maps to a :class:`Grant` holding the user's
    SheetStorm JWT (refreshed and rotated transparently)
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from sheetstorm_mcp.client import (
    AuthenticationError,
    Grant,
    no_cookie_jar,
    refresh_backend_tokens,
)

logger = logging.getLogger("sheetstorm_mcp.oauth")

# Redis key prefix for OAuth client registrations
_REDIS_CLIENT_PREFIX = "mcp:oauth:client:"

# Lifetimes (seconds)
PENDING_AUTH_TTL = 600                  # login page must be completed within 10 min
AUTH_CODE_TTL = 300                     # authorization code validity
ACCESS_TOKEN_TTL = 3600                 # MCP access token
REFRESH_TOKEN_TTL = 30 * 24 * 3600      # MCP refresh token (re-login after 30 days)
CLIENT_REGISTRATION_TTL = 90 * 24 * 3600  # Redis-persisted dynamic client records

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def allowed_redirect_hosts() -> set[str]:
    """Extra (non-loopback) redirect hosts from ``MCP_ALLOWED_REDIRECT_HOSTS``."""
    raw = os.getenv("MCP_ALLOWED_REDIRECT_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def redirect_uri_allowed(uri: str, extra_hosts: set[str] | None = None) -> bool:
    """Loopback http(s) redirect URIs are always allowed; other hosts only when
    listed in ``MCP_ALLOWED_REDIRECT_HOSTS`` and only over https."""
    try:
        parsed = urlparse(str(uri))
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if not host or parsed.username or parsed.password:
        return False
    if parsed.scheme in ("http", "https"):
        if host in _LOOPBACK_HOSTS:
            return True
        try:
            if ipaddress.ip_address(host).is_loopback:
                return True
        except ValueError:
            pass
    hosts = allowed_redirect_hosts() if extra_hosts is None else extra_hosts
    return parsed.scheme == "https" and host in hosts


# ---------------------------------------------------------------------------
# Stored records
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
    """Opaque MCP refresh-token record (backed by a :class:`Grant`)."""

    token: str
    client_id: str
    scopes: list[str]
    grant_id: str = ""
    expires_at: float | None = None  # MCP SDK rejects expired refresh tokens on /token


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------


class SheetStormOAuthProvider(
    OAuthAuthorizationServerProvider[StoredAuthCode, StoredRefreshToken, AccessToken]
):
    """MCP OAuth provider that delegates credential verification to the
    SheetStorm backend (``/auth/login``, ``/auth/refresh``, ``/auth/logout``).
    """

    def __init__(self, *, api_url: str, mcp_issuer_url: str, redis_url: str | None = None) -> None:
        self._api_url = api_url.rstrip("/")
        self._mcp_issuer_url = mcp_issuer_url.rstrip("/")
        self._http = self._new_http()

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
        self._grants: dict[str, Grant] = {}
        self._grant_by_token: dict[str, str] = {}  # MCP access/refresh token → grant_id
        # Pending auth params (keyed by random id) awaiting the login form
        self._pending_auth: dict[str, dict] = {}

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _new_token(nbytes: int = 32) -> str:
        return secrets.token_urlsafe(nbytes)

    @staticmethod
    def _new_http() -> httpx.AsyncClient:
        # Header-only auth: never persist the backend's auth cookies in a client
        # shared by every user of this server.
        return httpx.AsyncClient(timeout=httpx.Timeout(20), cookies=no_cookie_jar())

    def _get_http(self) -> httpx.AsyncClient:
        """Return the httpx client, re-creating it if it was previously closed.

        The provider is a module-level singleton that survives server lifespan
        cycles; a closed client is transparently re-created.
        """
        if self._http.is_closed:
            logger.info("HTTP client was closed — re-creating")
            self._http = self._new_http()
        return self._http

    async def close(self) -> None:
        if not self._http.is_closed:
            await self._http.aclose()
        if self._redis:
            self._redis.close()

    def purge_expired(self, now: float | None = None) -> None:
        """Drop expired pending logins, codes, tokens and orphaned grants."""
        now = time.time() if now is None else now
        for pid, p in list(self._pending_auth.items()):
            if now - p.get("created_at", 0) > PENDING_AUTH_TTL:
                self._pending_auth.pop(pid, None)
        for code, c in list(self._auth_codes.items()):
            if now > c.expires_at:
                self._auth_codes.pop(code, None)
        for tok, at in list(self._access_tokens.items()):
            if at.expires_at and now > at.expires_at:
                self._drop_token(tok)
        for tok, rt in list(self._refresh_tokens.items()):
            if rt.expires_at and now > rt.expires_at:
                self._drop_token(tok)
        live = set(self._grant_by_token.values())
        for gid in list(self._grants):
            if gid not in live:
                self._grants.pop(gid, None)

    def _drop_token(self, tok: str) -> None:
        self._access_tokens.pop(tok, None)
        self._refresh_tokens.pop(tok, None)
        self._grant_by_token.pop(tok, None)

    def _issue_tokens(self, grant: Grant, scopes: list[str], resource: str | None) -> OAuthToken:
        now = int(time.time())
        mcp_access = self._new_token()
        mcp_refresh = self._new_token()
        self._access_tokens[mcp_access] = AccessToken(
            token=mcp_access,
            client_id=grant.client_id,
            scopes=scopes,
            expires_at=now + ACCESS_TOKEN_TTL,
            resource=resource,
        )
        self._refresh_tokens[mcp_refresh] = StoredRefreshToken(
            token=mcp_refresh,
            client_id=grant.client_id,
            scopes=scopes,
            grant_id=grant.grant_id,
            expires_at=now + REFRESH_TOKEN_TTL,
        )
        self._grant_by_token[mcp_access] = grant.grant_id
        self._grant_by_token[mcp_refresh] = grant.grant_id
        return OAuthToken(
            access_token=mcp_access,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=mcp_refresh,
            scope=" ".join(scopes) if scopes else None,
        )

    # -----------------------------------------------------------------------
    # Client registration (RFC 7591 — persisted in Redis with a TTL)
    # -----------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        cached = self._clients.get(client_id)
        if cached:
            return cached

        if self._redis:
            try:
                key = f"{_REDIS_CLIENT_PREFIX}{client_id}"
                raw = self._redis.get(key)
                if raw:
                    info = OAuthClientInformationFull.model_validate(json.loads(raw))
                    self._redis.expire(key, CLIENT_REGISTRATION_TTL)  # sliding expiry
                    self._clients[client_id] = info  # warm cache
                    return info
            except Exception:
                logger.exception("Failed to load OAuth client %s from Redis", client_id)

        return None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        bad = [str(u) for u in (client_info.redirect_uris or []) if not redirect_uri_allowed(str(u))]
        if bad:
            raise RegistrationError(
                error="invalid_redirect_uri",
                error_description=(
                    "Redirect URIs must be loopback (http://127.0.0.1, http://localhost) "
                    "or an https host listed in MCP_ALLOWED_REDIRECT_HOSTS."
                ),
            )

        self._clients[client_info.client_id] = client_info
        if self._redis:
            try:
                self._redis.set(
                    f"{_REDIS_CLIENT_PREFIX}{client_info.client_id}",
                    json.dumps(client_info.model_dump(mode="json")),
                    ex=CLIENT_REGISTRATION_TTL,
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
        """Redirect to our own login/consent page, stashing params."""
        self.purge_expired()
        redirect_uri = str(params.redirect_uri)
        # Re-check here too: clients persisted before the restriction existed.
        if not redirect_uri_allowed(redirect_uri):
            raise AuthorizeError(
                error="invalid_request",
                error_description="redirect_uri host is not allowed by this server.",
            )
        pending_id = self._new_token(24)
        self._pending_auth[pending_id] = {
            "client_id": client.client_id,
            "client_name": client.client_name or "",
            "redirect_uri": redirect_uri,
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "state": params.state,
            "code_challenge": params.code_challenge,
            "scopes": params.scopes or [],
            "resource": params.resource,
            "created_at": time.time(),
        }
        return f"{self._mcp_issuer_url}/sheetstorm-login?{urlencode({'pid': pending_id})}"

    # -----------------------------------------------------------------------
    # Authorization code exchange
    # -----------------------------------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> StoredAuthCode | None:
        self.purge_expired()
        code_obj = self._auth_codes.get(authorization_code)
        if code_obj is None or code_obj.client_id != client.client_id:
            return None
        return code_obj

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: StoredAuthCode
    ) -> OAuthToken:
        # Consume the code (one-time use)
        self._auth_codes.pop(authorization_code.code, None)

        user = authorization_code.sheetstorm_user or {}
        grant = Grant(
            grant_id=self._new_token(16),
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            sheetstorm_access_token=authorization_code.sheetstorm_access_token,
            sheetstorm_refresh_token=authorization_code.sheetstorm_refresh_token,
            user_id=str(user["id"]) if user.get("id") else None,
            organization_id=str(user["organization_id"]) if user.get("organization_id") else None,
            email=user.get("email"),
        )
        self._grants[grant.grant_id] = grant
        logger.info("Issued MCP tokens for client=%s", client.client_id)
        return self._issue_tokens(grant, authorization_code.scopes, authorization_code.resource)

    # -----------------------------------------------------------------------
    # Refresh token exchange
    # -----------------------------------------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> StoredRefreshToken | None:
        self.purge_expired()
        rt = self._refresh_tokens.get(refresh_token)
        if rt and rt.client_id == client.client_id and rt.grant_id in self._grants:
            return rt
        return None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: StoredRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        grant = self._grants.get(refresh_token.grant_id)
        if grant is None:
            raise TokenError(error="invalid_grant", error_description="Session no longer exists.")

        # Refresh (and rotate) the backend session. If the backend refuses, the
        # MCP grant is dead: revoke it so the client starts a fresh login
        # instead of holding tokens that map to an unusable backend session.
        async with grant.lock:
            if not grant.sheetstorm_refresh_token:
                self.revoke_grant(grant.grant_id)
                raise TokenError(error="invalid_grant", error_description="Session expired; please sign in again.")
            try:
                access, new_refresh = await refresh_backend_tokens(
                    self._get_http(), f"{self._api_url}/auth/refresh", grant.sheetstorm_refresh_token
                )
            except (AuthenticationError, httpx.HTTPError, ValueError) as exc:
                logger.warning("SheetStorm token refresh failed for grant %s…: %s", grant.grant_id[:8], exc)
                self.revoke_grant(grant.grant_id)
                raise TokenError(
                    error="invalid_grant", error_description="Session expired; please sign in again."
                ) from exc
            grant.sheetstorm_access_token = access
            grant.sheetstorm_refresh_token = new_refresh

        # Rotate MCP tokens of THIS grant only (never other users of the same
        # client registration). Old access tokens stay valid until they expire
        # so in-flight sessions are not cut off mid-request.
        self._drop_token(refresh_token.token)
        return self._issue_tokens(grant, scopes or refresh_token.scopes, None)

    # -----------------------------------------------------------------------
    # Access token verification (called on EVERY MCP request)
    # -----------------------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        at = self._access_tokens.get(token)
        if at is None:
            return None
        if at.expires_at and time.time() > at.expires_at:
            self._drop_token(token)
            return None
        if self._grant_by_token.get(token) not in self._grants:
            self._drop_token(token)
            return None
        return at

    # -----------------------------------------------------------------------
    # Revocation
    # -----------------------------------------------------------------------

    async def revoke_token(self, token: AccessToken | StoredRefreshToken) -> None:
        """RFC 7009 revocation: revoking either token ends the whole grant."""
        gid = self._grant_by_token.get(token.token)
        self._drop_token(token.token)
        if gid:
            self.revoke_grant(gid)
        logger.info("Revoked MCP token")

    def revoke_grant(self, grant_id: str) -> None:
        """Invalidate every MCP token of a grant and forget its backend tokens."""
        for tok, gid in list(self._grant_by_token.items()):
            if gid == grant_id:
                self._drop_token(tok)
        self._grants.pop(grant_id, None)

    # -----------------------------------------------------------------------
    # Per-request resolution
    # -----------------------------------------------------------------------

    def get_grant(self, mcp_token: str) -> Grant | None:
        """Return the live grant for an MCP access token, or None."""
        at = self._access_tokens.get(mcp_token)
        if at is None or (at.expires_at and time.time() > at.expires_at):
            return None
        gid = self._grant_by_token.get(mcp_token)
        return self._grants.get(gid) if gid else None

    def get_sheetstorm_jwt(self, mcp_token: str) -> str | None:
        """Look up the current SheetStorm JWT for a given MCP access token."""
        grant = self.get_grant(mcp_token)
        return grant.sheetstorm_access_token if grant else None

    # -----------------------------------------------------------------------
    # Login flow helpers (called from Starlette routes, not MCP SDK)
    # -----------------------------------------------------------------------

    def get_pending_auth(self, pending_id: str) -> dict | None:
        self.purge_expired()
        return self._pending_auth.get(pending_id)

    async def handle_login(
        self, pending_id: str, email: str, password: str, mfa_code: str | None = None
    ) -> str:
        """Validate credentials against SheetStorm backend, issue auth code,
        and return the redirect URL for the client.

        Raises ``AuthorizeError`` on failure.
        """
        self.purge_expired()
        pending = self._pending_auth.pop(pending_id, None)
        if not pending:
            raise AuthorizeError(
                error="invalid_request",
                error_description="Login session expired. Please try again.",
            )

        payload: dict[str, Any] = {"email": email, "password": password}
        if mfa_code:
            payload["mfa_code"] = mfa_code

        try:
            resp = await self._get_http().post(f"{self._api_url}/auth/login", json=payload)
        except Exception:
            self._pending_auth[pending_id] = pending  # allow retry
            logger.exception("Failed to reach SheetStorm backend during login")
            raise AuthorizeError(
                error="server_error",
                error_description="Failed to reach the SheetStorm backend. Please try again.",
            )

        if resp.status_code >= 400:
            try:
                data = resp.json() if resp.content else {}
            except ValueError:
                data = {}
            self._pending_auth[pending_id] = pending  # allow retry
            if resp.status_code == 403 and data.get("mfa_required"):
                raise AuthorizeError(error="invalid_request", error_description="MFA code required.")
            msg = data.get("message") or data.get("error") or "Invalid credentials"
            raise AuthorizeError(error="access_denied", error_description=str(msg))

        data = resp.json()
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
            expires_at=now + AUTH_CODE_TTL,
            sheetstorm_access_token=data.get("access_token", ""),
            sheetstorm_refresh_token=data.get("refresh_token"),
            sheetstorm_user=data.get("user") or {},
            resource=pending.get("resource"),
        )

        redirect_uri = pending["redirect_uri"]
        query = {"code": code}
        if pending.get("state"):
            query["state"] = pending["state"]
        sep = "&" if "?" in redirect_uri else "?"
        logger.info("User authenticated, issuing auth code for client=%s", pending["client_id"])
        return f"{redirect_uri}{sep}{urlencode(query)}"
