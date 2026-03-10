"""MCP prompts — structured prompt templates for incident response analysis."""

from __future__ import annotations

from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import mcp, get_client


# ---------------------------------------------------------------------------
# Helper: fetch incident + related data
# ---------------------------------------------------------------------------

async def _fetch_incident_context(incident_id: str) -> dict:
    """Fetch incident with all related entities for prompt context."""
    client = get_client()
    ctx: dict = {"incident": None, "timeline": [], "hosts": [], "tasks": [],
                 "network_iocs": [], "host_iocs": [], "malware": [],
                 "notes": [], "artifacts": [], "graph": None}
    try:
        ctx["incident"] = await client.get(f"/incidents/{incident_id}")
    except SheetStormAPIError:
        pass
    # Fetch related data in parallel-ish (sequential for simplicity)
    for key, path in [
        ("timeline", f"/incidents/{incident_id}/timeline"),
        ("hosts", f"/incidents/{incident_id}/hosts"),
        ("tasks", f"/incidents/{incident_id}/tasks"),
        ("network_iocs", f"/incidents/{incident_id}/network-iocs"),
        ("host_iocs", f"/incidents/{incident_id}/host-iocs"),
        ("malware", f"/incidents/{incident_id}/malware"),
        ("notes", f"/incidents/{incident_id}/notes"),
        ("artifacts", f"/incidents/{incident_id}/artifacts"),
    ]:
        try:
            data = await client.get(path)
            items = data if isinstance(data, list) else data.get("items", [])
            ctx[key] = items
        except SheetStormAPIError:
            pass
    try:
        ctx["graph"] = await client.get(f"/incidents/{incident_id}/attack-graph")
    except SheetStormAPIError:
        pass
    return ctx


def _format_incident_summary(ctx: dict) -> str:
    """Format incident data into a text block for prompt context."""
    inc = ctx.get("incident", {}) or {}
    parts = []

    parts.append("## Incident Overview")
    parts.append(f"- **Title**: {inc.get('title', 'N/A')}")
    parts.append(f"- **ID**: {inc.get('id', 'N/A')}")
    parts.append(f"- **Severity**: {inc.get('severity', 'N/A')}")
    parts.append(f"- **Status**: {inc.get('status', 'N/A')}")
    parts.append(f"- **Phase**: {inc.get('phase', 'N/A')}")
    parts.append(f"- **Type**: {inc.get('incident_type', inc.get('type', 'N/A'))}")
    parts.append(f"- **Created**: {inc.get('created_at', 'N/A')}")
    if inc.get("description"):
        parts.append(f"\n**Description**: {inc['description']}")
    if inc.get("impact"):
        parts.append(f"**Impact**: {inc['impact']}")

    # Timeline
    timeline = ctx.get("timeline", [])
    if timeline:
        parts.append(f"\n## Timeline ({len(timeline)} events)")
        for e in timeline[:20]:
            parts.append(
                f"- [{e.get('event_time', e.get('timestamp', 'N/A'))}] "
                f"{e.get('title', e.get('description', 'N/A'))}"
            )
        if len(timeline) > 20:
            parts.append(f"  ... and {len(timeline) - 20} more events")

    # Hosts
    hosts = ctx.get("hosts", [])
    if hosts:
        parts.append(f"\n## Compromised Hosts ({len(hosts)})")
        for h in hosts:
            parts.append(
                f"- **{h.get('hostname', 'N/A')}** ({h.get('ip_address', 'N/A')}) "
                f"— {h.get('containment_status', 'N/A')}"
            )

    # Network IOCs
    net_iocs = ctx.get("network_iocs", [])
    if net_iocs:
        parts.append(f"\n## Network IOCs ({len(net_iocs)})")
        for i in net_iocs:
            parts.append(
                f"- {i.get('dns_ip', 'N/A')} "
                f"({i.get('protocol', '?')}:{i.get('port', '?')}) "
                f"{'[MALICIOUS]' if i.get('is_malicious') else ''}"
            )

    # Host IOCs
    host_iocs = ctx.get("host_iocs", [])
    if host_iocs:
        parts.append(f"\n## Host-Based IOCs ({len(host_iocs)})")
        for i in host_iocs:
            parts.append(
                f"- [{i.get('artifact_type', '?')}] {i.get('artifact_value', 'N/A')} "
                f"{'[MALICIOUS]' if i.get('is_malicious') else ''}"
            )

    # Malware
    malware = ctx.get("malware", [])
    if malware:
        parts.append(f"\n## Malware & Tools ({len(malware)})")
        for m in malware:
            parts.append(
                f"- **{m.get('file_name', 'N/A')}** "
                f"(SHA256: {m.get('sha256', 'N/A')[:16]}...)"
            )

    # Tasks
    tasks = ctx.get("tasks", [])
    if tasks:
        parts.append(f"\n## Tasks ({len(tasks)})")
        for t in tasks:
            status = t.get("status", "?")
            parts.append(f"- [{status}] {t.get('title', 'N/A')}")

    # Attack graph
    graph = ctx.get("graph")
    if graph:
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        if nodes or edges:
            parts.append(f"\n## Attack Graph ({len(nodes)} nodes, {len(edges)} edges)")
            for n in nodes[:15]:
                parts.append(f"- Node: {n.get('label', 'N/A')} ({n.get('node_type', '?')})")
            for e in edges[:15]:
                parts.append(
                    f"- Edge: {e.get('source_node_id', '?')[:8]}... "
                    f"→ {e.get('target_node_id', '?')[:8]}... "
                    f"({e.get('edge_type', '?')})"
                )

    # Notes
    notes = ctx.get("notes", [])
    if notes:
        parts.append(f"\n## Case Notes ({len(notes)})")
        for n in notes[:10]:
            parts.append(f"- [{n.get('category', 'general')}] {n.get('title', 'N/A')}")

    # Artifacts
    artifacts = ctx.get("artifacts", [])
    if artifacts:
        parts.append(f"\n## Artifacts ({len(artifacts)})")
        for a in artifacts:
            parts.append(
                f"- {a.get('original_filename', a.get('filename', 'N/A'))} "
                f"({a.get('file_size', '?')} bytes)"
            )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@mcp.prompt()
