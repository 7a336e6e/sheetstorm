"""Case template tools — start and seed investigations from templates."""

from __future__ import annotations

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import get_client, mcp


def _format_template(t: dict) -> str:
    s = t.get("summary") or {}
    kind = "built-in" if t.get("is_builtin") else "organization"
    lines = [
        f"**{t.get('name', 'Unnamed')}** (ID: {t.get('id', 'N/A')}, {kind})",
        f"  Incident type: {t.get('incident_type') or 'any'} | {s.get('questions', 0)} questions, "
        f"{s.get('leads', 0)} leads, {s.get('custom_fields', 0)} custom fields"
        + (f", playbook: {s['playbook']}" if s.get("playbook") else ""),
    ]
    if t.get("description"):
        lines.append(f"  {t['description']}")
    return "\n".join(lines)


@mcp.tool()
async def sheetstorm_list_case_templates() -> str:
    """List the case templates you can start an incident from (built-in and your
    organization's). Pass a template's ID to sheetstorm_create_incident
    (case_template) or sheetstorm_apply_case_template."""
    client = get_client()
    try:
        data = await client.get("/case-templates")
        items = data.get("items", []) if isinstance(data, dict) else data
        if not items:
            return "No case templates available."
        lines = [f"**Case Templates** ({len(items)})\n"]
        for t in items:
            lines.append(_format_template(t))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_apply_case_template(
    incident_id: str,
    template_id: str,
    apply_defaults: bool = False,
    dry_run: bool = False,
) -> str:
    """Apply a case template to an existing incident: adds its questions and
    starter leads, activates its playbook (unless one is already active) and
    its custom-field definitions. Safe to repeat: whatever already exists is
    skipped. Use dry_run to preview.

    Args:
        incident_id: UUID of the incident
        template_id: Template ID from sheetstorm_list_case_templates ("builtin:<key>" or a UUID)
        apply_defaults: Also raise severity/TLP to the template defaults and set an empty classification
            (never lowers anything). Default: false
        dry_run: Only report what would be created or skipped (default: false)
    """
    client = get_client()
    try:
        data = await client.post(
            f"/incidents/{incident_id}/case-templates/{template_id}/apply",
            json={"apply_defaults": apply_defaults, "dry_run": dry_run},
        )
        created = data.get("created") or {}
        lines = [
            f"✓ {'Dry run' if data.get('dry_run') else 'Applied'}: "
            f"{(data.get('template') or {}).get('name', template_id)}",
            f"  Created: {created.get('questions', 0)} questions, {created.get('leads', 0)} leads, "
            f"{created.get('links', 0)} question-lead links",
        ]
        playbook = data.get("playbook")
        if playbook:
            lines.append(f"  Playbook: {playbook.get('name')} ({playbook.get('status')})")
        for d in data.get("defaults_applied") or []:
            lines.append(f"  Default applied: {d.get('field')} {d.get('from')} -> {d.get('to')}")
        if data.get("custom_fields_added"):
            lines.append(f"  Custom fields added: {data['custom_fields_added']}")
        skipped = data.get("skipped") or []
        if skipped:
            lines.append(f"  Skipped ({len(skipped)}):")
            for s in skipped[:20]:
                lines.append(f"    - {s.get('kind')} {s.get('ref')}: {s.get('reason')}")
            if len(skipped) > 20:
                lines.append(f"    ... and {len(skipped) - 20} more")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
