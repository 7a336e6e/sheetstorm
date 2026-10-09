// User lifecycle admin types (W2-LIFE-UI). Shapes follow
// backend/app/api/v1/endpoints/{users,user_admin,auth_lifecycle}.py and
// backend/app/models/{user,user_invite}.py.
import type { User } from './index'

/** `GET /users?status=` values. */
export type UserStatusFilter = 'active' | 'disabled' | 'locked' | 'must_change_password'

/** A user as the admin list / detail returns it (`to_dict`, plus `to_admin_dict` fields with users:manage). */
export interface AdminUser extends User {
  is_verified?: boolean
  mfa_enabled?: boolean
  is_locked?: boolean
  /** Only set while the lock is in force. */
  locked_until?: string | null
  must_change_password?: boolean
  /** API-key-only account (W2-APIK). Absent on servers without API keys. */
  is_service_account?: boolean
  deactivated_at?: string | null
  // to_admin_dict (users:manage) only:
  failed_login_count?: number
  deactivated_by?: { id: string; name: string | null } | null
  deactivation_reason?: string | null
  password_changed_at?: string | null
}

/** `GET /users/stats`: org-wide counts (not just the current page). */
export interface UserStats {
  total: number
  active: number
  disabled: number
  locked: number
  mfa_enabled: number
  must_change_password: number
  pending_invites: number
  by_role: Record<string, number>
}

export type InviteStatus = 'pending' | 'accepted' | 'revoked' | 'expired'
/** `GET /users/invites?status=` values (`all` lists every state). */
export type InviteStatusFilter = InviteStatus | 'all'

export interface UserInvite {
  id: string
  organization_id: string
  email: string
  name: string | null
  organizational_role: string | null
  status: InviteStatus
  role_ids: string[]
  team_ids: string[]
  roles: { id: string; name: string }[]
  teams: { id: string; name: string }[]
  expires_at: string | null
  accepted_at: string | null
  accepted_user_id: string | null
  revoked_at: string | null
  created_by: { id: string; name: string | null } | null
  created_at: string | null
}

export interface InviteCreateInput {
  email: string
  name?: string
  role_ids?: string[]
  team_ids?: string[]
  organizational_role?: string
  /** 1..7 (server default 7). */
  expires_in_days?: number
}

/** `POST /users/invites` (201). `token` / the link are a credential: show once, never store. */
export interface InviteCreateResult {
  id: string
  invite: UserInvite
  token: string
  /** `/auth/invite#token=…` (relative). */
  accept_path: string
  /** Absolute link, only when the server has FRONTEND_URL configured. */
  accept_url?: string
  superseded_invite_id: string | null
}

export type ResetPasswordMode = 'link' | 'temp'

/** `POST /users/<id>/reset-password`. The secret is in this response only. */
export type AdminResetResult =
  | { mode: 'link'; token: string; accept_path: string; expires_at: string; accept_url?: string }
  | { mode: 'temp'; temp_password: string }

export type BulkUserAction = 'disable' | 'enable' | 'force_logout' | 'add_role' | 'remove_role' | 'add_team'

export interface BulkUserRequest {
  action: BulkUserAction
  /** 1..100 unique ids. */
  user_ids: string[]
  /** Required for `disable` (1..500 chars). */
  reason?: string
  /** Required for `add_role` / `remove_role` (needs roles:manage). */
  role_id?: string
  /** Required for `add_team`. */
  team_id?: string
}

export interface BulkItemResult {
  user_id: string
  status: 'ok' | 'skipped' | 'error'
  /** Guard / lifecycle code for skipped and failed items. */
  code?: string
  message?: string
}

export interface BulkUserResponse {
  action: BulkUserAction
  bulk_request_id: string
  results: BulkItemResult[]
  summary: { ok: number; skipped: number; failed: number }
}

export type UserActivityScope = 'actor' | 'target' | 'all'

/** `POST /auth/invites/lookup`. */
export interface InviteLookup {
  email: string
  name: string | null
  organization_name: string | null
  expires_at: string
}

/** Reasons carried by the `session:revoked` socket event. */
export type SessionRevokedReason = 'force_logout' | 'disabled' | 'password_reset' | 'mfa_reset' | 'deleted' | string
