import { mergeIntoList, type ListLike } from './realtime/merge'
import type { EntityChange } from './realtime/types'

/**
 * Tiny module-level cache for GET responses (no dependencies).
 *
 * Keys are full endpoint + query strings (e.g. `/incidents/42/hosts?page=2`).
 * Invalidation is by path prefix, segment-aware: `invalidate('/incidents/42')`
 * matches `/incidents/42?page=1` and `/incidents/42/hosts?…`, but not
 * `/incidents/420`. A prefix containing `?` is matched as a raw string prefix.
 *
 * Readers (usePaginatedQuery / useAllPages) show cached data instantly and
 * revalidate in the background, and subscribe so that a mutation elsewhere
 * (`invalidate`) or a live update (`upsertItem` / `removeItem`) reaches them.
 */

export interface CacheEntry<T = unknown> {
  data: T
  ts: number
}

export type CacheEvent =
  | { type: 'invalidate'; prefix: string }
  | { type: 'set'; key: string }
  /** One entry was dropped because a live change could not be placed in it. */
  | { type: 'stale'; key: string }

type Listener = (event: CacheEvent) => void

const MAX_ENTRIES = 300

const store = new Map<string, CacheEntry>()
const listeners = new Set<{ prefix: string; cb: Listener }>()

function pathOf(key: string): string {
  const i = key.indexOf('?')
  return i === -1 ? key : key.slice(0, i)
}

function trimSlash(p: string): string {
  return p.length > 1 && p.endsWith('/') ? p.slice(0, -1) : p
}

/** True when `key` (endpoint + query) falls under `prefix`. */
export function matchesPrefix(key: string, prefix: string): boolean {
  if (prefix.includes('?')) return key.startsWith(prefix)
  const path = trimSlash(pathOf(key))
  const p = trimSlash(prefix)
  return path === p || path.startsWith(p === '/' ? '/' : p + '/')
}

/** Either side contains the other (used to route events to subscribers). */
function related(a: string, b: string): boolean {
  return matchesPrefix(a, b) || matchesPrefix(b, a)
}

function emit(event: CacheEvent) {
  const target = event.type === 'invalidate' ? event.prefix : event.key
  Array.from(listeners).forEach((l) => {
    if (related(target, l.prefix)) l.cb(event)
  })
}

export function getCached<T>(key: string): CacheEntry<T> | undefined {
  return store.get(key) as CacheEntry<T> | undefined
}

export function setCached<T>(key: string, data: T): void {
  store.delete(key) // re-insert so Map order tracks recency
  store.set(key, { data, ts: Date.now() })
  if (store.size > MAX_ENTRIES) {
    const oldest = store.keys().next().value
    if (oldest !== undefined) store.delete(oldest)
  }
  emit({ type: 'set', key })
}

/** Drop every entry under `prefix` and tell subscribers to refetch. */
export function invalidate(prefix: string): void {
  Array.from(store.keys()).forEach((key) => {
    if (matchesPrefix(key, prefix)) store.delete(key)
  })
  emit({ type: 'invalidate', prefix })
}

/**
 * Drop every entry under `prefix` without notifying readers (access to an
 * incident ended: nothing may refetch it, and nothing cached may be shown).
 */
export function forget(prefix: string): void {
  Array.from(store.keys()).forEach((key) => {
    if (matchesPrefix(key, prefix)) store.delete(key)
  })
}

/** Drop everything without notifying (session change: login / logout). */
export function clearCache(): void {
  store.clear()
}

/**
 * Subscribe to events related to `prefix` (an endpoint path). Returns the
 * unsubscribe function.
 */
export function subscribe(prefix: string, cb: Listener): () => void {
  const entry = { prefix, cb }
  listeners.add(entry)
  return () => {
    listeners.delete(entry)
  }
}

type WithId = { id: string | number }

interface ListShape<T> {
  items: T[]
  total?: number
}

function isList<T>(data: unknown): data is ListShape<T> {
  return !!data && typeof data === 'object' && Array.isArray((data as ListShape<T>).items)
}

/**
 * Replace `item` (matched by `id`) in every cached list under `prefix`.
 * Returns true if it was found somewhere. When it was not found, its position
 * under the active sort/filters is unknown, so the prefix is invalidated and
 * readers refetch.
 */
export function upsertItem<T extends WithId>(prefix: string, item: T): boolean {
  let found = false
  Array.from(store.entries()).forEach(([key, entry]) => {
    if (!matchesPrefix(key, prefix) || !isList<T>(entry.data)) return
    const idx = entry.data.items.findIndex((x) => x.id === item.id)
    if (idx === -1) return
    found = true
    const items = entry.data.items.slice()
    items[idx] = { ...items[idx], ...item }
    store.set(key, { data: { ...entry.data, items }, ts: entry.ts })
    emit({ type: 'set', key })
  })
  if (!found) invalidate(prefix)
  return found
}

/** Remove the item with `id` from every cached list under `prefix`. */
export function removeItem(prefix: string, id: string | number): void {
  Array.from(store.entries()).forEach(([key, entry]) => {
    if (!matchesPrefix(key, prefix) || !isList<WithId>(entry.data)) return
    const items = entry.data.items.filter((x) => x.id !== id)
    if (items.length === entry.data.items.length) return
    const total =
      typeof entry.data.total === 'number' ? Math.max(0, entry.data.total - 1) : entry.data.total
    store.set(key, { data: { ...entry.data, items, total }, ts: entry.ts })
    emit({ type: 'set', key })
  })
}

/**
 * Drop one entry and tell its readers to refetch it (only readers showing
 * exactly `key` react; others refetch when they next need it).
 */
export function markStale(key: string): void {
  store.delete(key)
  emit({ type: 'stale', key })
}

/**
 * Merge a realtime change into every cached list whose path is exactly
 * `path` (all pages, sorts and filters of that list). See
 * `realtime/merge.mergeIntoList` for the placement rules. Entries the change
 * can't be placed in are marked stale. Returns the number of entries touched.
 */
export function mergeChange(path: string, change: EntityChange): number {
  const target = trimSlash(path)
  let touched = 0
  Array.from(store.entries()).forEach(([key, entry]) => {
    if (trimSlash(pathOf(key)) !== target || !isList(entry.data)) return
    const result = mergeIntoList(entry.data as ListLike, change, key)
    if (result.stale) {
      touched++
      markStale(key)
    } else if (result.changed) {
      touched++
      store.set(key, { data: result.data, ts: entry.ts })
      emit({ type: 'set', key })
    }
  })
  return touched
}
