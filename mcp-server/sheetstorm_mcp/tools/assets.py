"""Compromised assets tools — hosts and accounts management."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import get_client, mcp

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_ACQ_FLAGS = ("disk_imaged", "memory_captured", "logs_collected", "forensically_sound")


def _format_host(h: dict) -> str:
    text = (
        f"**{h.get('hostname', 'Unknown')}** (ID: {h.get('id', 'N/A')})\n"
        f"  IP: {h.get('ip_address', 'N/A')} | OS: {h.get('os_version', 'N/A')} | "
        f"Containment: {h.get('containment_status', 'N/A')} | "
        f"Triage: {h.get('triage_status') or 'N/A'}\n"
        f"  System: {h.get('system_type', 'N/A')} | "
        f"First Seen: {h.get('first_seen', 'N/A')} | Last Seen: {h.get('last_seen', 'N/A')}"
    )
    acq = h.get("acquisition_status") or {}
    if isinstance(acq, dict) and acq:
        flags = ", ".join(f"{k}={'yes' if acq.get(k) else 'no'}" for k in _ACQ_FLAGS if k in acq)
        if acq.get("acquired_at"):
            flags += f"{', ' if flags else ''}acquired_at={acq['acquired_at']}"
        text += f"\n  Acquisition: {flags}"
    return text


def _acquisition_updates(
    disk_imaged: Optional[bool],
    memory_captured: Optional[bool],
    logs_collected: Optional[bool],
    forensically_sound: Optional[bool],
    acquired_at: Optional[str],
) -> dict:
    values = {
        "disk_imaged": disk_imaged,
        "memory_captured": memory_captured,
        "logs_collected": logs_collected,
        "forensically_sound": forensically_sound,
        "acquired_at": acquired_at,
    }
    return {k: v for k, v in values.items() if v is not None}


def _format_account(a: dict) -> str:
    domain = a.get("domain", "")
    account_name = a.get("account_name", "Unknown")
    display = f"{domain}\\{account_name}" if domain else account_name
    host_info = a.get("host_system", "")
    if not host_info and isinstance(a.get("host"), dict):
        host_info = a["host"].get("hostname", a.get("host_id", "N/A"))
    return (
        f"**{display}** (ID: {a.get('id', 'N/A')})\n"
        f"  Type: {a.get('account_type', 'N/A')} | SID: {a.get('sid', 'N/A')}\n"
        f"  Host: {host_info or a.get('host_id', 'N/A')}\n"
        f"  Privileged: {'Yes' if a.get('is_privileged') else 'No'} | "
        f"Password: {'●●●●●●●●' if a.get('has_password') or a.get('password') else 'not set'}"
    )


# ---------------------------------------------------------------------------
# Host tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def sheetstorm_list_hosts(
    incident_id: str,
    triage_status: Optional[str] = None,
    acquisition: Optional[str] = None,
    containment_status: Optional[str] = None,
) -> str:
    """List compromised hosts for an incident (with triage verdict and acquisition status).

    Args:
        incident_id: UUID of the incident
        triage_status: Only these verdicts, comma-separated (clean, compromised, under_analysis, suspicious)
        acquisition: Acquisition flags that must be true, comma-separated (disk_imaged, memory_captured,
            logs_collected, forensically_sound); prefix a flag with ! for "not done",
            e.g. "memory_captured,!disk_imaged"
        containment_status: Only this containment status
    """
    client = get_client()
    try:
        params: dict = {"per_page": 200}
        for key, value in (("triage_status", triage_status), ("acquisition", acquisition),
                           ("containment_status", containment_status)):
            if value:
                params[key] = value
        data = await client.get(f"/incidents/{incident_id}/hosts", params=params)
        items = data if isinstance(data, list) else data.get("items", data.get("hosts", []))
        total = data.get("total", len(items)) if isinstance(data, dict) else len(items)

        if not items:
            return "No compromised hosts found."

        lines = [f"**Compromised Hosts** ({total}{', showing ' + str(len(items)) if total > len(items) else ''})\n"]
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
    os_version: Optional[str] = None,
    system_type: Optional[str] = None,
    containment_status: str = "active",
    notes: Optional[str] = None,
    triage_status: Optional[str] = None,
    disk_imaged: Optional[bool] = None,
    memory_captured: Optional[bool] = None,
    logs_collected: Optional[bool] = None,
    forensically_sound: Optional[bool] = None,
    acquired_at: Optional[str] = None,
) -> str:
    """Add a compromised host to an incident, with optional forensic triage and
    evidence-acquisition status.

    Args:
        incident_id: UUID of the incident
        hostname: Hostname (e.g. WORKSTATION-01)
        ip_address: IP address
        os_version: Operating system version
        system_type: System type (e.g. workstation, server)
        containment_status: Host status — one of: active, compromised, isolated, contained, reimaged, cleaned, decommissioned
        notes: Additional notes
        triage_status: Forensic verdict — one of: clean, compromised, under_analysis (default), suspicious
        disk_imaged: Whether a disk image has been acquired
        memory_captured: Whether memory has been captured
        logs_collected: Whether logs have been collected
        forensically_sound: Whether acquisition followed a forensically sound process
        acquired_at: ISO 8601 time evidence was acquired
    """
    client = get_client()
    try:
        payload: dict = {"hostname": hostname, "containment_status": containment_status}
        if triage_status:
            payload["triage_status"] = triage_status
        acq = _acquisition_updates(disk_imaged, memory_captured, logs_collected, forensically_sound, acquired_at)
        if acq:
            payload["acquisition_status"] = acq
        if ip_address:
            payload["ip_address"] = ip_address
        if os_version:
            payload["os_version"] = os_version
        if system_type:
            payload["system_type"] = system_type
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
    os_version: Optional[str] = None,
    system_type: Optional[str] = None,
    containment_status: Optional[str] = None,
    notes: Optional[str] = None,
    triage_status: Optional[str] = None,
    disk_imaged: Optional[bool] = None,
    memory_captured: Optional[bool] = None,
    logs_collected: Optional[bool] = None,
    forensically_sound: Optional[bool] = None,
    acquired_at: Optional[str] = None,
) -> str:
    """Update a compromised host, including triage verdict and acquisition status.
    Acquisition flags that are not given keep their current values.

    Args:
        incident_id: UUID of the incident
        host_id: UUID of the host
        hostname: New hostname
        ip_address: New IP address
        os_version: New OS version
        system_type: New system type
        containment_status: New status — one of: active, compromised, isolated, contained, reimaged, cleaned, decommissioned
        notes: New notes
        triage_status: Forensic verdict — one of: clean, compromised, under_analysis, suspicious
        disk_imaged: Whether a disk image has been acquired
        memory_captured: Whether memory has been captured
        logs_collected: Whether logs have been collected
        forensically_sound: Whether acquisition followed a forensically sound process
        acquired_at: ISO 8601 time evidence was acquired
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, value in [
            ("hostname", hostname),
            ("ip_address", ip_address),
            ("os_version", os_version),
            ("system_type", system_type),
            ("containment_status", containment_status),
            ("notes", notes),
            ("triage_status", triage_status),
        ]:
            if value is not None:
                payload[field] = value

        acq = _acquisition_updates(disk_imaged, memory_captured, logs_collected, forensically_sound, acquired_at)
        if acq:
            # The backend replaces acquisition_status wholesale — merge with current values.
            current: dict = {}
            # `focus` returns the page holding this host; per_page=1 makes it exactly that host.
            data = await client.get(f"/incidents/{incident_id}/hosts", params={"focus": host_id, "per_page": 1})
            for h in data.get("items", []) if isinstance(data, dict) else data:
                if str(h.get("id")) == host_id and isinstance(h.get("acquisition_status"), dict):
                    current = dict(h["acquisition_status"])
                    break
            current.update(acq)
            payload["acquisition_status"] = current

        if not payload:
            return "No fields to update."

        host = await client.put(f"/incidents/{incident_id}/hosts/{host_id}", json=payload)
        return f"✓ Host updated:\n{_format_host(host)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_bulk_update_hosts(
    incident_id: str,
    host_ids: list[str],
    triage_status: Optional[str] = None,
    containment_status: Optional[str] = None,
) -> str:
    """Set the triage verdict and/or containment status of many hosts at once (max 500).
    All hosts must belong to the incident; otherwise nothing is changed.

    Args:
        incident_id: UUID of the incident
        host_ids: Host UUIDs to update
        triage_status: New verdict — one of: clean, compromised, under_analysis, suspicious
        containment_status: New status — one of: active, compromised, isolated, contained, reimaged, cleaned, decommissioned
    """
    client = get_client()
    payload: dict = {"host_ids": list(host_ids)}
    if triage_status:
        payload["triage_status"] = triage_status
    if containment_status:
        payload["containment_status"] = containment_status
    if len(payload) == 1:
        return "Nothing to update: give triage_status and/or containment_status."
    try:
        data = await client.patch(f"/incidents/{incident_id}/hosts/bulk", json=payload)
        updated = data.get("updated", 0) if isinstance(data, dict) else 0
        names = ", ".join(h.get("hostname", "?") for h in (data.get("items") or [])[:20]) \
            if isinstance(data, dict) else ""
        return f"✓ {updated} host(s) updated" + (f": {names}" if names else "")
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
    account_name: str,
    domain: Optional[str] = None,
    password: Optional[str] = None,
    account_type: str = "domain",
    host_id: Optional[str] = None,
    sid: Optional[str] = None,
    is_privileged: bool = False,
    datetime_seen: Optional[str] = None,
) -> str:
    """Add a compromised account. Password will be encrypted at rest.

    Args:
        incident_id: UUID of the incident
        account_name: Account name
        domain: Account domain (e.g. CORP)
        password: Account password (will be encrypted)
        account_type: Type (local, domain, service)
        host_id: UUID of the associated host
        sid: Security Identifier
        is_privileged: Whether this is a privileged account
        datetime_seen: ISO-8601 timestamp when compromise was observed (defaults to now)
    """
    from datetime import datetime, timezone

    client = get_client()
    try:
        payload: dict = {
            "account_name": account_name,
            "account_type": account_type,
            "datetime_seen": datetime_seen or datetime.now(timezone.utc).isoformat(),
        }
        if domain:
            payload["domain"] = domain
        if password:
            payload["password"] = password
        if host_id:
            payload["host_id"] = host_id
        if sid:
            payload["sid"] = sid
        if is_privileged:
            payload["is_privileged"] = is_privileged

        account = await client.post(f"/incidents/{incident_id}/accounts", json=payload)
        return f"✓ Account added:\n{_format_account(account)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_account(
    incident_id: str,
    account_id: str,
    account_name: Optional[str] = None,
    domain: Optional[str] = None,
    account_type: Optional[str] = None,
    status: Optional[str] = None,
    sid: Optional[str] = None,
    is_privileged: Optional[bool] = None,
    host_id: Optional[str] = None,
    datetime_seen: Optional[str] = None,
    notes: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    """Update a compromised account. Only the fields given are changed.

    Args:
        incident_id: UUID of the incident
        account_id: UUID of the account
        account_name: New account name
        domain: New domain
        account_type: One of: domain, local, ftp, service, application, admin, other
        status: One of: active, disabled, reset, deleted
        sid: Security Identifier
        is_privileged: Whether the account is privileged
        host_id: UUID of the associated host ("" to unlink)
        datetime_seen: ISO 8601 time the compromise was observed
        notes: Notes
        password: New compromised password (encrypted at rest; "" clears it)
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, value in [
            ("account_name", account_name),
            ("domain", domain),
            ("account_type", account_type),
            ("status", status),
            ("sid", sid),
            ("is_privileged", is_privileged),
            ("host_id", host_id),
            ("datetime_seen", datetime_seen),
            ("notes", notes),
            ("password", password),
        ]:
            if value is not None:
                payload[field] = value
        if "host_id" in payload and payload["host_id"] == "":
            payload["host_id"] = None
        if not payload:
            return "No fields to update."
        account = await client.put(f"/incidents/{incident_id}/accounts/{account_id}", json=payload)
        return f"✓ Account updated:\n{_format_account(account)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_delete_account(incident_id: str, account_id: str) -> str:
    """Delete a compromised account record.

    Args:
        incident_id: UUID of the incident
        account_id: UUID of the account to delete
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/accounts/{account_id}")
        return f"✓ Account {account_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_reveal_account_password(incident_id: str, account_id: str) -> str:
    """Reveal the decrypted compromised password of ONE account. Requires the
    compromised_accounts:reveal permission; every reveal is audit-logged.

    WARNING: the plaintext password is returned into this conversation and
    therefore into the AI model's context and the MCP client's logs. Only use
    it when the user explicitly asks to see this specific password.

    Args:
        incident_id: UUID of the incident
        account_id: UUID of the account
    """
    client = get_client()
    try:
        target = None
        try:
            # Preferred: single-account reveal (decrypts only this account).
            target = await client.get(
                f"/incidents/{incident_id}/accounts/{account_id}", params={"reveal": "true"}
            )
        except SheetStormAPIError as exc:
            if exc.status_code not in (404, 405):
                raise
        if not target or str(target.get("id")) != account_id:
            target = await _reveal_via_list(client, incident_id, account_id)
        if target is None:
            return f"✗ Account {account_id} not found."
        pw = target.get("password")
        if not target.get("has_password") or pw is None:
            return f"Account {target.get('account_name', 'N/A')} has no stored password."
        if pw == "********":
            return "✗ Password not revealed — you lack the compromised_accounts:reveal permission."
        return f"Password for {target.get('account_name', 'N/A')}: {pw}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


async def _reveal_via_list(client, incident_id: str, account_id: str) -> dict | None:
    """Fallback when no single-account endpoint exists: find the account without
    revealing anything, then reveal only the accounts sharing its exact name and
    return just the target (other accounts never reach the tool output)."""
    page = 1
    name = None
    while name is None:
        data = await client.get(
            f"/incidents/{incident_id}/accounts", params={"page": page, "per_page": 200}
        )
        items = data.get("items", []) if isinstance(data, dict) else data
        for acct in items:
            if str(acct.get("id")) == account_id:
                name = acct.get("account_name") or ""
                break
        if name is not None or page >= (data.get("pages", 1) if isinstance(data, dict) else 1):
            break
        page += 1
    if name is None:
        return None
    data = await client.get(
        f"/incidents/{incident_id}/accounts",
        params={"reveal": "true", "search": name, "per_page": 200},
    )
    items = data.get("items", []) if isinstance(data, dict) else data
    return next((a for a in items if str(a.get("id")) == account_id), None)
