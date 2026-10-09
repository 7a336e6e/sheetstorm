"""Timeline event tools — manage timeline events within incidents."""

from __future__ import annotations

from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import get_client, mcp
from sheetstorm_bridge.tools._provenance import format_provenance, provenance_payload


def _format_event(e: dict) -> str:
    """Format a timeline event."""
    parts = [f"[{e.get('timestamp', 'N/A')}] {e.get('activity', 'N/A')}"]
    parts.append(f"  ID: {e.get('id', 'N/A')} | Phase: {e.get('phase', 'N/A')}")
    if e.get("source"):
        parts.append(f"  Source: {e['source']}")
    mappings = e.get("mitre_mappings") or []
    if mappings:
        for m in mappings:
            tactic = m.get("tactic", "N/A")
            technique = m.get("technique", "N/A")
            name = m.get("name", "")
            label = f"{tactic} / {technique}"
            if name:
                label += f" ({name})"
            parts.append(f"  MITRE: {label}")
    elif e.get("mitre_tactic"):
        parts.append(f"  MITRE: {e['mitre_tactic']} / {e.get('mitre_technique', 'N/A')}")
    if e.get("hostname"):
        parts.append(f"  Host: {e['hostname']}")
    if e.get("detection_time") or e.get("confidence_level"):
        parts.append(
            f"  Detected: {e.get('detection_time') or 'N/A'} | "
            f"Confidence: {e.get('confidence_level') or 'N/A'}"
        )
    parts.extend(format_provenance(e))
    if e.get("is_key_event"):
        parts.append("  ★ Key Event")
    if e.get("is_ioc"):
        parts.append("  ⚑ Marked as IOC")
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
    activity: str,
    timestamp: Optional[str] = None,
    source: Optional[str] = None,
    host_id: Optional[str] = None,
    phase: Optional[int] = None,
    is_key_event: bool = False,
    mitre_mappings: Optional[str] = None,
    mitre_tactic: Optional[str] = None,
    mitre_technique: Optional[str] = None,
    detection_time: Optional[str] = None,
    confidence_level: Optional[str] = None,
    source_evidence_id: Optional[str] = None,
    source_artifact_id: Optional[str] = None,
    source_record_type: Optional[str] = None,
    source_record_ref: Optional[str] = None,
    raw_timestamp: Optional[str] = None,
    source_timezone: Optional[str] = None,
    timestamp_type: Optional[str] = None,
    extraction_tool: Optional[str] = None,
    extraction_tool_version: Optional[str] = None,
) -> str:
    """Create a new timeline event for an incident.

    MITRE ATT&CK mappings can be provided as a JSON array of objects with
    tactic, technique, and optional name fields. Example:
    [{"tactic": "execution", "technique": "T1059", "name": "Command and Scripting Interpreter"}]
    Leave mitre_mappings empty to auto-suggest from the activity text.
    Legacy mitre_tactic/mitre_technique are still accepted for single mappings.

    Args:
        incident_id: UUID of the incident
        activity: Event activity description
        timestamp: ISO 8601 datetime (e.g. 2026-02-25T10:30:00Z). Required unless raw_timestamp is given
        source: Event source (e.g. SIEM, EDR, manual)
        host_id: Optional associated host UUID
        phase: IR phase (1-6)
        is_key_event: Mark as key event
        mitre_mappings: JSON array of MITRE mappings (each with tactic, technique, name)
        mitre_tactic: Legacy single MITRE ATT&CK tactic
        mitre_technique: Legacy single MITRE ATT&CK technique
        detection_time: ISO 8601 time the activity was DETECTED (timestamp is when it happened)
        confidence_level: Analyst confidence in this event — one of: low, medium, high, certain
        source_evidence_id: UUID of the registered evidence item this fact came from (same incident)
        source_artifact_id: UUID of a stored artifact this fact came from (same incident)
        source_record_type: file_path, evtx_record, offset, log_line, url, registry_key, db_row or other
        source_record_ref: Exact record reference, e.g. 'Security.evtx EventRecordID=48213' (stored as text only)
        raw_timestamp: The timestamp exactly as found in the source. With source_timezone (or an offset in the
            string) the server derives the UTC time, applying the host's clock skew; omit the explicit timestamp then
        source_timezone: IANA zone (Europe/Berlin), UTC, or UTC+HH:MM for a raw_timestamp without an offset
        timestamp_type: modified, accessed, changed, born, logged, first_seen, last_seen, observed or other
        extraction_tool: Tool that produced the record, e.g. EvtxECmd
        extraction_tool_version: Version of that tool
    """
    import json as _json
    if not timestamp and not raw_timestamp:
        return "✗ Error: provide timestamp or raw_timestamp (with source_timezone)."
    client = get_client()
    try:
        payload: dict = {"activity": activity}
        if timestamp:
            payload["timestamp"] = timestamp
        if detection_time:
            payload["detection_time"] = detection_time
        if confidence_level:
            payload["confidence_level"] = confidence_level
        if source:
            payload["source"] = source
        if host_id:
            payload["host_id"] = host_id
        if phase is not None:
            payload["phase"] = phase
        if is_key_event:
            payload["is_key_event"] = is_key_event
        if mitre_mappings:
            try:
                payload["mitre_mappings"] = _json.loads(mitre_mappings)
            except _json.JSONDecodeError:
                return "✗ Error: mitre_mappings must be a valid JSON array."
        elif mitre_tactic or mitre_technique:
            payload["mitre_tactic"] = mitre_tactic
            payload["mitre_technique"] = mitre_technique
        payload.update(provenance_payload(
            source_evidence_id=source_evidence_id, source_artifact_id=source_artifact_id,
            source_record_type=source_record_type, source_record_ref=source_record_ref,
            raw_timestamp=raw_timestamp, source_timezone=source_timezone, timestamp_type=timestamp_type,
            extraction_tool=extraction_tool, extraction_tool_version=extraction_tool_version,
        ))

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
    mitre_mappings: Optional[str] = None,
    mitre_tactic: Optional[str] = None,
    mitre_technique: Optional[str] = None,
    detection_time: Optional[str] = None,
    confidence_level: Optional[str] = None,
    source_evidence_id: Optional[str] = None,
    source_artifact_id: Optional[str] = None,
    source_record_type: Optional[str] = None,
    source_record_ref: Optional[str] = None,
    raw_timestamp: Optional[str] = None,
    source_timezone: Optional[str] = None,
    timestamp_type: Optional[str] = None,
    extraction_tool: Optional[str] = None,
    extraction_tool_version: Optional[str] = None,
) -> str:
    """Update an existing timeline event.

    MITRE ATT&CK mappings can be provided as a JSON array. See create_timeline_event for format.

    Args:
        incident_id: UUID of the incident
        event_id: UUID of the timeline event
        timestamp: New ISO 8601 datetime
        activity: New activity description
        source: New source
        phase: New IR phase (1-6)
        is_key_event: Mark/unmark as key event
        mitre_mappings: JSON array of MITRE mappings (each with tactic, technique, name)
        mitre_tactic: Legacy single MITRE tactic
        mitre_technique: Legacy single MITRE technique
        detection_time: ISO 8601 time the activity was detected
        confidence_level: One of: low, medium, high, certain
        source_evidence_id: UUID of the registered evidence item this fact came from (same incident)
        source_artifact_id: UUID of a stored artifact this fact came from (same incident)
        source_record_type: file_path, evtx_record, offset, log_line, url, registry_key, db_row or other
        source_record_ref: Exact record reference, e.g. 'Security.evtx EventRecordID=48213' (stored as text only)
        raw_timestamp: The timestamp exactly as found in the source. With source_timezone (or an offset in the
            string) the server derives the UTC time, applying the host's clock skew; omit the explicit timestamp then
        source_timezone: IANA zone (Europe/Berlin), UTC, or UTC+HH:MM for a raw_timestamp without an offset
        timestamp_type: modified, accessed, changed, born, logged, first_seen, last_seen, observed or other
        extraction_tool: Tool that produced the record, e.g. EvtxECmd
        extraction_tool_version: Version of that tool
    """
    import json as _json
    client = get_client()
    try:
        payload: dict = {}
        for field, value in [
            ("timestamp", timestamp),
            ("activity", activity),
            ("source", source),
            ("phase", phase),
            ("is_key_event", is_key_event),
            ("detection_time", detection_time),
            ("confidence_level", confidence_level),
        ]:
            if value is not None:
                payload[field] = value

        if mitre_mappings:
            try:
                payload["mitre_mappings"] = _json.loads(mitre_mappings)
            except _json.JSONDecodeError:
                return "✗ Error: mitre_mappings must be a valid JSON array."
        elif mitre_tactic is not None or mitre_technique is not None:
            if mitre_tactic is not None:
                payload["mitre_tactic"] = mitre_tactic
            if mitre_technique is not None:
                payload["mitre_technique"] = mitre_technique
        payload.update(provenance_payload(
            source_evidence_id=source_evidence_id, source_artifact_id=source_artifact_id,
            source_record_type=source_record_type, source_record_ref=source_record_ref,
            raw_timestamp=raw_timestamp, source_timezone=source_timezone, timestamp_type=timestamp_type,
            extraction_tool=extraction_tool, extraction_tool_version=extraction_tool_version,
        ))

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
async def sheetstorm_mark_timeline_event_as_ioc(
    incident_id: str,
    event_id: str,
    artifact_type: str = "other",
    notes: Optional[str] = None,
    is_malicious: bool = True,
) -> str:
    """Flag a timeline event as an IOC and create a linked host-based indicator
    (its value is the event's activity text, its host the event's host).

    Args:
        incident_id: UUID of the incident
        event_id: UUID of the timeline event
        artifact_type: Host IOC type — one of: wmi_event, asep, registry, scheduled_task, service, file, process, other
        notes: Optional analyst notes for the indicator
        is_malicious: Whether the indicator is confirmed malicious (default true)
    """
    client = get_client()
    try:
        payload: dict = {"artifact_type": artifact_type, "is_malicious": is_malicious}
        if notes:
            payload["notes"] = notes
        data = await client.post(
            f"/incidents/{incident_id}/timeline/{event_id}/mark-as-ioc", json=payload
        )
        ioc = data.get("ioc", {})
        return (
            f"✓ Event marked as IOC. Host indicator created (ID: {ioc.get('id', 'N/A')}, "
            f"type: {ioc.get('artifact_type', artifact_type)})"
        )
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_list_timeline_mitre_tactics() -> str:
    """List the MITRE ATT&CK tactic identifiers accepted by timeline events
    (mitre_tactic / mitre_mappings[].tactic). For full ATT&CK descriptions use
    sheetstorm_get_mitre_tactics."""
    client = get_client()
    try:
        data = await client.get("/mitre/tactics")
        tactics = data if isinstance(data, list) else data.get("tactics", [])
        if not tactics:
            return "No MITRE tactics available."
        lines = ["**Timeline MITRE ATT&CK Tactics**\n"]
        for t in tactics:
            if isinstance(t, dict):
                lines.append(f"- **{t.get('id', 'N/A')}**: {t.get('name', 'N/A')}")
            else:
                lines.append(f"- {t}")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_list_timeline_mitre_techniques(tactic: Optional[str] = None) -> str:
    """List the MITRE ATT&CK techniques accepted by timeline events, optionally for
    one tactic. For searchable ATT&CK details use sheetstorm_get_mitre_techniques.

    Args:
        tactic: Optional tactic identifier (from sheetstorm_list_timeline_mitre_tactics)
    """
    client = get_client()
    try:
        params: dict = {}
        if tactic:
            params["tactic"] = tactic
        data = await client.get("/mitre/techniques", params=params)
        techniques = data if isinstance(data, list) else data.get("techniques", [])
        if not techniques:
            return f"No techniques found for tactic: {tactic}"
        if isinstance(techniques, dict):  # all tactics: {tactic: [techniques]}
            lines = ["**Timeline MITRE ATT&CK Techniques**"]
            for tac, techs in techniques.items():
                lines.append(f"\n**{tac}**")
                lines.extend(f"- {t.get('id', 'N/A')}: {t.get('name', 'N/A')}" for t in techs)
            return "\n".join(lines)
        lines = [f"**Techniques for {tactic}**\n"]
        for t in techniques:
            if isinstance(t, dict):
                lines.append(f"- **{t.get('id', 'N/A')}**: {t.get('name', 'N/A')}")
            else:
                lines.append(f"- {t}")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
