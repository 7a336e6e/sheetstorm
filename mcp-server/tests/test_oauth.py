"""OAuth provider: redirect restrictions, consent page, token TTLs/purge, refresh
rotation, revocation, per-request identity and the remote-transport client."""

from __future__ import annotations

import html
import time
from types import SimpleNamespace

import pytest
from mcp.server.auth.provider import AccessToken, AuthorizationParams, RegistrationError, TokenError
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from starlette.applications import Starlette
from starlette.testclient import TestClient

from sheetstorm_mcp import login_routes, oauth_provider, server
from sheetstorm_mcp.client import _request_grant
from sheetstorm_mcp.oauth_provider import SheetStormOAuthProvider, redirect_uri_allowed
from sheetstorm_mcp.tools import auth as auth_tools

API = "http://backend.test/api/v1"


def _client_info(redirect="http://127.0.0.1:33418/cb", name="VS Code", cid="cid-1"):
    return OAuthClientInformationFull(
        client_id=cid, client_name=name, redirect_uris=[AnyUrl(redirect)],
        token_endpoint_auth_method="none", grant_types=["authorization_code", "refresh_token"],
        response_types=["code"], scope="sheetstorm",
    )


def _params(redirect="http://127.0.0.1:33418/cb"):
    return AuthorizationParams(
        state="st", scopes=["sheetstorm"], code_challenge="chal", redirect_uri=AnyUrl(redirect),
        redirect_uri_provided_explicitly=True, resource=None,
    )


@pytest.fixture
def provider():
    return SheetStormOAuthProvider(api_url=API, mcp_issuer_url="http://mcp.test")


async def _login(provider, backend, info=None, email="ann@x", user_id="u-ann", org="o-1",
                 access="acc-1", refresh="ref-1"):
    info = info or _client_info()
    backend.set("POST", "/auth/login", {"access_token": access, "refresh_token": refresh,
                                        "user": {"id": user_id, "organization_id": org, "email": email}})
    url = await provider.authorize(info, _params(str(info.redirect_uris[0])))
    pid = url.split("pid=")[1]
    redirect = await provider.handle_login(pid, email, "pw")
    code = redirect.split("code=")[1].split("&")[0]
    code_obj = await provider.load_authorization_code(info, code)
    return info, await provider.exchange_authorization_code(info, code_obj)


# -- redirect URI restrictions ------------------------------------------------------

@pytest.mark.parametrize("uri,ok", [
    ("http://127.0.0.1:33418/callback", True),
    ("http://localhost:6274/oauth/callback", True),
    ("http://[::1]:8080/cb", True),
    ("https://evil.example/cb", False),
    ("http://claude.ai/cb", False),
    ("https://user:pw@127.0.0.1/cb", False),
    ("javascript:alert(1)", False),
])
def test_redirect_uri_allowed_default(uri, ok):
    assert redirect_uri_allowed(uri, extra_hosts=set()) is ok


