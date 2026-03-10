"""Knowledge base tools — LOLBAS, event IDs, D3FEND, MITRE ATT&CK."""

from __future__ import annotations

from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import mcp, get_client


@mcp.tool()
async def sheetstorm_kb_lolbas(
    search: Optional[str] = None,
    binary_type: Optional[str] = None,
) -> str:
    """Search the LOLBAS (Living Off The Land Binaries and Scripts) database.

    Args:
        search: Search term (e.g. certutil, powershell, rundll32)
        binary_type: Filter by type (binary, script, library)
    """
    client = get_client()
    try:
        params: dict = {}
        if search:
            params["search"] = search
        if binary_type:
            params["type"] = binary_type
        data = await client.get("/knowledge-base/lolbas", params=params)
        items = data if isinstance(data, list) else data.get("items", data.get("results", []))

        if not items:
            return "No LOLBAS entries found."

        lines = [f"**LOLBAS Results** ({len(items)})\n"]
        for entry in items:
            lines.append(f"**{entry.get('name', 'Unknown')}**")
            if entry.get("description"):
                lines.append(f"  {entry['description']}")
            if entry.get("type"):
                lines.append(f"  Type: {entry['type']}")
            if entry.get("paths"):
                paths = entry["paths"]
                if isinstance(paths, list):
                    lines.append(f"  Paths: {', '.join(paths[:3])}")
            if entry.get("commands"):
                cmds = entry["commands"]
                if isinstance(cmds, list):
                    for cmd in cmds[:3]:
                        desc = cmd.get("description", "") if isinstance(cmd, dict) else str(cmd)
                        lines.append(f"  - {desc}")
            if entry.get("detection"):
                lines.append(f"  Detection: {entry['detection']}")
            lines.append("")

        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_kb_event_ids(
    search: Optional[str] = None,
    source: Optional[str] = None,
) -> str:
    """Search Windows Event ID reference database.

    Args:
        search: Search term (e.g. logon, process creation, 4624)
        source: Event log source (Security, System, Sysmon, PowerShell)
    """
    client = get_client()
    try:
        params: dict = {}
        if search:
            params["search"] = search
        if source:
            params["source"] = source
        data = await client.get("/knowledge-base/event-ids", params=params)
        items = data if isinstance(data, list) else data.get("items", data.get("results", []))

        if not items:
            return "No event IDs found."

        lines = [f"**Event IDs** ({len(items)})\n"]
        for e in items:
            eid = e.get("event_id", e.get("id", "?"))
            lines.append(f"**Event ID {eid}**: {e.get('description', e.get('name', 'N/A'))}")
            if e.get("source") or e.get("log"):
                lines.append(f"  Source: {e.get('source', e.get('log', 'N/A'))}")
            if e.get("category"):
                lines.append(f"  Category: {e['category']}")
            if e.get("significance"):
                lines.append(f"  Significance: {e['significance']}")
            if e.get("mitre_techniques"):
                techs = e["mitre_techniques"]
                if isinstance(techs, list):
                    lines.append(f"  MITRE: {', '.join(techs)}")
            lines.append("")

        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_kb_d3fend(
    search: Optional[str] = None,
    category: Optional[str] = None,
) -> str:
    """Search the MITRE D3FEND knowledge base of defensive techniques.

    Args:
        search: Search term
        category: D3FEND category (Harden, Detect, Isolate, Deceive, Evict)
    """
    client = get_client()
    try:
        params: dict = {}
        if search:
            params["search"] = search
        if category:
            params["category"] = category
        data = await client.get("/knowledge-base/d3fend", params=params)
        items = data if isinstance(data, list) else data.get("items", data.get("techniques", []))

        if not items:
            return "No D3FEND techniques found."

        lines = [f"**D3FEND Techniques** ({len(items)})\n"]
        for t in items:
            lines.append(f"**{t.get('id', 'N/A')}**: {t.get('name', t.get('label', 'N/A'))}")
            if t.get("definition") or t.get("description"):
                desc = t.get("definition", t.get("description", ""))
                lines.append(f"  {desc[:200]}")
            if t.get("tactic") or t.get("category"):
                lines.append(f"  Category: {t.get('tactic', t.get('category', 'N/A'))}")
            lines.append("")

        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_kb_d3fend_suggest(
    attack_techniques: str,
) -> str:
    """Suggest D3FEND defensive countermeasures for given ATT&CK techniques.

    Args:
        attack_techniques: Comma-separated MITRE ATT&CK technique IDs (e.g. T1059.001, T1548.002)
    """
    client = get_client()
    try:
        technique_ids = [t.strip() for t in attack_techniques.split(",")]
        data = await client.post(
            "/knowledge-base/d3fend/suggest",
            json={"techniques": technique_ids},
        )
        suggestions = data if isinstance(data, list) else data.get("suggestions", data.get("countermeasures", []))

        if not suggestions:
            return "No D3FEND countermeasures suggested."

        lines = [f"**D3FEND Suggestions** for {', '.join(technique_ids)}\n"]
        for s in suggestions:
            if isinstance(s, dict):
                lines.append(
                    f"**{s.get('id', 'N/A')}**: {s.get('name', s.get('label', 'N/A'))}"
                )
                if s.get("counters"):
                    counters = s["counters"]
                    if isinstance(counters, list):
                        lines.append(f"  Counters: {', '.join(counters)}")
                    else:
                        lines.append(f"  Counters: {counters}")
                if s.get("description"):
                    lines.append(f"  {s['description'][:200]}")
            else:
                lines.append(f"  - {s}")
            lines.append("")

        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_mitre_tactics() -> str:
    """Get all MITRE ATT&CK tactics."""
    client = get_client()
    try:
        data = await client.get("/knowledge-base/mitre-attack/tactics")
        items = data if isinstance(data, list) else data.get("tactics", [])

        if not items:
            return "No MITRE tactics found."

        lines = ["**MITRE ATT&CK Tactics**\n"]
        for t in items:
            tid = t.get("external_id", t.get("id", "N/A"))
            name = t.get("name", "N/A")
            desc = t.get("description", "")
            short_desc = desc[:100] + "..." if len(desc) > 100 else desc
            lines.append(f"**{tid}**: {name}")
            if short_desc:
                lines.append(f"  {short_desc}")
        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_mitre_techniques(
    search: Optional[str] = None,
    tactic: Optional[str] = None,
    platform: Optional[str] = None,
) -> str:
    """Search MITRE ATT&CK techniques.

    Args:
        search: Search term (e.g. credential dumping, phishing)
        tactic: Filter by tactic ID (e.g. TA0001)
        platform: Filter by platform (Windows, Linux, macOS, etc.)
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
        items = data if isinstance(data, list) else data.get("techniques", [])

        if not items:
            return "No MITRE techniques found."

        lines = [f"**MITRE ATT&CK Techniques** ({len(items)})\n"]
        for t in items:
            tid = t.get("external_id", t.get("id", "N/A"))
            name = t.get("name", "N/A")
            lines.append(f"**{tid}**: {name}")
            if t.get("description"):
                desc = t["description"]
                lines.append(f"  {desc[:150]}{'...' if len(desc) > 150 else ''}")
            if t.get("platforms"):
                plats = t["platforms"]
                if isinstance(plats, list):
                    lines.append(f"  Platforms: {', '.join(plats)}")
            if t.get("tactics"):
                tacs = t["tactics"]
                if isinstance(tacs, list):
                    lines.append(f"  Tactics: {', '.join(tacs)}")
            lines.append("")

        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
