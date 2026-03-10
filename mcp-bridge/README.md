# SheetStorm MCP Bridge

A **local stdio MCP bridge** that lets Claude Desktop (including the free plan) connect to a remote SheetStorm backend. Inspired by [mcp-velociraptor](https://github.com/mgreen27/mcp-velociraptor).

## Why?

Claude Desktop's free plan doesn't support remote MCP servers (OAuth/SSE). This bridge runs as a **local Python process** using stdio transport, proxying all tool calls directly to the SheetStorm REST API.

```
Claude Desktop ←→ stdio ←→ sheetstorm-bridge ←→ HTTPS ←→ SheetStorm Backend
```

## Features

- **~65 tools** covering the full SheetStorm IR workflow
- **9 structured prompts** for incident analysis, reporting, and threat intel
- **7 MCP resources** for reference data (IR phases, MITRE ATT&CK, severity levels)
- Auto-authenticates on startup (username/password or API token)
- Auto-refreshes expired JWT tokens
- Retry with exponential backoff for transient errors

## Quick Start

### 1. Install

```bash
cd mcp-bridge
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```ini
# SheetStorm backend URL (no trailing slash)
SHEETSTORM_API_URL=https://your-sheetstorm-instance.com/api/v1

# Option A: Username/password (will auto-login)
SHEETSTORM_USERNAME=admin@sheetstorm.local
SHEETSTORM_PASSWORD=changeme

# Option B: Pre-existing API token (skip login)
# SHEETSTORM_API_TOKEN=your-jwt-token-here

# Optional
# SHEETSTORM_LOG_LEVEL=INFO
```

### 3. Test

Verify it starts correctly:

```bash
python -m sheetstorm_bridge
```

You should see it connect and authenticate. Press `Ctrl+C` to stop.

### 4. Configure Claude Desktop

Add to your Claude Desktop config file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "sheetstorm": {
      "command": "/absolute/path/to/mcp-bridge/.venv/bin/python",
      "args": ["-m", "sheetstorm_bridge"],
      "env": {
        "SHEETSTORM_API_URL": "https://your-sheetstorm-instance.com/api/v1",
        "SHEETSTORM_USERNAME": "admin@sheetstorm.local",
        "SHEETSTORM_PASSWORD": "changeme"
      }
    }
  }
}
```

> **Tip**: You can pass credentials via `env` in the config (as shown above) instead of using a `.env` file. The `env` block takes precedence.

### 5. Restart Claude Desktop

Restart Claude Desktop. You should see "sheetstorm" appear in the MCP server list with all tools available.

## Tool Categories

| Category | Tools | Description |
|----------|-------|-------------|
| Auth | 2 | Get current user, logout |
| Incidents | 6 | CRUD, status updates, search |
| Timeline | 6 | Event management, MITRE tactics/techniques |
| Tasks | 6 | Task management, comments |
| Assets | 7 | Compromised hosts, accounts |
| IOCs | 12 | Network IOCs, host IOCs, malware |
| Artifacts | 5 | Upload, download, verify, chain of custody |
| Attack Graph | 10 | Nodes, edges, auto-generation |
| Case Notes | 5 | Investigator notes |
| Reports | 3 | PDF and AI-generated reports |
| Admin | 9 | Users, notifications, audit logs, health |
| Threat Intel | 7 | VirusTotal, MISP, CVE, reputation |
| Knowledge Base | 7 | LOLBAS, event IDs, D3FEND, MITRE |
| Advanced | 4 | Search, correlate, STIX export, bulk enrich |
| Defang | 2 | Defang/refang IOCs |

## Architecture

```
mcp-bridge/
├── pyproject.toml          # Package definition
├── requirements.txt
├── .env.example
├── README.md
└── sheetstorm_bridge/
    ├── __init__.py
    ├── __main__.py         # Entry point
    ├── config.py           # Environment config
    ├── client.py           # HTTP client (httpx)
    ├── server.py           # FastMCP server + lifespan
    └── tools/
        ├── auth.py
        ├── incidents.py
        ├── timeline.py
        ├── tasks.py
        ├── assets.py
        ├── iocs.py
        ├── artifacts.py
        ├── attack_graph.py
        ├── case_notes.py
        ├── reports.py
        ├── admin.py
        ├── threat_intel.py
        ├── knowledge_base.py
        ├── advanced_analysis.py
        ├── defang.py
        ├── resources.py    # MCP resources
        └── prompts.py      # MCP prompts
```

## Troubleshooting

**"No credentials configured"**: Set either `SHEETSTORM_API_TOKEN` or both `SHEETSTORM_USERNAME` + `SHEETSTORM_PASSWORD`.

**Authentication failures**: Verify your credentials work by logging into the SheetStorm web UI. Check the API URL includes `/api/v1`.

**Connection errors**: Ensure the SheetStorm backend is reachable from your machine. Test with `curl $SHEETSTORM_API_URL/health`.

**Claude Desktop doesn't show tools**: Check the config JSON syntax. Ensure the Python path is absolute. Check Claude Desktop logs for errors.

## License

Same as SheetStorm — see the project root LICENSE file.
