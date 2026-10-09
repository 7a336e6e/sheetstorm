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
| GET    | `/auth/password-policy` | Password rules for form hints: the caller's organization, else the platform organization (public) | 60/minute |
| GET    | `/auth/registration-status` | `{registration_enabled}` of the platform organization's security policy (public) | — |

Login returns one generic `401` for an unknown email, a wrong password, a locked or a disabled
account. `LOGIN_LOCKOUT_THRESHOLD` consecutive bad passwords / MFA codes lock the account for
`LOGIN_LOCKOUT_MINUTES`. A user with `must_change_password` (admin temporary password, seeded
admin, expired password) gets `403 password_change_required` on every route except `/auth/me`,
`/auth/change-password`, `/auth/password-policy`, `/auth/logout`, `/auth/refresh` and `/health*`.

Passwords follow the organization's security policy (see below). A violation answers
`400 {error: 'bad_request', code: 'password_policy', message, violations: [...]}`. Registration and
first SSO sign-ins follow the platform organization's policy: `403 registration_disabled` or
`403 email_domain_not_allowed`.

Every sign-in creates a session: the tokens carry its id (`sid`), refresh keeps it, logout revokes
it. Sign-in responses and `/auth/me` include `user.security`:
`{mfa_required, mfa_enrollment_required, mfa_grace_ends_at, password_change_required,
password_expires_at}`. While `mfa_enrollment_required` is true every route except `/auth/me`,
`/auth/mfa/setup`, `/auth/mfa/verify`, `/auth/password-policy`, `/auth/change-password`,
`/auth/logout`, `/auth/refresh` and `/health*` answers `403 mfa_enrollment_required` (API keys are
exempt). `/auth/mfa/disable` answers `403 mfa_required_by_policy` when the policy requires MFA for
the user.

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

**IR milestones** (`PUT /incidents/{id}`): `first_malicious_at`, `detected_at`, `responded_at`,
`contained_at`, `eradicated_at`, `recovered_at`, `closed_at` (ISO 8601; no offset = UTC; `null`
clears one). Rejected with `400 invalid_milestones` when a value is more than 5 minutes in the
future (`code: milestone_in_future`) or out of order
`first_malicious ≤ detected ≤ contained ≤ eradicated ≤ recovered ≤ closed`, or `responded` before
`detected` (`code: milestone_order`, `pair: [earlier, later]`). Only changed values are checked, so an
existing out-of-order pair does not block unrelated edits (the metrics report it as an anomaly). `executive_summary` and `lessons_learned` are capped
at 20000 characters. A lead change notifies the new lead.

