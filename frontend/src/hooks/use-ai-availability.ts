"use client"

/**
 * Whether AI features may run for an incident under the organization's
 * per-TLP AI policy (`OrgSettings.ai_tlp_policy`, enforced server side by
 * `ai_service` dispatch). Reads the per-incident providers endpoint
 * (`GET /incidents/<id>/reports/types` → `{policy_mode, providers:[{name, allowed, reason}]}`).
 *
 * Cosmetic only: a refused call still answers 403 `ai_blocked_by_tlp`. While
 * loading or after a failed lookup, `allowed` stays true so the UI never
 * blocks on its own; the server decides.
 *
 * Responses are cached per incident (shared by every gate on the page) and
 * refetched when `/incidents/<id>` is invalidated (e.g. after a TLP change).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { isAbortError } from '@/lib/api'
import { aiAvailability, aiAvailabilityEndpoint } from '@/lib/endpoints/rbac'
import { getCached, setCached, subscribe } from '@/lib/query-cache'
import type { AiAvailabilityResponse, AiPolicyMode, AiProviderAvailability, TLPLevel } from '@/types'

/** Cached answers younger than this are reused without a request. */
export const AI_AVAILABILITY_TTL_MS = 30_000

const TLP_TEXT: Record<string, string> = {
  white: 'TLP:WHITE',
  green: 'TLP:GREEN',
  amber: 'TLP:AMBER',
  amber_strict: 'TLP:AMBER+STRICT',
  red: 'TLP:RED',
}

const PROVIDER_REASON_TEXT: Record<string, string> = {
  cloud_provider: 'it is a cloud provider',
  not_allowlisted: 'its host is not on the outbound allowlist',
  public_host: 'its host is a public address',
  unresolvable: "its host can't be resolved",
  invalid_url: 'its URL is invalid',
  not_configured: 'it has no base URL configured',
  policy_block: 'AI is blocked for this TLP level',
}

export interface AiAvailabilityVerdict {
  allowed: boolean
  /** Human-readable reason when not allowed. */
  reason: string | null
}

function tlpText(tlp: string | null | undefined): string {
  return tlp ? TLP_TEXT[tlp] ?? `TLP:${tlp.toUpperCase()}` : 'this'
}

/**
 * Pure verdict for `provider` (or for "any provider" when omitted). Missing
 * data (loading / error) is reported as allowed.
 */
export function describeAiAvailability(
  data: AiAvailabilityResponse | null | undefined,
  provider?: string
): AiAvailabilityVerdict {
  if (!data) return { allowed: true, reason: null }
  const tlp = tlpText(data.tlp)
  if (!data.ai_configured || data.providers.length === 0) {
    return { allowed: false, reason: 'No AI provider is configured. An administrator can add one in Settings → AI Providers.' }
  }
  if (data.policy_mode === 'block') {
    return {
      allowed: false,
      reason: `AI is disabled for ${tlp} incidents by your organization's data egress policy.`,
    }
  }
  if (provider) {
    const entry = data.providers.find((p) => p.name === provider)
    if (!entry) return { allowed: false, reason: `AI provider "${provider}" is not configured.` }
    if (entry.allowed) return { allowed: true, reason: null }
    const why = PROVIDER_REASON_TEXT[entry.reason] ?? entry.reason
    return {
      allowed: false,
      reason: `${tlp} incidents may only use local AI providers; "${provider}" is refused because ${why}.`,
    }
  }
  if (data.providers.some((p) => p.allowed)) return { allowed: true, reason: null }
  return {
    allowed: false,
    reason:
      data.policy_mode === 'local_only'
        ? `${tlp} incidents may only use local AI providers (Ollama or an allowlisted OpenAI-compatible server), and none is available.`
        : `No AI provider may process ${tlp} data.`,
  }
}

const inflight = new Map<string, Promise<AiAvailabilityResponse>>()

/** One request per incident at a time, shared by every caller. */
function fetchShared(incidentId: string): Promise<AiAvailabilityResponse> {
  const key = aiAvailabilityEndpoint(incidentId)
  let p = inflight.get(key)
  if (!p) {
    p = aiAvailability
      .forIncident(incidentId)
      .then((data) => {
        setCached(key, data)
        return data
      })
      .finally(() => inflight.delete(key))
    inflight.set(key, p)
  }
  return p
}

export interface AiAvailability extends AiAvailabilityVerdict {
  loading: boolean
  error: unknown
  configured: boolean
  policyMode: AiPolicyMode | null
  tlp: TLPLevel | null
  providers: AiProviderAvailability[]
  allowedProviders: string[]
  refetch: () => void
}

export function useAiAvailability(
  incidentId: string | null | undefined,
  opts: { provider?: string; enabled?: boolean } = {}
): AiAvailability {
  const { provider, enabled = true } = opts
  const key = incidentId ? aiAvailabilityEndpoint(incidentId) : null
  const [data, setData] = useState<AiAvailabilityResponse | null>(() =>
    key ? getCached<AiAvailabilityResponse>(key)?.data ?? null : null
  )
  const [error, setError] = useState<unknown>(null)
  const [version, setVersion] = useState(0)
  const force = useRef(false)

  // Another incident: show its cached answer (if any) right away.
  const [lastKey, setLastKey] = useState(key)
  if (key !== lastKey) {
    setLastKey(key)
    setData(key ? getCached<AiAvailabilityResponse>(key)?.data ?? null : null)
    setError(null)
  }

  useEffect(() => {
    if (!incidentId || !enabled) return
    const cached = getCached<AiAvailabilityResponse>(aiAvailabilityEndpoint(incidentId))
    if (!force.current && cached && Date.now() - cached.ts < AI_AVAILABILITY_TTL_MS) return
    force.current = false
    let cancelled = false
    fetchShared(incidentId)
      .then((res) => {
        if (!cancelled) {
          setData(res)
          setError(null)
        }
      })
      .catch((err) => {
        if (!cancelled && !isAbortError(err)) setError(err)
      })
    return () => {
      cancelled = true
    }
  }, [incidentId, enabled, version])

  useEffect(() => {
    if (!key) return
    return subscribe(key, (event) => {
      if (event.type === 'invalidate') {
        setVersion((v) => v + 1)
      } else if (event.key === key) {
        const cached = getCached<AiAvailabilityResponse>(key)
        if (cached) setData(cached.data)
      }
    })
  }, [key])

  const refetch = useCallback(() => {
    force.current = true
    setVersion((v) => v + 1)
  }, [])

  const verdict = describeAiAvailability(error ? null : data, provider)
  return {
    ...verdict,
    loading: enabled && !!incidentId && !data && !error,
    error,
    configured: data?.ai_configured ?? false,
    policyMode: data?.policy_mode ?? null,
    tlp: data?.tlp ?? null,
    providers: data?.providers ?? [],
    allowedProviders: (data?.providers ?? []).filter((p) => p.allowed).map((p) => p.name),
    refetch,
  }
}