async def analyze_incident(incident_id: str) -> str:
    """Comprehensive incident analysis prompt. Fetches all incident data and asks for a thorough analysis."""
    ctx = await _fetch_incident_context(incident_id)
    summary = _format_incident_summary(ctx)
    return f"""You are an expert incident responder performing a comprehensive analysis of a security incident.

{summary}

Please provide a thorough analysis covering:

1. **Incident Summary** — What happened, when, and what is the current state?
2. **Attack Vector Analysis** — How did the attacker gain initial access?
3. **Scope Assessment** — What systems, data, and users are affected?
4. **IOC Analysis** — What indicators of compromise are present and what do they tell us?
5. **Threat Actor Assessment** — What can we infer about the attacker's capabilities and motivations?
6. **MITRE ATT&CK Mapping** — Map observed techniques to the ATT&CK framework.
7. **Risk Assessment** — What is the current risk level and potential for further damage?
8. **Recommended Actions** — Prioritized list of immediate and follow-up actions.
9. **Gaps & Questions** — What information is missing and what questions should be investigated?
"""


@mcp.prompt()
async def generate_timeline_summary(incident_id: str) -> str:
    """Generate a narrative timeline summary from incident events."""
    ctx = await _fetch_incident_context(incident_id)
    summary = _format_incident_summary(ctx)
    return f"""You are an incident response analyst creating a detailed timeline narrative.

{summary}

Please create a chronological narrative that:

1. **Describes each phase** of the attack in plain language.
2. **Highlights critical events** that represent escalation points.
3. **Identifies time gaps** where the attacker may have been active but undetected.
4. **Correlates events** across different data sources (network, host, logs).
5. **Estimates dwell time** — how long was the attacker in the environment?
6. **Notes any anomalies** in the timeline that warrant further investigation.

Format as a clear, chronological narrative suitable for an incident report.
"""


