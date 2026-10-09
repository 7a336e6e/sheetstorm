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

### Other fixes

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
