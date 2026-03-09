# MCP SDK v1.26.0 — Authentication Research

> Researched from SDK source installed in `sheetstorm-mcp` container at  
> `/usr/local/lib/python3.12/site-packages/mcp/server/auth/`

---

## 1. Full Interface: `OAuthAuthorizationServerProvider`

This is a `Protocol` (structural typing) — you don't subclass it, you just implement the methods.  
Generic over `[AuthorizationCodeT, RefreshTokenT, AccessTokenT]`, all must extend the base Pydantic models.

```python
from mcp.server.auth.provider import (
    OAuthAuthorizationServerProvider,
    AuthorizationCode,    # code, scopes, expires_at, client_id, code_challenge, redirect_uri, resource
    RefreshToken,         # token, client_id, scopes, expires_at
    AccessToken,          # token, client_id, scopes, expires_at, resource
    AuthorizationParams,  # state, scopes, code_challenge, redirect_uri, redirect_uri_provided_explicitly, resource
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


class OAuthAuthorizationServerProvider(Protocol, Generic[AuthorizationCodeT, RefreshTokenT, AccessTokenT]):

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Retrieve client info by ID. MAY raise NotImplementedError if dynamic registration disabled."""

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Save client info during registration. MAY raise NotImplementedError."""

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """
        Return a URL to redirect the user to for authorization.
        Called by the /authorize endpoint.
        Common pattern: redirect to a 3rd-party OAuth provider, then
        redirect back to params.redirect_uri with an auth code.
        """

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCodeT | None:
        """Load an authorization code by its string value."""

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCodeT
    ) -> OAuthToken:
        """Exchange an auth code for access + refresh tokens."""

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshTokenT | None:
        """Load a refresh token by its string value."""

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshTokenT, scopes: list[str]
    ) -> OAuthToken:
        """Exchange refresh token for new access + refresh tokens. SHOULD rotate both."""

    async def load_access_token(self, token: str) -> AccessTokenT | None:
        """Validate/load an access token. Called on every authenticated request."""

    async def revoke_token(self, token: AccessTokenT | RefreshTokenT) -> None:
        """Revoke a token. SHOULD revoke both access and refresh together."""
```

**This is HEAVY.** It implements a full OAuth 2.0 Authorization Server. You'd need to:
- Manage client registrations
- Implement PKCE authorization flow
- Issue/store/validate access tokens, refresh tokens, authorization codes
- Handle token rotation and revocation

---

## 2. Full Interface: `TokenVerifier`

```python
from mcp.server.auth.provider import TokenVerifier, AccessToken

class TokenVerifier(Protocol):
    """Protocol for verifying bearer tokens."""

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify a bearer token and return access info if valid."""
```

Where `AccessToken` is:
```python
class AccessToken(BaseModel):
    token: str
    client_id: str
    scopes: list[str]
    expires_at: int | None = None
    resource: str | None = None  # RFC 8707 resource indicator
```

**This is SIMPLE.** Just one async method. Return `AccessToken` if valid, `None` if invalid.

---

## 3. Two Auth Modes: `auth_server_provider` vs `token_verifier`

The SDK supports two mutually exclusive auth configuration patterns:

### Mode A: Full OAuth Authorization Server (`auth_server_provider`)
```python
mcp = FastMCP(
    "my-server",
    auth_server_provider=MyOAuthProvider(),  # Implements OAuthAuthorizationServerProvider
    auth=AuthSettings(
        issuer_url="https://my-server.com",
        resource_server_url="https://my-server.com",
        client_registration_options=ClientRegistrationOptions(enabled=True),
    ),
)
```

This registers OAuth endpoints: `/.well-known/oauth-authorization-server`, `/authorize`, `/token`, `/register`, `/revoke`.

The SDK auto-creates a `ProviderTokenVerifier` that delegates `verify_token()` → `provider.load_access_token()`.

