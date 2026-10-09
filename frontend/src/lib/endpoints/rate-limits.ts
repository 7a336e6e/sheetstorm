/**
 * Rate-limit settings (W4-RL).
 *
 *   GET  /system/rate-limits         organizations:manage or platform admin
 *   PUT  /system/rate-limits         platform admin (409 confirmation_required / settings_locked)
 *   POST /system/rate-limits/reset   platform admin
 */
import { api } from '@/lib/api'
import type { RateLimitGroup, RateLimitOverride, RateLimitSettings, RateLimitUpdate } from '@/types'

export const RATE_LIMITS_ENDPOINT = '/system/rate-limits'

export const rateLimitsApi = {
  get: (opts?: { signal?: AbortSignal }) => api.get<RateLimitSettings>(RATE_LIMITS_ENDPOINT, opts),
  update: (body: RateLimitUpdate) => api.put<RateLimitSettings>(RATE_LIMITS_ENDPOINT, body),
  reset: (groups?: string[]) =>
    api.post<RateLimitSettings>(`${RATE_LIMITS_ENDPOINT}/reset`, groups ? { groups } : {}),
}

const LIMIT_ITEM = /^\s*\d+\s*(\/|per)\s*(\d+\s+)?(second|minute|hour|day|month|year)s?\s*$/i

/** Client-side pre-check of a limit string such as `5 per minute;100 per day` (server is authoritative). */
export function isValidLimit(value: string): boolean {
  const items = value.split(/[;,]/).filter((s) => s.trim())
  return items.length > 0 && items.length <= 5 && items.every((s) => LIMIT_ITEM.test(s))
}

/** Override document for the PUT: only rows that differ from their non-override value. */
export function overridesFrom(
  groups: RateLimitGroup[],
  draft: Record<string, { limit: string; enabled: boolean }>
): Record<string, RateLimitOverride> {
  const out: Record<string, RateLimitOverride> = {}
  for (const g of groups) {
    const d = draft[g.key]
    if (!d) continue
    const base = g.env ?? g.default
    const entry: RateLimitOverride = {}
    const limit = d.limit.trim()
    if (limit && limit !== base) entry.limit = limit
    if (!d.enabled) entry.enabled = false
    if (Object.keys(entry).length) out[g.key] = entry
  }
  return out
}

export const CATEGORY_LABELS: Record<string, string> = {
  global: 'Global',
  auth: 'Authentication',
  admin: 'Administration',
  feature: 'Features',
  threat_intel: 'Threat intelligence',
}
