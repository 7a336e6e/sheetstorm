# Changelog

## Unreleased

### Behavior changes (upgrade notes)

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

### New

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

### Other fixes

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