### Mode B: Token Verifier Only (`token_verifier`) — RECOMMENDED FOR US
```python
mcp = FastMCP(
    "my-server",
    token_verifier=MyTokenVerifier(),  # Implements TokenVerifier
    auth=AuthSettings(
        issuer_url="https://backend.example.com",          # The Flask backend
        resource_server_url="https://mcp.example.com",     # This MCP server
    ),
)
```

This does NOT register OAuth endpoints. It only validates bearer tokens on incoming requests using the `TokenVerifier`. The actual OAuth/auth flow is handled by an external server (the `issuer_url`).

**Key validation rule in FastMCP.__init__:**
- `auth` + both `auth_server_provider` and `token_verifier` → Error
- `auth` + neither → Error
- No `auth` + either provider → Error
- `auth` + exactly one of them → OK

---

## 4. How Auth Middleware is Assembled (Same for SSE and Streamable-HTTP)

Both `sse_app()` and `streamable_http_app()` use **identical** auth wiring:

```python
# Middleware stack (applied to ALL routes):
middleware = [
    Middleware(AuthenticationMiddleware, backend=BearerAuthBackend(token_verifier)),
    Middleware(AuthContextMiddleware),
]

# MCP endpoint wrapped with RequireAuthMiddleware:
Route("/mcp", endpoint=RequireAuthMiddleware(streamable_http_app, required_scopes, resource_metadata_url))
```

**Execution order per request:**
1. `AuthenticationMiddleware` (Starlette built-in) → calls `BearerAuthBackend.authenticate()`
   - Extracts `Authorization: Bearer <token>` header
   - Calls `token_verifier.verify_token(token)`
   - Returns `(AuthCredentials(scopes), AuthenticatedUser(access_token))`
   - Sets `scope["user"]` and `scope["auth"]` on the ASGI scope

2. `AuthContextMiddleware` → copies `AuthenticatedUser` into a `contextvars.ContextVar`
   - Enables `get_access_token()` from anywhere in the async call stack (including tool handlers)

3. `RequireAuthMiddleware` → checks `scope["user"]` is `AuthenticatedUser` and has required scopes
   - Returns 401 if not authenticated, 403 if missing scopes

**SSE vs Streamable-HTTP: No difference in auth handling.** The middleware stack is identical.

---

## 5. Feasibility: Custom `TokenVerifier` Delegating to Flask JWT Backend

**YES — this is the simplest and recommended approach.**

The `TokenVerifier` protocol has exactly ONE method. We can implement it to proxy verification to the SheetStorm Flask backend:

```python
import httpx
from mcp.server.auth.provider import TokenVerifier, AccessToken


class SheetStormTokenVerifier:
    """
    Verifies MCP bearer tokens by proxying to the SheetStorm Flask backend.
    The token IS the Flask JWT — we just forward it for validation.
    """
    
    def __init__(self, backend_url: str = "http://backend:5000"):
        self.backend_url = backend_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self.backend_url, timeout=10.0)
    
    async def verify_token(self, token: str) -> AccessToken | None:
        """
        Verify token by calling the Flask backend's /api/v1/auth/me endpoint.
        If the token is valid, the backend returns the user profile.
        """
        try:
            resp = await self._http.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code != 200:
                return None
            
            user_data = resp.json()
            
            # Map Flask user to MCP AccessToken
            # Build scopes from the user's RBAC permissions
            scopes = user_data.get("permissions", [])
            
            return AccessToken(
                token=token,
                client_id=user_data.get("id", "unknown"),
                scopes=scopes,
                expires_at=None,  # JWT expiry is handled by the Flask backend
            )
        except Exception:
            return None
    
    async def close(self):
        await self._http.aclose()
```

### Server Integration

```python
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings

verifier = SheetStormTokenVerifier(backend_url="http://backend:5000")

mcp = FastMCP(
    "sheetstorm-mcp",
    token_verifier=verifier,
    auth=AuthSettings(
        issuer_url="http://backend:5000",          # Flask backend IS the issuer
        resource_server_url="http://mcp-server:8080",  # This MCP server
    ),
    host="0.0.0.0",
    port=8080,
)
```

