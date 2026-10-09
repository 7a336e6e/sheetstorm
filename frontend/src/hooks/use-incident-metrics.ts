"use client"

/**
 * `GET /incidents/<id>/metrics` for the Overview metrics card (and the
 * milestone strip, which can show the same durations).
 *
 * Refetches when `refreshKey` changes (pass `incident.version`: every
 * lifecycle edit bumps it) and, debounced, when a timeline event changes
 * (the dwell start may be derived from the timeline).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { isAbortError } from '@/lib/api'
import { postIncident } from '@/lib/endpoints/post-incident'
import { subscribeEntity } from '@/lib/realtime/live'
import { describeError } from '@/lib/errors'
import type { IncidentMetrics } from '@/types'

export const METRICS_TIMELINE_DEBOUNCE_MS = 1000

export interface IncidentMetricsState {
  data: IncidentMetrics | null
  error: string | null
  /** First load: nothing to show yet. */
  isLoading: boolean
  refetch(): void
}

export function useIncidentMetrics(incidentId: string, refreshKey?: string | number | null): IncidentMetricsState {
  const [data, setData] = useState<IncidentMetrics | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setLoading] = useState(true)
  const [nonce, setNonce] = useState(0)
  const [syncedId, setSyncedId] = useState(incidentId)
  if (syncedId !== incidentId) {
    setSyncedId(incidentId)
    setData(null)
    setError(null)
    setLoading(true)
  }

  useEffect(() => {
    const controller = new AbortController()
    postIncident
      .incidentMetrics(incidentId, { signal: controller.signal })
      .then((next) => {
        setData(next)
        setError(null)
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (isAbortError(err)) return
        setError(describeError(err).description)
        setLoading(false)
      })
    return () => controller.abort()
  }, [incidentId, refreshKey, nonce])

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    const off = subscribeEntity('timeline_event', (change) => {
      if (change.incident_id !== incidentId) return
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => setNonce((n) => n + 1), METRICS_TIMELINE_DEBOUNCE_MS)
    })
    return () => {
      off()
      if (timer.current) clearTimeout(timer.current)
    }
  }, [incidentId])

  const refetch = useCallback(() => setNonce((n) => n + 1), [])
  return { data, error, isLoading, refetch }
}
