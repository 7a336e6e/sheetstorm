# Changelog

## Unreleased

### Behavior changes (upgrade notes)

- **Archived incidents are hidden and read-only.** Without `incidents:archive`
  an archived incident answers 404 everywhere (detail, sub-resources, search,
  websocket rooms, MCP), even through an old link. Holders of
  `incidents:archive` can open it from Admin → Archived Incidents (titles now
  link to it) and browse it read-only: edit controls are hidden and every
  mutating request answers 409 `incident_archived` until it is unarchived
  (an Unarchive button sits in the archived banner).
- **Timestamps are UTC.** Timestamps without an offset are now stored as UTC.
  Events entered in local time before this fix were stored shifted by the
  server/database session offset; review timelines created before the upgrade
  if the original entry time matters.
- **Registration is closed by default on fresh installs.** Existing installs
  keep their current setting (the migration writes `registration_enabled: true`
  into the existing default organization when the key is absent).
- **`incidents:delete` is removed** from every role, including custom roles.
  Archive/unarchive use `incidents:archive`; permanent deletion uses
  `incidents:purge` (Administrator only).
- **System roles are immutable.** Built-in roles can no longer be edited or
  deleted; clone them into an organization custom role instead.
- **Permissions are additive across roles.** A user's permissions and incident
  visibility are the union of all their roles (for example Viewer + Analyst
  sees TLP:WHITE incidents plus team-scoped incidents).
- **Manager now receives admin-action activity events** (`activity:new` goes to
  every holder of `audit_logs:read`).
- **`GET /teams` requires `teams:read`.**
- **`tasks:delete` now works for custom roles** (it is checked as a permission,
  not a role name).

- **Legacy per-entity socket events are gone.** `incident_updated`,
  `timeline_event_added|updated|deleted`, `task_added|updated|deleted`,
  `task_comment_added`, `case_note_created|updated|deleted`, `host_added`,
  `graph_node_added|updated|deleted` and `graph_edge_added|updated|deleted`
  are replaced by `entity:changed` in per-scope rooms (and `incident:resync`
  for bulk changes); see `assets/docs/websocket-events.md`. External socket
  consumers of the old names must switch.
- **Optimistic concurrency on incident entities.** PUT/PATCH/DELETE accept
  `If-Match: "<version>"` (or `expected_version` in the body) and return
  `409 conflict` with the current row when it is stale; responses carry `ETag`.
  Requests without either keep last-write-wins. Two concurrent writes to the
  same row now give one `409` instead of a silent lost update.

- **No default admin password.** The seed no longer uses `ChangeMe123!` /
  `changeme`: with `ADMIN_PASSWORD` empty (the new default) or below the
  password policy, a random password is generated and printed **once** by the
  seed step (`start.sh` output). The seeded admin must change it at first
  sign-in (`403 password_change_required` until then). Re-running the seed on
  an existing install changes nothing.
- **Generic login errors and lockout.** Unknown, disabled, locked and
  wrong-password logins all return the same 401. Accounts lock after
  `LOGIN_LOCKOUT_THRESHOLD` (default 10) bad passwords/MFA codes for
  `LOGIN_LOCKOUT_MINUTES` (default 15); admins can unlock early.
- **Restricted accounts and fail-closed revocation.** Accounts that must change
  their password can only reach the change-password routes (sockets connect as
  anonymous). Session revocation (password change/reset, disable, force
  logout) fails closed: `503 revocation_failed` when Redis is unavailable.
- **User delete is safe.** Deleting a user referenced by records (incidents,
  evidence items, custody entries, ...) returns `409 user_has_records` with
  counts; deactivate instead (`?anonymize=true` for record-free users). Emails
  are stored lowercased.
- **Audit log is append-only and hash-chained.** `audit_logs` rows can no longer
  be updated or deleted (only the retention purge job may delete), each row is
  linked into a per-organization keyed hash chain (`AUDIT_CHAIN_KEY`, falls back
  to `SECRET_KEY` with a startup warning), and the audit foreign keys are
  dropped (rows keep the ids of deleted users/incidents). Rows written before
  the upgrade are not chained.
