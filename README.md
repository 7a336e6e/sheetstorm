<p align="center">
  <h1 align="center">⚡ SheetStorm</h1>
  <p align="center">
    <strong>Free & Open-Source Incident Response Platform</strong>
    <br />
    Track incidents, map attack paths, collaborate in real time, and generate AI-powered reports — all in one place.
    <br /><br />
    <a href="https://github.com/7a336e6e/sheetstorm/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License" /></a>
    <a href="https://github.com/7a336e6e/sheetstorm"><img src="https://img.shields.io/github/stars/7a336e6e/sheetstorm?style=social" alt="Stars" /></a>
  </p>
</p>

<br />

## Why SheetStorm?

Many security teams still coordinate incidents through shared spreadsheets. They're familiar and fast to set up — until concurrent edits collide, context gets lost, audit trails vanish, and there's zero integration with the tools responders actually need.

SheetStorm is a **free, open-source alternative** purpose-built for DFIR practitioners. It covers the full NIST incident response lifecycle and is designed to be useful whether you're a **solo analyst learning the ropes**, a **training lab instructor**, or part of an **in-house DFIR team or IR consultancy**.

```
Preparation → Identification → Containment → Eradication → Recovery → Lessons Learned
```

> SheetStorm is a DFIR **investigation tracker** - the structured replacement for the SANS incident-response spreadsheet - not a SIEM, SOAR, or SOC alert-triage platform. It doesn't aim to replace commercial SOAR platforms. It fills the gap between ad-hoc spreadsheets and heavyweight enterprise tools — giving every responder access to structured, collaborative IR for free.

## What's New

- MITRE ATT&CK suggestions now use an organization-scoped pattern model and ranked `/mitre/suggest` service.
- Tasks tab redesign adds search, status, priority, and assignee filters.
- Tasks are read-only for viewers, while task and comment deletion are administrator-only.
- Case notes enforce viewer read-only behavior, with note deletion restricted to administrators.
- Teams and organizational roles are backed by shipped migrations for `teams`, `team_members`, and user `organizational_role`.
- Stability fixes include null-safe storage analytics, IOC timeline duplicate suggestion-state cleanup, and a linearized Alembic migration chain.

---

<br />

<table>
<tr>
<td width="50%">

### 🔍 Investigate
- Track compromised hosts, accounts, and IOCs
- Map and suggest MITRE ATT&CK tactics & techniques
- Import evidence from Excel/CSV spreadsheets
- Chain of custody for forensic artifacts

</td>
<td width="50%">

### 🕸️ Visualize
- Auto-generated attack graphs from incident data
- 11 node types · 12 edge types · interactive layout
- Real-time graph sync between team members
- Export to PNG

</td>
</tr>
<tr>
<td width="50%">

### 🤖 Report
- AI-powered reports (OpenAI GPT-4 / Google Gemini)
- Executive, metrics, IOC analysis, and trend reports
- PDF generation with styled HTML
- Auto-save to Google Drive case folders

</td>
<td width="50%">

### 🛡️ Secure
- 6 RBAC roles with 40+ granular permissions
- MFA/TOTP with backup codes
- SSO configuration (SAML/OIDC)
- Fernet-encrypted credential storage
- Full audit trail

</td>
</tr>
<tr>
<td width="50%">

### 🔎 Threat Intelligence
- CVE lookup with CISA KEV + CVSS scoring
- IP, domain, email reputation lookups
- Ransomware victim search (ransomware.live)
- IOC defanging/refanging for safe sharing
- Auto-enrichment when integrations configured

</td>
<td width="50%">

### 📚 Knowledge Base
- LOLBAS — living-off-the-land binaries & scripts
- 65+ security-relevant Windows Event IDs
- MITRE D3FEND defensive countermeasures
- D3FEND ↔ ATT&CK suggestion engine

</td>
</tr>
<tr>
<td colspan="2">

### 🤖 MCP Server — AI Assistant Integration
- **70+ tools** across 17 modules for full platform control via natural language
- Claude, Cursor, and custom AI agents can query incidents, enrich IOCs, build attack graphs, and generate reports
- SSE transport with OAuth 2.1 authentication and Redis-backed client persistence
- 5 IR-focused prompt templates (incident analysis, timeline summary, MITRE mapping, lateral movement, executive summary)
- 5 reference data resources (IR phases, severities, statuses, MITRE tactics & techniques)

</td>
</tr>
</table>

---

## Quick Start

```bash
git clone https://github.com/7a336e6e/sheetstorm.git && cd sheetstorm
chmod +x start.sh && ./start.sh
```

That's it. The script generates secrets, builds 6 Docker containers, runs migrations, and seeds an admin user.

