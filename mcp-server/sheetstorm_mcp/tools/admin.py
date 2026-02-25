"""Admin tools — user management, notifications, audit logs, health check."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------

def _format_user(u: dict) -> str:
    return (
        f"**{u.get('name', u.get('username', 'Unknown'))}** (ID: {u.get('id', 'N/A')})\n"
        f"  Email: {u.get('email', 'N/A')} | Role: {u.get('role', 'N/A')}\n"
        f"  Active: {'Yes' if u.get('is_active', True) else 'No'} | "
        f"MFA: {'Enabled' if u.get('mfa_enabled') else 'Disabled'}"
    )


@mcp.tool()
async def sheetstorm_list_users(page: int = 1, per_page: int = 20) -> str:
    """List all users in the organization.

    Args:
        page: Page number (default 1)
        per_page: Items per page (default 20)
    """
    client = get_client()
    try:
        data = await client.get("/users", params={"page": page, "per_page": per_page})
        items = data.get("items", data.get("users", []))
        total = data.get("total", len(items))

        if not items:
            return "No users found."

        lines = [f"**Users** (page {page}, {total} total)\n"]
        for u in items:
            lines.append(_format_user(u))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_create_user(
    email: str,
    name: str,
    password: str,
    role: str = "analyst",
) -> str:
    """Create a new user.

    Args:
        email: User email address
        name: Display name
        password: Initial password
        role: Role (admin, manager, analyst, viewer)
    """
    client = get_client()
    try:
        user = await client.post(
            "/users",
            json={"email": email, "name": name, "password": password, "role": role},
        )
        return f"✓ User created:\n{_format_user(user)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_user(
    user_id: str,
    email: Optional[str] = None,
    name: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> str:
    """Update a user's details.

    Args:
        user_id: UUID of the user
        email: New email
        name: New name
        role: New role
        is_active: Activate/deactivate user
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, val in [
            ("email", email),
            ("name", name),
            ("role", role),
            ("is_active", is_active),
        ]:
            if val is not None:
                payload[field] = val
        if not payload:
            return "No fields to update."

        user = await client.put(f"/users/{user_id}", json=payload)
        return f"✓ User updated:\n{_format_user(user)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_delete_user(user_id: str) -> str:
    """Delete a user (soft-delete).

    Args:
        user_id: UUID of the user to delete
    """
    client = get_client()
    try:
        await client.delete(f"/users/{user_id}")
        return f"✓ User {user_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_list_notifications(unread_only: bool = False) -> str:
    """List notifications for the current user.

    Args:
        unread_only: Only show unread notifications
    """
    client = get_client()
    try:
        params: dict = {}
        if unread_only:
            params["unread"] = True
        data = await client.get("/notifications", params=params)
        items = data if isinstance(data, list) else data.get("items", data.get("notifications", []))

        if not items:
            return "No notifications."

        lines = [f"**Notifications** ({len(items)})\n"]
        for n in items:
            read_marker = "  " if n.get("read") or n.get("is_read") else "● "
            lines.append(
                f"{read_marker}[{n.get('created_at', 'N/A')}] "
                f"**{n.get('title', n.get('type', 'Notification'))}**\n"
                f"    {n.get('message', n.get('body', 'N/A'))} "
                f"(ID: {n.get('id', 'N/A')})"
            )
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_mark_notification_read(notification_id: str) -> str:
    """Mark a notification as read.

    Args:
        notification_id: UUID of the notification
    """
    client = get_client()
    try:
        await client.put(f"/notifications/{notification_id}/read")
        return f"✓ Notification {notification_id} marked as read."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_mark_all_notifications_read() -> str:
    """Mark all notifications as read."""
    client = get_client()
    try:
        await client.post("/notifications/mark-all-read")
        return "✓ All notifications marked as read."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_get_audit_logs(
    page: int = 1,
    per_page: int = 20,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
) -> str:
    """Get audit logs. Requires admin permissions.

    Args:
        page: Page number
        per_page: Items per page
        user_id: Filter by user UUID
        action: Filter by action type
    """
    client = get_client()
    try:
        params: dict = {"page": page, "per_page": per_page}
        if user_id:
            params["user_id"] = user_id
        if action:
            params["action"] = action

        data = await client.get("/audit-logs", params=params)
        items = data.get("items", data.get("logs", []))
        total = data.get("total", len(items))

        if not items:
            return "No audit logs found."

        lines = [f"**Audit Logs** (page {page}, {total} total)\n"]
        for log in items:
            lines.append(
                f"[{log.get('created_at', log.get('timestamp', 'N/A'))}] "
                f"**{log.get('action', 'N/A')}** by {log.get('user_name', log.get('user_id', 'Unknown'))}\n"
                f"  Resource: {log.get('resource_type', 'N/A')} / {log.get('resource_id', 'N/A')}\n"
                f"  Details: {log.get('details', 'N/A')}"
            )
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_health_check() -> str:
    """Check the SheetStorm API health status."""
    client = get_client()
    try:
        data = await client.get("/health")
        status = data.get("status", "unknown")
        parts = [f"**API Health**: {status}"]
        if data.get("version"):
            parts.append(f"  Version: {data['version']}")
        if data.get("database"):
            parts.append(f"  Database: {data['database']}")
        if data.get("redis"):
            parts.append(f"  Redis: {data['redis']}")
        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
    except Exception as exc:
        return f"✗ API unreachable: {exc}"
