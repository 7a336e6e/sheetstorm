# Roadmap

## Now — Shipped

SheetStorm already covers the core incident workspace: incident records, lifecycle phase tracking, evidence, IOCs, tasks, notes, MITRE mapping, reporting, RBAC, audit logs, and team scoping.

| NIST phase | Working today |
|------------|---------------|
| Preparation | RBAC roles and permissions, MFA/TOTP, SSO provider configuration, audit logging, teams, team membership, organizational roles, and NIST phase guidance in the incident UI. |
| Identification | Incident intake, severity/status/phase tracking, timeline events, compromised hosts/accounts, network IOCs, host IOCs, malware/tools, MITRE ATT&CK mapping, MITRE auto-suggestions, ATT&CK/D3FEND reference data, and attack graph generation. |
| Containment | Host containment status, compromised account status, response tasks by phase, task comments, linked task entities, administrator-only destructive actions, and audited state changes. |
| Eradication | Malware/tool records, remediated host-based IOCs, MITRE/D3FEND countermeasure references, evidence artifacts, and task-driven cleanup tracking. |
| Recovery | Incident status-to-phase sync, contained/eradicated/recovered/closed timestamps, artifact verification, chain of custody, PDF reports, and recovery guidance in the phase tracker. |
| Lessons Learned | Lessons-learned fields, case notes, AI incident summaries, PDF incident reports, recommendation sections, and trend/report types. AI post-incident reporting is partially shipped through the current report pipeline. |

## Next — In Progress / Prioritized

| NIST phase | Prioritized capability |
|------------|------------------------|
| Preparation | Runbooks library tied to incident type and NIST phase; playbook automation templates; on-call rotations and escalation ownership. |
| Identification | SIEM/EDR connectors for Splunk, Elastic, CrowdStrike, and Microsoft Sentinel; alert triage queue; MITRE coverage heatmap based on mapped timeline events and patterns. |
| Containment | Response action audit trail for containment decisions; SOAR-style orchestration hooks; ticket handoff model for responder tasks. |
| Eradication | IOC sweep automation against imported indicators; threat-hunting query library mapped to ATT&CK techniques. |
| Recovery | Restoration checklists; post-containment validation steps; evidence-backed recovery signoff. |
| Lessons Learned | MTTD/MTTR dashboards from incident timestamps; expanded AI post-incident report workflow with reviewer edits. |

## Soon — Planned

| NIST phase | Planned capability |
|------------|--------------------|
| Preparation | Asset inventory sync for hosts, services, cloud accounts, and ownership metadata; tabletop-exercise mode for training incidents. |
| Identification | Detection-as-code storage and review; normalized alert evidence from connectors; MITRE coverage heatmap gaps by tactic and technique. |
| Containment | EDR isolation API actions; Jira and ServiceNow ticketing integration; containment approval and rollback records. |
| Eradication | Sandbox integration for suspicious files and URLs; reusable threat-hunting query packs; recurring IOC sweep jobs. |
| Recovery | Communications templates for internal, legal, customer, and executive updates; service restoration checklists by asset class. |
| Lessons Learned | Cross-incident trend analytics; recurring findings, control gaps, and technique frequency summaries. |

## Later — Enterprise Grade

| NIST phase | Enterprise-grade direction |
|------------|----------------------------|
| Preparation | Mature runbook governance, approval workflows, environment-aware playbooks, asset ownership reconciliation, and exercise scoring. |
| Identification | High-volume connector ingestion, alert correlation, deduplication, detection coverage reporting, and ATT&CK heatmap rollups across teams. |
| Containment | SOAR action execution with approvals, responder accountability, EDR isolation workflows, and external ticket lifecycle sync. |
| Eradication | Fleet-wide IOC sweeps, sandbox verdict ingestion, hunt query execution history, and remediation evidence tracking. |
| Recovery | Recovery validation evidence, communications audit trail, business service dependency checks, and controlled return-to-service workflows. |
| Lessons Learned | Executive-ready metrics, MTTD/MTTR baselines, cross-incident trend analytics, and control-improvement tracking. |

### Cross-cutting Enterprise

| Area | Capability |
|------|------------|
| Identity | SSO/SAML/OIDC, SCIM provisioning, granular RBAC, and custom roles. |
| Tenant security | Multi-tenant isolation hardening and per-tenant encryption. |
| Audit | Audit log export to SIEM. |
| Compliance | SOC2, ISO27001, and HIPAA compliance posture. |
| Availability | HA deployment with HA Postgres, Redis Sentinel, and multi-replica API. |
| Edge security | Rate limiting, WAF, and Vault secrets management. |
| Performance | Large-incident pagination and async background workers. |
| Observability | OpenTelemetry traces, structured JSON logs, and alerting. |
