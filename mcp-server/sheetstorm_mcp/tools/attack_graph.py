"""Attack graph tools — nodes, edges, auto-generation, and visualization."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


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
async def sheetstorm_auto_generate_graph(incident_id: str) -> str:
    """Auto-generate attack graph from incident data (hosts, IOCs, timeline, etc.).

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.post(f"/incidents/{incident_id}/attack-graph/auto-generate")
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        return (
            f"✓ Attack graph generated: {len(nodes)} nodes, {len(edges)} edges.\n"
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
        node_type: Node type (host, account, ioc, malware, process, action, attacker, target, lateral_movement)
        compromised_host_id: UUID of the related compromised host
        compromised_account_id: UUID of the related compromised account
        position_x: X coordinate for positioning
        position_y: Y coordinate for positioning
        metadata: JSON string with extra metadata
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
                payload["metadata"] = _json.loads(metadata)
            except _json.JSONDecodeError:
                payload["metadata"] = metadata

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
        node_type: New node type
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
) -> str:
    """Add an edge between two attack graph nodes.

    Args:
        incident_id: UUID of the incident
        source_node_id: UUID of the source node
        target_node_id: UUID of the target node
        edge_type: Edge type (compromised, lateral_movement, command_control, data_exfiltration, exploited, spawned, accessed, communicates_with, drops, executes)
        label: Display label for the edge
    """
    client = get_client()
    try:
        payload: dict = {
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "edge_type": edge_type,
        }
        if label:
            payload["label"] = label
        edge = await client.post(f"/incidents/{incident_id}/attack-graph/edges", json=payload)
        return f"✓ Edge added:\n{_format_edge(edge)}"
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
async def sheetstorm_get_node_types(incident_id: str) -> str:
    """Get available attack graph node types.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/attack-graph/node-types")
        types = data if isinstance(data, list) else data.get("node_types", data.get("types", []))
        if not types:
            return "No node types available."
        return "**Node Types**: " + ", ".join(str(t) for t in types)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_get_edge_types(incident_id: str) -> str:
    """Get available attack graph edge types.

    Args:
        incident_id: UUID of the incident
    """
    client = get_client()
    try:
        data = await client.get(f"/incidents/{incident_id}/attack-graph/edge-types")
        types = data if isinstance(data, list) else data.get("edge_types", data.get("types", []))
        if not types:
            return "No edge types available."
        return "**Edge Types**: " + ", ".join(str(t) for t in types)
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
