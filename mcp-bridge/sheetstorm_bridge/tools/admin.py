"""Admin tools — user management, notifications, audit logs, and system health."""

from __future__ import annotations

from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import mcp, get_client


def _format_user(u: dict) -> str:
    return (
        f"**{u.get('name', u.get('username', 'N/A'))}** (ID: {u.get('id', 'N/A')})\n"
        f"  Email: {u.get('email', 'N/A')} | Role: {u.get('role', 'N/A')}\n"
        f"  Active: {'Yes' if u.get('is_active', True) else 'No'} | "
        f"Created: {u.get('created_at', 'N/A')}"
    )


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_list_users(page: int = 1, per_page: int = 50) -> str:
    """List all users (admin only).

    Args:
        page: Page number
        per_page: Items per page
    """
    client = get_client()
    try:
        data = await client.get("/users", params={"page": page, "per_page": per_page})
        items = data if isinstance(data, list) else data.get("items", data.get("users", []))
        total = data.get("total", len(items)) if isinstance(data, dict) else len(items)

        if not items:
            return "No users found."

        lines = [f"**Users** (showing {len(items)} of {total})\n"]
        for u in items:
            lines.append(_format_user(u))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_create_user(
    name: str,
    email: str,
    password: str,
    role: str = "analyst",
) -> str:
    """Create a new user (admin only).

    Args:
        name: Full name
        email: Email address
        password: Password
        role: Role (admin, manager, analyst, viewer)
    """
    client = get_client()
    try:
        user = await client.post(
            "/users",
            json={"name": name, "email": email, "password": password, "role": role},
        )
        return f"✓ User created:\n{_format_user(user)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_user(
    user_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> str:
    """Update a user (admin only).

    Args:
        user_id: UUID of the user
        name: New name
        email: New email
        role: New role
        is_active: Whether the user is active
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, val in [("name", name), ("email", email), ("role", role), ("is_active", is_active)]:
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
    """Delete a user (admin only).

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
    """List your notifications.

    Args:
        unread_only: Only show unread notifications
    """
    client = get_client()
    try:
        params: dict = {}
        if unread_only:
            params["unread"] = "true"
        data = await client.get("/notifications", params=params)
        items = data if isinstance(data, list) else data.get("items", data.get("notifications", []))

        if not items:
            return "No notifications."

        lines = [f"**Notifications** ({len(items)})\n"]
        for n in items:
            read_mark = "○" if not n.get("is_read") else "●"
            lines.append(
                f"{read_mark} [{n.get('created_at', 'N/A')}] "
                f"**{n.get('title', n.get('type', 'Notification'))}** — "
                f"{n.get('message', n.get('body', 'N/A'))} "
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
        await client.patch(f"/notifications/{notification_id}/read")
        return f"✓ Notification {notification_id} marked as read."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_mark_all_notifications_read() -> str:
    """Mark all notifications as read."""
    client = get_client()
    try:
        await client.patch("/notifications/read-all")
        return "✓ All notifications marked as read."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Audit & health
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_get_audit_logs(
    page: int = 1,
    per_page: int = 50,
    action: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    """Get audit logs (admin only).

    Args:
        page: Page number
        per_page: Items per page
        action: Filter by action type
        user_id: Filter by user UUID
    """
    client = get_client()
    try:
        params: dict = {"page": page, "per_page": per_page}
        if action:
            params["action"] = action
        if user_id:
            params["user_id"] = user_id
        data = await client.get("/audit-logs", params=params)
        items = data if isinstance(data, list) else data.get("items", data.get("logs", []))

        if not items:
            return "No audit logs found."

        lines = [f"**Audit Logs** ({len(items)})\n"]
        for log in items:
            lines.append(
                f"[{log.get('created_at', 'N/A')}] "
                f"**{log.get('action', 'N/A')}** by {log.get('user', log.get('user_id', 'N/A'))}\n"
                f"  Resource: {log.get('resource_type', 'N/A')} {log.get('resource_id', '')}\n"
                f"  Details: {log.get('details', 'N/A')}"
            )
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_health_check() -> str:
    """Check SheetStorm system health."""
    client = get_client()
    try:
        data = await client.get("/health")
        status = data.get("status", "unknown")
        parts = [f"**System Health**: {status.upper()}"]
        for key, val in data.items():
            if key != "status":
                parts.append(f"  {key}: {val}")
        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
