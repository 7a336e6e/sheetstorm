"""Async HTTP client for the SheetStorm backend API.

Simplified version for the local bridge — no OAuth, no ContextVars.
Handles authentication, token refresh (with refresh-token rotation), retries,
and typed errors.
"""

from __future__ import annotations

import logging
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
        self._access_token: str | None = config.api_token or None
        self._refresh_token: str | None = None
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
        """Log out, revoking both the access and the refresh token."""
        body = {"refresh_token": self._refresh_token} if self._refresh_token else None
        try:
            return await self._request("POST", "/auth/logout", json=body, _retry=1)
        finally:
            self._access_token = None
            self._refresh_token = None

    async def ensure_authenticated(self) -> None:
        if self.is_authenticated:
            return
        cfg = self._config
        if cfg.username and cfg.password:
            await self.login(cfg.username, cfg.password)
        else:
            raise AuthenticationError(
                "Not authenticated. Set SHEETSTORM_USERNAME/SHEETSTORM_PASSWORD or SHEETSTORM_API_TOKEN in .env",
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

        headers: dict[str, str] = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

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
