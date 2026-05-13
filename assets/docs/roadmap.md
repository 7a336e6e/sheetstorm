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
| P1 | MCP server for AI assistant integration (70+ tools) | ✅ Done |
| P1 | MITRE ATT&CK pattern model, suggest service & seed data | ✅ Done |
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

| NIST Phase | Capability |
|------------|------------|
| Preparation | Runbooks library tied to incident type and NIST phase; playbook automation templates; on-call rotations and escalation ownership. |
| Identification | SIEM/EDR connectors (Splunk, Elastic, CrowdStrike, Sentinel); alert triage queue; MITRE coverage heatmap based on mapped timeline events and patterns. |
| Containment | Response action audit trail; SOAR-style orchestration hooks; ticket handoff model for responder tasks. |
| Eradication | IOC sweep automation against imported indicators; threat-hunting query library mapped to ATT&CK techniques. |
| Recovery | Restoration checklists; post-containment validation steps; evidence-backed recovery signoff. |
| Lessons Learned | MTTD/MTTR dashboards from incident timestamps; expanded AI post-incident report workflow with reviewer edits. |

### Soon — Planned

| NIST Phase | Capability |
|------------|------------|
| Preparation | Asset inventory sync (hosts, services, cloud accounts, ownership metadata); tabletop-exercise mode for training incidents. |
| Identification | Detection-as-code storage and review; normalized alert evidence from connectors; MITRE coverage heatmap gaps by tactic and technique. |
| Containment | EDR isolation API actions; Jira and ServiceNow ticketing integration; containment approval and rollback records. |
| Eradication | Sandbox integration for suspicious files and URLs; reusable threat-hunting query packs; recurring IOC sweep jobs. |
| Recovery | Communications templates (internal, legal, customer, executive); service restoration checklists by asset class. |
| Lessons Learned | Cross-incident trend analytics; recurring findings, control gaps, and technique frequency summaries. |

### Later — Enterprise Grade

| NIST Phase | Direction |
|------------|-----------|
| Preparation | Mature runbook governance, approval workflows, environment-aware playbooks, asset ownership reconciliation, and exercise scoring. |
| Identification | High-volume connector ingestion, alert correlation, deduplication, detection coverage reporting, and ATT&CK heatmap rollups across teams. |
| Containment | SOAR action execution with approvals, responder accountability, EDR isolation workflows, and external ticket lifecycle sync. |
| Eradication | Fleet-wide IOC sweeps, sandbox verdict ingestion, hunt query execution history, and remediation evidence tracking. |
| Recovery | Recovery validation evidence, communications audit trail, business service dependency checks, and controlled return-to-service workflows. |
| Lessons Learned | Executive-ready metrics, MTTD/MTTR baselines, cross-incident trend analytics, and control-improvement tracking. |

#### Cross-cutting Enterprise

| Area | Capability |
|------|------------|
| Identity | SSO/SAML/OIDC, SCIM provisioning, granular RBAC, and custom roles. |
| Tenant security | Multi-tenant isolation hardening and per-tenant encryption. |
| Audit | Audit log export to SIEM. |
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
