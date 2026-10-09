"""Evidence register & custody ledger tools: list, get, register, custody
transfers (check-out / transfer / check-in) and chain verification.

Custody writes record real-world physical acts (a drive handed to a courier),
so ``sheetstorm_transfer_evidence`` refuses unless the human has confirmed the
event happened (``attested=True``). Every request carries
``X-SheetStorm-Client`` (see ``client.py``); the backend snapshots it into the
signed ledger entry.
"""

from __future__ import annotations

import json
from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import get_client, mcp
from sheetstorm_bridge.tools.artifacts import _format_custody_entry

_TRANSFER_MODES = {"check_out": "check-out", "transfer": "transfer", "check_in": "check-in"}

ATTESTATION_REQUIRED = (
    "✗ Not recorded. A custody transfer is a signed, append-only record of a physical event "
    "(who handed which evidence to whom, when). Confirm with the user that this hand-over "
    "actually happened as described, then call again with attested=true."
)


def _base(incident_id: str) -> str:
    return f"/incidents/{incident_id}/evidence"


def _format_item(i: dict) -> str:
    title = i.get("title", "Untitled")
    parts = [f"**{i.get('evidence_number', 'EV-?')}** {title} ({i.get('evidence_type', 'other')}) "
             f"(ID: {i.get('id', 'N/A')})"]
    holder = i.get("holder") or {}
    state = i.get("custody_state", "N/A")
    if holder.get("type") == "storage":
        where = f"in storage at {holder.get('name') or 'unknown location'}"
    else:
        where = f"held by {holder.get('name') or 'unknown'} ({holder.get('type')})"
    parts.append(f"  Custody: {state} | {where}")
    ident = [f"{label}: {i[key]}" for key, label in (("serial_number", "Serial"), ("seal_number", "Seal"),
                                                     ("make", "Make"), ("model", "Model")) if i.get(key)]
    if ident:
        parts.append("  " + " | ".join(ident))
    for h in i.get("acquisition_hashes") or []:
        if isinstance(h, dict) and not h.get("superseded"):
            parts.append(f"  {str(h.get('algorithm', '')).upper()}: {h.get('value')} ({h.get('source', '')})")
    if i.get("weak_hashes_only"):
        parts.append("  ⚠ Only MD5/SHA-1 recorded")
    if i.get("last_verification_result"):
        parts.append(f"  Last verification: {i['last_verification_result']} ({i.get('last_verified_at', '')})")
    if i.get("under_legal_hold"):
        parts.append("  Legal hold: YES")
    if i.get("voided_at"):
        parts.append(f"  VOIDED: {i.get('void_reason') or ''}")
    if i.get("parent"):
        parts.append(f"  Derived from: {i['parent'].get('evidence_number')}")
    return "\n".join(parts)