- **Audit `action` filter is exact.** `GET /audit-logs?action=` now matches
  exactly; use `action_contains=` for substring search.
- **Artifact delete is a tombstone.** The stored bytes are purged, but the row,
  its hashes and its custody history are kept (`deleted_at`, `deleted_by`,
  `deletion_reason`); lists and counts hide tombstones (`include_deleted=true`
  shows them), download/verify return 410.
- **Evidence register.** Every existing artifact is backfilled into an `EV-####`
  evidence item (one `digital_file` item per artifact). The custody ledger is
  append-only and hash-chained (v3); legacy custody rows keep verifying their
  signatures but are not chained. The migration downgrade is lossy (evidence
  items, v3 entries and tombstoned artifacts are dropped).
- **Incident purge** (`DELETE /incidents/<id>/permanent`) is blocked (409) while
  any artifact or evidence item is under legal hold, and logs the final ledger
  heads before deleting. Deleting an organization that has evidence is blocked.
- **Evidence legal holds keep audit rows.** The audit retention purge keeps the
  rows of incidents with an artifact or evidence item under legal hold.
- **No Administrator bypass in the web UI.** Every page, nav entry and admin tab
  is shown by permission only. The admin `sso`, `security` and `organization`
  pages are removed (404); their settings live under Admin → Settings.
- **Roles page uses the server permission catalog**; user modals only offer
  roles within the editor's own privileges and enforce the self-edit rules.
- **Archive and incident-list actions are permission-gated**
  (`incidents:archive`); the incidents list is server-paged, so every incident
  is reachable (not only the first 20).
- **Incident tabs are server-paged** (page size 50) with filters, sort and the
  selected row in the URL (`?tab=&row=`); Viewers see no mutation controls;
  task and case-note actions are checked by permission, not role name; deletes
  ask for confirmation and errors show as toasts. The events search no longer
  matches MITRE technique text.
- **Password login on an SSO-only account returns the generic 401.** It no
  longer answers "Please login with <provider>" (which revealed that the
  account exists); the attempt counts toward lockout like a wrong password.
- **Duplicate assignments return `409 already_assigned`** instead of
  `409 conflict` (incident assignments and user role assignments). `conflict`
  now only means an optimistic-concurrency version mismatch; API clients that
  matched the old code must switch.
- **`GET /storage/stats` no longer includes `disk_usage.path`** (the server
  filesystem path) except for platform admins.
- **Settings tabs are read-only without the integration permissions.**
  Integrations, AI Providers, Storage, Threat Intel and Notifications show add
  / test / configure / delete and Google Drive controls only to holders of
  `integrations:create`, `integrations:update` or `integrations:delete`.

- **Stricter task validation.** `assignee_id` must be an active user of the
  incident's organization (`400 invalid_assignee`); `parent_task_id` must be a
  task of the same incident without creating a cycle
  (`400 invalid_parent_task`); `evidence_refs` (at most 50) must point at
  records of the same incident (`400 invalid_evidence_refs`). Task responses
  carry `evidence` with labels resolved by the server; existing
  `extra_data.linked_entities` are backfilled into `evidence_refs`.
- **Host `acquisition_status` is allowlisted** (four booleans plus
  `acquired_at`; anything else is 400). The Hosts tab no longer offers the
  `monitoring` containment option, which the backend always rejected.
- **Incident create and update validate more.** Create returns 400 for a
  foreign team or lead responder or a `detected_at` in the future, and assigns
  and notifies the lead responder. PUT validates the IR milestones (no value
  more than 5 minutes in the future; `first_malicious <= detected <= contained
  <= eradicated <= recovered <= closed`, otherwise 400). A phase-only change
  stamps the matching milestone; reopening clears `closed_at`. Non-object JSON
  bodies return 400. The dashboard covers every incident you can access.
- **API-key tokens are refused on interactive-only routes** (password change,
  MFA setup/verify/disable, preferences); service accounts cannot sign in
  interactively.