**Status** (`PATCH /incidents/{id}/status`): `status` or `phase` (each implies the other). Entering
contained / eradicated / recovered / closed stamps that milestone if it is empty; reopening a closed
incident clears `closed_at`. The first status away from `open`, or the first explicit assignment
(`POST /incidents/{id}/assignments`; the creator's automatic one does not count), stamps `responded_at`
if it is empty.

**Overview summary**: `GET /incidents/{id}` (not the list) adds `summary`: `first_event_at`,
`last_event_at`, `earliest_detection_at` (needs `timeline:read`), `leads {total, open, by_outcome}`
(`tasks:read`), `hosts_by_triage` and `acquisition {disk_imaged, memory_captured, logs_collected,
forensically_sound}` (`hosts:read`); a part is `null` without its permission.

**Dashboard** (`GET /dashboard/stats`, 30/min): `incidents {total, active, closed, critical, created_7d,
created_30d, by_severity, by_status, by_phase_open, by_tlp}`, `mitre {events_total, events_mapped,
tactics: [{tactic, count, techniques: {Txxxx: n}}]}` (`timeline:read`, else `null`) and
`dfir {open_leads (tasks:read), hosts_by_triage (hosts:read)}`. Counts only, never incident ids or titles.

## Metrics, After-Action Review & Improvements

| Method | Endpoint                                  | Permission                     |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/metrics`                 | `incidents:read`               |
| GET    | `/metrics/incidents`                      | `metrics:read` (30/min)        |
| GET    | `/incidents/{id}/review`                  | `incidents:read`               |
| PUT    | `/incidents/{id}/review`                  | `incidents:update` (see below) |
| GET    | `/incidents/{id}/improvement-actions`     | `improvements:read`            |
| POST   | `/incidents/{id}/improvement-actions`     | `improvements:create`          |
| GET    | `/improvement-actions`                    | `improvements:read`            |
| PUT    | `/improvement-actions/{aid}`              | `improvements:update`          |
| DELETE | `/improvement-actions/{aid}`              | `improvements:delete`          |

**Metrics.** Durations in seconds, `null` when an endpoint is missing: `dwell_time` (first malicious →
detected), `time_to_respond`, `time_to_contain` (from detected), `contain_to_eradicate`,
`eradicate_to_recover`, `recover_to_close`, `total_open`. `first_malicious` is `incidents.first_malicious_at`
(manual override) or the earliest timeline event that is an IOC or carries a MITRE tactic / mapping or a
kill-chain phase. A negative interval is `null` plus an entry in `anomalies`; `sources.first_malicious` is
`override`, `timeline`, `restricted` (caller lacks `timeline:read`, so the timeline is not consulted) or `null`.
`GET /metrics/incidents` needs `from` and `to` (ISO date or datetime; a date-only `to` includes that day; at
most 731 days → 400 `invalid_range`), and takes `group_by` = `none|severity|classification|detection_source` and
`date_field` = `detected_at|closed_at`. It aggregates in SQL over the incidents the caller can see (the incident
list's visibility; archived excluded) and returns `{overall, groups}` with `{median, p90, n, anomalies}` per
metric; a metric with fewer than 3 values reports `n` only.

**Review** (`incident_reviews`, one per incident). `GET` returns `{review|null, legacy_lessons_learned, can_manage}`.
`PUT` upserts the sent fields (`what_went_well`, `what_went_wrong`, `root_cause`, `contributing_factors:
[{category, description}]`, `detection_source`, `review_date`, `participants` (same-org user ids), `status`
`draft|final`) with `If-Match`. A draft is edited with `incidents:update`; finalizing, reopening and editing a
final review also need `improvements:create` + `improvements:update` (403 `forbidden` / `review_finalized`).

**Improvement actions** survive a permanent incident delete (`incident_id` becomes null, `incident_ref` keeps
`#<n> <title>`). Fields: `title`, `description`, `owner_id` (active user of the org), `due_date`, `status`
`open|in_progress|blocked|done|wont_fix`, `priority`, `category`, `control_framework` (`nist_csf|d3fend|cis|
iso27001|other`) and `control_ref` (needs a framework; `nist_csf` like `RS.MA-01`, `d3fend` a known `D3-*` id).
`improvements:update` without `improvements:create` (Analyst, Operator) only covers actions you own or created.
The org list shows an action when its incident is visible to you, it has no incident, or you own it; filters:
`status`, `priority` (comma lists), `incident_id`, `owner_id` (`me`), `overdue=true`, `q`; default sort by due date.
Writes honour `If-Match` and emit `review` / `improvement_action` realtime changes.

## Decision log and response actions

| Method | Endpoint                                                  | Permission |
|--------|-----------------------------------------------------------|------------|
| GET    | `/incidents/{id}/decisions`                               | `decisions:read` |
| POST   | `/incidents/{id}/decisions`                               | `decisions:create` |
| GET    | `/incidents/{id}/decisions/{did}`                         | `decisions:read` |
| PUT    | `/incidents/{id}/decisions/{did}`                         | `decisions:update` (If-Match, `reason`) |
| POST   | `/incidents/{id}/decisions/{did}/approve`                 | `decisions:approve` (in-app) or `decisions:update` (`approved_by_name`) |
| POST   | `/incidents/{id}/decisions/{did}/reject`                  | `decisions:approve` (`reason`) |
| POST   | `/incidents/{id}/decisions/{did}/reopen` / `supersede`    | `decisions:update` |
| GET    | `/incidents/{id}/decisions/{did}/revisions`               | `decisions:read` |
| GET    | `/incidents/{id}/response-actions`                        | `response_actions:read` |
| POST   | `/incidents/{id}/response-actions`                        | `response_actions:create` |
| GET    | `/incidents/{id}/response-actions/{aid}`                  | `response_actions:read` |
| PUT    | `/incidents/{id}/response-actions/{aid}`                  | `response_actions:update` (If-Match, `reason`) |
| POST   | `/incidents/{id}/response-actions/{aid}/authorize`        | `response_actions:authorize` (in-app) or `:update` (`authorized_by_name`) |
| POST   | `/incidents/{id}/response-actions/{aid}/start` · `execute` · `fail` · `verify` · `rollback` · `cancel` | `response_actions:update` |
| GET    | `/incidents/{id}/response-actions/{aid}/revisions`        | `response_actions:read` |
| GET    | `/incidents/{id}/response-timeline`                       | `timeline:read` (+ the read permission of each kind) |
| GET    | `/incidents/{id}/decision-log/export`                     | `incidents:export` + read permissions (30/min) |

Decisions (`D-007`) are `proposed → approved | rejected | superseded` (`rejected → proposed` on reopen). Response
actions (`A-012`) are `requested → authorized → in_progress → executed → verified`, with `failed`, `rolled_back`
and `cancelled`; an invalid move is 409 `invalid_transition`. There is no DELETE. Writes to an existing record need
`If-Match` or body `expected_version` (428 `precondition_required` without one, 409 `conflict` when stale); a PUT
needs a `reason` and changes descriptive fields only. Retroactive logging: create accepts later-stage fields
(`approved_by_name`, `authorized_by_name`, `executed_at`, `verified_at` + `verification_result`) and derives the
status. An in-app approver/authorizer/executor/verifier is always the acting user; anyone else is recorded by name
(`*_by_name`, shown as "recorded"). `self_approved` / `self_verified` flag approver = requester and verifier =
executor. `links` use `[{evidence_type, evidence_id}]` (same incident; `decision` and `response_action` are
registered evidence-ref types). `execute` with `apply_target_state: true` sets the host `containment_status` /
account `status` (needs `hosts:update` / `accounts:update`); `rollback` restores it only if unchanged since
(409 `target_state_changed`, or `restore_target_state: false`).

Every change appends an INSERT-only revision (snapshot, `{field: {from, to}}` diff, reason, actor) chained per
record with `hash_chain` domain `decision-v1` and HMAC-signed with the custody key. `GET …/revisions` returns each
revision's `signature_status` and a `verification.status` of `intact`, `broken` (missing/reordered revisions or a
head row edited outside the log), `compromised` (a signature mismatch) or `unverifiable` (key rotated).

