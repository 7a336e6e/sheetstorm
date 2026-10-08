"""Authentication & session management tools.

With the OAuth 2.0 flow, login is handled automatically via the browser.
These tools let the user inspect their session and log out.
"""

from __future__ import annotations

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import current_grant, get_client, get_provider, mcp


@mcp.tool()
async def sheetstorm_get_current_user() -> str:
    """Get the currently authenticated user's profile information."""
    client = get_client()
    try:
        user = await client.get("/auth/me")
        roles = user.get('roles', [])
        role_str = ', '.join(roles) if isinstance(roles, list) else str(roles)
        return (
            f"User: {user.get('name', 'N/A')}\n"
            f"Email: {user.get('email', 'N/A')}\n"
            f"Roles: {role_str}\n"
            f"Organization: {user.get('organization_id', 'N/A')}\n"
            f"MFA Enabled: {user.get('mfa_enabled', False)}\n"
            f"Permissions: {', '.join(user.get('permissions', []))}"
        )
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_logout() -> str:
    """End the current SheetStorm session.

    Revokes the backend access and refresh tokens and, on the remote server,
    the MCP OAuth tokens of this connection. The MCP client will have to sign
    in again through the browser before further tool calls succeed.
    """
    client = get_client()
    grant = current_grant()
    error: str | None = None
    try:
        await client.logout()
    except SheetStormAPIError as exc:
        error = str(exc)
    finally:
        if grant is not None:
            get_provider().revoke_grant(grant.grant_id)
    if error and grant is not None:
        return f"✓ MCP session revoked; backend logout reported: {error}"
    if error:
        return f"✗ Error: {error}"
    return "✓ Logged out successfully."
