/**
 * Audit log filters: URL state ↔ list state ↔ API params.
 *
 * The activity page keeps its list state in the URL through
 * `usePaginatedQuery({ urlKey: AUDIT_URL_KEY })`, i.e. `audit.page`,
 * `audit.per`, `audit.sort`, `audit.q` and `audit.f.<filter>`. Filter names
 * are the backend param names (`audit_service.build_audit_query`), so the
 * hook sends them as-is; these helpers whitelist them for the export and
 * build shareable links (overview → activity).
 */
import {
  parseListState,
  serializeListState,
  type ListState,
} from '@/hooks/use-paginated-query'
import type { AuditEventType, AuditLogFilters, AuditStatusClass } from '@/types'

export const AUDIT_URL_KEY = 'audit'
export const ACTIVITY_PATH = '/dashboard/activity'
export const AUDIT_DEFAULT_SORT = '-created_at'
export const AUDIT_DEFAULT_PER_PAGE = 50
export const AUDIT_PAGE_SIZES = [25, 50, 100, 200]

/** Filter params the backend understands (minus `q`, which is list state). */
export const AUDIT_FILTER_KEYS = [
  'user_id',
  'user_email',
  'start_date',
  'end_date',
  'event_type',
  'action',
  'action_contains',
  'resource_type',
  'resource_id',
  'incident_id',
  'status',
  'ip',
  'has_changes',
] as const
export type AuditFilterKey = (typeof AUDIT_FILTER_KEYS)[number]

export const AUDIT_DEFAULTS: ListState = {
  page: 1,
  perPage: AUDIT_DEFAULT_PER_PAGE,
  sort: AUDIT_DEFAULT_SORT,
  q: undefined,
  filters: {},
}

/** Public sort names (backend `audit_service.SORTABLE`). */
export const AUDIT_SORT_KEYS = [
  'created_at',
  'event_type',
  'action',
  'user_email',
  'status_code',
  'resource_type',
  'chain_seq',
] as const

export const EVENT_TYPES: { value: AuditEventType; label: string; short: string }[] = [
  { value: 'authentication', label: 'Authentication', short: 'Auth' },
  { value: 'authorization', label: 'Authorization', short: 'Authz' },
  { value: 'data_access', label: 'Data access', short: 'Access' },
  { value: 'data_modification', label: 'Data modification', short: 'Modify' },
  { value: 'admin_action', label: 'Admin action', short: 'Admin' },
  { value: 'security_event', label: 'Security event', short: 'Security' },
  { value: 'system_event', label: 'System event', short: 'System' },
]

export const STATUS_OPTIONS: { value: AuditStatusClass; label: string }[] = [
  { value: 'success', label: 'Success (<400)' },
  { value: 'client_error', label: 'Client error (4xx)' },
  { value: 'denied', label: 'Denied (401/403)' },
  { value: 'server_error', label: 'Server error (5xx)' },
]

const KEY_SET: ReadonlySet<string> = new Set(AUDIT_FILTER_KEYS)

export function isAuditFilterKey(key: string): key is AuditFilterKey {
  return KEY_SET.has(key)
}

/**
 * API params for the current list state: known filters (trimmed, empties
 * dropped) plus `q`. Used for the export and the stats call so they match
 * the rows on screen exactly.
 */
export function auditApiFilters(state: Pick<ListState, 'filters' | 'q'>): AuditLogFilters {
  const out: Record<string, string> = {}
  for (const key of AUDIT_FILTER_KEYS) {
    const v = state.filters[key]?.trim()
    if (v) out[key] = v
  }
  const q = state.q?.trim()
  if (q) out.q = q
  return out as AuditLogFilters
}

/** Number of active filters (incl. the search text), for the toolbar badge. */
export function countActiveFilters(state: Pick<ListState, 'filters' | 'q'>): number {
  return Object.keys(auditApiFilters(state)).length
}

/** Selected event types of a comma-list filter value. */
export function parseEventTypes(value: string | undefined): AuditEventType[] {
  if (!value) return []
  const valid = new Set<string>(EVENT_TYPES.map((t) => t.value))
  return value
    .split(',')
    .map((s) => s.trim())
    .filter((s): s is AuditEventType => valid.has(s))
}

/** Toggle one event type in a comma-list value; undefined when none is left. */
export function toggleEventType(value: string | undefined, type: AuditEventType): string | undefined {
  const current = parseEventTypes(value)
  const next = current.includes(type) ? current.filter((t) => t !== type) : [...current, type]
  // Keep a stable order so the URL does not depend on click order.
  const ordered = EVENT_TYPES.map((t) => t.value).filter((t) => next.includes(t))
  return ordered.length ? ordered.join(',') : undefined
}

type ParamsLike = Pick<URLSearchParams, 'get' | 'forEach'>

/** List state of the activity page from its URL params. */
export function parseAuditUrl(params: ParamsLike): ListState {
  return parseListState(params, AUDIT_URL_KEY, AUDIT_DEFAULTS)
}

/** Query string (without `?`) for a list state, omitting defaults. */
export function serializeAuditUrl(state: ListState, base: ParamsLike = new URLSearchParams()): string {
  return serializeListState(base, AUDIT_URL_KEY, state, AUDIT_DEFAULTS).toString()
}

/**
 * Link to the activity page with these filters (and optional sort), e.g.
 * `activityHref({ event_type: 'admin_action', has_changes: 'true' })`.
 */
export function activityHref(filters: AuditLogFilters = {}, sort?: string): string {
  const clean: Record<string, string> = {}
  Object.entries(filters).forEach(([k, v]) => {
    if (typeof v === 'string' && v.trim() && (isAuditFilterKey(k) || k === 'q')) clean[k] = v.trim()
  })
  const { q, ...rest } = clean
  const qs = serializeAuditUrl({ ...AUDIT_DEFAULTS, sort: sort ?? AUDIT_DEFAULT_SORT, q, filters: rest })
  return qs ? `${ACTIVITY_PATH}?${qs}` : ACTIVITY_PATH
}

/**
 * Plain (un-prefixed) filter params such as `?event_type=admin_action&has_changes=true`
 * (older links, docs) rewritten into the `audit.*` form. Returns the new
 * query string, or null when there is nothing to migrate.
 */
export function migrateLegacyParams(params: ParamsLike): string | null {
  const legacy: Record<string, string> = {}
  let hasPrefixed = false
  params.forEach((value, key) => {
    if (key.startsWith(`${AUDIT_URL_KEY}.`)) hasPrefixed = true
    else if ((isAuditFilterKey(key) || key === 'q') && value.trim()) legacy[key] = value.trim()
  })
  if (hasPrefixed || Object.keys(legacy).length === 0) return null
  const rest = new URLSearchParams()
  params.forEach((value, key) => {
    if (!isAuditFilterKey(key) && key !== 'q') rest.append(key, value)
  })
  const { q, ...filters } = legacy
  return serializeAuditUrl({ ...AUDIT_DEFAULTS, q, filters }, rest)
}

/** True when the list shows the newest rows unfiltered (live updates apply). */
export function isLiveView(state: ListState): boolean {
  return (
    state.page === 1 &&
    countActiveFilters(state) === 0 &&
    (state.sort ?? AUDIT_DEFAULT_SORT) === AUDIT_DEFAULT_SORT
  )
}