**Privileged decisions** (`is_privileged`, set only with `decisions:read_privileged`) are 404 without that
permission and are excluded from lists, the response timeline, report appendices, exports (unless
`include_privileged=1` by a holder) and MCP. Their realtime changes go only to scope `decisions_privileged`.
Decision-log data is never sent to AI providers. The export takes `format=json|csv|pdf`,
`kind=decisions|actions|all`, `include_revisions=0|1`; CSV cells are formula-escaped. Full PDF reports include a
"Decisions & Response Actions" appendix (non-privileged only) inside the issued snapshot. The JSON custody export of
an evidence item lists `referenced_by` (events/IOCs citing it, decisions/actions linking it).

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

Timeline list (dual time): `sort` also accepts `detection_time`, `dwell`
(detection minus occurrence) and `confidence`; events without a detection
time or confidence sort last. Filters: `confidence=high,certain` (comma list
of `low|medium|high|certain`, anything else is 400 `invalid_filter`) and
`has_detection=true|false`.

## Compromised Assets

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/hosts`                   | List compromised hosts         |
| POST   | `/incidents/{id}/hosts`                   | Add compromised host           |
| PUT    | `/incidents/{id}/hosts/{hid}`             | Update host                    |
| PATCH  | `/incidents/{id}/hosts/bulk`              | Set triage / containment on up to 500 hosts (`hosts:update`) |
| DELETE | `/incidents/{id}/hosts/{hid}`             | Delete host                    |
| GET    | `/incidents/{id}/accounts`                | List compromised accounts      |
| POST   | `/incidents/{id}/accounts`                | Add account (password encrypted)|
| PUT    | `/incidents/{id}/accounts/{aid}`          | Update account                 |
| DELETE | `/incidents/{id}/accounts/{aid}`          | Delete account                 |
| GET    | `/incidents/{id}/accounts/{aid}/reveal`   | Reveal decrypted password      |

Hosts:
- List filters: `triage_status` (comma list of
  `clean|compromised|under_analysis|suspicious`), `acquisition` (comma list
  of `disk_imaged|memory_captured|logs_collected|forensically_sound` that must
  be true; prefix `!` for "not done", e.g. `memory_captured,!disk_imaged`),
  `containment_status`. `sort` also accepts `triage_status`.
- `acquisition_status` on create/update accepts only those four booleans plus
  `acquired_at` (ISO-8601, naive = UTC, stored as UTC). Unknown keys or wrong
  types return 400.
- Bulk: body `{host_ids: [uuid], triage_status?, containment_status?}`, with
  no other keys. 1..500 ids, de-duplicated. Every id must be a host of the
  incident, otherwise 400 `invalid_host_ids` with `invalid: [...]` and nothing
  changes. The response is `{updated, items}`, the update is audited as
  `bulk_update`, and clients receive one `incident:resync` for the `hosts`
  scope.

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

## Record provenance and clock skew

Timeline events, network IOCs, host IOCs and malware entries record where a
fact came from and how its UTC time was derived. All keys are optional on the
create/update bodies of those four resources; legacy rows have none of them.

| Key | Meaning |
|-----|---------|
| `source_evidence_id` / `source_artifact_id` | Source evidence item / artifact. Must belong to the same incident, otherwise 400 `invalid_source_evidence` / `invalid_source_artifact`. The UI links evidence items; deleting the source sets the link to null. |
| `source_record_type` | `file_path, evtx_record, offset, log_line, url, registry_key, db_row, other` |
| `source_record_ref` | Exact record reference (<= 1000 chars, no control characters). Stored and shown as text; URLs are never fetched or rendered as links. |
| `raw_timestamp` | The timestamp exactly as found (<= 100 chars). |
| `source_timezone` | IANA key (`Europe/Berlin`), `UTC` or `UTC+HH:MM`. |
| `timestamp_type` | `modified, accessed, changed, born, logged, first_seen, last_seen, observed, other` (malware: `modified`, `accessed`, `born` pick `modification_time`, `access_time`, `creation_time`). |
| `extraction_tool`, `extraction_tool_version` | Tool and version that produced the record. |
| `timestamp_derivation` (write: `manual` or `imported`) | `computed` is server-set. A null value reads as `manual`. |
| `fold` (write only, 0 or 1) | Picks the occurrence of a daylight-saving fold. |

Responses add `provenance_level` (`none | partial | full | verified`;
`full` = evidence/artifact link + record ref + raw timestamp + time zone),
`provenance_verifier {id, name}`, `clock_skew_applied_seconds` and the
verification columns, which are read-only.

IANA zone names need the system `tzdata` of the backend image (the pinned
`python:3.12-slim-bookworm` base has it; `UTC`, `UTC+HH:MM` and offsets inside
the raw string always work, and an unknown zone is 400 `invalid_timezone`).

Normalization: `utc = raw (+ offset or source_timezone, else the host's
timezone) - host clock_skew_seconds`. Create may omit `timestamp` (events) when
`raw_timestamp` is sent; the server derives it and sets
`timestamp_derivation: computed`. A `timestamp` that differs from the derived
value by more than 1 second is 400 `timestamp_mismatch` (with `computed`)
unless `timestamp_derivation: "manual"` is sent. A raw timestamp without an
offset and without any time zone is 400 `source_timezone_required`; a time in a
daylight-saving gap is 400 `nonexistent_local_time`, in a fold 400
`ambiguous_local_time` (with `candidates`, resend with `fold`); day/month
ambiguous or incomplete input is 400 `ambiguous_date` / `incomplete_raw_timestamp`.
On update the derivation re-runs only when `raw_timestamp`, `source_timezone`
or `timestamp_type` actually changed, so clients may resend whole records.
Overriding a computed `timestamp` makes it `manual`. Any material change to a
verified record clears its verification (the audit row carries
`provenance_verification_cleared`).

List filters on the four resources: `provenance_level`, `source_artifact_id`,
`source_evidence_id`, `unverified=true` (provenance recorded, not yet
verified).

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST   | `/incidents/{id}/provenance/verify` | Second-analyst verification. Body `{record_type: timeline_event\|network_ioc\|host_ioc\|malware, record_id, expected_version?}`; needs the type's `:update` permission. 400 `same_analyst` for the creator, 400 `no_provenance`, 409 `already_verified`. |
| DELETE | `/incidents/{id}/provenance/verify` | Withdraw (same body); only the verifier or a holder of `organizations:manage`. |
| POST   | `/incidents/{id}/provenance/normalize-preview` | `{raw_timestamp, source_timezone?, host_id?, fold?}` -> `{utc, skew_applied, timezone_used, offset_seconds}` (`timeline:read`, 60/minute). |
| PUT    | `/incidents/{id}/hosts/{hid}/clock-skew` | `{clock_skew_seconds?, clock_skew_basis?, timezone?}` (`hosts:update`, `If-Match`). Skew is host clock minus true UTC within +-604800 s; a non-zero skew needs a basis. Stamps who/when measured. Existing records keep the skew they snapshotted. |
| POST   | `/incidents/{id}/hosts/{hid}/clock-skew/reapply` | `{dry_run: true}` (default) lists records whose time would move; `{dry_run: false}` applies it (`hosts:update` + `timeline:update`, `network_iocs:update`, `host_iocs:update`, `malware:update`). Only `computed` records move, by the skew difference; verification of changed rows is cleared; one audit row `renormalize`; clients receive `incident:resync` for timeline, network_iocs, host_iocs and malware. |

## Attack Graph

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/attack-graph`            | Full graph with correlations   |
| POST   | `/incidents/{id}/attack-graph/auto-generate` | Auto-generate from data: `{mode: merge\|replace, confirm}` |
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

