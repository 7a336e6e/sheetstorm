/**
 * User-facing error copy and toast helpers.
 *
 * Mutations: `catch (err) { notifyError(err, 'delete the host') }`.
 * Lists don't toast: they render `describeError(query.error)` inline.
 * Only the server's `message` ever reaches the UI, never a stack or body dump,
 * and 5xx messages are replaced with generic copy.
 */
import { toast } from '@/components/ui/use-toast'
import { isAbortError, isApiError } from './api'

export interface ErrorDescription {
  title: string
  description: string
}

const TLP_LABEL: Record<string, string> = {
  white: 'TLP:WHITE',
  green: 'TLP:GREEN',
  amber: 'TLP:AMBER',
  amber_strict: 'TLP:AMBER+STRICT',
  red: 'TLP:RED',
}

function str(v: unknown): string | undefined {
  return typeof v === 'string' && v.trim() ? v : undefined
}

/** `a, b` from a string array, or undefined when empty / not an array. */
function keyList(v: unknown): string | undefined {
  if (!Array.isArray(v)) return undefined
  const keys = v.filter((x): x is string => typeof x === 'string' && x.length > 0)
  return keys.length ? keys.join(', ') : undefined
}

/** `3 case notes, 1 tasks` from a `{table: count}` map (user_has_records), or undefined. */
function recordCounts(v: unknown): string | undefined {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return undefined
  const parts = Object.entries(v as Record<string, unknown>)
    .filter((e): e is [string, number] => typeof e[1] === 'number' && e[1] > 0)
    .map(([table, n]) => `${n} ${table.replace(/_/g, ' ')}`)
  return parts.length ? parts.join(', ') : undefined
}

function withKeys(text: string, label: string, keys: unknown): string {
  const list = keyList(keys)
  return list ? `${text.replace(/\.$/, '')}. ${label}: ${list}.` : text
}

/** Copy for specific server error codes, independent of the HTTP status. */
function describeCode(
  code: string,
  details: Record<string, unknown> | undefined,
  message: string | undefined
): ErrorDescription | null {
  switch (code) {
    case 'ai_blocked_by_tlp': {
      const tlp = str(details?.tlp)
      const label = tlp ? TLP_LABEL[tlp] ?? `TLP:${tlp.toUpperCase()}` : 'this TLP level'
      const mode = str(details?.mode)
      return {
        title: 'Blocked by data egress policy',
        description:
          mode === 'local_only'
            ? `Your organization only allows local AI providers for ${label} incidents.`
            : `Your organization's policy does not allow AI features for ${label} incidents.`,
      }
    }
    case 'incident_archived':
      return {
        title: 'Incident is archived',
        description: message ?? 'Archived incidents are read-only. Unarchive it to make changes.',
      }
    case 'tlp_restricted':
      return {
        title: 'Blocked by TLP',
        description:
          message ?? 'These values appear in a restricted TLP incident and cannot be sent for enrichment.',
      }
    case 'password_change_required':
      return { title: 'Password change required', description: 'Change your password to continue.' }
    case 'mfa_enrollment_required':
      return {
        title: 'MFA enrollment required',
        description: 'Set up multi-factor authentication to continue.',
      }
    case 'already_assigned':
      return {
        title: 'Already assigned',
        description: message ?? 'That assignment already exists.',
      }
    case 'user_has_records': {
      const counts = recordCounts(details?.counts)
      return {
        title: 'User has authored records',
        description: `This user has authored records${counts ? ` (${counts})` : ''}; deactivate the account instead.`,
      }
    }
    case 'conflict':
      return {
        title: 'Changed by someone else',
        description: 'This item was modified after you opened it. Review the latest version and try again.',
      }
    // RBAC guardrails (backend services/rbac_guard.py): the server message is shown as is.
    case 'privilege_escalation': {
      const platformOnly = keyList(details?.platform_only)
      if (platformOnly) {
        return {
          title: 'Platform-only permission',
          description: `${message ?? 'Platform-only permissions cannot be granted in this organization.'} (${platformOnly})`,
        }
      }
      return {
        title: 'Exceeds your permissions',
        description: withKeys(message ?? "You can't grant permissions you don't hold.", 'Missing', details?.missing),
      }
    }
    case 'insufficient_privilege':
      return {
        title: 'Insufficient privilege',
        description: withKeys(message ?? "This user holds permissions you don't have.", 'Missing', details?.missing),
      }
    case 'last_admin':
      return {
        title: 'Last administrator',
        description: message ?? 'This change would leave the organization without an active administrator.',
      }
    case 'self_lockout':
      return {
        title: 'Would lock you out',
        description:
          message ?? 'This change would remove your own ability to manage users and roles. Ask another administrator.',
      }
    case 'self_action': {
      const action = str(details?.action)
      return {
        title: 'Not allowed on your own account',
        description: message ?? `You can't ${action ?? 'do that to'} your own account.`,
      }
    }
    case 'use_change_password':
      return {
        title: 'Use Change password',
        description: 'Change your own password from your profile; it asks for your current password.',
      }
    case 'unknown_permissions':
      return {
        title: 'Unknown permissions',
        description: withKeys(message ?? 'Unknown permission key(s).', 'Unknown', details?.unknown),
      }
    case 'system_role_immutable':
      return {
        title: 'Built-in role',
        description: message ?? "Built-in roles can't be changed. Clone the role and edit the copy.",
      }
    default:
      return null
  }
}

/** Map any thrown value to short, safe UI copy. */
export function describeError(err: unknown): ErrorDescription {
  if (isAbortError(err)) {
    return { title: 'Cancelled', description: 'The request was cancelled.' }
  }
  if (!isApiError(err)) {
    const message = err instanceof Error ? str(err.message) : undefined
    return { title: 'Something went wrong', description: message ?? 'An unexpected error occurred.' }
  }

  const message = str(err.message)
  if (err.code) {
    const byCode = describeCode(err.code, err.details, message)
    if (byCode) return byCode
  }

  const s = err.status
  if (s === 0) {
    return { title: 'Network error', description: 'Could not reach the server. Check your connection and try again.' }
  }
  if (s === 401) {
    return { title: 'Session expired', description: 'Sign in again to continue.' }
  }
  if (s === 403) {
    return { title: 'Permission denied', description: "You don't have permission to do that." }
  }
  if (s === 404) {
    return { title: 'Not found', description: 'Not found — it may have been deleted.' }
  }
  if (s === 429) {
    return { title: 'Too many requests', description: 'Too many requests — try again shortly.' }
  }
  if (s >= 500) {
    return { title: 'Server error', description: 'The server failed to handle the request. Try again later.' }
  }
  if (s === 409) {
    return { title: 'Conflict', description: message ?? 'The request conflicts with the current state.' }
  }
  // 400, 413, 422 and other 4xx: the server's validation message.
  return { title: 'Invalid request', description: message ?? 'The request was rejected.' }
}

/** Destructive toast `Couldn't <action>` with the described reason. Aborts are ignored. */
export function notifyError(err: unknown, action: string): void {
  if (isAbortError(err)) return
  if (process.env.NODE_ENV === 'development') {
    console.error(`Couldn't ${action}:`, err)
  }
  const { description } = describeError(err)
  toast({ variant: 'destructive', title: `Couldn't ${action}`, description })
}

export function notifySuccess(title: string, description?: string): void {
  toast({ title, description })
}