### Accessing Auth in Tool Handlers

From any tool handler, you can access the authenticated user:

```python
from mcp.server.auth.middleware.auth_context import get_access_token

@mcp.tool()
async def list_incidents() -> str:
    access_token = get_access_token()
    if access_token:
        # access_token.client_id = user ID
        # access_token.token = the raw JWT
        # access_token.scopes = user's permissions
        user_id = access_token.client_id
        jwt = access_token.token
        # Use the JWT to make backend API calls AS this user
    ...
```

---

## 6. Architecture Summary

```
┌─────────────┐     Bearer JWT      ┌──────────────────┐    /api/v1/auth/me    ┌─────────────────┐
│  MCP Client  │ ──────────────────> │  MCP Server      │ ───────────────────> │  Flask Backend   │
│  (Claude,    │                     │  (FastMCP +      │                      │  (SheetStorm)    │
│   Cursor)    │ <────────────────── │   TokenVerifier)  │ <───────────────── │                   │
└─────────────┘   tool responses     └──────────────────┘   user profile +    └─────────────────┘
                                                            permissions
```

**Flow:**
1. User authenticates with Flask backend (login → gets JWT)
2. MCP client sends requests with `Authorization: Bearer <jwt>`
3. MCP `BearerAuthBackend` extracts the JWT, calls `SheetStormTokenVerifier.verify_token(jwt)`
4. Verifier proxies to Flask `GET /api/v1/auth/me` with the JWT
5. Flask validates JWT, returns user profile + permissions
6. Verifier maps that to `AccessToken(client_id=user_id, scopes=permissions)`
7. `AuthContextMiddleware` stores this in a `ContextVar`
8. Tool handlers access it via `get_access_token()` and use the raw JWT for backend API calls

---

## 7. Key Files in SDK

| File | Purpose |
|------|---------|
| `mcp/server/auth/provider.py` | `TokenVerifier`, `AccessToken`, `OAuthAuthorizationServerProvider`, `ProviderTokenVerifier` |
| `mcp/server/auth/settings.py` | `AuthSettings`, `ClientRegistrationOptions`, `RevocationOptions` |
| `mcp/server/auth/middleware/bearer_auth.py` | `BearerAuthBackend`, `RequireAuthMiddleware`, `AuthenticatedUser` |
| `mcp/server/auth/middleware/auth_context.py` | `AuthContextMiddleware`, `get_access_token()`, `auth_context_var` |
| `mcp/server/auth/routes.py` | `create_auth_routes()`, `create_protected_resource_routes()` — only used with `auth_server_provider` |
| `mcp/server/auth/handlers/` | OAuth endpoint handlers (authorize, token, register, revoke, metadata) — only used with `auth_server_provider` |
| `mcp/server/fastmcp/server.py` | `FastMCP.__init__()`, `sse_app()`, `streamable_http_app()` — wires everything together |

---

## 8. Recommendation

**Use `token_verifier` mode (Mode B).** Do NOT implement `OAuthAuthorizationServerProvider`.

Reasons:
1. SheetStorm backend already has JWT auth — no need to duplicate it
2. `TokenVerifier` is 1 method (`verify_token`) vs 9 methods for the full OAuth provider
3. The MCP server acts as a **Resource Server** (RS), not an Authorization Server (AS) — this is the correct RFC 9728 pattern
4. `AuthSettings.issuer_url` correctly points to the Flask backend as the token issuer
5. `AuthSettings.resource_server_url` correctly points to the MCP server itself
6. The SDK auto-serves `/.well-known/oauth-protected-resource` metadata so MCP clients can discover the auth configuration

**Estimated implementation effort:** ~50 lines of code for the verifier + 5 lines to wire it into `FastMCP`.
