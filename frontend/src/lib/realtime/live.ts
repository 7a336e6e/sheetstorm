/**
 * Module-level realtime hub between the socket (`useIncidentRealtime`) and
 * the data layer.
 *
 * - List readers (`usePaginatedQuery` / `useAllPages` with `live: '<entity>'`)
 *   register here. `dispatchChange` merges an `entity:changed` envelope into
 *   the query cache once per registered list path, so every reader of that
 *   list re-renders from the cache.
 * - `resyncScopes` refetches the mounted readers (one request per distinct
 *   cache key) and runs scope-level resync handlers (e.g. the attack graph).
 * - Components that keep their own state (graph, incident header) use
 *   `subscribeEntity` / `subscribeResync`.
 */
import { mergeChange } from '@/lib/query-cache'
import { pathAcceptsIncident } from './merge'
import { entitiesForScope, type EntityChange } from './types'

export interface LiveReader {
  entity: string
  /** Endpoint path without the query string, e.g. `/incidents/<id>/hosts`. */
  path: string
  /** The cache key the reader currently shows (null when disabled). */
  key: () => string | null
  refetch: () => Promise<void>
}

type EntityListener = (change: EntityChange) => void
type ResyncListener = (incidentId: string) => Promise<unknown> | unknown

const readers = new Set<LiveReader>()
const entityListeners = new Set<{ entity: string; fn: EntityListener }>()
const resyncListeners = new Set<{ scope: string; fn: ResyncListener }>()

function trimSlash(p: string): string {
  return p.length > 1 && p.endsWith('/') ? p.slice(0, -1) : p
}

export function registerLiveList(reader: LiveReader): () => void {
  const entry = { ...reader, path: trimSlash(reader.path) }
  readers.add(entry)
  return () => {
    readers.delete(entry)
  }
}

/** Listen to changes of one entity (`'*'` for all). Returns the unsubscribe function. */
export function subscribeEntity(entity: string, fn: EntityListener): () => void {
  const entry = { entity, fn }
  entityListeners.add(entry)
  return () => {
    entityListeners.delete(entry)
  }
}

/** Run `fn(incidentId)` when `scope` must be resynced. Returns the unsubscribe function. */
export function subscribeResync(scope: string, fn: ResyncListener): () => void {
  const entry = { scope, fn }
  resyncListeners.add(entry)
  return () => {
    resyncListeners.delete(entry)
  }
}

/** Apply one validated `entity:changed` envelope to every live list and listener. */
export function dispatchChange(change: EntityChange): void {
  const paths = new Set<string>()
  readers.forEach((r) => {
    if (r.entity === change.entity && pathAcceptsIncident(r.path, change.incident_id)) paths.add(r.path)
  })
  paths.forEach((p) => mergeChange(p, change))
  Array.from(entityListeners).forEach((l) => {
    if (l.entity === change.entity || l.entity === '*') {
      try {
        l.fn(change)
      } catch {
        // A faulty listener must not break the others.
      }
    }
  })
}

/**
 * Refetch everything mounted that shows `scopes` of `incidentId`. Readers that
 * share a cache key share one request (the others pick it up from the cache).
 */
export function resyncScopes(incidentId: string, scopes: string[]): Promise<void> {
  const wanted = new Set(scopes)
  const entities = new Set(scopes.flatMap(entitiesForScope))
  const seenKeys = new Set<string>()
  const tasks: Array<Promise<unknown>> = []
  readers.forEach((r) => {
    if (!entities.has(r.entity) || !pathAcceptsIncident(r.path, incidentId)) return
    const key = r.key()
    if (!key || seenKeys.has(key)) return
    seenKeys.add(key)
    tasks.push(r.refetch())
  })
  resyncListeners.forEach((l) => {
    if (!wanted.has(l.scope)) return
    try {
      tasks.push(Promise.resolve(l.fn(incidentId)))
    } catch {
      // ignore: one failing handler must not block the rest
    }
  })
  return Promise.all(tasks.map((t) => t.catch(() => undefined))).then(() => undefined)
}

/** Test helper: number of registered live readers. */
export function liveReaderCount(): number {
  return readers.size
}
