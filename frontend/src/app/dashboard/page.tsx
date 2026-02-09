/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, StatCard } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { SeverityBadge, StatusBadge } from '@/components/ui/badge'
import { useIncidentStore, useAuthStore } from '@/lib/store'
import { formatRelativeTime } from '@/lib/utils'
import {
  AlertTriangle,
  Activity,
  FileText,
  Users,
  Plus,
  ArrowRight,
  Shield,
  TrendingUp,
} from 'lucide-react'
import { SkeletonStatCard, Skeleton } from '@/components/ui/skeleton'

export default function DashboardPage() {
  const { user } = useAuthStore()
  const { incidents, fetchIncidents, isLoading } = useIncidentStore()
  const [stats, setStats] = useState({
    total: 0,
    open: 0,
    critical: 0,
    thisWeek: 0,
  })

  useEffect(() => {
    fetchIncidents()
  }, [fetchIncidents])

  useEffect(() => {
    if (incidents.length > 0) {
      const now = new Date()
      const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)

      setStats({
        total: incidents.length,
        open: incidents.filter((i) => i.status === 'open').length,
        critical: incidents.filter((i) => i.severity === 'critical').length,
        thisWeek: incidents.filter((i) => new Date(i.created_at) > weekAgo).length,
      })
    }
  }, [incidents])

  const recentIncidents = incidents.slice(0, 5)

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
        <Link href="/dashboard/incidents/new">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            New Incident
          </Button>
        </Link>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {isLoading ? (
          <>
            <SkeletonStatCard />
            <SkeletonStatCard />
            <SkeletonStatCard />
            <SkeletonStatCard />
          </>
        ) : (
          <>
            <StatCard
              title="Total Incidents"
              value={stats.total}
              description="All time"
              icon={<Shield className="h-5 w-5" />}
            />
            <StatCard
              title="Open Incidents"
              value={stats.open}
              description="Requires attention"
              icon={<Activity className="h-5 w-5" />}
              trend={stats.open > 0 ? { value: stats.open, label: 'active', positive: false } : undefined}
            />
            <StatCard
              title="Critical"
              value={stats.critical}
              description="High priority"
              icon={<AlertTriangle className="h-5 w-5" />}
            />
            <StatCard
              title="This Week"
              value={stats.thisWeek}
              description="New incidents"
              icon={<TrendingUp className="h-5 w-5" />}
            />
          </>
        )}
      </div>

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
              {isLoading ? (
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
                  <h3 className="font-medium mb-1">No incidents yet</h3>
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
                        <h3 className="font-medium truncate">
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
