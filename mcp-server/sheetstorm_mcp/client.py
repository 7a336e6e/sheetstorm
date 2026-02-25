"""Async HTTP client for the SheetStorm backend API.

Handles authentication, token refresh, retries, and typed error propagation.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from sheetstorm_mcp.config import Config

logger = logging.getLogger("sheetstorm_mcp.client")


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


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class SheetStormClient:
    """Async HTTP client wrapping the SheetStorm REST API."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._base_url = config.api_url.rstrip("/")
        self._access_token: str | None = config.api_token
        self._refresh_token: str | None = None
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(config.http_timeout),
            follow_redirects=True,
        )

    # -- lifecycle -----------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    # -- auth ----------------------------------------------------------------

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    async def login(self, username: str, password: str, mfa_code: str | None = None) -> dict:
        """Authenticate and store tokens.

        Returns the login response payload (user info, tokens, etc.).
        Handles MFA challenge (403 with mfa_required flag).
        """
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
                data.get("error", "Login failed"),
                status_code=resp.status_code,
                detail=data,
            )

        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        logger.info("Authenticated as %s", username)
        return data

    async def refresh(self) -> None:
        """Refresh the access token using the stored refresh token."""
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
        self._access_token = data.get("access_token", self._access_token)
        logger.debug("Access token refreshed")

    async def logout(self) -> dict:
        """Logout and clear tokens."""
        try:
            resp = await self._request("POST", "/auth/logout")
            return resp
        finally:
            self._access_token = None
            self._refresh_token = None

    async def ensure_authenticated(self) -> None:
        """Auto-login using configured credentials if not authenticated."""
        if self.is_authenticated:
            return
        cfg = self._config
        if cfg.username and cfg.password:
            await self.login(cfg.username, cfg.password)
        else:
            raise AuthenticationError(
                "Not authenticated. Call login() or set SHEETSTORM_USERNAME/PASSWORD.",
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

    async def upload(self, path: str, file_path: str, field_name: str = "file") -> Any:
        """Upload a file via multipart/form-data."""
        import mimetypes
        from pathlib import Path

        p = Path(file_path)
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        files = {field_name: (p.name, p.read_bytes(), mime)}
        return await self._request("POST", path, files=files)

    async def download(self, path: str) -> bytes:
        """Download binary content."""
        await self.ensure_authenticated()
        headers = {"Authorization": f"Bearer {self._access_token}"}
        resp = await self._http.get(path, headers=headers)
        if resp.status_code >= 400:
            self._raise_for_status(resp)
        return resp.content

    # -- internal ------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        files: dict | None = None,
        _retry: int = 0,
    ) -> Any:
        """Execute an HTTP request with auth headers, retries, and error handling."""
        await self.ensure_authenticated()

        headers: dict[str, str] = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            resp = await self._http.request(
                method,
                path,
                headers=headers,
                json=json,
                params=params,
                files=files,
            )
        except httpx.TransportError as exc:
            if _retry < self._config.http_max_retries:
                logger.warning("Network error, retrying (%d/%d): %s", _retry + 1, self._config.http_max_retries, exc)
                return await self._request(method, path, json=json, params=params, files=files, _retry=_retry + 1)
            raise SheetStormAPIError(f"Network error: {exc}") from exc

        # auto-refresh on 401
        if resp.status_code == 401 and self._refresh_token and _retry == 0:
            logger.debug("Got 401, attempting token refresh")
            try:
                await self.refresh()
                return await self._request(method, path, json=json, params=params, files=files, _retry=1)
            except AuthenticationError:
                pass

        # retry 5xx
        if resp.status_code >= 500 and _retry < self._config.http_max_retries:
            logger.warning("Server error %d, retrying (%d/%d)", resp.status_code, _retry + 1, self._config.http_max_retries)
            return await self._request(method, path, json=json, params=params, files=files, _retry=_retry + 1)

        if resp.status_code >= 400:
            self._raise_for_status(resp)

        # some DELETE endpoints return 204 No Content
        if resp.status_code == 204 or not resp.content:
            return {"success": True}

        return resp.json()

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        """Raise a typed exception based on status code."""
        try:
            data = resp.json()
        except Exception:
            data = {"error": resp.text or "Unknown error"}

        message = data.get("error") or data.get("message") or data.get("msg") or str(data)
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
