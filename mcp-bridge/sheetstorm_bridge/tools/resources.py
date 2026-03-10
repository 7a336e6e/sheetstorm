"""MCP resources — static and dynamic reference data exposed via resource URIs."""

from __future__ import annotations

import json

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import mcp, get_client


# ---------------------------------------------------------------------------
# Static resources
# ---------------------------------------------------------------------------

IR_PHASES = [
    {"phase": 1, "name": "Preparation", "description": "Establish IR capability, policies, and procedures."},
    {"phase": 2, "name": "Identification", "description": "Detect and determine whether an incident has occurred."},
    {"phase": 3, "name": "Containment", "description": "Limit the scope and impact of the incident."},
    {"phase": 4, "name": "Eradication", "description": "Remove the threat and root cause from the environment."},
    {"phase": 5, "name": "Recovery", "description": "Restore systems to normal operation and verify."},
    {"phase": 6, "name": "Lessons Learned", "description": "Document findings and improve processes."},
]

SEVERITY_LEVELS = [
    {"level": "critical", "description": "Business-critical systems compromised. Immediate executive response required."},
    {"level": "high", "description": "Significant impact. Multiple systems affected or sensitive data at risk."},
    {"level": "medium", "description": "Moderate impact. Limited systems affected, situation is contained."},
    {"level": "low", "description": "Minor impact. Single system, low risk, routine response."},
]

INCIDENT_STATUSES = [
    {"status": "open", "description": "Incident is active and being investigated."},
    {"status": "in_progress", "description": "Investigation is underway with assigned responders."},
    {"status": "contained", "description": "Threat has been contained but not yet eradicated."},
    {"status": "eradicated", "description": "Threat has been removed from the environment."},
    {"status": "recovered", "description": "Systems have been restored to normal operation."},
    {"status": "closed", "description": "Incident is fully resolved and documented."},
]


@mcp.resource("sheetstorm://reference/ir-phases")
async def get_ir_phases() -> str:
    """Incident Response lifecycle phases (NIST SP 800-61)."""
    return json.dumps(IR_PHASES, indent=2)


@mcp.resource("sheetstorm://reference/severity-levels")
async def get_severity_levels() -> str:
    """Incident severity level definitions."""
    return json.dumps(SEVERITY_LEVELS, indent=2)


@mcp.resource("sheetstorm://reference/incident-statuses")
async def get_incident_statuses() -> str:
    """Incident status definitions."""
    return json.dumps(INCIDENT_STATUSES, indent=2)


# ---------------------------------------------------------------------------
# Dynamic resources (fetched from API)
# ---------------------------------------------------------------------------

@mcp.resource("sheetstorm://reference/mitre-tactics")
async def get_mitre_tactics_resource() -> str:
    """MITRE ATT&CK tactics reference."""
    client = get_client()
    try:
        data = await client.get("/knowledge-base/mitre-attack/tactics")
        items = data if isinstance(data, list) else data.get("tactics", [])
        return json.dumps(items, indent=2)
    except SheetStormAPIError:
        return json.dumps({"error": "Failed to fetch MITRE tactics"})


@mcp.resource("sheetstorm://reference/mitre-techniques")
async def get_mitre_techniques_resource() -> str:
    """MITRE ATT&CK techniques reference."""
    client = get_client()
    try:
        data = await client.get("/knowledge-base/mitre-attack")
        items = data if isinstance(data, list) else data.get("techniques", [])
        return json.dumps(items, indent=2)
    except SheetStormAPIError:
        return json.dumps({"error": "Failed to fetch MITRE techniques"})


@mcp.resource("sheetstorm://reference/node-types")
async def get_node_types_resource() -> str:
    """Attack graph node type definitions."""
    client = get_client()
    try:
        # Use a dummy incident ID — the node types endpoint may work without one,
        # or we fall back to a static list.
        data = await client.get("/attack-graph/node-types")
        return json.dumps(data, indent=2)
    except SheetStormAPIError:
        # Fallback static list
        return json.dumps([
            "host", "account", "ioc", "malware", "process",
            "action", "attacker", "target", "lateral_movement",
        ])


@mcp.resource("sheetstorm://reference/edge-types")
async def get_edge_types_resource() -> str:
    """Attack graph edge type definitions."""
    client = get_client()
    try:
        data = await client.get("/attack-graph/edge-types")
        return json.dumps(data, indent=2)
    except SheetStormAPIError:
        # Fallback static list
        return json.dumps([
            "compromised", "lateral_movement", "command_control",
            "data_exfiltration", "exploited", "spawned", "accessed",
            "communicates_with", "drops", "executes",
        ])
