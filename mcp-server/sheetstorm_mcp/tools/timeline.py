"""Timeline event tools — manage timeline events within incidents."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


def _format_event(e: dict) -> str:
    """Format a timeline event."""
    parts = [f"[{e.get('event_timestamp', 'N/A')}] {e.get('description', 'N/A')}"]
    parts.append(f"  ID: {e.get('id', 'N/A')} | Type: {e.get('event_type', 'N/A')}")
    if e.get("source"):
        parts.append(f"  Source: {e['source']}")
    if e.get("mitre_tactic"):
        parts.append(f"  MITRE: {e['mitre_tactic']} / {e.get('mitre_technique', 'N/A')}")
    if e.get("host_name"):
        parts.append(f"  Host: {e['host_name']}")
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
    event_timestamp: str,
    description: str,
    event_type: str = "other",
    source: Optional[str] = None,
    host_id: Optional[str] = None,
    mitre_tactic: Optional[str] = None,
    mitre_technique: Optional[str] = None,
) -> str:
    """Create a new timeline event for an incident.

    Args:
        incident_id: UUID of the incident
        event_timestamp: ISO 8601 datetime (e.g. 2026-02-25T10:30:00Z)
        description: Event description
        event_type: Event type (detection, lateral_movement, c2, exfiltration, containment, eradication, recovery, other)
        source: Event source (e.g. SIEM, EDR, manual)
        host_id: Optional associated host UUID
        mitre_tactic: Optional MITRE ATT&CK tactic
        mitre_technique: Optional MITRE ATT&CK technique
    """
    client = get_client()
    try:
        payload: dict = {
            "event_timestamp": event_timestamp,
            "description": description,
            "event_type": event_type,
        }
        if source:
            payload["source"] = source
        if host_id:
            payload["host_id"] = host_id
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
    event_timestamp: Optional[str] = None,
    description: Optional[str] = None,
    event_type: Optional[str] = None,
    source: Optional[str] = None,
    mitre_tactic: Optional[str] = None,
    mitre_technique: Optional[str] = None,
) -> str:
    """Update an existing timeline event.

    Args:
        incident_id: UUID of the incident
        event_id: UUID of the timeline event
        event_timestamp: New ISO 8601 datetime
        description: New description
        event_type: New event type
        source: New source
        mitre_tactic: New MITRE tactic
        mitre_technique: New MITRE technique
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, value in [
            ("event_timestamp", event_timestamp),
            ("description", description),
            ("event_type", event_type),
            ("source", source),
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


@mcp.tool()
async def sheetstorm_get_mitre_tactics() -> str:
    """List available MITRE ATT&CK tactics for timeline event mapping."""
    client = get_client()
    try:
        data = await client.get("/mitre/tactics")
        tactics = data if isinstance(data, list) else data.get("tactics", [])
        if not tactics:
            return "No MITRE tactics available."
        lines = ["**MITRE ATT&CK Tactics**\n"]
        for t in tactics:
            if isinstance(t, dict):
                lines.append(f"- **{t.get('id', 'N/A')}**: {t.get('name', 'N/A')}")
            else:
                lines.append(f"- {t}")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_mitre_techniques(tactic: str) -> str:
    """List MITRE ATT&CK techniques for a given tactic.

    Args:
        tactic: MITRE tactic identifier (e.g. 'initial-access', 'execution')
    """
    client = get_client()
    try:
        data = await client.get(f"/mitre/techniques/{tactic}")
        techniques = data if isinstance(data, list) else data.get("techniques", [])
        if not techniques:
            return f"No techniques found for tactic: {tactic}"
        lines = [f"**Techniques for {tactic}**\n"]
        for t in techniques:
            if isinstance(t, dict):
                lines.append(f"- **{t.get('id', 'N/A')}**: {t.get('name', 'N/A')}")
            else:
                lines.append(f"- {t}")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
