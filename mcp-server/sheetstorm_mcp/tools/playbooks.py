"""IR playbook tools — phase-gated runbook templates and their per-incident state."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import get_client, mcp

PHASE_NAMES = {
    1: "Preparation", 2: "Identification", 3: "Containment",
    4: "Eradication", 5: "Recovery", 6: "Lessons Learned",
}


def _format_template(p: dict, detail: bool = False) -> str:
    phases = (p.get("definition") or {}).get("phases", [])
    lines = [
        f"**{p.get('name', 'Unnamed')}** (ID: {p.get('id', 'N/A')})",
        f"  Incident type: {p.get('incident_type') or 'any'} | Phases defined: {len(phases)}",
    ]
    if p.get("description"):
        lines.append(f"  {p['description']}")
    if detail:
        for ph in phases:
            lines.append(_format_phase(ph, {}))
    return "\n".join(lines)


def _format_phase(ph: dict, task_state: dict, current: int | None = None) -> str:
    num = ph.get("phase")
    marker = " ◀ current" if current is not None and num == current else ""
    lines = [f"\n### Phase {num}: {ph.get('name') or PHASE_NAMES.get(num, '')}{marker}"]
    for i, t in enumerate(ph.get("tasks") or []):
        key = f"{num}:{i}"
        done = "x" if task_state.get(key) else " "
        owner = f" (owner: {t['owner_role']})" if t.get("owner_role") else ""
        lines.append(f"- [{done}] {t.get('title', 'Untitled')}{owner} — task_key `{key}`")
    for a in ph.get("actions") or []:
        auto = " [auto-run on phase entry]" if a.get("auto_run") else ""
        lines.append(
            f"- action `{a.get('key')}`: {a.get('name', a.get('type'))} ({a.get('type')}){auto}"
        )
    return "\n".join(lines)


def _format_instance(inst: dict | None) -> str:
    if not inst:
        return "No playbook is active on this incident."
    state = inst.get("state") or {}
    current = inst.get("current_phase")
    lines = [
        f"**Active playbook: {inst.get('name', 'Unnamed')}** (instance ID: {inst.get('id', 'N/A')})",
        f"  Current phase: {current} ({PHASE_NAMES.get(current, '?')}) | "
        f"Activated: {inst.get('activated_at', 'N/A')}",
    ]
    for ph in (inst.get("definition") or {}).get("phases", []):
        lines.append(_format_phase(ph, state.get("tasks") or {}, current))
    runs = state.get("action_runs") or []
    if runs:
        lines.append(f"\n**Action runs** ({len(runs)})")
        for r in runs[-10:]:
            result = r.get("result") or {}
            msg = result.get("message") or result.get("status") or ""
            lines.append(f"- [{r.get('run_at', 'N/A')}] {r.get('name') or r.get('key')}: {msg}")
    return "\n".join(lines)


def _format_runs(runs: list) -> str:
    if not runs:
        return ""
    lines = ["\n**Auto-run actions executed:**"]
    for r in runs:
        result = r.get("result") or {}
        lines.append(f"- {r.get('key')} ({r.get('type')}): {result.get('message') or result.get('status', '')}")
    return "\n".join(lines)


@mcp.tool()
async def sheetstorm_list_playbook_templates() -> str:
    """List the organization's IR playbook templates (phase-gated runbooks)."""
    client = get_client()
    try:
        data = await client.get("/playbooks")
        items = data.get("items", []) if isinstance(data, dict) else data
        if not items:
            return "No playbook templates defined."
        lines = [f"**Playbook Templates** ({len(items)})\n"]
        for p in items:
            lines.append(_format_template(p))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_playbook_template(playbook_id: str) -> str:
    """Get a playbook template with its phases, tasks and actions.

    Args:
        playbook_id: UUID of the playbook template
    """
    client = get_client()
    try:
        return _format_template(await client.get(f"/playbooks/{playbook_id}"), detail=True)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_activate_playbook(incident_id: str, playbook_id: str) -> str:
    """Activate a playbook template on an incident. It starts at the incident's
    current IR phase and immediately runs that phase's auto-run actions.

    Args:
        incident_id: UUID of the incident
        playbook_id: UUID of the playbook template
    """
    client = get_client()
    try:
        data = await client.post(f"/incidents/{incident_id}/playbooks/{playbook_id}/activate")
        return "✓ Playbook activated.\n" + _format_instance(data.get("incident_playbook")) + _format_runs(
            data.get("actions_executed") or []
        )
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_incident_playbook(incident_id: str) -> str:
    """Get the active playbook of an incident: current phase, task checklist
    (with task_keys), available actions (with action keys) and recent action runs.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/playbook")
        return _format_instance(data.get("incident_playbook"))
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_advance_playbook_phase(incident_id: str) -> str:
    """Advance the incident's active playbook to the next IR phase (max 6) and run
    the new phase's auto-run actions.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.put(f"/incidents/{incident_id}/playbook/advance")
        inst = data.get("incident_playbook") or {}
        return (
            f"✓ Playbook advanced to phase {inst.get('current_phase')}.\n"
            + _format_instance(inst)
            + _format_runs(data.get("actions_executed") or [])
        )
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_execute_playbook_action(incident_id: str, action_key: str) -> str:
    """Run one action of the incident's active playbook (enrich_iocs,
    generate_summary, suggest_mitre or create_task).

    Args:
        incident_id: UUID of the incident
        action_key: The action's key as shown by sheetstorm_get_incident_playbook
    """
    client = get_client()
    try:
        data = await client.post(
            f"/incidents/{incident_id}/playbook/execute", json={"action_key": action_key}
        )
        result = data.get("result") or {}
        status = result.get("status", "done")
        detail = result.get("message") or ""
        extra = {k: v for k, v in result.items() if k not in ("status", "message")}
        out = f"{'✗' if status == 'error' else '✓'} Action {action_key}: {status}"
        if detail:
            out += f" — {detail}"
        if extra:
            out += f"\n  Details: {extra}"
        return out
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_toggle_playbook_task(
    incident_id: str,
    task_key: str,
    done: Optional[bool] = True,
) -> str:
    """Mark a checklist task of the incident's active playbook as done or not done.

    Args:
        incident_id: UUID of the incident
        task_key: The task's key "<phase>:<index>" as shown by sheetstorm_get_incident_playbook
        done: True to tick the task (default), False to untick it
    """
    client = get_client()
    try:
        await client.put(
            f"/incidents/{incident_id}/playbook/task",
            json={"task_key": task_key, "done": bool(done)},
        )
        return f"✓ Playbook task {task_key} marked {'done' if done else 'not done'}."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
