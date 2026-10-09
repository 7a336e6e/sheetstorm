# API Reference

All endpoints are prefixed with `/api/v1`. Authentication via `Authorization: Bearer <token>` header.

---

## List endpoints: paging, sorting, filtering

Every list endpoint (incidents, archived incidents, users, notifications and
the per-incident timeline, hosts, accounts, network/host IOCs, malware, case
notes, tasks, artifacts, reports) follows one contract
(`backend/app/utils/pagination.py`):

| Param      | Rule |
|------------|------|
| `page`     | Integer ≥ 1, default 1. A non-integer is 400. |
| `per_page` | Clamped to 1..200, default 50. |
| `sort`     | `field` or `-field` (descending), up to 2 comma-separated, from the endpoint's whitelist; otherwise 400 `invalid_sort`. The row id is always the final tie-breaker, so pages are stable. Legacy `order=asc\|desc` applies when the sort is a single bare field. |
| `q`        | Free text (legacy alias `search`), ≤ 200 chars, `%`/`_`/`\` match literally, case-insensitive substring match over the endpoint's text columns. |
| filters    | Endpoint-specific (e.g. incidents `status=open,investigating`, `severity`, `phase`, `classification`, `team_id`). Invalid values are 400 `invalid_filter`. |
| `focus`    | Row UUID: returns the page containing that row under the current sort and filters, with `focus_found: true`; if the row is not in the filtered set, the requested page with `focus_found: false`. |

Response: `{items, total, page, per_page, pages, sort, focus_found?}` plus any
endpoint extras (notifications add `unread_count`).

## Search

| Method | Endpoint  | Description | Rate Limit |
|--------|-----------|-------------|------------|
| GET    | `/search` | Cross-incident search over incidents, timeline, hosts, accounts, network/host IOCs, malware and case notes | 60/minute |

Params: `q` (2..200 chars), `types` (comma list), `incident_id` (404 unless
accessible), `since`/`until`, `sort` = `relevance` (default: exact, then
prefix match on the primary value, then newest) \| `-timestamp` \|
`timestamp`, `page`, `per_page` (≤ 50). Only incidents the caller can see are
searched, and types whose read permission (`timeline:read`, `hosts:read`,
`accounts:read`, `network_iocs:read`, `host_iocs:read`, `malware:read`;
incidents and notes need `incidents:read`) is missing are left out. Response:
`{results, total, page, per_page, pages, facets: {type: count}, sort}`; each
result has `id`, `type`, `incident_id`, `incident_title`, `title`, `snippet`,
`timestamp` and `link: {incident_id, tab, row}` for deep links.

---

## Authentication

| Method | Endpoint           | Description          | Rate Limit |
|--------|--------------------|----------------------|------------|
| POST   | `/auth/register`   | Register new user    | 3/hour     |
| POST   | `/auth/login`      | Login                | 5/minute   |
| POST   | `/auth/logout`     | Logout (revoke JWT)  | —          |
| POST   | `/auth/refresh`    | Refresh access token | —          |
| GET    | `/auth/me`         | Current user info    | —          |
| PUT    | `/auth/password`   | Change password      | —          |
| POST   | `/auth/invites/lookup` | `{token}` → invite email, org, expiry (`400 invite_invalid`) | 10/minute, 60/hour |
| POST   | `/auth/invites/accept` | `{token, name, password}` → 201 tokens + cookies (one generic `400 invite_invalid`) | 5/minute, 20/hour |
| POST   | `/auth/password-reset/complete` | `{token, new_password}` (admin-issued link; `400 reset_invalid`) | 5/minute, 20/hour |

Login returns one generic `401` for an unknown email, a wrong password, a locked or a disabled
account. `LOGIN_LOCKOUT_THRESHOLD` consecutive bad passwords / MFA codes lock the account for
`LOGIN_LOCKOUT_MINUTES`. A user with `must_change_password` (admin temporary password, seeded
admin) gets `403 password_change_required` on every route except `/auth/me`, `/auth/change-password`,
`/auth/logout`, `/auth/refresh` and `/health*`.

## Incidents

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents`                              | List incidents (paginated)     |
| POST   | `/incidents`                              | Create incident                |
| GET    | `/incidents/{id}`                         | Get incident details           |
| PUT    | `/incidents/{id}`                         | Update incident                |
| POST   | `/incidents/{id}/archive`                 | Archive (`incidents:archive`)  |
| POST   | `/incidents/{id}/unarchive`               | Restore (`incidents:archive`)  |
| GET    | `/incidents/archived`                     | List archived (`incidents:archive`) |
| DELETE | `/incidents/{id}/permanent`               | Purge an archived incident (`incidents:purge`) |
| PATCH  | `/incidents/{id}/status`                  | Update status/phase            |
| POST   | `/incidents/{id}/import/parse`            | Parse Excel file               |
| POST   | `/incidents/{id}/import/submit`           | Submit mapped import data      |
| GET    | `/dashboard/stats`                        | Dashboard counts over every incident you can access (`incidents:read`) |

