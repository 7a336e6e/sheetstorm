// RBAC, organization settings and AI availability types (W1-RBAC-UI).
// Shapes follow backend/app/api/v1/endpoints/{roles,organization,reports}.py.
import type { TLPLevel } from './index'

/** One entry of the server permission catalog (`GET /permissions`). */
export interface PermissionDef {
  key: string
  group: string
  label: string
  description: string
  /** Destructive or security-sensitive: the UI confirms before granting it. */
  dangerous: boolean
  /** Part of the MFA "privileged" scope. */
  privileged: boolean
  api_key_grantable: boolean
  /** Only effective in the platform organization. */
  platform_only: boolean
}

export interface PermissionGroupDef {
  key: string
  label: string
}

export interface PermissionCatalog {
  /** Ordered: render groups in this order. */
  groups: PermissionGroupDef[]
  items: PermissionDef[]
}

export interface Role {
  id: string
  name: string
  description: string
  permissions: string[]
  /** Global built-in role: immutable, clone it to customise. */
  is_system: boolean
  /** null for system roles. */
  organization_id?: string | null
  /** Users of the caller's org holding the role. */
  user_count?: number
  /** Custom role the caller may edit/delete (holds roles:manage and every permission of it). */
  editable?: boolean
  created_at?: string | null
}

export interface RoleInput {
  name: string
  description?: string
  permissions: string[]
}

export interface ClonedRole extends Role {
  cloned_from: string
  /** Platform-only permissions dropped because the org is not the platform org. */
  dropped_permissions?: string[]
}

export type AiPolicyMode = 'allow' | 'local_only' | 'block'

/** Per-TLP AI egress policy (missing keys fall back to the server defaults). */
export type AiTlpPolicy = Record<TLPLevel, AiPolicyMode>

export interface OrganizationSettings {
  timezone?: string
  auto_enrich_iocs?: boolean
  enrichment_allow_amber_strict?: boolean
  /** GET always returns the effective policy (all five levels). */
  ai_tlp_policy?: Partial<AiTlpPolicy>
}

export interface Organization {
  id: string
  name: string
  slug: string
  is_default: boolean
  settings: OrganizationSettings
  updated_at?: string | null
}

export interface OrganizationUpdate {
  name?: string
  /** Self-registration is not an org setting (security policy, W3-SEC). */
  settings?: OrganizationSettings
}

/** Why a provider is (not) usable under the incident's policy mode. */
export type AiProviderReason =
  | 'allowed'
  | 'local'
  | 'policy_block'
  | 'cloud_provider'
  | 'not_configured'
  | 'invalid_url'
  | 'unresolvable'
  | 'public_host'
  | 'not_allowlisted'

export interface AiProviderAvailability {
  name: string
  allowed: boolean
  reason: AiProviderReason | string
}

/** `GET /incidents/<id>/reports/types` (AI part). */
export interface AiAvailabilityResponse {
  ai_configured: boolean
  ai_allowed: boolean
  ai_providers: string[]
  policy_mode: AiPolicyMode
  providers: AiProviderAvailability[]
  tlp: TLPLevel | null
}
