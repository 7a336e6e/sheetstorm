/**
 * Pure merge of realtime `entity:changed` envelopes into client state.
 *
 * Version rule: an `updated` (or a `created` for a row we already hold) only
 * applies when its `version` is newer than the local copy, so the actor's own
 * echo and out-of-order events are no-ops. Without a version on either side
 * the change applies (it carries the server's latest copy).
 */
import type { EntityChange } from './types'

type Row = { id: string | number; version?: number | null }

/** True when `change` is not newer than `local` (both versions known). */
export function isStaleChange(local: { version?: number | null } | null | undefined, change: EntityChange): boolean {
  const lv = local?.version
  const cv = change.version
  return typeof lv === 'number' && typeof cv === 'number' && cv <= lv
}

function withVersion<T>(data: T, change: EntityChange): T {
  if (typeof change.version === 'number' && data && typeof data === 'object') {
    const v = (data as { version?: unknown }).version
    if (typeof v !== 'number') return { ...data, version: change.version }
  }
  return data
}

/**
 * Apply one change to a plain list (no paging): created → upsert if absent,
 * updated → replace when newer, deleted → remove. Returns the same array when
 * nothing changed, so React state setters bail out.
 */
export function applyChange<T extends Row>(list: T[], change: EntityChange): T[] {
  const idx = list.findIndex((x) => String(x.id) === change.id)
  if (change.op === 'deleted') {
    return idx === -1 ? list : list.filter((_, i) => i !== idx)
  }
  if (!change.data) return list
  const incoming = withVersion(change.data as unknown as T, change)
  if (idx === -1) {
    // An update for a row we never had is not inserted: it may not belong here.
    return change.op === 'created' ? [...list, incoming] : list
  }
  if (isStaleChange(list[idx], change)) return list
  const next = list.slice()
  next[idx] = { ...list[idx], ...incoming }
  return next
}

/** Apply a change to a single object (incident header, review). `deleted` → null. */
export function applyToObject<T extends Row>(obj: T | null, change: EntityChange): T | null {
  if (!obj || String(obj.id) !== change.id) return obj
  if (change.op === 'deleted') return null
  if (!change.data || isStaleChange(obj, change)) return obj
  return { ...obj, ...withVersion(change.data as unknown as T, change) }
}

// ── Cached list responses ────────────────────────────────────────────────

/** Query params that are list controls, not filters. */
const CONTROL_PARAMS = new Set(['page', 'per_page', 'sort', 'order', 'q', 'search', 'focus', '__all'])

export interface ListLike<T = Row> {
  items: T[]
  total?: number
  page?: number
  per_page?: number
  pages?: number
  sort?: string
  [k: string]: unknown
}

export interface MergeResult<D> {
  /** The new data (the same object when unchanged). */
  data: D
  changed: boolean
  /** The change could not be placed safely: the list must be refetched. */
  stale: boolean
}

function splitKey(key: string): { path: string; params: URLSearchParams } {
  const i = key.indexOf('?')
  return i === -1
    ? { path: key, params: new URLSearchParams() }
    : { path: key.slice(0, i), params: new URLSearchParams(key.slice(i + 1)) }
}

const ID_SEGMENT = /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+)$/i

/** Incident id named by a path (`/incidents/<id>/…`), if any. */
export function incidentOfPath(path: string): string | undefined {
  const segs = path.split('/').filter(Boolean)
  const i = segs.indexOf('incidents')
  return i !== -1 && segs[i + 1] && ID_SEGMENT.test(segs[i + 1]) ? segs[i + 1] : undefined
}

/** Whether a list at `path` can hold rows of `incidentId` (lists of no incident accept any). */
export function pathAcceptsIncident(path: string, incidentId: string): boolean {
  const own = incidentOfPath(path)
  return own === undefined || own === incidentId
}

function sameValue(v: unknown, expected: string): boolean {
  if (v === null || v === undefined) return expected === '' || expected === 'null'
  return String(v) === expected
}

/**
 * Whether `item` passes the list's equality filters: true / false, or
 * undefined when a filter names a field the item does not carry (unknown).
 * A comma-separated filter value matches any of its parts.
 */
export function matchesFilters(item: Record<string, unknown>, params: URLSearchParams): boolean | undefined {
  let result: boolean | undefined = true
  params.forEach((value, name) => {
    if (result === false || CONTROL_PARAMS.has(name)) return
    if (!(name in item)) {
      result = undefined
      return
    }
    const options = value.includes(',') ? value.split(',') : [value]
    if (!options.some((o) => sameValue(item[name], o))) result = false
  })
  return result
}

/**
 * Whether a new row belongs under the parent ids in `path` other than the
 * incident (e.g. `/tasks/<task_id>/comments` needs `task_id`). Undefined when
 * the row lacks the parent field.
 */
export function matchesParents(item: Record<string, unknown>, path: string): boolean | undefined {
  const segs = path.split('/').filter(Boolean)
  let result: boolean | undefined = true
  for (let i = 0; i < segs.length - 1; i++) {
    const seg = segs[i]
    const id = segs[i + 1]
    if (seg === 'incidents' || !ID_SEGMENT.test(id) || ID_SEGMENT.test(seg)) continue
    const field = `${seg.replace(/-/g, '_').replace(/s$/, '')}_id`
    if (!(field in item)) {
      result = undefined
      continue
    }
    if (String(item[field]) !== id) return false
  }
  return result
}