def test_redirect_uri_allowlist_env(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_REDIRECT_HOSTS", "claude.ai, vscode.dev")
    assert redirect_uri_allowed("https://claude.ai/api/mcp/auth_callback")
    assert not redirect_uri_allowed("http://claude.ai/api/mcp/auth_callback")  # https only
    assert not redirect_uri_allowed("https://evil.claude.ai.attacker.com/cb")


async def test_register_rejects_non_loopback_redirect(provider):
    with pytest.raises(RegistrationError) as exc:
        await provider.register_client(_client_info("https://phish.example/cb"))
    assert exc.value.error == "invalid_redirect_uri"
    await provider.register_client(_client_info())
    assert await provider.get_client("cid-1") is not None


async def test_authorize_rejects_previously_persisted_bad_redirect(provider):
    from mcp.server.auth.provider import AuthorizeError

    with pytest.raises(AuthorizeError):
        await provider.authorize(_client_info("https://phish.example/cb"), _params("https://phish.example/cb"))


async def test_redis_registration_has_ttl(provider):
    calls = {}

    class FakeRedis:
        def set(self, key, value, ex=None):
            calls["set"] = (key, ex)

        def get(self, key):
            return None

        def close(self):
            pass

    provider._redis = FakeRedis()
    await provider.register_client(_client_info())
    assert calls["set"][1] == oauth_provider.CLIENT_REGISTRATION_TTL


# -- consent / login page ---------------------------------------------------------------

def test_render_login_escapes_pid_email_error_and_client_name():
    malicious_pid = 'pid"><script>alert(1)</script>'
    malicious_email = 'user@example.com" autofocus onfocus="alert(1)'
    malicious_error = '<img src=x onerror="alert(1)"> & "bad"'
    malicious_name = '<script>steal()</script>'
    rendered = login_routes._render_login(
        pid=malicious_pid, email=malicious_email, error=malicious_error,
        client_name=malicious_name, redirect_uri="http://127.0.0.1:9/cb",
    )
    for bad in (malicious_pid, malicious_email, malicious_error, malicious_name):
        assert bad not in rendered
    assert html.escape(malicious_pid, quote=True) in rendered
    assert html.escape(malicious_email, quote=True) in rendered
    assert html.escape(malicious_error, quote=True) in rendered
    assert html.escape(malicious_name) in rendered
    assert "<script>" not in rendered and "<img" not in rendered
    assert 'pattern="[0-9]{6}"' in login_routes._MFA_FIELD


async def test_consent_page_shows_client_and_redirect_host_and_requires_consent(provider, backend):
    info = _client_info("http://127.0.0.1:33418/callback", name="Totally Legit Client")
    url = await provider.authorize(info, _params("http://127.0.0.1:33418/callback"))
    pid = url.split("pid=")[1]
    app = Starlette(routes=login_routes.create_login_routes(provider))
    with TestClient(app) as tc:
        page = tc.get(f"/sheetstorm-login?pid={pid}")
        assert page.status_code == 200
        assert "Totally Legit Client" in page.text and "127.0.0.1:33418" in page.text
        assert 'name="consent"' in page.text and "frame-ancestors 'none'" in page.headers["content-security-policy"]

        no_consent = tc.post("/sheetstorm-login", data={"pid": pid, "email": "a@x", "password": "pw"},
                             follow_redirects=False)
        assert no_consent.status_code == 400 and "must confirm" in no_consent.text
        assert backend.find("POST", "/auth/login") is None  # credentials never forwarded without consent

        backend.set("POST", "/auth/login", {"access_token": "a", "refresh_token": "r", "user": {"id": "u"}})
        ok = tc.post("/sheetstorm-login", data={"pid": pid, "email": "a@x", "password": "pw", "consent": "yes"},
                     follow_redirects=False)
        assert ok.status_code == 302
        assert ok.headers["location"].startswith("http://127.0.0.1:33418/callback?code=")
        assert "state=st" in ok.headers["location"]


async def test_login_error_is_escaped_and_does_not_leak_exceptions(provider, backend):
    info = _client_info()
    url = await provider.authorize(info, _params())
    pid = url.split("pid=")[1]
    backend.set("POST", "/auth/login", {"error": "unauthorized", "message": '<b onmouseover="x">bad</b>'},
                status=401)
    app = Starlette(routes=login_routes.create_login_routes(provider))
    with TestClient(app) as tc:
        r = tc.post("/sheetstorm-login", data={"pid": pid, "email": '"><script>alert(1)</script>',
                                               "password": "nope", "consent": "yes"})
    assert r.status_code == 400
    assert "<script>alert(1)</script>" not in r.text and "<b onmouseover" not in r.text


# -- TTLs / purge -------------------------------------------------------------------------

async def test_pending_auth_and_codes_expire(provider, backend):
    info = _client_info()
    url = await provider.authorize(info, _params())
    pid = url.split("pid=")[1]
    provider._pending_auth[pid]["created_at"] -= oauth_provider.PENDING_AUTH_TTL + 1
    assert provider.get_pending_auth(pid) is None

    info, _ = await _login(provider, backend)
    code = next(iter(provider._auth_codes), None)
    assert code is None  # consumed on exchange
    url = await provider.authorize(info, _params())
    pid = url.split("pid=")[1]
    redirect = await provider.handle_login(pid, "ann@x", "pw")
    code = redirect.split("code=")[1].split("&")[0]
    provider._auth_codes[code].expires_at = time.time() - 1
    assert await provider.load_authorization_code(info, code) is None
    assert code not in provider._auth_codes


async def test_tokens_expire_and_grants_are_purged(provider, backend):
    _, tok = await _login(provider, backend)
    assert provider._refresh_tokens[tok.refresh_token].expires_at > time.time() + 29 * 24 * 3600
    future = time.time() + oauth_provider.REFRESH_TOKEN_TTL + 10
    provider.purge_expired(now=future)
    assert not provider._access_tokens and not provider._refresh_tokens and not provider._grants
    assert await provider.load_access_token(tok.access_token) is None


# -- refresh rotation ----------------------------------------------------------------------

async def test_refresh_stores_rotated_backend_refresh_token(provider, backend):
    info, tok = await _login(provider, backend)
    backend.set("POST", "/auth/refresh", {"access_token": "acc-2", "refresh_token": "ref-2"})
    rt = await provider.load_refresh_token(info, tok.refresh_token)
    tok2 = await provider.exchange_refresh_token(info, rt, [])
    grant = provider.get_grant(tok2.access_token)
    assert grant.sheetstorm_access_token == "acc-2" and grant.sheetstorm_refresh_token == "ref-2"
    assert backend.calls[-1]["auth"] == "Bearer ref-1"
    # old MCP refresh token is single-use
    assert await provider.load_refresh_token(info, tok.refresh_token) is None
    # the second refresh presents the ROTATED backend refresh token
    backend.set("POST", "/auth/refresh", {"access_token": "acc-3", "refresh_token": "ref-3"})
    await provider.exchange_refresh_token(info, await provider.load_refresh_token(info, tok2.refresh_token), [])
    assert backend.calls[-1]["auth"] == "Bearer ref-2"


async def test_backend_refresh_failure_raises_invalid_grant_and_revokes(provider, backend):
    info, tok = await _login(provider, backend)
    backend.set("POST", "/auth/refresh", {"error": "token_revoked"}, status=401)
    rt = await provider.load_refresh_token(info, tok.refresh_token)
    with pytest.raises(TokenError) as exc:
        await provider.exchange_refresh_token(info, rt, [])
    assert exc.value.error == "invalid_grant"
    assert await provider.load_access_token(tok.access_token) is None
    assert not provider._grants


async def test_refresh_only_rotates_own_grant(provider, backend):
    info, tok_a = await _login(provider, backend, email="a@x", user_id="ua")
    _, tok_b = await _login(provider, backend, info=info, email="b@x", user_id="ub", access="acc-b")
    backend.set("POST", "/auth/refresh", {"access_token": "acc-a2", "refresh_token": "ref-a2"})
    await provider.exchange_refresh_token(info, await provider.load_refresh_token(info, tok_a.refresh_token), [])
    assert provider.get_sheetstorm_jwt(tok_b.access_token) == "acc-b"  # other user untouched


async def test_revoke_token_ends_grant(provider, backend):
    info, tok = await _login(provider, backend)
    at = await provider.load_access_token(tok.access_token)
    await provider.revoke_token(at)
    assert await provider.load_refresh_token(info, tok.refresh_token) is None


# -- per-request identity / remote client -------------------------------------------------------

@pytest.fixture
def remote(monkeypatch, make_client, provider, backend, tmp_path):
    c = make_client("sse", ARTIFACT_DIR=str(tmp_path / "artifacts"), SHEETSTORM_API_TOKEN="static-token")
    monkeypatch.setattr(server, "_provider", provider)
    state = {"token": None}
    monkeypatch.setattr(server, "_current_mcp_token", lambda: state["token"])
    return SimpleNamespace(client=c, state=state, provider=provider)


def test_current_mcp_token_comes_from_the_request_scope(monkeypatch):
    user = SimpleNamespace(access_token=AccessToken(token="tok-from-this-request", client_id="c", scopes=[]))
    req = SimpleNamespace(scope={"user": user})
    ctx = SimpleNamespace(request_context=SimpleNamespace(request=req))
    monkeypatch.setattr(server.mcp, "get_context", lambda: ctx)
    assert server._current_mcp_token() == "tok-from-this-request"


async def test_remote_transport_ignores_static_token(remote, backend):
    from sheetstorm_mcp.client import AuthenticationError

    with pytest.raises(AuthenticationError):
        await remote.client.get("/auth/me")
    assert not backend.calls


async def test_tool_uses_current_requests_user_and_refreshes_backend_token(remote, backend):
    info, tok = await _login(remote.provider, backend, access="acc-old", refresh="ref-1")
    remote.state["token"] = tok.access_token
    backend.set("POST", "/auth/refresh", {"access_token": "acc-new", "refresh_token": "ref-2"})
    backend.set("GET", "/auth/me", lambda req: (
        (401, {"error": "token_expired"}) if req.headers["authorization"] == "Bearer acc-old"
        else (200, {"name": "Ann", "roles": [], "permissions": []})))
    out = await auth_tools.sheetstorm_get_current_user()
    assert out.startswith("User: Ann")
    grant = remote.provider.get_grant(tok.access_token)
    assert grant.sheetstorm_access_token == "acc-new" and grant.sheetstorm_refresh_token == "ref-2"


async def test_grant_contextvar_is_reset_between_requests(remote, backend):
    _, tok = await _login(remote.provider, backend)
    remote.state["token"] = tok.access_token
    server.get_client()
    assert _request_grant.get() is not None
    remote.state["token"] = None
    server.get_client()
    assert _request_grant.get() is None


async def test_logout_tool_revokes_backend_and_mcp_tokens(remote, backend):
    info, tok = await _login(remote.provider, backend)
    remote.state["token"] = tok.access_token
    out = await auth_tools.sheetstorm_logout()
    assert out == "✓ Logged out successfully."
    call = backend.find("POST", "/auth/logout")
    assert call["auth"] == "Bearer acc-1" and call["json"] == {"refresh_token": "ref-1"}
    assert await remote.provider.load_access_token(tok.access_token) is None
    assert await remote.provider.load_refresh_token(info, tok.refresh_token) is None
