"""Threat intelligence tools — VirusTotal, MISP, CVE, IP/Domain/Email reputation, Ransomware lookups."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


# ---------------------------------------------------------------------------
# VirusTotal
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_virustotal_lookup(
    lookup_type: str,
    value: str,
) -> str:
    """Look up a hash, URL, domain, or IP address on VirusTotal.

    Requires VirusTotal integration to be configured in your organisation.

    Args:
        lookup_type: Type of lookup — one of: hash, url, domain, ip
        value: The IOC value to look up (hash, URL, domain, or IP address)
    """
    client = get_client()
    try:
        data = await client.post(
            "/threat-intel/virustotal/lookup",
            json={"type": lookup_type, "value": value},
        )

        if not data.get("found"):
            return f"Not found in VirusTotal: {value} (type: {lookup_type})"

        parts = [f"**VirusTotal — {lookup_type.upper()} Lookup**: {value}\n"]

        if data.get("detection_ratio"):
            parts.append(f"Detection Ratio: **{data['detection_ratio']}**")
        if data.get("malicious") is not None:
            parts.append(
                f"Malicious: {data['malicious']} | Suspicious: {data.get('suspicious', 0)} | "
                f"Harmless: {data.get('harmless', 0)} | Undetected: {data.get('undetected', 0)}"
            )
        if data.get("file_type"):
            parts.append(f"File Type: {data['file_type']}")
        if data.get("file_name"):
            parts.append(f"File Name: {data['file_name']}")
        if data.get("sha256"):
            parts.append(f"SHA256: {data['sha256']}")
        if data.get("reputation") is not None:
            parts.append(f"Reputation Score: {data['reputation']}")
        if data.get("tags"):
            parts.append(f"Tags: {', '.join(data['tags'])}")
        if data.get("popular_threat_names"):
            parts.append(f"Threat Names: {', '.join(data['popular_threat_names'])}")
        if data.get("country"):
            parts.append(f"Country: {data['country']}")
        if data.get("as_owner"):
            parts.append(f"AS Owner: {data['as_owner']}")

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# MISP
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_misp_push_iocs(
    incident_id: str,
    iocs: list[dict],
    event_info: Optional[str] = None,
) -> str:
    """Push IOCs from an incident to MISP as a new event.

    Requires MISP integration to be configured in your organisation.

    Args:
        incident_id: UUID of the incident the IOCs belong to
        iocs: List of IOC dicts, each with 'type' (MISP attribute type, e.g. ip-dst, md5), 'value', and optional 'comment'
        event_info: Optional MISP event title (defaults to auto-generated)
    """
    client = get_client()
    try:
        payload: dict = {"incident_id": incident_id, "iocs": iocs}
        if event_info:
            payload["event_info"] = event_info

        data = await client.post("/threat-intel/misp/push", json=payload)

        if data.get("success"):
            return (
                f"✓ Pushed {data.get('attributes_pushed', 0)} IOCs to MISP\n"
                f"  Event ID: {data.get('misp_event_id')}\n"
                f"  Event UUID: {data.get('misp_event_uuid')}"
            )
        return f"✗ MISP push failed: {data.get('message', 'unknown error')}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# CVE Lookup
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_cve_lookup(
    cve_id: str,
) -> str:
    """Look up a CVE by ID using NVD and CISA Known Exploited Vulnerabilities catalog.

    No API key required — uses free public endpoints.

    Args:
        cve_id: CVE identifier (e.g. CVE-2024-1234)
    """
    client = get_client()
    try:
        data = await client.post(
            "/threat-intel/cve/lookup",
            json={"cve_id": cve_id},
        )

        if not data.get("found"):
            return f"CVE not found: {cve_id}"

        parts = [f"**{cve_id}**\n"]

        nvd = data.get("nvd")
        if nvd:
            parts.append(f"**Description**: {nvd.get('description', 'N/A')}")
            if nvd.get("cvss_score"):
                parts.append(f"**CVSS**: {nvd['cvss_score']} ({nvd.get('cvss_severity', 'N/A')})")
            if nvd.get("cvss_vector"):
                parts.append(f"**Vector**: {nvd['cvss_vector']}")
            if nvd.get("cwes"):
                parts.append(f"**CWEs**: {', '.join(nvd['cwes'])}")
            parts.append(f"**Published**: {nvd.get('published', 'N/A')}")

        kev = data.get("kev")
        if kev:
            parts.append("\n**⚠ CISA Known Exploited Vulnerability**")
            parts.append(f"  Vendor: {kev.get('vendor')} — {kev.get('product')}")
            parts.append(f"  Name: {kev.get('vulnerability_name')}")
            parts.append(f"  Date Added: {kev.get('date_added')}")
            parts.append(f"  Due Date: {kev.get('due_date')}")
            parts.append(f"  Required Action: {kev.get('required_action')}")
            if kev.get("known_ransomware_use") and kev["known_ransomware_use"] != "Unknown":
                parts.append(f"  Ransomware Use: {kev['known_ransomware_use']}")

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# IP Reputation
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_ip_reputation(
    ip: str,
) -> str:
    """Look up IP reputation using AbuseIPDB, VirusTotal, and free geo data.

    AbuseIPDB and VirusTotal require integrations; geo lookup is always available.

    Args:
        ip: IP address to look up
    """
    client = get_client()
    try:
        data = await client.post("/threat-intel/ip/lookup", json={"ip": ip})

        parts = [f"**IP Reputation**: {data.get('ip', ip)}\n"]
        sources = data.get("sources", {})

        abuse = sources.get("abuseipdb")
        if abuse:
            parts.append("**AbuseIPDB**:")
            parts.append(f"  Confidence Score: {abuse.get('abuse_confidence_score')}%")
            parts.append(f"  Total Reports: {abuse.get('total_reports')}")
            parts.append(f"  ISP: {abuse.get('isp')}")
            if abuse.get("is_tor"):
                parts.append("  ⚠ Tor Exit Node")

        vt = sources.get("virustotal")
        if vt:
            parts.append("**VirusTotal**:")
            parts.append(
                f"  Malicious: {vt.get('malicious')} | Suspicious: {vt.get('suspicious')} | "
                f"Harmless: {vt.get('harmless')}"
            )
            parts.append(f"  Reputation: {vt.get('reputation')}")

        geo = sources.get("geo")
        if geo:
            parts.append("**Geolocation**:")
            parts.append(f"  {geo.get('city', '?')}, {geo.get('region', '?')}, {geo.get('country', '?')}")
            parts.append(f"  ISP: {geo.get('isp')} | Org: {geo.get('org')}")
            parts.append(f"  AS: {geo.get('as')}")

        if not sources:
            parts.append("No enrichment data available (no integrations configured).")

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Domain Reputation
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_domain_reputation(
    domain: str,
) -> str:
    """Look up domain reputation via VirusTotal.

    Requires VirusTotal integration to be configured.

    Args:
        domain: Domain name to look up (e.g. evil.com)
    """
    client = get_client()
    try:
        data = await client.post("/threat-intel/domain/lookup", json={"domain": domain})

        parts = [f"**Domain Reputation**: {data.get('domain', domain)}\n"]
        sources = data.get("sources", {})

        vt = sources.get("virustotal")
        if vt:
            parts.append(
                f"Malicious: {vt.get('malicious')} | Suspicious: {vt.get('suspicious')} | "
                f"Harmless: {vt.get('harmless')} | Undetected: {vt.get('undetected')}"
            )
            parts.append(f"Reputation: {vt.get('reputation')}")
            if vt.get("registrar"):
                parts.append(f"Registrar: {vt['registrar']}")
            if vt.get("creation_date"):
                parts.append(f"Created: {vt['creation_date']}")
            if vt.get("categories"):
                cats = ", ".join(f"{k}: {v}" for k, v in vt["categories"].items())
                parts.append(f"Categories: {cats}")
        else:
            parts.append("No enrichment data (VirusTotal integration not configured).")

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Email Reputation
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_email_reputation(
    email: str,
) -> str:
    """Look up email address in breach databases (Have I Been Pwned).

    Requires HIBP integration to be configured.

    Args:
        email: Email address to check
    """
    client = get_client()
    try:
        data = await client.post("/threat-intel/email/lookup", json={"email": email})

        parts = [f"**Email Reputation**: {data.get('email', email)}\n"]
        sources = data.get("sources", {})

        hibp = sources.get("hibp")
        if hibp:
            count = hibp.get("breach_count", 0)
            parts.append(f"Breaches Found: **{count}**")
            for b in hibp.get("breaches", [])[:10]:
                parts.append(
                    f"  • {b.get('name')} ({b.get('breach_date', 'N/A')}) — "
                    f"{b.get('pwn_count', 0):,} accounts, "
                    f"data: {', '.join(b.get('data_classes', [])[:5])}"
                )
        else:
            parts.append("No enrichment data (HIBP integration not configured).")

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Ransomware Victim Lookup
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_ransomware_lookup(
    query: str,
) -> str:
    """Search ransomware.live for victim postings by company/organisation name.

    No API key required — uses public API.

    Args:
        query: Company or organisation name to search (minimum 3 characters)
    """
    client = get_client()
    try:
        data = await client.post("/threat-intel/ransomware/lookup", json={"query": query})

        if not data.get("found"):
            return f"No ransomware victim postings found for: {query}"

        items = data.get("items", [])
        parts = [f"**Ransomware Victims** matching \"{query}\" ({data.get('total', 0)} results)\n"]
        for v in items[:20]:
            parts.append(
                f"• **{v.get('victim', 'Unknown')}** — Group: {v.get('group', '?')} | "
                f"Discovered: {v.get('discovered', 'N/A')}"
            )
            if v.get("country"):
                parts[-1] += f" | Country: {v['country']}"
        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
