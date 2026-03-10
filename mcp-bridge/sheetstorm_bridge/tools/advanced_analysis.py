"""Advanced analysis tools — search, IOC correlation, STIX export, bulk enrichment."""

from __future__ import annotations

from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import mcp, get_client


@mcp.tool()
async def sheetstorm_search(
    query: str,
    entity_type: Optional[str] = None,
    incident_id: Optional[str] = None,
) -> str:
    """Search across all SheetStorm data (incidents, IOCs, hosts, notes, etc.).

    Args:
        query: Search query string
        entity_type: Filter by entity type (incident, host, ioc, note, task, artifact)
        incident_id: Scope search to a specific incident
    """
    client = get_client()
    try:
        params: dict = {"q": query}
        if entity_type:
            params["type"] = entity_type
        if incident_id:
            params["incident_id"] = incident_id
        data = await client.get("/search", params=params)
        results = data if isinstance(data, list) else data.get("results", data.get("items", []))

        if not results:
            return f"No results for '{query}'."

        lines = [f"**Search Results** for '{query}' ({len(results)} found)\n"]
        for r in results:
            rtype = r.get("type", r.get("entity_type", "unknown"))
            title = r.get("title", r.get("name", r.get("value", "N/A")))
            rid = r.get("id", "N/A")
            lines.append(f"[{rtype}] **{title}** (ID: {rid})")
            if r.get("snippet") or r.get("description"):
                snippet = r.get("snippet", r.get("description", ""))
                lines.append(f"  {snippet[:200]}")
            if r.get("incident_id"):
                lines.append(f"  Incident: {r['incident_id']}")
            lines.append("")

        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_correlate_iocs(
    indicators: str,
    incident_id: Optional[str] = None,
) -> str:
    """Correlate IOCs across incidents to find connections.

    Args:
        indicators: Pipe-separated list of indicators (e.g. '192.168.1.1|evil.com|abc123hash')
        incident_id: Optional incident ID to scope correlation
    """
    client = get_client()
    try:
        indicator_list = [i.strip() for i in indicators.split("|") if i.strip()]
        payload: dict = {"indicators": indicator_list}
        if incident_id:
            payload["incident_id"] = incident_id
        data = await client.post("/correlate-iocs", json=payload)
        correlations = data if isinstance(data, list) else data.get("correlations", data.get("results", []))

        if not correlations:
            return "No correlations found."

        lines = [f"**IOC Correlations** ({len(correlations)})\n"]
        for c in correlations:
            ioc_val = c.get("indicator", c.get("value", "N/A"))
            lines.append(f"**{ioc_val}**")
            incidents = c.get("incidents", c.get("found_in", []))
            if incidents:
                lines.append(f"  Found in {len(incidents)} incident(s):")
                for inc in incidents[:10]:
                    if isinstance(inc, dict):
                        lines.append(f"    - {inc.get('title', inc.get('id', 'N/A'))} (ID: {inc.get('id', 'N/A')})")
                    else:
                        lines.append(f"    - {inc}")
            if c.get("related_iocs"):
                lines.append(f"  Related IOCs: {len(c['related_iocs'])}")
            lines.append("")

        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_export_stix(incident_id: str) -> str:
    """Export incident data in STIX 2.1 format.

    Args:
        incident_id: UUID of the incident to export
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/export/stix")

        # Return a summary rather than the full STIX bundle
        if isinstance(data, dict):
            objects = data.get("objects", [])
            obj_types: dict = {}
            for obj in objects:
                otype = obj.get("type", "unknown")
                obj_types[otype] = obj_types.get(otype, 0) + 1

            lines = [f"**STIX 2.1 Export** for incident {incident_id}\n"]
            lines.append(f"  Bundle ID: {data.get('id', 'N/A')}")
            lines.append(f"  Total Objects: {len(objects)}")
            if obj_types:
                lines.append("  Object Types:")
                for otype, count in sorted(obj_types.items()):
                    lines.append(f"    - {otype}: {count}")
            return "\n".join(lines)
        else:
            return f"✓ STIX export completed. Data type: {type(data).__name__}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_bulk_enrich(
    indicators: str,
    enrichment_types: Optional[str] = None,
) -> str:
    """Bulk enrich multiple indicators at once.

    Args:
        indicators: Pipe-separated list of indicators (e.g. '192.168.1.1|evil.com|abc123hash')
        enrichment_types: Comma-separated enrichment sources (virustotal, whois, geoip, abuse). Defaults to all.
    """
    client = get_client()
    try:
        indicator_list = [i.strip() for i in indicators.split("|") if i.strip()]
        payload: dict = {"indicators": indicator_list}
        if enrichment_types:
            payload["enrichment_types"] = [t.strip() for t in enrichment_types.split(",")]
        data = await client.post("/bulk-enrich", json=payload)
        results = data if isinstance(data, list) else data.get("results", data.get("enrichments", []))

        if not results:
            return "No enrichment results."

        lines = [f"**Bulk Enrichment** ({len(results)} indicators)\n"]
        for r in results:
            indicator = r.get("indicator", r.get("value", "N/A"))
            lines.append(f"**{indicator}**")
            enrichments = r.get("enrichments", r.get("data", {}))
            if isinstance(enrichments, dict):
                for source, info in enrichments.items():
                    if isinstance(info, dict):
                        status = info.get("status", "ok")
                        lines.append(f"  [{source}] {status}")
                        if info.get("risk_score") is not None:
                            lines.append(f"    Risk: {info['risk_score']}")
                        if info.get("detections") is not None:
                            lines.append(f"    Detections: {info['detections']}")
                    else:
                        lines.append(f"  [{source}] {info}")
            elif isinstance(enrichments, list):
                for e in enrichments:
                    lines.append(f"  - {e}")
            lines.append("")

        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
