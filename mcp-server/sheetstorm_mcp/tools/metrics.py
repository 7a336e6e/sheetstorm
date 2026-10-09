"""Response metrics and improvement-action tools.

The backend enforces authorization with the caller's token (`incidents:read`
for metrics, `improvements:read` / `improvements:create` for actions). The
MCP sends no If-Match, so edits it makes are last-write-wins.
"""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import get_client, mcp

METRIC_LABELS = [
    ("dwell_time", "Dwell time (first malicious -> detected)"),
    ("time_to_respond", "Time to respond (detected -> responded)"),
    ("time_to_contain", "Time to contain (detected -> contained)"),
    ("contain_to_eradicate", "Contain -> eradicate"),
    ("eradicate_to_recover", "Eradicate -> recover"),
    ("recover_to_close", "Recover -> close"),
    ("total_open", "Total open"),
]


def _duration(seconds) -> str:
    """Human duration for a number of seconds ('-' when unknown)."""
    if seconds is None:
        return "-"
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def _format_action(a: dict) -> str:
    owner = (a.get("owner") or {}).get("name") or "unassigned"
    due = (a.get("due_date") or "no due date")[:10]
    control = ""
    if a.get("control_framework"):
        control = f" | Control: {a['control_framework']} {a.get('control_ref') or ''}".rstrip()
    incident = a.get("incident_ref") or (a.get("incident") or {}).get("title") or "-"
    return (
        f"**{a.get('title', 'Untitled')}** (ID: {a.get('id', 'N/A')})\n"
        f"  Status: {a.get('status')} | Priority: {a.get('priority')} | Owner: {owner} | Due: {due}{control}\n"
        f"  Incident: {incident}"
    )


@mcp.tool()
async def sheetstorm_get_incident_metrics(incident_id: str) -> str:
    """Response metrics for one incident: dwell time, time to respond, contain,
    eradicate, recover and close, computed from the incident's lifecycle
    timestamps. A timestamp edited out of order produces an anomaly note
    instead of a negative duration.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/metrics")
    except SheetStormAPIError as exc:
        return f"✗ Error loading metrics: {exc}"

    durations = data.get("durations") or {}
    lines = [f"# Metrics for incident {data.get('incident_id', incident_id)}"]
    for key, label in METRIC_LABELS:
        lines.append(f"- {label}: {_duration(durations.get(key))}")
    source = (data.get("sources") or {}).get("first_malicious")
    notes = {
        "override": "first malicious activity set manually",
        "timeline": "first malicious activity derived from the timeline",
        "restricted": "first malicious activity not derived (timeline access required)",
    }
    lines.append(f"\n**Dwell start**: {notes.get(source, 'unknown (no malicious timeline events)')}")
    for anomaly in data.get("anomalies") or []:
        lines.append(f"⚠ Anomaly: {anomaly.get('metric')} is {anomaly.get('reason')} "
                     f"({anomaly.get('seconds')}s) - check the lifecycle timestamps")
    return "\n".join(lines)


@mcp.tool()
async def sheetstorm_list_improvement_actions(
    status: Optional[str] = None,
    owner_id: Optional[str] = None,
    incident_id: Optional[str] = None,
    overdue: bool = False,
    page: int = 1,
    per_page: int = 50,
) -> str:
    """List post-incident improvement actions across the organization.

    Args:
        status: Comma-separated filter: open, in_progress, blocked, done, wont_fix
        owner_id: UUID of the owner (or "me")
        incident_id: UUID of the source incident
        overdue: Only open actions past their due date
        page: Page number (default 1)
        per_page: Items per page (default 50, max 100)
    """
    client = get_client()
    try:
        params: dict = {"page": page, "per_page": min(max(per_page, 1), 100)}
        if status:
            params["status"] = status
        if owner_id:
            params["owner_id"] = owner_id
        if incident_id:
            params["incident_id"] = incident_id
        if overdue:
            params["overdue"] = "true"
        data = await client.get("/improvement-actions", params=params)
        items = data.get("items", [])
        if not items:
            return "No improvement actions found."
        lines = [f"**Improvement actions** (showing {len(items)} of {data.get('total', len(items))})\n"]
        for a in items:
            lines.append(_format_action(a))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error listing improvement actions: {exc}"


@mcp.tool()
async def sheetstorm_add_improvement_action(
    incident_id: str,
    title: str,
    description: Optional[str] = None,
    owner_id: Optional[str] = None,
    due_date: Optional[str] = None,
    priority: str = "medium",
    category: Optional[str] = None,
    control_framework: Optional[str] = None,
    control_ref: Optional[str] = None,
) -> str:
    """Add a lessons-learned improvement action to an incident.

    Args:
        incident_id: UUID of the incident
        title: What should change
        description: Details
        owner_id: UUID of the responsible user (same organization)
        due_date: Due date, ISO format (YYYY-MM-DD)
        priority: low, medium, high or critical
        category: people, process, technology, detection, communication, third_party or other
        control_framework: nist_csf, d3fend, cis, iso27001 or other
        control_ref: Control id, e.g. RS.MA-01 (nist_csf) or D3-MFA (d3fend); needs control_framework
    """
    client = get_client()
    try:
        payload: dict = {"title": title, "priority": priority}
        for key, value in (
            ("description", description), ("owner_id", owner_id), ("due_date", due_date),
            ("category", category), ("control_framework", control_framework), ("control_ref", control_ref),
        ):
            if value:
                payload[key] = value
        action = await client.post(f"/incidents/{incident_id}/improvement-actions", json=payload)
        return f"✓ Improvement action added:\n{_format_action(action)}"
    except SheetStormAPIError as exc:
        return f"✗ Error adding improvement action: {exc}"
