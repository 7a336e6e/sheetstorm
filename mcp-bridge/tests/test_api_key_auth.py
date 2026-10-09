"""API-key authentication of the client (api-keys plan §3.8 / §6)."""

from __future__ import annotations

import importlib
import logging
import time

import pytest
from conftest import PKG

client_mod = importlib.import_module(f"{PKG}.client")
config_mod = importlib.import_module(f"{PKG}.config")

# A syntactically valid, obviously fake key (test-only).
SECRET = "S" * 43
KEY = "ssk_" + "a" * 12 + "_" + SECRET
PREFIX = KEY[:16]


def _token_calls(backend):
    return [c for c in backend.calls if c["path"] == "/auth/token"]


def _tokens(*values, expires_in=900):
    """Dynamic /auth/token response handing out `values` in order."""
    it = iter(values)

    def respond(_req):
        return 200, {"access_token": next(it), "token_type": "Bearer", "expires_in": expires_in}
    return respond


async def test_api_key_mode_exchanges_on_first_call_only(make_client, backend):
    c = make_client("stdio", SHEETSTORM_API_KEY=KEY)
    backend.set("POST", "/auth/token", _tokens("acc-1"))
    backend.set("GET", "/auth/me", {"name": "bot"})
    await c.get("/auth/me")
    await c.get("/auth/me")
    calls = _token_calls(backend)
    assert len(calls) == 1
    assert calls[0]["json"] == {"api_key": KEY} and calls[0]["auth"] is None
    assert [x["auth"] for x in backend.calls if x["path"] == "/auth/me"] == ["Bearer acc-1"] * 2


async def test_401_re_exchanges_exactly_once(make_client, backend):
    c = make_client("stdio", SHEETSTORM_API_KEY=KEY)
    backend.set("POST", "/auth/token", _tokens("acc-1", "acc-2"))
    backend.set("GET", "/auth/me", lambda req: (
        (401, {"error": "token_revoked"}) if req.headers["authorization"] == "Bearer acc-1"
        else (200, {"name": "bot"})))
    assert (await c.get("/auth/me"))["name"] == "bot"
    assert len(_token_calls(backend)) == 2
    assert not backend.find("POST", "/auth/refresh") and not backend.find("POST", "/auth/login")


async def test_persistent_401_does_not_loop(make_client, backend):
    c = make_client("stdio", SHEETSTORM_API_KEY=KEY)
    backend.set("POST", "/auth/token", _tokens("acc-1", "acc-2", "acc-3"))
    backend.set("GET", "/auth/me", {"error": "forbidden", "message": "nope"}, status=401)
    with pytest.raises(client_mod.AuthenticationError):
        await c.get("/auth/me")
    assert len(_token_calls(backend)) == 2


async def test_proactive_re_exchange_near_expiry(make_client, backend):
    c = make_client("stdio", SHEETSTORM_API_KEY=KEY)
    backend.set("POST", "/auth/token", _tokens("acc-1", "acc-2"))
    await c.get("/auth/me")
    c._token_expires_at = time.monotonic() + client_mod.API_KEY_REFRESH_MARGIN - 1
    await c.get("/auth/me")
    assert len(_token_calls(backend)) == 2
    assert backend.calls[-1]["auth"] == "Bearer acc-2"


async def test_rejected_key_raises_clear_error_without_retry(make_client, backend, caplog):
    caplog.set_level(logging.DEBUG)
    c = make_client("stdio", SHEETSTORM_API_KEY=KEY)
    backend.set("POST", "/auth/token", {"error": "invalid_api_key", "message": "Invalid API key"}, status=401)
    with pytest.raises(client_mod.AuthenticationError) as exc:
        await c.get("/auth/me")
    assert "rejected (revoked, expired or disabled)" in str(exc.value)
    assert PREFIX in str(exc.value) and SECRET not in str(exc.value)
    assert len(_token_calls(backend)) == 1
    assert not backend.find("GET", "/auth/me")


async def test_key_never_logged(make_client, backend, caplog):
    caplog.set_level(logging.DEBUG)
    c = make_client("stdio", SHEETSTORM_API_KEY=KEY)
    backend.set("POST", "/auth/token", _tokens("acc-1", "acc-2"))
    backend.set("GET", "/auth/me", lambda req: (
        (401, {}) if req.headers["authorization"] == "Bearer acc-1" else (200, {})))
    await c.get("/auth/me")
    await c.logout()
    assert caplog.records
    for rec in caplog.records:
        assert SECRET not in rec.getMessage()
    assert SECRET not in repr(config_mod.Config())


async def test_logout_drops_token_and_next_call_exchanges_again(make_client, backend):
    c = make_client("stdio", SHEETSTORM_API_KEY=KEY)
    backend.set("POST", "/auth/token", _tokens("acc-1", "acc-2"))
    await c.get("/auth/me")
    await c.logout()
    assert backend.find("POST", "/auth/logout")["auth"] == "Bearer acc-1"
    assert c._access_token is None
    await c.get("/auth/me")
    assert backend.calls[-1]["auth"] == "Bearer acc-2"


def test_precedence_api_key_over_token_over_password(make_client, monkeypatch):
    monkeypatch.setenv("SHEETSTORM_API_KEY", KEY)
    monkeypatch.setenv("SHEETSTORM_API_TOKEN", "static")
    monkeypatch.setenv("SHEETSTORM_USERNAME", "u@x")
    monkeypatch.setenv("SHEETSTORM_PASSWORD", "pw")
    assert config_mod.Config().auth_mode == "api_key"
    monkeypatch.setenv("SHEETSTORM_API_KEY", "")
    assert config_mod.Config().auth_mode == "api_token"
    monkeypatch.setenv("SHEETSTORM_API_TOKEN", "")
    assert config_mod.Config().auth_mode == "password"

    c = make_client("stdio", SHEETSTORM_API_KEY=KEY, SHEETSTORM_API_TOKEN="static")
    assert c.uses_api_key and c._access_token is None


async def test_static_token_still_works_without_api_key(make_client, backend):
    c = make_client("stdio", SHEETSTORM_API_KEY="", SHEETSTORM_API_TOKEN="static-token")
    await c.get("/auth/me")
    assert not _token_calls(backend) and backend.calls[-1]["auth"] == "Bearer static-token"
