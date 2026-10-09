/**
 * Audit governance and admin overview types (backend `endpoints/audit.py`,
 * `endpoints/admin_status.py`, `services/{audit_service,system_status_service}.py`).
 */
import type { AuditLog } from './index'

/**
 * One entry of `details.changes` (backend `utils/audit_diff.py`), one shape
 * everywhere:
 *   scalar / dict change  `{from, to}`
 *   list of scalars       `{added, removed}`
 *   sensitive field       `{changed: true}` (values never stored)
 * Nested dicts are flattened to dotted keys (`settings.ai_tlp_policy.red`).
 */
export interface AuditChange {
  from?: unknown
  to?: unknown
  added?: unknown[]
  removed?: unknown[]
  changed?: boolean
}

/** `details.changes`; `_truncated: true` when the diff hit the 100-key cap. */
export type AuditChanges = Record<string, AuditChange | boolean>

/** An audit row as `GET /audit-logs` returns it (full `to_dict`, chain columns included). */
export interface AuditLogEntry extends AuditLog {
  organization_id?: string | null
  user_id?: string | null
  chain_seq?: number | null
  prev_hash?: string | null
  row_hash?: string | null
  chain_key_id?: string | null
}

export type AuditEventType =
  | 'authentication'
  | 'authorization'
  | 'data_access'
  | 'data_modification'
  | 'admin_action'
  | 'security_event'
  | 'system_event'

/** `status` filter classes (or a literal HTTP status code). */
export type AuditStatusClass = 'success' | 'client_error' | 'server_error' | 'denied'

/**
 * Filter params of `GET /audit-logs` / `stats` / `export`
 * (backend `audit_service.build_audit_query`). All optional strings.
 */
export interface AuditLogFilters {
  user_id?: string
  user_email?: string
  /** ISO 8601 (UTC). */
  start_date?: string
  end_date?: string
  /** Comma list of event types. */
  event_type?: string
  /** Exact action. */
  action?: string
  /** Substring of the action (LIKE wildcards escaped server side). */
  action_contains?: string
  resource_type?: string
  resource_id?: string
  incident_id?: string
  status?: AuditStatusClass | string
  /** IP address or CIDR. */
  ip?: string
  /** 'true': only rows with `details.changes`. */
  has_changes?: string
  q?: string
}

export type AuditExportFormat = 'csv' | 'jsonl'

export interface AuditFacets {
  actions: string[]
  resource_types: string[]
  event_types: AuditEventType[]
}

export interface AuditStats {
  by_event_type: Record<string, number>
  by_day: Record<string, number>
  total: number
}

export interface AuditSettings {
  /** null = keep forever. */
  audit_retention_days: number | null
  legal_hold: boolean
  legal_hold_reason: string | null
  legal_hold_set_by: string | null
  legal_hold_set_at: string | null
  min_retention_days: number
  max_retention_days: number
}

export interface AuditSettingsUpdate {
  audit_retention_days?: number | null
  legal_hold?: boolean
  legal_hold_reason?: string
  /** Required (true) to shorten retention; otherwise 409 `confirmation_required`. */
  confirm?: boolean
}

/** 409 body of `PUT /admin/audit-settings` when shortening without `confirm`. */
export interface AuditRetentionConflict {
  error: 'confirmation_required'
  message: string
  would_purge: number
  cutoff: string
}

export type AuditIntegrityReason =
  | 'hash_mismatch'
  | 'prev_hash_mismatch'
  | 'gap'
  | 'duplicate'
  | 'head_mismatch'
  | string

export interface AuditIntegrityFailure {
  seq: number | null
  id: string | null
  reason: AuditIntegrityReason
}

/** `GET /admin/audit-integrity` (backend `audit_service.verify_chain`). */
export interface AuditIntegrityResult {
  ok: boolean
  organization_id: string | null
  chain_key: string
  checked: number
  failure_count: number
  failures: AuditIntegrityFailure[]
  unverifiable_rotated_key: number
  legacy_unchained: number
  head_seq: number
  head_hash: string | null
  purged_through_seq: number
  first_seq: number | null
  last_seq: number | null
  key_id: string
  verified_at: string
}

// ── System status ───────────────────────────────────────────────────────

/** What a failed probe reports instead of its section. */
export interface ProbeFailure {
  ok: false
  error: string
}

export interface StatusStorage {
  backend?: 's3' | 'google_drive' | 'local' | string
  /** Infra (platform admins), s3. */
  bucket?: string | null
  endpoint_host?: string | null
  /** Infra (platform admins), local. */
  disk?: { ok: true; total_bytes: number; free_bytes: number; used_pct: number | null } | ProbeFailure
  ok?: false
  error?: string
}

export interface StatusAiProvider {
  provider: string
  source: 'integration' | 'env'
  last_tested_at: string | null
  last_test_ok: boolean | null
}

export interface StatusIntegration {
  id: string
  type: string
  name: string
  is_enabled: boolean
  last_tested_at: string | null
  last_test_ok: boolean | null
  last_used_at: string | null
  last_error: string | null
}

export interface StatusCounts {
  users: number
  active_users: number
  incidents: number
  open_incidents: number
  artifacts: number
  artifact_bytes: number
}

export interface AuditChainStatus {
  head_seq: number
  head_hash: string | null
  purged_through_seq: number
  last_verified_at: string | null
  last_verify_ok: boolean | null
  legacy_unchained: number
}

export interface StatusAudit {
  retention_days: number | null
  legal_hold: boolean
  total_rows: number
  oldest_entry_at: string | null
  chain: AuditChainStatus
}

export interface StatusApp {
  version: string | null
  commit: string | null
  environment: string
}

export interface StatusDatabase {
  ok: true
  latency_ms: number
  server_version: string
}

export interface StatusAlembic {
  ok: true
  current: string[]
  head: string[]
  up_to_date: boolean
}

export interface StatusRedis {
  ok: true
  latency_ms: number
}

export interface StatusRateLimiting {
  enabled: boolean
  storage: string
  default_limit: string
}

/**
 * `GET /admin/system-status`. Organization sections always; the
 * deployment-global infra sections (`app`, `database`, `alembic`, `redis`,
 * `rate_limiting`, storage details) only for platform admins
 * (`infra_visible`). Any section may be a `ProbeFailure`.
 */
export interface SystemStatus {
  infra_visible: boolean
  storage: StatusStorage
  ai_providers: StatusAiProvider[] | ProbeFailure
  integrations: StatusIntegration[] | ProbeFailure
  counts: StatusCounts | ProbeFailure
  audit: StatusAudit | ProbeFailure
  app?: StatusApp | ProbeFailure
  database?: StatusDatabase | ProbeFailure
  alembic?: StatusAlembic | ProbeFailure
  redis?: StatusRedis | ProbeFailure
  rate_limiting?: StatusRateLimiting | ProbeFailure
  generated_at: string
}

// ── Admin overview ──────────────────────────────────────────────────────

export interface AdminOverviewUsers {
  total: number
  active: number
  disabled: number
  by_role: Record<string, number>
  mfa_enabled: number
  mfa_adoption_pct: number | null
  admins_without_mfa: number
  /** null until the lockout / invite features report a count. */
  locked: number | null
  pending_invites: number | null
}

export interface RecentAdminAction {
  id: string
  action: string
  resource_type: string | null
  resource_id: string | null
  user_email: string | null
  created_at: string | null
  has_changes: boolean
}

/** `GET /admin/overview`. */
export interface AdminOverview {
  users: AdminOverviewUsers
  active_admin_count: number
  last_admin_warning: boolean
  recent_admin_actions: RecentAdminAction[]
  registration_enabled: boolean
}
