/**
 * User lifecycle endpoints (W2-LIFE-UI): the admin namespace behind
 * `/users/*` (backend endpoints/{users,user_admin}.py) and the public account
 * routes behind `/auth/invites/*`, `/auth/password-reset/*` and
 * `/auth/change-password` (endpoints/{auth_lifecycle,auth}.py).
 *
 * Secrets (invite tokens / links, reset links, temporary passwords) come back
 * in a response body exactly once. Callers keep them in component state only:
 * never in the query cache, a store or browser storage.
 */
import { api, buildQuery } from '@/lib/api'
import { checkPassword, DEFAULT_PASSWORD_RULES, meetsPasswordRules, type PasswordCheck } from '@/lib/endpoints/security'
import type {
  AdminResetResult,
  AdminUser,
  AuditLog,
  BulkUserRequest,
  BulkUserResponse,
  InviteCreateInput,
  InviteCreateResult,
  InviteLookup,
  InviteStatusFilter,
  PaginatedResponse,
  PasswordRules,
  ResetPasswordMode,
  User,
  UserActivityScope,
  UserInvite,
  UserStats,
} from '@/types'

/** List endpoints (also the query-cache prefixes to invalidate). */
export const USERS_ENDPOINT = '/users'
export const INVITES_ENDPOINT = '/users/invites'

export const usersAdmin = {
  stats: () => api.get<UserStats>('/users/stats'),
  get: (id: string) => api.get<AdminUser>(`/users/${id}`),
  activity: (
    id: string,
    params: { scope?: UserActivityScope; page?: number; per_page?: number } = {},
    opts?: { signal?: AbortSignal }
  ) => api.get<PaginatedResponse<AuditLog>>(`/users/${id}/activity${buildQuery(params)}`, opts),

  disable: (id: string, reason: string) => api.post<{ user: AdminUser }>(`/users/${id}/disable`, { reason }),
  enable: (id: string) => api.post<{ user: AdminUser }>(`/users/${id}/enable`),
  forceLogout: (id: string) => api.post<{ message: string }>(`/users/${id}/force-logout`),
  unlock: (id: string) => api.post<{ user: AdminUser }>(`/users/${id}/unlock`),
  resetPassword: (id: string, mode: ResetPasswordMode, opts: { revokeSessions?: boolean } = {}) =>
    api.post<AdminResetResult>(`/users/${id}/reset-password`, {
      mode,
      ...(opts.revokeSessions === undefined ? {} : { revoke_sessions: opts.revokeSessions }),
    }),
  resetMfa: (id: string) => api.post<{ user: AdminUser }>(`/users/${id}/reset-mfa`),
  /** 409 `user_has_records` {counts, hint:'deactivate'} when the user authored records. */
  remove: (id: string, opts: { anonymize?: boolean } = {}) =>
    api.delete<{ message: string; outcome: 'deleted' | 'anonymized' }>(
      `/users/${id}${buildQuery({ anonymize: opts.anonymize ? 'true' : undefined })}`
    ),
  bulk: (body: BulkUserRequest) => api.post<BulkUserResponse>('/users/bulk', body),
  syncSupabase: () =>
    api.post<{ message: string; created: number; skipped: number; skipped_other_org?: number }>('/users/sync-supabase'),

  invites: {
    list: (params: { status?: InviteStatusFilter; q?: string; page?: number; per_page?: number } = {}) =>
      api.get<PaginatedResponse<UserInvite>>(`${INVITES_ENDPOINT}${buildQuery(params)}`),
    create: (body: InviteCreateInput) => api.post<InviteCreateResult>(INVITES_ENDPOINT, body),
    revoke: (id: string) => api.delete<{ invite: UserInvite }>(`${INVITES_ENDPOINT}/${id}`),
  },
}

/** Public (token) and self-service account routes. */
export const accountPublic = {
  lookupInvite: (token: string) => api.post<InviteLookup>('/auth/invites/lookup', { token }),
  /** Sets the session cookies on success (201). */
  acceptInvite: (body: { token: string; name: string; password: string }) =>
    api.post<{ user: User }>('/auth/invites/accept', body),
  completePasswordReset: (body: { token: string; new_password: string }) =>
    api.post<{ message: string }>('/auth/password-reset/complete', body),
  /** Authenticated; clears `must_change_password` and re-issues this session's cookies. */
  changePassword: (body: { current_password: string; new_password: string }) =>
    api.post<{ message: string }>('/auth/change-password', body),
}

/**
 * The absolute link for a one-time `accept_path` (`/auth/invite#token=…`).
 * The server's `accept_url` (FRONTEND_URL configured) wins; otherwise the
 * current origin, i.e. the address the admin is using.
 */
export function absoluteLink(res: { accept_path: string; accept_url?: string }): string {
  if (res.accept_url) return res.accept_url
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return `${origin}${res.accept_path}`
}

/**
 * Read `#token=…` from the URL fragment and strip it from the address bar so
 * the credential never reaches history, server logs or a Referer header.
 */
export function takeHashToken(): string | null {
  if (typeof window === 'undefined') return null
  const hash = window.location.hash.replace(/^#/, '')
  const token = new URLSearchParams(hash).get('token')
  if (hash) {
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
  }
  return token && token.length <= 200 ? token : null
}

/**
 * Mirror of the backend password rules (security_policy.validate_password).
 * Without `rules` the code defaults apply (12+, upper, lower, digit, any
 * non-alphanumeric symbol); pass the org's rules from usePasswordPolicy.
 */
export function passwordChecks(pw: string, rules: PasswordRules = DEFAULT_PASSWORD_RULES) {
  const met = (key: PasswordCheck['key']) => checkPassword(pw, rules).find((c) => c.key === key)?.met ?? true
  return {
    length: met('length') && met('max_bytes'),
    uppercase: met('uppercase'),
    lowercase: met('lowercase'),
    number: met('number'),
    special: met('special'),
  }
}

export function isPasswordValid(pw: string, rules: PasswordRules = DEFAULT_PASSWORD_RULES): boolean {
  return meetsPasswordRules(pw, rules)
}

/** Human copy for bulk/lifecycle item codes (per-item results carry the server message too). */
export const BULK_ACTION_LABEL: Record<BulkUserRequest['action'], string> = {
  disable: 'Disable',
  enable: 'Enable',
  force_logout: 'Force logout',
  add_role: 'Add role',
  remove_role: 'Remove role',
  add_team: 'Add to team',
}
