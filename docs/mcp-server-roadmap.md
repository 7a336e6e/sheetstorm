# MCP Server Roadmap — SheetStorm

## Overview

A **Model Context Protocol (MCP) server** for SheetStorm enables AI assistants (Claude Code, Cursor, custom agents) to interact with the incident response platform programmatically — querying incidents, enriching IOCs, creating timeline events, and generating reports through natural language.

## Architecture

```
┌──────────────────────┐      MCP Protocol       ┌──────────────────────┐
│  AI Client           │ ◄──────────────────────► │  SheetStorm MCP      │
│  (Claude, Cursor,    │   stdio / SSE / HTTP     │  Server              │
│   custom agents)     │                          │                      │
└──────────────────────┘                          └──────┬───────────────┘
                                                         │
                                                         │ REST API + JWT
                                                         ▼
                                                  ┌──────────────────────┐
                                                  │  SheetStorm Backend  │
                                                  │  (Flask API)         │
                                                  └──────────────────────┘
```

The MCP server acts as a bridge between AI assistants and the SheetStorm REST API, translating natural language tool calls into authenticated API requests.

## Phase 1 — Core Read Tools (v0.1)

**Target:** 2 weeks  
**Goal:** AI can query and analyze incident data

### Tools

| Tool | Description | API Endpoint |
|------|-------------|--------------|
| `list_incidents` | List incidents with filters (status, severity, phase) | `GET /api/v1/incidents` |
| `get_incident` | Get full incident details by ID | `GET /api/v1/incidents/{id}` |
| `list_timeline_events` | Get chronological events for an incident | `GET /api/v1/incidents/{id}/events` |
| `list_compromised_hosts` | List affected systems | `GET /api/v1/incidents/{id}/hosts` |
| `list_iocs` | List network/host IOCs for an incident | `GET /api/v1/incidents/{id}/network-iocs` |
| `list_tasks` | Get incident tasks and their status | `GET /api/v1/incidents/{id}/tasks` |
| `list_artifacts` | List evidence artifacts | `GET /api/v1/incidents/{id}/artifacts` |
| `get_attack_graph` | Get attack graph nodes and edges | `GET /api/v1/incidents/{id}/attack-graph` |
| `list_case_notes` | Get analyst case notes | `GET /api/v1/incidents/{id}/notes` |

### Resources

| Resource | Description |
|----------|-------------|
| `incident://{id}` | Full incident context as a document |
| `timeline://{incident_id}` | Complete timeline as structured text |
| `attack-graph://{incident_id}` | Attack graph as DOT/Mermaid notation |

### Authentication

- MCP server authenticates to SheetStorm via a **service account JWT** stored in server config
- Service account has `mcp_service` role with read-only permissions
- JWT refresh handled internally by the MCP server

## Phase 2 — Write Tools + Enrichment (v0.2)

**Target:** 3 weeks  
**Goal:** AI can create, update, and enrich incident data

### Tools

| Tool | Description | API Endpoint |
|------|-------------|--------------|
| `create_timeline_event` | Add event to incident timeline | `POST /api/v1/incidents/{id}/events` |
| `create_case_note` | Document findings as case notes | `POST /api/v1/incidents/{id}/notes` |
| `update_incident_status` | Change incident status/phase | `PATCH /api/v1/incidents/{id}/status` |
| `create_task` | Create response tasks | `POST /api/v1/incidents/{id}/tasks` |
| `complete_task` | Mark task as complete | `PATCH /api/v1/incidents/{id}/tasks/{tid}` |
| `add_ioc` | Add IOC (network or host-based) | `POST /api/v1/incidents/{id}/network-iocs` |
| `virustotal_lookup` | Enrich hash/domain/IP via VirusTotal | `POST /api/v1/threat-intel/virustotal/lookup` |
| `misp_push` | Push IOCs to MISP platform | `POST /api/v1/threat-intel/misp/push` |
| `add_compromised_host` | Register a compromised system | `POST /api/v1/incidents/{id}/hosts` |

### Prompts

| Prompt | Description |
|--------|-------------|
| `analyze_incident` | Generate comprehensive incident analysis with recommendations |
| `generate_timeline_summary` | Produce human-readable timeline narrative |
| `suggest_mitre_mapping` | Map observed activities to MITRE ATT&CK |
| `identify_lateral_movement` | Analyze host connections for lateral movement paths |
| `draft_executive_summary` | Write executive summary from incident data |

