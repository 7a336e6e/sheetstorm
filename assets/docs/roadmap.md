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
| MCP server (133 tools, 9 prompts, 7 resources, OAuth, Docker) | ✅ 20/20 |
| Testing | 🔜 0/4 deferred |

---

## What's New

- **MITRE ATT&CK pattern suggestions** — backend model, migration, seed data, and suggest service; auto-recommends patterns from timeline events
- **Tasks tab redesign** — status filters, role-based controls: viewers read-only, admin-only delete
- **Notes hardening** — viewer role is read-only across all notes; admin-only delete enforced
- **Teams & org roles** — team membership and organizational role support added via migration
- **Storage tab crash fix** — null-safe handling prevents crash on empty artifact lists
- **IOC timeline deduplication** — duplicate suggestion entries removed
- **Migration chain linearized** — `down_revision` chained correctly; single Alembic head guaranteed

---

## Feature Roadmap

| Priority | Feature | Status |
|----------|---------|--------|
| P0 | MFA enforcement on OAuth flows (GitHub/Supabase) | ✅ Done |
| P0 | Team-based incident access restrictions | ✅ Done |
| P0 | Roles management admin page | ✅ Done |
| P1 | 22 integration types with test buttons & DB-first config | ✅ Done |
| P1 | Case notes & kill chain phase per event | ✅ Done |
| P1 | VirusTotal lookup & MISP IOC push | ✅ Done |
| P1 | MCP server for AI assistant integration (133 tools) | ✅ Done |
| P1 | MITRE ATT&CK pattern model, suggest service & seed data | ✅ Done |
| P1 | Test suite — pytest (started) · Vitest · Playwright | 🚧 In progress |
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
| P1 | Evidence register (incl. non-uploaded evidence) with external custody transfers | 🔜 Planned |
| P1 | Tamper-evident, signed chain-of-custody ledger | 🔜 Planned |
| P1 | Investigative questions board linked to findings | 🔜 Planned |
| P1 | Finding & timestamp provenance (source, tool, timezone, confidence) | 🔜 Planned |
| P1 | Decision & response-action log | 🔜 Planned |
| P2 | Case templates (ransomware, BEC, insider threat, cloud compromise) | 🚧 Backend, API and MCP shipped (generic intrusion + ransomware); UI and remaining templates in progress |
| P3 | VERIS incident classification & reporting | 🔜 Planned |
| P2 | Global search UI across incidents, IOCs, notes, and evidence | 🔜 Planned |
| P2 | Real-time collaboration (presence, conflict-safe concurrent edits) | 🔜 Planned |
| P2 | Report builder (section-level templates, reviewer edits) | 🔜 Planned |
| P2 | Notification-obligation tracker (regulatory/contractual deadlines) | 🔜 Planned |
| P2 | Admin guardrails: user lifecycle, security policy, API keys, audit governance | 🔜 Planned |
| P3 | STIX 2.1 export | 🔜 Planned |
| P3 | Activity distribution plots | 🔜 Planned |

---

## NIST IR Lifecycle Roadmap

Capabilities mapped to the NIST incident response lifecycle phases across four delivery horizons.

### Now — Shipped

| NIST Phase | Working Today |
|------------|---------------|
| Preparation | RBAC roles and permissions, MFA/TOTP, SSO provider configuration, audit logging, teams, team membership, organizational roles, and NIST phase guidance in the incident UI. |
| Identification | Incident intake, severity/status/phase tracking, timeline events, compromised hosts/accounts, network IOCs, host IOCs, malware/tools, MITRE ATT&CK mapping, MITRE auto-suggestions, ATT&CK/D3FEND reference data, and attack graph generation. |
| Containment | Host containment status, compromised account status, response tasks by phase, task comments, linked task entities, administrator-only destructive actions, and audited state changes. |
| Eradication | Malware/tool records, remediated host-based IOCs, MITRE/D3FEND countermeasure references, evidence artifacts, and task-driven cleanup tracking. |
| Recovery | Incident status-to-phase sync, contained/eradicated/recovered/closed timestamps, artifact verification, chain of custody, PDF reports, and recovery guidance in the phase tracker. |
| Lessons Learned | Lessons-learned fields, case notes, AI incident summaries, PDF incident reports, recommendation sections, and report types. AI post-incident reporting is partially shipped through the current report pipeline. |

### Next — Prioritized

SheetStorm is a DFIR **investigation tracker** (the structured replacement for the SANS incident-response spreadsheet), not a SOC alert platform. Roadmap items focus on evidence, findings, decisions, and defensible reporting rather than alert ingestion or triage queues.