@mcp.prompt()
async def suggest_mitre_mapping(incident_id: str) -> str:
    """Suggest MITRE ATT&CK technique mappings for observed activity."""
    ctx = await _fetch_incident_context(incident_id)
    summary = _format_incident_summary(ctx)
    return f"""You are a threat intelligence analyst mapping observed incident activity to the MITRE ATT&CK framework.

{summary}

For each observed activity or indicator, suggest the most appropriate MITRE ATT&CK technique mapping:

1. **List each technique** with its ID (e.g., T1059.001) and name.
2. **Explain the evidence** — which data points support each mapping?
3. **Assess confidence** — High/Medium/Low for each mapping.
4. **Identify the tactic** each technique falls under.
5. **Note sub-techniques** where applicable.
6. **Suggest additional techniques** that the attacker likely used but we haven't detected evidence of yet.
7. **Recommend detection rules** or queries for unconfirmed techniques.

Format as a structured table or list suitable for documentation.
"""


@mcp.prompt()
async def identify_lateral_movement(incident_id: str) -> str:
    """Analyze incident data for signs of lateral movement."""
    ctx = await _fetch_incident_context(incident_id)
    summary = _format_incident_summary(ctx)
    return f"""You are a senior incident responder analyzing the incident for lateral movement.

{summary}

Analyze the data for evidence of lateral movement:

1. **Identify movement paths** — Which hosts were accessed from which hosts?
2. **Methods used** — What protocols or tools were used for lateral movement (RDP, SMB, WMI, PsExec, etc.)?
3. **Credential usage** — Were compromised credentials used? Which accounts?
4. **Timeline of movement** — When did each lateral movement event occur?
5. **Pivot points** — Which hosts served as pivot points for further movement?
6. **Scope assessment** — Based on the movement patterns, what is the likely full scope of compromise?
7. **Containment recommendations** — Which network segments or hosts should be isolated?
8. **Detection gaps** — Where might lateral movement have occurred but not been detected?
"""


@mcp.prompt()
async def draft_executive_summary(
    incident_id: str,
    audience: Optional[str] = None,
) -> str:
    """Draft an executive summary of the incident for leadership."""
    ctx = await _fetch_incident_context(incident_id)
    summary = _format_incident_summary(ctx)
    audience_note = f"\nTarget audience: {audience}" if audience else "\nTarget audience: C-suite executives"
    return f"""You are drafting an executive summary of a security incident for senior leadership.
{audience_note}

{summary}

Write a concise executive summary (1-2 pages) that covers:

1. **What happened** — Plain-language description of the incident.
2. **Business impact** — What systems, data, or operations were affected?
3. **Current status** — Where are we in the response process?
4. **Actions taken** — Key response actions completed so far.
5. **Risk assessment** — Current risk level and exposure.
6. **Next steps** — Planned actions with estimated timelines.
7. **Resource needs** — Any additional resources or budget required.
8. **Lessons learned** (if applicable) — Initial observations on prevention.

Use clear, non-technical language. Avoid jargon. Focus on business impact and decision points.
"""


@mcp.prompt()
async def full_ir_report(incident_id: str) -> str:
    """Generate a comprehensive incident response report."""
    ctx = await _fetch_incident_context(incident_id)
    summary = _format_incident_summary(ctx)
    return f"""You are creating a comprehensive incident response report following NIST SP 800-61 guidelines.

{summary}

Generate a full incident response report with the following sections:

1. **Executive Summary** — Brief overview for leadership.
2. **Incident Details**
   - Incident classification and severity
   - Detection method and initial indicators
   - Timeline of events
3. **Technical Analysis**
   - Attack vector and initial access method
   - Malware analysis (if applicable)
   - IOC summary (network and host-based)
   - MITRE ATT&CK mapping
4. **Scope and Impact**
   - Affected systems and networks
   - Data exposure assessment
   - Business impact
5. **Response Actions**
   - Containment measures
   - Eradication steps
   - Recovery procedures
6. **Root Cause Analysis** — What allowed this to happen?
7. **Recommendations**
   - Immediate actions
   - Short-term improvements (30 days)
   - Long-term strategic changes (90 days)
8. **Lessons Learned**
   - What went well
   - What needs improvement
   - Process changes
9. **Appendices**
   - Full IOC list
   - Detailed timeline
   - Evidence inventory

Format as a professional report suitable for stakeholders and regulatory requirements.
"""


