"""Timeline event tools — manage timeline events within incidents."""

from __future__ import annotations

from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import mcp, get_client


def _format_event(e: dict) -> str:
    """Format a timeline event."""
    parts = [f"[{e.get('timestamp', 'N/A')}] {e.get('activity', 'N/A')}"]
    parts.append(f"  ID: {e.get('id', 'N/A')} | Phase: {e.get('phase', 'N/A')}")
    if e.get("source"):
        parts.append(f"  Source: {e['source']}")
    if e.get("mitre_tactic"):
        parts.append(f"  MITRE: {e['mitre_tactic']} / {e.get('mitre_technique', 'N/A')}")
    if e.get("hostname"):
        parts.append(f"  Host: {e['hostname']}")
    if e.get("is_key_event"):
        parts.append("  ★ Key Event")
    return "\n".join(parts)


@mcp.tool()
async def sheetstorm_list_timeline_events(
    incident_id: str,
    phase: Optional[int] = None,
    host_id: Optional[str] = None,
) -> str:
    """List timeline events for an incident, ordered chronologically.

    Args:
        incident_id: UUID of the incident
        phase: Optional filter by IR phase (1-6)
        host_id: Optional filter by host UUID
    """
    client = get_client()
    try:
        params: dict = {}
        if phase is not None:
            params["phase"] = phase
        if host_id:
            params["host_id"] = host_id

        data = await client.get(f"/incidents/{incident_id}/timeline", params=params)
        items = data if isinstance(data, list) else data.get("items", data.get("timeline", []))

        if not items:
            return "No timeline events found."

        lines = [f"**Timeline Events** ({len(items)} events)\n"]
        for e in items:
            lines.append(_format_event(e))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_create_timeline_event(
    incident_id: str,
    timestamp: str,
    activity: str,
    source: Optional[str] = None,
    host_id: Optional[str] = None,
    phase: Optional[int] = None,
    is_key_event: bool = False,
    mitre_tactic: Optional[str] = None,
    mitre_technique: Optional[str] = None,
) -> str:
    """Create a new timeline event for an incident.

    Args:
        incident_id: UUID of the incident
        timestamp: ISO 8601 datetime (e.g. 2026-02-25T10:30:00Z)
        activity: Event activity description
        source: Event source (e.g. SIEM, EDR, manual)
        host_id: Optional associated host UUID
        phase: IR phase (1-6)
        is_key_event: Mark as key event
        mitre_tactic: Optional MITRE ATT&CK tactic
        mitre_technique: Optional MITRE ATT&CK technique
    """
    client = get_client()
    try:
        payload: dict = {
            "timestamp": timestamp,
            "activity": activity,
        }
        if source:
            payload["source"] = source
        if host_id:
            payload["host_id"] = host_id
        if phase is not None:
            payload["phase"] = phase
        if is_key_event:
            payload["is_key_event"] = is_key_event
        if mitre_tactic:
            payload["mitre_tactic"] = mitre_tactic
        if mitre_technique:
            payload["mitre_technique"] = mitre_technique

        event = await client.post(f"/incidents/{incident_id}/timeline", json=payload)
        return f"✓ Timeline event created:\n{_format_event(event)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_timeline_event(
    incident_id: str,
    event_id: str,
    timestamp: Optional[str] = None,
    activity: Optional[str] = None,
    source: Optional[str] = None,
    phase: Optional[int] = None,
    is_key_event: Optional[bool] = None,
    mitre_tactic: Optional[str] = None,
    mitre_technique: Optional[str] = None,
) -> str:
    """Update an existing timeline event.

    Args:
        incident_id: UUID of the incident
        event_id: UUID of the timeline event
        timestamp: New ISO 8601 datetime
        activity: New activity description
        source: New source
        phase: New IR phase (1-6)
        is_key_event: Mark/unmark as key event
        mitre_tactic: New MITRE tactic
        mitre_technique: New MITRE technique
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, value in [
            ("timestamp", timestamp),
            ("activity", activity),
            ("source", source),
            ("phase", phase),
            ("is_key_event", is_key_event),
            ("mitre_tactic", mitre_tactic),
            ("mitre_technique", mitre_technique),
        ]:
            if value is not None:
                payload[field] = value

        if not payload:
            return "No fields to update."

        event = await client.put(f"/incidents/{incident_id}/timeline/{event_id}", json=payload)
        return f"✓ Timeline event updated:\n{_format_event(event)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_delete_timeline_event(incident_id: str, event_id: str) -> str:
    """Delete a timeline event.

    Args:
        incident_id: UUID of the incident
        event_id: UUID of the timeline event to delete
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/timeline/{event_id}")
        return f"✓ Timeline event {event_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
