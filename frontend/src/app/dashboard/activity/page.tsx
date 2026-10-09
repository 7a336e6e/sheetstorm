/**
 * Activity / audit log (audit_logs:read).
 *
 * Server-paginated DataTable on `GET /audit-logs`. Filters, search, sort,
 * page and page size live in the URL (`audit.*`, see
 * components/audit/audit-filters.ts), so a filtered view can be shared.
 * Expanding a row shows its details and the before/after diff of admin
 * changes. Export (CSV / JSONL) of the current filters needs
 * `audit_logs:export`.
 */

"use client"

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { Filter, GitCompare, Radio } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { DataTable, type DataTableColumn } from '@/components/ui/data-table'
import { Timestamp } from '@/components/ui/timestamp'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import { useSocketEvent } from '@/hooks/use-socket'
import { AUDIT_LOGS_ENDPOINT, auditLogsApi } from '@/lib/endpoints/admin'
import { cn } from '@/lib/utils'
import type { AuditFacets, AuditLogEntry, AuditStats } from '@/types'
import {
  AUDIT_DEFAULTS,
  AUDIT_PAGE_SIZES,
  AUDIT_URL_KEY,
  EVENT_TYPES,
  auditApiFilters,
  countActiveFilters,
  isLiveView,
  migrateLegacyParams,
} from '@/components/audit/audit-filters'
import { AuditFilterBar } from '@/components/audit/AuditFilterBar'
import { AuditExportMenu } from '@/components/audit/AuditExportMenu'
import { AuditLogDetail, actionLabel, humanize, statusTone } from '@/components/audit/AuditLogDetail'
import { hasChanges } from '@/components/audit/AuditDiffViewer'

const EVENT_BADGE: Record<string, string> = {
  authentication: 'bg-emerald-500/15 text-emerald-400',
  authorization: 'bg-orange-500/15 text-orange-400',
  data_access: 'bg-sky-500/15 text-sky-400',
  data_modification: 'bg-blue-500/15 text-blue-400',
  admin_action: 'bg-purple-500/15 text-purple-400',
  security_event: 'bg-red-500/15 text-red-400',
  system_event: 'bg-muted text-muted-foreground',
}

const METHOD_TONE: Record<string, string> = {
  GET: 'text-emerald-400 bg-emerald-500/10',
  POST: 'text-blue-400 bg-blue-500/10',
  PUT: 'text-amber-400 bg-amber-500/10',
  PATCH: 'text-orange-400 bg-orange-500/10',
  DELETE: 'text-red-400 bg-red-500/10',
}

const SHORT_LABEL = Object.fromEntries(EVENT_TYPES.map((t) => [t.value, t.short]))

/** UTC calendar day (`YYYY-MM-DD`) `daysAgo` days before now (stats `by_day` keys). */
function utcDay(daysAgo = 0): string {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() - daysAgo)
  return d.toISOString().slice(0, 10)
}

const columns: DataTableColumn<AuditLogEntry>[] = [
  {
    id: 'time',
    header: 'Time',
    sortKey: 'created_at',
    className: 'whitespace-nowrap',
    cell: (a) => <Timestamp value={a.created_at} className="text-xs text-muted-foreground" />,
  },
  {
    id: 'event',
    header: 'Event',
    sortKey: 'action',
    cell: (a) => (
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        <span className="font-medium">{actionLabel(a.action, a.details)}</span>
        <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-medium', EVENT_BADGE[a.event_type] ?? EVENT_BADGE.system_event)}>
          {SHORT_LABEL[a.event_type] ?? humanize(a.event_type)}
        </span>
        {hasChanges(a.details) && (
          <span className="inline-flex items-center gap-1 rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-muted-foreground" title="Has a before/after diff">
            <GitCompare className="h-3 w-3" aria-hidden />
            diff
          </span>
        )}
      </div>
    ),
  },
  {
    id: 'user',
    header: 'User',
    sortKey: 'user_email',
    cell: (a) => (
      <span className="block max-w-[220px] truncate text-sm text-muted-foreground" title={a.user_email ?? undefined}>
        {a.user?.name || a.user_email || 'System'}
      </span>
    ),
  },
  {
    id: 'resource',
    header: 'Resource',
    sortKey: 'resource_type',
    hideBelow: 'md',
    cell: (a) => (
      <span className="text-sm text-muted-foreground">
        {a.resource_type ? humanize(a.resource_type) : '—'}
        {a.incident?.title && <span className="block max-w-[200px] truncate text-xs">{a.incident.title}</span>}
      </span>
    ),
  },
  {
    id: 'status',
    header: 'Status',
    sortKey: 'status_code',
    hideBelow: 'lg',
    cell: (a) => (
      <span className="inline-flex items-center gap-2">
        {a.request_method && (
          <span className={cn('rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold', METHOD_TONE[a.request_method] ?? 'bg-muted text-muted-foreground')}>
            {a.request_method}
          </span>
        )}
        {a.status_code != null && <span className={cn('font-mono text-xs', statusTone(a.status_code))}>{a.status_code}</span>}
      </span>
    ),
  },
  {
    id: 'ip',
    header: 'IP',
    hideBelow: 'lg',
    cell: (a) => <span className="font-mono text-xs text-muted-foreground">{a.ip_address ?? '—'}</span>,
  },
  {
    id: 'seq',
    header: 'Seq',
    sortKey: 'chain_seq',
    hideBelow: 'lg',
    className: 'text-right',
    cell: (a) => <span className="font-mono text-xs text-muted-foreground">{a.chain_seq ?? '—'}</span>,
  },
]

