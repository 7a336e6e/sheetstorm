"""Incident assignment tools — manage personnel assigned to incidents."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_assignment(a: dict) -> str:
    user = a.get("user") or {}
    user_name = user.get("name", "Unknown") if isinstance(user, dict) else "Unknown"
    user_email = user.get("email", "") if isinstance(user, dict) else ""
    role = a.get("role", "No role")
    return (
        f"**{user_name}** (ID: {a.get('id', 'N/A')})\n"
        f"  Email: {user_email}\n"
        f"  Role: {role}\n"
        f"  Assigned: {a.get('assigned_at', 'N/A')}"
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def sheetstorm_list_assignments(incident_id: str) -> str:
    """List all personnel assigned to an incident.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/assignments")
        items = data.get("items", []) if isinstance(data, dict) else data

        if not items:
            return "No personnel assigned to this incident."

        lines = [f"**Assigned Personnel** ({len(items)} total)\n"]
        for a in items:
            lines.append(_format_assignment(a))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error listing assignments: {exc}"


@mcp.tool()
async def sheetstorm_assign_user(
    incident_id: str,
    user_id: str,
    role: Optional[str] = None,
) -> str:
    """Assign a user to an incident with an optional role.

    When role is 'Lead Responder', the incident's lead_responder_id is
    also updated automatically.

    Args:
        incident_id: UUID of the incident
        user_id: UUID of the user to assign
        role: Optional role — one of: Lead Responder, Analyst,
              Forensic Investigator, Communications, Legal, Observer
    """
    client = get_client()
    try:
        payload: dict = {"user_id": user_id}
        if role:
            payload["role"] = role

        result = await client.post(f"/incidents/{incident_id}/assignments", json=payload)

        user = result.get("user") or {}
        user_name = user.get("name", "Unknown") if isinstance(user, dict) else "Unknown"
        role_str = result.get("role", "no role")
        return (
            f"✓ Assigned **{user_name}** to incident as **{role_str}**\n"
            f"  Assignment ID: {result.get('id', 'N/A')}"
        )
    except SheetStormAPIError as exc:
        return f"✗ Error assigning user: {exc}"


@mcp.tool()
async def sheetstorm_remove_assignment(
    incident_id: str,
    assignment_id: str,
) -> str:
    """Remove a user assignment from an incident.

    If the removed assignment had the Lead Responder role, the incident's
    lead responder field is cleared automatically.

    Args:
        incident_id: UUID of the incident
        assignment_id: UUID of the assignment to remove
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/assignments/{assignment_id}")
        return f"✓ Assignment {assignment_id} removed successfully."
    except SheetStormAPIError as exc:
        return f"✗ Error removing assignment: {exc}"
