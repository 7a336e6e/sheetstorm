"""Artifact & evidence management tools — upload, download, verify, chain of custody,
legal hold and custody export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import get_client, mcp


def _local_path(path_str: str) -> Path:
    """The bridge runs on the user's own machine: any local path is allowed."""
    return Path(path_str).expanduser()


def _read_local_file(p: Path) -> bytes:
    if not p.is_file():
        raise IsADirectoryError(f"Not a regular file: {p}")
    return p.read_bytes()


def _write_local_file(p: Path, content: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def _format_artifact(a: dict) -> str:
    parts = [
        f"**{a.get('original_filename', a.get('filename', 'Unknown'))}** "
        f"(ID: {a.get('id', 'N/A')})",
        f"  Size: {a.get('file_size', 'N/A')} bytes",
    ]
    if a.get("md5"):
        parts.append(f"  MD5: {a['md5']}")
    if a.get("sha256"):
        parts.append(f"  SHA256: {a['sha256']}")
    parts.append(f"  Uploaded: {a.get('created_at', 'N/A')}")
    if a.get("description"):
        parts.append(f"  Description: {a['description']}")
    acq = [
        f"{label}: {a[key]}"
        for key, label in (
            ("acquired_at", "Acquired"),
            ("acquisition_method", "Method"),
            ("acquisition_tool", "Tool"),
            ("source_host", "Source host"),
        )
        if a.get(key)
    ]
    if acq:
        parts.append("  " + " | ".join(acq))
    if a.get("under_legal_hold") or a.get("is_locked"):
        until = a.get("legal_hold_until")
        parts.append(f"  Legal hold: YES{f' (until {until})' if until else ''}")
    return "\n".join(parts)


def _format_custody_entry(e: dict) -> str:
    performer = e.get("performer")
    performer_name = (
        performer.get("name", "Unknown") if isinstance(performer, dict)
        else str(performer or e.get("performed_by") or "Unknown")
    )
    line = f"[{e.get('created_at', 'N/A')}] **{e.get('action', 'N/A')}** by {performer_name}"
    extras = []
    if e.get("purpose"):
        extras.append(f"Purpose: {e['purpose']}")
    if e.get("verification_result"):
        extras.append(f"Verification: {e['verification_result']}")
    recipient = e.get("recipient")
    if isinstance(recipient, dict) and recipient.get("name"):
        extras.append(f"Recipient: {recipient['name']}")
    if "signature_status" in e:
        extras.append(f"Signature: {e['signature_status']}")
    elif "signature_valid" in e:
        extras.append(f"Signature: {'valid' if e['signature_valid'] else 'INVALID'}")
    if extras:
        line += "\n  " + " | ".join(extras)
    return line


@mcp.tool()
async def sheetstorm_list_artifacts(incident_id: str) -> str:
    """List artifacts/evidence files for an incident.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/artifacts")
        items = data if isinstance(data, list) else data.get("items", data.get("artifacts", []))

        if not items:
            return "No artifacts found."

        lines = [f"**Artifacts** ({len(items)})\n"]
        for a in items:
            lines.append(_format_artifact(a))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_upload_artifact(
    incident_id: str,
    file_path: str,
    description: Optional[str] = None,
    source: Optional[str] = None,
    acquired_at: Optional[str] = None,
    acquisition_method: Optional[str] = None,
    acquisition_tool: Optional[str] = None,
    source_host: Optional[str] = None,
) -> str:
    """Upload an artifact/evidence file. MD5/SHA256/SHA512 are computed by the server
    and an 'upload' chain-of-custody entry is recorded.

    Args:
        incident_id: UUID of the incident
        file_path: Local path of the file to upload
        description: Optional description of the evidence
        source: Where the evidence came from (e.g. "EDR export", "customer upload")
        acquired_at: ISO 8601 time the evidence was acquired
        acquisition_method: How it was acquired (e.g. "live memory capture", "disk image")
        acquisition_tool: Tool used (e.g. "FTK Imager 4.7", "WinPmem")
        source_host: Hostname the evidence was taken from
    """
    client = get_client()
    try:
        try:
            p = _local_path(file_path)
            content = _read_local_file(p)
        except FileNotFoundError:
            return f"✗ File not found: {file_path}"
        except OSError as exc:
            return f"✗ Cannot read {file_path}: {exc.strerror or exc}"

        form = {
            k: v for k, v in {
                "description": description,
                "source": source,
                "acquired_at": acquired_at,
                "acquisition_method": acquisition_method,
                "acquisition_tool": acquisition_tool,
                "source_host": source_host,
            }.items() if v
        }
        artifact = await client.upload(
            f"/incidents/{incident_id}/artifacts", p.name, content, data=form or None
        )
        return f"✓ Artifact uploaded:\n{_format_artifact(artifact)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_verify_artifact(incident_id: str, artifact_id: str) -> str:
    """Verify integrity of an artifact by recomputing its hashes on the server and
    comparing them with the hashes stored at upload. Records a 'verify' custody entry.

    Args:
        incident_id: UUID of the incident
        artifact_id: UUID of the artifact
    """
    client = get_client()
    try:
        result = await client.post(f"/incidents/{incident_id}/artifacts/{artifact_id}/verify")
        outcome = result.get("result")
        status = "PASS ✓ (hashes match)" if outcome == "match" else f"FAIL ✗ ({outcome or 'unknown'})"
        parts = [f"**Integrity Check**: {status}"]
        stored = result.get("stored_hashes") or {}
        computed = result.get("computed_hashes") or {}
        matches = result.get("matches") or {}
        for algo in ("md5", "sha256", "sha512"):
            if algo in stored or algo in computed:
                flag = ""
                if algo in matches:
                    flag = " ✓" if matches[algo] else " ✗ MISMATCH"
                parts.append(f"  {algo.upper()}{flag}")
                parts.append(f"    stored:   {stored.get(algo, 'N/A')}")
                parts.append(f"    computed: {computed.get(algo, 'N/A')}")
        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_chain_of_custody(incident_id: str, artifact_id: str) -> str:
    """Get the chain of custody log for an artifact (who did what, when, and the
    per-entry signature status where the server provides it).

    Args:
        incident_id: UUID of the incident
        artifact_id: UUID of the artifact
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/artifacts/{artifact_id}/custody")
        events = data if isinstance(data, list) else data.get("chain_of_custody", [])

        if not events:
            return "No chain of custody events recorded."

        name = data.get("original_filename") if isinstance(data, dict) else None
        header = f"**Chain of Custody** ({len(events)} events)"
        if name:
            header += f" — {name}"
        lines = [header + "\n"]
        lines.extend(_format_custody_entry(e) for e in events)
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_set_legal_hold(
    incident_id: str,
    artifact_id: str,
    hold: bool = True,
    reason: Optional[str] = None,
    until: Optional[str] = None,
) -> str:
    """Place or release a legal hold (preservation lock) on an artifact. A held
    artifact cannot be deleted. Recorded in the chain of custody.

    Args:
        incident_id: UUID of the incident
        artifact_id: UUID of the artifact
        hold: True to place the hold, False to release it
        reason: Reason recorded in the chain of custody (e.g. "litigation hold – case 2026-114")
        until: Optional ISO 8601 date the hold expires
    """
    client = get_client()
    try:
        payload: dict = {"hold": hold}
        if reason:
            payload["reason"] = reason
        if until:
            payload["until"] = until
        artifact = await client.post(
            f"/incidents/{incident_id}/artifacts/{artifact_id}/legal-hold", json=payload
        )
        verb = "placed on" if hold else "released for"
        return f"✓ Legal hold {verb} artifact:\n{_format_artifact(artifact)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_export_custody(incident_id: str, artifact_id: str) -> str:
    """Export the court-defensible chain-of-custody report for an artifact (JSON):
    artifact hashes and acquisition details, every custody event, per-entry
    signature validity and overall chain integrity.

    Args:
        incident_id: UUID of the incident
        artifact_id: UUID of the artifact
    """
    client = get_client()
    try:
        report = await client.get(
            f"/incidents/{incident_id}/artifacts/{artifact_id}/custody/export",
            params={"format": "json"},
        )
        entries = report.get("custody_entries", [])
        integrity = report.get("chain_integrity")
        status = report.get("chain_integrity_status") or ("intact" if integrity else "compromised")
        a = report.get("artifact", {})
        lines = [
            f"**Custody Report** — {a.get('original_filename', 'N/A')} (ID: {a.get('id', artifact_id)})",
            f"  Chain integrity: {status.upper()}",
            f"  Generated: {report.get('generated_at', 'N/A')} | Entries: {len(entries)}",
            "",
            "```json",
            json.dumps(report, indent=2, default=str),
            "```",
        ]
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_download_artifact(
    incident_id: str,
    artifact_id: str,
    save_path: Optional[str] = None,
) -> str:
    """Download an artifact file. Records a 'download' custody entry.

    Args:
        incident_id: UUID of the incident
        artifact_id: UUID of the artifact
        save_path: Local path to save the file to (if omitted, only the size is reported)
    """
    client = get_client()
    try:
        target = _local_path(save_path) if save_path else None
        content = await client.download(
            f"/incidents/{incident_id}/artifacts/{artifact_id}/download"
        )
        if target is None:
            return f"✓ Artifact downloaded ({len(content)} bytes). Provide save_path to save to disk."
        try:
            _write_local_file(target, content)
        except OSError as exc:
            return f"✗ Cannot write {save_path}: {exc.strerror or exc}"
        return f"✓ Artifact downloaded to {save_path} ({len(content)} bytes)"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
