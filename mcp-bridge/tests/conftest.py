"""Shared fixtures: a mocked SheetStorm backend (respx) and a client bound to it."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl

# Deterministic environment BEFORE the package is imported (config is read at
# import time and python-dotenv never overrides variables that are already set).
os.environ.update({
    "SHEETSTORM_API_URL": "http://backend.test/api/v1",
    "MCP_TRANSPORT": "stdio",
    "SHEETSTORM_API_TOKEN": "static-token",
    "SHEETSTORM_USERNAME": "",
    "SHEETSTORM_PASSWORD": "",
    "REDIS_URL": "",
    "MCP_ALLOWED_REDIRECT_HOSTS": "",
    "MCP_ISSUER_URL": "http://mcp.test",
    "HTTP_MAX_RETRIES": "0",
    "LOG_LEVEL": "WARNING",
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402

PKG = "sheetstorm_bridge"
API = "http://backend.test/api/v1"


class Backend:
    """Records every request; responses come from ``responses`` or a default."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.responses: dict[tuple[str, str], object] = {}

    def set(self, method: str, path: str, body: object = None, status: int = 200) -> None:
        self.responses[(method, path)] = (status, body)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        ctype = request.headers.get("content-type", "")
        body: object = None
        if request.content and ctype.startswith("application/json"):
            body = json.loads(request.content)
        elif request.content and ctype.startswith("multipart/form-data"):
            body = request.content
        self.calls.append({
            "method": request.method,
            "path": path,
            "params": dict(parse_qsl(request.url.query.decode())),
            "json": body,
            "auth": request.headers.get("authorization"),
            "cookie": request.headers.get("cookie"),
        })
        status, resp = self.responses.get(
            (request.method, path),
            (200, {"items": [], "total": 0, "pages": 1, "id": "obj-1"}),
        )
        if callable(resp):  # dynamic response: fn(request) -> (status, body)
            status, resp = resp(request)
        if isinstance(resp, (bytes, str)):
            return httpx.Response(status, content=resp)
        return httpx.Response(status, json=resp)

    def find(self, method: str, path: str) -> dict | None:
        for c in self.calls:
            if c["method"] == method and c["path"] == path:
                return c
        return None


@pytest.fixture
def backend():
    be = Backend()
    with respx.mock(assert_all_called=False) as router:
        router.route(host="backend.test").mock(side_effect=be.handler)
        yield be


@pytest.fixture
def pkg():
    import importlib

    return importlib.import_module(f"{PKG}.server")


@pytest.fixture
def make_client(monkeypatch, pkg):
    """Create a client for the given transport and install it as the shared client."""
    import importlib

    client_mod = importlib.import_module(f"{PKG}.client")
    config_mod = importlib.import_module(f"{PKG}.config")
    made = []

    def _make(transport: str = "stdio", **env: str):
        monkeypatch.setenv("MCP_TRANSPORT", transport)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        c = client_mod.SheetStormClient(config_mod.Config())
        monkeypatch.setattr(pkg, "_client", c)
        made.append(c)
        return c

    return _make


@pytest.fixture
def client(make_client, backend):
    return make_client("stdio")
