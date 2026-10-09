"""Incident management tools — CRUD, search, status updates."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import get_client, mcp

# IR milestones in the order the backend enforces (each <= the next).
MILESTONE_FIELDS = ("first_malicious_at", "detected_at", "responded_at", "contained_at", "eradicated_at",
                    "recovered_at", "closed_at")


def _format_incident(inc: dict) -> str:
    """Format a single incident into a readable string."""
    tlp = inc.get('tlp', 'amber')
    team = inc.get('owning_team', {}) or {}
    team_name = team.get('name', 'N/A') if isinstance(team, dict) else 'N/A'
    return (
        f"**{inc.get('title', 'Untitled')}** (ID: {inc.get('id', 'N/A')})\n"
        f"  Status: {inc.get('status', 'N/A')} | Severity: {inc.get('severity', 'N/A')} | "
        f"Phase: {inc.get('phase', 'N/A')}\n"
        f"  Classification: {inc.get('classification', 'N/A')} | "
        f"TLP: {tlp.upper()} | Team: {team_name}\n"
        f"  Created: {inc.get('created_at', 'N/A')}"
    )


def _format_incident_detail(inc: dict) -> str:
    """Format full incident details."""
    tlp = inc.get('tlp', 'amber')
    team = inc.get('owning_team', {}) or {}
    team_name = team.get('name', 'N/A') if isinstance(team, dict) else 'N/A'
    parts = [
        f"# {inc.get('title', 'Untitled')}",
        f"**ID**: {inc.get('id', 'N/A')}",
        f"**Status**: {inc.get('status', 'N/A')}",
        f"**Severity**: {inc.get('severity', 'N/A')}",
        f"**Phase**: {inc.get('phase', 'N/A')}",
        f"**Classification**: {inc.get('classification', 'N/A')}",
        f"**TLP**: {tlp.upper()}",
        f"**Owning Team**: {team_name}",
        f"**Created**: {inc.get('created_at', 'N/A')}",
        f"**Updated**: {inc.get('updated_at', 'N/A')}",
    ]
    if inc.get("description"):
        parts.append(f"\n**Description**:\n{inc['description']}")
    if inc.get("executive_summary"):
        parts.append(f"\n**Executive Summary**:\n{inc['executive_summary']}")
    if inc.get("lessons_learned"):
        parts.append(f"\n**Lessons Learned**:\n{inc['lessons_learned']}")

    lead = inc.get("lead_responder") or {}
    if isinstance(lead, dict) and lead.get("name"):
        parts.append(f"**Lead Responder**: {lead['name']} ({lead.get('id', 'N/A')})")

    # IR milestones
    milestones = [(f, inc[f]) for f in MILESTONE_FIELDS if inc.get(f)]
    if milestones:
        parts.append("\n**IR Milestones**:")
        parts.extend(f"- {f.removesuffix('_at').replace('_', ' ').title()}: {v}" for f, v in milestones)

    summary = inc.get("summary") or {}
    if summary:
        parts.append("\n**Overview**:")
        if summary.get("first_event_at"):
            parts.append(f"- First known activity: {summary['first_event_at']}")
        if summary.get("last_event_at"):
            parts.append(f"- Latest event: {summary['last_event_at']}")
        if summary.get("earliest_detection_at"):
            parts.append(f"- Earliest detection: {summary['earliest_detection_at']}")
        leads = summary.get("leads")
        if isinstance(leads, dict):
            parts.append(f"- Leads: {leads.get('open', 0)} open of {leads.get('total', 0)}")
        triage = summary.get("hosts_by_triage")
        if isinstance(triage, dict) and triage:
            parts.append("- Hosts by triage: " + ", ".join(f"{k} {v}" for k, v in sorted(triage.items())))

    return "\n".join(parts)


@mcp.tool()
async def sheetstorm_list_incidents(
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    search: Optional[str] = None,
    q: Optional[str] = None,
    sort: Optional[str] = None,
) -> str:
    """List incidents with optional filters and pagination.

    Args:
        page: Page number (default 1)
        per_page: Items per page (default 20, max 200)
        status: Filter by status; comma-separate several (open, investigating, contained, eradicated, recovered, closed)
        severity: Filter by severity; comma-separate several (critical, high, medium, low)
        search: Search term for title/description (legacy alias of q)
        q: Search term for title/description/incident number
        sort: Sort field, "-" prefix for descending, up to 2 comma-separated (created_at, updated_at, incident_number, title, severity, status, phase, detected_at). Default -created_at.
    """
    client = get_client()
    try:
        params: dict = {"page": page, "per_page": max(1, min(per_page, 200))}
        if status:
            params["status"] = status
        if severity:
            params["severity"] = severity
        if q:
            params["q"] = q
        elif search:
            params["search"] = search
        if sort:
            params["sort"] = sort

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
    tlp: str = "amber",
    team_id: Optional[str] = None,
    detected_at: Optional[str] = None,
    lead_responder_id: Optional[str] = None,
    case_template: Optional[str] = None,
) -> str:
    """Create a new incident.

    Args:
        title: Incident title (at least 3 characters)
        description: Incident description
        severity: Severity level (critical, high, medium, low)
        classification: Optional classification type
        phase: Ignored (new incidents always start in phase 1 = Preparation); kept for compatibility
        tlp: Traffic Light Protocol level (white, green, amber, amber_strict, red). Default: amber
        team_id: UUID of the owning team (optional; must be a team of your organization)
        detected_at: When the incident was detected, ISO 8601 (no offset = UTC). Default: now. Not in the future.
        lead_responder_id: UUID of the lead responder (an active user of your organization); they get the
            "Lead Responder" assignment and a notification
        case_template: Start from a case template ("builtin:<key>" or a template UUID from
            sheetstorm_list_case_templates): seeds questions, starter leads, a playbook and custom
            fields, and fills severity/TLP/classification you did not set
    """
    client = get_client()
    try:
        payload: dict = {
            "title": title,
            "description": description,
            "severity": severity,
            "phase": phase,
            "tlp": tlp,
        }
        if classification:
            payload["classification"] = classification
        if team_id:
            payload["team_id"] = team_id
        if detected_at:
            payload["detected_at"] = detected_at
        if lead_responder_id:
            payload["lead_responder_id"] = lead_responder_id
        if case_template:
            payload["case_template"] = case_template

        inc = await client.post("/incidents", json=payload)
        out = f"✓ Incident created:\n{_format_incident(inc)}"
        result = inc.get("case_template_result") if isinstance(inc, dict) else None
        if result:
            created = result.get("created") or {}
            out += (
                f"\n  Template applied: {created.get('questions', 0)} questions, "
                f"{created.get('leads', 0)} leads"
                + (f", playbook: {result['playbook'].get('name')}" if result.get("playbook") else "")
            )
        return out
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
    tlp: Optional[str] = None,
    team_id: Optional[str] = None,
    lead_responder_id: Optional[str] = None,
    first_malicious_at: Optional[str] = None,
    detected_at: Optional[str] = None,
    responded_at: Optional[str] = None,
    contained_at: Optional[str] = None,
    eradicated_at: Optional[str] = None,
    recovered_at: Optional[str] = None,
    closed_at: Optional[str] = None,
    clear_milestones: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> str:
    """Update incident details and IR milestones.

    Milestones must be in order first_malicious <= detected <= contained <=
    eradicated <= recovered <= closed, responded must not precede detected,
    and none may be more than 5 minutes in the future; the server rejects
    violations (nothing is saved).

    Args:
        incident_id: UUID of the incident
        title: New title
        description: New description (max 10000 characters)
        severity: New severity (critical, high, medium, low)
        classification: New classification
        executive_summary: Executive summary text (plain text, max 20000 characters)
        lessons_learned: Lessons learned text (plain text, max 20000 characters)
        tlp: Traffic Light Protocol level (white, green, amber, amber_strict, red)
        team_id: UUID of the owning team
        lead_responder_id: UUID of the new lead responder (notified, gets the "Lead Responder" assignment)
        first_malicious_at: Earliest known malicious activity, ISO 8601 (no offset = UTC)
        detected_at: Detection time, ISO 8601 (no offset = UTC)
        responded_at: First response time, ISO 8601 (set automatically on the first assignment or status change)
        contained_at: Containment time, ISO 8601
        eradicated_at: Eradication time, ISO 8601
        recovered_at: Recovery time, ISO 8601
        closed_at: Closure time, ISO 8601
        clear_milestones: Comma-separated milestones to clear, e.g. "recovered_at,closed_at"
        expected_version: Incident version you last read; the update fails with a conflict if it changed since
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
            ("tlp", tlp),
            ("team_id", team_id),
            ("lead_responder_id", lead_responder_id),
            ("first_malicious_at", first_malicious_at),
            ("detected_at", detected_at),
            ("responded_at", responded_at),
            ("contained_at", contained_at),
            ("eradicated_at", eradicated_at),
            ("recovered_at", recovered_at),
            ("closed_at", closed_at),
        ]:
            if value is not None:
                payload[field] = value
        for field in (clear_milestones or "").split(","):
            field = field.strip()
            if not field:
                continue
            if field not in MILESTONE_FIELDS:
                return f"✗ Unknown milestone '{field}'. Use: {', '.join(MILESTONE_FIELDS)}"
            if field in payload:
                return f"✗ '{field}' is both set and cleared."
            payload[field] = None

        if not payload:
            return "No fields to update. Provide at least one field."

        if expected_version is not None:
            payload["expected_version"] = expected_version
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
        status: New status (open, investigating, contained, eradicated, recovered, closed); the IR phase follows automatically
        phase: New IR phase (1=Preparation, 2=Identification, 3=Containment, 4=Eradication, 5=Recovery, 6=Lessons Learned)

    Entering contained/eradicated/recovered/closed stamps that milestone if it is
    empty; reopening a closed incident clears closed_at.
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
async def sheetstorm_archive_incident(incident_id: str) -> str:
    """Archive an incident (soft delete). The incident disappears from normal
    listings but all its data is kept and it can be restored with
    sheetstorm_unarchive_incident. Requires the incidents:archive permission.

    Args:
        incident_id: UUID of the incident to archive
    """
    client = get_client()
    try:
        await client.post(f"/incidents/{incident_id}/archive")
        return f"✓ Incident {incident_id} archived (restorable)."
    except SheetStormAPIError as exc:
        return f"✗ Error archiving incident: {exc}"


