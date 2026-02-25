"""Report generation tools — PDF, AI-generated, and listing."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


def _format_report(r: dict) -> str:
    parts = [
        f"**{r.get('title', r.get('report_type', 'Report'))}** (ID: {r.get('id', 'N/A')})",
        f"  Type: {r.get('report_type', 'N/A')} | Format: {r.get('format', 'N/A')}",
        f"  Created: {r.get('created_at', 'N/A')}",
    ]
    if r.get("file_size"):
        parts.append(f"  Size: {r['file_size']} bytes")
    if r.get("status"):
        parts.append(f"  Status: {r['status']}")
    return "\n".join(parts)


@mcp.tool()
async def sheetstorm_list_reports(incident_id: str) -> str:
    """List generated reports for an incident.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/reports")
        items = data if isinstance(data, list) else data.get("items", data.get("reports", []))

        if not items:
            return "No reports found for this incident."

        lines = [f"**Reports** ({len(items)})\n"]
        for r in items:
            lines.append(_format_report(r))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_generate_pdf_report(
    incident_id: str,
    report_type: str = "full",
    sections: Optional[str] = None,
) -> str:
    """Generate a PDF report for an incident.

    Args:
        incident_id: UUID of the incident
        report_type: Report type (full, executive, technical, timeline)
        sections: Comma-separated list of sections to include (e.g. "summary,timeline,hosts,iocs")
    """
    client = get_client()
    try:
        payload: dict = {"report_type": report_type}
        if sections:
            payload["sections"] = [s.strip() for s in sections.split(",")]

        result = await client.post(f"/incidents/{incident_id}/reports/generate-pdf", json=payload)
        return f"✓ PDF report generated:\n{_format_report(result)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_generate_ai_report(
    incident_id: str,
    report_type: str = "executive",
    additional_context: Optional[str] = None,
) -> str:
    """Generate an AI-written incident report using the backend AI service.

    Args:
        incident_id: UUID of the incident
        report_type: Report type (executive, technical, lessons_learned)
        additional_context: Extra context for the AI to consider
    """
    client = get_client()
    try:
        payload: dict = {"report_type": report_type}
        if additional_context:
            payload["additional_context"] = additional_context

        result = await client.post(f"/incidents/{incident_id}/reports/ai-generate", json=payload)

        if isinstance(result, dict) and result.get("content"):
            content = result["content"]
            preview = content[:500] + "..." if len(content) > 500 else content
            return f"✓ AI report generated ({report_type}):\n\n{preview}"

        return f"✓ AI report generated:\n{_format_report(result)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
