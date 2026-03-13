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

SheetStorm is a **free, open-source alternative** purpose-built for DFIR practitioners. It covers the full NIST incident response lifecycle and is designed to be useful whether you're a **solo analyst learning the ropes**, a **training lab instructor**, or running an **enterprise SOC**.

```
Preparation → Identification → Containment → Eradication → Recovery → Lessons Learned
```

> SheetStorm doesn't aim to replace commercial SOAR platforms. It fills the gap between ad-hoc spreadsheets and heavyweight enterprise tools — giving every responder access to structured, collaborative IR for free.

---

## Features

### Incident Lifecycle Management

- Create and manage incidents through all six NIST IR phases
- Assign severity, classification, and responsible teams
- Track incident status with phase-aware progression
- Full audit trail on every entity change

### Investigation & Tracking

- **Compromised Hosts** — track affected systems with OS, IP, hostname, and containment status
- **Compromised Accounts** — log impacted user accounts with compromise type and reset status
- **Network IOCs** — IPs, domains, URLs, and email addresses with defang/refang support
- **Host IOCs** — file hashes, registry keys, services, scheduled tasks, and processes
- **Malware Samples** — catalogue malware with hashes, file paths, and persistence mechanisms
- **Excel / CSV Import** — bulk-import existing investigation data

### MITRE ATT&CK Integration

- Map every finding to MITRE ATT&CK tactics and techniques
- Full ATT&CK matrix browser built into the platform
- Coverage heatmap showing which techniques are observed per incident
- Form-integrated tactic/technique picker for fast tagging

### Timeline & Evidence

- **Event Timeline** — chronological record of attacker activity with kill-chain phase tagging
- **Case Notes** — rich-text analyst notes tied to each incident
- **Artifact Storage** — upload, hash-verify, and maintain chain-of-custody for evidence files
- **Google Drive Integration** — optionally sync artifacts to a shared Drive folder per case

### Threat Intelligence

- **IOC Enrichment** — IP reputation, domain reputation, and email reputation lookups
- **CVE Lookup** — search vulnerabilities by CVE ID
- **Ransomware Lookup** — check ransomware group profiles
- **VirusTotal** — optional integration for file and IOC analysis
- **Bulk Enrichment** — enrich multiple IOCs in a single operation
- **IOC Correlation** — find IOCs that appear across multiple incidents
- **Defang / Refang** — safely share IOCs in reports and chat
- **STIX Export** — export incident IOCs as STIX 2.1 bundles

### Knowledge Bases

- **MITRE ATT&CK** — full tactic and technique reference
- **MITRE D3FEND** — defensive technique suggestions mapped to observed ATT&CK techniques
- **LOLBAS** — Living Off The Land Binaries and Scripts reference
- **Windows Event IDs** — searchable log source reference for Windows forensics

### Attack Graph

- Visual node-and-edge graph of attack paths within an incident
- Drag-and-drop graph editor with configurable node and edge types
- Auto-generate graphs from existing incident data (hosts, IOCs, accounts, malware)

### AI-Powered Reports

- Generate executive summaries, technical deep-dives, and lessons-learned reports using GPT-4o or Gemini
- Export reports as styled PDF documents
- Multiple report templates (executive, technical, post-incident)

### Real-Time Collaboration

- **WebSocket-driven** live updates across all incident views
- **Incident Rooms** — join a case and see changes from other analysts instantly
- **In-app Notifications** — real-time alerts on assignments, status changes, and comments
- **Task Management** — create, assign, and track response tasks with priority and due dates
- **Task Comments** — threaded discussion on each task

### Access Control & Security

- **Role-Based Access Control** — six default roles with 40+ granular permissions (`entity:action` format)
- **Custom Roles** — create roles tailored to your organization
- **Multi-Factor Authentication** — TOTP-based MFA with QR setup
- **GitHub SSO** — authenticate via GitHub OAuth
- **JWT Authentication** — short-lived access tokens with refresh rotation
- **Redis-backed Token Blocklist** — instant session revocation
- **Rate Limiting** — per-endpoint rate limits to prevent abuse
- **Input Sanitization** — HTML/XSS stripping on all user input
- **Multi-tenancy** — organization-scoped data isolation

### MCP Server

SheetStorm ships with a **Model Context Protocol (MCP) server** exposing 70+ tools, allowing AI assistants (Claude, Copilot, etc.) to interact with your incident data programmatically — create incidents, query IOCs, run enrichments, and more, all through natural language.

### Search & Cross-Incident Analysis

- Full-text search across all incident entities (hosts, IOCs, accounts, malware, timeline, notes)
- Cross-incident IOC correlation to surface shared indicators
- Filterable, sortable tables on every entity type

---

## Quick Start

```bash
git clone https://github.com/7a336e6e/sheetstorm.git
cd sheetstorm
cp .env.example .env   # edit secrets as needed
./start.sh             # builds, migrates, seeds — all Docker
```

| Service   | URL                          |
|-----------|------------------------------|
| Frontend  | `http://localhost:8080`      |
| API       | `http://localhost:8080/api/v1` |

**Default admin:** `admin@sheetstorm.local` / value of `ADMIN_PASSWORD` in `.env` (default `changeme`).

### Requirements

- Docker & Docker Compose v2
- 2 GB RAM minimum (4 GB recommended)

### Optional Integrations

Configure via environment variables in `.env`:

| Integration | Purpose |
|-------------|---------|
| **OpenAI / Gemini** | AI-generated incident reports |
| **VirusTotal** | IOC and file reputation lookups |
| **MISP** | Push IOCs to a MISP instance |
| **Google Drive** | Cloud artifact storage per case |
| **Slack** | Notification webhooks |
| **S3-compatible** | External artifact storage backend |

---

## Who Is This For?

| Use Case | How SheetStorm Helps |
|----------|----------------------|
| **Solo analyst / student** | Practice structured IR with a real tool instead of spreadsheets |
| **University / training lab** | Provide students with a multi-user IR platform at zero cost |
| **Small security team** | Coordinate response across analysts with real-time collaboration |
| **CTF / red-vs-blue exercises** | Track blue-team findings with MITRE mapping and kill-chain timelines |
| **Enterprise SOC (lightweight)** | Quick stand-up for overflow incidents or teams evaluating IR tooling |

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

---

## License

[MIT](LICENSE) — free for personal, educational, and commercial use.