@mcp.tool()
async def sheetstorm_list_evidence(
    incident_id: str,
    evidence_type: Optional[str] = None,
    custody_state: Optional[str] = None,
    search: Optional[str] = None,
    include_voided: bool = False,
    page: int = 1,
    per_page: int = 50,
) -> str:
    """List the evidence register of an incident (EV-0001, EV-0002, ...): evidence items
    with type, custody state, current holder, hashes and legal hold.

    Args:
        incident_id: UUID of the incident
        evidence_type: disk_image, memory_capture, triage_package, logical_collection,
            mobile_device, storage_media, computer_system, network_capture, cloud_export,
            log_export, document, digital_file or other
        custody_state: in_storage, checked_out, transferred or disposed
        search: EV number, title, serial, seal or bag number, or an exact hash value
        include_voided: Include items voided as entered in error
        page: Page number (1-based)
        per_page: Items per page (max 200)
    """
    client = get_client()
    params: dict = {"page": max(1, page), "per_page": max(1, min(per_page, 200))}
    for key, value in (("type", evidence_type), ("custody_state", custody_state), ("q", search)):
        if value:
            params[key] = value
    if include_voided:
        params["include_voided"] = "true"
    try:
        data = await client.get(_base(incident_id), params=params)
        items = data.get("items", []) if isinstance(data, dict) else data
        if not items:
            return "No evidence items found."
        total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
        lines = [f"**Evidence register** ({total} items, page {data.get('page', page)})\n"]
        for i in items:
            lines.append(_format_item(i))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_evidence(incident_id: str, evidence_id: str) -> str:
    """Get one evidence item: details, stored file copies, derived items, chain status and
    its custody ledger (every check-out, transfer, check-in, verification, export).

    Args:
        incident_id: UUID of the incident
        evidence_id: UUID of the evidence item
    """
    client = get_client()
    try:
        item = await client.get(f"{_base(incident_id)}/{evidence_id}")
        custody = await client.get(f"{_base(incident_id)}/{evidence_id}/custody")
        lines = [_format_item(item)]
        chain = item.get("chain_summary") or {}
        if chain:
            lines.append(f"  Chain: {str(chain.get('status', 'unknown')).upper()} "
                         f"(head seq {chain.get('head_seq')}, {chain.get('head_hash')})")
        for a in item.get("artifacts") or []:
            gone = " [deleted]" if a.get("deleted_at") else ""
            lines.append(f"  File: {a.get('original_filename')} (ID: {a.get('id')}){gone}")
        for c in item.get("children") or []:
            lines.append(f"  Derived item: {c.get('evidence_number')} {c.get('title')}")
        entries = custody.get("entries", []) if isinstance(custody, dict) else []
        lines.append(f"\n**Custody ledger** ({len(entries)} entries)")
        lines.extend(_format_custody_entry(e) for e in entries)
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_register_evidence(
    incident_id: str,
    title: str,
    evidence_type: str,
    description: Optional[str] = None,
    serial_number: Optional[str] = None,
    seal_number: Optional[str] = None,
    storage_location: Optional[str] = None,
    acquired_at: Optional[str] = None,
    acquisition_method: Optional[str] = None,
    acquisition_tool: Optional[str] = None,
    hashes_json: Optional[str] = None,
    parent_id: Optional[str] = None,
    source_host_id: Optional[str] = None,
) -> str:
    """Register an evidence item that is not (or not only) a file in SheetStorm: a disk
    image in the lab, a phone, a memory capture. Assigns the next EV number and records a
    signed 'register' custody entry.

    Args:
        incident_id: UUID of the incident
        title: Short description (e.g. "Laptop SSD, finance-ws-07")
        evidence_type: disk_image, memory_capture, triage_package, logical_collection,
            mobile_device, storage_media, computer_system, network_capture, cloud_export,
            log_export, document, digital_file or other
        description: Optional longer description
        serial_number: Device or media serial number
        seal_number: Tamper-evident seal number
        storage_location: Where the item is stored (e.g. "Lab safe B/2")
        acquired_at: ISO 8601 time of acquisition
        acquisition_method: e.g. "physical image (write-blocked)"
        acquisition_tool: e.g. "FTK Imager 4.7"
        hashes_json: JSON list of tool-reported hashes, e.g.
            '[{"algorithm": "sha256", "value": "<64 hex>", "source": "tool_reported"}]'
        parent_id: UUID of the item this one was derived from
        source_host_id: UUID of the compromised host it was acquired from
    """
    payload: dict = {"title": title, "evidence_type": evidence_type}
    for key, value in (("description", description), ("serial_number", serial_number),
                       ("seal_number", seal_number), ("storage_location", storage_location),
                       ("acquired_at", acquired_at), ("acquisition_method", acquisition_method),
                       ("acquisition_tool", acquisition_tool), ("parent_id", parent_id),
                       ("source_host_id", source_host_id)):
        if value:
            payload[key] = value
    if hashes_json:
        try:
            hashes = json.loads(hashes_json)
        except json.JSONDecodeError as exc:
            return f"✗ hashes_json is not valid JSON: {exc.msg}"
        if not isinstance(hashes, list):
            return "✗ hashes_json must be a JSON list of {algorithm, value, source} objects"
        payload["acquisition_hashes"] = hashes
    client = get_client()
    try:
        item = await client.post(_base(incident_id), json=payload)
        return f"✓ Evidence registered:\n{_format_item(item)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_transfer_evidence(
    incident_id: str,
    evidence_id: str,
    mode: str,
    reason: Optional[str] = None,
    to_user_id: Optional[str] = None,
    to_party_id: Optional[str] = None,
    transfer_method: Optional[str] = None,
    storage_location: Optional[str] = None,
    seal_intact: Optional[bool] = None,
    attested: bool = False,
) -> str:
    """Record a physical custody event for an evidence item in the signed ledger.

    Only call this after the user has confirmed the hand-over really happened, and pass
    attested=true; otherwise nothing is recorded.

    Args:
        incident_id: UUID of the incident
        evidence_id: UUID of the evidence item
        mode: check_out (to a user or external party, returns later), transfer (released to
            an external party, e.g. a lab or law enforcement) or check_in (returned to storage)
        reason: check_out: purpose (required); transfer: reason (required);
            check_in: condition notes (optional)
        to_user_id: Recipient user (check_out / transfer)
        to_party_id: Recipient external custody party (check_out / transfer)
        transfer_method: hand_delivery, courier, registered_mail, secure_file_transfer,
            internal or other (required for transfer)
        storage_location: Where the item is stored after check_in (required for check_in)
        seal_intact: Whether the seal was intact on check_in (required for check_in)
        attested: The user confirmed this physical event happened as described
    """
    if mode not in _TRANSFER_MODES:
        return f"✗ mode must be one of: {', '.join(_TRANSFER_MODES)}"
    if not attested:
        return ATTESTATION_REQUIRED
    if mode == "check_in":
        payload: dict = {"storage_location": storage_location, "seal_intact": seal_intact}
        if reason:
            payload["condition_notes"] = reason
    else:
        payload = {"purpose" if mode == "check_out" else "reason": reason}
        for key, value in (("to_user_id", to_user_id), ("to_party_id", to_party_id),
                           ("transfer_method", transfer_method)):
            if value:
                payload[key] = value
    client = get_client()
    try:
        item = await client.post(
            f"{_base(incident_id)}/{evidence_id}/custody/{_TRANSFER_MODES[mode]}", json=payload
        )
        lines = [f"✓ Custody {mode.replace('_', ' ')} recorded:", _format_item(item)]
        lines.extend(_format_custody_entry(e) for e in item.get("ledger_entries") or [])
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_verify_evidence_chain(incident_id: str, evidence_id: Optional[str] = None) -> str:
    """Verify the tamper-evident custody ledger: recompute every entry hash and chain link
    and check the HMAC signatures. With evidence_id, one item's chain; without it, the whole
    incident ledger (every item chain plus the incident chain).

    Args:
        incident_id: UUID of the incident
        evidence_id: Optional UUID of one evidence item
    """
    client = get_client()
    path = (f"{_base(incident_id)}/{evidence_id}/custody/verify" if evidence_id
            else f"{_base(incident_id)}/custody/verify")
    try:
        r = await client.get(path)
        chain = r.get("item_chain") or r.get("incident_chain") or {}
        status = str(r.get("status", "unknown"))
        lines = [
            f"**Chain verification** ({r.get('scope', 'item' if evidence_id else 'incident')}): {status.upper()}",
            f"  Entries: {chain.get('length')} | head seq {chain.get('head_seq')} | {chain.get('head_hash')}",
            "  Signatures: " + ", ".join(f"{k}={v}" for k, v in sorted((r.get("signatures") or {}).items())),
        ]
        for b in r.get("breaks") or []:
            lines.append(f"  BREAK {b.get('chain')} seq={b.get('seq')}: {b.get('reason')}")
        for d in r.get("projection_drift") or []:
            lines.append(f"  Drift: {d.get('field')} (item {d.get('item_value')} vs ledger {d.get('ledger_value')})")
        for n in r.get("notes") or []:
            lines.append(f"  Note: {n}")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
