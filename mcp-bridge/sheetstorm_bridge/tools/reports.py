"""Report tools — PDF generation and AI-powered report generation."""

from __future__ import annotations

from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import mcp, get_client


def _format_report(r: dict) -> str:
    return (
        f"**{r.get('title', r.get('report_type', 'Report'))}** (ID: {r.get('id', 'N/A')})\n"
        f"  Type: {r.get('report_type', 'N/A')} | Format: {r.get('format', 'N/A')}\n"
        f"  Created: {r.get('created_at', 'N/A')} | "
        f"Status: {r.get('status', 'N/A')}"
    )


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
            return "No reports found."

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
) -> str:
    """Generate a PDF report for an incident.

    Args:
        incident_id: UUID of the incident
        report_type: Report type (full, executive, technical, timeline)
    """
    client = get_client()
    try:
        data = await client.post(
            f"/incidents/{incident_id}/reports/generate-pdf",
            json={"report_type": report_type},
        )
        return f"✓ PDF report generated:\n{_format_report(data)}" if isinstance(data, dict) and data.get("id") else f"✓ PDF report generation initiated. {data}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_generate_ai_report(
    incident_id: str,
    report_type: str = "full",
    additional_context: Optional[str] = None,
) -> str:
    """Generate an AI-powered incident report.

    Args:
        incident_id: UUID of the incident
        report_type: Report type (full, executive, technical, lessons_learned)
        additional_context: Extra context or instructions for the AI
    """
    client = get_client()
    try:
        payload: dict = {"report_type": report_type}
        if additional_context:
            payload["additional_context"] = additional_context
        data = await client.post(
            f"/incidents/{incident_id}/reports/ai-generate",
            json=payload,
        )
        # Show preview of content if available
        content = data.get("content", "")
        preview = content[:2000] + "..." if len(content) > 2000 else content
        parts = [f"✓ AI report generated (type: {report_type})"]
        if data.get("id"):
            parts.append(f"  Report ID: {data['id']}")
        if preview:
            parts.append(f"\n---\n{preview}")
        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
