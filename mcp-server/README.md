# SheetStorm MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that exposes the SheetStorm incident response platform as AI-accessible tools. Connect Claude Desktop, VS Code Copilot, or any MCP client to manage incidents, IOCs, attack graphs, and more — directly from your AI assistant.

## Features

- **50+ tools** covering the full SheetStorm API surface
- **8 MCP resources** for reference data (MITRE ATT&CK, IR phases, severity levels, etc.)
- **Async HTTP client** with JWT auth, auto-refresh, and retry logic
- **stdio & SSE transports** — works with Claude Desktop, VS Code, and remote clients

## Quick Start

### Prerequisites

- Python 3.11+
- A running SheetStorm instance (default: `http://localhost:5000`)

### Installation

```bash
cd mcp-server
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

### Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `SHEETSTORM_API_URL` | `http://localhost:5000/api/v1` | Backend API base URL |
| `SHEETSTORM_USERNAME` | — | Auto-login username |
| `SHEETSTORM_PASSWORD` | — | Auto-login password |
| `SHEETSTORM_API_TOKEN` | — | Pre-existing JWT token |
| `MCP_TRANSPORT` | `stdio` | Transport: `stdio` or `sse` |

### Run

```bash
# stdio transport (default — for Claude Desktop / VS Code)
sheetstorm-mcp

# SSE transport (for remote clients)
MCP_TRANSPORT=sse sheetstorm-mcp
```

## Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sheetstorm": {
      "command": "/path/to/mcp-server/.venv/bin/sheetstorm-mcp",
      "env": {
        "SHEETSTORM_API_URL": "http://localhost:5000/api/v1",
        "SHEETSTORM_USERNAME": "admin@sheetstorm.local",
        "SHEETSTORM_PASSWORD": "changeme"
      }
    }
  }
}
```

## VS Code Configuration

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "sheetstorm": {
      "command": "${workspaceFolder}/mcp-server/.venv/bin/sheetstorm-mcp",
      "env": {
        "SHEETSTORM_API_URL": "http://localhost:5000/api/v1",
        "SHEETSTORM_USERNAME": "admin@sheetstorm.local",
        "SHEETSTORM_PASSWORD": "changeme"
      }
    }
  }
}
```

## Tool Categories

### Authentication (3 tools)
- `sheetstorm_login` — Authenticate with credentials
- `sheetstorm_get_current_user` — Get current user profile
- `sheetstorm_logout` — Invalidate session

### Incidents (6 tools)
- `sheetstorm_list_incidents` — List/filter incidents
- `sheetstorm_get_incident` — Get incident details
- `sheetstorm_create_incident` — Create new incident
- `sheetstorm_update_incident` — Update incident fields
- `sheetstorm_update_incident_status` — Change incident status/phase
- `sheetstorm_delete_incident` — Delete incident

### Timeline (6 tools)
- `sheetstorm_list_timeline_events` — List timeline events
- `sheetstorm_create_timeline_event` — Add timeline event
- `sheetstorm_update_timeline_event` — Update timeline event
- `sheetstorm_delete_timeline_event` — Delete timeline event
- `sheetstorm_get_mitre_tactics` — List MITRE ATT&CK tactics
- `sheetstorm_get_mitre_techniques` — List MITRE techniques by tactic

### Tasks (6 tools)
- `sheetstorm_list_tasks` — List incident tasks
- `sheetstorm_create_task` — Create task
- `sheetstorm_update_task` — Update task
- `sheetstorm_delete_task` — Delete task
- `sheetstorm_add_task_comment` — Add task comment
- `sheetstorm_list_task_comments` — List task comments

### Compromised Assets (8 tools)
- `sheetstorm_list_hosts` / `sheetstorm_add_host` / `sheetstorm_update_host` / `sheetstorm_delete_host`
- `sheetstorm_list_accounts` / `sheetstorm_add_account` / `sheetstorm_reveal_account_password`

### IOCs (12 tools)
- Network IOCs: `sheetstorm_list_network_iocs` / `sheetstorm_add_network_ioc` / `sheetstorm_update_network_ioc` / `sheetstorm_delete_network_ioc`
- Host IOCs: `sheetstorm_list_host_iocs` / `sheetstorm_add_host_ioc` / `sheetstorm_update_host_ioc` / `sheetstorm_delete_host_ioc`
- Malware: `sheetstorm_list_malware` / `sheetstorm_add_malware` / `sheetstorm_update_malware` / `sheetstorm_delete_malware`

### Artifacts (5 tools)
- `sheetstorm_list_artifacts` — List evidence files
- `sheetstorm_upload_artifact` — Upload evidence
- `sheetstorm_verify_artifact` — Verify integrity
- `sheetstorm_get_chain_of_custody` — View custody chain
- `sheetstorm_download_artifact` — Download evidence file

### Attack Graph (10 tools)
- `sheetstorm_get_attack_graph` — Full graph view
- `sheetstorm_auto_generate_graph` — Auto-generate from data
- Nodes: `sheetstorm_add_graph_node` / `sheetstorm_update_graph_node` / `sheetstorm_delete_graph_node`
- Edges: `sheetstorm_add_graph_edge` / `sheetstorm_delete_graph_edge`
- Reference: `sheetstorm_get_node_types` / `sheetstorm_get_edge_types`

### Reports (3 tools)
- `sheetstorm_list_reports` — List reports
- `sheetstorm_generate_pdf_report` — Generate PDF
- `sheetstorm_generate_ai_report` — AI-generated report

### Admin (9 tools)
- Users: `sheetstorm_list_users` / `sheetstorm_create_user` / `sheetstorm_update_user` / `sheetstorm_delete_user`
- Notifications: `sheetstorm_list_notifications` / `sheetstorm_mark_notification_read` / `sheetstorm_mark_all_notifications_read`
- `sheetstorm_get_audit_logs` — Audit trail
- `sheetstorm_health_check` — API health

## Resources

| URI | Description |
|-----|-------------|
| `sheetstorm://reference/ir-phases` | NIST IR lifecycle phases |
| `sheetstorm://reference/severity-levels` | Severity level definitions |
| `sheetstorm://reference/incident-statuses` | Valid incident statuses |
| `sheetstorm://reference/mitre-tactics` | MITRE ATT&CK tactics |
| `sheetstorm://reference/mitre-techniques` | MITRE ATT&CK techniques |
| `sheetstorm://reference/node-types` | Attack graph node types |
| `sheetstorm://reference/edge-types` | Attack graph edge types |

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
ruff format .
```

## License

MIT