- **Evidence exports need `incidents:export`** (C24) on top of the read
  permission: evidence register CSV/PDF and item/incident custody bundles.
  `sheetstorm_transfer_evidence` refuses unless `attested=true`.
- **`custody_chain_verified` audit rows** are written for explicit chain
  verifications, exports and any broken/compromised result; plain evidence
  detail and custody-list views no longer write one per read.
- **`GET /storage/stats` requires `integrations:read` or
  `organizations:manage`** (the Storage settings tab's gate); Viewers no longer
  read org storage totals. The MITRE test-suggest button (Settings → Threat
  Intel) needs `incidents:read`.
- **Edit User has no Active switch or password field.** Disable/enable and
  password reset are row actions on the users page; deleting a user who
  authored records is refused and the UI suggests disabling instead.

- **Self-registration moved to Settings → Security** (platform organization
  only). The setting now lives in the organization security policy
  (`provisioning.registration_enabled`); the upgrade copies each
  organization's stored value there and removes the old settings key.
  `PUT /organization` with `registration_enabled` is now a 400.
- **Password policy is enforced on every password write** (register, change,
  admin create and reset, invite accept, reset complete): symbol rule, 72-byte
  cap, password history and an optional maximum age that forces a change at
  the next sign-in. Violations are 400 with error code `password_policy` and a
  `violations` list.
- **Sign-ins are tracked sessions.** Logout revokes the session; "sign out
  other devices" is available on the profile page. Token lifetimes are per
  organization (defaults unchanged: 60-minute access, 7-day refresh).
- **STIX and CSV exports need `incidents:export`** on top of the read
  permission, so Analyst, Operator and Viewer lose STIX export. STIX bundles
  carry TLP markings.
- **Reports are immutable snapshots.** A generated PDF is stored with its
  SHA-256 and every download re-checks it (`X-Report-SHA256`; an altered or
  missing file is a 409 `integrity_error`). Reports issued before the upgrade
  are re-rendered and marked `X-Report-Snapshot: legacy`.
- **Attack-graph auto-generate merges by default.** It only adds missing nodes
  and edges and never moves or deletes existing ones; `mode: "replace"` needs
  `confirm: true`.
- **Due-date reminders:** the first reminder job run on an existing install
  sends one "overdue" notification per task or improvement action that is
  already overdue.
- **Playbook create/edit/delete needs `templates:manage`**, and holders can
  edit any playbook of the organization. `GET /playbooks` also returns the
  built-in playbooks (`is_builtin`).
- **MISP push without an incident needs an explicit `tlp`.** `bulk-enrich`
  and `correlate-iocs` validate their input and are audited.
- **The Artifacts tab is now Evidence.** Old `?tab=artifacts` links still
  open it.
- **`responded_at` is stamped automatically** on the first assignment
  (`POST /incidents/<id>/assignments`) or the first status change away from
  open.
- **CORS exposes `Content-Disposition`, `X-Report-SHA256`, `X-Report-Id` and
  `ETag`** to an allowed cross-origin frontend.

### New

- **Guided tours:** a short walkthrough on the dashboard, incidents, incident,
  users, settings, activity and case-template pages, shown once per page and
  replayable from "Page tour" in the sidebar. Administrators switch tours on or
  off (or replay them) per user from the Users page row menu, or for everyone
  from "Guided tours" in the page header. Seen tours are kept per user.
- **Case templates are editable:** built-ins stay as shipped, but "Customize"
  creates your organization's copy and opens it in the editor (optionally
  deactivating the built-in); any template, built-in included, can be
  deactivated per organization. The editor has an example and a format reference.
- **One-click DFIQ import:** platform administrators can import Google's DFIQ
  investigative questions (Apache-2.0) from Admin → Case Templates. The server
  downloads one pinned DFIQ commit from GitHub (or takes the same archive as an
  upload on offline installs), refuses it unless its SHA-256 matches the value
  pinned in code, parses it in memory with `yaml.safe_load`, and stores it in
  the database, so it survives rebuilds and reaches every worker within 30 s.
