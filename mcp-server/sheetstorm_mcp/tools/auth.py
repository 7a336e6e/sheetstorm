"""Authentication & session management tools."""

from __future__ import annotations

from sheetstorm_mcp.client import AuthenticationError, SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


@mcp.tool()
async def sheetstorm_login(username: str, password: str, mfa_code: str | None = None) -> str:
    """Authenticate with SheetStorm and establish a session.

    Args:
        username: Email address (e.g. admin@sheetstorm.local)
        password: Account password
        mfa_code: Optional TOTP MFA code if MFA is enabled
    """
    client = get_client()
    try:
        result = client.login(username, password, mfa_code)
        result = await result
        if result.get("mfa_required"):
            return "MFA code required. Please call sheetstorm_login again with the mfa_code parameter."

        user = result.get("user", {})
        return (
            f"✓ Logged in as {user.get('first_name', '')} {user.get('last_name', '')} "
            f"({user.get('email', username)})\n"
            f"Role: {user.get('role', 'N/A')}\n"
            f"Organization: {user.get('organization', 'N/A')}"
        )
    except AuthenticationError as exc:
        return f"✗ Login failed: {exc}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


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
