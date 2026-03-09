"""Authentication & session management tools.

With the OAuth 2.0 flow, login is handled automatically via the browser.
These tools let the user inspect their session and perform logout/revocation.
"""

from __future__ import annotations

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


@mcp.tool()
async def sheetstorm_get_current_user() -> str:
    """Get the currently authenticated user's profile information."""
    client = get_client()
    try:
        user = await client.get("/auth/me")
        return (
            f"User: {user.get('first_name', '')} {user.get('last_name', '')}\n"
            f"Email: {user.get('email', 'N/A')}\n"
            f"Role: {user.get('role', 'N/A')}\n"
            f"Organization: {user.get('organization_name', 'N/A')}\n"
            f"MFA Enabled: {user.get('mfa_enabled', False)}\n"
            f"Permissions: {', '.join(user.get('permissions', []))}"
        )
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_logout() -> str:
    """End the current SheetStorm session."""
    client = get_client()
    try:
        await client.logout()
        return "✓ Logged out successfully."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
