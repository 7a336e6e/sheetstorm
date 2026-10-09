/**
 * API key and service-account endpoints (W3-APIK-UI): backend
 * `endpoints/api_keys.py`, plus the two org settings that govern them
 * (`api_keys_enabled`, `api_key_max_lifetime_days` via `PUT /organization`).
 *
 * The full key (`secret`) is in the body of a create / rotate response
 * exactly once. Callers keep it in component state only: never in the query
 * cache, a store or browser storage.
 */
import { api, buildQuery, isAbortError, isApiError } from '@/lib/api'
import { describeError, type ErrorDescription } from '@/lib/errors'
import { toast } from '@/components/ui/use-toast'
import type {
  ApiKey,
  ApiKeyCreateInput,
  ApiKeyListParams,
  ApiKeyOrgSettings,
  ApiKeyRotateInput,
  ApiKeyScopeGroup,
  ApiKeyScopesResponse,
  ApiKeyWithSecret,
  ServiceAccount,
  ServiceAccountCreateInput,
  ServiceAccountUpdateInput,
  PaginatedResponse,
} from '@/types'

/** List endpoints (also the query-cache prefixes to invalidate). */
export const API_KEYS_ENDPOINT = '/api-keys'
export const SERVICE_ACCOUNTS_ENDPOINT = '/service-accounts'

export const apiKeys = {
  /** Grantable scopes (grouped) for `ownerId` (default: me), plus the org limits. */
  scopes: (ownerId?: string, opts?: { signal?: AbortSignal }) =>
    api.get<ApiKeyScopesResponse>(`${API_KEYS_ENDPOINT}/scopes${buildQuery({ owner_id: ownerId })}`, opts),
  list: (params: ApiKeyListParams = {}, opts?: { signal?: AbortSignal }) =>
    api.get<PaginatedResponse<ApiKey>>(
      `${API_KEYS_ENDPOINT}${buildQuery({ ...params, mine: params.mine ? 'true' : undefined })}`,
      opts
    ),
  get: (id: string) => api.get<ApiKey>(`${API_KEYS_ENDPOINT}/${id}`),
  /** 201 -> the key plus its one-time `secret`. */
  create: (body: ApiKeyCreateInput) => api.post<ApiKeyWithSecret>(API_KEYS_ENDPOINT, body),
  /** 201 -> the replacement key plus its one-time `secret`. The old key stops after the grace period. */
  rotate: (id: string, body: ApiKeyRotateInput) =>
    api.post<ApiKeyWithSecret>(`${API_KEYS_ENDPOINT}/${id}/rotate`, body),
  /** Idempotent soft revoke; the row stays for audit. */
  revoke: (id: string, reason?: string) =>
    api.delete<ApiKey>(`${API_KEYS_ENDPOINT}/${id}`, reason ? { reason } : {}),
}

export const serviceAccounts = {
  list: (
    params: { q?: string; is_active?: boolean; sort?: string; page?: number; per_page?: number } = {},
    opts?: { signal?: AbortSignal }
  ) =>
    api.get<PaginatedResponse<ServiceAccount>>(
      `${SERVICE_ACCOUNTS_ENDPOINT}${buildQuery({ ...params, is_active: params.is_active === undefined ? undefined : String(params.is_active) })}`,
      opts
    ),
  create: (body: ServiceAccountCreateInput) => api.post<ServiceAccount>(SERVICE_ACCOUNTS_ENDPOINT, body),
  update: (id: string, body: ServiceAccountUpdateInput) =>
    api.patch<ServiceAccount>(`${SERVICE_ACCOUNTS_ENDPOINT}/${id}`, body),
  /** Revokes every key, then soft-disables the account. */
  remove: (id: string) => api.delete<ServiceAccount>(`${SERVICE_ACCOUNTS_ENDPOINT}/${id}`),
}

/** The two org settings. Writing needs `organizations:manage` (the org endpoint's gate). */
export const apiKeyOrgSettings = {
  get: async (): Promise<Required<ApiKeyOrgSettings>> => {
    const org = await api.get<{ settings?: ApiKeyOrgSettings }>('/organization')
    return {
      api_keys_enabled: org.settings?.api_keys_enabled !== false,
      api_key_max_lifetime_days: org.settings?.api_key_max_lifetime_days ?? API_KEY_MAX_LIFETIME_DEFAULT,
    }
  },
  update: (settings: ApiKeyOrgSettings) => api.put<{ settings?: ApiKeyOrgSettings }>('/organization', { settings }),
}

// ── Pure helpers ──────────────────────────────────────────────────────

export const API_KEY_MAX_LIFETIME_DEFAULT = 365
export const API_KEY_DEFAULT_LIFETIME_DAYS = 90
/** A key expiring within this many days is flagged. */
export const API_KEY_EXPIRY_WARN_DAYS = 14
export const MAX_GRACE_MINUTES = 1440
/** MCP server setup guide (API keys section). */
export const MCP_DOCS_URL = 'https://github.com/7a336e6e/sheetstorm/blob/main/mcp-server/README.md#api-keys'
/** Env var the MCP server and bridge read. */
export const MCP_API_KEY_ENV = 'SHEETSTORM_API_KEY'

