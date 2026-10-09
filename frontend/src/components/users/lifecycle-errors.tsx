'use client'

/**
 * Copy for the user-lifecycle codes that `describeError` leaves generic
 * (backend services/{user_lifecycle,invite_service,token_revocation}.py).
 * Guard codes (`privilege_escalation`, `insufficient_privilege`, `last_admin`,
 * `self_action`, `use_change_password`, ...) and `user_has_records` /
 * `already_assigned` stay with `describeError` / `GuardErrorAlert`.
 */
import { isAbortError, isApiError } from '@/lib/api'
import { describeError, type ErrorDescription } from '@/lib/errors'
import { toast } from '@/components/ui/use-toast'
import { GuardErrorAlert } from '@/components/auth/guard-error-alert'

const LIFECYCLE_COPY: Record<string, ErrorDescription> = {
  revocation_failed: {
    title: 'Sessions could not be revoked',
    description: 'The session store is unavailable, so nothing was changed. Try again shortly.',
  },
  already_disabled: { title: 'Already disabled', description: 'This user is already disabled.' },
  user_disabled: {
    title: 'User is disabled',
    description: 'Enable the user before resetting their password.',
  },
  mfa_not_enabled: { title: 'MFA not enabled', description: 'This user has no MFA to reset.' },
  not_assigned: { title: 'Role not assigned', description: 'The user does not hold that role.' },
  already_member: {
    title: 'Already a member',
    description: 'A user with this email is already a member of your organization.',
  },
  too_many_pending: {
    title: 'Too many pending invites',
    description: 'Revoke some pending invites before creating new ones.',
  },
  already_accepted: { title: 'Already accepted', description: 'This invite was already accepted.' },
  invite_invalid: {
    title: 'Invitation not valid',
    description: 'This invitation is invalid or has expired. Ask your administrator for a new link.',
  },
  reset_invalid: {
    title: 'Reset link not valid',
    description: 'This reset link is invalid or has expired. Ask your administrator for a new one.',
  },
}

/** `describeError` plus the lifecycle codes above. */
export function describeUserError(err: unknown): ErrorDescription {
  if (isApiError(err) && err.code && LIFECYCLE_COPY[err.code]) return LIFECYCLE_COPY[err.code]
  return describeError(err)
}

/** Destructive toast `Couldn't <action>` with lifecycle-aware copy. */
export function notifyUserError(err: unknown, action: string): void {
  if (isAbortError(err)) return
  toast({ variant: 'destructive', title: `Couldn't ${action}`, description: describeUserError(err).description })
}

/** Inline alert for a failed lifecycle call: guard codes via GuardErrorAlert. */
export function UserErrorAlert({ error, labelOf }: { error: unknown; labelOf?: (key: string) => string }) {
  if (!error) return null
  if (isApiError(error) && error.code && LIFECYCLE_COPY[error.code]) {
    const { title, description } = LIFECYCLE_COPY[error.code]
    return (
      <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
        <p className="font-medium">{title}</p>
        <p className="mt-0.5">{description}</p>
      </div>
    )
  }
  return <GuardErrorAlert error={error} labelOf={labelOf} />
}
