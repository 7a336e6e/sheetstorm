"""Task management tools — manage tasks within incidents."""

from __future__ import annotations

import json
from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import get_client, mcp


def _parse_evidence_refs(raw: Optional[str]) -> list | None:
    """Parse the evidence_refs JSON argument; raises ValueError when malformed."""
    if raw is None:
        return None
    refs = json.loads(raw) if raw.strip() else []
    if not isinstance(refs, list) or not all(isinstance(r, dict) for r in refs):
        raise ValueError("evidence_refs must be a JSON array of objects")
    return refs


def _format_task(t: dict) -> str:
    """Format a task."""
    parts = [
        f"**{t.get('title', 'Untitled')}** (ID: {t.get('id', 'N/A')})",
        f"  Status: {t.get('status', 'N/A')} | Priority: {t.get('priority', 'N/A')} | "
        f"Type: {t.get('task_type') or 'action_item'}",
    ]
    if t.get("lead_outcome"):
        parts.append(f"  Lead outcome: {t['lead_outcome']}")
    if t.get("investigation_direction"):
        parts.append(f"  Investigation direction: {t['investigation_direction']}")
    refs = t.get("evidence_refs") or []
    if refs:
        rendered = ", ".join(
            f"{r.get('evidence_type', '?')}:{r.get('evidence_id', '?')}" if isinstance(r, dict) else str(r)
            for r in refs
        )
        parts.append(f"  Evidence: {rendered}")
    assignee = t.get("assignee")
    if isinstance(assignee, dict):
        parts.append(f"  Assignee: {assignee.get('name', assignee.get('email', 'Unknown'))}")
    elif assignee:
        parts.append(f"  Assignee: {assignee}")
    if t.get("due_date"):
        parts.append(f"  Due: {t['due_date']}")
    if t.get("phase"):
        parts.append(f"  Phase: {t['phase']}")
    if t.get("description"):
        desc = t["description"][:100] + ("..." if len(t["description"]) > 100 else "")
        parts.append(f"  Description: {desc}")
    progress = t.get("checklist_progress")
    if progress:
        parts.append(f"  Checklist: {progress.get('completed', 0)}/{progress.get('total', 0)} ({progress.get('percentage', 0)}%)")
    return "\n".join(parts)