**Create** (`POST /incidents`): `title` (3–500), `description` (≤ 10000), `severity`,
`classification`, `tlp`, `detected_at` (default now), `lead_responder_id`, `team_id`, `team_ids`.
`team_id`/`team_ids` must be teams of your organization (400 `invalid_team`) and the lead an active
user of it (400 `invalid_lead_responder`). The lead gets a "Lead Responder" assignment and a
notification. Nothing is written on a 400.

**IR milestones** (`PUT /incidents/{id}`): `detected_at`, `contained_at`, `eradicated_at`,
`recovered_at`, `closed_at` (ISO 8601; no offset = UTC; `null` clears one). Rejected with
`400 invalid_milestones` when a value is more than 5 minutes in the future (`code: milestone_in_future`)
or out of order `detected ≤ contained ≤ eradicated ≤ recovered ≤ closed`
(`code: milestone_order`, `pair: [earlier, later]`). Only changed values are checked, so an existing
out-of-order pair does not block unrelated edits. `executive_summary` and `lessons_learned` are capped
at 20000 characters. A lead change notifies the new lead.

**Status** (`PATCH /incidents/{id}/status`): `status` or `phase` (each implies the other). Entering
contained / eradicated / recovered / closed stamps that milestone if it is empty; reopening a closed
incident clears `closed_at`.

**Overview summary**: `GET /incidents/{id}` (not the list) adds `summary`: `first_event_at`,
`last_event_at`, `earliest_detection_at` (needs `timeline:read`), `leads {total, open, by_outcome}`
(`tasks:read`), `hosts_by_triage` and `acquisition {disk_imaged, memory_captured, logs_collected,
forensically_sound}` (`hosts:read`); a part is `null` without its permission.

**Dashboard** (`GET /dashboard/stats`, 30/min): `incidents {total, active, closed, critical, created_7d,
created_30d, by_severity, by_status, by_phase_open, by_tlp}`, `mitre {events_total, events_mapped,
tactics: [{tactic, count, techniques: {Txxxx: n}}]}` (`timeline:read`, else `null`) and
`dfir {open_leads (tasks:read), hosts_by_triage (hosts:read)}`. Counts only, never incident ids or titles.

## Timeline Events

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/timeline`                | List timeline events           |
| POST   | `/incidents/{id}/timeline`                | Create event                   |
| PUT    | `/incidents/{id}/timeline/{eid}`          | Update event                   |
| DELETE | `/incidents/{id}/timeline/{eid}`          | Delete event                   |
| POST   | `/incidents/{id}/timeline/{eid}/mark-ioc` | Flag event as IOC              |
| GET    | `/mitre/tactics`                          | List MITRE tactics             |
| GET    | `/mitre/techniques/{tactic}`              | List techniques for tactic     |

## Compromised Assets

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/hosts`                   | List compromised hosts         |
| POST   | `/incidents/{id}/hosts`                   | Add compromised host           |
| PUT    | `/incidents/{id}/hosts/{hid}`             | Update host                    |
| DELETE | `/incidents/{id}/hosts/{hid}`             | Delete host                    |
| GET    | `/incidents/{id}/accounts`                | List compromised accounts      |
| POST   | `/incidents/{id}/accounts`                | Add account (password encrypted)|
| PUT    | `/incidents/{id}/accounts/{aid}`          | Update account                 |
| DELETE | `/incidents/{id}/accounts/{aid}`          | Delete account                 |
| GET    | `/incidents/{id}/accounts/{aid}/reveal`   | Reveal decrypted password      |