### Attack graph auto-generate: merge and replace

`mode: "merge"` (the default, also for an empty body) only adds what is
missing and never moves, edits or deletes existing nodes and edges. Generated
nodes and edges carry `extra_data.origin = "auto"` and an `auto_key`
(`host:<id>`, `account:<id>`, `malware:<id>`, `hioc:<id>`, `nioc:<value>`;
edges `<type>:<src key>-><dst key>`); graphs built before keys existed are
matched by their host / account links and by type + label, so they are not
duplicated. Only `origin = "auto"` nodes get their `label` / `extra_data`
refreshed; manual nodes and every position are left alone. `mode: "replace"`
deletes the whole graph first (manual nodes, edges and positions included) and
needs `confirm: true` (400 `confirmation_required` otherwise). The response is
`{created: {nodes, edges}, mode, message, nodes, edges}`.

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

Tasks:
- List filters: `task_type` (comma list), `lead_outcome` (comma list; `open`
  = no outcome yet), plus `status`, `priority`, `assignee_id` and `phase`.
  `sort` also accepts `updated_at`. `include_comments=false` omits the
  embedded comments. `lead_counts=true` adds `lead_counts` (`{open,
  false_positive, confirmed_malicious, inconclusive, resolved}` over the
  incident's investigative leads).
- `evidence_refs`: at most 50 `{evidence_type, evidence_id}` refs to
  records of the same incident. Types: `timeline_event, host, account,
  network_ioc, host_ioc, malware, artifact, evidence_item`. The aliases
  `host_indicator` and `network_indicator` are stored canonically. Bad,
  unknown or cross-incident refs return 400 `invalid_evidence_refs` with
  `invalid: [{index, evidence_type, evidence_id, reason}]`. Refs already on
  the task are kept on update even if their record was deleted.
- Responses include `evidence: [{evidence_type, evidence_id, label, missing,
  restricted?}]`, with labels resolved by the server. Socket payloads carry
  the refs without labels.
- `assignee_id` must be an active user of the incident's organization (400
  `invalid_assignee`). `parent_task_id` must be a task of the same incident
  and must not create a cycle (400 `invalid_parent_task`).
  `investigation_direction` is capped at 5000 characters and `title` at 500.