interface SortKey {
  field: string
  desc: boolean
}

function parseSort(sort: string): SortKey[] {
  return sort
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => (s.startsWith('-') ? { field: s.slice(1), desc: true } : { field: s.replace(/^\+/, ''), desc: false }))
}

function compareValues(a: unknown, b: unknown): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(a) - Number(b)
  return String(a).localeCompare(String(b))
}

/**
 * Compare two rows under a server sort (`-a,b`), NULLS LAST in both
 * directions and the row id as the final ascending tiebreaker, like
 * `utils/pagination.order_clauses`.
 */
export function compareRows(a: Record<string, unknown>, b: Record<string, unknown>, sort: string): number {
  for (const { field, desc } of parseSort(sort)) {
    const av = a[field]
    const bv = b[field]
    const an = av === null || av === undefined
    const bn = bv === null || bv === undefined
    if (an && bn) continue
    if (an) return 1
    if (bn) return -1
    const c = compareValues(av, bv)
    if (c !== 0) return desc ? -c : c
  }
  return compareValues(a.id, b.id)
}

function recount<D extends ListLike>(data: D, items: unknown[], total: number | undefined): D {
  const next = { ...data, items } as D
  if (typeof total === 'number') {
    ;(next as ListLike).total = Math.max(0, total)
    if (typeof data.per_page === 'number' && data.per_page > 0 && typeof data.pages === 'number') {
      ;(next as ListLike).pages = Math.ceil(Math.max(0, total) / data.per_page)
    }
  }
  return next
}

/**
 * Merge a change into one cached list response stored under `key`
 * (endpoint + query). Handles both `usePaginatedQuery` pages and
 * `useAllPages` entries (`__all` in the key).
 *
 * - deleted: removed wherever present (total − 1).
 * - updated: replaced when newer; dropped from the page when it no longer
 *   passes the list's equality filters. A row not on this page is ignored.
 * - created: appended to all-pages lists; inserted at its sorted position
 *   on page 1 of a paged list. When the position can't be known (search
 *   active, later page, unknown sort or filter field) the list is `stale`.
 */
export function mergeIntoList<D extends ListLike>(data: D, change: EntityChange, key: string): MergeResult<D> {
  const same: MergeResult<D> = { data, changed: false, stale: false }
  const stale: MergeResult<D> = { data, changed: false, stale: true }
  const items = data.items as Row[]
  const idx = items.findIndex((x) => x && String(x.id) === change.id)
  const total = typeof data.total === 'number' ? data.total : undefined
  const { path, params } = splitKey(key)

  if (change.op === 'deleted') {
    if (idx === -1) return same
    const next = items.filter((_, i) => i !== idx)
    return { data: recount(data, next, total === undefined ? undefined : total - 1), changed: true, stale: false }
  }

  if (!change.data) return idx === -1 && change.op === 'updated' ? same : stale

  if (idx !== -1) {
    if (isStaleChange(items[idx], change)) return same
    const merged = { ...items[idx], ...withVersion(change.data as Row, change) } as Row
    if (matchesFilters(merged as Record<string, unknown>, params) === false) {
      const next = items.filter((_, i) => i !== idx)
      return { data: recount(data, next, total === undefined ? undefined : total - 1), changed: true, stale: false }
    }
    const next = items.slice()
    next[idx] = merged
    return { data: { ...data, items: next }, changed: true, stale: false }
  }

  if (change.op !== 'created') return same

  const row = withVersion(change.data as Row, change) as Row & Record<string, unknown>
  if (params.get('q') || params.get('search')) return stale
  const filterMatch = matchesFilters(row, params)
  if (filterMatch === false) return same
  const parentMatch = matchesParents(row, path)
  if (parentMatch === false) return same
  if (filterMatch === undefined || parentMatch === undefined) return stale

  const newTotal = total === undefined ? undefined : total + 1
  if (params.has('__all')) {
    return { data: recount(data, [...items, row], newTotal), changed: true, stale: false }
  }

  const page = Number(params.get('page') ?? data.page ?? 1)
  if (page !== 1) return stale
  const sort = (typeof data.sort === 'string' && data.sort) || params.get('sort') || ''
  if (!sort) return stale
  if (parseSort(sort).some(({ field }) => !(field in row))) return stale

  let pos = items.findIndex((x) => compareRows(row, x as Record<string, unknown>, sort) < 0)
  if (pos === -1) pos = items.length
  const perPage = typeof data.per_page === 'number' && data.per_page > 0 ? data.per_page : Number(params.get('per_page')) || Infinity
  if (pos >= perPage) {
    // Sorts after this page: only the count moves.
    return { data: recount(data, items, newTotal), changed: true, stale: false }
  }
  const next = items.slice()
  next.splice(pos, 0, row)
  if (next.length > perPage) next.length = perPage
  return { data: recount(data, next, newTotal), changed: true, stale: false }
}
