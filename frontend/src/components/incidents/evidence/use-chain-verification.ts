"use client"

/**
 * Chain verification of the whole incident ledger (or one item), run lazily
 * and cached.
 *
 * - Runs on mount when `enabled`; a cached result younger than `FRESH_MS` is
 *   shown without a request (the endpoint is rate limited and audited).
 * - Any `invalidate('/incidents/<id>/evidence')` (a register / custody write)
 *   drops the cache and re-verifies, so the badge never describes a chain
 *   that has since grown.
 * - `verify()` is the explicit "check again" action.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { isAbortError } from '@/lib/api'
import { evidenceApi, evidenceBase, evidenceItemPath } from '@/lib/endpoints/evidence'
import { getCached, setCached, subscribe } from '@/lib/query-cache'
import { subscribeEntity } from '@/lib/realtime/live'
import type { ChainVerification } from '@/types'
import type { ChainBadgeStatus } from './ChainStatusBadge'

export const CHAIN_FRESH_MS = 60_000

export interface ChainVerificationState {
  status: ChainBadgeStatus
  data: ChainVerification | null
  error: unknown
  /** Verify again now (explicit, audited server side). */
  verify(): Promise<void>
}

export function useChainVerification(
  incidentId: string,
  itemId: string | null = null,
  enabled = true
): ChainVerificationState {
  const base = evidenceBase(incidentId)
  const key = itemId ? `${evidenceItemPath(incidentId, itemId)}/custody/verify` : `${base}/custody/verify`

  const [data, setData] = useState<ChainVerification | null>(() => getCached<ChainVerification>(key)?.data ?? null)
  const [error, setError] = useState<unknown>(null)
  const [checking, setChecking] = useState(false)
  const ctrlRef = useRef<AbortController | null>(null)

  const run = useCallback(async () => {
    ctrlRef.current?.abort()
    const ctrl = new AbortController()
    ctrlRef.current = ctrl
    setChecking(true)
    try {
      const res = itemId
        ? await evidenceApi.verifyItemChain(incidentId, itemId, { signal: ctrl.signal })
        : await evidenceApi.verifyIncidentChain(incidentId, { signal: ctrl.signal })
      if (ctrl.signal.aborted) return
      setCached(key, res)
      setData(res)
      setError(null)
    } catch (err) {
      if (isAbortError(err) || ctrl.signal.aborted) return
      setError(err)
    } finally {
      if (ctrlRef.current === ctrl) setChecking(false)
    }
  }, [incidentId, itemId, key])

  // Lazy first run (or cached result).
  useEffect(() => {
    if (!enabled) return
    const cached = getCached<ChainVerification>(key)
    if (cached && Date.now() - cached.ts < CHAIN_FRESH_MS) {
      setData(cached.data)
      return
    }
    void run()
    return () => ctrlRef.current?.abort()
  }, [enabled, key, run])

  // A write under the evidence prefix, or a live ledger change, makes the verdict stale.
  useEffect(() => {
    if (!enabled) return
    const off = subscribe(base, (ev) => {
      if (ev.type === 'invalidate') void run()
    })
    let timer: ReturnType<typeof setTimeout> | null = null
    const onLive = (change: { incident_id: string }) => {
      if (change.incident_id !== incidentId) return
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => void run(), 800)
    }
    const offLive = subscribeEntity('custody_entry', onLive)
    return () => {
      off()
      offLive()
      if (timer) clearTimeout(timer)
    }
  }, [enabled, base, incidentId, run])

  const status: ChainBadgeStatus = checking && !data ? 'checking' : error && !data ? 'error' : data ? data.status : enabled ? 'checking' : 'unknown'
  return { status, data, error, verify: run }
}
