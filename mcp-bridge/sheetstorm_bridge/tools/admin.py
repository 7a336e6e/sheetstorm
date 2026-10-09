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
    flags = []
    if u.get('is_locked'):
        flags.append(f"Locked until {u.get('locked_until') or '?'}")
    if u.get('must_change_password'):
        flags.append("Must change password")
    return (
        f"**{u.get('name', 'Unknown')}** (ID: {u.get('id', 'N/A')})\n"
        f"  Email: {u.get('email', 'N/A')} | Roles: {role_str}\n"
        f"  Active: {'Yes' if u.get('is_active', True) else 'No'} | "
        f"MFA: {'Enabled' if u.get('mfa_enabled') else 'Disabled'}"
        + (f"\n  {' | '.join(flags)}" if flags else "")
    )


_USER_STATUSES = ("active", "disabled", "locked", "must_change_password")


@mcp.tool()
async def sheetstorm_list_users(
    page: int = 1,
    per_page: int = 20,
    search: Optional[str] = None,
    status: Optional[str] = None,
    role: Optional[str] = None,
    team_id: Optional[str] = None,
) -> str:
    """List users in the organization.

    Args:
        page: Page number (default 1)
        per_page: Items per page (default 20)
        search: Match name or email
        status: active, disabled, locked or must_change_password
        role: Only users holding this role (role name)
        team_id: Only members of this team (UUID)
    """
    if status and status not in _USER_STATUSES:
        return f"✗ status must be one of: {', '.join(_USER_STATUSES)}"
    params: dict = {"page": page, "per_page": per_page}
    if search:
        params["q"] = search
    if status:
        params["status"] = status
    if role:
        params["role"] = _canonical_role(role)
    if team_id:
        params["team_id"] = team_id
    client = get_client()
    try:
        data = await client.get("/users", params=params)
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
    """Permanently delete a user (hard delete, not reversible). Requires
    users:delete and that the user holds no permission you lack. You cannot
    delete yourself or the last administrator. A user referenced by records
    they authored (incidents, timeline events, evidence, ...) cannot be
    deleted: the error lists those records; disable the user instead
    (sheetstorm_disable_user).

    Args:
        user_id: UUID of the user to delete
    """
    client = get_client()
    try:
        await client.delete(f"/users/{user_id}")
        return f"✓ User {user_id} deleted."
    except SheetStormAPIError as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if exc.status_code == 409 and detail.get("error") == "user_has_records":
            counts = detail.get("counts") or {}
            listed = ", ".join(f"{table}: {n}" for table, n in sorted(counts.items())) or "unknown records"
            return (f"✗ User {user_id} authored records and cannot be deleted ({listed}). "
                    "Disable the user instead (sheetstorm_disable_user).")
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# User lifecycle: invites, disable/enable, force logout, unlock, activity.
# Password and MFA resets are deliberately NOT exposed here: they return
# account-takeover secrets or strip a factor, and must not pass through an
# LLM context. Use the web UI for those.
# ---------------------------------------------------------------------------

def _app_url(path: str) -> str:
    """Absolute UI link for a backend-relative path (API URL minus /api/v1)."""
    base = getattr(get_client(), "_base_url", "") or ""
    if base.endswith("/api/v1"):
        base = base[: -len("/api/v1")]
    return f"{base.rstrip('/')}{path}"


async def _role_id(client, role: str) -> Optional[str]:
    name = _canonical_role(role).lower()
    data = await client.get("/roles")
    items = data.get("items", []) if isinstance(data, dict) else data
    for r in items or []:
        if str(r.get("name", "")).lower() == name:
            return r.get("id")
    return None