## Phase 3 — Velociraptor Integration (v0.3)

**Target:** 4 weeks  
**Goal:** Direct forensic collection and endpoint querying through MCP

### Tools

| Tool | Description |
|------|-------------|
| `vr_list_clients` | List Velociraptor clients/endpoints |
| `vr_query_client` | Run VQL query on a specific endpoint |
| `vr_collect_artifact` | Start artifact collection on endpoint |
| `vr_get_flow_results` | Get results from a collection flow |
| `vr_hunt` | Create/manage hunts across endpoints |

### Prerequisites

- Velociraptor integration configured in SheetStorm settings
- API key with appropriate Velociraptor ACLs
- Network connectivity from MCP server → Velociraptor API

## Phase 4 — Report Generation + Advanced Analysis (v0.4)

**Target:** 3 weeks  
**Goal:** End-to-end report generation and advanced correlation

### Tools

| Tool | Description |
|------|-------------|
| `generate_report` | Create full IR report (PDF/DOCX) | 
| `correlate_iocs` | Cross-reference IOCs across incidents |
| `search_audit_logs` | Query audit trail |
| `export_incident` | Export incident as structured JSON |

### Prompts

| Prompt | Description |
|--------|-------------|
| `full_ir_report` | Generate complete incident response report |
| `lessons_learned` | Produce lessons learned document |
| `containment_checklist` | Generate containment action checklist |
| `ioc_summary` | Compile IOC list for threat sharing |

## Implementation Details

### Technology Stack

- **Runtime:** Python 3.12+ or TypeScript (Node.js 20+)
- **MCP SDK:** `@modelcontextprotocol/sdk` (TS) or `mcp` (Python)
- **Transport:** stdio (default for Claude Code), SSE for web clients
- **HTTP Client:** `httpx` (Python) or `fetch` (Node.js)
- **Config:** JSON config file for server URL, service account token

### Project Structure

```
mcp-server/
├── src/
│   ├── server.ts          # MCP server entry point
│   ├── tools/
│   │   ├── incidents.ts   # Incident CRUD tools
│   │   ├── timeline.ts    # Timeline tools
│   │   ├── enrichment.ts  # VT/MISP tools
│   │   ├── forensics.ts   # Velociraptor tools
│   │   └── reports.ts     # Report generation tools
│   ├── resources/
│   │   ├── incident.ts    # Incident resource provider
│   │   └── graph.ts       # Attack graph resource
│   ├── prompts/
│   │   ├── analysis.ts    # Analysis prompts
│   │   └── reporting.ts   # Report prompts
│   ├── api-client.ts      # SheetStorm API wrapper
│   └── config.ts          # Configuration
├── package.json
├── tsconfig.json
└── README.md
```

### Example Usage

```
User: "Show me all critical incidents from this week"

→ MCP calls list_incidents(severity="critical", since="7d")
→ Returns formatted incident list

User: "Look up hash abc123def on VirusTotal and add findings to incident INC-42"

→ MCP calls virustotal_lookup(type="hash", value="abc123def")
→ MCP calls create_case_note(incident_id="...", title="VT Lookup: abc123def", content="...")
→ Returns enrichment results
```

### Security Considerations

1. **Least Privilege:** MCP service account gets only required permissions
2. **Audit Trail:** All MCP actions logged via existing audit middleware
3. **Rate Limiting:** Inherits backend rate limits; additional MCP-level throttling
4. **Token Rotation:** Service account JWT rotated on schedule
5. **Input Validation:** All tool inputs validated before API calls
6. **Sensitive Data:** Credentials never exposed through MCP resources
7. **Network Isolation:** MCP server runs in same Docker network as backend

## Success Metrics

| Metric | Target |
|--------|--------|
| Incident analysis time | 50% reduction |
| IOC enrichment coverage | 90% automated |
| Report generation time | 80% reduction |
| Mean time to containment | 30% improvement |

## Timeline Summary

| Phase | Duration | Status |
|-------|----------|--------|
| Phase 1 — Core Read Tools | 2 weeks | 🔲 Not Started |
| Phase 2 — Write + Enrichment | 3 weeks | 🔲 Not Started |
| Phase 3 — Velociraptor | 4 weeks | 🔲 Not Started |
| Phase 4 — Reports + Advanced | 3 weeks | 🔲 Not Started |
| **Total** | **12 weeks** | |
