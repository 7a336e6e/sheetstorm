"""Authentication & session tools."""

from __future__ import annotations

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import mcp, get_client


@mcp.tool()
async def sheetstorm_get_current_user() -> str:
    """Get the currently authenticated user's profile information."""
    client = get_client()
    try:
        user = await client.get("/auth/me")
        roles = user.get("roles", [])
        role_str = ", ".join(roles) if isinstance(roles, list) else str(roles)
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
    """End the current SheetStorm session."""
    client = get_client()
    try:
        await client.logout()
        return "✓ Logged out successfully."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
