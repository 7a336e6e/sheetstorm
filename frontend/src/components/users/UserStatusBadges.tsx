'use client'

import { Badge } from '@/components/ui/badge'
import type { AdminUser } from '@/types'

/** Account-state badges: Active/Disabled, Locked, Must change password, MFA, Service account. */
export function UserStatusBadges({ user }: { user: AdminUser }) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {user.is_active ? (
        <Badge variant="success">Active</Badge>
      ) : (
        <Badge variant="destructive" title={user.deactivation_reason ?? undefined}>
          Disabled
        </Badge>
      )}
      {user.is_locked && (
        <Badge variant="warning" title={user.locked_until ? `Locked until ${user.locked_until}` : undefined}>
          Locked
        </Badge>
      )}
      {user.must_change_password && <Badge variant="outline">Must change password</Badge>}
      {user.mfa_enabled && <Badge variant="default">MFA</Badge>}
      {user.is_service_account === true && (
        <Badge variant="info" title="API-key-only account; it cannot sign in interactively">
          Service account
        </Badge>
      )}
    </div>
  )
}
