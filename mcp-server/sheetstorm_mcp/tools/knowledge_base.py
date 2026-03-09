"""Knowledge base tools — LOLBAS, Windows Event IDs, MITRE ATT&CK, MITRE D3FEND reference data."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


# ---------------------------------------------------------------------------
# LOLBAS
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_kb_lolbas(
    search: Optional[str] = None,
    category: Optional[str] = None,
) -> str:
    """Search the LOLBAS (Living Off The Land Binaries and Scripts) knowledge base.

    Returns Windows binaries commonly abused by attackers with detection guidance.

    Args:
        search: Optional search term (matches name, description, MITRE ID)
        category: Optional filter by category (Download, Execute, Copy)
    """
    client = get_client()
    try:
        params: dict = {}
        if search:
            params["search"] = search
        if category:
            params["category"] = category

        data = await client.get("/knowledge-base/lolbas", params=params)
        items = data.get("items", [])

        if not items:
            return "No LOLBAS entries found."

        parts = [f"**LOLBAS** ({data.get('total', len(items))} results)\n"]
        for b in items:
            parts.append(
                f"### {b['name']} ({b.get('category', 'N/A')}) — {b.get('mitre_id', 'N/A')}\n"
                f"{b.get('description', '')}\n"
                f"**Path**: `{b.get('path', 'N/A')}`\n"
                f"**Commands**:"
            )
            for cmd in b.get("commands", []):
                parts.append(f"  • `{cmd}`")
            parts.append("**Detection**:")
            for det in b.get("detection", []):
                parts.append(f"  • {det}")
            parts.append("")

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Windows Event IDs
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_kb_event_ids(
    search: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
) -> str:
    """Search the Windows Event ID knowledge base for incident investigation.

    Returns event IDs with descriptions, categories, providers, and severity.

    Args:
        search: Optional search term (matches event ID, description, provider)
        category: Optional filter (Authentication, Privilege Use, Account Management, Lateral Movement, Persistence, Defense Evasion, PowerShell, Process, Credential Access, Firewall)
        severity: Optional filter (info, warning, critical)
    """
    client = get_client()
    try:
        params: dict = {}
        if search:
            params["search"] = search
        if category:
            params["category"] = category
        if severity:
            params["severity"] = severity

        data = await client.get("/knowledge-base/event-ids", params=params)
        items = data.get("items", [])

        if not items:
            return "No matching Event IDs found."

        parts = [f"**Windows Event IDs** ({data.get('total', len(items))} results)\n"]
        for e in items:
            sev_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(e.get("severity", ""), "")
            parts.append(
                f"**{e['event_id']}** {sev_icon} — {e.get('description', 'N/A')}\n"
                f"  Category: {e.get('category', 'N/A')} | Provider: {e.get('provider', 'N/A')} | "
                f"Severity: {e.get('severity', 'N/A')}"
            )

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# MITRE D3FEND
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_kb_d3fend(
    search: Optional[str] = None,
    tactic: Optional[str] = None,
    attack_id: Optional[str] = None,
) -> str:
    """Search the MITRE D3FEND defensive countermeasures knowledge base.

    Args:
        search: Optional search term (matches name, description, D3FEND ID)
        tactic: Optional filter by D3FEND tactic (Harden, Detect, Isolate, Deceive, Evict, Restore)
        attack_id: Optional MITRE ATT&CK technique ID to find matching countermeasures
    """
    client = get_client()
    try:
        params: dict = {}
        if search:
            params["search"] = search
        if tactic:
            params["tactic"] = tactic
        if attack_id:
            params["attack_id"] = attack_id

        data = await client.get("/knowledge-base/d3fend", params=params)
        items = data.get("items", [])

        if not items:
            return "No D3FEND techniques found."

        parts = [f"**MITRE D3FEND** ({data.get('total', len(items))} results)\n"]
        for t in items:
            parts.append(
                f"### {t['id']} — {t['name']} ({t.get('tactic', 'N/A')})\n"
                f"{t.get('description', '')}\n"
                f"**ATT&CK Mappings**: {', '.join(t.get('mitre_attack_mappings', []))}\n"
                f"**Examples**: {', '.join(t.get('examples', []))}\n"
            )

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_kb_d3fend_suggest(
    attack_techniques: list[str],
) -> str:
    """Given a list of MITRE ATT&CK technique IDs, suggest D3FEND countermeasures.

    Args:
        attack_techniques: List of ATT&CK technique IDs (e.g. ["T1059", "T1078", "T1021"])
    """
    client = get_client()
    try:
        data = await client.post(
            "/knowledge-base/d3fend/suggest",
            json={"attack_techniques": attack_techniques},
        )
        items = data.get("items", [])

        if not items:
            return "No D3FEND countermeasures found for the given ATT&CK techniques."

        parts = [f"**Suggested D3FEND Countermeasures** ({len(items)} matches)\n"]
        for t in items:
            matched = ", ".join(t.get("matched_techniques", []))
            parts.append(
                f"### {t['id']} — {t['name']} ({t.get('tactic', 'N/A')})\n"
                f"{t.get('description', '')}\n"
                f"**Addresses**: {matched}\n"
                f"**Examples**: {', '.join(t.get('examples', []))}\n"
            )

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# MITRE ATT&CK — Enterprise Techniques & Tactics
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_get_mitre_tactics() -> str:
    """List all 14 MITRE ATT&CK Enterprise tactics with their IDs and descriptions."""
    client = get_client()
    try:
        data = await client.get("/knowledge-base/mitre-attack/tactics")
        items = data.get("items", [])

        if not items:
            return "No ATT&CK tactics available."

        parts = [f"**MITRE ATT&CK Tactics** ({len(items)} total)\n"]
        for t in items:
            parts.append(
                f"**{t['id']}** — {t['name']}\n"
                f"  {t.get('description', '')}\n"
            )

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_mitre_techniques(
    search: Optional[str] = None,
    tactic: Optional[str] = None,
    platform: Optional[str] = None,
) -> str:
    """Search MITRE ATT&CK Enterprise techniques with detection guidance.

    Returns techniques with ID, name, tactic, description, platforms, and detection hints.

    Args:
        search: Optional free-text search across technique ID, name, description
        tactic: Optional tactic name filter (e.g., "Initial Access", "Execution", "Persistence")
        platform: Optional platform filter (Windows, Linux, macOS, Cloud, Network, Containers)
    """
    client = get_client()
    try:
        params: dict = {}
        if search:
            params["search"] = search
        if tactic:
            params["tactic"] = tactic
        if platform:
            params["platform"] = platform

        data = await client.get("/knowledge-base/mitre-attack", params=params)
        items = data.get("items", [])

        if not items:
            return "No matching ATT&CK techniques found."

        parts = [f"**MITRE ATT&CK Techniques** ({data.get('total', len(items))} results)\n"]
        for t in items:
            platforms = ", ".join(t.get("platforms", []))
            parts.append(
                f"### {t['id']} — {t['name']} ({t.get('tactic', 'N/A')})\n"
                f"{t.get('description', '')}\n"
                f"**Platforms**: {platforms}\n"
                f"**Detection**: {t.get('detection', 'N/A')}\n"
            )

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