function StatCard({ label, value }: { label: string; value: number | null }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl tabular-nums">{value === null ? '—' : value.toLocaleString()}</CardTitle>
      </CardHeader>
    </Card>
  )
}

function ActivityInner() {
  const router = useRouter()
  const pathname = usePathname()

  // Older links used plain params (`?event_type=admin_action&has_changes=true`).
  useEffect(() => {
    const qs = migrateLegacyParams(new URLSearchParams(window.location.search))
    if (qs !== null) router.replace(`${pathname}${qs ? `?${qs}` : ''}`, { scroll: false })
  }, [router, pathname])

  const query = usePaginatedQuery<AuditLogEntry>({
    endpoint: AUDIT_LOGS_ENDPOINT,
    urlKey: AUDIT_URL_KEY,
    defaults: { perPage: AUDIT_DEFAULTS.perPage, sort: AUDIT_DEFAULTS.sort },
  })
  const { state, refetch } = query
  const apiFilters = useMemo(() => auditApiFilters(state), [state])
  const filtersSig = JSON.stringify(apiFilters)
  const activeFilters = countActiveFilters(state)

  const [showFilters, setShowFilters] = useState(activeFilters > 0)
  const [facets, setFacets] = useState<AuditFacets | null>(null)
  const [stats, setStats] = useState<AuditStats | null>(null)
  const [live, setLive] = useState<{ sig: string; n: number }>({ sig: '', n: 0 })

  useEffect(() => {
    let cancelled = false
    auditLogsApi
      .facets()
      .then((f) => {
        if (!cancelled) setFacets(f)
      })
      .catch(() => {
        // Facets only feed suggestions; the filters still work without them.
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const ctrl = new AbortController()
    auditLogsApi
      .stats(JSON.parse(filtersSig), { signal: ctrl.signal })
      .then((s) => setStats(s))
      .catch(() => {
        if (!ctrl.signal.aborted) setStats(null)
      })
    return () => ctrl.abort()
  }, [filtersSig])

  // Live: count new rows while the unfiltered newest-first first page is
  // shown; the count belongs to one list state and resets when it changes.
  const stateSig = JSON.stringify(state)
  const stateRef = useRef({ state, sig: stateSig })
  useEffect(() => {
    stateRef.current = { state, sig: stateSig }
  }, [state, stateSig])
  useSocketEvent(
    'activity:new',
    useCallback(() => {
      const { state: s, sig } = stateRef.current
      if (!isLiveView(s)) return
      setLive((prev) => ({ sig, n: prev.sig === sig ? prev.n + 1 : 1 }))
    }, [])
  )
  const newCount = live.sig === stateSig ? live.n : 0
  const showNew = async () => {
    setLive({ sig: stateSig, n: 0 })
    await refetch()
  }

  const byDay = stats?.by_day ?? {}
  const today = stats ? byDay[utcDay(0)] ?? 0 : null
  const week = stats ? Array.from({ length: 7 }, (_, i) => byDay[utcDay(i)] ?? 0).reduce((a, b) => a + b, 0) : null
  const security = stats ? stats.by_event_type.security_event ?? 0 : null

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Activity</h1>
          <p className="mt-1 text-sm text-muted-foreground">Audit log of every action in your organization</p>
        </div>
        <div className="flex items-center gap-2">
          {newCount > 0 && (
            <Button variant="outline" size="sm" onClick={() => void showNew()} className="border-emerald-500/30 text-emerald-400">
              <Radio className="h-3 w-3 animate-pulse" />
              Show {newCount} new
            </Button>
          )}
          <AuditExportMenu filters={apiFilters} />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Matching events" value={stats ? stats.total : null} />
        <StatCard label="Today (UTC)" value={today} />
        <StatCard label="Last 7 days" value={week} />
        <StatCard label="Security events" value={security} />
      </div>

      {showFilters && (
        <Card>
          <CardContent className="pt-6">
            <AuditFilterBar query={query} facets={facets} />
          </CardContent>
        </Card>
      )}

      <DataTable<AuditLogEntry>
        query={query}
        columns={columns}
        getRowId={(a) => a.id}
        ariaLabel="Audit log"
        searchPlaceholder="Search action, user, resource, path…"
        pageSizes={AUDIT_PAGE_SIZES}
        toolbar={
          <Button
            variant="outline"
            size="sm"
            aria-expanded={showFilters}
            onClick={() => setShowFilters((v) => !v)}
            className={cn(activeFilters > 0 && 'border-primary/40 text-foreground')}
          >
            <Filter className="h-3.5 w-3.5" />
            Filters
            {activeFilters > 0 && (
              <span className="ml-1 rounded-full bg-primary px-1.5 text-[10px] text-primary-foreground tabular-nums">{activeFilters}</span>
            )}
          </Button>
        }
        renderExpanded={(a) => <AuditLogDetail log={a} />}
        empty={{ title: 'No activity yet', description: 'Actions in your organization will appear here.' }}
      />
    </div>
  )
}

export default function ActivityPage() {
  return (
    <Suspense fallback={null}>
      <ActivityInner />
    </Suspense>
  )
}