@mcp.tool()
async def sheetstorm_list_archived_incidents(
    page: int = 1,
    per_page: int = 20,
    search: Optional[str] = None,
    q: Optional[str] = None,
    sort: Optional[str] = None,
) -> str:
    """List archived incidents. Requires the incidents:archive permission.

    Args:
        page: Page number (default 1)
        per_page: Items per page (default 20, max 200)
        search: Search term for title/description (legacy alias of q)
        q: Search term for title/description/incident number
        sort: Sort field, "-" prefix for descending (archived_at, created_at, updated_at, title, severity, status, ...). Default -archived_at.
    """
    client = get_client()
    try:
        params: dict = {"page": page, "per_page": max(1, min(per_page, 200))}
        if q:
            params["q"] = q
        elif search:
            params["search"] = search
        if sort:
            params["sort"] = sort
        data = await client.get("/incidents/archived", params=params)
        items = data.get("items", [])
        if not items:
            return "No archived incidents found."
        lines = [f"**Archived Incidents** (page {page}, {len(items)} of {data.get('total', len(items))} total)\n"]
        for inc in items:
            lines.append(_format_incident(inc) + f"\n  Archived: {inc.get('archived_at', 'N/A')}")
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error listing archived incidents: {exc}"


@mcp.tool()
async def sheetstorm_unarchive_incident(incident_id: str) -> str:
    """Restore an archived incident to the active list. Requires incidents:archive.

    Args:
        incident_id: UUID of the archived incident
    """
    client = get_client()
    try:
        await client.post(f"/incidents/{incident_id}/unarchive")
        return f"✓ Incident {incident_id} restored from archive."
    except SheetStormAPIError as exc:
        return f"✗ Error restoring incident: {exc}"


