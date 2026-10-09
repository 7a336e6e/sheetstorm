"""Decision log and response-action tools (W4-DEC).

The assistant can record decisions and response actions, list them and record
a verification, but it can never approve a decision, authorize an action or
change a host/account state: those stay human-in-the-loop (the backend also
refuses ``decisions:approve`` / ``response_actions:authorize`` to API keys).
Privileged decisions are never listed to the assistant: it cannot set
``is_privileged`` and API keys cannot hold ``decisions:read_privileged``.
"""

from __future__ import annotations

import json
from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import get_client, mcp


def _parse_list(raw: Optional[str], name: str) -> list | None:
    """Parse a JSON-array argument; raises ValueError when malformed."""
    if raw is None:
        return None
    value = json.loads(raw) if raw.strip() else []
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise ValueError(f"{name} must be a JSON array of objects")
    return value


def _who(rec: dict, user_field: str, name_field: str) -> str:
    user = (rec.get("users") or {}).get(user_field) or {}
    if user.get("name"):
        return user["name"]
    return f"{rec[name_field]} (recorded)" if rec.get(name_field) else "-"


def _format_decision(d: dict) -> str:
    line = (f"**{d.get('display_id')}: {d.get('title')}** (ID: {d.get('id')})\n"
            f"  Status: {d.get('status')} | Category: {d.get('category')} | Decided: "
            f"{(d.get('decided_at') or '')[:16]} by {_who(d, 'decided_by_user_id', 'decided_by_name')}")
    if d.get("approved_at"):
        line += f"\n  Approved by {_who(d, 'approved_by_user_id', 'approved_by_name')} at {d['approved_at'][:16]}"
    line += f"\n  Decision: {d.get('decision')}"
    if d.get("rationale"):
        line += f"\n  Rationale: {d['rationale']}"
    return line


def _format_action(a: dict) -> str:
    line = (f"**{a.get('display_id')}: {a.get('title')}** (ID: {a.get('id')})\n"
            f"  Type: {a.get('action_type')} | Status: {a.get('status')} | Target: "
            f"{a.get('target_type')} {a.get('target_label') or ''}".rstrip())
    if a.get("executed_at"):
        line += f"\n  Executed {a['executed_at'][:16]} by {_who(a, 'executed_by_user_id', 'executed_by_name')}"
    if a.get("verified_at"):
        line += (f"\n  Verified {a['verified_at'][:16]} ({a.get('verification_result')}) by "
                 f"{_who(a, 'verified_by_user_id', 'verified_by_name')}")
    return line


@mcp.tool()
async def sheetstorm_log_decision(
    incident_id: str,
    title: str,
    decision: str,
    category: str = "other",
    rationale: Optional[str] = None,
    decided_at: Optional[str] = None,
    alternatives: Optional[str] = None,
    decided_by_name: Optional[str] = None,
    approved_by_name: Optional[str] = None,
    approved_at: Optional[str] = None,
    links: Optional[str] = None,
) -> str:
    """Record a decision in the incident's decision log (it starts as
    "proposed" unless an external approver is named). The assistant cannot
    approve decisions or mark them privileged.

    Args:
        incident_id: UUID of the incident
        title: Short summary, e.g. "Do not pay the ransom"
        decision: What was decided
        category: containment, eradication, recovery, notification, ransom_legal, scope, communication, evidence or other
        rationale: Why
        decided_at: When it was decided (ISO 8601; default now)
        alternatives: JSON array of rejected options, e.g. [{"option": "Pay", "reason_not_chosen": "Policy"}]
        decided_by_name: Decision maker outside SheetStorm (default: the API key owner)
        approved_by_name: External approver already on record, e.g. "General Counsel"
        approved_at: When the external approval was given (ISO 8601)
        links: JSON array of evidence references, e.g. [{"evidence_type": "timeline_event", "evidence_id": "<uuid>"}]
    """
    try:
        alt = _parse_list(alternatives, "alternatives")
        refs = _parse_list(links, "links")
    except ValueError as exc:
        return f"✗ Error: {exc}"
    payload: dict = {"title": title, "decision": decision, "category": category}
    for key, value in (("rationale", rationale), ("decided_at", decided_at), ("decided_by_name", decided_by_name),
                       ("approved_by_name", approved_by_name), ("approved_at", approved_at)):
        if value:
            payload[key] = value
    if alt is not None:
        payload["alternatives"] = alt
    if refs is not None:
        payload["links"] = refs
    try:
        d = await get_client().post(f"/incidents/{incident_id}/decisions", json=payload)
        return f"✓ Decision recorded:\n{_format_decision(d)}"
    except SheetStormAPIError as exc:
        return f"✗ Error recording decision: {exc}"


