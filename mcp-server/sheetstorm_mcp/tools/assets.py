"""Compromised assets tools — hosts and accounts management."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_host(h: dict) -> str:
    return (
        f"**{h.get('hostname', 'Unknown')}** (ID: {h.get('id', 'N/A')})\n"
        f"  IP: {h.get('ip_address', 'N/A')} | OS: {h.get('os', 'N/A')} | "
        f"Status: {h.get('status', 'N/A')}\n"
        f"  First Seen: {h.get('first_seen', 'N/A')} | Last Seen: {h.get('last_seen', 'N/A')}"
    )


def _format_account(a: dict) -> str:
    domain = a.get("domain", "")
    username = a.get("username", "Unknown")
    display = f"{domain}\\{username}" if domain else username
    return (
        f"**{display}** (ID: {a.get('id', 'N/A')})\n"
        f"  Type: {a.get('account_type', 'N/A')} | SID: {a.get('sid', 'N/A')}\n"
        f"  Host: {a.get('host_name', a.get('host_id', 'N/A'))}\n"
        f"  Password: {'●●●●●●●●' if a.get('has_password') or a.get('password') else 'not set'}"
    )


# ---------------------------------------------------------------------------
# Host tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def sheetstorm_list_hosts(incident_id: str) -> str:
    """List compromised hosts for an incident.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/hosts")
        items = data if isinstance(data, list) else data.get("items", data.get("hosts", []))

        if not items:
            return "No compromised hosts found."

        lines = [f"**Compromised Hosts** ({len(items)})\n"]
        for h in items:
            lines.append(_format_host(h))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_add_host(
    incident_id: str,
    hostname: str,
    ip_address: Optional[str] = None,
    os: Optional[str] = None,
    status: str = "compromised",
    notes: Optional[str] = None,
) -> str:
    """Add a compromised host to an incident.

    Args:
        incident_id: UUID of the incident
        hostname: Hostname (e.g. WORKSTATION-01)
        ip_address: IP address
        os: Operating system
        status: Host status (compromised, contained, cleaned)
        notes: Additional notes
    """
    client = get_client()
    try:
        payload: dict = {"hostname": hostname, "status": status}
        if ip_address:
            payload["ip_address"] = ip_address
        if os:
            payload["os"] = os
        if notes:
            payload["notes"] = notes

        host = await client.post(f"/incidents/{incident_id}/hosts", json=payload)
        return f"✓ Host added:\n{_format_host(host)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_host(
    incident_id: str,
    host_id: str,
    hostname: Optional[str] = None,
    ip_address: Optional[str] = None,
    os: Optional[str] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Update a compromised host.

    Args:
        incident_id: UUID of the incident
        host_id: UUID of the host
        hostname: New hostname
        ip_address: New IP address
        os: New OS
        status: New status (compromised, contained, cleaned)
        notes: New notes
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, value in [
            ("hostname", hostname),
            ("ip_address", ip_address),
            ("os", os),
            ("status", status),
            ("notes", notes),
        ]:
            if value is not None:
                payload[field] = value

        if not payload:
            return "No fields to update."

        host = await client.put(f"/incidents/{incident_id}/hosts/{host_id}", json=payload)
        return f"✓ Host updated:\n{_format_host(host)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_delete_host(incident_id: str, host_id: str) -> str:
    """Delete a compromised host.

    Args:
        incident_id: UUID of the incident
        host_id: UUID of the host to delete
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/hosts/{host_id}")
        return f"✓ Host {host_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Account tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def sheetstorm_list_accounts(incident_id: str) -> str:
    """List compromised accounts for an incident.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/accounts")
        items = data if isinstance(data, list) else data.get("items", data.get("accounts", []))

        if not items:
            return "No compromised accounts found."

        lines = [f"**Compromised Accounts** ({len(items)})\n"]
        for a in items:
            lines.append(_format_account(a))
            lines.append("")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_add_account(
    incident_id: str,
    username: str,
    domain: Optional[str] = None,
    password: Optional[str] = None,
    account_type: str = "domain",
    host_id: Optional[str] = None,
    sid: Optional[str] = None,
) -> str:
    """Add a compromised account. Password will be encrypted at rest.

    Args:
        incident_id: UUID of the incident
        username: Account username
        domain: Account domain (e.g. CORP)
        password: Account password (will be encrypted)
        account_type: Type (local, domain, service)
        host_id: UUID of the associated host
        sid: Security Identifier
    """
    client = get_client()
    try:
        payload: dict = {"username": username, "account_type": account_type}
        if domain:
            payload["domain"] = domain
        if password:
            payload["password"] = password
        if host_id:
            payload["host_id"] = host_id
        if sid:
            payload["sid"] = sid

        account = await client.post(f"/incidents/{incident_id}/accounts", json=payload)
        return f"✓ Account added:\n{_format_account(account)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_reveal_account_password(incident_id: str, account_id: str) -> str:
    """Reveal decrypted password for a compromised account. Requires appropriate permissions.

    Args:
        incident_id: UUID of the incident
        account_id: UUID of the account
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/accounts/{account_id}/reveal")
        return f"Password: {data.get('password', 'N/A')}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
