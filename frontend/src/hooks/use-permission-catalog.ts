"use client"

/**
 * The server permission catalog (`GET /permissions`), cached for the session:
 * it is static metadata, so every consumer shares one request.
 */
import { useCallback, useEffect, useState } from 'react'
import { getCached, setCached } from '@/lib/query-cache'
import { rbac } from '@/lib/endpoints/rbac'
import type { PermissionCatalog, PermissionDef } from '@/types'

const KEY = '/permissions'

export interface PermissionCatalogState {
  catalog: PermissionCatalog | null
  loading: boolean
  error: unknown
  /** Catalog entry for a key (undefined for unknown keys). */
  lookup: (key: string) => PermissionDef | undefined
  /** Human label for a key, falling back to the key itself. */
  labelOf: (key: string) => string
  reload: () => void
}

export function usePermissionCatalog(): PermissionCatalogState {
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(
    () => getCached<PermissionCatalog>(KEY)?.data ?? null
  )
  const [loading, setLoading] = useState(catalog === null)
  const [error, setError] = useState<unknown>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (catalog && attempt === 0) return
    let cancelled = false
    rbac
      .listPermissions()
      .then((data) => {
        setCached(KEY, data)
        if (!cancelled) {
          setCatalog(data)
          setError(null)
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt])

  const lookup = useCallback(
    (key: string) => catalog?.items.find((p) => p.key === key),
    [catalog]
  )
  const labelOf = useCallback((key: string) => lookup(key)?.label ?? key, [lookup])
  const reload = useCallback(() => {
    setLoading(true)
    setAttempt((n) => n + 1)
  }, [])

  return { catalog, loading, error, lookup, labelOf, reload }
}