@mcp.tool()
async def sheetstorm_list_decisions(
    incident_id: str,
    status: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> str:
    """List the incident's decisions (privileged decisions are never shown).

    Args:
        incident_id: UUID of the incident
        status: Comma-separated filter: proposed, approved, rejected, superseded
        category: Comma-separated category filter
        page: Page number (default 1)
        per_page: Items per page (default 50, max 100)
    """
    params: dict = {"page": page, "per_page": min(max(per_page, 1), 100)}
    if status:
        params["status"] = status
    if category:
        params["category"] = category
    try:
        data = await get_client().get(f"/incidents/{incident_id}/decisions", params=params)
    except SheetStormAPIError as exc:
        return f"✗ Error listing decisions: {exc}"
    items = data.get("items", [])
    if not items:
        return "No decisions found."
    lines = [f"**Decisions** (showing {len(items)} of {data.get('total', len(items))})\n"]
    for d in items:
        lines += [_format_decision(d), ""]
    return "\n".join(lines)


@mcp.tool()
async def sheetstorm_log_response_action(
    incident_id: str,
    action_type: str,
    title: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    target_label: Optional[str] = None,
    decision_id: Optional[str] = None,
    executed_at: Optional[str] = None,
    executed_by_name: Optional[str] = None,
    rollback_plan: Optional[str] = None,
    links: Optional[str] = None,
) -> str:
    """Record a response action (status "requested", or "executed" when
    executed_at is given). It never changes the host or account itself and
    cannot authorize the action.

    Args:
        incident_id: UUID of the incident
        action_type: isolate_host, release_host, contain_host, reimage_host, decommission_host, disable_account, reset_credentials, revoke_sessions, delete_account, block_ioc, sinkhole_domain, quarantine_file, remove_persistence, patch, notify_party or other
        title: Short description
        target_type: host, account, network_ioc, host_ioc, malware, external or none
        target_id: UUID of the target record (host/account/IOC/malware of this incident)
        target_label: Free-text target for external targets, e.g. the notified party
        decision_id: UUID of the decision this action implements
        executed_at: When it was already carried out (ISO 8601)
        executed_by_name: Who carried it out, if not the API key owner (e.g. an MSSP)
        rollback_plan: How to undo it
        links: JSON array of evidence references, e.g. [{"evidence_type": "host", "evidence_id": "<uuid>"}]
    """
    try:
        refs = _parse_list(links, "links")
    except ValueError as exc:
        return f"✗ Error: {exc}"
    payload: dict = {"action_type": action_type, "title": title}
    for key, value in (("target_type", target_type), ("target_id", target_id), ("target_label", target_label),
                       ("decision_id", decision_id), ("executed_at", executed_at),
                       ("executed_by_name", executed_by_name), ("rollback_plan", rollback_plan)):
        if value:
            payload[key] = value
    if refs is not None:
        payload["links"] = refs
    try:
        a = await get_client().post(f"/incidents/{incident_id}/response-actions", json=payload)
        return f"✓ Response action recorded:\n{_format_action(a)}"
    except SheetStormAPIError as exc:
        return f"✗ Error recording response action: {exc}"


@mcp.tool()
async def sheetstorm_list_response_actions(
    incident_id: str,
    status: Optional[str] = None,
    action_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> str:
    """List the incident's response actions.

    Args:
        incident_id: UUID of the incident
        status: Comma-separated filter: requested, authorized, in_progress, executed, verified, failed, rolled_back, cancelled
        action_type: Comma-separated action type filter
        page: Page number (default 1)
        per_page: Items per page (default 50, max 100)
    """
    params: dict = {"page": page, "per_page": min(max(per_page, 1), 100)}
    if status:
        params["status"] = status
    if action_type:
        params["action_type"] = action_type
    try:
        data = await get_client().get(f"/incidents/{incident_id}/response-actions", params=params)
    except SheetStormAPIError as exc:
        return f"✗ Error listing response actions: {exc}"
    items = data.get("items", [])
    if not items:
        return "No response actions found."
    lines = [f"**Response actions** (showing {len(items)} of {data.get('total', len(items))})\n"]
    for a in items:
        lines += [_format_action(a), ""]
    return "\n".join(lines)


@mcp.tool()
async def sheetstorm_update_action_verification(
    incident_id: str,
    action_id: str,
    result: str,
    method: str,
    verified_at: Optional[str] = None,
    notes: Optional[str] = None,
    verified_by_name: Optional[str] = None,
) -> str:
    """Record the verification of an executed response action.

    Args:
        incident_id: UUID of the incident
        action_id: UUID of the response action (must be "executed")
        result: success, partial or failed
        method: How it was verified, e.g. "EDR console shows host isolated"
        verified_at: When (ISO 8601; default now)
        notes: Details
        verified_by_name: Who verified it, if not the API key owner
    """
    client = get_client()
    path = f"/incidents/{incident_id}/response-actions/{action_id}"
    try:
        current = await client.get(path)
        payload: dict = {"verification_result": result, "verification_method": method,
                         "expected_version": current.get("version")}
        for key, value in (("verified_at", verified_at), ("verification_notes", notes),
                           ("verified_by_name", verified_by_name)):
            if value:
                payload[key] = value
        a = await client.post(f"{path}/verify", json=payload)
        return f"✓ Verification recorded:\n{_format_action(a)}"
    except SheetStormAPIError as exc:
        return f"✗ Error recording verification: {exc}"
