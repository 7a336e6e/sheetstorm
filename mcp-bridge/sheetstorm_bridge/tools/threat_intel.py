"""Threat intelligence tools — VirusTotal, MISP, CVE, reputation lookups, ransomware."""

from __future__ import annotations

from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import mcp, get_client


@mcp.tool()
async def sheetstorm_virustotal_lookup(
    indicator: str,
    indicator_type: Optional[str] = None,
) -> str:
    """Look up an indicator in VirusTotal (hash, IP, domain, or URL).

    Args:
        indicator: The indicator to look up
        indicator_type: Type hint (hash, ip, domain, url). Auto-detected if omitted.
    """
    client = get_client()
    try:
        payload: dict = {"indicator": indicator}
        if indicator_type:
            payload["indicator_type"] = indicator_type
        data = await client.post("/threat-intel/virustotal/lookup", json=payload)

        parts = [f"**VirusTotal Lookup**: {indicator}\n"]

        if data.get("error"):
            return f"✗ VirusTotal error: {data['error']}"

        # Detection stats
        stats = data.get("last_analysis_stats", data.get("stats", {}))
        if stats:
            parts.append(
                f"  Detections: {stats.get('malicious', 0)}/{stats.get('malicious', 0) + stats.get('undetected', 0)}"
            )
        if data.get("reputation") is not None:
            parts.append(f"  Reputation: {data['reputation']}")

        # File-specific info
        if data.get("sha256"):
            parts.append(f"  SHA256: {data['sha256']}")
        if data.get("meaningful_name") or data.get("name"):
            parts.append(f"  Name: {data.get('meaningful_name', data.get('name'))}")
        if data.get("type_description"):
            parts.append(f"  Type: {data['type_description']}")
        if data.get("size"):
            parts.append(f"  Size: {data['size']} bytes")

        # Network-specific
        if data.get("country"):
            parts.append(f"  Country: {data['country']}")
        if data.get("as_owner"):
            parts.append(f"  AS Owner: {data['as_owner']}")

        # Tags/categories
        if data.get("tags"):
            parts.append(f"  Tags: {', '.join(data['tags'])}")
        if data.get("categories"):
            cats = data["categories"]
            if isinstance(cats, dict):
                unique = set(cats.values())
                parts.append(f"  Categories: {', '.join(unique)}")
            else:
                parts.append(f"  Categories: {cats}")

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_misp_push_iocs(
    incident_id: str,
    ioc_types: Optional[str] = None,
) -> str:
    """Push incident IOCs to MISP threat intelligence platform.

    Args:
        incident_id: UUID of the incident
        ioc_types: Comma-separated IOC types to push (network, host, malware). Defaults to all.
    """
    client = get_client()
    try:
        payload: dict = {"incident_id": incident_id}
        if ioc_types:
            payload["ioc_types"] = [t.strip() for t in ioc_types.split(",")]
        data = await client.post("/threat-intel/misp/push", json=payload)
        pushed = data.get("pushed", data.get("count", 0))
        event_id = data.get("event_id", data.get("misp_event_id", "N/A"))
        return (
            f"✓ Pushed {pushed} IOCs to MISP\n"
            f"  MISP Event ID: {event_id}\n"
            f"  URL: {data.get('event_url', 'N/A')}"
        )
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_cve_lookup(cve_id: str) -> str:
    """Look up a CVE by ID (e.g. CVE-2024-1234).

    Args:
        cve_id: CVE identifier (e.g. CVE-2024-1234)
    """
    client = get_client()
    try:
        data = await client.post("/threat-intel/cve/lookup", json={"cve_id": cve_id})
        if data.get("error"):
            return f"✗ CVE lookup error: {data['error']}"

        parts = [f"**{data.get('id', cve_id)}**: {data.get('description', 'No description')}\n"]

        if data.get("cvss_score") is not None or data.get("cvss"):
            score = data.get("cvss_score", data.get("cvss", {}).get("score", "N/A"))
            severity = data.get("severity", data.get("cvss", {}).get("severity", "N/A"))
            parts.append(f"  CVSS: {score} ({severity})")
        if data.get("published"):
            parts.append(f"  Published: {data['published']}")
        if data.get("references"):
            refs = data["references"]
            if isinstance(refs, list):
                parts.append(f"  References: {len(refs)} linked")
                for r in refs[:5]:
                    url = r.get("url", r) if isinstance(r, dict) else r
                    parts.append(f"    - {url}")
        if data.get("affected_products") or data.get("cpe"):
            products = data.get("affected_products", data.get("cpe", []))
            if isinstance(products, list):
                parts.append(f"  Affected products: {len(products)}")
                for p in products[:5]:
                    parts.append(f"    - {p}")

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_ip_reputation(ip_address: str) -> str:
    """Check reputation of an IP address.

    Args:
        ip_address: IP address to look up
    """
    client = get_client()
    try:
        data = await client.post("/threat-intel/ip/lookup", json={"ip": ip_address})
        if data.get("error"):
            return f"✗ IP reputation error: {data['error']}"

        parts = [f"**IP Reputation**: {ip_address}\n"]
        if data.get("risk_score") is not None:
            parts.append(f"  Risk Score: {data['risk_score']}")
        if data.get("country"):
            parts.append(f"  Country: {data['country']}")
        if data.get("isp") or data.get("as_owner"):
            parts.append(f"  ISP/AS: {data.get('isp', data.get('as_owner', 'N/A'))}")
        if data.get("is_tor") is not None:
            parts.append(f"  Tor Exit: {'Yes' if data['is_tor'] else 'No'}")
        if data.get("is_vpn") is not None:
            parts.append(f"  VPN: {'Yes' if data['is_vpn'] else 'No'}")
        if data.get("abuse_reports") is not None:
            parts.append(f"  Abuse Reports: {data['abuse_reports']}")
        if data.get("tags"):
            parts.append(f"  Tags: {', '.join(data['tags'])}")

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_domain_reputation(domain: str) -> str:
    """Check reputation of a domain.

    Args:
        domain: Domain name to look up
    """
    client = get_client()
    try:
        data = await client.post("/threat-intel/domain/lookup", json={"domain": domain})
        if data.get("error"):
            return f"✗ Domain reputation error: {data['error']}"

        parts = [f"**Domain Reputation**: {domain}\n"]
        if data.get("risk_score") is not None:
            parts.append(f"  Risk Score: {data['risk_score']}")
        if data.get("category"):
            parts.append(f"  Category: {data['category']}")
        if data.get("registrar"):
            parts.append(f"  Registrar: {data['registrar']}")
        if data.get("creation_date"):
            parts.append(f"  Created: {data['creation_date']}")
        if data.get("dns_records"):
            records = data["dns_records"]
            if isinstance(records, list):
                parts.append(f"  DNS Records: {len(records)}")
                for r in records[:5]:
                    parts.append(f"    - {r}")
        if data.get("tags"):
            parts.append(f"  Tags: {', '.join(data['tags'])}")

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_email_reputation(email: str) -> str:
    """Check reputation of an email address.

    Args:
        email: Email address to look up
    """
    client = get_client()
    try:
        data = await client.post("/threat-intel/email/lookup", json={"email": email})
        if data.get("error"):
            return f"✗ Email reputation error: {data['error']}"

        parts = [f"**Email Reputation**: {email}\n"]
        if data.get("risk_score") is not None:
            parts.append(f"  Risk Score: {data['risk_score']}")
        if data.get("disposable") is not None:
            parts.append(f"  Disposable: {'Yes' if data['disposable'] else 'No'}")
        if data.get("deliverable") is not None:
            parts.append(f"  Deliverable: {'Yes' if data['deliverable'] else 'No'}")
        if data.get("breach_count") is not None:
            parts.append(f"  Known Breaches: {data['breach_count']}")
        if data.get("domain_reputation") is not None:
            parts.append(f"  Domain Rep: {data['domain_reputation']}")
        if data.get("tags"):
            parts.append(f"  Tags: {', '.join(data['tags'])}")

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_ransomware_lookup(
    name: Optional[str] = None,
    extension: Optional[str] = None,
) -> str:
    """Look up ransomware by name or file extension.

    Args:
        name: Ransomware family name (e.g. LockBit, BlackCat)
        extension: Encrypted file extension (e.g. .lockbit, .encrypted)
    """
    client = get_client()
    try:
        payload: dict = {}
        if name:
            payload["name"] = name
        if extension:
            payload["extension"] = extension
        if not payload:
            return "Provide at least a ransomware name or file extension."

        data = await client.post("/threat-intel/ransomware/lookup", json=payload)
        if data.get("error"):
            return f"✗ Ransomware lookup error: {data['error']}"

        results = data.get("results", [data] if data.get("name") else [])
        if not results:
            return "No ransomware information found."

        parts = [f"**Ransomware Lookup** ({len(results)} results)\n"]
        for r in results:
            parts.append(f"**{r.get('name', 'Unknown')}**")
            if r.get("extensions"):
                exts = r["extensions"]
                if isinstance(exts, list):
                    parts.append(f"  Extensions: {', '.join(exts)}")
                else:
                    parts.append(f"  Extensions: {exts}")
            if r.get("ransom_note"):
                parts.append(f"  Ransom Note: {r['ransom_note']}")
            if r.get("decryptor_available") is not None:
                parts.append(f"  Decryptor Available: {'Yes' if r['decryptor_available'] else 'No'}")
            if r.get("references"):
                refs = r["references"]
                if isinstance(refs, list):
                    for ref in refs[:3]:
                        parts.append(f"    - {ref}")
            parts.append("")

        return "\n".join(parts)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
