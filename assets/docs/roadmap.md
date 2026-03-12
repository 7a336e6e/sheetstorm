# SheetStorm — Roadmap & Project Status

## Project Status

**76 / 84** tasks completed across 15 epics.

| Epic | Status |
|------|--------|
| Critical bug fixes | ✅ 6/6 |
| Attack graph auto-linking | ✅ 2/2 |
| WebSocket real-time | ✅ 3/3 |
| Frontend features (artifacts, reports, notifications, admin) | ✅ 7/7 |
| Code quality (hooks, error boundaries, validation, stores) | ✅ 8/8 |
| Security (MFA, SSO, sanitization, rate limiting, OAuth MFA) | ✅ 6/6 |
| Backend documentation | ✅ 1/1 |
| AI reports & Google Drive | ✅ 4/4 |
| Integrations expansion (25 types, test buttons, DB config) | ✅ 4/4 |
| RBAC & team-based access control | ✅ 2/2 |
| Threat intelligence (VT, MISP, CVE, IP/domain/email, ransomware, defang) | ✅ 10/10 |
| Knowledge base (LOLBAS, Event IDs, D3FEND) | ✅ 4/4 |
| Auto-enrichment & soft fallback | ✅ 1/1 |
| MCP server (70+ tools, 5 prompts, 5 resources, OAuth, Docker) | ✅ 20/20 |
| Testing | 🔜 0/4 deferred |

---

## Roadmap

| Priority | Feature | Status |
|----------|---------|--------|
| P0 | MFA enforcement on OAuth flows (GitHub/Supabase) | ✅ Done |
| P0 | Team-based incident access restrictions | ✅ Done |
| P0 | Roles management admin page | ✅ Done |
| P1 | 22 integration types with test buttons & DB-first config | ✅ Done |
| P1 | Case notes & kill chain phase per event | ✅ Done |
| P1 | VirusTotal lookup & MISP IOC push | ✅ Done |
| P1 | MCP server for AI assistant integration (70+ tools) | ✅ Done |
| P1 | Test suite — pytest · Vitest · Playwright | 🔜 Planned |
| P1 | CI/CD — GitHub Actions | 🔜 Planned |
| P1 | CVE lookup (CISA KEV + NVD) | ✅ Done |
| P1 | IP / domain / email reputation lookups | ✅ Done |
| P1 | IOC defanging for safe sharing | ✅ Done |
| P1 | Ransomware victim lookup (ransomware.live) | ✅ Done |
| P1 | LOLBAS knowledge base | ✅ Done |
| P1 | Windows Event ID knowledge base | ✅ Done |
| P1 | MITRE D3FEND defensive countermeasure mapping | ✅ Done |
| P1 | Auto-enrichment service with soft fallback | ✅ Done |
| P2 | MITRE ATT&CK navigator heatmap | 🔜 Planned |
| P2 | Lateral movement graph visualization | 🔜 Planned |
| P2 | Incident templates (ransomware, phishing, insider threat) | 🔜 Planned |
| P3 | VERIS incident classification & reporting | 🔜 Planned |
| P3 | Dashboard analytics & MTTR charts | 🔜 Planned |
| P3 | STIX 2.1 export | 🔜 Planned |
| P3 | Activity distribution plots | 🔜 Planned |

---

## MCP Server — Detailed Tool Reference

SheetStorm includes a fully operational **Model Context Protocol (MCP) server** that enables AI assistants (Claude, Cursor, custom agents) to interact with the incident response platform through natural language.

```
AI Client  ◄──── MCP Protocol (SSE) ────►  SheetStorm MCP Server  ──── REST + JWT ────►  Flask Backend
```

### Tool Modules

| Module | Tools | Description |
|--------|-------|-------------|
| **auth** | 3 | Login, logout, session info |
| **incidents** | 7 | Full incident CRUD + search |
| **timeline** | 6 | Timeline events + MITRE tactic/technique lookup |
| **tasks** | 7 | Task management with comments |
| **assets** | 8 | Compromised hosts + accounts |
| **iocs** | 9 | Network IOCs, host IOCs, malware |
| **artifacts** | 5 | Evidence upload/download + chain of custody |
| **attack_graph** | 9 | Nodes, edges, auto-generation |
| **reports** | 3 | PDF + AI report generation |
| **admin** | 5 | Users, notifications, audit logs |
| **case_notes** | 5 | Case note CRUD |
| **threat_intel** | 7 | VT, MISP, CVE, IP/domain/email, ransomware |
| **knowledge_base** | 4 | LOLBAS, Event IDs, D3FEND |
| **defang** | 2 | IOC defanging/refanging |
| **prompts** | 5 | IR analysis templates |
| **resources** | 5 | Reference data (phases, severities, MITRE) |

**Transport:** SSE on port 8811 · **Auth:** OAuth 2.1 with Redis-backed client persistence · **Runtime:** Python 3.12 + FastMCP SDK

> See [MCP Server Roadmap](mcp-server-roadmap.md) for future phases (Velociraptor, cross-incident correlation) and architecture details.

---

## Tech Stack

| Layer          | Stack |
|----------------|-------|
| **Frontend**   | Next.js 14 · TypeScript · Tailwind CSS · Zustand · React Flow · Radix UI · Framer Motion |
| **Backend**    | Flask 3.0 · SQLAlchemy · Flask-SocketIO · Flask-JWT-Extended · WeasyPrint · pandas |
| **MCP Server** | Python 3.12 · FastMCP SDK · httpx · SSE transport · OAuth 2.1 |
| **Database**   | PostgreSQL 16 · Redis 7 |
| **AI**         | OpenAI GPT-4 · Google Gemini Pro |
| **Infra**      | Docker Compose · Nginx · S3 · Google Drive · Slack |