- **Admin-configurable rate limits:** every rate-limited route belongs to a
  named group; platform administrators can change limits, disable groups or turn
  rate limiting off from Settings → Security → Rate limiting, without a restart.
  Weakening changes need confirmation and are logged as security events;
  `RATE_LIMIT_SETTINGS_LOCKED=true` pins the limits to the environment. Report
  generation (PDF/AI) gains its own limit (`reports_generate`, 10/minute).
- **Decision & response-action log:** a "Decisions & Actions" incident tab
  records decisions (D-NNN) and response actions (A-NNN) with lifecycle steps,
  approvals/authorizations by name, and optional host/account state changes with
  rollback. Every change is a hash-chained, signed revision (append-only in the
  database). Privileged decisions need `decisions:read_privileged` and never
  reach reports, AI or MCP. Export (CSV/JSON/PDF) needs `incidents:export`; full
  PDF reports include a decision-log appendix. Five MCP tools (none can approve,
  authorize or mark a decision privileged).
- **Investigative questions UI:** an incident "Questions" tab (answer with
  status and confidence, add from the library, apply a case template with a dry
  run preview), progress and custom fields on the Overview, a case-template
  picker on the new-incident form, built-in playbooks on the Playbook tab (the AI
  summary action honours the AI TLP policy), and Admin → Case Templates
  (clone built-ins, edit organization templates as checked JSON).
- **RFC 3161 anchoring (optional):** with `TSA_URL` set, the incident custody
  ledger head can be timestamped by a trusted timestamp authority
  (`POST …/evidence/custody/anchor`); verification reports `anchor_status`, and
  the incident bundle README explains offline `openssl ts -verify`. Off by default.
- **Audit governance:** filtered audit search, CSV/JSONL export
  (`audit_logs:export`, capped by `AUDIT_EXPORT_MAX_ROWS`), retention and legal
  hold (`/admin/audit-settings`), chain integrity check
  (`/admin/audit-integrity`), system status (`/admin/system-status`;
  infrastructure sections for platform admins only) and an admin overview
  (`/admin/overview`). Daily jobs `flask sheetstorm purge-audit-logs` and
  `verify-audit-chain`. Integration and team changes record before/after diffs;
  integration tests are audited. The activity feed is filtered by the
  incident-entity permissions of the reader.
- **User lifecycle:** invites (one-time join links), disable/enable, force
  logout, unlock, admin password-reset links, bulk actions, per-user activity
  and `/users/stats`; user list filters (status, team, role, MFA).
- **Evidence register and custody ledger core:** evidence items with per-item
  and per-incident hash chains, custody parties and anchors; uploads create or
  attach an evidence item in one transaction.
- **Data egress card** (Admin → Settings → General): per-TLP AI policy and the
  amber+strict enrichment switch. Google/Azure OAuth integrations can no longer
  be added. Artifact *Verify* is available to holders of `artifacts:read`.
- **Command palette** (Ctrl/⌘+K) and a global search page
  (`/dashboard/search`); notification panel fixes; dashboard analytics cover up
  to 1,000 incidents.
- **MCP:** `sheetstorm_get_system_status`, audit log filters, and 8 user
  lifecycle tools (`sheetstorm_invite_user`, `sheetstorm_list_invites`,
  `sheetstorm_revoke_invite`, `sheetstorm_disable_user`,
  `sheetstorm_enable_user`, `sheetstorm_force_logout_user`,
  `sheetstorm_unlock_user`, `sheetstorm_get_user_activity`).
- **API keys and service accounts:** scoped keys (`ssk_…`) for users and
  service accounts, exchanged at `POST /auth/token` for a 15-minute bearer;
  organization settings `api_keys_enabled` and `api_key_max_lifetime_days`.
  Keys are revoked when the owner is disabled, deleted, force-logged-out or has
  the password/MFA reset. `SHEETSTORM_API_KEY` is now the recommended MCP
  credential (stdio server and bridge).
