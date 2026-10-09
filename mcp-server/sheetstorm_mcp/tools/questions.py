"""Investigative question tools — the answerable questions of an investigation."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import get_client, mcp

STATUSES = {"open", "in_progress", "answered", "unanswerable"}


def _render_evidence(evidence: list) -> str:
    out = []
    for e in evidence or []:
        if not isinstance(e, dict):
            continue
        etype, eid = e.get("evidence_type", "?"), e.get("evidence_id", "?")
        if e.get("missing"):
            out.append(f"{etype}:{eid} (deleted)")
        elif e.get("restricted") or not e.get("label"):
            out.append(f"{etype}:{eid}")
        else:
            out.append(f'{etype} "{e["label"]}" ({eid})')
    return ", ".join(out)


def _format_question(q: dict, with_incident: bool = False) -> str:
    lines = [f"**{q.get('question', 'Untitled')}** (ID: {q.get('id', 'N/A')})"]
    meta = f"  Status: {q.get('status', 'N/A')} | Priority: {q.get('priority', 'N/A')}"
    if q.get("phase"):
        meta += f" | Phase: {q['phase']}"
    if q.get("facet"):
        meta += f" | Facet: {q['facet']}"
    lines.append(meta)
    if with_incident and q.get("incident"):
        inc = q["incident"]
        lines.append(f"  Incident: #{inc.get('incident_number')} {inc.get('title')} (ID: {inc.get('id')})")
    if q.get("owner"):
        lines.append(f"  Owner: {q['owner'].get('name')}")
    if q.get("answer"):
        lines.append(f"  Answer ({q.get('confidence') or 'no confidence set'}): {q['answer']}")
    if q.get("evidence"):
        lines.append(f"  Evidence: {_render_evidence(q['evidence'])}")
    if q.get("lead_ids"):
        lines.append(f"  Leads: {', '.join(q['lead_ids'])}")
    if q.get("version") is not None:
        lines.append(f"  Version: {q['version']}")
    return "\n".join(lines)


@mcp.tool()
async def sheetstorm_list_open_questions(
    incident_id: Optional[str] = None,
    status: str = "open,in_progress",
    limit: int = 50,
) -> str:
    """List investigative questions that still need an answer.

    With an incident_id this lists that incident's questions (plus its
    progress summary); without one it lists questions across every incident
    you can access (most urgent first).

    Args:
        incident_id: UUID of the incident (optional; omit for all accessible incidents)
        status: Comma-separated statuses to include: open, in_progress, answered, unanswerable.
            Default: open,in_progress
        limit: Maximum number of questions to return (default 50, max 200)
    """
    client = get_client()
    try:
        params = {"status": status, "per_page": str(max(1, min(int(limit), 200)))}
        if incident_id:
            data = await client.get(f"/incidents/{incident_id}/questions", params=params)
        else:
            data = await client.get("/questions", params=params)
        items = data.get("items", []) if isinstance(data, dict) else data
        if not items:
            return "No matching questions."
        lines = [f"**Questions** ({data.get('total', len(items))} match, showing {len(items)})"]
        summary = data.get("summary") if isinstance(data, dict) else None
        if summary:
            lines.append(
                f"Progress: {summary.get('resolved', 0)}/{summary.get('total', 0)} resolved, "
                f"{summary.get('open_high_priority', 0)} high-priority open"
            )
        lines.append("")
        for q in items:
            lines.append(_format_question(q, with_incident=incident_id is None))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_answer_question(
    incident_id: str,
    question_id: str,
    answer: str,
    confidence: str,
    status: str = "answered",
    evidence_refs: Optional[list[dict]] = None,
    expected_version: Optional[int] = None,
) -> str:
    """Record the answer to an investigative question.

    An answered question needs an answer and a confidence; confidence
    "confirmed" also needs at least one evidence reference. Use status
    "unanswerable" with the answer as the rationale when it cannot be answered.

    Args:
        incident_id: UUID of the incident
        question_id: UUID of the question
        answer: The answer (markdown text, max 20000 characters)
        confidence: low, medium, high or confirmed
        status: answered (default), unanswerable, in_progress or open
        evidence_refs: Records that support the answer, e.g.
            [{"evidence_type": "host", "evidence_id": "<uuid>"}]. Types: timeline_event, host, account,
            network_ioc, host_ioc, malware, artifact, evidence_item, case_note, task. Replaces the list.
        expected_version: Version you last read (the server returns 409 if the question changed since)
    """
    client = get_client()
    try:
        payload: dict = {"answer": answer, "confidence": confidence, "status": status}
        if evidence_refs is not None:
            payload["evidence_refs"] = evidence_refs
        if expected_version is not None:
            payload["expected_version"] = expected_version
        q = await client.put(f"/incidents/{incident_id}/questions/{question_id}", json=payload)
        return f"✓ Question updated:\n{_format_question(q)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_add_question(
    incident_id: str,
    question: Optional[str] = None,
    library_ref: Optional[str] = None,
    facet: Optional[str] = None,
    phase: Optional[int] = None,
    priority: str = "medium",
    owner_id: Optional[str] = None,
) -> str:
    """Add an investigative question to an incident: your own text, or one from
    the built-in library (e.g. library_ref "ss:SSQ-006"). A question already on
    the incident is not added twice.

    Args:
        incident_id: UUID of the incident
        question: The question text (required unless library_ref is given)
        library_ref: Library question id such as "ss:SSQ-006" or "dfiq:Q1058"
        facet: Grouping label, e.g. "Initial Access"
        phase: IR phase 1-6 the question belongs to
        priority: low, medium, high or critical (default medium)
        owner_id: UUID of the user who owns the question
    """
    client = get_client()
    try:
        payload: dict = {"priority": priority}
        if library_ref:
            payload["library_ref"] = library_ref
        elif question:
            payload["question"] = question
        else:
            return "✗ Error: give either question or library_ref."
        if facet:
            payload["facet"] = facet
        if phase is not None:
            payload["phase"] = phase
        if owner_id:
            payload["owner_id"] = owner_id
        q = await client.post(f"/incidents/{incident_id}/questions", json=payload)
        return f"✓ Question added:\n{_format_question(q)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_question_report(incident_id: str) -> str:
    """Get the investigation's questions grouped for a report: answered,
    unanswerable and still-open questions with their evidence and the leads
    that informed them.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/questions/report-data")
        s = data.get("summary") or {}
        lines = [
            f"**Investigative questions** — {s.get('resolved', 0)}/{s.get('total', 0)} resolved "
            f"({s.get('answered', 0)} answered, {s.get('unanswerable', 0)} unanswerable, "
            f"{s.get('open', 0) + s.get('in_progress', 0)} open)",
        ]
        for title, key in (("Answered", "answered"), ("Unanswerable", "unanswerable"), ("Open", "open")):
            items = data.get(key) or []
            if not items:
                continue
            lines.append(f"\n### {title} ({len(items)})")
            for q in items:
                lines.append(_format_question(q))
                for lead in q.get("leads") or []:
                    outcome = f", outcome: {lead['lead_outcome']}" if lead.get("lead_outcome") else ""
                    lines.append(f"  Lead: {lead.get('title')} ({lead.get('status')}{outcome})")
                lines.append("")
        if data.get("attribution"):
            lines.append(data["attribution"])
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
