/**
 * Security policy and sign-in sessions (W3-SEC): `/organization/security-policy`
 * (organizations:manage), `/auth/password-policy` (public) and
 * `/users/:id/sessions` (self, or users:manage in the same org).
 *
 * The policy is versioned: PUT sends the `version` it was loaded with and a
 * stale one answers 409 `conflict` (reload and retry).
 */
import { api, buildQuery } from '@/lib/api'
import type {
  PaginatedResponse,
  PasswordRules,
  SecurityPolicyResponse,
  SecurityPolicyUpdate,
  UserSession,
} from '@/types'

export const SECURITY_POLICY_ENDPOINT = '/organization/security-policy'

export const securityPolicy = {
  get: () => api.get<SecurityPolicyResponse>(SECURITY_POLICY_ENDPOINT),
  update: (policy: SecurityPolicyUpdate, version: number) =>
    api.put<SecurityPolicyResponse>(SECURITY_POLICY_ENDPOINT, { policy, version }),
  passwordRules: () => api.get<PasswordRules>('/auth/password-policy'),
}

export const sessionsEndpoint = (userId: string) => `/users/${userId}/sessions`

export const sessions = {
  list: (userId: string, opts?: { signal?: AbortSignal }) =>
    api.get<PaginatedResponse<UserSession>>(
      `${sessionsEndpoint(userId)}${buildQuery({ per_page: 100, sort: '-last_seen_at' })}`,
      opts
    ),
  revoke: (userId: string, sessionId: string) =>
    api.delete<{ id: string; revoked: boolean }>(`${sessionsEndpoint(userId)}/${sessionId}`),
  /** Every active session; `exceptCurrent` keeps the caller's own ("sign out other devices"). */
  revokeAll: (userId: string, opts: { exceptCurrent?: boolean } = {}) =>
    api.delete<{ id: string; revoked: number }>(
      `${sessionsEndpoint(userId)}${buildQuery({ except_current: opts.exceptCurrent ? 'true' : undefined })}`
    ),
}

/** Code defaults (backend DEFAULT_POLICY.password), used until the server answers. */
export const DEFAULT_PASSWORD_RULES: PasswordRules = {
  min_length: 12,
  max_bytes: 72,
  require_upper: true,
  require_lower: true,
  require_digit: true,
  require_symbol: true,
  history_count: 0,
  max_age_days: 0,
}

export interface PasswordCheck {
  key: 'length' | 'max_bytes' | 'uppercase' | 'lowercase' | 'number' | 'special'
  label: string
  met: boolean
}

/** UTF-8 byte length (no TextEncoder: also runs in jsdom). */
function utf8Length(value: string): number {
  let bytes = 0
  for (const ch of Array.from(value)) {
    const cp = ch.codePointAt(0) ?? 0
    bytes += cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4
  }
  return bytes
}

/**
 * Client mirror of `security_policy.validate_password` (hints only; the server
 * is authoritative and also checks history and the email address).
 */
export function checkPassword(pw: string, rules: PasswordRules = DEFAULT_PASSWORD_RULES): PasswordCheck[] {
  const checks: PasswordCheck[] = [
    { key: 'length', label: `${rules.min_length}+ characters`, met: pw.length >= rules.min_length },
  ]
  if (utf8Length(pw) > rules.max_bytes) {
    checks.push({ key: 'max_bytes', label: `At most ${rules.max_bytes} bytes`, met: false })
  }
  const chars = Array.from(pw)
  const isUpper = (c: string) => c !== c.toLowerCase()
  const isLower = (c: string) => c !== c.toUpperCase()
  const isDigit = (c: string) => c >= '0' && c <= '9'
  if (rules.require_upper) checks.push({ key: 'uppercase', label: 'Uppercase', met: chars.some(isUpper) })
  if (rules.require_lower) checks.push({ key: 'lowercase', label: 'Lowercase', met: chars.some(isLower) })
  if (rules.require_digit) checks.push({ key: 'number', label: 'Number', met: chars.some(isDigit) })
  if (rules.require_symbol) {
    // Any non-alphanumeric character (cased letters and digits are alphanumeric).
    const isSymbol = (c: string) => !isUpper(c) && !isLower(c) && !isDigit(c)
    checks.push({ key: 'special', label: 'Special char', met: chars.some(isSymbol) })
  }
  return checks
}

export function meetsPasswordRules(pw: string, rules: PasswordRules = DEFAULT_PASSWORD_RULES): boolean {
  return checkPassword(pw, rules).every((c) => c.met)
}

/** One-line summary for form hints, e.g. "At least 14 characters with upper, lower, number and symbol." */
export function describePasswordRules(rules: PasswordRules): string {
  const classes = [
    rules.require_upper && 'uppercase',
    rules.require_lower && 'lowercase',
    rules.require_digit && 'a number',
    rules.require_symbol && 'a symbol',
  ].filter(Boolean) as string[]
  const tail =
    classes.length === 0
      ? ''
      : classes.length === 1
        ? ` with ${classes[0]}`
        : ` with ${classes.slice(0, -1).join(', ')} and ${classes[classes.length - 1]}`
  const history = rules.history_count > 0 ? ` Not one of your last ${rules.history_count}.` : ''
  return `At least ${rules.min_length} characters${tail}.${history}`
}

/** Short label for a session's user agent ("Firefox on macOS"). */
export function describeUserAgent(ua: string | null | undefined): string {
  if (!ua) return 'Unknown device'
  const browser =
    /Edg\//.test(ua) ? 'Edge'
      : /OPR\//.test(ua) ? 'Opera'
        : /Firefox\//.test(ua) ? 'Firefox'
          : /Chrome\//.test(ua) ? 'Chrome'
            : /Safari\//.test(ua) ? 'Safari'
              : /curl|python|httpx|node|axios/i.test(ua) ? 'Script'
                : 'Browser'
  const os =
    /Windows/.test(ua) ? 'Windows'
      : /iPhone|iPad|iOS/.test(ua) ? 'iOS'
        : /Mac OS X|Macintosh/.test(ua) ? 'macOS'
          : /Android/.test(ua) ? 'Android'
            : /Linux/.test(ua) ? 'Linux'
              : ''
  return os ? `${browser} on ${os}` : browser
}
