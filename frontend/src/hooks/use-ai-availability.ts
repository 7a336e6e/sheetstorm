"use client"

/**
 * TEMPORARY STUB (W1-LST). W1-RBAC-UI ships the real `useAiAvailability` at
 * this path (§1 #22b / C23b); it merges first. On rebase, take RBAC-UI's file
 * and drop this one. Only the subset of the real API that W1-LST uses is
 * declared here, with the real hook's "unknown → allowed" behaviour (the
 * server decides and answers 403 `ai_blocked_by_tlp`).
 */
export interface AiAvailability {
  allowed: boolean
  /** Human-readable reason when not allowed. */
  reason: string | null
  loading: boolean
}

export function useAiAvailability(
  _incidentId: string | null | undefined,
  _opts: { provider?: string; enabled?: boolean } = {}
): AiAvailability {
  return { allowed: true, reason: null, loading: false }
}
