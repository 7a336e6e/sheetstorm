"""Async HTTP client for the SheetStorm backend API.

Simplified version for the local bridge — no OAuth, no ContextVars.
Handles authentication, token refresh (with refresh-token rotation), retries,
and typed errors.

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
import logging
import time
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any

import httpx

from sheetstorm_bridge.config import Config

logger = logging.getLogger("sheetstorm_bridge.client")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SheetStormAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class AuthenticationError(SheetStormAPIError):
    pass


class NotFoundError(SheetStormAPIError):
    pass


class ValidationError(SheetStormAPIError):
    pass


class ServerError(SheetStormAPIError):
    pass


# Re-exchange an API key this many seconds before its token expires.
API_KEY_REFRESH_MARGIN = 60


def api_key_prefix(key: str | None) -> str:
    """The public part of an API key (`ssk_<lookup>`), safe to log."""
    if key and key.startswith("ssk_") and len(key) > 16:
        return key[:16]
    return "ssk_…"


def no_cookie_jar() -> CookieJar:
    """Cookie jar that never stores or sends cookies (auth is header-only)."""
    return CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class SheetStormClient:
    """Async HTTP client wrapping the SheetStorm REST API."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._base_url = config.api_url.rstrip("/")
        # Precedence: api_key > api_token > username/password.
        self._api_key: str | None = config.api_key or None
        self._access_token: str | None = None if self._api_key else (config.api_token or None)
        self._refresh_token: str | None = None
        self._token_expires_at: float | None = None  # monotonic; API-key tokens only
        self._exchange_lock = asyncio.Lock()
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(config.http_timeout),
            follow_redirects=True,
            cookies=no_cookie_jar(),
            # Informational: the backend snapshots it into custody ledger entries.
            headers={"X-SheetStorm-Client": "mcp-bridge"},
        )

    async def close(self) -> None:
        await self._http.aclose()

    # -- auth ----------------------------------------------------------------

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    async def login(self, username: str, password: str) -> dict:
        payload: dict[str, Any] = {"email": username, "password": password}
        resp = await self._http.post("/auth/login", json=payload)
        data = resp.json()

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
        """Refresh the access token. The backend rotates refresh tokens: the
        presented one is revoked, so the new one MUST be stored."""
        if not self._refresh_token:
            raise AuthenticationError("No refresh token available", status_code=401)
        resp = await self._http.post(
            "/auth/refresh",
            headers={"Authorization": f"Bearer {self._refresh_token}"},
        )
        if resp.status_code >= 400:
            self._access_token = None
            self._refresh_token = None
            raise AuthenticationError("Token refresh failed", status_code=resp.status_code)
        data = resp.json()
        if not data.get("access_token"):
            self._access_token = None
            self._refresh_token = None
            raise AuthenticationError("Token refresh returned no access token", status_code=resp.status_code)
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token") or None

    async def logout(self) -> dict:
        """Log out, revoking both the access and the refresh token.

        With an API key this only revokes the current short-lived token (the
        next call exchanges the key again); revoke the key itself in the UI."""
        body = {"refresh_token": self._refresh_token} if self._refresh_token else None
        try:
            return await self._request("POST", "/auth/logout", json=body, _retry=1)
        finally:
            self._access_token = None
            self._refresh_token = None
            self._token_expires_at = None

    async def ensure_authenticated(self) -> None:
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
                "Not authenticated. Set SHEETSTORM_API_KEY (recommended), SHEETSTORM_API_TOKEN "
                "or SHEETSTORM_USERNAME/SHEETSTORM_PASSWORD in .env",
                status_code=401,
            )

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
        resp = await self._send("GET", path)
        return resp.content

    # -- internal ------------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = await self._send(method, path, **kwargs)
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
        await self.ensure_authenticated()

        token = self._access_token
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

        # auto-refresh (or re-login) on 401, once
        if resp.status_code == 401 and _retry == 0:
            if self._api_key:
                # Re-exchange once; a rejected key raises (no retry loop).
                await self._ensure_api_key_token(failed_token=token)
                return await self._send(method, path, **again, _retry=1)
            try:
                if self._refresh_token:
                    await self.refresh()
                else:
                    self._access_token = None
                    await self.ensure_authenticated()
                return await self._send(method, path, **again, _retry=1)
            except AuthenticationError:
                logger.debug("Re-authentication after 401 failed")

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
        """Raise a typed exception; prefers the human-readable ``message``."""
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