## IOCs

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/network-iocs`            | List network indicators        |
| POST   | `/incidents/{id}/network-iocs`            | Add network IOC                |
| PUT    | `/incidents/{id}/network-iocs/{nid}`      | Update network IOC             |
| DELETE | `/incidents/{id}/network-iocs/{nid}`      | Delete network IOC             |
| GET    | `/incidents/{id}/host-iocs`               | List host-based indicators     |
| POST   | `/incidents/{id}/host-iocs`               | Add host IOC                   |
| PUT    | `/incidents/{id}/host-iocs/{hid}`         | Update host IOC                |
| DELETE | `/incidents/{id}/host-iocs/{hid}`         | Delete host IOC                |
| GET    | `/incidents/{id}/malware`                 | List malware/tools             |
| POST   | `/incidents/{id}/malware`                 | Add malware entry              |
| PUT    | `/incidents/{id}/malware/{mid}`           | Update malware entry           |
| DELETE | `/incidents/{id}/malware/{mid}`           | Delete malware entry           |

## Attack Graph

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/attack-graph`            | Full graph with correlations   |
| POST   | `/incidents/{id}/attack-graph/auto-generate` | Auto-generate from data     |
| GET    | `/incidents/{id}/attack-graph/nodes`      | List nodes                     |
| POST   | `/incidents/{id}/attack-graph/nodes`      | Create node                    |
| PUT    | `/incidents/{id}/attack-graph/nodes/{nid}`| Update node                    |
| DELETE | `/incidents/{id}/attack-graph/nodes/{nid}`| Delete node                    |
| GET    | `/incidents/{id}/attack-graph/edges`      | List edges                     |
| POST   | `/incidents/{id}/attack-graph/edges`      | Create edge                    |
| PUT    | `/incidents/{id}/attack-graph/edges/{eid}`| Update edge                    |
| DELETE | `/incidents/{id}/attack-graph/edges/{eid}`| Delete edge                    |
| GET    | `/attack-graph/node-types`                | Available node types           |
| GET    | `/attack-graph/edge-types`                | Available edge types           |

## Artifacts & Evidence

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/artifacts`               | List artifacts                 |
| POST   | `/incidents/{id}/artifacts`               | Upload artifact (multipart)    |
| GET    | `/incidents/{id}/artifacts/{aid}/download` | Download artifact             |
| POST   | `/incidents/{id}/artifacts/{aid}/verify`  | Verify integrity               |
| GET    | `/incidents/{id}/artifacts/{aid}/custody` | Chain of custody log           |

## Tasks

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/tasks`                   | List tasks                     |
| POST   | `/incidents/{id}/tasks`                   | Create task                    |
| PUT    | `/incidents/{id}/tasks/{tid}`             | Update task                    |
| DELETE | `/incidents/{id}/tasks/{tid}`             | Delete task                    |
| POST   | `/incidents/{id}/tasks/{tid}/comments`    | Add comment                    |
| GET    | `/incidents/{id}/tasks/{tid}/comments`    | List comments                  |

## Reports

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| POST   | `/incidents/{id}/reports/generate-pdf`    | Generate PDF report            |
| POST   | `/incidents/{id}/reports/ai-generate`     | Generate AI summary            |
| GET    | `/incidents/{id}/reports`                 | List reports                   |