PERMANENT_DELETE_CONFIRMATION = "DELETE PERMANENTLY"


@mcp.tool()
async def sheetstorm_permanently_delete_incident(incident_id: str, confirmation: str) -> str:
    """IRREVERSIBLY delete an ARCHIVED incident and all of its evidence records,
    timeline, IOCs and notes. Requires incidents:purge. The incident must be
    archived first (sheetstorm_archive_incident). Only call this after the user
    has explicitly asked for permanent deletion of this specific incident.

    Args:
        incident_id: UUID of the archived incident
        confirmation: Must be exactly "DELETE PERMANENTLY" — anything else aborts
    """
    if confirmation != PERMANENT_DELETE_CONFIRMATION:
        return (
            f"✗ Aborted: confirmation must be exactly '{PERMANENT_DELETE_CONFIRMATION}'. "
            "Prefer sheetstorm_archive_incident, which is reversible."
        )
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/permanent")
        return f"✓ Incident {incident_id} permanently deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error deleting incident: {exc}"


def _format_counts(counts: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))) or "none"


@mcp.tool()
async def sheetstorm_get_dashboard_stats() -> str:
    """Organization dashboard: counts over every incident you can access
    (totals, severity/status/phase/TLP breakdowns, MITRE ATT&CK tactic and
    technique counts from timeline events, open leads, hosts by triage).
    Counts only; no incident titles or ids.
    """
    client = get_client()
    try:
        data = await client.get("/dashboard/stats")
    except SheetStormAPIError as exc:
        return f"✗ Error loading dashboard stats: {exc}"

    inc = data.get("incidents") or {}
    lines = [
        "# Dashboard",
        f"**Incidents**: {inc.get('total', 0)} total, {inc.get('active', 0)} active, "
        f"{inc.get('closed', 0)} closed, {inc.get('critical', 0)} critical",
        f"**New**: {inc.get('created_7d', 0)} in 7 days, {inc.get('created_30d', 0)} in 30 days",
        f"**By severity**: {_format_counts(inc.get('by_severity') or {})}",
        f"**By status**: {_format_counts(inc.get('by_status') or {})}",
        f"**Open by phase**: {_format_counts(inc.get('by_phase_open') or {})}",
        f"**By TLP**: {_format_counts(inc.get('by_tlp') or {})}",
    ]
    dfir = data.get("dfir") or {}
    if dfir.get("open_leads") is not None:
        lines.append(f"**Open leads**: {dfir['open_leads']}")
    if dfir.get("hosts_by_triage") is not None:
        lines.append(f"**Hosts by triage**: {_format_counts(dfir['hosts_by_triage'])}")
    mitre = data.get("mitre")
    if mitre:
        lines.append(f"\n**MITRE ATT&CK** ({mitre.get('events_mapped', 0)}/{mitre.get('events_total', 0)} "
                     "events mapped)")
        for t in mitre.get("tactics") or []:
            lines.append(f"- {t.get('tactic')}: {t.get('count', 0)} ({_format_counts(t.get('techniques') or {})})")
    return "\n".join(lines)