- **DFIR triage and leads:** timeline sort by detection time, dwell and
  confidence (`confidence=`, `has_detection=` filters); host filters by triage,
  acquisition and containment and `PATCH /incidents/{id}/hosts/bulk` (up to
  500 hosts); task filters (`task_type`, `lead_outcome`, `assignee_id`, …,
  `lead_counts=true`) and a Leads view on the Tasks tab
  (`?tab=tasks&tasks.view=leads`). MCP: `sheetstorm_list_leads`,
  `sheetstorm_bulk_update_hosts`.
- **Incident overview and dashboard:** overview summary with open leads and
  hosts under analysis, IR milestone strip, create form with TLP, detection
  time and lead responder, and `GET /dashboard/stats`. MCP:
  `sheetstorm_get_dashboard_stats` plus milestone and lead fields on the
  incident tools.
- **Live incident pages:** realtime merge of every incident tab, presence
  avatars and a live indicator, a conflict dialog on stale edits (reload
  theirs / overwrite mine), redirect when access is revoked, live preview of
  attack-graph drags, and instant sign-out when an admin revokes your sessions
  (`/login?reason=session_revoked` with the reason).
- **Evidence register API:** evidence items, custody check-out / transfer /
  check-in / acknowledge, custody parties, chain verification, register
  CSV/PDF, a printable custody form and an offline verifier bundle (exit codes
  0 intact / 1 broken or tampered / 2 malformed input). MCP: 5 evidence tools; MCP clients send
  `X-SheetStorm-Client`, recorded in custody entries.
- **User administration UI:** server-paged users page with stats, filters
  (including service accounts), invites, bulk actions and a user drawer; new
  `/auth/invite`, `/auth/reset-password` and forced `/auth/change-password`
  pages.
- **Audit UI:** activity filters kept in the URL and applied server-side,
  before/after diffs, CSV/JSONL export (`audit_logs:export`), an admin
  overview page and an Audit Retention settings tab (purge preview with typed
  confirmation, legal hold reason, chain verification).
- **New environment variables:** `AUDIT_CHAIN_KEY`,
  `AUDIT_CHAIN_PREVIOUS_KEYS`, `AUDIT_EXPORT_MAX_ROWS`, `AUDIT_PURGE_BATCH_SIZE`,
  `APP_VERSION`, `GIT_COMMIT`, `LOCAL_ARTIFACT_DIR`, `LOGIN_LOCKOUT_THRESHOLD`,
  `LOGIN_LOCKOUT_MINUTES`, `PASSWORD_RESET_TTL_HOURS`, `API_KEY_PEPPER`,
  `API_KEY_TOKEN_TTL_MINUTES` (see
  `assets/docs/configuration.md`).

- **Security policy (Settings → Security):** password rules, optional MFA
  requirement with a grace period (API keys are exempt), per-organization
  token lifetimes, email-domain allowlist and default role (applied to
  registration, SSO, admin create and invites), tracked sessions with
  per-user revoke. MCP: `sheetstorm_get_security_policy` (read-only).
- **API keys UI:** Settings → API Keys (organization policy, every key,
  service accounts) and Profile → My API keys; scope picker with presets,
  secret shown once with an MCP setup hint, rotate with a grace period, revoke
  with a reason.
- **Record provenance and clock skew:** timeline events, IOCs and malware
  record their source evidence or artifact, raw timestamp and zone, MACB and
  tool; the UTC time is derived from the raw time minus the host clock skew.
  Second-analyst verification, a clock-skew editor with a re-normalize
  preview, and provenance parameters on the MCP timeline and IOC tools.
- **Investigative questions and case templates:** questions and case
  templates API, `case_template` on `POST /incidents`, custom fields; content:
  37 core questions plus the `generic-intrusion` and `ransomware` templates
  and playbooks. MCP: questions and case-template tools.
