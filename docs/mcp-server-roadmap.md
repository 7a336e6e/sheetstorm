# MCP Server Roadmap — SheetStorm

## Overview

A **Model Context Protocol (MCP) server** for SheetStorm enables AI assistants (Claude Code, Cursor, custom agents) to interact with the incident response platform programmatically — querying incidents, enriching IOCs, creating timeline events, and generating reports through natural language.

## Architecture

```
┌──────────────────────┐      MCP Protocol       ┌──────────────────────┐
│  AI Client           │ ◄──────────────────────► │  SheetStorm MCP      │
│  (Claude, Cursor,    │   stdio / SSE / HTTP     │  Server              │
│   custom agents)     │                          │  (Python + FastMCP)  │
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

**Runtime:** Python 3.12+ with `mcp` SDK (FastMCP high-level API)  
**Transport:** SSE on port 8811 (proxied via nginx at `/mcp/`)  
**Deployment:** Docker container in the same compose network as the backend  

## Current Implementation Status

### Implemented Tools (70+)

The MCP server is fully operational with the following tool modules:

| Module | Tools | Status |
|--------|-------|--------|
| **auth** | `login`, `logout`, `whoami` | ✅ Complete |
| **incidents** | `list`, `get`, `create`, `update`, `update_status`, `delete`, `search` | ✅ Complete |
| **timeline** | `list`, `create`, `update`, `delete`, `list_mitre_tactics`, `list_mitre_techniques` | ✅ Complete |
| **tasks** | `list`, `get`, `create`, `update`, `delete`, `add_comment`, `list_comments` | ✅ Complete |
| **assets** | `list_hosts`, `get_host`, `create_host`, `update_host`, `delete_host`, `list_accounts`, `create_account`, `delete_account` | ✅ Complete |
| **iocs** | `list_network`, `create_network`, `delete_network`, `list_host`, `create_host`, `delete_host`, `list_malware`, `create_malware`, `delete_malware` | ✅ Complete |
| **artifacts** | `list`, `upload`, `download`, `verify_integrity`, `chain_of_custody` | ✅ Complete |
| **attack_graph** | `get_graph`, `create_node`, `update_node`, `delete_node`, `create_edge`, `delete_edge`, `auto_generate`, `list_node_types`, `list_edge_types` | ✅ Complete |
| **reports** | `list`, `generate_pdf`, `generate_ai_summary` | ✅ Complete |
| **admin** | `list_users`, `list_notifications`, `mark_notification_read`, `get_audit_logs`, `health_check` | ✅ Complete |
| **resources** | `ir_phases`, `severity_levels`, `incident_statuses`, `mitre_tactics_resource`, `mitre_techniques_resource` | ✅ Complete |
| **case_notes** | `list`, `get`, `create`, `update`, `delete` | ✅ Complete |
| **threat_intel** | `virustotal_lookup`, `misp_push_iocs`, `cve_lookup`, `ip_reputation`, `domain_reputation`, `email_reputation`, `ransomware_lookup` | ✅ Complete |
| **knowledge_base** | `kb_lolbas`, `kb_event_ids`, `kb_d3fend`, `kb_d3fend_suggest` | ✅ Complete |
| **defang** | `defang_iocs`, `refang_iocs` | ✅ Complete |

### Implemented Prompts

| Prompt | Description | Status |
|--------|-------------|--------|
| `analyze_incident` | Comprehensive incident analysis with timeline, IOCs, assets, recommendations | ✅ Complete |
| `generate_timeline_summary` | Narrative timeline summary with MITRE ATT&CK mapping | ✅ Complete |
| `suggest_mitre_mapping` | Suggest ATT&CK technique mappings for incident events | ✅ Complete |
| `identify_lateral_movement` | Analyze incident for lateral movement evidence | ✅ Complete |
| `draft_executive_summary` | Executive summary for management/stakeholders | ✅ Complete |

### Implemented Resources

| Resource | Description | Status |
|----------|-------------|--------|
| IR Phases | Incident response phases (1-6) with descriptions | ✅ Complete |
| Severity Levels | Severity level definitions | ✅ Complete |
| Incident Statuses | Valid incident status values | ✅ Complete |
| MITRE Tactics | ATT&CK tactic reference data | ✅ Complete |
| MITRE Techniques | ATT&CK technique reference data | ✅ Complete |

### Authentication

- Auto-authentication via service account credentials in environment config
- JWT token management with automatic refresh
- Credentials configured via `SHEETSTORM_EMAIL` / `SHEETSTORM_PASSWORD` env vars
- Falls back to manual `login` tool if auto-auth fails

## Project Structure

```
mcp-server/
├── sheetstorm_mcp/
│   ├── __init__.py         # Package version
│   ├── __main__.py         # Entry point
│   ├── server.py           # FastMCP server + lifespan
│   ├── client.py           # SheetStorm API client (httpx)
│   ├── config.py           # Configuration from env
│   └── tools/
│       ├── auth.py         # Authentication tools
│       ├── incidents.py    # Incident CRUD + search
│       ├── timeline.py     # Timeline event management
│       ├── tasks.py        # Task management
│       ├── assets.py       # Hosts + accounts
│       ├── iocs.py         # Network/host/malware IOCs
│       ├── artifacts.py    # Evidence artifacts + CoC
│       ├── attack_graph.py # Attack graph nodes + edges
│       ├── reports.py      # Report generation
│       ├── admin.py        # User/notification/audit admin
│       ├── resources.py    # Reference data resources
│       ├── case_notes.py   # Case notes CRUD
│       ├── threat_intel.py # VT, MISP, CVE, IP/domain/email
│       ├── knowledge_base.py # LOLBAS, Event IDs, D3FEND
│       ├── defang.py       # IOC defang/refang utilities
│       └── prompts.py      # IR analysis prompt templates
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Phase 3 — Velociraptor Integration (Future)

