/** Admin-configurable rate limits (W4-RL). Backend: `endpoints/system.py`. */
export type RateLimitSource = 'code' | 'env' | 'override'

export interface RateLimitGroup {
  key: string
  description: string
  category: 'global' | 'auth' | 'admin' | 'feature' | 'threat_intel' | string
  auth_sensitive: boolean
  routes: string[]
  default: string
  env: string | null
  override: string | null
  /** Configured limit (override, env or default). */
  limit: string
  source: RateLimitSource
  enabled: boolean
  /** Limit in force now; null when exempt (rate limiting off). */
  effective: string | null
}

export interface RateLimitSettings {
  enabled: boolean
  locked: boolean
  hard_disabled: boolean
  can_edit: boolean
  version: number
  updated_at: string | null
  cache_ttl_seconds: number
  groups: RateLimitGroup[]
}

export interface RateLimitOverride {
  limit?: string | null
  enabled?: boolean
}

export interface RateLimitUpdate {
  enabled: boolean
  groups: Record<string, RateLimitOverride>
  version: number
  confirm_weakening?: boolean
}