- **Post-incident metrics:** `first_malicious_at` and `responded_at`
  milestones, a response metrics card, Metrics and Improvements pages, a
  Post-Incident Review tab, improvement actions and due-date reminders through
  the jobs service (`send-due-reminders`). MCP: metrics and improvement-action
  tools; `sheetstorm_update_incident` sets and clears the two new milestones.
- **Exports and analysis:** header Export menu (per-entity CSV with the active
  tab's filters, STIX), IOC correlation dialog, bulk enrich with the TLP gate,
  graph regenerate dialog (merge or replace), report integrity badges, MISP
  TLP select. MCP: `sheetstorm_export_csv`.
- **Evidence tab:** register with paging, filters and live updates, chain
  status badge; uploading a file registers an evidence item, and physical and
  metadata-only items are supported. The drawer covers the custody timeline,
  write-once hashes (supersede), verification, check out / check in /
  transfer, acknowledge with receipt, dispose/void with typed confirmation and
  legal hold. Exports are gated by `incidents:export`.
- **MCP:** 138 tools in 21 modules (server and bridge).

### Other fixes

- The command palette (Ctrl/⌘ + K) no longer opens partly off-screen.
- The proxy re-resolves the frontend/backend/MCP containers at runtime
  (`resolver` from the container's DNS, override with `NGINX_RESOLVER`), so
  recreating one of them no longer leaves the proxy answering 502 until it is
  restarted.
- Date-time fields use the full field width, show the time zone on the label
  line, and open the calendar/time picker on click.
- The attack graph canvas grows with the window (at least 600px), so fit to
  screen keeps nodes readable on large screens; edge labels show up to 200px
  with the full text on hover.
- Native scrollbars, pickers and form controls follow the dark theme.
- The events table keeps host names and MITRE tactics on one line.
- The dashboard's TLP tiles wrap `TLP:AMBER+STRICT` instead of overflowing.
- `NGINX_RESOLVER` is passed to the proxy container (`docker-compose.yml`) and
  documented.
- Frontend unit tests run in a fixed time zone with daylight saving
  (`America/New_York`), so they pass on any machine and the DST tests always run.

- **Upgrades of databases with orphaned rows:** `flask sheetstorm repair-orphans`
  reports (and with `--apply` repairs) rows whose foreign keys point at missing
  parents; the user-lifecycle migration clears orphaned `granted_by` values and
  the evidence migration stops with a message naming the command instead of a
  NOT NULL error. See configuration.md → Database migrations.

- **Dependencies refreshed** (minor/patch only, every release at least 7 days
  old): Flask-Limiter 3.12, alembic 1.20, pydantic 2.13, openai 1.109,
  supabase 2.31, boto3 1.43, pandas 2.3 and others on the backend (SQLAlchemy is
  held at 2.0.x: 2.1 switches `postgresql://` to psycopg 3); React 19.3,
  React Flow 12.12, TypeScript 5.9, Radix and Supabase JS on the frontend.
  `scripts/lock-python.sh` now applies its 7-day cutoff to the minute.

- An update rejected with a 4xx (for example an unknown `host_id` on an IOC or
  compromised account, or an empty case-note content) no longer persists the
  fields it set before the check; audit rows record the real status of every
  response.
- Deleting an attack-graph node also tells connected clients that its edges
  are gone; changing the lead responder from the incident form updates the
  assignments panel live.
- The attack-graph "draw connection" dialog lists every timeline event, not
  only the first 50.
- Compromised-account passwords: the `********` mask no longer round-trips into
  the stored password; legacy values equal to the mask are reported as "no
  password stored".
- Spreadsheet/JSON import parses ISO-8601 dates with `Z`/offsets and rejects
  unparseable dates (400) instead of substituting the current time.
- AI report text is HTML-escaped before Markdown rendering into PDFs.
- MISP push checks incident access, refuses TLP:RED (and TLP:AMBER+STRICT unless
  the organization allows it) and tags the MISP event with the TLP.
- The web client retries only idempotent requests (GET/HEAD/OPTIONS) on server
  or network errors.
- STIX export escapes values inside STIX patterns (pattern injection).
