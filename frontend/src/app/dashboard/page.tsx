/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { useEffect, useState, useMemo } from 'react'
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, StatCard } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { SeverityBadge, StatusBadge } from '@/components/ui/badge'
import { useAuthStore } from '@/lib/store'
import { formatRelativeTime } from '@/lib/utils'
import api, { isAbortError } from '@/lib/api'
import { describeError } from '@/lib/errors'
import { incidentOverview } from '@/lib/endpoints/incident-overview'
import type { DashboardStats, Incident, PaginatedResponse } from '@/types'
import { MitreTTPAnalytics } from '@/components/incidents/MitreTTPAnalytics'
import {
  AlertTriangle,
  Activity,
  FileText,
  Users,
  Plus,
  ArrowRight,
  Shield,
  TrendingUp,
  CheckCircle2,
  Target,
  BarChart3,
  Search,
} from 'lucide-react'
import { SkeletonStatCard, Skeleton } from '@/components/ui/skeleton'

const PHASE_INFO = [
  { number: 1, name: 'Preparation', color: 'from-blue-500 to-cyan-500', bg: 'bg-blue-500' },
  { number: 2, name: 'Identification', color: 'from-cyan-500 to-teal-500', bg: 'bg-cyan-500' },
  { number: 3, name: 'Containment', color: 'from-teal-500 to-green-500', bg: 'bg-teal-500' },
  { number: 4, name: 'Eradication', color: 'from-green-500 to-yellow-500', bg: 'bg-green-500' },
  { number: 5, name: 'Recovery', color: 'from-yellow-500 to-orange-500', bg: 'bg-yellow-500' },
  { number: 6, name: 'Lessons Learned', color: 'from-orange-500 to-red-500', bg: 'bg-orange-500' },
]

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-green-500',
}

const TLP_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  white: { bg: 'bg-gray-500/20', text: 'text-gray-300', label: 'WHITE' },
  green: { bg: 'bg-green-500/20', text: 'text-green-400', label: 'GREEN' },
  amber: { bg: 'bg-amber-500/20', text: 'text-amber-400', label: 'AMBER' },
  amber_strict: { bg: 'bg-orange-500/20', text: 'text-orange-400', label: 'AMBER+STRICT' },
  red: { bg: 'bg-red-500/20', text: 'text-red-400', label: 'RED' },
}

