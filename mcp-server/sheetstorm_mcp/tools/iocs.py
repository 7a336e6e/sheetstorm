"""IOC management tools — network IOCs, host-based IOCs, and malware/tools."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _format_network_ioc(i: dict) -> str:
    src_ref = i.get('source_host_ref', {})
    dst_ref = i.get('destination_host_ref', {})
    src_name = src_ref.get('hostname', i.get('source_host', 'N/A')) if isinstance(src_ref, dict) else i.get('source_host', 'N/A')
    dst_name = dst_ref.get('hostname', i.get('destination_host', 'N/A')) if isinstance(dst_ref, dict) else i.get('destination_host', 'N/A')
    return (
        f"**{i.get('dns_ip', 'N/A')}** (ID: {i.get('id', 'N/A')})\n"
        f"  Protocol: {i.get('protocol', 'N/A')} | Port: {i.get('port', 'N/A')} | "
        f"Direction: {i.get('direction', 'N/A')}\n"
        f"  Source: {src_name} \u2192 Dest: {dst_name}\n"
        f"  Description: {i.get('description', 'N/A')} | "
        f"Malicious: {'Yes' if i.get('is_malicious') else 'No'}"
    )


def _format_host_ioc(i: dict) -> str:
    return (
        f"**{i.get('artifact_value', 'N/A')}** (ID: {i.get('id', 'N/A')})\n"
        f"  Type: {i.get('artifact_type', 'N/A')}\n"
        f"  Host: {i.get('host', i.get('host_id', 'N/A'))}\n"
        f"  Notes: {i.get('notes', 'N/A')} | "
        f"Malicious: {'Yes' if i.get('is_malicious') else 'No'}"
    )


def _format_malware(m: dict) -> str:
    parts = [
        f"**{m.get('file_name', 'Unknown')}** (ID: {m.get('id', 'N/A')})",
        f"  Path: {m.get('file_path', 'N/A')} | Size: {m.get('file_size', 'N/A')} bytes",
    ]
    if m.get("md5"):
        parts.append(f"  MD5: {m['md5']}")
    if m.get("sha256"):
        parts.append(f"  SHA256: {m['sha256']}")
    parts.append(f"  Host: {m.get('host', m.get('host_id', 'N/A'))}")
    if m.get("malware_family"):
        parts.append(f"  Family: {m['malware_family']}")
    if m.get("threat_actor"):
        parts.append(f"  Threat Actor: {m['threat_actor']}")
    if m.get("description"):
        parts.append(f"  Description: {m['description']}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Host auto-resolution helper
# ---------------------------------------------------------------------------

async def _resolve_host_by_text(
    client, incident_id: str, text: str
) -> Optional[str]:
    """Try to match a text IP/hostname to an existing compromised host.

    Returns the host UUID if found, else None.
    """
    if not text:
        return None
    try:
        data = await client.get(f"/incidents/{incident_id}/hosts")
        items = data if isinstance(data, list) else data.get("items", [])
        text_lower = text.lower().strip()
        for h in items:
            if (h.get("hostname", "").lower() == text_lower
                    or h.get("ip_address", "").lower() == text_lower):
                return h["id"]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Network IOC tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_list_network_iocs(incident_id: str) -> str:
    """List network indicators of compromise (IPs, domains, URLs) for an incident.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/network-iocs")
        items = data if isinstance(data, list) else data.get("items", [])
        if not items:
            return "No network IOCs found."
        lines = [f"**Network IOCs** ({len(items)})\n"]
        for i in items:
            lines.append(_format_network_ioc(i))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_add_network_ioc(
    incident_id: str,
    dns_ip: str,
    protocol: Optional[str] = None,
    port: Optional[int] = None,
    source_host: Optional[str] = None,
    destination_host: Optional[str] = None,
    direction: Optional[str] = None,
    description: Optional[str] = None,
    is_malicious: bool = True,
    host_id: Optional[str] = None,
    timestamp: Optional[str] = None,
    source_host_id: Optional[str] = None,
    destination_host_id: Optional[str] = None,
    add_to_attack_graph: bool = False,
) -> str:
    """Add a network IOC (IP address, domain, or URL).

    Args:
        incident_id: UUID of the incident
        dns_ip: The indicator value (IP, domain, or URL)
        protocol: Network protocol (TCP, UDP, HTTP, HTTPS, DNS, ICMP, SMB, RDP, SSH)
        port: Port number
        source_host: Source hostname or IP (legacy text field; prefer source_host_id)
        destination_host: Destination hostname or IP (legacy text field; prefer destination_host_id)
        direction: Direction (inbound, outbound, lateral)
        description: Description
        is_malicious: Whether this is confirmed malicious
        host_id: UUID of a compromised host to correlate with (shown in UI)
        timestamp: ISO-8601 timestamp when the IOC was observed (defaults to now)
        source_host_id: UUID of the source compromised host (creates a host link)
        destination_host_id: UUID of the destination compromised host (creates a host link)
        add_to_attack_graph: If true, automatically creates an attack graph node for this IOC
    """
    from datetime import datetime as dt, timezone

    client = get_client()
    try:
        payload: dict = {
            "dns_ip": dns_ip,
            "timestamp": timestamp or dt.now(timezone.utc).isoformat(),
        }
        if protocol:
            payload["protocol"] = protocol
        if port is not None:
            payload["port"] = port
        if host_id:
            payload["host_id"] = host_id
        if source_host:
            payload["source_host"] = source_host
        if destination_host:
            payload["destination_host"] = destination_host
        if direction:
            payload["direction"] = direction
        if description:
            payload["description"] = description
        payload["is_malicious"] = is_malicious
        # Auto-resolve: if text source/destination provided but no ID, try to find matching host
        resolved_src = source_host_id or (await _resolve_host_by_text(client, incident_id, source_host) if source_host else None)
        resolved_dst = destination_host_id or (await _resolve_host_by_text(client, incident_id, destination_host) if destination_host else None)
        if resolved_src:
            payload["source_host_id"] = resolved_src
        if resolved_dst:
            payload["destination_host_id"] = resolved_dst
        if add_to_attack_graph:
            payload["add_to_attack_graph"] = True

        ioc = await client.post(f"/incidents/{incident_id}/network-iocs", json=payload)
        return f"✓ Network IOC added:\n{_format_network_ioc(ioc)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_network_ioc(
    incident_id: str,
    ioc_id: str,
    dns_ip: Optional[str] = None,
    protocol: Optional[str] = None,
    port: Optional[int] = None,
    source_host: Optional[str] = None,
    destination_host: Optional[str] = None,
    description: Optional[str] = None,
    source_host_id: Optional[str] = None,
    destination_host_id: Optional[str] = None,
) -> str:
    """Update a network IOC.

    Args:
        incident_id: UUID of the incident
        ioc_id: UUID of the network IOC
        dns_ip: New indicator value
        protocol: New protocol
        port: New port
        source_host: New source host (text)
        destination_host: New destination host (text)
        description: New description
        source_host_id: UUID of source compromised host (or 'null' to clear)
        destination_host_id: UUID of destination compromised host (or 'null' to clear)
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, val in [
            ("dns_ip", dns_ip),
            ("protocol", protocol),
            ("port", port),
            ("source_host", source_host),
            ("destination_host", destination_host),
            ("description", description),
            ("source_host_id", source_host_id),
            ("destination_host_id", destination_host_id),
        ]:
            if val is not None:
                payload[field] = val
        if not payload:
            return "No fields to update."
        ioc = await client.put(f"/incidents/{incident_id}/network-iocs/{ioc_id}", json=payload)
        return f"✓ Network IOC updated:\n{_format_network_ioc(ioc)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_delete_network_ioc(incident_id: str, ioc_id: str) -> str:
    """Delete a network IOC.

    Args:
        incident_id: UUID of the incident
        ioc_id: UUID of the network IOC to delete
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/network-iocs/{ioc_id}")
        return f"✓ Network IOC {ioc_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Host-based IOC tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_list_host_iocs(incident_id: str) -> str:
    """List host-based indicators of compromise (file hashes, registry keys, processes, etc.).

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/host-iocs")
        items = data if isinstance(data, list) else data.get("items", [])
        if not items:
            return "No host-based IOCs found."
        lines = [f"**Host-Based IOCs** ({len(items)})\n"]
        for i in items:
            lines.append(_format_host_ioc(i))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_add_host_ioc(
    incident_id: str,
    artifact_type: str,
    artifact_value: str,
    host_id: Optional[str] = None,
    notes: Optional[str] = None,
    is_malicious: bool = True,
) -> str:
    """Add a host-based IOC.

    Args:
        incident_id: UUID of the incident
        artifact_type: Type (file_hash, registry_key, process, service, scheduled_task)
        artifact_value: The indicator value
        host_id: UUID of the associated host
        notes: Additional notes
        is_malicious: Whether this is confirmed malicious
    """
    client = get_client()
    try:
        payload: dict = {"artifact_type": artifact_type, "artifact_value": artifact_value}
        if host_id:
            payload["host_id"] = host_id
        if notes:
            payload["notes"] = notes
        payload["is_malicious"] = is_malicious
        ioc = await client.post(f"/incidents/{incident_id}/host-iocs", json=payload)
        return f"✓ Host IOC added:\n{_format_host_ioc(ioc)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_host_ioc(
    incident_id: str,
    ioc_id: str,
    artifact_type: Optional[str] = None,
    artifact_value: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Update a host-based IOC.

    Args:
        incident_id: UUID of the incident
        ioc_id: UUID of the host IOC
        artifact_type: New type
        artifact_value: New value
        notes: New notes
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, val in [
            ("artifact_type", artifact_type),
            ("artifact_value", artifact_value),
            ("notes", notes),
        ]:
            if val is not None:
                payload[field] = val
        if not payload:
            return "No fields to update."
        ioc = await client.put(f"/incidents/{incident_id}/host-iocs/{ioc_id}", json=payload)
        return f"✓ Host IOC updated:\n{_format_host_ioc(ioc)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_delete_host_ioc(incident_id: str, ioc_id: str) -> str:
    """Delete a host-based IOC.

    Args:
        incident_id: UUID of the incident
        ioc_id: UUID of the host IOC to delete
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/host-iocs/{ioc_id}")
        return f"✓ Host IOC {ioc_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Malware / Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_list_malware(incident_id: str) -> str:
    """List malware and tools found during the incident.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/malware")
        items = data if isinstance(data, list) else data.get("items", [])
        if not items:
            return "No malware/tools found."
        lines = [f"**Malware & Tools** ({len(items)})\n"]
        for m in items:
            lines.append(_format_malware(m))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_add_malware(
    incident_id: str,
    file_name: str,
    file_path: Optional[str] = None,
    md5: Optional[str] = None,
    sha256: Optional[str] = None,
    file_size: Optional[int] = None,
    host_id: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Add a malware/tool entry.

    Args:
        incident_id: UUID of the incident
        file_name: Filename of the malware
        file_path: Full path where found
        md5: MD5 hash
        sha256: SHA256 hash
        file_size: File size in bytes
        host_id: UUID of the host where found
        description: Description
    """
    client = get_client()
    try:
        payload: dict = {"file_name": file_name}
        for field, val in [
            ("file_path", file_path),
            ("md5", md5),
            ("sha256", sha256),
            ("file_size", file_size),
            ("host_id", host_id),
            ("description", description),
        ]:
            if val is not None:
                payload[field] = val
        malware = await client.post(f"/incidents/{incident_id}/malware", json=payload)
        return f"✓ Malware entry added:\n{_format_malware(malware)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_malware(
    incident_id: str,
    malware_id: str,
    file_name: Optional[str] = None,
    file_path: Optional[str] = None,
    md5: Optional[str] = None,
    sha256: Optional[str] = None,
    file_size: Optional[int] = None,
    description: Optional[str] = None,
) -> str:
    """Update a malware/tool entry.

    Args:
        incident_id: UUID of the incident
        malware_id: UUID of the malware entry
        file_name: New filename
        file_path: New path
        md5: New MD5 hash
        sha256: New SHA256 hash
        file_size: New file size
        description: New description
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, val in [
            ("file_name", file_name),
            ("file_path", file_path),
            ("md5", md5),
            ("sha256", sha256),
            ("file_size", file_size),
            ("description", description),
        ]:
            if val is not None:
                payload[field] = val
        if not payload:
            return "No fields to update."
        malware = await client.put(f"/incidents/{incident_id}/malware/{malware_id}", json=payload)
        return f"✓ Malware entry updated:\n{_format_malware(malware)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_delete_malware(incident_id: str, malware_id: str) -> str:
    """Delete a malware/tool entry.

    Args:
        incident_id: UUID of the incident
        malware_id: UUID of the malware entry to delete
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/malware/{malware_id}")
        return f"✓ Malware entry {malware_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