@mcp.tool()
async def sheetstorm_invite_user(
    email: str,
    role: Optional[str] = None,
    team_ids: Optional[list[str]] = None,
    expires_in_days: int = 7,
    name: Optional[str] = None,
) -> str:
    """Invite someone to your organization (no email is sent: you get a
    one-time join link to pass on). Requires users:manage; a role also needs
    roles:manage and must be within your own permissions. Without a role the
    invitee becomes a Viewer. Inviting the same email again replaces the
    previous invite.

    WARNING: the returned link is a credential: anyone holding it can join as
    that email until it expires or is revoked. Share it only with the invitee.

    Args:
        email: Invitee email address
        role: A system role (Administrator, Incident Responder, Analyst,
            Manager, Operator, Viewer) or one of your org's custom roles
        team_ids: Team UUIDs to add the invitee to
        expires_in_days: Link lifetime, 1..7 days (default 7)
        name: Optional display name suggestion
    """
    client = get_client()
    try:
        payload: dict = {"email": email, "expires_in_days": expires_in_days}
        if name:
            payload["name"] = name
        if team_ids:
            payload["team_ids"] = team_ids
        if role and role.strip():
            role_id = await _role_id(client, role)
            if not role_id:
                return f"✗ Unknown role {role!r} (see sheetstorm_list_roles)."
            payload["role_ids"] = [role_id]
        data = await client.post("/users/invites", json=payload)
        invite = data.get("invite") or {}
        link = data.get("accept_url") or _app_url(data.get("accept_path", ""))
        lines = [
            f"✓ Invite created for {invite.get('email', email)} (ID: {invite.get('id', data.get('id', 'N/A'))})",
            f"  Expires: {invite.get('expires_at', 'N/A')}",
            f"  Join link (shown once; treat it as a password): {link}",
        ]
        if data.get("superseded_invite_id"):
            lines.append(f"  Replaced the previous invite {data['superseded_invite_id']}.")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_list_invites(status: str = "pending") -> str:
    """List invites of your organization. Requires users:manage.

    Args:
        status: pending (default), accepted, revoked, expired or all
    """
    client = get_client()
    try:
        data = await client.get("/users/invites", params={"status": status})
        items = data.get("items", [])
        if not items:
            return f"No {status} invites."
        lines = [f"**Invites** ({status}, {data.get('total', len(items))} total)\n"]
        for inv in items:
            roles = ", ".join(r.get("name", "") for r in inv.get("roles") or []) or "Viewer (default)"
            by = (inv.get("created_by") or {}).get("name") or "N/A"
            lines.append(
                f"- {inv.get('email')} [{inv.get('status')}] (ID: {inv.get('id')})\n"
                f"  Roles: {roles} | Expires: {inv.get('expires_at')} | Invited by: {by}"
            )
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_revoke_invite(invite_id: str) -> str:
    """Revoke a pending invite so its link stops working. Requires users:manage.

    Args:
        invite_id: UUID of the invite
    """
    client = get_client()
    try:
        await client.delete(f"/users/invites/{invite_id}")
        return f"✓ Invite {invite_id} revoked."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_disable_user(user_id: str, reason: str) -> str:
    """Disable a user account: blocks sign-in and immediately revokes all of
    the user's sessions and live connections. Requires users:manage and that
    the user holds no permission you lack. You cannot disable yourself or the
    last administrator.

    Args:
        user_id: UUID of the user
        reason: Why (1-500 characters; kept in the audit log)
    """
    client = get_client()
    try:
        data = await client.post(f"/users/{user_id}/disable", json={"reason": reason})
        return f"✓ User disabled:\n{_format_user(data.get('user') or {})}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_enable_user(user_id: str) -> str:
    """Re-enable a disabled user. Old sessions stay revoked; the user signs in
    again. Requires users:manage.

    Args:
        user_id: UUID of the user
    """
    client = get_client()
    try:
        data = await client.post(f"/users/{user_id}/enable")
        return f"✓ User enabled:\n{_format_user(data.get('user') or {})}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_force_logout_user(user_id: str) -> str:
    """Sign a user out everywhere: revokes every token and disconnects live
    sessions. The account stays active. Requires users:manage.

    Args:
        user_id: UUID of the user
    """
    client = get_client()
    try:
        await client.post(f"/users/{user_id}/force-logout")
        return f"✓ All sessions of user {user_id} were revoked."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_unlock_user(user_id: str) -> str:
    """Clear a login lockout (after too many failed sign-in attempts).
    Requires users:manage.

    Args:
        user_id: UUID of the user
    """
    client = get_client()
    try:
        data = await client.post(f"/users/{user_id}/unlock")
        return f"✓ User unlocked:\n{_format_user(data.get('user') or {})}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_user_activity(user_id: str, scope: str = "all", per_page: int = 20) -> str:
    """Recent audit activity for a user. Requires audit_logs:read.

    Args:
        user_id: UUID of the user
        scope: actor (what the user did), target (what was done to the
            account) or all (default)
        per_page: Number of entries (max 100)
    """
    client = get_client()
    try:
        data = await client.get(f"/users/{user_id}/activity", params={"scope": scope, "per_page": per_page})
        items = data.get("items", [])
        if not items:
            return "No activity found."
        lines = [f"**Activity for {user_id}** ({scope}, {data.get('total', len(items))} total)\n"]
        for log in items:
            lines.append(
                f"[{log.get('created_at', 'N/A')}] **{log.get('action', 'N/A')}** "
                f"by {log.get('user_email') or 'system'} on {log.get('resource_type') or '-'}"
                f" (status {log.get('status_code', 'N/A')})"
            )
        return "\n".join(lines)
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