**Status:** Not started  
**Goal:** Direct forensic collection and endpoint querying through MCP

### Planned Tools

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

## Phase 4 — Advanced Analysis (Future)

**Status:** Not started  
**Goal:** Cross-incident correlation and advanced export capabilities

### Planned Tools

| Tool | Description |
|------|-------------|
| `correlate_iocs` | Cross-reference IOCs across incidents |
| `export_incident` | Export incident as structured JSON/STIX |
| `bulk_enrich` | Batch IOC enrichment across multiple sources |
| `search_across_incidents` | Full-text search across all incident data |

### Planned Prompts

| Prompt | Description |
|--------|-------------|
| `full_ir_report` | Generate complete incident response report |
| `lessons_learned` | Produce lessons learned document |
| `containment_checklist` | Generate containment action checklist |
| `ioc_summary` | Compile IOC list for threat sharing (STIX/CSV) |

## Security Considerations

1. **Least Privilege:** MCP service account gets only required permissions
2. **Audit Trail:** All MCP actions logged via existing audit middleware
3. **Rate Limiting:** Inherits backend rate limits; additional MCP-level throttling possible
4. **Token Rotation:** JWT auto-refreshed by the MCP client
5. **Input Validation:** All tool inputs validated before API calls
6. **Sensitive Data:** Credentials never exposed through MCP resources or tool outputs
7. **Network Isolation:** MCP server runs in same Docker network as backend
8. **Error Handling:** Generic error messages returned to clients; details logged server-side

## Success Metrics

| Metric | Target |
|--------|--------|
| Incident analysis time | 50% reduction |
| IOC enrichment coverage | 90% automated |
| Report generation time | 80% reduction |
| Mean time to containment | 30% improvement |

## Timeline Summary

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 1 — Core Read Tools | Incident, timeline, IOC, task, artifact, attack graph queries | ✅ Complete |
| Phase 2 — Write + Enrichment | Full CRUD, threat intel, knowledge base, defang, prompts | ✅ Complete |
| Phase 3 — Velociraptor | Direct endpoint forensics via Velociraptor API | 🔲 Not Started |
| Phase 4 — Advanced Analysis | Cross-incident correlation, bulk enrichment, advanced export | 🔲 Not Started |
