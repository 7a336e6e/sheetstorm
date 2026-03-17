"""MCP Prompt templates — pre-built analytical prompts for incident response.

These prompts help LLMs perform structured IR analysis by providing
domain-specific context and formatting guidance.
"""

from __future__ import annotations

from sheetstorm_mcp.server import mcp, get_client
from sheetstorm_mcp.client import SheetStormAPIError


def _format_mitre_label(e: dict, prefix: str = "", existing_prefix: str = "") -> str:
    """Build a MITRE label string from an event's mitre_mappings or legacy fields."""
    mappings = e.get("mitre_mappings") or []
    if mappings:
        labels = []
        for m in mappings:
            labels.append(f"{m.get('tactic', '?')}/{m.get('technique', '?')}")
        pfx = existing_prefix or prefix
        return f" {pfx}[{', '.join(labels)}]" if labels else ""
    if e.get("mitre_tactic"):
        pfx = existing_prefix or prefix
        return f" {pfx}[{e['mitre_tactic']}/{e.get('mitre_technique', '?')}]"
    return ""


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
        (f"/incidents/{incident_id}/network-iocs", "network"),
        (f"/incidents/{incident_id}/host-iocs", "host"),
        (f"/incidents/{incident_id}/malware", "malware"),
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
            mitre = _format_mitre_label(e)
            parts.append(f"- [{e.get('timestamp', '?')}] {e.get('activity', '?')}{mitre}")

    # IOCs
    total_iocs = len(network_iocs) + len(host_iocs) + len(malware_iocs)
    if total_iocs:
        parts.append(f"\n## IOCs ({total_iocs} total)")
        if network_iocs:
            parts.append("### Network Indicators")
            for i in network_iocs[:30]:
                parts.append(f"- {i.get('dns_ip', '?')} | {i.get('protocol', '?')}:{i.get('port', '?')} — {i.get('description', '')}")
        if host_iocs:
            parts.append("### Host-Based Indicators")
            for i in host_iocs[:30]:
                parts.append(f"- [{i.get('artifact_type', '?')}] {i.get('artifact_value', '?')} — {i.get('notes', '')}")
        if malware_iocs:
            parts.append("### Malware/Tools")
            for m in malware_iocs[:20]:
                parts.append(f"- {m.get('file_name', '?')} ({m.get('malware_family', '?')}) — {m.get('description', '')}")

    # Assets
    if hosts or accounts:
        parts.append(f"\n## Compromised Assets ({len(hosts)} hosts, {len(accounts)} accounts)")
        for h in hosts[:30]:
            parts.append(f"- Host: {h.get('hostname', '?')} ({h.get('ip_address', '?')}) — Status: {h.get('containment_status', '?')}")
        for a in accounts[:30]:
            parts.append(f"- Account: {a.get('account_name', '?')} ({a.get('account_type', '?')}) — Status: {a.get('status', '?')}")

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
            mitre = _format_mitre_label(e, prefix="| MITRE: ")
            parts.append(
                f"- **{e.get('timestamp', '?')}** "
                f"{e.get('activity', '?')}{mitre}"
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
        (f"/incidents/{incident_id}/network-iocs", "network"),
        (f"/incidents/{incident_id}/host-iocs", "host"),
        (f"/incidents/{incident_id}/malware", "malware"),
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
            existing = _format_mitre_label(e, existing_prefix="EXISTING: ")
            parts.append(f"- {e.get('activity', '?')}{existing}")

    for label, items in ioc_data.items():
        if items:
            parts.append(f"\n## {label.title()} IOCs")
            for i in items[:20]:
                if label == "network":
                    parts.append(f"- {i.get('dns_ip', '?')} ({i.get('protocol', '?')}:{i.get('port', '?')})")
                elif label == "host":
                    parts.append(f"- [{i.get('artifact_type', '?')}] {i.get('artifact_value', '?')}")
                else:
                    parts.append(f"- {i.get('file_name', '?')} ({i.get('malware_family', '?')})")

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
                f"OS: {h.get('os_version', '?')} | "
                f"Status: {h.get('containment_status', 'N/A')}"
            )

    if accounts:
        parts.append(f"\n## Compromised Accounts ({len(accounts)})")
        for a in accounts:
            parts.append(
                f"- {a.get('account_name', '?')} ({a.get('account_type', '?')}) — "
                f"Status: {a.get('status', '?')}"
            )

    if events:
        parts.append(f"\n## Timeline Events ({len(events)} total)")
        for e in events[:50]:
            parts.append(
                f"- [{e.get('timestamp', '?')}] "
                f"{e.get('activity', '?')}"
            )
            if e.get("hostname"):
                parts[-1] += f" (host: {e['hostname']})"

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
    for ep in ["/network-iocs", "/host-iocs", "/malware"]:
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


