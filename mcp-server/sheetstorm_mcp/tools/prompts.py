"""MCP Prompt templates — pre-built analytical prompts for incident response.

These prompts help LLMs perform structured IR analysis by providing
domain-specific context and formatting guidance.
"""

from __future__ import annotations

from sheetstorm_mcp.server import mcp, get_client
from sheetstorm_mcp.client import SheetStormAPIError


# ---------------------------------------------------------------------------
# Analyze Incident
# ---------------------------------------------------------------------------

@mcp.prompt()
async def analyze_incident(incident_id: str) -> str:
    """Perform a comprehensive analysis of an incident including timeline, IOCs, assets, and recommendations.

    Args:
        incident_id: UUID of the incident to analyze
    """
    client = get_client()
    try:
        incident = await client.get(f"/incidents/{incident_id}")
    except SheetStormAPIError:
        return f"Could not fetch incident {incident_id}. Please verify the ID and try again."

    # Gather all related data in parallel-safe order
    timeline_items = []
    hosts = []
    accounts = []
    network_iocs = []
    host_iocs = []
    malware_iocs = []
    tasks = []
    notes = []

    try:
        tl = await client.get(f"/incidents/{incident_id}/timeline")
        timeline_items = tl if isinstance(tl, list) else tl.get("items", tl.get("timeline", []))
    except SheetStormAPIError:
        pass

    for endpoint, target in [
        (f"/incidents/{incident_id}/hosts", "hosts"),
        (f"/incidents/{incident_id}/accounts", "accounts"),
        (f"/incidents/{incident_id}/iocs/network", "network"),
        (f"/incidents/{incident_id}/iocs/host", "host"),
        (f"/incidents/{incident_id}/iocs/malware", "malware"),
        (f"/incidents/{incident_id}/tasks", "tasks"),
        (f"/incidents/{incident_id}/notes", "notes"),
    ]:
        try:
            data = await client.get(endpoint)
            items = data.get("items", data) if isinstance(data, dict) else data
            if target == "hosts":
                hosts = items
            elif target == "accounts":
                accounts = items
            elif target == "network":
                network_iocs = items
            elif target == "host":
                host_iocs = items
            elif target == "malware":
                malware_iocs = items
            elif target == "tasks":
                tasks = items
            elif target == "notes":
                notes = items
        except SheetStormAPIError:
            pass

    parts = [
        "You are an expert incident responder. Analyze the following incident data and provide:\n"
        "1. **Incident Summary** — what happened, when, and how severe\n"
        "2. **Attack Timeline** — key events in chronological order with MITRE ATT&CK mapping\n"
        "3. **Indicators of Compromise** — categorized list with risk assessment\n"
        "4. **Compromised Assets** — affected systems and accounts with impact\n"
        "5. **Current Status** — progress, open tasks, blockers\n"
        "6. **Recommendations** — prioritized next steps\n"
        "7. **Gaps** — missing data or investigation steps needed\n",
        f"---\n\n# Incident: {incident.get('title', 'Unknown')}\n",
        f"**ID**: {incident.get('id')}",
        f"**Status**: {incident.get('status')} | **Phase**: {incident.get('phase')} | "
        f"**Severity**: {incident.get('severity')}",
        f"**Classification**: {incident.get('classification', 'N/A')}",
        f"**Created**: {incident.get('created_at')} | **Updated**: {incident.get('updated_at')}",
    ]

    if incident.get("description"):
        parts.append(f"\n**Description**:\n{incident['description']}")

    # Timeline
    if timeline_items:
        parts.append(f"\n## Timeline ({len(timeline_items)} events)")
        for e in timeline_items[:50]:
            mitre = ""
            if e.get("mitre_tactic"):
                mitre = f" [{e['mitre_tactic']}/{e.get('mitre_technique', '?')}]"
            parts.append(f"- [{e.get('event_timestamp', '?')}] {e.get('description', '?')}{mitre}")

    # IOCs
    total_iocs = len(network_iocs) + len(host_iocs) + len(malware_iocs)
    if total_iocs:
        parts.append(f"\n## IOCs ({total_iocs} total)")
        if network_iocs:
            parts.append("### Network Indicators")
            for i in network_iocs[:30]:
                parts.append(f"- [{i.get('indicator_type', '?')}] {i.get('value', '?')} — {i.get('description', '')}")
        if host_iocs:
            parts.append("### Host-Based Indicators")
            for i in host_iocs[:30]:
                parts.append(f"- [{i.get('indicator_type', '?')}] {i.get('value', '?')} — {i.get('description', '')}")
        if malware_iocs:
            parts.append("### Malware/Tools")
            for m in malware_iocs[:20]:
                parts.append(f"- {m.get('name', '?')} ({m.get('type', '?')}) — {m.get('description', '')}")

    # Assets
    if hosts or accounts:
        parts.append(f"\n## Compromised Assets ({len(hosts)} hosts, {len(accounts)} accounts)")
        for h in hosts[:30]:
            parts.append(f"- Host: {h.get('hostname', '?')} ({h.get('ip_address', '?')}) — {h.get('compromise_type', '?')}")
        for a in accounts[:30]:
            parts.append(f"- Account: {a.get('account_name', '?')} ({a.get('account_type', '?')}) — {a.get('compromise_type', '?')}")

    # Tasks
    if tasks:
        parts.append(f"\n## Tasks ({len(tasks)} total)")
        for t in tasks[:30]:
            status_icon = {"completed": "✅", "in_progress": "🔄"}.get(t.get("status", ""), "⬜")
            parts.append(f"- {status_icon} [{t.get('priority', '?')}] {t.get('title', '?')}")

    # Case notes
    if notes:
        parts.append(f"\n## Case Notes ({len(notes)} total)")
        for n in notes[:20]:
            parts.append(f"- **{n.get('title', '?')}** ({n.get('category', '?')}): {(n.get('content', '') or '')[:150]}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Generate Timeline Summary
# ---------------------------------------------------------------------------

@mcp.prompt()
async def generate_timeline_summary(incident_id: str) -> str:
    """Generate a narrative timeline summary for an incident.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        incident = await client.get(f"/incidents/{incident_id}")
        tl = await client.get(f"/incidents/{incident_id}/timeline")
        events = tl if isinstance(tl, list) else tl.get("items", tl.get("timeline", []))
    except SheetStormAPIError as exc:
        return f"Could not fetch incident data: {exc}"

    parts = [
        "You are an expert incident responder. Based on the timeline events below, "
        "write a clear **narrative summary** of the incident timeline.\n\n"
        "Structure your response as:\n"
        "1. **Initial Compromise** — how and when the attacker gained access\n"
        "2. **Lateral Movement** — how the attacker moved through the environment\n"
        "3. **Actions on Objectives** — what the attacker did (data exfil, ransomware, etc.)\n"
        "4. **Detection & Response** — when and how the incident was detected\n"
        "5. **Key Observations** — notable patterns, TTPs, or gaps\n\n"
        "Map each phase to MITRE ATT&CK tactics/techniques where applicable.\n",
        f"---\n\n# Incident: {incident.get('title', 'Unknown')}",
        f"Severity: {incident.get('severity')} | Status: {incident.get('status')} | Phase: {incident.get('phase')}\n",
    ]

    if events:
        parts.append(f"## Timeline ({len(events)} events)\n")
        for e in events:
            mitre = ""
            if e.get("mitre_tactic"):
                mitre = f" | MITRE: {e['mitre_tactic']}/{e.get('mitre_technique', '?')}"
            parts.append(
                f"- **{e.get('event_timestamp', '?')}** [{e.get('event_type', '?')}] "
                f"{e.get('description', '?')}{mitre}"
            )
            if e.get("source"):
                parts[-1] += f" (source: {e['source']})"
    else:
        parts.append("No timeline events recorded yet.")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Suggest MITRE ATT&CK Mapping
# ---------------------------------------------------------------------------

@mcp.prompt()
async def suggest_mitre_mapping(incident_id: str) -> str:
    """Suggest MITRE ATT&CK technique mappings based on incident data.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        incident = await client.get(f"/incidents/{incident_id}")
        tl = await client.get(f"/incidents/{incident_id}/timeline")
        events = tl if isinstance(tl, list) else tl.get("items", tl.get("timeline", []))
    except SheetStormAPIError as exc:
        return f"Could not fetch incident data: {exc}"

    ioc_data = {}
    for endpoint, label in [
        (f"/incidents/{incident_id}/iocs/network", "network"),
        (f"/incidents/{incident_id}/iocs/host", "host"),
        (f"/incidents/{incident_id}/iocs/malware", "malware"),
    ]:
        try:
            data = await client.get(endpoint)
            ioc_data[label] = data.get("items", data) if isinstance(data, dict) else data
        except SheetStormAPIError:
            ioc_data[label] = []

    parts = [
        "You are a MITRE ATT&CK expert. Based on the incident data below, suggest:\n\n"
        "1. **Technique Mappings** — for each timeline event and IOC, suggest the most likely "
        "ATT&CK technique(s) with confidence level (high/medium/low)\n"
        "2. **Tactic Chain** — reconstruct the likely attack path through ATT&CK tactics\n"
        "3. **Missing Coverage** — identify ATT&CK tactics that likely occurred but have no evidence\n"
        "4. **Detection Gaps** — suggest what additional data sources would improve coverage\n\n"
        "Format each mapping as: `Tactic > Technique (ID)` with a brief justification.\n",
        f"---\n\n# Incident: {incident.get('title', 'Unknown')}",
        f"Classification: {incident.get('classification', 'N/A')}\n",
    ]

    if events:
        parts.append("## Timeline Events")
        for e in events[:40]:
            existing = ""
            if e.get("mitre_tactic"):
                existing = f" [EXISTING: {e['mitre_tactic']}/{e.get('mitre_technique', '?')}]"
            parts.append(f"- [{e.get('event_type', '?')}] {e.get('description', '?')}{existing}")

    for label, items in ioc_data.items():
        if items:
            parts.append(f"\n## {label.title()} IOCs")
            for i in items[:20]:
                parts.append(f"- [{i.get('indicator_type', i.get('type', '?'))}] "
                             f"{i.get('value', i.get('name', '?'))}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Identify Lateral Movement
# ---------------------------------------------------------------------------

@mcp.prompt()
async def identify_lateral_movement(incident_id: str) -> str:
    """Analyze an incident for evidence of lateral movement.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        incident = await client.get(f"/incidents/{incident_id}")
        tl = await client.get(f"/incidents/{incident_id}/timeline")
        events = tl if isinstance(tl, list) else tl.get("items", tl.get("timeline", []))
    except SheetStormAPIError as exc:
        return f"Could not fetch incident data: {exc}"

    hosts = []
    accounts = []
    try:
        h = await client.get(f"/incidents/{incident_id}/hosts")
        hosts = h.get("items", h) if isinstance(h, dict) else h
    except SheetStormAPIError:
        pass
    try:
        a = await client.get(f"/incidents/{incident_id}/accounts")
        accounts = a.get("items", a) if isinstance(a, dict) else a
    except SheetStormAPIError:
        pass

    parts = [
        "You are a threat hunting expert. Analyze the following incident data for "
        "evidence of **lateral movement**.\n\n"
        "Provide:\n"
        "1. **Confirmed Lateral Movement** — clear evidence with source/destination hosts\n"
        "2. **Suspected Lateral Movement** — indicators that suggest but don't confirm movement\n"
        "3. **Movement Map** — describe the path through the network (host A → host B → host C)\n"
        "4. **Techniques Used** — ATT&CK lateral movement techniques (T1021.*, T1570, etc.)\n"
        "5. **Compromised Credentials** — accounts used for movement\n"
        "6. **Recommendations** — how to contain and prevent further movement\n",
        f"---\n\n# Incident: {incident.get('title', 'Unknown')}\n",
    ]

    if hosts:
        parts.append(f"## Compromised Hosts ({len(hosts)})")
        for h in hosts:
            parts.append(
                f"- {h.get('hostname', '?')} ({h.get('ip_address', '?')}) — "
                f"Type: {h.get('compromise_type', '?')} | "
                f"Method: {h.get('access_method', 'N/A')}"
            )

    if accounts:
        parts.append(f"\n## Compromised Accounts ({len(accounts)})")
        for a in accounts:
            parts.append(
                f"- {a.get('account_name', '?')} ({a.get('account_type', '?')}) — "
                f"Compromise: {a.get('compromise_type', '?')}"
            )

    if events:
        parts.append(f"\n## Timeline Events ({len(events)} total)")
        for e in events[:50]:
            parts.append(
                f"- [{e.get('event_timestamp', '?')}] [{e.get('event_type', '?')}] "
                f"{e.get('description', '?')}"
            )
            if e.get("host_name"):
                parts[-1] += f" (host: {e['host_name']})"

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Draft Executive Summary
# ---------------------------------------------------------------------------

@mcp.prompt()
async def draft_executive_summary(incident_id: str) -> str:
    """Draft an executive summary for an incident suitable for management/stakeholders.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        incident = await client.get(f"/incidents/{incident_id}")
    except SheetStormAPIError as exc:
        return f"Could not fetch incident data: {exc}"

    hosts = []
    accounts = []
    ioc_count = 0
    try:
        h = await client.get(f"/incidents/{incident_id}/hosts")
        hosts = h.get("items", h) if isinstance(h, dict) else h
    except SheetStormAPIError:
        pass
    try:
        a = await client.get(f"/incidents/{incident_id}/accounts")
        accounts = a.get("items", a) if isinstance(a, dict) else a
    except SheetStormAPIError:
        pass
    for ep in ["/iocs/network", "/iocs/host", "/iocs/malware"]:
        try:
            data = await client.get(f"/incidents/{incident_id}{ep}")
            items = data.get("items", data) if isinstance(data, dict) else data
            ioc_count += len(items)
        except SheetStormAPIError:
            pass

    parts = [
        "You are a senior incident response manager writing an executive summary for "
        "C-level stakeholders and legal/compliance teams.\n\n"
        "Write a **concise, non-technical executive summary** that covers:\n"
        "1. **What Happened** — 2-3 sentence overview\n"
        "2. **Business Impact** — affected systems, data, users, operations\n"
        "3. **Response Status** — current phase, key actions taken\n"
        "4. **Risk Assessment** — ongoing risks and exposure\n"
        "5. **Recommended Actions** — business decisions needed\n"
        "6. **Timeline** — key dates (detection, containment, expected resolution)\n\n"
        "Keep the language clear and jargon-free. Use bullet points. "
        "Maximum 1 page.\n",
        f"---\n\n# Incident Data\n",
        f"**Title**: {incident.get('title', 'Unknown')}",
        f"**Severity**: {incident.get('severity')} | **Status**: {incident.get('status')} | "
        f"**Phase**: {incident.get('phase')}",
        f"**Classification**: {incident.get('classification', 'N/A')}",
        f"**Created**: {incident.get('created_at')}",
    ]

    if incident.get("description"):
        parts.append(f"**Technical Description**: {incident['description']}")
    if incident.get("executive_summary"):
        parts.append(f"**Existing Summary**: {incident['executive_summary']}")

    parts.append(f"\n**Scope**: {len(hosts)} compromised hosts, {len(accounts)} compromised accounts, "
                 f"{ioc_count} IOCs identified")

    phase_dates = []
    for field, label in [
        ("detected_at", "Detected"),
        ("contained_at", "Contained"),
        ("eradicated_at", "Eradicated"),
        ("recovered_at", "Recovered"),
        ("closed_at", "Closed"),
    ]:
        if incident.get(field):
            phase_dates.append(f"  {label}: {incident[field]}")
    if phase_dates:
        parts.append("\n**Key Dates**:")
        parts.extend(phase_dates)

    return "\n".join(parts)