> **Local access works over plain HTTP** on `http://localhost:8080` / `http://127.0.0.1:8080`. For any other host or IP use HTTPS (see [Deployment](#deployment)).

| Service    | URL                              |
|------------|----------------------------------|
| Proxy      | http://127.0.0.1:8080            |
| Frontend   | http://127.0.0.1:3000            |
| API        | http://127.0.0.1:5000/api/v1     |
| MCP Server | http://127.0.0.1:8811/sse        |

> **Default login:** `admin@sheetstorm.local` · password in `ADMIN_PASSWORD` from `.env`

### Requirements

- Docker & Docker Compose v2
- 2 GB RAM minimum (4 GB recommended)

### Optional Integrations

Configure via environment variables in `.env` or throught the GUI in the platform:

| Integration | Purpose |
|-------------|---------|
| **OpenAI / Gemini** | AI-generated incident reports |
| **VirusTotal** | IOC and file reputation lookups |
| **MISP** | Push IOCs to a MISP instance |
| **Google Drive** | Cloud artifact storage per case |
| **Slack** | Notification webhooks |
| **S3-compatible** | External artifact storage backend |

---

## Configuration

All settings live in `.env` (copied from `.env.example`; never commit it). Highlights:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY`, `JWT_SECRET_KEY`, `FERNET_KEY` | Generated by `start.sh`; required in production |
| `CUSTODY_SIGNING_KEY` | HMAC key for chain-of-custody signatures. Generate once with `python3 -c "import secrets; print(secrets.token_hex(32))"`; do not rotate casually (see [Configuration](assets/docs/configuration.md#custody-signing-key-and-rotation)) |
| `CORS_ORIGINS`, `FRONTEND_URL` | Set to your public origin when not using localhost |
| `JWT_COOKIE_SECURE` | `true` by default in production (HTTPS only cookies) |
| `OUTBOUND_URL_ALLOWLIST` | Hosts/CIDRs self-hosted integrations (Ollama, MISP, ...) may target, e.g. `ollama,misp.internal,10.0.0.0/8` |
| `IOC_AUTO_ENRICH` | `false` by default; enables automatic third-party IOC enrichment |

The full list (AI providers, storage, SSO, MCP) is in [assets/docs/configuration.md](assets/docs/configuration.md).

## Deployment

- **HTTPS is required for non-localhost use.** Auth cookies are `Secure` in production, so logging in over `http://<lan-ip>:8080` silently fails. Terminate TLS in front of the bundled proxy (Cloudflare Tunnel, load balancer, Caddy, ...) and set `FRONTEND_URL` and `CORS_ORIGINS` to the `https://` origin. Only on a trusted network, `JWT_COOKIE_SECURE=false` allows plain HTTP.
- **Migrations run automatically.** The backend applies `flask db upgrade` on every start (with retries) and exits with an error if it fails, so a fresh `docker compose up` yields a working schema and a broken one is never served.
- **Client IPs behind a load balancer/CDN:** by default the bundled proxy trusts no forwarded-IP headers (safe for direct exposure). If you run behind Cloudflare, Traefik, an ALB, etc., set `TRUSTED_PROXY_CIDRS` and `REAL_IP_HEADER` - see [Running behind a reverse proxy / CDN](assets/docs/configuration.md#running-behind-a-reverse-proxy--cdn).
- **Back up** the `postgres_data` and `artifacts_data` volumes and your `.env` (especially `FERNET_KEY` and `CUSTODY_SIGNING_KEY`).
- **Tests:** backend tests run in Docker with `./backend/tests/run_in_docker.sh` (see [Development](assets/docs/development.md#testing)).

---

## Who Is This For?

| Use Case | How SheetStorm Helps |
|----------|----------------------|
| **Solo analyst / student** | Practice structured IR with a real tool instead of spreadsheets |
| **University / training lab** | Provide students with a multi-user IR platform at zero cost |
| **Small security team** | Coordinate response across analysts with real-time collaboration |
| **CTF / red-vs-blue exercises** | Track blue-team findings with MITRE mapping and kill-chain timelines |
| **DFIR consultancy / IR retainer** | Keep evidence, findings, and decisions for each client case organized and defensible |

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](assets/docs/architecture.md) | System design, service topology, data flow |
| [API Reference](assets/docs/api-reference.md) | REST endpoint catalogue |
| [WebSocket Events](assets/docs/websocket-events.md) | Real-time event reference |
| [Configuration](assets/docs/configuration.md) | Environment variables and settings |
| [Development](assets/docs/development.md) | Local dev setup, testing, contributing |
| [Roadmap](assets/docs/roadmap.md) | Planned features and milestones |
| [MCP Server](assets/docs/mcp-server-roadmap.md) | MCP integration details |
| [Supply-Chain Security](assets/docs/supply-chain.md) | Dependency policy (`npm ci`, no install scripts, release-age cooldown, hash-locked pip, digest-pinned images) and compromise playbook |
| [Security Policy](SECURITY.md) | How to report a vulnerability |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, Radix UI, Zustand |
| Backend | Python, Flask 3, SQLAlchemy, Flask-JWT-Extended, Flask-SocketIO |
| Database | PostgreSQL 16, Redis |
| AI | OpenAI GPT-4o, Google Gemini (configurable) |
| Infra | Docker Compose, Nginx reverse proxy |
| MCP | Model Context Protocol server (70+ tools) |

---

## Contributing

Contributions are welcome. Please open an issue to discuss significant changes before submitting a PR.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes
4. Push and open a Pull Request

Dependency changes must follow the [supply-chain policy](assets/docs/supply-chain.md). Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

---

## License

[MIT](LICENSE) — free for personal, educational, and commercial use.
