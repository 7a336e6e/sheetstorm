"""Starlette routes for the SheetStorm login page and form submission.

These are mounted alongside the MCP SDK's built-in OAuth routes to handle
the ``/sheetstorm-login`` endpoint that users are redirected to during the
OAuth authorization flow.
"""

from __future__ import annotations

import html
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

if TYPE_CHECKING:
    from sheetstorm_mcp.oauth_provider import SheetStormOAuthProvider

logger = logging.getLogger("sheetstorm_mcp.login_routes")

# ---------------------------------------------------------------------------
# Login page HTML (inline to avoid template dependencies)
# ---------------------------------------------------------------------------

_LOGIN_PAGE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SheetStorm — Sign In</title>
<style>
  :root {{
    --bg: #0c0e14;
    --card: rgba(255,255,255,0.04);
    --border: rgba(255,255,255,0.08);
    --accent: #6366f1;
    --accent-hover: #818cf8;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --danger: #ef4444;
    --input-bg: rgba(255,255,255,0.06);
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 2.5rem;
    width: 100%;
    max-width: 420px;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
  }}
  .logo {{
    text-align: center;
    margin-bottom: 1.5rem;
  }}
  .logo h1 {{
    font-size: 1.5rem;
    font-weight: 600;
    background: linear-gradient(135deg, #6366f1, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }}
  .logo p {{
    color: var(--muted);
    font-size: 0.85rem;
    margin-top: 0.25rem;
  }}
  .error {{
    background: rgba(239,68,68,0.1);
    border: 1px solid rgba(239,68,68,0.3);
    color: var(--danger);
    padding: 0.75rem 1rem;
    border-radius: 8px;
    font-size: 0.85rem;
    margin-bottom: 1rem;
  }}
  label {{
    display: block;
    font-size: 0.8rem;
    color: var(--muted);
    margin-bottom: 0.35rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  input[type="email"],
  input[type="password"],
  input[type="text"] {{
    width: 100%;
    padding: 0.7rem 1rem;
    background: var(--input-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-size: 0.95rem;
    outline: none;
    transition: border-color 0.2s;
    margin-bottom: 1rem;
  }}
  input:focus {{
    border-color: var(--accent);
  }}
  button {{
    width: 100%;
    padding: 0.75rem;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
  }}
  button:hover {{
    background: var(--accent-hover);
  }}
  .consent {{
    background: rgba(99,102,241,0.08);
    border: 1px solid rgba(99,102,241,0.3);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    font-size: 0.85rem;
    margin-bottom: 1rem;
    line-height: 1.5;
    word-break: break-all;
  }}
  .consent strong {{ color: #fff; }}
  .consent-check {{
    display: flex;
    gap: 0.5rem;
    align-items: flex-start;
    font-size: 0.8rem;
    color: var(--text);
    text-transform: none;
    letter-spacing: 0;
    margin-bottom: 1rem;
  }}
  .footer {{
    text-align: center;
    margin-top: 1.25rem;
    font-size: 0.75rem;
    color: var(--muted);
  }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <h1>SheetStorm</h1>
    <p>Sign in to connect your AI assistant</p>
  </div>
  {error_block}
  {consent_block}
  <form method="POST" action="/sheetstorm-login">
    <input type="hidden" name="pid" value="{pid}">
    <label for="email">Email</label>
    <input type="email" id="email" name="email" required autofocus
           placeholder="you@example.com" value="{email}">
    <label for="password">Password</label>
    <input type="password" id="password" name="password" required
           placeholder="Enter your password">
    {mfa_block}
    <label class="consent-check" for="consent">
      <input type="checkbox" id="consent" name="consent" value="yes" required>
      <span>I recognise this application and allow it to act on SheetStorm as me.</span>
    </label>
    <button type="submit">Sign In &amp; Allow</button>
  </form>
  <div class="footer">
    Your credentials are sent directly to the SheetStorm server.<br>
    They are not stored by the MCP server.
  </div>
</div>
</body>
</html>
"""

_MFA_FIELD = """\
    <label for="mfa_code">MFA Code</label>
    <input type="text" id="mfa_code" name="mfa_code"
           placeholder="6-digit code" autocomplete="one-time-code"
           pattern="[0-9]{6}" inputmode="numeric">
"""


def _redirect_host(redirect_uri: str) -> str:
    try:
        parsed = urlparse(redirect_uri)
    except ValueError:
        return "(invalid)"
    host = parsed.hostname or "(unknown)"
    return f"{host}:{parsed.port}" if parsed.port else host


def _render_login(
    pid: str,
    error: str | None = None,
    email: str = "",
    show_mfa: bool = False,
    client_name: str | None = None,
    redirect_uri: str | None = None,
) -> str:
    # Escape every interpolated value — pid/email/client name are reflected
    # into HTML and error into element text. Without escaping, a crafted value
    # breaks out and executes script on the MCP origin.
    safe_pid = html.escape(pid, quote=True)
    safe_email = html.escape(email, quote=True)
    error_block = f'<div class="error">{html.escape(error)}</div>' if error else ""
    mfa_block = _MFA_FIELD if show_mfa else ""
    consent_block = ""
    if redirect_uri is not None:
        name = html.escape(client_name or "Unnamed MCP client")
        host = html.escape(_redirect_host(redirect_uri))
        consent_block = (
            '<div class="consent">'
            f'<strong>{name}</strong> is requesting access to your SheetStorm account.<br>'
            f'After sign-in you will be sent back to <strong>{host}</strong>.<br>'
            'Only continue if you started this connection yourself.'
            '</div>'
        )
    return _LOGIN_PAGE_HTML.format(
        pid=safe_pid,
        error_block=error_block,
        consent_block=consent_block,
        email=safe_email,
        mfa_block=mfa_block,
    )


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


_NO_STORE = {"Cache-Control": "no-store", "X-Frame-Options": "DENY",
             "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
                                        "form-action 'self'; frame-ancestors 'none'"}


def create_login_routes(provider: SheetStormOAuthProvider) -> list[Route]:
    """Return Starlette routes for the login/consent page."""

    def _page(pid: str, pending: dict | None, status: int = 200, **kw) -> HTMLResponse:
        return HTMLResponse(
            _render_login(
                pid=pid,
                client_name=(pending or {}).get("client_name"),
                redirect_uri=(pending or {}).get("redirect_uri"),
                **kw,
            ),
            status_code=status,
            headers=_NO_STORE,
        )

    async def get_login(request: Request) -> Response:
        pid = request.query_params.get("pid", "")
        pending = provider.get_pending_auth(pid)
        if not pending:
            return _page(
                "", None, 400,
                error="Invalid or expired login session. Please try again from your MCP client.",
            )
        return _page(pid, pending)

    async def post_login(request: Request) -> Response:
        form = await request.form()
        pid = str(form.get("pid", ""))
        email = str(form.get("email", ""))
        password = str(form.get("password", ""))
        mfa_code = str(form.get("mfa_code", "")).strip() or None
        consent = str(form.get("consent", "")) == "yes"
        pending = provider.get_pending_auth(pid)

        if not pending:
            return _page(
                "", None, 400,
                error="Invalid or expired login session. Please try again from your MCP client.",
            )
        if not consent:
            return _page(pid, pending, 400, email=email,
                         error="You must confirm that you allow this application to access SheetStorm.")
        if not email or not password:
            return _page(pid, pending, 400, email=email, error="Email and password are required.")

        try:
            redirect_url = await provider.handle_login(pid, email, password, mfa_code)
            return RedirectResponse(url=redirect_url, status_code=302)
        except Exception as exc:
            error_msg = getattr(exc, "error_description", None) or "Sign-in failed."
            show_mfa = "mfa" in error_msg.lower()
            return _page(pid, provider.get_pending_auth(pid), 400,
                         error=error_msg, email=email, show_mfa=show_mfa)

    return [
        Route("/sheetstorm-login", endpoint=get_login, methods=["GET"]),
        Route("/sheetstorm-login", endpoint=post_login, methods=["POST"]),
    ]