## Investigative questions

Reads need `incidents:read`, writes `incidents:update` (a Viewer is read-only).

| Method | Endpoint                                              | Description                                   |
|--------|-------------------------------------------------------|-----------------------------------------------|
| GET    | `/incidents/{id}/questions`                           | List (filters, `summary`)                     |
| POST   | `/incidents/{id}/questions`                           | Add a manual question or a `library_ref`      |
| POST   | `/incidents/{id}/questions/bulk`                      | Add up to 100 library questions (`{refs}`)    |
| GET    | `/incidents/{id}/questions/{qid}`                     | One question (ETag)                           |
| PUT    | `/incidents/{id}/questions/{qid}`                     | Edit / answer (`If-Match` or `expected_version`) |
| DELETE | `/incidents/{id}/questions/{qid}`                     | Archive (soft delete)                         |
| PUT    | `/incidents/{id}/questions/{qid}/leads`               | Replace the linked leads (`{task_ids}`)       |
| GET    | `/incidents/{id}/question-links`                      | `[{question_id, task_id}]` for the lead queue |
| GET    | `/incidents/{id}/questions/report-data`               | Answered / unanswerable / open for a report   |
| GET    | `/questions`                                          | Questions across the incidents you can access |
| GET    | `/questions/library`, `/questions/library/{ref}`      | Built-in library (tree, one question)         |

