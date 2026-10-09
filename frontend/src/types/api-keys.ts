// API keys and service accounts (W3-APIK-UI).
// Shapes follow backend/app/{models/api_key,schemas/api_keys}.py and
// api/v1/endpoints/api_keys.py. The secret exists only in a create / rotate
// response (`ApiKeyWithSecret`); no other shape carries it.

export type ApiKeyStatus = 'active' | 'expired' | 'revoked'
export type ApiKeyStatusFilter = ApiKeyStatus | 'all'

export interface ApiKeyOwner {
  id: string
  name: string
  email: string
  is_service_account: boolean
}

export interface ApiKey {
  id: string
  organization_id: string
  owner_user_id: string
  name: string
  description: string | null
  /** Public identifier `ssk_<lookup>`; safe to show and log. */
  prefix: string
  scopes: string[]
  status: ApiKeyStatus
  expires_at: string
  last_used_at: string | null
  last_used_ip: string | null
  use_count: number
  rotated_from_id: string | null
  /** May lie in the future: a rotation with a grace period schedules the revocation. */
  revoked_at: string | null
  revoked_by: string | null
  revoked_reason: string | null
  created_by: string | null
  created_at: string
  updated_at: string | null
  owner?: ApiKeyOwner
}

/** 201 body of create / rotate: the only time the full key is ever returned. */
export interface ApiKeyWithSecret extends ApiKey {
  secret: string
}

export interface ApiKeyScope {
  /** Permission key, e.g. `incidents:read`. */
  value: string
  label: string
  description?: string
  /** Dangerous / destructive: flagged in the picker. */
  sensitive: boolean
  /** Defensive: the server only lists grantable scopes; `false` hides one. */
  grantable?: boolean
}

export interface ApiKeyScopeGroup {
  group: string
  label: string
  scopes: ApiKeyScope[]
}

/** `GET /api-keys/scopes` */
export interface ApiKeyScopesResponse {
  owner_id: string
  groups: ApiKeyScopeGroup[]
  max_lifetime_days: number
  api_keys_enabled: boolean
}

export interface ApiKeyCreateInput {
  name: string
  description?: string
  scopes: string[]
  expires_in_days?: number
  /** Omit for a key of your own; a service account id with `api_keys:manage`. */
  owner_id?: string
}

export interface ApiKeyRotateInput {
  expires_in_days?: number
  /** 0..1440: how long the old key keeps working. */
  grace_minutes: number
}

export interface ApiKeyListParams {
  status?: ApiKeyStatusFilter
  owner_id?: string
  mine?: boolean
  q?: string
  sort?: string
  page?: number
  per_page?: number
}

export interface ServiceAccountRole {
  id: string
  name: string
}

export interface ServiceAccount {
  id: string
  name: string
  email: string
  is_active: boolean
  is_service_account: true
  roles: ServiceAccountRole[]
  active_key_count: number
  created_at: string | null
  deactivated_at: string | null
}

export interface ServiceAccountCreateInput {
  name: string
  role_ids: string[]
}

export interface ServiceAccountUpdateInput {
  name?: string
  is_active?: boolean
  role_ids?: string[]
}

/** The API-key settings in `GET/PUT /organization` (`settings`). */
export interface ApiKeyOrgSettings {
  api_keys_enabled?: boolean
  api_key_max_lifetime_days?: number
}
