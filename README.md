<p align="center">
  <h1 align="center">⚡ SheetStorm</h1>
  <p align="center">
    <strong>Kill the Spreadsheet of Doom.</strong>
    <br />
    Full-stack incident response platform with attack graphs, MITRE ATT&CK, AI reports, and real-time collaboration.
    <br />
    <em>Because your IR workflow deserves better than a shared Excel file.</em>
  </p>
</p>

<p align="center">
  <a href="docs/api-reference.md">API Reference</a> ·
  <a href="docs/architecture.md">Architecture</a> ·
  <a href="docs/development.md">Development</a> ·
  <a href="docs/configuration.md">Configuration</a>
</p>

---

## What is SheetStorm?

SheetStorm replaces the infamous "Spreadsheet of Doom" — the shared Excel workbook that security teams reluctantly use during incident response — with a purpose-built platform covering the full IR lifecycle:

```
Preparation → Identification → Containment → Eradication → Recovery → Lessons Learned
```

<br />

<table>
<tr>
<td width="50%">

### 🔍 Investigate
- Track compromised hosts, accounts, and IOCs
- Map MITRE ATT&CK tactics & techniques
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
</table>

---

## Quick Start

```bash
git clone https://github.com/7a336e6e/sheetstorm.git && cd sheetstorm
chmod +x start.sh && ./start.sh
```

That's it. The script generates secrets, builds 4 Docker containers, runs migrations, and seeds an admin user.

| Service  | URL                          |
|----------|------------------------------|
| Frontend | http://127.0.0.1:3000        |
| API      | http://127.0.0.1:5000/api/v1 |

> **Default login:** `admin@sheetstorm.local` · password in `ADMIN_PASSWORD` from `.env`

---

## Tech Stack

| Layer          | Stack |
|----------------|-------|
| **Frontend**   | Next.js 14 · TypeScript · Tailwind CSS · Zustand · React Flow · Radix UI · Framer Motion |
| **Backend**    | Flask 3.0 · SQLAlchemy · Flask-SocketIO · Flask-JWT-Extended · WeasyPrint · pandas |
| **Database**   | PostgreSQL 16 · Redis 7 |
| **AI**         | OpenAI GPT-4 · Google Gemini Pro |
| **Infra**      | Docker Compose · S3 · Google Drive · Slack |

---

## Project Status

**36 / 40** tasks completed across 9 epics and 7 sprints.

| Epic | Status |
|------|--------|
| Critical bug fixes | ✅ 6/6 |
| Attack graph auto-linking | ✅ 2/2 |
| WebSocket real-time | ✅ 3/3 |
| Frontend features (artifacts, reports, notifications, admin) | ✅ 7/7 |
| Code quality (hooks, error boundaries, validation, stores) | ✅ 8/8 |
| Security (MFA, SSO, sanitization, rate limiting) | ✅ 5/5 |
| Backend documentation | ✅ 1/1 |
| AI reports & Google Drive | ✅ 4/4 |
| Testing | 🔜 0/4 deferred |

---

## Roadmap

| Priority | Feature |
|----------|---------|
| P1 | Test suite — pytest · Vitest · Playwright |
| P1 | CI/CD — GitHub Actions |
| P2 | MITRE ATT&CK navigator heatmap |
| P2 | Threat intel feed ingestion (STIX/TAXII, VirusTotal) |
| P3 | Incident templates (ransomware, phishing, insider threat) |
| P3 | Dashboard analytics & MTTR charts |
| P3 | STIX 2.1 export |

---

## Documentation

| Doc | Description |
|-----|-------------|
| [Architecture](docs/architecture.md) | System design, tech stack, project structure, design system |
| [API Reference](docs/api-reference.md) | All REST endpoints with methods and descriptions |
| [WebSocket Events](docs/websocket-events.md) | Socket.IO event payloads (client ↔ server) |
| [Configuration](docs/configuration.md) | Environment variables and database schema |
| [Development](docs/development.md) | Setup guide, useful commands, migration workflow |

---

## License

MIT — see [LICENSE](LICENSE).