@mcp.prompt()
async def lessons_learned(incident_id: str) -> str:
    """Generate a lessons learned analysis for post-incident review."""
    ctx = await _fetch_incident_context(incident_id)
    summary = _format_incident_summary(ctx)
    return f"""You are facilitating a post-incident lessons learned review.

{summary}

Conduct a thorough lessons learned analysis covering:

1. **Incident Recap** — Brief summary of what happened.
2. **Detection Assessment**
   - How was the incident detected? How could detection be improved?
   - What was the mean time to detect (MTTD)?
3. **Response Assessment**
   - How effective was the response? What was the mean time to respond (MTTR)?
   - Were response procedures followed? Any deviations?
4. **What Went Well** — Positive aspects of the response.
5. **What Needs Improvement** — Areas where the response fell short.
6. **Root Cause Analysis** — Why did this incident occur? Contributing factors?
7. **Gap Analysis**
   - Technology gaps
   - Process gaps
   - People/training gaps
8. **Recommendations** — Prioritized list of improvements with owners and timelines.
9. **Metrics to Track** — KPIs for measuring improvement.
10. **Action Items** — Specific tasks with assignees and due dates.
"""


@mcp.prompt()
async def containment_checklist(incident_id: str) -> str:
    """Generate a containment checklist based on incident specifics."""
    ctx = await _fetch_incident_context(incident_id)
    summary = _format_incident_summary(ctx)
    return f"""You are creating a containment checklist for an active security incident.

{summary}

Generate a prioritized containment checklist:

1. **Immediate Actions** (0-1 hours)
   - Network isolation steps
   - Account lockouts needed
   - Critical system preservation

2. **Short-Term Containment** (1-4 hours)
   - Firewall rules to implement
   - DNS sinkhole entries
   - Endpoint isolation steps

3. **Evidence Preservation**
   - Memory dumps to capture
   - Log files to preserve
   - Disk images to take

4. **Communication Steps**
   - Internal notifications needed
   - External notifications (legal, regulatory, customers)
   - Law enforcement considerations

5. **Monitoring Enhancement**
   - Additional detection rules to deploy
   - Network monitoring changes
   - Endpoint monitoring changes

6. **Verification Steps**
   - How to confirm containment is effective
   - Canary indicators to watch
   - Re-compromise detection

For each item, provide:
- [ ] Specific action description
- Priority: Critical/High/Medium
- Estimated time to complete
- Responsible team/role
"""


@mcp.prompt()
async def ioc_summary(incident_id: str) -> str:
    """Generate a structured IOC summary for threat intelligence sharing."""
    ctx = await _fetch_incident_context(incident_id)
    summary = _format_incident_summary(ctx)
    return f"""You are creating an IOC summary for threat intelligence sharing and defensive deployment.

{summary}

Generate a structured IOC summary that includes:

1. **IOC Overview**
   - Total number and types of IOCs
   - Confidence levels
   - First/last seen dates

2. **Network IOCs**
   - IP addresses (with geolocation and reputation notes)
   - Domains (with registration and hosting info)
   - URLs (with purpose/function)
   - Network signatures

3. **Host-Based IOCs**
   - File hashes (MD5, SHA256) with file descriptions
   - File paths and names
   - Registry keys
   - Process names and command lines
   - Service names
   - Scheduled tasks

4. **Behavioral IOCs**
   - Techniques and procedures observed
   - Communication patterns
   - Timing patterns

5. **Deployment Recommendations**
   - SIEM rules to create
   - EDR detection rules
   - Firewall/proxy blocks
   - Email security rules

6. **STIX/TAXII Format** — IOCs formatted for automated sharing.

7. **False Positive Assessment** — Which IOCs might cause false positives and how to tune.

Categorize each IOC by:
- Confidence: High/Medium/Low
- Actionability: Block/Alert/Monitor
- Scope: Specific to this incident / Campaign-level / Infrastructure-level
"""