- List filters: `status` and `priority` (comma lists), `phase`, `owner_id`, `owner=me`, `facet`,
  `task_id` (questions linked to that lead), `include_archived`, `q`. The response adds `summary`
  (`total`, per-status counts, `resolved`, `progress`, `open_high_priority`, `top_open`) computed over all
  non-archived questions. Items carry `lead_ids` and server-resolved `evidence` (as for tasks).
- Rules: `answered` needs `answer` and `confidence`; `unanswerable` needs an `answer` (the rationale);
  confidence `confirmed` needs at least one evidence ref (400 `answer_required`, `confidence_required`,
  `evidence_required`). Leaving answered/unanswerable clears `answered_at`/`answered_by` but keeps the text.
  `answer` is at most 20000 characters and is plain text in the UI.
- `evidence_refs`: at most 50 `{evidence_type, evidence_id}` refs to records of the same incident
  (`timeline_event, host, account, network_ioc, host_ioc, malware, artifact, evidence_item, case_note,
  task`); `owner_id` must be an active user of the organization who can see the incident
  (400 `invalid_owner`); leads must be tasks of the incident (400 `invalid_leads`).
- Adding a question that is already on the incident (same library ref, or the same text ignoring case and
  spaces) is 409 `duplicate_question` with `existing_id`; bulk add skips such refs instead. An archived
  question is never recreated by a library add or a template apply.
- Library refs: `ss:SSQ-###` (SheetStorm core, MIT) and, when vendored, `dfiq:Q####` (DFIQ, Apache-2.0,
  with attribution in `GET /questions/library` `sources`).

## Case templates and playbooks

