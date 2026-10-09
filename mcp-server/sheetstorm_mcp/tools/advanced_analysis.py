"""Advanced analysis tools — cross-incident search, IOC correlation,
STIX export, CSV export, and bulk enrichment."""

from __future__ import annotations

import csv
import io
import json
from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.config import get_config
from sheetstorm_mcp.server import get_client, mcp
from sheetstorm_mcp.tools.artifacts import LocalPathError, _safe_local_path, _write_local_file

# Entities of GET /incidents/<id>/export/<entity> (backend services/csv_export.py).
EXPORT_ENTITIES = ("timeline", "hosts", "accounts", "network-iocs", "host-iocs", "malware", "tasks")
MAX_INLINE_ROWS = 200

# ---------------------------------------------------------------------------
# Global Search
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_search(
    query: str,
    types: Optional[str] = None,
    incident_id: Optional[str] = None,
    sort: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> str:
    """Search across all incidents you can access.

    Matches substrings (partial IPs, hash prefixes, paths, DOMAIN\\user) in
    incidents, timeline events, hosts, accounts, IOCs, malware, and case notes.
    Types you lack the read permission for are left out.

    Args:
        query: Search term (2-200 characters)
        types: Comma-separated entity types to search (incidents,timeline,hosts,accounts,network_iocs,host_iocs,malware,notes). Default: all.
        incident_id: Restrict results to one incident (UUID)
        sort: relevance (default), -timestamp (newest first) or timestamp (oldest first)
        since: Only results at or after this ISO-8601 timestamp
        until: Only results at or before this ISO-8601 timestamp
        page: Page number (default 1)
        per_page: Results per page (default 50, max 50)
    """
    client = get_client()
    try:
        params: dict = {"q": query, "page": page, "per_page": max(1, min(per_page, 50))}
        for key, value in (("types", types), ("incident_id", incident_id), ("sort", sort),
                           ("since", since), ("until", until)):
            if value:
                params[key] = value

        data = await client.get("/search", params=params)
        results = data.get("results", [])
        total = data.get("total", 0)

        if not results:
            return f"No results found for '{query}'."

        parts = [f"**Search Results** — {total} matches for '{query}' "
                 f"(page {data.get('page', page)} of {data.get('pages', 1)})"]
        facets = data.get("facets") or {}
        if facets:
            parts.append("By type: " + ", ".join(f"{k}: {v}" for k, v in sorted(facets.items())))
        parts.append("")
        for r in results:
            icon = {
                'incident': '📋', 'timeline_event': '⏱️', 'host': '🖥️',
                'account': '👤', 'network_ioc': '🌐', 'host_ioc': '🔍',
                'malware': '🦠', 'case_note': '📝',
            }.get(r['type'], '📌')

            parts.append(
                f"{icon} **[{r['type'].upper()}]** {r['title']}\n"
                f"   ID: `{r.get('id', '')}`\n"
                f"   Incident: {r.get('incident_title', 'N/A')} (`{r.get('incident_id', '')}`)\n"
                f"   {(r.get('snippet') or '')[:150]}\n"
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
    incident_id: Optional[str] = None,
) -> str:
    """Find IOCs that appear across multiple incidents.

    Identifies shared indicators of compromise (IPs, domains, hashes,
    hostnames, file artifacts) across different incidents to detect
    related threat activity. Only incidents you can access are listed.

    Args:
        ioc_values: Optional comma-separated list of specific IOC values to check (max 1000).
                    If empty, finds ALL IOCs shared across 2+ incidents.
        ioc_types: Comma-separated IOC types to check (ip,domain,hash,hostname,file,all). Default: all.
        incident_id: Optional incident UUID. With no ioc_values, the values recorded in
                    that incident are checked against your other incidents.
    """
    client = get_client()
    try:
        body: dict = {}
        if ioc_values:
            body["ioc_values"] = [v.strip() for v in ioc_values.split(",") if v.strip()]
        if ioc_types:
            body["ioc_types"] = [t.strip() for t in ioc_types.split(",") if t.strip()]
        if incident_id:
            body["incident_id"] = incident_id

        data = await client.post("/correlate-iocs", json=body)
        correlations = data.get("correlations", [])

        if not correlations:
            return "No cross-incident IOC correlations found."

        parts = [f"**IOC Correlations** — {len(correlations)} shared indicators\n"]
        for c in correlations:
            others = [i for i in c.get("incidents", []) if not incident_id or i.get("id") != incident_id]
            incidents_str = ", ".join(f"{i['title']} (`{i['id'][:8]}…`)" for i in others)
            label = "Also seen in" if incident_id else "Seen in"
            count = len(others) if incident_id else c["incident_count"]
            parts.append(
                f"### `{c['ioc_value']}` ({c['ioc_type']})\n"
                f"{label} **{count}** incidents: {incidents_str}\n"
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
    save_path: Optional[str] = None,
) -> str:
    """Export an incident as a STIX 2.1 JSON bundle (marked with the incident's TLP).

    Generates a standards-compliant STIX 2.1 bundle containing all
    incident artifacts: indicators, malware, infrastructure, attack
    patterns, and their relationships. Needs the incidents:export permission.

    On the remote MCP server, save_path is relative to your private per-user
    artifact directory; on a local (stdio) server it is any local path.

    Args:
        incident_id: UUID of the incident to export
        save_path: Optional file to save the full bundle to (otherwise only a summary is returned)
    """
    client = get_client()
    try:
        target = None
        if save_path:
            try:
                target = _safe_local_path(save_path)
            except LocalPathError as exc:
                return f"✗ {exc}"
        resp = await client._send("GET", f"/incidents/{incident_id}/export/stix")
        data = resp.json()

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

        if target is not None:
            try:
                _write_local_file(target, resp.content, private=get_config().transport != "stdio")
            except LocalPathError as exc:
                return f"✗ {exc}"
            except OSError as exc:
                return f"✗ Cannot write {save_path}: {exc.strerror or exc}"
            parts.append(f"\n✓ Full bundle saved to {save_path} ({len(resp.content)} bytes)")
        else:
            parts.append("\n_Pass save_path to save the full STIX JSON, or GET "
                         f"/incidents/{incident_id}/export/stix._")

        return "\n".join(parts)

    except SheetStormAPIError as exc:
        return f"STIX export failed: {exc}"


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_export_csv(
    incident_id: str,
    entity: str,
    filters_json: Optional[str] = None,
    save_path: Optional[str] = None,
    defang: bool = False,
) -> str:
    """Export one entity of an incident as CSV (server-side, formula-safe, UTC times).

    Needs incidents:export plus the entity's read permission. Accounts never
    include passwords. Without save_path at most 200 rows are returned inline.

    On the remote MCP server, save_path is relative to your private per-user
    artifact directory; on a local (stdio) server it is any local path.

    Args:
        incident_id: UUID of the incident
        entity: One of: timeline, hosts, accounts, network-iocs, host-iocs, malware, tasks
        filters_json: Optional JSON object of the entity list's filters, e.g.
            '{"triage_status": "compromised", "q": "ws-", "sort": "-first_seen"}'
        save_path: Optional file to save the complete CSV to
        defang: Defang indicator values (evil[.]com, hxxp://) in IOC columns
    """
    if entity not in EXPORT_ENTITIES:
        return f"✗ entity must be one of: {', '.join(EXPORT_ENTITIES)}"
    params: dict = {}
    if filters_json:
        try:
            filters = json.loads(filters_json)
        except ValueError:
            return "✗ filters_json must be a JSON object"
        if not isinstance(filters, dict) or any(
                not isinstance(v, (str, int, float, bool)) for v in filters.values()):
            return "✗ filters_json must be a JSON object of simple values"
        params.update({str(k): str(v).lower() if isinstance(v, bool) else str(v) for k, v in filters.items()})
    if defang:
        params["defang"] = "true"

    client = get_client()
    try:
        target = None
        if save_path:
            try:
                target = _safe_local_path(save_path)
            except LocalPathError as exc:
                return f"✗ {exc}"
        resp = await client._send("GET", f"/incidents/{incident_id}/export/{entity}", params=params or None)
        content = resp.content
        if target is not None:
            try:
                _write_local_file(target, content, private=get_config().transport != "stdio")
            except LocalPathError as exc:
                return f"✗ {exc}"
            except OSError as exc:
                return f"✗ Cannot write {save_path}: {exc.strerror or exc}"
            return f"✓ {entity} CSV saved to {save_path} ({len(content)} bytes)"

        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig", errors="replace"))))
        header, body = (rows[0] if rows else []), rows[1:]
        total = len(body)
        shown = body[:MAX_INLINE_ROWS]
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(shown)
        note = (f"Showing the first {len(shown)} of {total} rows; pass save_path for the complete file."
                if total > len(shown) else f"{total} rows.")
        return f"**{entity} export**\n```csv\n{out.getvalue()}```\n{note}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Bulk Enrichment
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_bulk_enrich(
    ioc_values: str,
    incident_id: Optional[str] = None,
) -> str:
    """Enrich multiple IOCs in batch against threat intelligence sources.

    Queries VirusTotal, AbuseIPDB, and other configured sources for
    reputation and context on each IOC. The values are sent to those
    third-party providers; TLP:RED data is never sent (and AMBER+STRICT only
    when the organization allows it), the server refuses or marks such values
    as blocked.

    Args:
        ioc_values: Pipe-separated list of IOCs in format 'type:value'.
                    Types: ip, domain, hash, md5, sha1, sha256, email, hostname.
                    Example: 'ip:8.8.8.8|domain:evil.com|sha256:abc123...'
        incident_id: Optional incident UUID the values belong to; its TLP is
                    checked first (a restricted incident is refused as a whole).
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

        body: dict = {"ioc_values": ioc_list}
        if incident_id:
            body["incident_id"] = incident_id
        data = await client.post("/bulk-enrich", json=body)
        results = data.get("results", [])

        parts = [
            f"**Bulk Enrichment** — {data.get('total', 0)} IOCs processed\n",
            f"✅ Enriched: {data.get('enriched', 0)} | ❌ Failed: {data.get('failed', 0)}"
            f" | ⛔ Blocked (TLP): {data.get('blocked', 0)}\n",
        ]
        if data.get("providers"):
            parts.append(f"Providers: {', '.join(data['providers'])}\n")

        for r in results:
            status_icon = {"success": "✅", "blocked": "⛔"}.get(r["status"], "❌")
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
