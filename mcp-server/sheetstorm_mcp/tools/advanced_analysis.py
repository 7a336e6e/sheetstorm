"""Advanced analysis tools — cross-incident search, IOC correlation,
STIX export, and bulk enrichment."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


# ---------------------------------------------------------------------------
# Global Search
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_search(
    query: str,
    types: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> str:
    """Search across all incidents for matching data.

    Full-text search across incidents, timeline events, hosts, accounts,
    IOCs, malware, and case notes.

    Args:
        query: Search term (min 2 characters)
        types: Comma-separated entity types to search (incidents,timeline,hosts,accounts,network_iocs,host_iocs,malware,notes). Default: all.
        page: Page number (default 1)
        per_page: Results per page (default 50, max 200)
    """
    client = get_client()
    try:
        params: dict = {"q": query, "page": page, "per_page": per_page}
        if types:
            params["types"] = types

        data = await client.get("/search", params=params)
        results = data.get("results", [])
        total = data.get("total", 0)

        if not results:
            return f"No results found for '{query}'."

        parts = [f"**Search Results** — {total} matches for '{query}' (page {page})\n"]
        for r in results:
            icon = {
                'incident': '📋', 'timeline_event': '⏱️', 'host': '🖥️',
                'account': '👤', 'network_ioc': '🌐', 'host_ioc': '🔍',
                'malware': '🦠', 'case_note': '📝',
            }.get(r['type'], '📌')

            parts.append(
                f"{icon} **[{r['type'].upper()}]** {r['title']}\n"
                f"   Incident: {r.get('incident_title', 'N/A')} (`{r.get('incident_id', '')[:8]}…`)\n"
                f"   {r.get('snippet', '')[:150]}\n"
                f"   _{r.get('timestamp', 'N/A')}_\n"
            )

        return "\n".join(parts)

    except SheetStormAPIError as exc:
        return f"Search failed: {exc}"


# ---------------------------------------------------------------------------
# IOC Correlation
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_correlate_iocs(
    ioc_values: Optional[str] = None,
    ioc_types: Optional[str] = None,
) -> str:
    """Find IOCs that appear across multiple incidents.

    Identifies shared indicators of compromise (IPs, domains, hashes,
    hostnames, file artifacts) across different incidents to detect
    related threat activity.

    Args:
        ioc_values: Optional comma-separated list of specific IOC values to check.
                    If empty, finds ALL IOCs shared across 2+ incidents.
        ioc_types: Comma-separated IOC types to check (ip,domain,hash,hostname,file,all). Default: all.
    """
    client = get_client()
    try:
        body: dict = {}
        if ioc_values:
            body["ioc_values"] = [v.strip() for v in ioc_values.split(",")]
        if ioc_types:
            body["ioc_types"] = [t.strip() for t in ioc_types.split(",")]

        data = await client.post("/correlate-iocs", json=body)
        correlations = data.get("correlations", [])

        if not correlations:
            return "No cross-incident IOC correlations found."

        parts = [f"**IOC Correlations** — {len(correlations)} shared indicators\n"]
        for c in correlations:
            incidents_str = ", ".join(
                f"{i['title']} (`{i['id'][:8]}…`)" for i in c.get("incidents", [])
            )
            parts.append(
                f"### `{c['ioc_value']}` ({c['ioc_type']})\n"
                f"Seen in **{c['incident_count']}** incidents: {incidents_str}\n"
            )

        return "\n".join(parts)

    except SheetStormAPIError as exc:
        return f"IOC correlation failed: {exc}"


# ---------------------------------------------------------------------------
# STIX Export
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_export_stix(
    incident_id: str,
) -> str:
    """Export an incident as a STIX 2.1 JSON bundle.

    Generates a standards-compliant STIX 2.1 bundle containing all
    incident artifacts: indicators, malware, infrastructure, attack
    patterns, and their relationships.

    Args:
        incident_id: UUID of the incident to export
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/export/stix")

        objects = data.get("objects", [])
        type_counts: dict[str, int] = {}
        for obj in objects:
            t = obj.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        parts = [
            f"**STIX 2.1 Export** — Bundle `{data.get('id', 'N/A')}`\n",
            f"Total objects: {len(objects)}\n",
        ]
        for t, count in sorted(type_counts.items()):
            parts.append(f"- **{t}**: {count}")

        # Show report summary
        for obj in objects:
            if obj.get("type") == "report":
                parts.append(f"\n**Report**: {obj.get('name', 'N/A')}")
                parts.append(f"Labels: {', '.join(obj.get('labels', []))}")
                parts.append(f"Object refs: {len(obj.get('object_refs', []))}")
                break

        parts.append(f"\n_Full STIX JSON available via API GET /incidents/{incident_id}/export/stix_")

        return "\n".join(parts)

    except SheetStormAPIError as exc:
        return f"STIX export failed: {exc}"


# ---------------------------------------------------------------------------
# Bulk Enrichment
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_bulk_enrich(
    ioc_values: str,
) -> str:
    """Enrich multiple IOCs in batch against threat intelligence sources.

    Queries VirusTotal, AbuseIPDB, and other configured sources for
    reputation and context on each IOC.

    Args:
        ioc_values: Pipe-separated list of IOCs in format 'type:value'.
                    Types: ip, domain, hash, md5, sha256, email.
                    Example: 'ip:8.8.8.8|domain:evil.com|hash:abc123'
    """
    client = get_client()
    try:
        # Parse pipe-separated input
        ioc_list = []
        for entry in ioc_values.split("|"):
            entry = entry.strip()
            if ":" not in entry:
                continue
            ioc_type, value = entry.split(":", 1)
            ioc_list.append({"type": ioc_type.strip(), "value": value.strip()})

        if not ioc_list:
            return "No valid IOCs provided. Format: 'type:value|type:value'"

        data = await client.post("/bulk-enrich", json={"ioc_values": ioc_list})
        results = data.get("results", [])

        parts = [
            f"**Bulk Enrichment** — {data.get('total', 0)} IOCs processed\n",
            f"✅ Enriched: {data.get('enriched', 0)} | ❌ Failed: {data.get('failed', 0)}\n",
        ]

        for r in results:
            status_icon = "✅" if r["status"] == "success" else "❌"
            parts.append(f"{status_icon} **{r['type']}**: `{r['value']}`")
            if r["status"] == "success" and r.get("enrichment"):
                enrich = r["enrichment"]
                for key, val in list(enrich.items())[:5]:
                    parts.append(f"   - {key}: {val}")
            elif r.get("error"):
                parts.append(f"   Error: {r['error']}")

        return "\n".join(parts)

    except SheetStormAPIError as exc:
        return f"Bulk enrichment failed: {exc}"