# ---------------------------------------------------------------------------
# Full IR Report (Phase 4)
# ---------------------------------------------------------------------------

@mcp.prompt()
async def full_ir_report(incident_id: str) -> str:
    """Generate a comprehensive incident response report with all evidence, analysis, and recommendations.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        incident = await client.get(f"/incidents/{incident_id}")
    except SheetStormAPIError as exc:
        return f"Could not fetch incident data: {exc}"

    # Gather everything
    data_sections = {}
    endpoints = {
        'timeline': f"/incidents/{incident_id}/timeline",
        'hosts': f"/incidents/{incident_id}/hosts",
        'accounts': f"/incidents/{incident_id}/accounts",
        'network_iocs': f"/incidents/{incident_id}/network-iocs",
        'host_iocs': f"/incidents/{incident_id}/host-iocs",
        'malware': f"/incidents/{incident_id}/malware",
        'tasks': f"/incidents/{incident_id}/tasks",
        'notes': f"/incidents/{incident_id}/notes",
        'artifacts': f"/incidents/{incident_id}/artifacts",
    }

    for key, endpoint in endpoints.items():
        try:
            resp = await client.get(endpoint)
            data_sections[key] = resp.get("items", resp) if isinstance(resp, dict) else resp
        except SheetStormAPIError:
            data_sections[key] = []

    timeline = data_sections.get('timeline', [])
    hosts = data_sections.get('hosts', [])
    accounts = data_sections.get('accounts', [])
    network_iocs = data_sections.get('network_iocs', [])
    host_iocs = data_sections.get('host_iocs', [])
    malware = data_sections.get('malware', [])
    tasks = data_sections.get('tasks', [])
    notes = data_sections.get('notes', [])
    artifacts = data_sections.get('artifacts', [])

    parts = [
        "You are an expert incident response analyst. Using ALL the evidence below, write a "
        "**comprehensive IR report** suitable for legal, compliance, insurance, and management audiences.\n\n"
        "## Required Sections:\n"
        "1. **Executive Summary** (1 paragraph, non-technical)\n"
        "2. **Incident Classification** (type, severity, scope, regulatory impact)\n"
        "3. **Timeline of Events** (narrative, chronological, with MITRE ATT&CK mapping)\n"
        "4. **Attack Vector & Root Cause** (how the attacker gained initial access)\n"
        "5. **Indicators of Compromise** (tables of IPs, domains, hashes, artifacts)\n"
        "6. **Affected Systems & Accounts** (inventory with impact assessment)\n"
        "7. **Malware Analysis** (samples found, capabilities, attribution)\n"
        "8. **Containment & Eradication Actions** (what was done)\n"
        "9. **Evidence Preservation** (chain of custody, artifacts collected)\n"
        "10. **Impact Assessment** (data exposure, operational impact, business loss)\n"
        "11. **Recommendations** (immediate, short-term, long-term)\n"
        "12. **Appendices** (IOC tables, affected host list, reference links)\n\n"
        "Use professional formatting with headers, tables, and bullet points.\n",
        f"---\n\n# INCIDENT DATA\n",
        f"**Title**: {incident.get('title', 'Unknown')}",
        f"**ID**: {incident.get('id')}",
        f"**Status**: {incident.get('status')} | **Phase**: {incident.get('phase_name', incident.get('phase'))} | "
        f"**Severity**: {incident.get('severity')}",
        f"**Classification**: {incident.get('classification', 'N/A')}",
        f"**Created**: {incident.get('created_at')} | **Updated**: {incident.get('updated_at')}",
    ]

    if incident.get("description"):
        parts.append(f"\n**Description**:\n{incident['description']}")
    if incident.get("executive_summary"):
        parts.append(f"\n**Executive Summary (existing)**:\n{incident['executive_summary']}")
    if incident.get("lessons_learned"):
        parts.append(f"\n**Lessons Learned (existing)**:\n{incident['lessons_learned']}")

    # Phase dates
    for field, label in [("detected_at", "Detected"), ("contained_at", "Contained"),
                         ("eradicated_at", "Eradicated"), ("recovered_at", "Recovered"), ("closed_at", "Closed")]:
        if incident.get(field):
            parts.append(f"**{label}**: {incident[field]}")

    # Timeline
    if timeline:
        parts.append(f"\n## Timeline ({len(timeline)} events)")
        for e in timeline[:80]:
            mitre = _format_mitre_label(e)
            src = f" (source: {e['source']})" if e.get('source') else ""
            host = f" @{e['hostname']}" if e.get('hostname') else ""
            parts.append(f"- [{e.get('timestamp', '?')}]{host} {e.get('activity', '?')}{mitre}{src}")

    # IOCs
    total_iocs = len(network_iocs) + len(host_iocs) + len(malware)
    if total_iocs:
        parts.append(f"\n## Indicators of Compromise ({total_iocs} total)")
        if network_iocs:
            parts.append("### Network Indicators")
            for i in network_iocs:
                parts.append(f"- {i.get('dns_ip')} | {i.get('protocol', '?')}:{i.get('port', '?')} | "
                             f"Direction: {i.get('direction', '?')} | Malicious: {i.get('is_malicious', '?')} | {i.get('description', '')}")
        if host_iocs:
            parts.append("### Host-Based Indicators")
            for i in host_iocs:
                parts.append(f"- [{i.get('artifact_type')}] {i.get('artifact_value')} | Host: {i.get('host', '?')} | "
                             f"Malicious: {i.get('is_malicious', '?')} | {i.get('notes', '')}")
        if malware:
            parts.append("### Malware & Tools")
            for m in malware:
                hashes = f"MD5:{m.get('md5', 'N/A')} SHA256:{m.get('sha256', 'N/A')}"
                parts.append(f"- {m.get('file_name')} | Path: {m.get('file_path', '?')} | Family: {m.get('malware_family', '?')} | {hashes}")

    # Hosts
    if hosts:
        parts.append(f"\n## Compromised Hosts ({len(hosts)})")
        for h in hosts:
            parts.append(f"- {h.get('hostname')} ({h.get('ip_address', '?')}) | OS: {h.get('os_version', '?')} | "
                         f"Type: {h.get('system_type', '?')} | Containment: {h.get('containment_status', '?')}")

    # Accounts
    if accounts:
        parts.append(f"\n## Compromised Accounts ({len(accounts)})")
        for a in accounts:
            parts.append(f"- {a.get('domain', '')}\\{a.get('account_name')} | Type: {a.get('account_type', '?')} | "
                         f"Status: {a.get('status', '?')} | Privilege: {a.get('privilege_level', '?')}")

    # Tasks
    if tasks:
        parts.append(f"\n## Response Tasks ({len(tasks)})")
        for t in tasks:
            parts.append(f"- [{t.get('status', '?')}] {t.get('title')} (Priority: {t.get('priority', '?')})")

    # Artifacts
    if artifacts:
        parts.append(f"\n## Collected Artifacts ({len(artifacts)})")
        for a in artifacts:
            parts.append(f"- {a.get('filename', '?')} | Type: {a.get('artifact_type', '?')} | "
                         f"Hash: {a.get('sha256_hash', 'N/A')}")

    # Notes
    if notes:
        parts.append(f"\n## Case Notes ({len(notes)})")
        for n in notes:
            parts.append(f"- **{n.get('title')}** ({n.get('category', '?')}): {(n.get('content', '') or '')[:200]}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Lessons Learned (Phase 4)
# ---------------------------------------------------------------------------

@mcp.prompt()
async def lessons_learned(incident_id: str) -> str:
    """Generate a lessons learned analysis for a closed or near-closed incident.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        incident = await client.get(f"/incidents/{incident_id}")
    except SheetStormAPIError as exc:
        return f"Could not fetch incident data: {exc}"

    timeline = []
    tasks = []
    notes = []
    try:
        tl = await client.get(f"/incidents/{incident_id}/timeline")
        timeline = tl.get("items", tl) if isinstance(tl, dict) else tl
    except SheetStormAPIError:
        pass
    try:
        t = await client.get(f"/incidents/{incident_id}/tasks")
        tasks = t.get("items", t) if isinstance(t, dict) else t
    except SheetStormAPIError:
        pass
    try:
        n = await client.get(f"/incidents/{incident_id}/notes")
        notes = n.get("items", n) if isinstance(n, dict) else n
    except SheetStormAPIError:
        pass

    parts = [
        "You are a senior incident response manager conducting a **Lessons Learned / Post-Incident Review** "
        "(NIST SP 800-61 Phase 6).\n\n"
        "## Analyze and produce:\n"
        "1. **Incident Summary** — brief recap (what, when, how, impact)\n"
        "2. **What Went Well** — effective detection, response, communication\n"
        "3. **What Could Be Improved** — gaps, delays, miscommunication, tool limitations\n"
        "4. **Root Cause Analysis** — primary cause + contributing factors (use 5 Whys method)\n"
        "5. **Detection Gap Analysis** — how was it found, could it have been caught earlier?\n"
        "6. **Response Timeline Analysis** — time from detection to containment to resolution\n"
        "7. **Process Improvements** — specific changes to playbooks, tools, training\n"
        "8. **Technical Improvements** — detection rules, hardening, monitoring gaps\n"
        "9. **Action Items** — SMART goals with owners and deadlines\n"
        "10. **Metrics** — MTTD, MTTC, MTTR, total IOCs, affected systems\n\n",
        f"---\n\n# Incident: {incident.get('title', 'Unknown')}",
        f"**Severity**: {incident.get('severity')} | **Status**: {incident.get('status')} | "
        f"**Phase**: {incident.get('phase_name', incident.get('phase'))}",
        f"**Classification**: {incident.get('classification', 'N/A')}",
    ]

    # Calculate response metrics
    for field, label in [("created_at", "Created"), ("detected_at", "Detected"),
                         ("contained_at", "Contained"), ("eradicated_at", "Eradicated"),
                         ("recovered_at", "Recovered"), ("closed_at", "Closed")]:
        if incident.get(field):
            parts.append(f"**{label}**: {incident[field]}")

    if incident.get("lessons_learned"):
        parts.append(f"\n**Existing Lessons Learned notes**:\n{incident['lessons_learned']}")

    if timeline:
        parts.append(f"\n## Timeline ({len(timeline)} events)")
        for e in timeline[:60]:
            parts.append(f"- [{e.get('timestamp', '?')}] {e.get('activity', '?')}")

    if tasks:
        completed = sum(1 for t in tasks if t.get('status') == 'completed')
        parts.append(f"\n## Tasks ({completed}/{len(tasks)} completed)")
        for t in tasks:
            parts.append(f"- [{t.get('status')}] {t.get('title')} — {t.get('priority', '?')}")

    if notes:
        parts.append(f"\n## Case Notes")
        for n in notes:
            parts.append(f"- {n.get('title')}: {(n.get('content', '') or '')[:200]}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Containment Checklist (Phase 4)
# ---------------------------------------------------------------------------

@mcp.prompt()
async def containment_checklist(incident_id: str) -> str:
    """Generate a containment checklist based on incident IOCs, hosts, and scope.

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
    network_iocs = []
    host_iocs = []
    malware = []
    for endpoint, key in [
        (f"/incidents/{incident_id}/hosts", "hosts"),
        (f"/incidents/{incident_id}/accounts", "accounts"),
        (f"/incidents/{incident_id}/network-iocs", "network"),
        (f"/incidents/{incident_id}/host-iocs", "host"),
        (f"/incidents/{incident_id}/malware", "malware"),
    ]:
        try:
            data = await client.get(endpoint)
            items = data.get("items", data) if isinstance(data, dict) else data
            if key == "hosts":
                hosts = items
            elif key == "accounts":
                accounts = items
            elif key == "network":
                network_iocs = items
            elif key == "host":
                host_iocs = items
            elif key == "malware":
                malware = items
        except SheetStormAPIError:
            pass

    parts = [
        "You are an incident response containment specialist. Based on the compromised assets and IOCs below, "
        "generate a **prioritized containment checklist**.\n\n"
        "## Checklist Requirements:\n"
        "1. **Immediate Actions** (within 1 hour) — isolate critical systems, block known-bad IPs/domains\n"
        "2. **Short-term Actions** (within 24 hours) — credential resets, EDR sweeps, firewall rules\n"
        "3. **Network Containment** — specific IPs/domains to block with firewall rules\n"
        "4. **Host Containment** — specific hosts to isolate, processes to kill, files to quarantine\n"
        "5. **Account Containment** — accounts to disable/reset, MFA enforcement\n"
        "6. **Detection Rules** — SIEM/EDR rules to deploy for monitoring\n"
        "7. **Communication Steps** — who to notify, escalation path\n"
        "8. **Verification Steps** — how to confirm containment is effective\n\n"
        "Format each item as a checkbox: `[ ] Action — Justification`\n",
        f"---\n\n# Incident: {incident.get('title', 'Unknown')}",
        f"**Severity**: {incident.get('severity')} | **Classification**: {incident.get('classification', 'N/A')}",
        f"**Current Phase**: {incident.get('phase_name', incident.get('phase'))}\n",
    ]

    if hosts:
        parts.append(f"## Compromised Hosts ({len(hosts)})")
        for h in hosts:
            parts.append(f"- {h.get('hostname')} ({h.get('ip_address', '?')}) — "
                         f"OS: {h.get('os_version', '?')} | Type: {h.get('system_type', '?')} | "
                         f"Containment: {h.get('containment_status', 'unknown')}")

    if accounts:
        parts.append(f"\n## Compromised Accounts ({len(accounts)})")
        for a in accounts:
            parts.append(f"- {a.get('domain', '')}\\{a.get('account_name')} — "
                         f"Type: {a.get('account_type', '?')} | Privilege: {a.get('privilege_level', '?')}")

    if network_iocs:
        parts.append(f"\n## Network IOCs to Block ({len(network_iocs)})")
        for i in network_iocs:
            parts.append(f"- {i.get('dns_ip')} | {i.get('protocol', '?')}:{i.get('port', '?')} | {i.get('direction', '?')}")

    if host_iocs:
        parts.append(f"\n## Host Artifacts to Remediate ({len(host_iocs)})")
        for i in host_iocs:
            parts.append(f"- [{i.get('artifact_type')}] {i.get('artifact_value')}")

    if malware:
        parts.append(f"\n## Malware to Quarantine ({len(malware)})")
        for m in malware:
            parts.append(f"- {m.get('file_name')} | Path: {m.get('file_path', '?')} | "
                         f"MD5: {m.get('md5', 'N/A')} | Family: {m.get('malware_family', '?')}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# IOC Summary (Phase 4)
# ---------------------------------------------------------------------------

@mcp.prompt()
async def ioc_summary(incident_id: str) -> str:
    """Generate a structured IOC summary for threat intelligence sharing.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        incident = await client.get(f"/incidents/{incident_id}")
    except SheetStormAPIError as exc:
        return f"Could not fetch incident data: {exc}"

    network_iocs = []
    host_iocs = []
    malware = []
    for endpoint, key in [
        (f"/incidents/{incident_id}/network-iocs", "network"),
        (f"/incidents/{incident_id}/host-iocs", "host"),
        (f"/incidents/{incident_id}/malware", "malware"),
    ]:
        try:
            data = await client.get(endpoint)
            items = data.get("items", data) if isinstance(data, dict) else data
            if key == "network":
                network_iocs = items
            elif key == "host":
                host_iocs = items
            elif key == "malware":
                malware = items
        except SheetStormAPIError:
            pass

    total = len(network_iocs) + len(host_iocs) + len(malware)

    parts = [
        "You are a threat intelligence analyst. Using the IOCs below, produce a "
        "**structured IOC summary** suitable for sharing with ISACs, CERTs, or partner organizations.\n\n"
        "## Required Output:\n"
        "1. **IOC Overview** — total count by type, confidence assessment\n"
        "2. **Network Indicators Table** — IP, domain, port, protocol, direction, first seen, malicious confidence\n"
        "3. **File Indicators Table** — filename, path, MD5, SHA256, type, malware family\n"
        "4. **Host Artifacts Table** — artifact type, value, host, remediation status\n"
        "5. **TTPs Observed** — MITRE ATT&CK techniques associated with the IOCs\n"
        "6. **Attribution Assessment** — if possible, suspected threat actor/campaign\n"
        "7. **STIX/OpenIOC Patterns** — generate detection patterns for each key IOC\n"
        "8. **Sharing Recommendations** — TLP marking, distribution scope\n\n"
        "Use tables for structured data. Include confidence levels (High/Medium/Low).\n",
        f"---\n\n# Incident: {incident.get('title', 'Unknown')}",
        f"**Classification**: {incident.get('classification', 'N/A')} | **Severity**: {incident.get('severity')}",
        f"**Total IOCs**: {total}\n",
    ]

    if network_iocs:
        parts.append(f"## Network IOCs ({len(network_iocs)})")
        for i in network_iocs:
            parts.append(f"- {i.get('dns_ip')} | Protocol: {i.get('protocol', '?')} | Port: {i.get('port', '?')} | "
                         f"Direction: {i.get('direction', '?')} | Malicious: {i.get('is_malicious', '?')} | "
                         f"Source: {i.get('threat_intel_source', 'N/A')} | {i.get('description', '')}")

    if host_iocs:
        parts.append(f"\n## Host IOCs ({len(host_iocs)})")
        for i in host_iocs:
            parts.append(f"- [{i.get('artifact_type')}] {i.get('artifact_value')} | Host: {i.get('host', '?')} | "
                         f"Malicious: {i.get('is_malicious', '?')} | Remediated: {i.get('remediated', '?')} | "
                         f"{i.get('notes', '')}")

    if malware:
        parts.append(f"\n## Malware/Tools ({len(malware)})")
        for m in malware:
            parts.append(f"- **{m.get('file_name')}** | Path: {m.get('file_path', '?')} | "
                         f"Family: {m.get('malware_family', '?')} | Actor: {m.get('threat_actor', '?')}\n"
                         f"  MD5: {m.get('md5', 'N/A')} | SHA256: {m.get('sha256', 'N/A')} | "
                         f"Size: {m.get('file_size', '?')} bytes")

    return "\n".join(parts)