| Method | Endpoint                                                          | Permission           |
|--------|-------------------------------------------------------------------|----------------------|
| GET    | `/case-templates`, `/case-templates/{ref}`                        | `incidents:read`     |
| POST   | `/case-templates`                                                 | `templates:manage`   |
| PUT/DELETE | `/case-templates/{ref}`                                       | `templates:manage`   |
| POST   | `/case-templates/{ref}/clone`                                     | `templates:manage`   |
| POST   | `/incidents/{id}/case-templates/{ref}/apply`                      | `incidents:update`   |
| GET    | `/incidents/{id}/case-templates`                                  | `incidents:read`     |
| GET/PUT | `/incidents/{id}/custom-fields`                                  | read / `incidents:update` |
| GET    | `/playbooks` (org + built-in), `/playbooks/builtin/{key}`         | `incidents:read`     |
| POST/PUT/DELETE | `/playbooks`, `/playbooks/{id}`                          | `templates:manage`   |
| POST   | `/playbooks/builtin/{key}/clone`                                  | `templates:manage`   |
| POST   | `/incidents/{id}/playbooks/builtin/{key}/activate`                | `incidents:update`   |

- `{ref}` is `builtin:<key>` (shipped with the application, read-only: PUT/DELETE are 403, clone one to
  edit) or the UUID of an organization template. `GET /case-templates` returns a `summary` of counts per
  template (`include_definition=true` embeds the definitions; deactivated templates only with
  `include_inactive=true` for `templates:manage`). Updating a template bumps `version`; send `If-Match` or
  `expected_version` to avoid lost updates.
- A template `definition` (`schema_version: 1`, unknown keys rejected) holds `defaults`
  (`severity`, `tlp`, `classification`), `questions` (library `ref` or own `key` + `question`, up to
  200), `leads` (up to 100, each `answers` questions), `playbook` (`{builtin}` or `{playbook_id}`) and
  `custom_fields` (`text, number, boolean, date, select`; up to 30). Writes are capped at 256 KB; invalid
  definitions are 400 `validation_error` with a `fields` map.
- Apply (rate limited to 20 per minute) body, all optional: `apply_defaults`, `include`
  (`questions, leads, playbook, custom_fields`), `dry_run`, `run_auto_actions`. It is an idempotent merge:
  existing questions (including archived ones) and leads are skipped, an incident with an active playbook
  keeps it, defaults only raise TLP/severity and fill an empty classification, leads need `tasks:create`
  (otherwise skipped with reason `forbidden`). Response: `created {questions, leads, links}`, `skipped`,
  `playbook`, `defaults_applied`, `custom_fields_added`, `template`.
- `POST /incidents` accepts `case_template` (`builtin:<key>` or a UUID): the incident is created and seeded in
  one transaction, defaults only fill `severity`/`tlp`/`classification` the request did not set, and the
  response adds `case_template_result`. An unknown or inactive template is 400 `invalid_case_template` and
  nothing is created.
- Custom-field values: `PUT .../custom-fields` takes `{values: {key: value}}`; keys must be defined by an
  applied template, types and select options are validated, `null` clears a key. Values are also on the
  incident as `custom_fields`.
- Playbook definitions: unique phase numbers 1-6, at most 50 tasks and 20 actions per phase, task `title`
  required, `create_task` configs checked when saved. Built-in playbooks never set `auto_run`.

## Reports

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| POST   | `/incidents/{id}/reports/generate-pdf`    | Generate (issue) a PDF report; stored as a snapshot, `X-Report-SHA256` / `X-Report-Id` headers |
| POST   | `/incidents/{id}/reports/ai-generate`     | Generate AI summary            |
| GET    | `/incidents/{id}/reports`                 | List reports (not the soft-deleted ones); `is_snapshot`, `sha256`, `size_bytes` |
| GET    | `/incidents/{id}/reports/{rid}/download`  | Download the issued PDF (stored bytes, SHA-256 re-checked) |
| DELETE | `/incidents/{id}/reports/{rid}`           | Soft delete (the issued file is kept) |

A report is what was issued: the PDF bytes are stored once under
`incidents/<incident>/reports/<report>.pdf` with their SHA-256, and every
download returns those bytes (`X-Report-SHA256`, `X-Report-Snapshot: stored`).
A missing or altered file is a 409 `integrity_error` and a
`security_event / report_integrity_failure`; if the snapshot cannot be stored
generation fails (500) and no report row is created. Reports issued before
snapshots (`is_snapshot: false`) are re-rendered from current data and marked
`X-Report-Snapshot: legacy`. Report files are removed only by the permanent
incident purge (`incident_purge` steps `report_files_collect` / `report_files`).

