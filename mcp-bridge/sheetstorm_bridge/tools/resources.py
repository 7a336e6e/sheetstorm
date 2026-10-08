"""MCP Resources — read-only reference data exposed as MCP resources."""

from __future__ import annotations

import json

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import get_client, mcp

# ---------------------------------------------------------------------------
# Static reference resources
# ---------------------------------------------------------------------------

IR_PHASES = [
    {"phase": 1, "name": "Preparation", "description": "Establish incident response capability and readiness."},
    {"phase": 2, "name": "Identification", "description": "Detect and determine whether an incident has occurred."},
    {"phase": 3, "name": "Containment", "description": "Limit the scope and magnitude of the incident."},
    {"phase": 4, "name": "Eradication", "description": "Remove the threat from the environment."},
    {"phase": 5, "name": "Recovery", "description": "Restore systems and operations to normal."},
    {"phase": 6, "name": "Lessons Learned", "description": "Document findings and improve future response."},
]

SEVERITY_LEVELS = [
    {"level": "critical", "description": "Business-critical systems compromised, data exfiltration confirmed."},
    {"level": "high", "description": "Significant impact, active threat requiring immediate response."},
    {"level": "medium", "description": "Moderate impact, threat contained but needs investigation."},
    {"level": "low", "description": "Minor impact, suspicious activity under monitoring."},
]

INCIDENT_STATUSES = [
    {"status": "open", "phase": 1, "description": "Incident opened, scoping not yet started."},
    {"status": "investigating", "phase": 2, "description": "Investigation and scoping underway."},
    {"status": "contained", "phase": 3, "description": "Threat has been contained."},
    {"status": "eradicated", "phase": 4, "description": "Threat has been removed from the environment."},
    {"status": "recovered", "phase": 5, "description": "Systems restored to normal operation."},
    {"status": "closed", "phase": 6, "description": "Post-incident review complete, case closed."},
]


@mcp.resource("sheetstorm://reference/ir-phases")
async def get_ir_phases() -> str:
    """NIST IR lifecycle phases used by SheetStorm."""
    return json.dumps(IR_PHASES, indent=2)


@mcp.resource("sheetstorm://reference/severity-levels")
async def get_severity_levels() -> str:
    """Incident severity levels used by SheetStorm."""
    return json.dumps(SEVERITY_LEVELS, indent=2)


@mcp.resource("sheetstorm://reference/incident-statuses")
async def get_incident_statuses() -> str:
    """Incident status values used by SheetStorm."""
    return json.dumps(INCIDENT_STATUSES, indent=2)


# ---------------------------------------------------------------------------
# Dynamic reference resources
# ---------------------------------------------------------------------------

@mcp.resource("sheetstorm://reference/mitre-tactics")
async def get_mitre_tactics_resource() -> str:
    """MITRE ATT&CK tactics available in SheetStorm."""
    client = get_client()
    try:
        data = await client.get("/mitre/tactics")
        return json.dumps(data, indent=2)
    except SheetStormAPIError:
        return json.dumps({"error": "Could not fetch MITRE tactics. Ensure backend is running."})


@mcp.resource("sheetstorm://reference/mitre-techniques")
async def get_mitre_techniques_resource() -> str:
    """MITRE ATT&CK techniques available in SheetStorm."""
    client = get_client()
    try:
        data = await client.get("/mitre/techniques")
        return json.dumps(data, indent=2)
    except SheetStormAPIError:
        return json.dumps({"error": "Could not fetch MITRE techniques. Ensure backend is running."})


@mcp.resource("sheetstorm://reference/node-types")
async def get_graph_node_types_resource() -> str:
    """Valid attack graph node types (from the backend)."""
    client = get_client()
    try:
        data = await client.get("/attack-graph/node-types")
        return json.dumps(data.get("node_types", []), indent=2)
    except SheetStormAPIError:
        return json.dumps({"error": "Could not fetch node types. Ensure backend is running."})


@mcp.resource("sheetstorm://reference/edge-types")
async def get_graph_edge_types_resource() -> str:
    """Valid attack graph edge types (from the backend)."""
    client = get_client()
    try:
        data = await client.get("/attack-graph/edge-types")
        return json.dumps(data.get("edge_types", []), indent=2)
    except SheetStormAPIError:
        return json.dumps({"error": "Could not fetch edge types. Ensure backend is running."})
