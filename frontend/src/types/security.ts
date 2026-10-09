// Security policy + sign-in sessions (W3-SEC). Shapes follow
// backend/app/services/security_policy.py, backend/app/api/v1/endpoints/
// {organization,sessions,auth}.py and models/user.py::Session.to_dict.

/** `GET /auth/password-policy` (public: the caller's org, else the platform org). */
export interface PasswordRules {
  min_length: number
  /** bcrypt limit: longer passwords are refused. */
  max_bytes: number
  require_upper: boolean
  require_lower: boolean
  require_digit: boolean
  /** Any non-alphanumeric character counts as a symbol. */
  require_symbol: boolean
  /** How many most recent passwords may not be reused (0 = off). */
  history_count: number
  /** 0 = passwords never expire. */
  max_age_days: number
}

/** API value `privileged` is shown as "Admins" (users holding any privileged permission). */
export type MfaScope = 'none' | 'privileged' | 'all'

export interface SecurityPolicy {
  password: Omit<PasswordRules, 'max_bytes'>
  lockout: { threshold: number; duration_minutes: number }
  mfa: {
    required_for: MfaScope
    grace_days: number
    /** Server-managed: when the current requirement started. */
    enforced_since: string | null
  }
  session: { access_token_minutes: number; refresh_token_days: number }
  provisioning: {
    allowed_email_domains: string[]
    /** Only meaningful (and only editable) on the platform organization. */
    registration_enabled: boolean
    default_role: string
  }
}

export type SecurityPolicySection = keyof SecurityPolicy

/** A partial update: any subset of sections and fields. */
export type SecurityPolicyUpdate = {
  [S in SecurityPolicySection]?: Partial<SecurityPolicy[S]>
}

export interface SecurityPolicyBound {
  min?: number
  max?: number
  /** Value that turns the setting off (e.g. max_age_days 0). */
  off?: number
  max_items?: number
}

export interface MfaAdoptionStats {
  users_total: number
  users_mfa: number
  privileged_total: number
  privileged_mfa: number
  users_without_mfa_past_grace: number
}

/** `GET/PUT /organization/security-policy`. */
export interface SecurityPolicyResponse {
  id: string | null
  organization_id: string
  policy: SecurityPolicy
  /** 0 until the policy is first saved (code defaults). Send it back on PUT. */
  version: number
  defaults: SecurityPolicy
  bounds: Record<string, SecurityPolicyBound>
  stats: MfaAdoptionStats
  is_platform_org: boolean
  updated_by: { id: string; name: string | null } | null
  updated_at: string | null
}

/** `user.security` on `/auth/me` and sign-in responses. */
export interface SecurityStatus {
  mfa_required: boolean
  /** Restricted now: only MFA enrollment (and sign-out) work until enrolled. */
  mfa_enrollment_required: boolean
  /** Set while MFA is required but not enrolled (grace deadline). */
  mfa_grace_ends_at: string | null
  password_change_required: boolean
  password_expires_at: string | null
}

/** `GET /users/:id/sessions` items. */
export interface UserSession {
  id: string
  user_id: string
  ip_address: string | null
  user_agent: string | null
  auth_method: string | null
  created_at: string | null
  last_seen_at: string | null
  expires_at: string | null
  revoked_at: string | null
  /** The caller's own session. */
  current: boolean
}