## Admin & System

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/users`                                  | List users (`q`, `role`, `role_id`, `status`=active\|disabled\|locked\|must_change_password, `team_id`, `mfa`) |
| GET    | `/users/stats`                            | Org-wide counts (active, disabled, locked, MFA, pending invites, by role) |
| POST   | `/users/invites`                          | Invite (`users:manage`; roles need `roles:manage`); returns the one-time `token`/`accept_path` once |
| GET    | `/users/invites`                          | Invites (`status`=pending\|accepted\|revoked\|expired\|all) |
| DELETE | `/users/invites/{id}`                     | Revoke an invite (`409 already_accepted`) |
| POST   | `/users/{id}/disable`                     | Disable with `{reason}`; revokes every session (`users:manage`) |
| POST   | `/users/{id}/enable`                      | Re-enable (old sessions stay revoked) |
| POST   | `/users/{id}/force-logout`                | Revoke every session and socket |
| POST   | `/users/{id}/unlock`                      | Clear a login lockout |
| POST   | `/users/{id}/reset-password`              | `{mode: link\|temp, revoke_sessions?}` → one-time link or temporary password (forced change) |
| POST   | `/users/{id}/reset-mfa`                   | Remove MFA and revoke sessions (`409 mfa_not_enabled`) |
| POST   | `/users/bulk`                             | `{action: disable\|enable\|force_logout\|add_role\|remove_role\|add_team, user_ids (≤100)}` → per-item results (10/minute) |
| GET    | `/users/{id}/activity`                    | Audit rows by / about the user (`audit_logs:read`, `scope`=actor\|target\|all) |
| POST   | `/users`                                  | Create user (`users:create`; roles need `roles:manage` and must be within your permissions) |
| GET    | `/users/{id}`                             | Get user details               |
| PUT    | `/users/{id}`                             | Update user (`users:update`; you must outrank the user) |
| DELETE | `/users/{id}`                             | Delete user (`users:delete`; never yourself or the last admin). A user with authored records → `409 user_has_records {counts, hint:'deactivate'}`; `?anonymize=true` scrubs personal data and keeps the row |
| GET    | `/users/{id}/roles`                       | Get user roles                 |
| POST   | `/users/{id}/roles`                       | Assign role (`roles:manage`, within your permissions) |
| DELETE | `/users/{id}/roles/{rid}`                 | Remove role (`roles:manage`; last-admin / self-lockout guarded) |
| POST   | `/users/sync-supabase`                    | Import Supabase users into the default org (`users:manage`, default-org admins only) |
| GET    | `/permissions`                            | Permission catalog `{groups, items}` (any authenticated user) |
| GET    | `/roles`                                  | System roles + your org's roles (`users:read`) |
| GET    | `/roles/{id}`                             | Role details                   |
| POST   | `/roles`                                  | Create custom role (`roles:manage`) |
| PUT    | `/roles/{id}`                             | Edit custom role (system roles: `403 system_role_immutable`) |
| POST   | `/roles/{id}/clone`                       | Clone a role into your org     |
| DELETE | `/roles/{id}`                             | Delete an unassigned custom role |
| GET    | `/teams`                                  | List teams (`teams:read`)      |
| GET    | `/teams/{id}`                             | Team with members (`teams:read` + `users:read`) |
| POST   | `/teams`                                  | Create team (`teams:create`)   |
| PUT    | `/teams/{id}`                             | Edit team (`teams:update`); members via `/teams/{id}/members` |
| DELETE | `/teams/{id}`                             | Delete team (`teams:delete`)   |
| GET    | `/organization`                           | Organization with allow-listed settings |
| PUT    | `/organization`                           | Update name / settings (`organizations:manage`; unknown keys → `400 validation_error`) |
| GET    | `/notifications`                          | List notifications             |
| PUT    | `/notifications/{id}/read`                | Mark as read                   |
| POST   | `/notifications/mark-all-read`            | Mark all as read               |
| GET    | `/audit-logs`                             | List audit logs (paginated)    |
| GET    | `/audit-logs/stats`                       | Audit statistics               |
| GET    | `/integrations`                           | List integrations              |
| POST   | `/integrations`                           | Create integration             |
| GET    | `/health`                                 | Health check                   |

### Organization settings

`PUT /organization` accepts `{name?, settings?}`; `settings` keys (all optional, merged over the
stored ones): `timezone` (IANA name), `auto_enrich_iocs` (bool), `enrichment_allow_amber_strict`
(bool), `ai_tlp_policy` (`{white|green|amber|amber_strict|red: allow|local_only|block}`, defaults
`red`/`amber_strict` → `local_only`, others `allow`) and `registration_enabled` (bool, default
organization only, otherwise `400 not_applicable`). Self-registration is **closed by default**.
Every change is audited with a before/after diff; loosening the AI policy for any TLP level also
records an `ai_tlp_policy_loosened` security event.

### Guard errors

| Status | `error`                 | Extra fields          |
|--------|-------------------------|-----------------------|
| 400    | `unknown_permissions`   | `unknown`             |
| 400    | `self_action`           | `action`              |
| 400    | `use_change_password`   | —                     |
| 403    | `privilege_escalation`  | `missing` (`platform_only`) |
| 403    | `insufficient_privilege`| `missing`             |
| 403    | `system_role_immutable` | —                     |
| 409    | `last_admin`            | —                     |
| 409    | `self_lockout`          | `lost`                |
