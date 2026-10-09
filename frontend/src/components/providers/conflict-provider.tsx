"use client"

/**
 * Global edit-conflict handling.
 *
 * Registers `api.setConflictHandler`, so every `put/patch/delete(...,
 * {ifMatch})` answered with 409 `conflict` opens ConflictDialog instead of
 * failing straight away. The caller's promise stays pending until the user
 * chooses:
 *
 * - "Overwrite with mine": the same write is re-sent with the server's
 *   current version; the caller's promise settles with that result (a
 *   further conflict opens the dialog again).
 * - "Reload theirs" (or closing the dialog): the server's copy is merged
 *   into the cached lists and the open incident, and the caller's promise
 *   rejects with `ConflictDismissedError`, an abort-type error that
 *   `notifyError` ignores, so no second error toast appears.
 *
 * Conflicts are queued and shown one at a time.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import api, { type ApiError, type ConflictRequest } from '@/lib/api'
import { invalidate, mergeChange } from '@/lib/query-cache'
import { useIncidentStore } from '@/lib/store'
import { toast } from '@/components/ui/use-toast'
import { ConflictDialog } from '@/components/incidents/ConflictDialog'

/** Rejection for a conflict the user resolved by keeping the other version. */
export class ConflictDismissedError extends Error {
  readonly conflict: ApiError

  constructor(conflict: ApiError) {
    super('The other version was kept')
    // Abort-type: callers treat it like a cancelled request (no error toast).
    this.name = 'AbortError'
    this.conflict = conflict
  }
}

export function isConflictDismissed(err: unknown): err is ConflictDismissedError {
  return err instanceof ConflictDismissedError
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

/** The version to overwrite with: `current_version`, else `current.version`. */
export function currentVersionOf(err: ApiError): number | undefined {
  const d = err.details
  if (typeof d?.current_version === 'number') return d.current_version
  const cur = d?.current
  return isRecord(cur) && typeof cur.version === 'number' ? cur.version : undefined
}

const ID_SEGMENT = /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+)$/i

/**
 * Where the written row lives: `/incidents/<i>/hosts/<h>` → collection
 * `/incidents/<i>/hosts`, id `<h>`; `/incidents/<i>/status` → `/incidents`, `<i>`.
 */
export function collectionOf(endpoint: string): { collection: string; id: string } | null {
  const segs = endpoint.split('?')[0].split('/').filter(Boolean)
  for (let k = segs.length - 1; k > 0; k--) {
    if (ID_SEGMENT.test(segs[k])) return { collection: `/${segs.slice(0, k).join('/')}`, id: segs[k] }
  }
  return null
}

/** Show the server's current copy wherever the client holds that row. */
export function applyServerCopy(conflict: Pick<ConflictRequest, 'endpoint' | 'error'>): void {
  const current = conflict.error.details?.current
  const where = collectionOf(conflict.endpoint)
  if (!where || !isRecord(current) || String(current.id ?? where.id) !== where.id) {
    invalidate(conflict.endpoint.split('?')[0].replace(/\/[^/]+$/, '') || '/')
    return
  }
  const version = currentVersionOf(conflict.error)
  mergeChange(where.collection, {
    incident_id: '',
    entity: '',
    op: 'updated',
    id: where.id,
    version: version ?? null,
    data: current,
  })
  if (where.collection === '/incidents') {
    const store = useIncidentStore.getState()
    if (store.currentIncident?.id === where.id) {
      useIncidentStore.setState({ currentIncident: { ...store.currentIncident, ...current } })
    }
  }
}

interface Pending {
  id: number
  conflict: ConflictRequest
  resolve: (value: unknown) => void
  reject: (reason: unknown) => void
}

interface ConflictContextValue {
  /** Number of conflicts waiting for a decision. */
  pending: number
}

const ConflictContext = createContext<ConflictContextValue>({ pending: 0 })

export function useConflicts(): ConflictContextValue {
  return useContext(ConflictContext)
}

export function ConflictProvider({ children }: { children: ReactNode }) {
  const [queue, setQueue] = useState<Pending[]>([])
  const queueRef = useRef<Pending[]>([])
  useEffect(() => {
    queueRef.current = queue
  }, [queue])

  useEffect(() => {
    let nextId = 0
    api.setConflictHandler(
      (conflict) =>
        new Promise((resolve, reject) => {
          const id = ++nextId
          setQueue((q) => [...q, { id, conflict, resolve, reject }])
        })
    )
    return () => {
      api.setConflictHandler(null)
      // Nobody can answer them any more: settle as "kept theirs".
      queueRef.current.forEach((p) => p.reject(new ConflictDismissedError(p.conflict.error)))
    }
  }, [])

  const active = queue[0]

  const reloadTheirs = useCallback(() => {
    const p = queueRef.current[0]
    if (!p) return
    queueRef.current = queueRef.current.slice(1)
    setQueue((q) => q.filter((x) => x.id !== p.id))
    applyServerCopy(p.conflict)
    toast({ title: 'Showing the latest version', description: 'Your change was not saved.' })
    p.reject(new ConflictDismissedError(p.conflict.error))
  }, [])

  const overwrite = useCallback(() => {
    const p = queueRef.current[0]
    if (!p) return
    // Close first: the retry may itself conflict and queue a new dialog.
    queueRef.current = queueRef.current.slice(1)
    setQueue((q) => q.filter((x) => x.id !== p.id))
    p.conflict.retry(currentVersionOf(p.conflict.error)).then(p.resolve, p.reject)
  }, [])

  const value = useMemo(() => ({ pending: queue.length }), [queue.length])

  return (
    <ConflictContext.Provider value={value}>
      {children}
      {active && (
        <ConflictDialog
          key={active.id}
          open
          method={active.conflict.method}
          mine={active.conflict.data}
          theirs={active.conflict.error.details?.current}
          currentVersion={currentVersionOf(active.conflict.error)}
          onReloadTheirs={reloadTheirs}
          onOverwrite={overwrite}
        />
      )}
    </ConflictContext.Provider>
  )
}