export default function DashboardPage() {
  const { user } = useAuthStore()
  // Server-side aggregates over every incident the user can access (W2-DFIR-B):
  // no client fan-out, no truncation at a page size.
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [statsLoading, setStatsLoading] = useState(true)
  const [statsError, setStatsError] = useState<string | null>(null)
  const [recentIncidents, setRecentIncidents] = useState<Incident[]>([])
  const [recentLoading, setRecentLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    incidentOverview
      .dashboardStats({ signal: controller.signal })
      .then((data) => setStats(data))
      .catch((err) => {
        if (!isAbortError(err)) setStatsError(describeError(err).description)
      })
      .finally(() => {
        if (!controller.signal.aborted) setStatsLoading(false)
      })
    api
      .get<PaginatedResponse<Incident>>('/incidents?per_page=6&sort=-created_at', { signal: controller.signal })
      .then((res) => setRecentIncidents(res.items || []))
      .catch(() => {
        // The list renders its empty state; the stats error (if any) is shown above.
      })
      .finally(() => {
        if (!controller.signal.aborted) setRecentLoading(false)
      })
    return () => controller.abort()
  }, [])

  const isLoading = statsLoading
  const analytics = useMemo(() => {
    if (!stats) return null
    const inc = stats.incidents
    const severityDist = {
      critical: inc.by_severity.critical ?? 0,
      high: inc.by_severity.high ?? 0,
      medium: inc.by_severity.medium ?? 0,
      low: inc.by_severity.low ?? 0,
    }
    const phaseDist: Record<number, number> = {}
    Object.entries(inc.by_phase_open).forEach(([phase, n]) => { phaseDist[Number(phase)] = n })
    return {
      total: inc.total,
      open: inc.active,
      closed: inc.closed,
      critical: inc.critical,
      thisWeek: inc.created_7d,
      thisMonth: inc.created_30d,
      severityDist,
      maxSeverity: Math.max(...Object.values(severityDist), 1),
      phaseDist,
      tlpDist: inc.by_tlp as Record<string, number>,
      // Average incidents per week (last 30 days)
      avgPerWeek: inc.created_30d > 0 ? Math.round((inc.created_30d / 4.3) * 10) / 10 : 0,
    }
  }, [stats])


  const currentDate = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">
            Welcome back, {user?.name?.split(' ')[0] || 'User'}
          </h1>
          <p className="text-sm text-muted-foreground">{currentDate}</p>
        </div>
        <Link href="/dashboard/incidents/new" data-tour="new-incident">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            New Incident
          </Button>
        </Link>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4" data-tour="dashboard-stats">
        {isLoading ? (
          <>
            {[1,2,3,4,5,6].map(i => <SkeletonStatCard key={i} />)}
          </>
        ) : (
          <>
            <StatCard
              title="Total"
              value={analytics?.total || 0}
              description="All time"
              icon={<Shield className="h-5 w-5" />}
            />
            <StatCard
              title="Active"
              value={analytics?.open || 0}
              description="Non-closed"
              icon={<Activity className="h-5 w-5" />}
              trend={analytics?.open && analytics.total ? { value: Math.round((analytics.open / analytics.total) * 100), label: 'active', positive: false } : undefined}
            />
            <StatCard
              title="Closed"
              value={analytics?.closed || 0}
              description="Resolved"
              icon={<CheckCircle2 className="h-5 w-5" />}
            />
            <StatCard
              title="Critical"
              value={analytics?.critical || 0}
              description="High priority"
              icon={<AlertTriangle className="h-5 w-5" />}
            />
            <StatCard
              title="This Week"
              value={analytics?.thisWeek || 0}
              description="New incidents"
              icon={<TrendingUp className="h-5 w-5" />}
            />
            <StatCard
              title="Avg/Week"
              value={analytics?.avgPerWeek || 0}
              description="Last 30 days"
              icon={<BarChart3 className="h-5 w-5" />}
            />
          </>
        )}
      </div>

      {statsError && (
        <p role="alert" className="text-sm text-red-400">
          Could not load dashboard statistics: {statsError}
        </p>
      )}

      {/* Analytics Row */}
      {!isLoading && analytics && analytics.total > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
          {/* Severity Distribution */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Severity Distribution</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {(['critical', 'high', 'medium', 'low'] as const).map(severity => {
                const count = analytics.severityDist[severity]
                const pct = Math.round((count / analytics.total) * 100)
                return (
                  <div key={severity} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="capitalize text-muted-foreground">{severity}</span>
                      <span className="font-medium text-foreground">{count} ({pct}%)</span>
                    </div>
                    <div className="w-full bg-black/5 dark:bg-white/10 rounded-full h-2 overflow-hidden">
                      <div className={`h-full rounded-full ${SEVERITY_COLORS[severity]}`} style={{ width: `${(count / analytics.maxSeverity) * 100}%` }} />
                    </div>
                  </div>
                )
              })}
            </CardContent>
          </Card>

          {/* Active Incidents by Phase - Pipeline */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Active Incident Pipeline</CardTitle>
              <CardDescription className="text-xs">Non-closed incidents by phase</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {PHASE_INFO.map(phase => {
                  const count = analytics.phaseDist[phase.number] || 0
                  return (
                    <div key={phase.number} className="flex items-center gap-3">
                      <div className={`w-7 h-7 rounded-full bg-gradient-to-r ${phase.color} flex items-center justify-center text-white text-xs font-bold shrink-0`}>
                        {phase.number}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex justify-between">
                          <span className="text-xs text-muted-foreground truncate">{phase.name}</span>
                          <span className="text-xs font-bold text-foreground ml-2">{count}</span>
                        </div>
                        <div className="w-full bg-black/5 dark:bg-white/10 rounded-full h-1.5 mt-1 overflow-hidden">
                          <div className={`h-full rounded-full bg-gradient-to-r ${phase.color}`} style={{ width: count > 0 ? `${Math.max((count / analytics.open) * 100, 8)}%` : '0%' }} />
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </CardContent>
          </Card>

          {/* TLP Distribution */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">TLP Distribution</CardTitle>
              <CardDescription className="text-xs">Traffic Light Protocol levels</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(analytics.tlpDist).map(([tlp, count]) => {
                  const style = TLP_STYLES[tlp] || TLP_STYLES.amber
                  return (
                    <div key={tlp} className={`p-3 rounded-lg ${style.bg} border border-black/10 dark:border-white/10 text-center`}>
                      <div className={`text-lg font-bold ${style.text}`}>{count}</div>
                      <div className={`text-[10px] font-mono ${style.text}`}>TLP:{style.label.replace('+', '+\u200b')}</div>
                    </div>
                  )
                })}
              </div>
              {Object.keys(analytics.tlpDist).length === 0 && (
                <p className="text-xs text-muted-foreground text-center py-4">No TLP data</p>
              )}
            </CardContent>
          </Card>

          {/* DFIR queue: open leads and host triage (null without the read permission) */}
          {stats && (stats.dfir.open_leads !== null || stats.dfir.hosts_by_triage !== null) && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Investigation Queue</CardTitle>
                <CardDescription className="text-xs">Across all accessible incidents</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {stats.dfir.open_leads !== null && (
                  <div className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1.5 text-muted-foreground">
                      <Search className="h-3.5 w-3.5" /> Open leads
                    </span>
                    <span className="font-bold text-foreground">{stats.dfir.open_leads}</span>
                  </div>
                )}
                {stats.dfir.hosts_by_triage &&
                  Object.entries(stats.dfir.hosts_by_triage)
                    .sort(([, a], [, b]) => b - a)
                    .map(([triage, count]) => (
                      <div key={triage} className="flex items-center justify-between text-xs">
                        <span className="capitalize text-muted-foreground">Hosts {triage.replace(/_/g, ' ')}</span>
                        <span className="font-medium text-foreground">{count}</span>
                      </div>
                    ))}
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Cross-incident MITRE TTP Analytics */}
      {!isLoading && stats?.mitre && stats.mitre.events_mapped > 0 && (
        <MitreTTPAnalytics
          aggregate={stats.mitre}
          title="MITRE ATT&CK Coverage"
          description="Tactics and techniques observed across all incidents"
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Incidents */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <div>
                <CardTitle>Recent Incidents</CardTitle>
                <CardDescription>Latest incidents requiring attention</CardDescription>
              </div>
              <Link href="/dashboard/incidents">
                <Button variant="ghost" size="sm">
                  View all
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </CardHeader>
            <CardContent>
              {recentLoading ? (
                <div className="divide-y divide-border">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <div key={i} className="flex items-center gap-4 py-3 -mx-4 px-4">
                      <div className="flex-1 space-y-2">
                        <div className="flex items-center gap-2">
                          <Skeleton className="h-4 w-12" />
                          <Skeleton className="h-5 w-16 rounded-full" />
                          <Skeleton className="h-5 w-14 rounded-full" />
                        </div>
                        <Skeleton className="h-4 w-3/4" />
                        <Skeleton className="h-3 w-1/3" />
                      </div>
                      <div className="space-y-1 text-right">
                        <Skeleton className="h-3 w-16" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : recentIncidents.length === 0 ? (
                <div className="text-center py-12">
                  <div className="mx-auto w-12 h-12 rounded-md bg-muted flex items-center justify-center mb-4">
                    <Shield className="h-6 w-6 text-muted-foreground" />
                  </div>
                  <h3 className="text-base font-medium mb-1">No incidents yet</h3>
                  <p className="text-muted-foreground text-sm mb-4">
                    Create your first incident to get started
                  </p>
                  <Link href="/dashboard/incidents/new">
                    <Button size="sm">
                      <Plus className="mr-2 h-4 w-4" />
                      Create Incident
                    </Button>
                  </Link>
                </div>
              ) : (
                <div className="divide-y divide-border">
                  {recentIncidents.map((incident) => (
                    <Link
                      key={incident.id}
                      href={`/dashboard/incidents/${incident.id}`}
                      className="flex items-center gap-4 py-3 hover:bg-muted/50 -mx-4 px-4 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-mono text-muted-foreground">
                            #{incident.incident_number}
                          </span>
                          <SeverityBadge severity={incident.severity as any} />
                          <StatusBadge status={incident.status as any} />
                        </div>
                        <h3 className="text-sm font-medium leading-snug truncate">
                          {incident.title}
                        </h3>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Phase {incident.phase}: {incident.phase_name}
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-xs text-muted-foreground">
                          {formatRelativeTime(incident.created_at)}
                        </p>
                        {incident.lead_responder && (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {incident.lead_responder.name}
                          </p>
                        )}
                      </div>
                      <ArrowRight className="h-4 w-4 text-muted-foreground" />
                    </Link>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Quick Actions */}
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider px-1">
            Quick Actions
          </h3>
          <div className="space-y-2">
            <QuickActionCard
              title="Generate Report"
              description="Create executive summary"
              icon={<FileText className="h-5 w-5" />}
              href="/dashboard/reports"
            />
            <QuickActionCard
              title="Manage Team"
              description="View assignments"
              icon={<Users className="h-5 w-5" />}
              href="/dashboard/admin/users"
            />
            <QuickActionCard
              title="View Activity"
              description="Review audit logs"
              icon={<Activity className="h-5 w-5" />}
              href="/dashboard/activity"
            />
            <QuickActionCard
              title="Knowledge Base"
              description="MITRE & D3FEND lookups"
              icon={<Target className="h-5 w-5" />}
              href="/dashboard/knowledge-base"
            />
          </div>
        </div>
      </div>
    </div>
  )
}

function QuickActionCard({
  title,
  description,
  icon,
  href,
}: {
  title: string
  description: string
  icon: React.ReactNode
  href: string
}) {
  return (
    <Link href={href}>
      <Card className="hover:bg-muted/50 transition-colors">
        <CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-md bg-muted text-muted-foreground">
              {icon}
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-medium text-sm">{title}</h3>
              <p className="text-xs text-muted-foreground">{description}</p>
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}
