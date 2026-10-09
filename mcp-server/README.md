# SheetStorm MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that exposes the SheetStorm incident response platform as AI-accessible tools. Connect Claude Desktop, VS Code Copilot, or any MCP client to manage incidents, IOCs, attack graphs, and more — directly from your AI assistant.

## Features

- **120 tools** covering the SheetStorm API surface (incidents, timeline, leads, evidence & custody, playbooks, IOCs, attack graph, threat intel)
- **9 prompts** and **7 MCP resources** for reference data (IR phases, MITRE ATT&CK, severity levels, graph types)
- **stdio transport** for a single local user, **remote HTTP transport** (`/sse` + Streamable HTTP `/mcp`) with per-user OAuth
- Async HTTP client with header-only JWT auth, refresh-token rotation, and retries

## Quick Start

### Prerequisites

- Python 3.11+
- A running SheetStorm instance (default: `http://localhost:5000`)

### Installation

```bash
cd mcp-server
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --require-hashes --no-deps -r requirements.lock        # hash-locked, reviewed pins
pip install --require-hashes --no-deps -r build-requirements.lock  # pinned build backend (hatchling)
pip install --no-deps --no-build-isolation -e .
```

`mcp` must stay on 1.x (`>=1.30,<2`): mcp 2.x removed `mcp.server.fastmcp`.

### Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `SHEETSTORM_API_URL` | `http://localhost:5000/api/v1` | Backend API base URL |
| `MCP_TRANSPORT` | `stdio` | `stdio` (local, single user) or `sse` (remote, multi-user OAuth) |
| `SHEETSTORM_USERNAME` / `SHEETSTORM_PASSWORD` | — | **stdio only** — auto-login credentials |
| `SHEETSTORM_API_TOKEN` | — | **stdio only** — pre-issued JWT |
| `MCP_ISSUER_URL` | `http://localhost:8811` | Public URL clients reach (OAuth issuer) — sse only |
| `MCP_SSE_PORT` / `SSE_PORT` | `8811` | HTTP port — sse only |
| `REDIS_URL` | — | Persist OAuth client registrations (90-day TTL) — sse only |
| `MCP_ALLOWED_REDIRECT_HOSTS` | — | Comma-separated https hosts allowed as OAuth redirect targets besides loopback (e.g. `claude.ai,vscode.dev`) — sse only |
| `ARTIFACT_DIR` | `/tmp/sheetstorm-artifacts` | Root of per-user artifact sandboxes — sse only |

The remote transport ignores the static credentials above: every user signs
in with their own SheetStorm account through the browser OAuth flow.

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

For local stdio transport, add to `.vscode/mcp.json`:

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

## Remote server (OAuth)

With `MCP_TRANSPORT=sse` (the Docker image default) the server exposes
`/sse` and Streamable HTTP `/mcp`. Clients discover OAuth via
`/.well-known/oauth-authorization-server`, register dynamically, and open
`/sheetstorm-login` in the browser. The login page shows the requesting
client's name and the host it will redirect to and requires explicit consent.

```bash
code --add-mcp '{"name": "sheetstorm", "type": "http", "url": "https://your-domain.example.com/mcp"}'
```

Security properties of the remote transport:

- Dynamically registered redirect URIs must be loopback (`http://127.0.0.1`,
  `http://localhost`) or an https host in `MCP_ALLOWED_REDIRECT_HOSTS`.
- Each MCP request is executed as the user whose bearer token it carries; MCP
  access tokens live 1 hour, refresh tokens 30 days, pending logins 10 minutes.
  Backend refresh tokens are rotated and re-stored on every refresh; if the
  backend refuses a refresh the client is forced to sign in again.
- `sheetstorm_logout` revokes the backend tokens and the connection's MCP tokens.
- Artifact upload/download paths are relative to a private per-user directory
  `ARTIFACT_DIR/<org_id>/<user_id>/` (mode 0700; absolute paths, traversal and
  symlinks are rejected).

## Tool Categories

Run `sheetstorm-mcp` with an MCP inspector to see full descriptions. Highlights:

- **Auth (2)**: `sheetstorm_get_current_user`, `sheetstorm_logout`
- **Incidents (10)**: list/get (milestones, lead, overview summary)/create (`detected_at`, `lead_responder_id`)/update
  (IR milestones, `clear_milestones`, `expected_version`), `sheetstorm_update_incident_status`, `sheetstorm_get_dashboard_stats`,
  `sheetstorm_archive_incident`, `sheetstorm_unarchive_incident`, `sheetstorm_list_archived_incidents`,
  `sheetstorm_permanently_delete_incident` (Administrator, archived incidents only, requires `confirmation="DELETE PERMANENTLY"`)
- **Assignments (3)**: list/assign/remove responders
- **Timeline (7)**: list/create/update/delete events (`detection_time`, `confidence_level`),
  `sheetstorm_mark_timeline_event_as_ioc`, `sheetstorm_list_timeline_mitre_tactics`, `sheetstorm_list_timeline_mitre_techniques`
- **Tasks & leads (6)**: tasks with `task_type`, `lead_outcome`, `investigation_direction`, `evidence_refs`; comments
- **Compromised assets (9)**: hosts (`triage_status`, acquisition flags), accounts incl. `sheetstorm_update_account`,
  `sheetstorm_delete_account`, `sheetstorm_reveal_account_password` (one account; plaintext enters the model context)
- **IOCs (12)**: network IOCs, host IOCs, malware
- **Artifacts (7)**: list, upload (acquisition metadata), download, verify, chain of custody,
  `sheetstorm_set_legal_hold`, `sheetstorm_export_custody` (JSON)
- **Attack graph (10)**: graph, auto-generate, node/edge CRUD incl. `sheetstorm_update_graph_edge`, node/edge types
- **Case notes (5)**, **Reports (3)**, **Threat intel (7)**, **Knowledge base (6)**,
  **Advanced analysis (4)**, **Defang (2)**
- **Admin (20)**: users (list with `status`/`role`/`team_id` filters, create, update, delete: a user who
  authored records cannot be deleted, the error lists them), roles, permissions, notifications, audit logs,
  health, system status (`sheetstorm_get_system_status`), and the user lifecycle: `sheetstorm_invite_user` (returns a one-time join link, a credential),
  `sheetstorm_list_invites`, `sheetstorm_revoke_invite`, `sheetstorm_disable_user`, `sheetstorm_enable_user`,
  `sheetstorm_force_logout_user`, `sheetstorm_unlock_user`, `sheetstorm_get_user_activity`.
  Password and MFA resets are not exposed over MCP (they hand out takeover-grade secrets); use the web UI.
- **Playbooks (7)**: `sheetstorm_list_playbook_templates`, `sheetstorm_get_playbook_template`,
  `sheetstorm_activate_playbook`, `sheetstorm_get_incident_playbook`, `sheetstorm_advance_playbook_phase`,
  `sheetstorm_execute_playbook_action`, `sheetstorm_toggle_playbook_task`

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
pip install --require-hashes --no-deps -r requirements-dev.lock   # runtime + test/lint + build backend
pip install --no-deps --no-build-isolation -e .
pytest
ruff check .
ruff format .
```

## License

MIT
