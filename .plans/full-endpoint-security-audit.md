# Plan: Full Security Audit of All API Endpoints

ClickUp: https://app.clickup.com/t/86c9ng9t5

## Context
Recent reviews found two missing permission decorators (Ollama models endpoint, MITRE pattern CRUD). The codebase has grown across many endpoint files — a systematic pass is needed to confirm every route is properly decorated. This task produces a findings report; fixes are follow-up tasks.

## Audit checklist per endpoint

For every `@api_bp.route(...)` in `backend/app/api/v1/endpoints/`:

| Check | What to look for |
|---|---|
| Auth | `@jwt_required()` present on all non-public routes |
| Permission | `@require_permission(...)` or `@require_incident_access(...)` present |
| Audit trail | `@audit_log(...)` on all POST/PUT/PATCH/DELETE routes |
| Input validation | Query params and JSON body fields are validated (type, length, format) before use |
| SQL safety | No raw string concatenation into queries; all filters use ORM or `text()` with bound params |
| SSRF | Any outbound URL built from user input validated against an allowlist |

## Files to audit

```
backend/app/api/v1/endpoints/
  auth.py
  incidents.py
  integrations.py
  knowledge_base.py
  notes.py
  playbooks.py
  storage.py
  tasks.py
  teams.py
  timeline.py
  users.py
  (any others present)
```

## Output format

Structured findings report — one row per issue:

```
| Severity | File | Line | Endpoint | Issue | Recommendation |
```

Severity: **critical** (unauthenticated + mutating), **high** (authenticated but unpermissioned), **normal** (missing audit log / input gap), **low** (style / informational).

## How Claude should run this

1. Read each endpoint file in full (not via shell — use the Read tool).
2. For each route, check the decorator stack above it.
3. Cross-reference `@require_permission` values against the permission registry (grep `require_permission` across the codebase to find all values in use and confirm consistency).
4. Flag any endpoint that:
   - Has `@jwt_required()` but no permission check
   - Has no `@audit_log` on a mutating route
   - Passes user-supplied string directly into DB filter without validation
5. Produce the findings table.
6. Create follow-up ClickUp tasks (BackEnd list `901509338967`, workspace `9015967512`) for each critical/high finding.

## Verification

The audit is complete when:
- All files in `endpoints/` have been read
- Findings table has at least one entry per file (or "no issues" noted)
- Follow-up tasks created in ClickUp for critical and high findings
