/**
 * Admin overview (organizations:manage): users and MFA adoption, the
 * last-admin warning, recent admin changes, the audit chain and system
 * status. Infra sections appear only when the backend returns them
 * (platform admins).
 */

"use client"

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowRight, GitCompare, Loader2, RefreshCw, ScrollText, ShieldAlert, Users } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermission } from '@/components/auth/permission-gate'
import { admin } from '@/lib/endpoints/admin'
import { describeError } from '@/lib/errors'
import type { AdminOverview, AdminOverviewUsers, RecentAdminAction, SystemStatus } from '@/types'
import { activityHref } from '@/components/audit/audit-filters'
import { AuditIntegrityPanel } from '@/components/audit/AuditIntegrityPanel'
import { SystemStatusGrid, isProbeFailure } from '@/components/audit/SystemStatusGrid'
import { actionLabel, humanize } from '@/components/audit/AuditLogDetail'

const OVERVIEW_PERMISSION = 'organizations:manage'

type Load<T> = { data: T | null; error: unknown; loading: boolean }
const initial = { data: null, error: null, loading: true }

function SectionError({ error, onRetry }: { error: unknown; onRetry(): void }) {
  const d = describeError(error)
  return (
    <div role="alert" className="flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm">
      <AlertTriangle className="h-4 w-4 text-red-400" />
      <span>{d.description}</span>
      <Button variant="ghost" size="sm" className="ml-auto" onClick={onRetry}>
        Retry
      </Button>
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: 'warn' }) {
  return (
    <div className="rounded-md border border-white/10 bg-slate-900/40 px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`text-xl font-semibold tabular-nums ${tone === 'warn' ? 'text-amber-400' : ''}`}>{value}</p>
    </div>
  )
}