@mcp.tool()
async def sheetstorm_list_tasks(
    incident_id: str,
    status: Optional[str] = None,
    assignee_id: Optional[str] = None,
    priority: Optional[str] = None,
    phase: Optional[int] = None,
    task_type: Optional[str] = None,
) -> str:
    """List tasks for an incident, including DFIR fields (task type, lead outcome,
    investigation direction, evidence references).

    Args:
        incident_id: UUID of the incident
        status: Filter by status (pending, in_progress, completed, blocked, cancelled)
        assignee_id: Filter by assignee UUID
        priority: Filter by priority (low, medium, high, critical)
        phase: Filter by IR phase (1-6)
        task_type: Only show this task type (action_item, investigative_lead, verification, documentation, reporting)
    """
    client = get_client()
    try:
        params: dict = {"per_page": 200}
        if status:
            params["status"] = status
        if assignee_id:
            params["assignee_id"] = assignee_id
        if priority:
            params["priority"] = priority
        if phase is not None:
            params["phase"] = phase

        data = await client.get(f"/incidents/{incident_id}/tasks", params=params)
        items = data if isinstance(data, list) else data.get("items", data.get("tasks", []))
        if task_type:
            items = [t for t in items if (t.get("task_type") or "action_item") == task_type]

        if not items:
            return "No tasks found."

        lines = [f"**Tasks** ({len(items)} total)\n"]
        for t in items:
            lines.append(_format_task(t))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_create_task(
    incident_id: str,
    title: str,
    description: Optional[str] = None,
    priority: str = "medium",
    assignee_id: Optional[str] = None,
    due_date: Optional[str] = None,
    phase: Optional[int] = None,
    task_type: Optional[str] = None,
    lead_outcome: Optional[str] = None,
    investigation_direction: Optional[str] = None,
    evidence_refs: Optional[str] = None,
) -> str:
    """Create a new task for an incident. Use task_type="investigative_lead" to track
    an investigative lead (hypothesis to prove/disprove) and record its outcome later.

    Args:
        incident_id: UUID of the incident
        title: Task title
        description: Task description
        priority: Priority (low, medium, high, critical)
        assignee_id: UUID of the user to assign
        due_date: Due date in ISO format (YYYY-MM-DD)
        phase: IR phase (1-6)
        task_type: One of: action_item (default), investigative_lead, verification, documentation, reporting
        lead_outcome: For leads — one of: false_positive, confirmed_malicious, inconclusive, resolved
        investigation_direction: Free text: what this lead/task is trying to establish
        evidence_refs: JSON array linking evidence, e.g. [{"evidence_type": "artifact", "evidence_id": "<uuid>"}]
    """
    client = get_client()
    try:
        try:
            refs = _parse_evidence_refs(evidence_refs)
        except ValueError as exc:
            return f"✗ Error: invalid evidence_refs — {exc}"
        payload: dict = {"title": title, "priority": priority}
        if task_type:
            payload["task_type"] = task_type
        if lead_outcome:
            payload["lead_outcome"] = lead_outcome
        if investigation_direction:
            payload["investigation_direction"] = investigation_direction
        if refs is not None:
            payload["evidence_refs"] = refs
        if description:
            payload["description"] = description
        if assignee_id:
            payload["assignee_id"] = assignee_id
        if due_date:
            payload["due_date"] = due_date
        if phase is not None:
            payload["phase"] = phase

        task = await client.post(f"/incidents/{incident_id}/tasks", json=payload)
        return f"✓ Task created:\n{_format_task(task)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_task(
    incident_id: str,
    task_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee_id: Optional[str] = None,
    due_date: Optional[str] = None,
    phase: Optional[int] = None,
    task_type: Optional[str] = None,
    lead_outcome: Optional[str] = None,
    investigation_direction: Optional[str] = None,
    evidence_refs: Optional[str] = None,
) -> str:
    """Update an existing task (including its DFIR lead fields).

    Args:
        incident_id: UUID of the incident
        task_id: UUID of the task
        title: New title
        description: New description
        status: New status (pending, in_progress, completed, blocked, cancelled)
        priority: New priority (low, medium, high, critical)
        assignee_id: New assignee UUID
        due_date: New due date (YYYY-MM-DD)
        phase: New IR phase (1-6)
        task_type: One of: action_item, investigative_lead, verification, documentation, reporting
        lead_outcome: One of: false_positive, confirmed_malicious, inconclusive, resolved
        investigation_direction: What this lead/task is trying to establish
        evidence_refs: JSON array replacing the evidence links, e.g. [{"evidence_type": "artifact", "evidence_id": "<uuid>"}]
    """
    client = get_client()
    try:
        try:
            refs = _parse_evidence_refs(evidence_refs)
        except ValueError as exc:
            return f"✗ Error: invalid evidence_refs — {exc}"
        payload: dict = {}
        if refs is not None:
            payload["evidence_refs"] = refs
        for field, value in [
            ("title", title),
            ("description", description),
            ("status", status),
            ("priority", priority),
            ("assignee_id", assignee_id),
            ("due_date", due_date),
            ("phase", phase),
            ("task_type", task_type),
            ("lead_outcome", lead_outcome),
            ("investigation_direction", investigation_direction),
        ]:
            if value is not None:
                payload[field] = value

        if not payload:
            return "No fields to update."

        task = await client.put(f"/incidents/{incident_id}/tasks/{task_id}", json=payload)
        return f"✓ Task updated:\n{_format_task(task)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_delete_task(incident_id: str, task_id: str) -> str:
    """Delete a task.

    Args:
        incident_id: UUID of the incident
        task_id: UUID of the task to delete
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/tasks/{task_id}")
        return f"✓ Task {task_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_add_task_comment(incident_id: str, task_id: str, content: str) -> str:
    """Add a comment to a task.

    Args:
        incident_id: UUID of the incident
        task_id: UUID of the task
        content: Comment text
    """
    client = get_client()
    try:
        comment = await client.post(
            f"/incidents/{incident_id}/tasks/{task_id}/comments",
            json={"content": content},
        )
        author = comment.get("author", {})
        author_name = author.get("name", "You") if isinstance(author, dict) else "You"
        return (
            f"✓ Comment added by {author_name}\n"
            f"  {comment.get('content', content)}\n"
            f"  at {comment.get('created_at', 'now')}"
        )
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_list_task_comments(incident_id: str, task_id: str) -> str:
    """List comments on a task.

    Args:
        incident_id: UUID of the incident
        task_id: UUID of the task
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/tasks/{task_id}/comments")
        comments = data if isinstance(data, list) else data.get("items", data.get("comments", []))

        if not comments:
            return "No comments on this task."

        lines = [f"**Task Comments** ({len(comments)})\n"]
        for c in comments:
            author = c.get("author", {})
            author_name = author.get("name", "Unknown") if isinstance(author, dict) else "Unknown"
            lines.append(
                f"[{c.get('created_at', 'N/A')}] **{author_name}**: "
                f"{c.get('content', 'N/A')}"
            )
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
