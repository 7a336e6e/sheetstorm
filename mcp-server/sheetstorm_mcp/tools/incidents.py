"""Incident management tools — CRUD, search, status updates."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


def _format_incident(inc: dict) -> str:
    """Format a single incident into a readable string."""
    return (
        f"**{inc.get('title', 'Untitled')}** (ID: {inc.get('id', 'N/A')})\n"
        f"  Status: {inc.get('status', 'N/A')} | Severity: {inc.get('severity', 'N/A')} | "
        f"Phase: {inc.get('phase', 'N/A')}\n"
        f"  Classification: {inc.get('classification', 'N/A')}\n"
        f"  Created: {inc.get('created_at', 'N/A')}"
    )


def _format_incident_detail(inc: dict) -> str:
    """Format full incident details."""
    parts = [
        f"# {inc.get('title', 'Untitled')}",
        f"**ID**: {inc.get('id', 'N/A')}",
        f"**Status**: {inc.get('status', 'N/A')}",
        f"**Severity**: {inc.get('severity', 'N/A')}",
        f"**Phase**: {inc.get('phase', 'N/A')}",
        f"**Classification**: {inc.get('classification', 'N/A')}",
        f"**Created**: {inc.get('created_at', 'N/A')}",
        f"**Updated**: {inc.get('updated_at', 'N/A')}",
    ]
    if inc.get("description"):
        parts.append(f"\n**Description**:\n{inc['description']}")
    if inc.get("executive_summary"):
        parts.append(f"\n**Executive Summary**:\n{inc['executive_summary']}")
    if inc.get("lessons_learned"):
        parts.append(f"\n**Lessons Learned**:\n{inc['lessons_learned']}")

    # Phase timestamps
    for ts_name in ["detected_at", "contained_at", "eradicated_at", "recovered_at", "closed_at"]:
        if inc.get(ts_name):
            parts.append(f"**{ts_name.replace('_', ' ').title()}**: {inc[ts_name]}")

    return "\n".join(parts)


@mcp.tool()
async def sheetstorm_list_incidents(
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    search: Optional[str] = None,
) -> str:
    """List incidents with optional filters and pagination.

    Args:
        page: Page number (default 1)
        per_page: Items per page (default 20, max 100)
        status: Filter by status (open, contained, eradicated, recovered, closed)
        severity: Filter by severity (critical, high, medium, low)
        search: Search term for title/description
    """
    client = get_client()
    try:
        params: dict = {"page": page, "per_page": min(per_page, 100)}
        if status:
            params["status"] = status
        if severity:
            params["severity"] = severity
        if search:
            params["search"] = search

        data = await client.get("/incidents", params=params)
        items = data.get("items", [])
        total = data.get("total", 0)

        if not items:
            return "No incidents found matching the criteria."

        lines = [f"**Incidents** (page {page}, {len(items)} of {total} total)\n"]
        for inc in items:
            lines.append(_format_incident(inc))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error listing incidents: {exc}"


@mcp.tool()
async def sheetstorm_get_incident(incident_id: str) -> str:
    """Get full details of a specific incident.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        inc = await client.get(f"/incidents/{incident_id}")
        return _format_incident_detail(inc)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_create_incident(
    title: str,
    description: str,
    severity: str = "medium",
    classification: Optional[str] = None,
    phase: int = 1,
) -> str:
    """Create a new incident.

    Args:
        title: Incident title
        description: Incident description
        severity: Severity level (critical, high, medium, low)
        classification: Optional classification type
        phase: IR phase 1-6 (default 1 = Preparation)
    """
    client = get_client()
    try:
        payload: dict = {
            "title": title,
            "description": description,
            "severity": severity,
            "phase": phase,
        }
        if classification:
            payload["classification"] = classification

        inc = await client.post("/incidents", json=payload)
        return f"✓ Incident created:\n{_format_incident(inc)}"
    except SheetStormAPIError as exc:
        return f"✗ Error creating incident: {exc}"


@mcp.tool()
async def sheetstorm_update_incident(
    incident_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    severity: Optional[str] = None,
    classification: Optional[str] = None,
    executive_summary: Optional[str] = None,
    lessons_learned: Optional[str] = None,
) -> str:
    """Update incident details.

    Args:
        incident_id: UUID of the incident
        title: New title
        description: New description
        severity: New severity (critical, high, medium, low)
        classification: New classification
        executive_summary: Executive summary text
        lessons_learned: Lessons learned text
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, value in [
            ("title", title),
            ("description", description),
            ("severity", severity),
            ("classification", classification),
            ("executive_summary", executive_summary),
            ("lessons_learned", lessons_learned),
        ]:
            if value is not None:
                payload[field] = value

        if not payload:
            return "No fields to update. Provide at least one field."

        inc = await client.put(f"/incidents/{incident_id}", json=payload)
        return f"✓ Incident updated:\n{_format_incident(inc)}"
    except SheetStormAPIError as exc:
        return f"✗ Error updating incident: {exc}"


@mcp.tool()
async def sheetstorm_update_incident_status(
    incident_id: str,
    status: Optional[str] = None,
    phase: Optional[int] = None,
) -> str:
    """Update incident status and/or IR phase.

    Args:
        incident_id: UUID of the incident
        status: New status (open, contained, eradicated, recovered, closed)
        phase: New IR phase (1=Preparation, 2=Identification, 3=Containment, 4=Eradication, 5=Recovery, 6=Lessons Learned)
    """
    client = get_client()
    try:
        payload: dict = {}
        if status:
            payload["status"] = status
        if phase is not None:
            payload["phase"] = phase

        if not payload:
            return "No status or phase provided."

        inc = await client.patch(f"/incidents/{incident_id}/status", json=payload)
        return f"✓ Incident status updated:\n  Status: {inc.get('status')} | Phase: {inc.get('phase')}"
    except SheetStormAPIError as exc:
        return f"✗ Error updating status: {exc}"


@mcp.tool()
async def sheetstorm_delete_incident(incident_id: str) -> str:
    """Delete an incident. This is irreversible.

    Args:
        incident_id: UUID of the incident to delete
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}")
        return f"✓ Incident {incident_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error deleting incident: {exc}"
