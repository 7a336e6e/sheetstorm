"""Admin tools — user management, notifications, audit logs, system status, health check."""

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
# Audit Logs + system status
# ---------------------------------------------------------------------------

def _format_changes(changes: dict) -> str:
    parts = []
    for field, diff in list(changes.items())[:8]:
        if not isinstance(diff, dict):
            continue
        if diff.get("changed"):
            parts.append(f"{field} (changed, redacted)")
        elif "added" in diff or "removed" in diff:
            parts.append(f"{field} +{len(diff.get('added') or [])}/-{len(diff.get('removed') or [])}")
        else:
            parts.append(f"{field}: {diff.get('from')!r} → {diff.get('to')!r}")
    more = len(changes) - 8
    return "; ".join(parts) + (f" (+{more} more)" if more > 0 else "")


@mcp.tool()
async def sheetstorm_get_audit_logs(
    page: int = 1,
    per_page: int = 20,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    event_type: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    incident_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    ip: Optional[str] = None,
    user_email: Optional[str] = None,
    sort: Optional[str] = None,
    order: Optional[str] = None,
) -> str:
    """Search your organization's audit log. Requires audit_logs:read.
    (There is deliberately no export tool: export the log from the web UI.)

    Args:
        page: Page number
        per_page: Items per page (max 200)
        user_id: Only actions by this user (UUID)
        action: Substring of the action name (e.g. "login", "update")
        event_type: Comma list of authentication, authorization, data_access,
            data_modification, admin_action, security_event, system_event
        resource_type: e.g. "incident", "role", "integration"
        resource_id: UUID of the resource
        incident_id: UUID of the incident
        start_date: ISO-8601 lower bound (e.g. 2026-01-01T00:00:00Z)
        end_date: ISO-8601 upper bound
        status: success, client_error, server_error, denied, or an HTTP code
        ip: IP address or CIDR (e.g. 10.0.0.0/8)
        user_email: Exact actor email (case-insensitive; matches deleted users)
        sort: created_at, event_type, action, user_email, status_code,
            resource_type or chain_seq; prefix "-" for descending
        order: asc or desc (when sort is a single bare field)
    """
    client = get_client()
    try:
        params: dict = {"page": page, "per_page": min(max(per_page, 1), 200)}
        for key, val in [
            ("user_id", user_id),
            ("action_contains", action),
            ("event_type", event_type),
            ("resource_type", resource_type),
            ("resource_id", resource_id),
            ("incident_id", incident_id),
            ("start_date", start_date),
            ("end_date", end_date),
            ("status", status),
            ("ip", ip),
            ("user_email", user_email),
            ("sort", sort),
            ("order", order),
        ]:
            if val:
                params[key] = val

        data = await client.get("/audit-logs", params=params)
        items = data.get("items", data.get("logs", []))
        total = data.get("total", len(items))

        if not items:
            return "No audit logs found."

        lines = [f"**Audit Logs** (page {data.get('page', page)}, {total} total)\n"]
        for log in items:
            actor = log.get("user_email") or log.get("user_id") or "system"
            status_code = log.get("status_code")
            line = (
                f"[{log.get('created_at', 'N/A')}] **{log.get('action', 'N/A')}** "
                f"({log.get('event_type', 'N/A')}) by {actor}"
                + (f" → {status_code}" if status_code is not None else "")
                + f"\n  Resource: {log.get('resource_type') or 'N/A'} / {log.get('resource_id') or 'N/A'}"
            )
            if log.get("incident_id"):
                line += f" | Incident: {log['incident_id']}"
            details = log.get("details") or {}
            changes = details.get("changes") if isinstance(details, dict) else None
            if changes:
                line += f"\n  Changes: {_format_changes(changes)}"
            lines.append(line)
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


def _ok(section) -> str:
    if not isinstance(section, dict):
        return "n/a"
    return "OK" if section.get("ok") else f"FAIL ({section.get('error', 'unknown')})"


@mcp.tool()
async def sheetstorm_get_system_status() -> str:
    """Show the admin system status: storage, AI providers, integrations, counts
    and the audit log (retention, legal hold, hash-chain head and last
    verification). Platform admins also see database, migrations, Redis, rate
    limiting and version. Requires organizations:manage."""
    client = get_client()
    try:
        data = await client.get("/admin/system-status")
        lines = ["**System Status**"]
        if data.get("infra_visible"):
            app = data.get("app") or {}
            db = data.get("database") or {}
            alembic = data.get("alembic") or {}
            limiter = data.get("rate_limiting") or {}
            lines.append(f"  Version: {app.get('version') or 'n/a'} ({app.get('commit') or 'n/a'}), "
                         f"env {app.get('environment', 'n/a')}")
            lines.append(f"  Database: {_ok(db)}"
                         + (f", {db.get('latency_ms')} ms, PostgreSQL {db.get('server_version')}" if db.get("ok") else ""))
            lines.append(f"  Migrations: {'up to date' if alembic.get('up_to_date') else 'NOT up to date'} "
                         f"(current {', '.join(alembic.get('current') or []) or 'n/a'})")
            lines.append(f"  Redis: {_ok(data.get('redis'))}")
            lines.append(f"  Rate limiting: {'on' if limiter.get('enabled') else 'off'} "
                         f"({limiter.get('storage', 'n/a')}, default {limiter.get('default_limit', 'n/a')})")
        storage = data.get("storage") or {}
        disk = storage.get("disk") or {}
        lines.append(f"  Storage: {storage.get('backend', 'n/a')}"
                     + (f", {disk.get('used_pct')}% used" if disk.get("ok") else ""))
        providers = data.get("ai_providers")
        if isinstance(providers, list):
            names = ", ".join(f"{p.get('provider')} ({p.get('source')})" for p in providers) or "none"
            lines.append(f"  AI providers: {names}")
        integrations = data.get("integrations")
        if isinstance(integrations, list) and integrations:
            lines.append("  Integrations:")
            for i in integrations:
                tested = i.get("last_test_ok")
                state = "never tested" if tested is None else ("last test OK" if tested else "last test FAILED")
                lines.append(f"    - {i.get('name')} [{i.get('type')}] "
                             f"{'enabled' if i.get('is_enabled') else 'disabled'}, {state}")
        counts = data.get("counts") or {}
        if counts.get("users") is not None:
            lines.append(f"  Users: {counts.get('active_users')}/{counts.get('users')} active | "
                         f"Incidents: {counts.get('open_incidents')}/{counts.get('incidents')} open | "
                         f"Artifacts: {counts.get('artifacts')}")
        audit = data.get("audit") or {}
        if audit.get("total_rows") is not None:
            chain = audit.get("chain") or {}
            retention = audit.get("retention_days")
            verified = chain.get("last_verify_ok")
            lines.append(
                f"  Audit log: {audit.get('total_rows')} rows, retention "
                f"{f'{retention} days' if retention else 'forever'}"
                f"{', LEGAL HOLD' if audit.get('legal_hold') else ''}; chain head "
                f"{chain.get('head_seq')}:{(chain.get('head_hash') or '')[:16]}, last verification "
                f"{'n/a' if verified is None else ('OK' if verified else 'FAILED')}"
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