## Exports

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/export/{entity}`         | CSV of `timeline`, `hosts`, `accounts`, `network-iocs`, `host-iocs`, `malware` or `tasks` (30/minute) |
| GET    | `/incidents/{id}/export/stix`             | STIX 2.1 bundle (`application/stix+json`, TLP-marked) |
| POST   | `/correlate-iocs`                         | `{incident_id?, ioc_values?, ioc_types?}`: indicators shared across incidents you can access |
| POST   | `/bulk-enrich`                            | `{incident_id?, ioc_values: [{value, type}]}` (≤ 100; 10/minute) |

Every export needs `incidents:export` **and** the entity's read permission
(`timeline:read`, `hosts:read`, `accounts:read`, `network_iocs:read`,
`host_iocs:read`, `malware:read`, `tasks:read`; STIX needs `incidents:read`)
plus access to the incident. CSV takes the matching list endpoint's filters,
`q` and `sort` (no paging), streams UTF-8 with a BOM, writes UTC times as
`...Z`, neutralises formula cells (`= + - @ TAB CR LF` get a leading `'`),
never includes passwords (accounts carry `Has Password` only) and supports
`defang=true` for indicator columns. File names are
`incident-<n>-TLP_<LEVEL>-<entity>-<YYYYMMDDTHHMMZ>.csv`. Each export writes a
`data_access` audit row (`export_csv` / `export_stix`) with the entity, row
count and filters.

STIX is built as an object model and every pattern value is escaped for a STIX
string literal, so values cannot break out of a pattern. Every object
references the incident's TLP `marking-definition` (white, green, amber and
red use the STIX 2.1 TLP 1.0 ids; `amber_strict` is marked TLP:AMBER plus a
`TLP:AMBER+STRICT` statement marking).

`/correlate-iocs` bounds its input (≤ 1000 values of ≤ 2048 characters;
`ioc_types` from `ip, domain, hash, hostname, file, all`), checks
`incident_id` access (404 / 403) and, without `ioc_values`, correlates the
values recorded in that incident. `/bulk-enrich` validates every value
against its type, checks `incident_id` access, refuses a restricted incident
as a whole (403 `tlp_restricted`: `red`, and `amber_strict` unless the org
allows it), marks values found in restricted incidents `blocked`, and returns
the `providers` that answered. Both are audited (`correlate_iocs`,
`bulk_enrich`).

`POST /threat-intel/misp/push` without an `incident_id` must carry `tlp`
(`white|green|amber|amber_strict|red`; 400 `tlp_required` otherwise). `red` is
always refused and `amber_strict` only when the organization allows it (403
`tlp_restricted`); the event is tagged with that TLP. With an `incident_id`
the incident's TLP applies.

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
| GET    | `/organization/security-policy`           | Security policy `{policy, version, defaults, bounds, stats, is_platform_org, updated_by, updated_at}` (`organizations:manage`) |
| PUT    | `/organization/security-policy`           | `{policy: {<section>: {...}}, version}` (or `If-Match`); partial sections keep other values; `400 validation_error {fields}`, `409 conflict`, `428` without a version |
| GET    | `/users/{id}/sessions`                    | Active sign-in sessions (`current` marks yours); self, or `users:manage` in the same org; interactive sessions only |
| DELETE | `/users/{id}/sessions/{sid}`              | Revoke one session (its access and refresh tokens stop working at once; other sessions are unaffected) |
| DELETE | `/users/{id}/sessions`                    | Revoke every session; `?except_current=true` keeps yours ("sign out other devices") |
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
`red`/`amber_strict` → `local_only`, others `allow`). Self-registration is not an organization
setting: it is `provisioning.registration_enabled` in the platform organization's security policy
(**closed by default**); `registration_enabled` and `security` are rejected here.
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
