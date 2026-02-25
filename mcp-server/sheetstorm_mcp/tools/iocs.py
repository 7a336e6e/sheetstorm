"""IOC management tools — network IOCs, host-based IOCs, and malware/tools."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _format_network_ioc(i: dict) -> str:
    return (
        f"**{i.get('value', 'N/A')}** (ID: {i.get('id', 'N/A')})\n"
        f"  Type: {i.get('indicator_type', 'N/A')} | "
        f"Protocol: {i.get('protocol', 'N/A')} | Port: {i.get('port', 'N/A')}\n"
        f"  Source Host: {i.get('source_host_name', i.get('source_host_id', 'N/A'))}\n"
        f"  Description: {i.get('description', 'N/A')}"
    )


def _format_host_ioc(i: dict) -> str:
    return (
        f"**{i.get('value', 'N/A')}** (ID: {i.get('id', 'N/A')})\n"
        f"  Type: {i.get('indicator_type', 'N/A')}\n"
        f"  Host: {i.get('host_name', i.get('host_id', 'N/A'))}\n"
        f"  Notes: {i.get('notes', 'N/A')}"
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
    parts.append(f"  Host: {m.get('host_name', m.get('host_id', 'N/A'))}")
    if m.get("description"):
        parts.append(f"  Description: {m['description']}")
    return "\n".join(parts)


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
    indicator_type: str,
    value: str,
    protocol: Optional[str] = None,
    port: Optional[int] = None,
    source_host_id: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Add a network IOC (IP address, domain, or URL).

    Args:
        incident_id: UUID of the incident
        indicator_type: Type of indicator (ip, domain, url)
        value: The indicator value (e.g. 192.168.1.100, evil.com)
        protocol: Network protocol (TCP, UDP, HTTP, etc.)
        port: Port number
        source_host_id: UUID of the source host
        description: Description
    """
    client = get_client()
    try:
        payload: dict = {"indicator_type": indicator_type, "value": value}
        if protocol:
            payload["protocol"] = protocol
        if port is not None:
            payload["port"] = port
        if source_host_id:
            payload["source_host_id"] = source_host_id
        if description:
            payload["description"] = description

        ioc = await client.post(f"/incidents/{incident_id}/network-iocs", json=payload)
        return f"✓ Network IOC added:\n{_format_network_ioc(ioc)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_network_ioc(
    incident_id: str,
    ioc_id: str,
    indicator_type: Optional[str] = None,
    value: Optional[str] = None,
    protocol: Optional[str] = None,
    port: Optional[int] = None,
    description: Optional[str] = None,
) -> str:
    """Update a network IOC.

    Args:
        incident_id: UUID of the incident
        ioc_id: UUID of the network IOC
        indicator_type: New type
        value: New value
        protocol: New protocol
        port: New port
        description: New description
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, val in [
            ("indicator_type", indicator_type),
            ("value", value),
            ("protocol", protocol),
            ("port", port),
            ("description", description),
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
    indicator_type: str,
    value: str,
    host_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Add a host-based IOC.

    Args:
        incident_id: UUID of the incident
        indicator_type: Type (file_hash, registry_key, process, service, scheduled_task)
        value: The indicator value
        host_id: UUID of the associated host
        notes: Additional notes
    """
    client = get_client()
    try:
        payload: dict = {"indicator_type": indicator_type, "value": value}
        if host_id:
            payload["host_id"] = host_id
        if notes:
            payload["notes"] = notes
        ioc = await client.post(f"/incidents/{incident_id}/host-iocs", json=payload)
        return f"✓ Host IOC added:\n{_format_host_ioc(ioc)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_host_ioc(
    incident_id: str,
    ioc_id: str,
    indicator_type: Optional[str] = None,
    value: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Update a host-based IOC.

    Args:
        incident_id: UUID of the incident
        ioc_id: UUID of the host IOC
        indicator_type: New type
        value: New value
        notes: New notes
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, val in [
            ("indicator_type", indicator_type),
            ("value", value),
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