function UsersCard({ users, registrationEnabled }: { users: AdminOverviewUsers; registrationEnabled: boolean }) {
  const roles = Object.entries(users.by_role).sort((a, b) => b[1] - a[1])
  const pct = users.mfa_adoption_pct
  return (
    <Card data-testid="overview-users">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Users className="h-4 w-4 text-muted-foreground" />
          Users
        </CardTitle>
        <CardDescription>
          Self-registration is {registrationEnabled ? 'open' : 'closed'}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Stat label="Total" value={users.total} />
          <Stat label="Active" value={users.active} />
          <Stat label="Disabled" value={users.disabled} />
          {users.locked !== null && <Stat label="Locked" value={users.locked} tone={users.locked > 0 ? 'warn' : undefined} />}
          {users.pending_invites !== null && <Stat label="Pending invites" value={users.pending_invites} />}
        </div>

        <div>
          <div className="mb-1 flex items-baseline justify-between text-sm">
            <span className="text-muted-foreground">MFA adoption (active users)</span>
            <span className="tabular-nums">{pct === null ? '—' : `${pct}%`}</span>
          </div>
          <div
            className="h-2 overflow-hidden rounded-full bg-white/10"
            role="progressbar"
            aria-label="MFA adoption"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct ?? 0}
          >
            <div className="h-full bg-emerald-500/70" style={{ width: `${Math.min(100, Math.max(0, pct ?? 0))}%` }} />
          </div>
          {users.admins_without_mfa > 0 && (
            <p className="mt-2 flex items-center gap-1.5 text-xs text-amber-400">
              <ShieldAlert className="h-3.5 w-3.5" />
              {users.admins_without_mfa} administrator{users.admins_without_mfa === 1 ? '' : 's'} without MFA
            </p>
          )}
        </div>

        {roles.length > 0 && (
          <div>
            <p className="mb-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">Active users by role</p>
            <dl className="space-y-1">
              {roles.map(([name, n]) => (
                <div key={name} className="flex justify-between text-sm">
                  <dt>{name}</dt>
                  <dd className="tabular-nums text-muted-foreground">{n}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        <Link href="/dashboard/admin/users" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
          Manage users <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </CardContent>
    </Card>
  )
}

function actionHref(a: RecentAdminAction): string {
  return a.resource_id
    ? activityHref({ event_type: 'admin_action', resource_id: a.resource_id })
    : activityHref({ event_type: 'admin_action', action: a.action })
}

function RecentActionsCard({ actions }: { actions: RecentAdminAction[] }) {
  return (
    <Card data-testid="overview-recent-actions">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Recent admin actions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {actions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No admin actions recorded yet.</p>
        ) : (
          <ul className="divide-y divide-white/5">
            {actions.map((a) => (
              <li key={a.id}>
                <Link href={actionHref(a)} className="flex items-center gap-3 py-2 text-sm hover:bg-white/5">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">
                      {actionLabel(a.action)}
                      {a.resource_type && <span className="font-normal text-muted-foreground"> · {humanize(a.resource_type)}</span>}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">{a.user_email ?? 'System'}</p>
                  </div>
                  {a.has_changes && (
                    <span className="inline-flex items-center gap-1 rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      <GitCompare className="h-3 w-3" aria-hidden />
                      diff
                    </span>
                  )}
                  <Timestamp value={a.created_at} className="shrink-0 text-xs text-muted-foreground" />
                </Link>
              </li>
            ))}
          </ul>
        )}
        <Link
          href={activityHref({ event_type: 'admin_action', has_changes: 'true' })}
          className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
        >
          All admin changes <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </CardContent>
    </Card>
  )
}

function AuditCard({ status }: { status: SystemStatus | null }) {
  const audit = status && !isProbeFailure(status.audit) ? status.audit : null
  return (
    <Card data-testid="overview-audit">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ScrollText className="h-4 w-4 text-muted-foreground" />
          Audit log
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {status && isProbeFailure(status.audit) && <p className="text-sm text-red-400">Audit status unavailable</p>}
        {audit && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
            <dt className="text-muted-foreground">Retention</dt>
            <dd>{audit.retention_days === null ? 'Keep forever' : `${audit.retention_days} days`}</dd>
            <dt className="text-muted-foreground">Legal hold</dt>
            <dd className={audit.legal_hold ? 'text-amber-400' : undefined}>{audit.legal_hold ? 'On (purges blocked)' : 'Off'}</dd>
            <dt className="text-muted-foreground">Rows</dt>
            <dd className="tabular-nums">{audit.total_rows.toLocaleString()}</dd>
            <dt className="text-muted-foreground">Oldest entry</dt>
            <dd>
              <Timestamp value={audit.oldest_entry_at} />
            </dd>
          </dl>
        )}
        <AuditIntegrityPanel chain={audit?.chain ?? null} />
        <Link
          href="/dashboard/admin/settings?tab=audit-retention"
          className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
        >
          Retention & legal hold <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </CardContent>
    </Card>
  )
}

function OverviewContent() {
  const [overview, setOverview] = useState<Load<AdminOverview>>(initial)
  const [status, setStatus] = useState<Load<SystemStatus>>(initial)

  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    admin
      .getOverview()
      .then((data) => !cancelled && setOverview({ data, error: null, loading: false }))
      .catch((error) => !cancelled && setOverview({ data: null, error, loading: false }))
    admin
      .getSystemStatus()
      .then((data) => !cancelled && setStatus({ data, error: null, loading: false }))
      .catch((error) => !cancelled && setStatus({ data: null, error, loading: false }))
    return () => {
      cancelled = true
    }
  }, [tick])

  const load = useCallback(() => {
    setOverview((s) => ({ ...s, loading: true }))
    setStatus((s) => ({ ...s, loading: true }))
    setTick((t) => t + 1)
  }, [])

  const busy = overview.loading || status.loading
  const ov = overview.data

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Admin overview</h1>
          <p className="mt-1 text-sm text-muted-foreground">Accounts, audit integrity and system status for your organization</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={busy}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Refresh
        </Button>
      </div>

      {ov?.last_admin_warning && (
        <div role="alert" className="flex items-start gap-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Only one active administrator</p>
            <p className="text-amber-300/80">
              If this account is lost or locked, nobody can manage the organization. Grant a second user administrator access.
            </p>
          </div>
        </div>
      )}

      {overview.error ? <SectionError error={overview.error} onRetry={load} /> : null}

      <div className="grid gap-4 lg:grid-cols-3">
        {ov ? (
          <>
            <UsersCard users={ov.users} registrationEnabled={ov.registration_enabled} />
            <RecentActionsCard actions={ov.recent_admin_actions} />
          </>
        ) : overview.loading ? (
          <>
            <Skeleton className="h-72" />
            <Skeleton className="h-72" />
          </>
        ) : null}
        <AuditCard status={status.data} />
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">System status</h2>
        {status.error ? <SectionError error={status.error} onRetry={load} /> : null}
        {status.data ? (
          <SystemStatusGrid status={status.data} />
        ) : status.loading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
        ) : null}
      </section>
    </div>
  )
}

export default function AdminOverviewPage() {
  const allowed = usePermission(OVERVIEW_PERMISSION)
  if (!allowed) {
    return (
      <div className="p-6">
        <p className="text-sm text-muted-foreground">You don&apos;t have access to the admin overview.</p>
      </div>
    )
  }
  return <OverviewContent />
}
