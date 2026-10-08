from __future__ import annotations

import html
import importlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest

# This test belongs to the MCP server (mcp-server/), whose package is not
# installed in the backend image. Skip here; it should move to mcp-server/tests.
pytest.importorskip("sheetstorm_mcp")


def _load_login_routes(monkeypatch):
    if importlib.util.find_spec("starlette") is None:
        starlette = types.ModuleType("starlette")
        requests = types.ModuleType("starlette.requests")
        responses = types.ModuleType("starlette.responses")
        routing = types.ModuleType("starlette.routing")

        class Request:
            pass

        class Response:
            pass

        class HTMLResponse(Response):
            pass

        class RedirectResponse(Response):
            pass

        class Route:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        requests.Request = Request
        responses.HTMLResponse = HTMLResponse
        responses.RedirectResponse = RedirectResponse
        responses.Response = Response
        routing.Route = Route

        monkeypatch.setitem(sys.modules, "starlette", starlette)
        monkeypatch.setitem(sys.modules, "starlette.requests", requests)
        monkeypatch.setitem(sys.modules, "starlette.responses", responses)
        monkeypatch.setitem(sys.modules, "starlette.routing", routing)

    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(repo_root / "mcp-server"))
    return importlib.import_module("sheetstorm_mcp.login_routes")


def test_render_login_escapes_pid_email_and_error(monkeypatch):
    login_routes = _load_login_routes(monkeypatch)

    malicious_pid = 'pid"><script>alert(1)</script>'
    malicious_email = 'user@example.com" autofocus onfocus="alert(1)'
    malicious_error = '<img src=x onerror="alert(1)"> & "bad"'

    rendered = login_routes._render_login(
        pid=malicious_pid,
        email=malicious_email,
        error=malicious_error,
    )

    assert malicious_pid not in rendered
    assert malicious_email not in rendered
    assert malicious_error not in rendered
    assert html.escape(malicious_pid, quote=True) in rendered
    assert html.escape(malicious_email, quote=True) in rendered
    assert html.escape(malicious_error, quote=True) in rendered
    assert "<script>" not in rendered
    assert "<img" not in rendered