/** Expiry choices (days) that fit under the org's `max`; `max` itself is always offered. */
export function expiryOptions(max: number): number[] {
  const cap = Math.max(1, max)
  const fixed = [7, 30, 90, 180, 365].filter((d) => d <= cap)
  return fixed.includes(cap) ? fixed : [...fixed, cap]
}

/** Default lifetime: 90 days, or `max` when the org caps it lower. */
export function defaultExpiry(max: number): number {
  return Math.min(API_KEY_DEFAULT_LIFETIME_DAYS, Math.max(1, max))
}

/** Whole days from `now` until `iso` (negative once passed); null for a bad date. */
export function daysUntil(iso: string | null | undefined, now: number = Date.now()): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return null
  return Math.ceil((t - now) / 86_400_000)
}

/** Active key that expires within `API_KEY_EXPIRY_WARN_DAYS`. */
export function expiresSoon(key: Pick<ApiKey, 'status' | 'expires_at'>, now: number = Date.now()): boolean {
  if (key.status !== 'active') return false
  const days = daysUntil(key.expires_at, now)
  return days !== null && days <= API_KEY_EXPIRY_WARN_DAYS
}

/** Groups with non-grantable scopes (and then-empty groups) removed. */
export function visibleGroups(groups: ApiKeyScopeGroup[] | undefined): ApiKeyScopeGroup[] {
  return (groups ?? [])
    .map((g) => ({ ...g, scopes: g.scopes.filter((s) => s.grantable !== false) }))
    .filter((g) => g.scopes.length > 0)
}

/** The `.env` / MCP client snippet for a full key. The MCP config reads it via `${env:...}`. */
export function envSnippet(secret: string): string {
  return `${MCP_API_KEY_ENV}=${secret}`
}

/** MCP client config that references the variable instead of embedding the key. */
export const MCP_CONFIG_HINT = `{
  "mcpServers": {
    "sheetstorm": {
      "command": "/path/to/mcp-server/.venv/bin/sheetstorm-mcp",
      "env": {
        "SHEETSTORM_API_URL": "http://localhost:5000/api/v1",
        "${MCP_API_KEY_ENV}": "\${env:${MCP_API_KEY_ENV}}"
      }
    }
  }
}`

// ── Errors ────────────────────────────────────────────────────────────

const API_KEY_COPY: Record<string, ErrorDescription> = {
  api_keys_disabled: {
    title: 'API keys are disabled',
    description: 'API keys are switched off for this organization. An administrator can enable them in Settings.',
  },
  interactive_session_required: {
    title: 'Sign-in required',
    description: 'API keys can only be managed from a signed-in browser session, not with an API key.',
  },
  api_key_limit: {
    title: 'Key limit reached',
    description: 'The limit of active API keys has been reached. Revoke a key you no longer use and try again.',
  },
  name_conflict: {
    title: 'Name already in use',
    description: 'An active key with this name already exists. Choose another name.',
  },
  key_not_active: {
    title: 'Key is not active',
    description: 'Only an active key can be rotated. Create a new key instead.',
  },
  owner_inactive: {
    title: 'Owner is disabled',
    description: 'The owner of this key is disabled. Enable the account first.',
  },
  not_service_account: {
    title: 'Not a service account',
    description: 'Keys can only be created for yourself or for a service account.',
  },
  revocation_failed: {
    title: 'Could not revoke sessions',
    description: 'The session store is unavailable, so nothing was changed. Try again shortly.',
  },
}

/** Whether `err` carries a code this module (not `describeError`) has copy for. */
export function isApiKeyCode(err: unknown): boolean {
  return isApiError(err) && !!err.code && (err.code === 'invalid_scopes' || err.code in API_KEY_COPY)
}

function list(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
}

/** `describeError` plus the API-key codes it leaves generic (incl. `invalid_scopes` details). */
export function describeApiKeyError(err: unknown): ErrorDescription {
  if (isApiError(err) && err.code) {
    if (err.code === 'invalid_scopes') {
      const d = err.details ?? {}
      const parts = [
        ['Not grantable to keys', list(d.forbidden)],
        ['Unknown', list(d.unknown)],
        ['Not held by the owner', list(d.not_held)],
      ]
        .filter(([, keys]) => (keys as string[]).length > 0)
        .map(([label, keys]) => `${label}: ${(keys as string[]).join(', ')}`)
      return {
        title: 'Invalid scopes',
        description: parts.length ? parts.join('. ') + '.' : err.message || 'Select at least one scope.',
      }
    }
    if (API_KEY_COPY[err.code]) return API_KEY_COPY[err.code]
  }
  return describeError(err)
}

/** Destructive toast `Couldn't <action>` with API-key-aware copy. Aborts are ignored. */
export function notifyApiKeyError(err: unknown, action: string): void {
  if (isAbortError(err)) return
  toast({ variant: 'destructive', title: `Couldn't ${action}`, description: describeApiKeyError(err).description })
}

/** `{field: message}` from a 400 `validation_error` body (empty for anything else). */
export function fieldErrors(err: unknown): Record<string, string> {
  if (!isApiError(err)) return {}
  const fields = err.details?.fields
  if (!fields || typeof fields !== 'object') return {}
  return Object.fromEntries(
    Object.entries(fields as Record<string, unknown>).filter((e): e is [string, string] => typeof e[1] === 'string')
  )
}
