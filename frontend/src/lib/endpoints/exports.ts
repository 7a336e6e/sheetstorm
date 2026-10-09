/**
 * Exports, STIX, IOC correlation and bulk enrichment (W3-DFIR-C).
 *
 * CSV is produced by the server (`GET /incidents/<id>/export/<entity>`): it
 * takes the same filter / sort / search params as the entity's list endpoint,
 * so "export what I filtered" is built from the URL state that
 * `usePaginatedQuery({ urlKey })` writes (`<tab>.q`, `<tab>.sort`,
 * `<tab>.f.<name>`). Every export needs `incidents:export` plus the entity's
 * read permission (the menu hides what the user cannot get; the API decides).
 */
import api, { downloadTo, withQuery } from '@/lib/api'
import { parseListState, type ListState } from '@/hooks/use-paginated-query'
import type {
  BulkEnrichResponse,
  EnrichmentGate,
  EnrichIOCType,
  EnrichRequestItem,
  ExportEntity,
  IOCCorrelationResponse,
  TLPLevel,
} from '@/types'

/** Permission that gates every export (in addition to the entity read permission). */
export const EXPORT_PERMISSION = 'incidents:export'

export interface TabExport {
  entity: ExportEntity
  label: string
  /** Entity read permission (the API requires it too). */
  permission: string
  /** Holds indicator values: offer the defanged variant. */
  ioc: boolean
}

/** Incident tab id (`?tab=`) -> exportable entity. The tab id is also its list `urlKey`. */
export const TAB_EXPORTS: Record<string, TabExport> = {
  events: { entity: 'timeline', label: 'Events', permission: 'timeline:read', ioc: false },
  hosts: { entity: 'hosts', label: 'Hosts', permission: 'hosts:read', ioc: false },
  accounts: { entity: 'accounts', label: 'Accounts', permission: 'accounts:read', ioc: false },
  network: { entity: 'network-iocs', label: 'Network IOCs', permission: 'network_iocs:read', ioc: true },
  'host-iocs': { entity: 'host-iocs', label: 'Host IOCs', permission: 'host_iocs:read', ioc: true },
  malware: { entity: 'malware', label: 'Malware', permission: 'malware:read', ioc: true },
  tasks: { entity: 'tasks', label: 'Tasks', permission: 'tasks:read', ioc: false },
}

const EMPTY_DEFAULTS: ListState = { page: 1, perPage: 50, filters: {} }
/** The Leads view of the Tasks tab (LeadsView) keeps its own list state and defaults. */
const LEADS_DEFAULTS: ListState = { ...EMPTY_DEFAULTS, sort: '-updated_at', filters: { lead_outcome: 'open' } }
const TASKS_VIEW_PARAM = 'tasks.view'

type ParamsLike = Pick<URLSearchParams, 'get' | 'forEach'>

/**
 * Export params for a tab from the page URL: its search text, sort and
 * filters, exactly as the table shows them (paging is not part of an export).
 */
export function exportParamsFromUrl(params: ParamsLike, tab: string): Record<string, string> {
  const leads = tab === 'tasks' && params.get(TASKS_VIEW_PARAM) === 'leads'
  const state = leads
    ? parseListState(params, 'leads', LEADS_DEFAULTS)
    : parseListState(params, tab, EMPTY_DEFAULTS)
  const out: Record<string, string> = {}
  for (const [name, value] of Object.entries(state.filters)) {
    if (value !== '') out[name] = value
  }
  if (leads) out.task_type = 'investigative_lead'
  if (state.q) out.q = state.q
  if (state.sort) out.sort = state.sort
  return out
}

export function csvEndpoint(incidentId: string, entity: ExportEntity, params: Record<string, string> = {}): string {
  return withQuery(`/incidents/${incidentId}/export/${entity}`, params)
}

export const stixEndpoint = (incidentId: string) => `/incidents/${incidentId}/export/stix`

export const exportsApi = {
  /** Download a CSV (server names the file; `fallbackName` is the safety net). */
  downloadCsv: (
    incidentId: string,
    entity: ExportEntity,
    opts: { params?: Record<string, string>; defang?: boolean; fallbackName: string }
  ) =>
    downloadTo(
      csvEndpoint(incidentId, entity, { ...(opts.params ?? {}), ...(opts.defang ? { defang: 'true' } : {}) }),
      { fallbackName: opts.fallbackName }
    ),

  downloadStix: (incidentId: string, fallbackName: string) =>
    downloadTo(stixEndpoint(incidentId), { fallbackName }),

  /** Other incidents sharing values with this one. */
  correlate: (incidentId: string) =>
    api.post<IOCCorrelationResponse>('/correlate-iocs', { incident_id: incidentId }),

  bulkEnrich: (incidentId: string, items: EnrichRequestItem[]) =>
    api.post<BulkEnrichResponse>('/bulk-enrich', { incident_id: incidentId, ioc_values: items }),
}

// ─── Enrichment (TLP gate) ───────────────────────────────────────────────

export const TLP_LABELS: Record<TLPLevel, string> = {
  white: 'TLP:WHITE',
  green: 'TLP:GREEN',
  amber: 'TLP:AMBER',
  amber_strict: 'TLP:AMBER+STRICT',
  red: 'TLP:RED',
}

/**
 * What the UI shows before enriching values of an incident (mirrors the server
 * block in `services/egress_policy.py`; the API stays authoritative):
 * - `red`: blocked, always (no setting unblocks it);
 * - `amber_strict`: blocked unless the org allows it, then a destructive
 *   confirmation with an explicit acknowledgement;
 * - everything else: a plain confirmation.
 */
export function enrichmentGate(tlp: TLPLevel | string | undefined, allowAmberStrict: boolean): EnrichmentGate {
  if (tlp === 'red') return 'blocked'
  if (tlp === 'amber_strict') return allowAmberStrict ? 'acknowledge' : 'blocked'
  return 'confirm'
}

const HEX = /^[0-9a-fA-F]+$/
const IPV4 = /^\d{1,3}(\.\d{1,3}){3}$/
const HASH_TYPES: Record<number, EnrichIOCType> = { 32: 'md5', 40: 'sha1', 64: 'sha256' }

/**
 * Enrichment type for an IOC value, or null when the value is not something
 * the providers can look up (the server validates the same shapes).
 */
export function enrichTypeFor(value: string | null | undefined): EnrichIOCType | null {
  const v = (value ?? '').trim()
  if (!v) return null
  if (IPV4.test(v) && v.split('.').every((o) => Number(o) <= 255)) return 'ip'
  if (HEX.test(v) && HASH_TYPES[v.length]) return HASH_TYPES[v.length]
  if (/^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9.-]{1,253}$/.test(v)) return 'email'
  if (/^[A-Za-z0-9_]([A-Za-z0-9_.-]{0,251}[A-Za-z0-9_])?$/.test(v) && v.includes('.')) return 'domain'
  return null
}

/** Unique, enrichable `{value, type}` items from rows (unsupported values are counted, not sent). */
export function buildEnrichItems(values: Array<string | null | undefined>): {
  items: EnrichRequestItem[]
  skipped: number
} {
  const seen = new Set<string>()
  const items: EnrichRequestItem[] = []
  let skipped = 0
  for (const raw of values) {
    const value = (raw ?? '').trim()
    if (!value) continue
    const key = value.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    const type = enrichTypeFor(value)
    if (type) items.push({ value, type })
    else skipped += 1
  }
  return { items, skipped }
}
