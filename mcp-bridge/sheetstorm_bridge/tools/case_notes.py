"""Case notes tools — investigator notes linked to incidents."""

from __future__ import annotations

from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import mcp, get_client

CATEGORIES = [
    "general",
    "analysis",
    "containment",
    "eradication",
    "recovery",
    "lessons_learned",
    "evidence",
    "communication",
]


def _format_note(n: dict) -> str:
    return (
        f"**{n.get('title', 'Untitled')}** (ID: {n.get('id', 'N/A')})\n"
        f"  Category: {n.get('category', 'general')} | "
        f"Created: {n.get('created_at', 'N/A')}\n"
        f"  Author: {n.get('author', n.get('created_by', 'N/A'))}"
    )


def _format_note_detail(n: dict) -> str:
    header = _format_note(n)
    content = n.get("content", "No content.")
    kill_chain = n.get("kill_chain_phase", "")
    parts = [header]
    if kill_chain:
        parts.append(f"  Kill Chain Phase: {kill_chain}")
    parts.append(f"\n{content}")
    return "\n".join(parts)


@mcp.tool()
async def sheetstorm_list_case_notes(
    incident_id: str,
    category: Optional[str] = None,
) -> str:
    """List case notes for an incident.

    Args:
        incident_id: UUID of the incident
        category: Filter by category (general, analysis, containment, eradication, recovery, lessons_learned, evidence, communication)
    """
    client = get_client()
    try:
        params: dict = {}
        if category:
            params["category"] = category
        data = await client.get(f"/incidents/{incident_id}/notes", params=params)
        items = data if isinstance(data, list) else data.get("items", data.get("notes", []))

        if not items:
            return "No case notes found."

        lines = [f"**Case Notes** ({len(items)})\n"]
        for n in items:
            lines.append(_format_note(n))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_case_note(incident_id: str, note_id: str) -> str:
    """Get full details of a case note.

    Args:
        incident_id: UUID of the incident
        note_id: UUID of the case note
    """
    client = get_client()
    try:
        note = await client.get(f"/incidents/{incident_id}/notes/{note_id}")
        return _format_note_detail(note)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_create_case_note(
    incident_id: str,
    title: str,
    content: str,
    category: str = "general",
    kill_chain_phase: Optional[str] = None,
) -> str:
    """Create a new case note.

    Args:
        incident_id: UUID of the incident
        title: Note title
        content: Markdown content of the note
        category: Category (general, analysis, containment, eradication, recovery, lessons_learned, evidence, communication)
        kill_chain_phase: Optional kill chain phase
    """
    client = get_client()
    try:
        payload: dict = {"title": title, "content": content, "category": category}
        if kill_chain_phase:
            payload["kill_chain_phase"] = kill_chain_phase
        note = await client.post(f"/incidents/{incident_id}/notes", json=payload)
        return f"✓ Case note created:\n{_format_note_detail(note)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_case_note(
    incident_id: str,
    note_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    category: Optional[str] = None,
    kill_chain_phase: Optional[str] = None,
) -> str:
    """Update a case note.

    Args:
        incident_id: UUID of the incident
        note_id: UUID of the note
        title: New title
        content: New markdown content
        category: New category
        kill_chain_phase: New kill chain phase
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, val in [
            ("title", title),
            ("content", content),
            ("category", category),
            ("kill_chain_phase", kill_chain_phase),
        ]:
            if val is not None:
                payload[field] = val
        if not payload:
            return "No fields to update."
        note = await client.put(f"/incidents/{incident_id}/notes/{note_id}", json=payload)
        return f"✓ Case note updated:\n{_format_note_detail(note)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_delete_case_note(incident_id: str, note_id: str) -> str:
    """Delete a case note.

    Args:
        incident_id: UUID of the incident
        note_id: UUID of the note to delete
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/notes/{note_id}")
        return f"✓ Case note {note_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
