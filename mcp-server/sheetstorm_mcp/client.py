"""Async HTTP client for the SheetStorm backend API.

Handles authentication, token refresh (with refresh-token rotation), retries,
and typed error propagation.

Per-request authentication
--------------------------
When the MCP server runs on the remote (OAuth) transport, ``server.get_client()``
resolves the OAuth grant of the *current* MCP request and stores it in the
``_request_grant`` ContextVar before each tool executes. The shared client then
uses that grant's SheetStorm JWT, refreshing it (and storing the rotated
refresh token) when the backend answers 401. Static credentials from the
environment are only ever used on the stdio transport.

API keys
--------
With ``SHEETSTORM_API_KEY`` the client exchanges the key at
``POST /auth/token`` for a short-lived access token, re-exchanges shortly
before it expires and once after a 401. A rejected key (revoked, expired,
disabled) raises ``AuthenticationError`` without retrying. The key is never
logged; messages show its public prefix only.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import time
from dataclasses import dataclass, field
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any

import httpx

from sheetstorm_mcp.config import Config

logger = logging.getLogger("sheetstorm_mcp.client")


# ---------------------------------------------------------------------------
# Per-user OAuth grant (remote transport)
# ---------------------------------------------------------------------------

@dataclass
class Grant:
    """SheetStorm session backing one OAuth authorization (one user + client).

    Both the MCP access token and MCP refresh token of an authorization point
    at the same grant, so rotating the backend tokens here is visible to every
    MCP token of that authorization.
    """

    grant_id: str
    client_id: str
    scopes: list[str]
    sheetstorm_access_token: str
    sheetstorm_refresh_token: str | None = None
    user_id: str | None = None
    organization_id: str | None = None
    email: str | None = None
    created_at: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)


# Grant of the MCP request currently being served. Always (re)set by
# ``server.get_client()`` — never left over from a previous request.
_request_grant: contextvars.ContextVar[Grant | None] = contextvars.ContextVar(
    "sheetstorm_request_grant", default=None
)


def no_cookie_jar() -> CookieJar:
    """A cookie jar that never stores or sends cookies.

    The backend sets auth cookies on login/refresh. Auth here is header-only;
    persisting cookies in a client shared by several users would leak one
    user's session into another user's requests.
    """
    return CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))


async def refresh_backend_tokens(
    http: httpx.AsyncClient, url: str, refresh_token: str
) -> tuple[str, str | None]:
    """Call ``POST /auth/refresh`` and return ``(access_token, refresh_token)``.

    The backend rotates refresh tokens: the presented one is revoked and a new
    one is returned, which callers MUST store. Raises ``AuthenticationError``
    when the backend rejects the refresh.
    """
    resp = await http.post(url, headers={"Authorization": f"Bearer {refresh_token}"})
    if resp.status_code >= 400:
        raise AuthenticationError("Token refresh failed", status_code=resp.status_code)
    data = resp.json()
    access = data.get("access_token")
    if not access:
        raise AuthenticationError("Token refresh returned no access token", status_code=resp.status_code)
    return access, data.get("refresh_token") or None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SheetStormAPIError(Exception):
    """Base exception for SheetStorm API errors."""

    def __init__(self, message: str, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class AuthenticationError(SheetStormAPIError):
    """401/403 — authentication or authorization failure."""


class NotFoundError(SheetStormAPIError):
    """404 — resource not found."""


class ValidationError(SheetStormAPIError):
    """400 — bad request / validation failure."""


class ServerError(SheetStormAPIError):
    """5xx — backend server error."""


# Re-exchange an API key this many seconds before its token expires.
API_KEY_REFRESH_MARGIN = 60


def api_key_prefix(key: str | None) -> str:
    """The public part of an API key (`ssk_<lookup>`), safe to log."""
    if key and key.startswith("ssk_") and len(key) > 16:
        return key[:16]
    return "ssk_…"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class SheetStormClient:
    """Async HTTP client wrapping the SheetStorm REST API."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._base_url = config.api_url.rstrip("/")
        # Static credentials are a stdio-only convenience. On the remote OAuth
        # transport every request must carry the calling user's own grant
        # (SHEETSTORM_API_KEY is ignored there too).
        self._api_key: str | None = (config.api_key or None) if self.is_stdio else None
        self._access_token: str | None = (
            (config.api_token or None) if self.is_stdio and not self._api_key else None
        )
        self._refresh_token: str | None = None
        self._token_expires_at: float | None = None  # monotonic; API-key tokens only
        self._exchange_lock = asyncio.Lock()
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(config.http_timeout),
            follow_redirects=True,
            cookies=no_cookie_jar(),
            # Informational: the backend snapshots it into custody ledger entries.
            headers={"X-SheetStorm-Client": "mcp-server"},
        )

    @property
    def is_stdio(self) -> bool:
        return self._config.transport == "stdio"

    # -- lifecycle -----------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    # -- auth ----------------------------------------------------------------

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    async def login(self, username: str, password: str, mfa_code: str | None = None) -> dict:
        """Authenticate and store tokens (stdio transport only).

        Returns the login response payload (user info, tokens, etc.).
        Handles MFA challenge (403 with mfa_required flag).
        """
        if not self.is_stdio:
            raise AuthenticationError(
                "Direct login is disabled on the remote transport; use the browser OAuth flow.",
                status_code=401,
            )
        payload: dict[str, Any] = {"email": username, "password": password}
        if mfa_code:
            payload["mfa_code"] = mfa_code

        resp = await self._http.post("/auth/login", json=payload)
        data = resp.json()

        # MFA required — return the challenge so the caller can prompt
        if resp.status_code == 403 and data.get("mfa_required"):
            return {"mfa_required": True, "message": data.get("message", "MFA code required")}

        if resp.status_code >= 400:
            raise AuthenticationError(
                data.get("message") or data.get("error") or "Login failed",
                status_code=resp.status_code,
                detail=data,
            )

        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        logger.info("Authenticated to SheetStorm backend")
        return data

    @property
    def uses_api_key(self) -> bool:
        return self._api_key is not None

    def _api_key_token_fresh(self) -> bool:
        return (
            self._access_token is not None
            and self._token_expires_at is not None
            and time.monotonic() < self._token_expires_at - API_KEY_REFRESH_MARGIN
        )

    async def exchange_api_key(self) -> dict:
        """``POST /auth/token`` with the configured key; stores the access token.

        Raises AuthenticationError when the backend rejects the key (no retry)."""
        if not self._api_key:
            raise AuthenticationError("No API key configured", status_code=401)
        prefix = api_key_prefix(self._api_key)
        try:
            resp = await self._http.post("/auth/token", json={"api_key": self._api_key})
        except httpx.TransportError as exc:
            raise SheetStormAPIError(f"Network error during API key exchange: {exc}") from exc
        if resp.status_code in (401, 403):
            self._access_token = None
            self._token_expires_at = None
            raise AuthenticationError(
                f"API key {prefix} rejected (revoked, expired or disabled)",
                status_code=resp.status_code,
            )
        if resp.status_code >= 400:
            self._raise_for_status(resp)
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise AuthenticationError("API key exchange returned no access token", status_code=resp.status_code)
        self._access_token = token
        self._token_expires_at = time.monotonic() + float(data.get("expires_in") or 900)
        logger.info("Authenticated to SheetStorm backend with API key %s", prefix)
        return data

    async def _ensure_api_key_token(self, failed_token: str | None = None) -> None:
        """Exchange when the token is missing or about to expire, or after a
        401 on `failed_token`; one exchange at a time."""
        async with self._exchange_lock:
            if failed_token is not None:
                if self._access_token != failed_token and self._api_key_token_fresh():
                    return  # another request already re-exchanged
            elif self._api_key_token_fresh():
                return
            await self.exchange_api_key()

    async def refresh(self) -> None:
        """Refresh the stdio session's access token, storing the rotated refresh token."""
        if not self._refresh_token:
            raise AuthenticationError("No refresh token available", status_code=401)
        try:
            access, new_refresh = await refresh_backend_tokens(
                self._http, "/auth/refresh", self._refresh_token
            )
        except AuthenticationError:
            self._access_token = None
            self._refresh_token = None
            raise
        self._access_token = access
        # Rotation: the old refresh token is now revoked by the backend.
        self._refresh_token = new_refresh
        logger.debug("Access token refreshed")

    async def _refresh_grant(self, grant: Grant, failed_token: str) -> None:
        """Refresh a remote user's backend tokens once, even under concurrency."""
        async with grant.lock:
            if grant.sheetstorm_access_token != failed_token:
                return  # another request already refreshed this grant
            if not grant.sheetstorm_refresh_token:
                raise AuthenticationError("No refresh token available", status_code=401)
            access, new_refresh = await refresh_backend_tokens(
                self._http, "/auth/refresh", grant.sheetstorm_refresh_token
            )
            grant.sheetstorm_access_token = access
            grant.sheetstorm_refresh_token = new_refresh
            logger.debug("Refreshed backend tokens for grant %s…", grant.grant_id[:8])

    async def logout(self) -> dict:
        """Log out of the backend, revoking the access AND refresh token.

        With an API key this only revokes the current short-lived token (the
        next call exchanges the key again); revoke the key itself in the UI."""
        grant = _request_grant.get()
        refresh = grant.sheetstorm_refresh_token if grant else self._refresh_token
        body = {"refresh_token": refresh} if refresh else None
        try:
            return await self._request("POST", "/auth/logout", json=body, _retry=1)
        finally:
            if grant is None:
                self._access_token = None
                self._refresh_token = None
                self._token_expires_at = None

    async def ensure_authenticated(self) -> None:
        """Ensure a usable token exists.

        Remote transport: the current request's OAuth grant is mandatory.
        stdio transport: stored token, else auto-login with configured credentials.
        """
        if _request_grant.get() is not None:
            return
        if not self.is_stdio:
            raise AuthenticationError(
                "Not authenticated. Please authenticate via the browser OAuth flow.",
                status_code=401,
            )
        if self._api_key:
            await self._ensure_api_key_token()
            return
        if self.is_authenticated:
            return
        cfg = self._config
        if cfg.username and cfg.password:
            await self.login(cfg.username, cfg.password)
        else:
            raise AuthenticationError(
                "Not authenticated. Set SHEETSTORM_API_KEY (recommended), "
                "SHEETSTORM_API_TOKEN or SHEETSTORM_USERNAME/SHEETSTORM_PASSWORD.",
                status_code=401,
            )

    def _current_token(self) -> str | None:
        grant = _request_grant.get()
        if grant is not None:
            return grant.sheetstorm_access_token
        return self._access_token if self.is_stdio else None

    # -- HTTP methods --------------------------------------------------------

    async def get(self, path: str, params: dict | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: dict | None = None) -> Any:
        return await self._request("POST", path, json=json)

    async def put(self, path: str, json: dict | None = None) -> Any:
        return await self._request("PUT", path, json=json)

    async def patch(self, path: str, json: dict | None = None) -> Any:
        return await self._request("PATCH", path, json=json)

    async def delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    async def upload(
        self,
        path: str,
        filename: str,
        content: bytes,
        data: dict[str, str] | None = None,
        field_name: str = "file",
    ) -> Any:
        """Upload file content via multipart/form-data with optional form fields."""
        import mimetypes

        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        files = {field_name: (filename, content, mime)}
        return await self._request("POST", path, files=files, data=data)

    async def download(self, path: str) -> bytes:
        """Download binary content."""
        resp = await self._send("GET", path)
        return resp.content

    # -- internal ------------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = await self._send(method, path, **kwargs)
        # some DELETE endpoints return 204 No Content
        if resp.status_code == 204 or not resp.content:
            return {"success": True}
        return resp.json()

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        files: dict | None = None,
        data: dict | None = None,
        _retry: int = 0,
    ) -> httpx.Response:
        """Execute an HTTP request with auth headers, retries, and error handling."""
        await self.ensure_authenticated()

        token = self._current_token()
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        again = dict(json=json, params=params, files=files, data=data)
        try:
            resp = await self._http.request(
                method, path, headers=headers, json=json, params=params, files=files, data=data,
            )
        except httpx.TransportError as exc:
            if _retry < self._config.http_max_retries:
                logger.warning(
                    "Network error, retrying (%d/%d): %s",
                    _retry + 1, self._config.http_max_retries, exc,
                )
                return await self._send(method, path, **again, _retry=_retry + 1)
            raise SheetStormAPIError(f"Network error: {exc}") from exc

        # auto-refresh on 401 (once)
        if resp.status_code == 401 and _retry == 0:
            grant = _request_grant.get()
            if grant is None and self._api_key:
                # Re-exchange once; a rejected key raises (no retry loop).
                await self._ensure_api_key_token(failed_token=token)
                return await self._send(method, path, **again, _retry=1)
            try:
                if grant is not None and token:
                    await self._refresh_grant(grant, token)
                elif grant is None and self.is_stdio and self._refresh_token:
                    await self.refresh()
                else:
                    raise AuthenticationError("no refresh possible")
                return await self._send(method, path, **again, _retry=1)
            except AuthenticationError:
                logger.debug("Token refresh not possible after 401")

        # retry 5xx
        if resp.status_code >= 500 and _retry < self._config.http_max_retries:
            logger.warning(
                "Server error %d, retrying (%d/%d)",
                resp.status_code, _retry + 1, self._config.http_max_retries,
            )
            return await self._send(method, path, **again, _retry=_retry + 1)

        if resp.status_code >= 400:
            self._raise_for_status(resp)
        return resp

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        """Raise a typed exception based on status code.

        Prefers the human-readable ``message`` over the machine ``error`` code.
        """
        try:
            data = resp.json()
        except Exception:
            data = {"message": resp.text or "Unknown error"}
        if not isinstance(data, dict):
            data = {"message": str(data)}

        message = data.get("message") or data.get("error") or data.get("msg") or str(data)
        status = resp.status_code

        if status == 400:
            raise ValidationError(message, status_code=status, detail=data)
        elif status in (401, 403):
            raise AuthenticationError(message, status_code=status, detail=data)
        elif status == 404:
            raise NotFoundError(message, status_code=status, detail=data)
        elif status >= 500:
            raise ServerError(message, status_code=status, detail=data)
        else:
            raise SheetStormAPIError(message, status_code=status, detail=data)
