'use client'

/**
 * User details drawer: profile, account state (with the admin-only fields
 * when you hold users:manage), roles, teams, a sessions placeholder and the
 * recent activity by / about the user (audit_logs:read).
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Loader2 } from 'lucide-react'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermission } from '@/components/auth/permission-gate'
import { isAbortError } from '@/lib/api'
import { usersAdmin } from '@/lib/endpoints/users-admin'
import type { AdminUser, AuditLog } from '@/types'
import { describeUserError } from './lifecycle-errors'
import { UserStatusBadges } from './UserStatusBadges'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-2 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words text-foreground">{children}</dd>
    </div>
  )
}

export function UserDetailDrawer({
  user,
  open,
  onOpenChange,
}: {
  user: AdminUser | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-lg">
        {user && <DrawerBody key={user.id} user={user} />}
      </SheetContent>
    </Sheet>
  )
}

function DrawerBody({ user }: { user: AdminUser }) {
  const canReadAudit = usePermission('audit_logs:read')
  const [detail, setDetail] = useState<AdminUser | null>(null)
  const [activity, setActivity] = useState<AuditLog[] | null>(null)
  const [activityError, setActivityError] = useState<unknown>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    usersAdmin
      .get(user.id)
      .then((d) => !ctrl.signal.aborted && setDetail(d))
      .catch(() => {
        /* the row data stays on screen */
      })
    if (canReadAudit) {
      usersAdmin
        .activity(user.id, { scope: 'all', per_page: 20 }, { signal: ctrl.signal })
        .then((res) => !ctrl.signal.aborted && setActivity(res.items))
        .catch((err) => {
          if (!isAbortError(err) && !ctrl.signal.aborted) setActivityError(err)
        })
    }
    return () => ctrl.abort()
  }, [user.id, canReadAudit])

  const u = detail ?? user

  return (
    <div className="space-y-6">
      <SheetHeader>
        <SheetTitle>{u.name || u.email}</SheetTitle>
        <SheetDescription>{u.email}</SheetDescription>
        <UserStatusBadges user={u} />
      </SheetHeader>

      <section aria-labelledby="user-profile">
        <h3 id="user-profile" className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Account
        </h3>
        <dl className="divide-y divide-border">
          <Row label="Sign-in">
            {u.is_service_account === true ? 'Service account (API keys only)' : u.auth_provider || 'local'}
          </Row>
          <Row label="Organisational role">{u.organizational_role || '—'}</Row>
          <Row label="Last sign-in">
            <Timestamp value={u.last_login} seconds={false} fallback="Never" />
          </Row>
          <Row label="Created">
            <Timestamp value={u.created_at} seconds={false} />
          </Row>
          {u.password_changed_at !== undefined && (
            <Row label="Password changed">
              <Timestamp value={u.password_changed_at} seconds={false} fallback="—" />
            </Row>
          )}
          {u.is_locked && (
            <Row label="Locked until">
              <Timestamp value={u.locked_until} seconds={false} />
            </Row>
          )}
          {u.failed_login_count !== undefined && <Row label="Failed sign-ins">{u.failed_login_count}</Row>}
          {!u.is_active && (
            <>
              <Row label="Disabled">
                <Timestamp value={u.deactivated_at} seconds={false} fallback="—" />
                {u.deactivated_by?.name ? ` by ${u.deactivated_by.name}` : ''}
              </Row>
              {u.deactivation_reason && <Row label="Reason">{u.deactivation_reason}</Row>}
            </>
          )}
        </dl>
      </section>

      <section aria-labelledby="user-access">
        <h3 id="user-access" className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Roles and teams
        </h3>
        <div className="flex flex-wrap gap-1">
          {u.roles.map((r) => (
            <Badge key={r} variant="outline">
              {r}
            </Badge>
          ))}
          {(u.teams ?? []).map((t) => (
            <Badge key={t.id} variant="default">
              {t.name}
            </Badge>
          ))}
        </div>
      </section>

      <section aria-labelledby="user-sessions" className="rounded-md border border-border p-3">
        <h3 id="user-sessions" className="text-sm font-medium">
          Sessions
        </h3>
        <p className="mt-1 text-xs text-muted-foreground">Available with session management.</p>
      </section>

      {canReadAudit && (
        <section aria-labelledby="user-activity">
          <div className="mb-2 flex items-center justify-between">
            <h3 id="user-activity" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Recent activity
            </h3>
            <Link
              href={`/dashboard/activity?user_id=${encodeURIComponent(u.id)}`}
              className="text-xs text-primary hover:underline"
            >
              View all
            </Link>
          </div>
          {activityError ? (
            <p role="alert" className="text-sm text-red-400">
              {describeUserError(activityError).description}
            </p>
          ) : activity === null ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Loading activity" />
          ) : activity.length === 0 ? (
            <p className="text-sm text-muted-foreground">No activity recorded.</p>
          ) : (
            <ul className="space-y-1.5" aria-label="Recent activity">
              {activity.map((a) => (
                <li key={a.id} className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="min-w-0 truncate">
                    <span className="font-mono text-xs text-muted-foreground">{a.action}</span>
                    {a.user?.name && a.user.id !== u.id && (
                      <span className="ml-2 text-xs text-muted-foreground">by {a.user.name}</span>
                    )}
                  </span>
                  <Timestamp value={a.created_at} seconds={false} className="shrink-0 text-xs text-muted-foreground" />
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
