"""Task management tools — manage tasks within incidents."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


def _format_task(t: dict) -> str:
    """Format a task."""
    parts = [
        f"**{t.get('title', 'Untitled')}** (ID: {t.get('id', 'N/A')})",
        f"  Status: {t.get('status', 'N/A')} | Priority: {t.get('priority', 'N/A')}",
    ]
    if t.get("assignee_name") or t.get("assignee"):
        assignee = t.get("assignee_name") or t.get("assignee", {}).get("name", "Unassigned")
        parts.append(f"  Assignee: {assignee}")
    if t.get("due_date"):
        parts.append(f"  Due: {t['due_date']}")
    if t.get("description"):
        desc = t["description"][:100] + ("..." if len(t["description"]) > 100 else "")
        parts.append(f"  Description: {desc}")
    return "\n".join(parts)


@mcp.tool()
async def sheetstorm_list_tasks(
    incident_id: str,
    status: Optional[str] = None,
    assignee_id: Optional[str] = None,
) -> str:
    """List tasks for an incident.

    Args:
        incident_id: UUID of the incident
        status: Filter by status (pending, in_progress, completed)
        assignee_id: Filter by assignee UUID
    """
    client = get_client()
    try:
        params: dict = {}
        if status:
            params["status"] = status
        if assignee_id:
            params["assignee_id"] = assignee_id

        data = await client.get(f"/incidents/{incident_id}/tasks", params=params)
        items = data if isinstance(data, list) else data.get("items", data.get("tasks", []))

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
) -> str:
    """Create a new task for an incident.

    Args:
        incident_id: UUID of the incident
        title: Task title
        description: Task description
        priority: Priority (low, medium, high, critical)
        assignee_id: UUID of the user to assign
        due_date: Due date in ISO format (YYYY-MM-DD)
        phase: IR phase (1-6)
    """
    client = get_client()
    try:
        payload: dict = {"title": title, "priority": priority}
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
) -> str:
    """Update an existing task.

    Args:
        incident_id: UUID of the incident
        task_id: UUID of the task
        title: New title
        description: New description
        status: New status (pending, in_progress, completed)
        priority: New priority
        assignee_id: New assignee UUID
        due_date: New due date
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, value in [
            ("title", title),
            ("description", description),
            ("status", status),
            ("priority", priority),
            ("assignee_id", assignee_id),
            ("due_date", due_date),
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
        return (
            f"✓ Comment added by {comment.get('author_name', 'You')}\n"
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
        comments = data if isinstance(data, list) else data.get("comments", [])

        if not comments:
            return "No comments on this task."

        lines = [f"**Task Comments** ({len(comments)})\n"]
        for c in comments:
            lines.append(
                f"[{c.get('created_at', 'N/A')}] **{c.get('author_name', 'Unknown')}**: "
                f"{c.get('content', 'N/A')}"
            )
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
