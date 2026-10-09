/**
 * RBAC, organization and AI-availability endpoints plus the pure helpers the
 * admin UI uses to mirror the backend guardrails (cosmetic only: the server's
 * `rbac_guard` stays authoritative).
 */
import { api, isApiError } from '@/lib/api'
import type {
  AiAvailabilityResponse,
  ClonedRole,
  Organization,
  OrganizationUpdate,
  PermissionCatalog,
  PermissionDef,
  Role,
  RoleInput,
} from '@/types'

export const rbac = {
  listPermissions: () => api.get<PermissionCatalog>('/permissions'),
  listRoles: () => api.get<{ items: Role[] }>('/roles'),
  getRole: (id: string) => api.get<Role>(`/roles/${id}`),
  createRole: (data: RoleInput) => api.post<Role>('/roles', data),
  updateRole: (id: string, data: Partial<RoleInput>) => api.put<Role>(`/roles/${id}`, data),
  cloneRole: (id: string, data: { name: string; description?: string }) =>
    api.post<ClonedRole>(`/roles/${id}/clone`, data),
  deleteRole: (id: string) => api.delete<{ message: string }>(`/roles/${id}`),
  assignRole: (userId: string, roleId: string) => api.post(`/users/${userId}/roles`, { role_id: roleId }),
  revokeRole: (userId: string, roleId: string) => api.delete(`/users/${userId}/roles/${roleId}`),
}

export const organization = {
  get: () => api.get<Organization>('/organization'),
  update: (data: OrganizationUpdate) => api.put<Organization>('/organization', data),
}

export const aiAvailabilityEndpoint = (incidentId: string) => `/incidents/${incidentId}/reports/types`

export const aiAvailability = {
  forIncident: (incidentId: string, opts?: { signal?: AbortSignal }) =>
    api.get<AiAvailabilityResponse>(aiAvailabilityEndpoint(incidentId), opts),
}

/** Holding both makes a user an administrator for the last-admin guard (backend ADMIN_CORE). */
export const ADMIN_CORE = ['users:manage', 'roles:manage'] as const

/**
 * Mirror of backend `permissions.IMPLIED_PERMISSIONS`: used only for the
 * grant-ceiling comparison (an Administrator holds read_all, not read_team).
 */
export const IMPLIED_PERMISSIONS: Record<string, readonly string[]> = {
  'incidents:read_all': ['incidents:read_team', 'incidents:read_tlp_white'],
}

export function withImplied(perms: readonly string[] | undefined): Set<string> {
  const out = new Set(perms ?? [])
  for (const key of Array.from(out)) {
    for (const implied of IMPLIED_PERMISSIONS[key] ?? []) out.add(implied)
  }
  return out
}

/** Keys of `required` the holder of `granted` lacks (sorted). */
export function missingPermissions(
  required: readonly string[] | undefined,
  granted: readonly string[] | undefined
): string[] {
  const have = withImplied(granted)
  return Array.from(new Set(required ?? [])).filter((p) => !have.has(p)).sort()
}

/** Whether a caller holding `granted` may grant all of `perms` (backend assert_can_grant). */
export function canGrant(granted: readonly string[] | undefined, perms: readonly string[] | undefined): boolean {
  return missingPermissions(perms, granted).length === 0
}

export function isAdminCore(perms: readonly string[] | undefined): boolean {
  return ADMIN_CORE.every((p) => (perms ?? []).includes(p))
}

/** The catalog grouped in server order; unknown groups go last. */
export function groupCatalog(
  catalog: PermissionCatalog | null | undefined
): { key: string; label: string; items: PermissionDef[] }[] {
  if (!catalog) return []
  const byGroup = new Map<string, PermissionDef[]>()
  for (const item of catalog.items) {
    const list = byGroup.get(item.group) ?? []
    list.push(item)
    byGroup.set(item.group, list)
  }
  const out = catalog.groups
    .filter((g) => byGroup.has(g.key))
    .map((g) => ({ key: g.key, label: g.label, items: byGroup.get(g.key)! }))
  const known = new Set(catalog.groups.map((g) => g.key))
  byGroup.forEach((items, key) => {
    if (!known.has(key)) out.push({ key, label: key, items })
  })
  return out
}

/** Codes the RBAC guard answers with (backend services/rbac_guard.py). */
export const GUARD_CODES = [
  'privilege_escalation',
  'insufficient_privilege',
  'last_admin',
  'self_lockout',
  'self_action',
  'use_change_password',
  'unknown_permissions',
] as const

/**
 * Permission keys a guard error names: `missing` (privilege_escalation /
 * insufficient_privilege), `platform_only` (platform-scoped grant outside the
 * platform org) and `unknown` (unknown_permissions).
 */
export function permissionsFromError(err: unknown): string[] {
  if (!isApiError(err) || !err.details) return []
  const keys: string[] = []
  for (const field of ['missing', 'platform_only', 'unknown'] as const) {
    const v = err.details[field]
    if (Array.isArray(v)) keys.push(...v.filter((x): x is string => typeof x === 'string'))
  }
  return Array.from(new Set(keys))
}
