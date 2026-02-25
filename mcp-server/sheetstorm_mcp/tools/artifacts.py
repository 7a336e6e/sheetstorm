"""Artifact & evidence management tools — upload, download, verify, chain of custody."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


def _format_artifact(a: dict) -> str:
    parts = [
        f"**{a.get('original_filename', a.get('filename', 'Unknown'))}** "
        f"(ID: {a.get('id', 'N/A')})",
        f"  Size: {a.get('file_size', 'N/A')} bytes",
    ]
    if a.get("md5_hash") or a.get("md5"):
        parts.append(f"  MD5: {a.get('md5_hash', a.get('md5', 'N/A'))}")
    if a.get("sha256_hash") or a.get("sha256"):
        parts.append(f"  SHA256: {a.get('sha256_hash', a.get('sha256', 'N/A'))}")
    parts.append(f"  Uploaded: {a.get('created_at', a.get('uploaded_at', 'N/A'))}")
    if a.get("description"):
        parts.append(f"  Description: {a['description']}")
    return "\n".join(parts)


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
) -> str:
    """Upload an artifact/evidence file. Hashes will be computed automatically.

    Args:
        incident_id: UUID of the incident
        file_path: Local filesystem path to the file to upload
        description: Optional description
    """
    client = get_client()
    try:
        from pathlib import Path

        p = Path(file_path)
        if not p.exists():
            return f"✗ File not found: {file_path}"
        if not p.is_file():
            return f"✗ Not a file: {file_path}"

        artifact = await client.upload(f"/incidents/{incident_id}/artifacts", file_path)
        return f"✓ Artifact uploaded:\n{_format_artifact(artifact)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_verify_artifact(incident_id: str, artifact_id: str) -> str:
    """Verify integrity of an artifact by recomputing hashes.

    Args:
        incident_id: UUID of the incident
        artifact_id: UUID of the artifact
    """
    client = get_client()
    try:
        result = await client.post(f"/incidents/{incident_id}/artifacts/{artifact_id}/verify")
        status = "PASS ✓" if result.get("verified") or result.get("match") else "FAIL ✗"
        parts = [f"**Integrity Check**: {status}"]
        if result.get("stored_hash") or result.get("original_sha256"):
            parts.append(f"  Stored SHA256: {result.get('stored_hash', result.get('original_sha256', 'N/A'))}")
        if result.get("computed_hash") or result.get("current_sha256"):
            parts.append(f"  Computed SHA256: {result.get('computed_hash', result.get('current_sha256', 'N/A'))}")
        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_chain_of_custody(incident_id: str, artifact_id: str) -> str:
    """Get the chain of custody log for an artifact.

    Args:
        incident_id: UUID of the incident
        artifact_id: UUID of the artifact
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/artifacts/{artifact_id}/custody")
        events = data if isinstance(data, list) else data.get("events", data.get("custody", []))

        if not events:
            return "No chain of custody events recorded."

        lines = [f"**Chain of Custody** ({len(events)} events)\n"]
        for e in events:
            lines.append(
                f"[{e.get('timestamp', e.get('created_at', 'N/A'))}] "
                f"**{e.get('action', 'N/A')}** by {e.get('user_name', e.get('performed_by', 'Unknown'))}\n"
                f"  {e.get('details', e.get('description', 'N/A'))}"
            )
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_download_artifact(
    incident_id: str,
    artifact_id: str,
    save_path: Optional[str] = None,
) -> str:
    """Download an artifact file.

    Args:
        incident_id: UUID of the incident
        artifact_id: UUID of the artifact
        save_path: Local path to save the file (if not provided, returns file info only)
    """
    client = get_client()
    try:
        content = await client.download(
            f"/incidents/{incident_id}/artifacts/{artifact_id}/download"
        )
        if save_path:
            from pathlib import Path

            p = Path(save_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
            return f"✓ Artifact downloaded to {save_path} ({len(content)} bytes)"
        else:
            return f"✓ Artifact downloaded ({len(content)} bytes). Provide save_path to save to disk."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