| NIST Phase | Capability |
|------------|------------|
| Preparation | Case templates (ransomware, BEC, insider threat, cloud compromise) that pre-seed tasks, investigative questions, and evidence checklists; admin guardrails (user lifecycle, security policy, API keys, audit governance). |
| Identification | Evidence register that also covers non-uploaded evidence (physical media, remote collections, third-party-held data); investigative questions board linking each question to supporting and refuting findings; finding and timestamp provenance (source artifact, tool, timezone, confidence). |
| Containment | Decision & response-action log (what was decided, by whom, rationale, outcome, rollback); external custody transfers (counsel, vendors, law enforcement) with receipts. |
| Eradication | Evidence-backed remediation verification per host and account; links from remediation steps to the findings that justify them. |
| Recovery | Evidence-backed recovery signoff; restoration and validation checklists tied to affected assets. |
| Lessons Learned | Report builder with section templates and reviewer edits; notification-obligation tracker (regulatory and contractual deadlines, who was notified and when). |

### Soon — Planned

| NIST Phase | Capability |
|------------|------------|
| Preparation | Tamper-evident custody ledger (hash-chained, HMAC-signed entries with verification and export); runbook library tied to incident type and NIST phase. |
| Identification | Global search UI across incidents, IOCs, notes, timeline events, and evidence; real-time collaboration (presence, conflict-safe concurrent edits). |
| Containment | Containment approval and rollback records; responder accountability on actions. |
| Eradication | Reusable hunt-note library mapped to ATT&CK techniques; sandbox verdict attachment to evidence. |
| Recovery | Communications templates (internal, legal, customer, executive) with an audit trail. |
| Lessons Learned | Cross-case trend summaries (recurring findings, control gaps, technique frequency). |

### Later — Enterprise Grade

| NIST Phase | Direction |
|------------|-----------|
| Preparation | Mature runbook governance, approval workflows, tabletop-exercise mode, and exercise scoring. |
| Identification | Cross-case technique rollups and ATT&CK heatmaps across teams; provenance verification when importing third-party collections. |
| Containment | Approval workflows for response actions and external ticket handoff for responder tasks. |
| Eradication | Remediation evidence tracking across large environments. |
| Recovery | Recovery validation evidence, communications audit trail, and controlled return-to-service records. |
| Lessons Learned | Executive-ready case metrics and control-improvement tracking. |

#### Cross-cutting Enterprise

| Area | Capability |
|------|------------|
| Identity | SSO/SAML/OIDC, SCIM provisioning, granular RBAC, and custom roles. |
| Tenant security | Multi-tenant isolation hardening and per-tenant encryption. |
| Audit | Audit governance: retention policy, tamper-evident export, and reviewer sign-off. |
| Compliance | SOC2, ISO 27001, and HIPAA compliance posture. |
| Availability | HA deployment: HA Postgres, Redis Sentinel, multi-replica API. |
| Edge security | Rate limiting, WAF, and Vault secrets management. |
| Performance | Large-incident pagination and async background workers. |
| Observability | OpenTelemetry traces, structured JSON logs, and alerting. |

---

## MCP Server — Detailed Tool Reference

SheetStorm includes a fully operational **Model Context Protocol (MCP) server** that enables AI assistants (Claude, Cursor, custom agents) to interact with the incident response platform through natural language.

```
AI Client  ◄──── MCP Protocol (SSE) ────►  SheetStorm MCP Server  ──── REST + JWT ────►  Flask Backend
```

### Tool Modules

| Module | Tools | Description |
|--------|-------|-------------|
| **auth** | 2 | Current user, logout |
| **incidents** | 10 | Incident CRUD, milestones, status, dashboard stats, archive, permanent delete |
| **assignments** | 3 | Assign / unassign responders |
| **timeline** | 7 | Timeline events, mark as IOC, MITRE tactic/technique lookup |
| **tasks** | 7 | Tasks and investigative leads with evidence refs, lead queue, comments |
| **assets** | 10 | Compromised hosts (triage, bulk update) + accounts |
| **iocs** | 12 | Network IOCs, host IOCs, malware |
| **artifacts** | 7 | Evidence upload/download, verify, chain of custody, legal hold, custody export |
| **evidence** | 5 | Evidence register, custody transfers, ledger verification |
| **attack_graph** | 10 | Nodes, edges, auto-generation, node/edge types |
| **case_notes** | 5 | Case note CRUD |
| **playbooks** | 7 | Templates (incl. built-in `builtin:<key>`), activation, phases, actions, tasks |
| **questions** | 4 | Investigative questions: list open, answer with evidence, add, report data |
| **case_templates** | 2 | List templates, apply a template to an incident |
| **reports** | 3 | PDF + AI report generation |
| **admin** | 20 | Users and lifecycle, roles, permissions, notifications, audit logs, health, system status |
| **threat_intel** | 7 | VT, MISP, CVE, IP/domain/email, ransomware |
| **knowledge_base** | 6 | LOLBAS, Event IDs, D3FEND, MITRE ATT&CK |
| **advanced_analysis** | 4 | Search, correlation, STIX export, bulk enrich |
| **defang** | 2 | IOC defanging/refanging |
| **prompts** | 9 | IR analysis templates |
| **resources** | 7 | Reference data (phases, severities, statuses, MITRE, graph types) |

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
