"""Admin tools — user management, notifications, audit logs, health check."""

from __future__ import annotations

from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import get_client, mcp

# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------

def _format_user(u: dict) -> str:
    roles = u.get('roles', [])
    role_str = ', '.join(roles) if isinstance(roles, list) else str(roles)
    return (
        f"**{u.get('name', 'Unknown')}** (ID: {u.get('id', 'N/A')})\n"
        f"  Email: {u.get('email', 'N/A')} | Roles: {role_str}\n"
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


_ROLE_ALIASES = {"admin": "Administrator", "responder": "Incident Responder", "ir": "Incident Responder"}
_SYSTEM_ROLE_NAMES = ["Administrator", "Incident Responder", "Analyst", "Manager", "Operator", "Viewer"]


def _canonical_role(role: str) -> str:
    """Map common aliases / casing of system roles; pass any other name through
    (org custom roles exist) and let the server validate it."""
    key = " ".join(role.replace("_", " ").split()).lower()
    for name in _SYSTEM_ROLE_NAMES:
        if name.lower() == key:
            return name
    return _ROLE_ALIASES.get(key, role.strip())


@mcp.tool()
async def sheetstorm_create_user(
    email: str,
    name: str,
    password: str,
    role: Optional[str] = None,
    organizational_role: Optional[str] = None,
) -> str:
    """Create a new user in your organization. Requires users:create; assigning a
    role additionally requires roles:manage, and you can only assign roles whose
    permissions you hold yourself. Without a role the user gets Viewer.

    Args:
        email: User email address
        name: Display name
        password: Initial password (must meet the server password policy)
        role: A system role (Administrator, Incident Responder, Analyst, Manager,
            Operator, Viewer; aliases admin/responder/ir) or one of your
            organization's custom roles (see sheetstorm_list_roles)
        organizational_role: Optional job title (e.g. "DFIR Lead")
    """
    payload: dict = {"email": email, "name": name, "password": password}
    if role and role.strip():
        payload["roles"] = [_canonical_role(role)]
    if organizational_role:
        payload["organizational_role"] = organizational_role
    client = get_client()
    try:
        user = await client.post("/users", json=payload)
        return f"✓ User created:\n{_format_user(user)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_list_roles() -> str:
    """List the roles you can see: the built-in system roles and your
    organization's custom roles. Requires users:read."""
    client = get_client()
    try:
        data = await client.get("/roles")
        items = data.get("items", []) if isinstance(data, dict) else data
        if not items:
            return "No roles found."
        lines = [f"**Roles** ({len(items)})\n"]
        for r in items:
            tag = "system" if r.get("is_system") else "custom"
            perms = r.get("permissions") or []
            lines.append(
                f"**{r.get('name', 'N/A')}** [{tag}] (ID: {r.get('id', 'N/A')})\n"
                f"  {len(perms)} permission(s) | Users: {r.get('user_count', 'N/A')}"
                + (f"\n  {r['description']}" if r.get("description") else "")
            )
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_list_permissions(group: Optional[str] = None) -> str:
    """List the permission catalog (every permission key with its meaning).
    Dangerous permissions are flagged.

    Args:
        group: Only show one group (e.g. "incidents", "users", "decisions")
    """
    client = get_client()
    try:
        data = await client.get("/permissions")
        groups = {g.get("key"): g.get("label") for g in data.get("groups", [])}
        items = [p for p in data.get("items", []) if not group or p.get("group") == group]
        if not items:
            return f"No permissions found{f' in group {group!r}' if group else ''}."
        lines = ["**Permissions**\n"]
        current = None
        for p in items:
            if p.get("group") != current:
                current = p.get("group")
                lines.append(f"\n__{groups.get(current, current)}__")
            flag = " ⚠ dangerous" if p.get("dangerous") else ""
            lines.append(f"- `{p.get('key')}` — {p.get('label', '')}{flag}: {p.get('description', '')}")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_user(
    user_id: str,
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
    organizational_role: Optional[str] = None,
) -> str:
    """Update a user's name, active flag or job title. (Email and roles cannot be
    changed through this tool.) Requires users:update and that the user holds no
    permission you lack; deactivating also requires users:manage. You cannot
    deactivate yourself or the organization's last administrator.

    Args:
        user_id: UUID of the user
        name: New display name
        is_active: Activate (true) or deactivate (false) the user
        organizational_role: New job title ("" clears it)
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, val in [
            ("name", name),
            ("is_active", is_active),
            ("organizational_role", organizational_role),
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
    """Delete a user. Requires users:delete and that the user holds no permission
    you lack. You cannot delete yourself or the last administrator.

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
            params["unread_only"] = "true"
        data = await client.get("/notifications", params=params)
        items = data if isinstance(data, list) else data.get("items", data.get("notifications", []))

        if not items:
            return "No notifications."

        lines = [f"**Notifications** ({len(items)})\n"]
        for n in items:
            read_marker = "  " if n.get("is_read") else "● "
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
        await client.post(f"/notifications/{notification_id}/read")
        return f"✓ Notification {notification_id} marked as read."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_mark_all_notifications_read() -> str:
    """Mark all notifications as read."""
    client = get_client()
    try:
        await client.post("/notifications/read-all")
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
