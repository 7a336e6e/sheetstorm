"""Attack graph tools — nodes, edges, auto-generation, and visualization."""

from __future__ import annotations

from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import get_client, mcp

# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _format_node(n: dict) -> str:
    label = n.get("label", n.get("name", "Unknown"))
    host_id = n.get("compromised_host_id", "")
    acct_id = n.get("compromised_account_id", "")
    entity = host_id or acct_id or "N/A"
    return (
        f"**{label}** (ID: {n.get('id', 'N/A')})\n"
        f"  Type: {n.get('node_type', 'N/A')} | "
        f"Entity: {entity}\n"
        f"  Position: ({n.get('position_x', '?')}, {n.get('position_y', '?')})"
    )


def _format_edge(e: dict) -> str:
    return (
        f"**{e.get('label', e.get('edge_type', 'N/A'))}** (ID: {e.get('id', 'N/A')})\n"
        f"  {e.get('source_node_id', 'N/A')} → {e.get('target_node_id', 'N/A')}\n"
        f"  Type: {e.get('edge_type', 'N/A')}"
    )


# ---------------------------------------------------------------------------
# Graph-level tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_get_attack_graph(incident_id: str) -> str:
    """Get the full attack graph (nodes and edges) for an incident.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/attack-graph")
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        lines = [f"**Attack Graph** — {len(nodes)} nodes, {len(edges)} edges\n"]

        if nodes:
            lines.append("### Nodes")
            for n in nodes:
                lines.append(_format_node(n))
                lines.append("")

        if edges:
            lines.append("### Edges")
            for e in edges:
                lines.append(_format_edge(e))
                lines.append("")

        if not nodes and not edges:
            lines.append("Graph is empty. Use auto-generate to build from incident data.")

        return "\n".join(lines)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_auto_generate_graph(
    incident_id: str,
    mode: str = "merge",
    confirm: bool = False,
) -> str:
    """Auto-generate the attack graph from incident data (hosts, IOCs, timeline, etc.).

    mode "merge" (default) only adds what is missing and never moves, edits or
    deletes existing nodes and edges. mode "replace" deletes the whole graph
    (including manual nodes, edges and positions) and rebuilds it; it needs
    confirm=true.

    Args:
        incident_id: UUID of the incident
        mode: "merge" (default) or "replace"
        confirm: Must be true for mode "replace"
    """
    client = get_client()
    try:
        body: dict = {"mode": mode}
        if confirm:
            body["confirm"] = True
        data = await client.post(f"/incidents/{incident_id}/attack-graph/auto-generate", json=body)
        created = data.get("created") or {}
        nodes = created.get("nodes", len(data.get("nodes", [])))
        edges = created.get("edges", len(data.get("edges", [])))
        verb = "rebuilt" if data.get("mode", mode) == "replace" else "updated (merge)"
        return (
            f"✓ Attack graph {verb}: {nodes} nodes, {edges} edges created.\n"
            f"Use sheetstorm_get_attack_graph to view the full graph."
        )
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Node tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_add_graph_node(
    incident_id: str,
    label: str,
    node_type: str,
    compromised_host_id: Optional[str] = None,
    compromised_account_id: Optional[str] = None,
    position_x: Optional[float] = None,
    position_y: Optional[float] = None,
    metadata: Optional[str] = None,
) -> str:
    """Add a node to the attack graph.

    Args:
        incident_id: UUID of the incident
        label: Display label for the node
        node_type: Node type — one of: workstation, server, domain_controller, attacker, c2_server, cloud_resource, user, service_account, external, unknown, ip_address, malware, host_indicator, database, web_server, file_server
        compromised_host_id: UUID of the related compromised host
        compromised_account_id: UUID of the related compromised account
        position_x: X coordinate for positioning
        position_y: Y coordinate for positioning
        metadata: JSON object string with extra metadata (stored as the node's extra_data)
    """
    client = get_client()
    try:
        import json as _json

        payload: dict = {"label": label, "node_type": node_type}
        if compromised_host_id:
            payload["compromised_host_id"] = compromised_host_id
        if compromised_account_id:
            payload["compromised_account_id"] = compromised_account_id
        if position_x is not None:
            payload["position_x"] = position_x
        if position_y is not None:
            payload["position_y"] = position_y
        if metadata:
            try:
                extra = _json.loads(metadata)
            except _json.JSONDecodeError:
                return "✗ Error: metadata must be a JSON object."
            if not isinstance(extra, dict):
                return "✗ Error: metadata must be a JSON object."
            payload["extra_data"] = extra

        node = await client.post(f"/incidents/{incident_id}/attack-graph/nodes", json=payload)
        return f"✓ Node added:\n{_format_node(node)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_graph_node(
    incident_id: str,
    node_id: str,
    label: Optional[str] = None,
    node_type: Optional[str] = None,
    position_x: Optional[float] = None,
    position_y: Optional[float] = None,
) -> str:
    """Update an attack graph node.

    Args:
        incident_id: UUID of the incident
        node_id: UUID of the node
        label: New label
        node_type: New node type — one of: workstation, server, domain_controller, attacker, c2_server, cloud_resource, user, service_account, external, unknown, ip_address, malware, host_indicator, database, web_server, file_server
        position_x: New X coordinate
        position_y: New Y coordinate
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, val in [("label", label), ("node_type", node_type), ("position_x", position_x), ("position_y", position_y)]:
            if val is not None:
                payload[field] = val
        if not payload:
            return "No fields to update."
        node = await client.put(
            f"/incidents/{incident_id}/attack-graph/nodes/{node_id}", json=payload
        )
        return f"✓ Node updated:\n{_format_node(node)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_delete_graph_node(incident_id: str, node_id: str) -> str:
    """Delete an attack graph node (also removes connected edges).

    Args:
        incident_id: UUID of the incident
        node_id: UUID of the node to delete
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/attack-graph/nodes/{node_id}")
        return f"✓ Node {node_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Edge tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_add_graph_edge(
    incident_id: str,
    source_node_id: str,
    target_node_id: str,
    edge_type: str,
    label: Optional[str] = None,
    mitre_tactic: Optional[str] = None,
    mitre_technique: Optional[str] = None,
    timestamp: Optional[str] = None,
    description: Optional[str] = None,
    timeline_event_id: Optional[str] = None,
) -> str:
    """Add an edge between two attack graph nodes.

    Args:
        incident_id: UUID of the incident
        source_node_id: UUID of the source node
        target_node_id: UUID of the target node
        edge_type: Edge type — one of: lateral_movement, credential_theft, data_exfiltration, command_control, initial_access, privilege_escalation, persistence, discovery, execution, defense_evasion, collection, associated_with
        label: Display label for the edge
        mitre_tactic: Optional MITRE ATT&CK tactic for this step
        mitre_technique: Optional MITRE ATT&CK technique ID (e.g. T1021.001)
        timestamp: Optional ISO 8601 time of this step
        description: Optional description
        timeline_event_id: Optional timeline event UUID to link (fills MITRE/timestamp from it)
    """
    client = get_client()
    try:
        payload: dict = {
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "edge_type": edge_type,
        }
        for field, val in [
            ("label", label),
            ("mitre_tactic", mitre_tactic),
            ("mitre_technique", mitre_technique),
            ("timestamp", timestamp),
            ("description", description),
            ("timeline_event_id", timeline_event_id),
        ]:
            if val:
                payload[field] = val
        edge = await client.post(f"/incidents/{incident_id}/attack-graph/edges", json=payload)
        return f"✓ Edge added:\n{_format_edge(edge)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_update_graph_edge(
    incident_id: str,
    edge_id: str,
    edge_type: Optional[str] = None,
    label: Optional[str] = None,
    mitre_tactic: Optional[str] = None,
    mitre_technique: Optional[str] = None,
    timestamp: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Update an attack graph edge. Only the fields given are changed.

    Args:
        incident_id: UUID of the incident
        edge_id: UUID of the edge
        edge_type: New edge type — one of: lateral_movement, credential_theft, data_exfiltration, command_control, initial_access, privilege_escalation, persistence, discovery, execution, defense_evasion, collection, associated_with
        label: New display label
        mitre_tactic: MITRE ATT&CK tactic
        mitre_technique: MITRE ATT&CK technique ID
        timestamp: ISO 8601 time of this step
        description: Description
    """
    client = get_client()
    try:
        payload: dict = {}
        for field, val in [
            ("edge_type", edge_type),
            ("label", label),
            ("mitre_tactic", mitre_tactic),
            ("mitre_technique", mitre_technique),
            ("timestamp", timestamp),
            ("description", description),
        ]:
            if val is not None:
                payload[field] = val
        if not payload:
            return "No fields to update."
        edge = await client.put(
            f"/incidents/{incident_id}/attack-graph/edges/{edge_id}", json=payload
        )
        return f"✓ Edge updated:\n{_format_edge(edge)}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_delete_graph_edge(incident_id: str, edge_id: str) -> str:
    """Delete an attack graph edge.

    Args:
        incident_id: UUID of the incident
        edge_id: UUID of the edge to delete
    """
    client = get_client()
    try:
        await client.delete(f"/incidents/{incident_id}/attack-graph/edges/{edge_id}")
        return f"✓ Edge {edge_id} deleted."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

@mcp.tool()
async def sheetstorm_get_node_types() -> str:
    """Get the valid attack graph node types."""
    client = get_client()
    try:
        data = await client.get("/attack-graph/node-types")
        types = data if isinstance(data, list) else data.get("node_types", [])
        if not types:
            return "No node types available."
        return "**Node Types**: " + ", ".join(str(t) for t in types)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_edge_types() -> str:
    """Get the valid attack graph edge types."""
    client = get_client()
    try:
        data = await client.get("/attack-graph/edge-types")
        types = data if isinstance(data, list) else data.get("edge_types", [])
        if not types:
            return "No edge types available."
        return "**Edge Types**: " + ", ".join(str(t) for t in types)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
