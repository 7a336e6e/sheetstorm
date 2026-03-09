"""Case notes tools — create, read, update, and delete case notes within incidents."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client

# Valid note categories — keep in sync with CaseNote.CATEGORIES in the backend
CATEGORIES = [
    "general",
    "forensic",
    "communication",
    "evidence",
    "remediation",
    "legal",
    "executive",
]


def _format_note(n: dict) -> str:
    """Format a single case note into a readable string."""
    pinned = " 📌" if n.get("is_pinned") else ""
    return (
        f"**{n.get('title', 'Untitled')}**{pinned} (ID: {n.get('id', 'N/A')})\n"
        f"  Category: {n.get('category', 'N/A')} | "
        f"Created: {n.get('created_at', 'N/A')}\n"
        f"  {(n.get('content', '') or '')[:200]}"
    )


def _format_note_detail(n: dict) -> str:
    """Format full case note details."""
    pinned = " (pinned)" if n.get("is_pinned") else ""
    parts = [
        f"# {n.get('title', 'Untitled')}{pinned}",
        f"**ID**: {n.get('id', 'N/A')}",
        f"**Category**: {n.get('category', 'N/A')}",
        f"**Created**: {n.get('created_at', 'N/A')}",
        f"**Updated**: {n.get('updated_at', 'N/A')}",
    ]
    if n.get("content"):
        parts.append(f"\n**Content**:\n{n['content']}")
    return "\n".join(parts)


@mcp.tool()
async def sheetstorm_list_case_notes(
    incident_id: str,
    category: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> str:
    """List case notes for an incident with optional category filter.

    Args:
        incident_id: UUID of the incident
        category: Optional filter — one of: general, forensic, communication, evidence, remediation, legal, executive
        page: Page number (default 1)
        per_page: Items per page (default 50, max 100)
    """
    client = get_client()
    try:
        params: dict = {"page": page, "per_page": per_page}
        if category:
            params["category"] = category

        data = await client.get(f"/incidents/{incident_id}/notes", params=params)
        items = data.get("items", [])
        total = data.get("total", len(items))

        if not items:
            return "No case notes found."

        lines = [f"**Case Notes** (showing {len(items)} of {total})\n"]
        for n in items:
            lines.append(_format_note(n))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error listing case notes: {exc}"


@mcp.tool()
async def sheetstorm_get_case_note(
    incident_id: str,
    note_id: str,
) -> str:
    """Get full details of a specific case note.

    Args:
        incident_id: UUID of the incident
        note_id: UUID of the case note
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/notes/{note_id}")
        return _format_note_detail(data)
    except SheetStormAPIError as exc:
        return f"✗ Error retrieving case note: {exc}"


@mcp.tool()
async def sheetstorm_create_case_note(
    incident_id: str,
    title: str,
    content: str,
    category: str = "general",
    is_pinned: bool = False,
) -> str:
    """Create a new case note for an incident.

    Args:
        incident_id: UUID of the incident
        title: Note title
        content: Note content (Markdown supported)
        category: Note category — one of: general, forensic, communication, evidence, remediation, legal, executive
        is_pinned: Pin the note to the top (default false)
    """
    client = get_client()
    try:
        payload = {
            "title": title,
            "content": content,
            "category": category,
            "is_pinned": is_pinned,
        }
        data = await client.post(f"/incidents/{incident_id}/notes", json=payload)
        return f"✓ Case note created: **{data.get('title')}** (ID: {data.get('id')})"
    except SheetStormAPIError as exc:
        return f"✗ Error creating case note: {exc}"


@mcp.tool()
async def sheetstorm_update_case_note(
    incident_id: str,
    note_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    category: Optional[str] = None,
    is_pinned: Optional[bool] = None,
) -> str:
    """Update an existing case note.

    Args:
        incident_id: UUID of the incident
        note_id: UUID of the case note to update
        title: New title (optional)
        content: New content (optional, Markdown supported)
        category: New category (optional) — one of: general, forensic, communication, evidence, remediation, legal, executive
        is_pinned: Pin or unpin the note (optional)
    """
    client = get_client()
    try:
        payload: dict = {}
        if title is not None:
            payload["title"] = title
        if content is not None:
            payload["content"] = content
        if category is not None:
            payload["category"] = category
        if is_pinned is not None:
            payload["is_pinned"] = is_pinned

        if not payload:
            return "✗ No fields to update — provide at least one of: title, content, category, is_pinned."

        data = await client.put(f"/incidents/{incident_id}/notes/{note_id}", json=payload)
        return f"✓ Case note updated: **{data.get('title')}** (ID: {data.get('id')})"
    except SheetStormAPIError as exc:
        return f"✗ Error updating case note: {exc}"


@mcp.tool()
async def sheetstorm_delete_case_note(
    incident_id: str,
    note_id: str,
) -> str:
    """Delete a case note (soft-delete).

    Args:
        incident_id: UUID of the incident
        note_id: UUID of the case note to delete
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/notes/{note_id}")
        return f"✓ Case note {note_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error deleting case note: {exc}"
