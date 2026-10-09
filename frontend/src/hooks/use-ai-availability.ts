"use client"

/**
 * PLACEHOLDER (W1-TBL). The real hook is shipped by W1-RBAC-UI (C23b): it
 * reads `GET /incidents/<id>/reports/types` and reports whether the org's
 * per-TLP AI policy lets AI run for the incident, with a readable reason.
 *
 * This stub has the same signature and always answers "allowed" (which is
 * also what the real hook answers while loading), so W1-TBL builds on its
 * own. At merge, keep W1-RBAC-UI's file; the only consumer here is
 * `components/incidents/detail/IncidentModals.tsx` (`allowed`, `reason`).
 */
export interface AiAvailability {
  allowed: boolean
  reason: string | null
  loading: boolean
  error: unknown
  configured: boolean
  policyMode: string | null
  tlp: string | null
  providers: { name: string; allowed: boolean; reason: string }[]
  allowedProviders: string[]
  refetch: () => void
}

export function useAiAvailability(
  incidentId: string | null | undefined,
  opts: { provider?: string; enabled?: boolean } = {}
): AiAvailability {
  void incidentId
  void opts
  return {
    allowed: true,
    reason: null,
    loading: false,
    error: null,
    configured: false,
    policyMode: null,
    tlp: null,
    providers: [],
    allowedProviders: [],
    refetch: () => {},
  }
}
