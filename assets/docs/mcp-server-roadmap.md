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

### Implemented Tools (143)

143 tools in 22 modules (`@mcp.tool` in `sheetstorm_mcp/tools/*.py`; tool names carry the `sheetstorm_` prefix, omitted below). `mcp-bridge` exposes the same set.

| Module | Tools | Scope |
|--------|-------|-------|
| **auth** (2) | `get_current_user`, `logout` | Session |
| **incidents** (10) | `list_incidents`, `get_incident`, `create_incident`, `update_incident`, `update_incident_status`, `archive_incident`, `list_archived_incidents`, `unarchive_incident`, `permanently_delete_incident`, `get_dashboard_stats` | Incidents, archive/purge, dashboard |
| **assignments** (3) | `list_assignments`, `assign_user`, `remove_assignment` | Incident assignments |
| **timeline** (7) | `list_timeline_events`, `create_timeline_event`, `update_timeline_event`, `delete_timeline_event`, `mark_timeline_event_as_ioc`, `list_timeline_mitre_tactics`, `list_timeline_mitre_techniques` | Timeline events (+ provenance) |
| **tasks** (7) | `list_tasks`, `list_leads`, `create_task`, `update_task`, `delete_task`, `add_task_comment`, `list_task_comments` | Tasks and leads |
| **assets** (10) | `list_hosts`, `add_host`, `update_host`, `bulk_update_hosts`, `delete_host`, `list_accounts`, `add_account`, `update_account`, `delete_account`, `reveal_account_password` | Hosts and accounts |
| **iocs** (12) | `list_network_iocs`, `add_network_ioc`, `update_network_ioc`, `delete_network_ioc`, `list_host_iocs`, `add_host_ioc`, `update_host_ioc`, `delete_host_ioc`, `list_malware`, `add_malware`, `update_malware`, `delete_malware` | Network/host IOCs and malware (+ provenance) |
| **artifacts** (7) | `list_artifacts`, `upload_artifact`, `verify_artifact`, `get_chain_of_custody`, `set_legal_hold`, `export_custody`, `download_artifact` | Artifacts, custody, legal hold |
| **evidence** (5) | `list_evidence`, `get_evidence`, `register_evidence`, `transfer_evidence`, `verify_evidence_chain` | Evidence register and custody chain |
| **attack_graph** (10) | `get_attack_graph`, `auto_generate_graph`, `add_graph_node`, `update_graph_node`, `delete_graph_node`, `add_graph_edge`, `update_graph_edge`, `delete_graph_edge`, `get_node_types`, `get_edge_types` | Attack graph (merge/replace auto-generate) |
| **case_notes** (5) | `list_case_notes`, `get_case_note`, `create_case_note`, `update_case_note`, `delete_case_note` | Case notes |
| **playbooks** (7) | `list_playbook_templates`, `get_playbook_template`, `activate_playbook`, `get_incident_playbook`, `advance_playbook_phase`, `execute_playbook_action`, `toggle_playbook_task` | Playbooks (org + built-in) |
| **questions** (4) | `list_open_questions`, `answer_question`, `add_question`, `get_question_report` | Investigative questions |
| **case_templates** (2) | `list_case_templates`, `apply_case_template` | Case templates |
| **metrics** (3) | `get_incident_metrics`, `list_improvement_actions`, `add_improvement_action` | Response metrics and improvement actions |
| **decisions** (5) | `log_decision`, `list_decisions`, `log_response_action`, `list_response_actions`, `update_action_verification` | Decision & response-action log (no approve/authorize, no privileged) |
| **reports** (3) | `list_reports`, `generate_pdf_report`, `generate_ai_report` | Reports and snapshots |
| **admin** (21) | `list_users`, `create_user`, `list_roles`, `list_permissions`, `update_user`, `delete_user`, `invite_user`, `list_invites`, `revoke_invite`, `disable_user`, `enable_user`, `force_logout_user`, `unlock_user`, `get_user_activity`, `list_notifications`, `mark_notification_read`, `mark_all_notifications_read`, `get_audit_logs`, `get_system_status`, `get_security_policy`, `health_check` | Users, invites, notifications, audit, system status, security policy |
| **threat_intel** (7) | `virustotal_lookup`, `misp_push_iocs`, `cve_lookup`, `ip_reputation`, `domain_reputation`, `email_reputation`, `ransomware_lookup` | Threat intel lookups, MISP |
| **knowledge_base** (6) | `kb_lolbas`, `kb_event_ids`, `kb_d3fend`, `kb_d3fend_suggest`, `get_mitre_tactics`, `get_mitre_techniques` | LOLBAS, Event IDs, D3FEND, MITRE |
| **advanced_analysis** (5) | `search`, `correlate_iocs`, `export_stix`, `export_csv`, `bulk_enrich` | Search, correlation, STIX/CSV export, bulk enrich |
| **defang** (2) | `defang_iocs`, `refang_iocs` | IOC defang/refang |

### Implemented Prompts (9)

| Prompt | Status |
|--------|--------|
| `analyze_incident` | ✅ Complete |
| `generate_timeline_summary` | ✅ Complete |
| `suggest_mitre_mapping` | ✅ Complete |
| `identify_lateral_movement` | ✅ Complete |
| `draft_executive_summary` | ✅ Complete |
| `full_ir_report` | ✅ Complete |
| `lessons_learned` | ✅ Complete |
| `containment_checklist` | ✅ Complete |
| `ioc_summary` | ✅ Complete |

### Implemented Resources (7)

| Resource function | Status |
|-------------------|--------|
| `get_ir_phases` | ✅ Complete |
| `get_severity_levels` | ✅ Complete |
| `get_incident_statuses` | ✅ Complete |
| `get_mitre_tactics_resource` | ✅ Complete |
| `get_mitre_techniques_resource` | ✅ Complete |
| `get_graph_node_types_resource` | ✅ Complete |
| `get_graph_edge_types_resource` | ✅ Complete |

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
│       ├── _provenance.py
│       ├── admin.py
│       ├── advanced_analysis.py
│       ├── artifacts.py
│       ├── assets.py
│       ├── assignments.py
│       ├── attack_graph.py
│       ├── auth.py
│       ├── case_notes.py
│       ├── case_templates.py
│       ├── defang.py
│       ├── evidence.py
│       ├── incidents.py
│       ├── iocs.py
│       ├── knowledge_base.py
│       ├── metrics.py
│       ├── playbooks.py
│       ├── prompts.py
│       ├── questions.py
│       ├── reports.py
│       ├── resources.py
│       ├── tasks.py
│       ├── threat_intel.py
│       └── timeline.py
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

## Phase 4 — Advanced Analysis

**Status:** Delivered (`advanced_analysis` module and the prompts above): `sheetstorm_search`, `sheetstorm_correlate_iocs`, `sheetstorm_export_stix`, `sheetstorm_export_csv`, `sheetstorm_bulk_enrich`. The tables below are the original plan.  
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
| Phase 4 — Advanced Analysis | Cross-incident correlation, bulk enrichment, advanced export | ✅ Complete |
