"use client"

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge, TLPBadge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Clock,
  Server,
  Globe,
  Fingerprint,
  CheckSquare,
  Key,
  Bug,
  FileText,
  ChevronRight,
} from 'lucide-react'
import { formatDateTime, formatRelativeTime } from '@/lib/utils'
import { StatCard } from './StatCard'
import { LeadResponderSelector } from './LeadResponderSelector'
import { AssignmentsPanel } from '@/components/incidents/AssignmentsPanel'
import { MitreTTPAnalytics } from '@/components/incidents/MitreTTPAnalytics'
import type { TimelineEvent, CompromisedHost, Task, Incident } from '@/types'

// ─── Overview Tab ────────────────────────────────────────────────────────

interface OverviewTabProps {
  incident: Incident
  incidentId: string
  tasks: Task[]
  hosts: CompromisedHost[]
  timeline: TimelineEvent[]
  assignmentsKey: number
  onViewEvents: () => void
  onIncidentUpdated: () => void
  onAssignmentsRefresh: () => void
}

export function OverviewTab({
  incident,
  incidentId,
  tasks,
  hosts,
  timeline,
  assignmentsKey,
  onViewEvents,
  onIncidentUpdated,
  onAssignmentsRefresh,
}: OverviewTabProps) {
  const completedTasks = tasks.filter((t) => t.status === 'completed').length
  const pendingTasks = tasks.filter((t) => t.status === 'pending').length
  const inProgressTasks = tasks.filter((t) => t.status === 'in_progress').length
  const taskProgress = tasks.length > 0 ? Math.round((completedTasks / tasks.length) * 100) : 0

  const containmentGroups = hosts.reduce((acc, h) => {
    const status = h.containment_status || 'active'
    acc[status] = (acc[status] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  const containmentColors: Record<string, string> = {
    active: 'text-red-700 dark:text-red-400 bg-red-500/10 border-red-500/20',
    monitoring: 'text-yellow-700 dark:text-yellow-400 bg-yellow-500/10 border-yellow-500/20',
    isolated: 'text-amber-700 dark:text-amber-400 bg-amber-500/10 border-amber-500/20',
    reimaged: 'text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    decommissioned: 'text-muted-foreground bg-muted border-border',
  }

  // Calculate incident duration
  const createdDate = incident.created_at ? new Date(incident.created_at) : null
  const now = new Date()
  let durationStr = 'N/A'
  if (createdDate) {
    const diffMs = now.getTime() - createdDate.getTime()
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    const diffHours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
    durationStr = diffDays > 0 ? `${diffDays}d ${diffHours}h` : `${diffHours}h`
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-6">
        {/* Primary Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard title="Events" value={incident.counts?.timeline_events || 0} icon={<Clock className="h-4 w-4" />} />
          <StatCard
            title="Hosts"
            value={incident.counts?.compromised_hosts || 0}
            icon={<Server className="h-4 w-4" />}
            description={hosts.filter(h => h.containment_status === 'isolated').length > 0 ? `${hosts.filter(h => h.containment_status === 'isolated').length} isolated` : undefined}
          />
          <StatCard title="Network IOCs" value={incident.counts?.network_indicators || 0} icon={<Globe className="h-4 w-4" />} />
          <StatCard title="Host IOCs" value={incident.counts?.host_indicators || 0} icon={<Fingerprint className="h-4 w-4" />} />
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard title="Tasks" value={tasks.length} description={`${taskProgress}% complete`} icon={<CheckSquare className="h-4 w-4" />} />
          <StatCard title="Accounts" value={incident.counts?.compromised_accounts || 0} icon={<Key className="h-4 w-4" />} />
          <StatCard title="Malware" value={incident.counts?.malware_tools || 0} icon={<Bug className="h-4 w-4" />} />
          <StatCard title="Artifacts" value={incident.counts?.artifacts || 0} icon={<FileText className="h-4 w-4" />} />
        </div>

        {/* Task Progress */}
        {tasks.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Task Progress</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="w-full bg-muted rounded-full h-3 overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-500"
                  style={{ width: `${taskProgress}%` }}
                />
              </div>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div className="p-3 rounded-lg bg-muted/50 border border-border">
                  <div className="text-xl font-bold text-muted-foreground">{pendingTasks}</div>
                  <div className="text-xs text-muted-foreground">Pending</div>
                </div>
                <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/20">
                  <div className="text-xl font-bold text-blue-600 dark:text-blue-400">{inProgressTasks}</div>
                  <div className="text-xs text-muted-foreground">In Progress</div>
                </div>
                <div className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                  <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">{completedTasks}</div>
                  <div className="text-xs text-muted-foreground">Completed</div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Host Containment Status */}
        {hosts.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Host Containment</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                {Object.entries(containmentGroups).map(([status, count]) => (
                  <div key={status} className={`p-3 rounded-lg border text-center ${containmentColors[status] || 'bg-muted/50 border-border'}`}>
                    <div className="text-xl font-bold">{count}</div>
                    <div className="text-xs capitalize">{status.replace('_', ' ')}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* MITRE ATT&CK Coverage */}
        {timeline.length > 0 && <MitreTTPAnalytics events={timeline} />}

        {/* Recent Activity */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-lg">Recent Activity</CardTitle>
            <Button variant="ghost" size="sm" onClick={onViewEvents}>
              View all <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent>
            {timeline.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">No recent activity</div>
            ) : (
              <div className="space-y-4">
                {timeline.slice(0, 5).map(event => (
                  <div key={event.id} className="flex gap-4 p-3 rounded-lg hover:bg-muted/50 transition-colors">
                    <div className="text-xs text-muted-foreground w-24 shrink-0 pt-0.5">{formatRelativeTime(event.timestamp)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm text-foreground truncate">{event.activity}</p>
                        {event.is_ioc && (
                          <Badge variant="critical" className="text-[10px] px-1.5 py-0">IOC</Badge>
                        )}
                      </div>
                      {event.hostname && (
                        <span className="text-xs text-muted-foreground flex items-center gap-1 mt-1">
                          <Server className="h-3 w-3" />{event.hostname}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Sidebar */}
      <div className="space-y-6">
        {/* Details Card */}
        <Card>
          <CardHeader><CardTitle className="text-lg">Details</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Classification</p>
              <p className="font-medium text-foreground">{incident.classification || 'Not classified'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">TLP Level</p>
              <TLPBadge tlp={incident.tlp || 'amber'} />
            </div>
            {incident.owning_team && (
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Owning Team</p>
                <p className="font-medium text-foreground">{incident.owning_team.name}</p>
              </div>
            )}
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Lead Responder</p>
              <LeadResponderSelector
                incidentId={incidentId}
                currentLead={incident.lead_responder as any}
                onUpdated={() => {
                  onIncidentUpdated()
                  onAssignmentsRefresh()
                }}
              />
            </div>
            {incident.teams && incident.teams.length > 0 && (
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Team Access</p>
                <div className="flex flex-wrap gap-1.5">
                  {incident.teams.map(team => (
                    <Badge key={team.id} variant="outline" className="text-xs">
                      {team.name}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Timing Card */}
        <Card>
          <CardHeader><CardTitle className="text-lg">Timing</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between">
              <span className="text-xs text-muted-foreground">Created</span>
              <span className="text-xs font-medium text-foreground">{incident.created_at ? formatDateTime(incident.created_at) : 'N/A'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-xs text-muted-foreground">Last Updated</span>
              <span className="text-xs font-medium text-foreground">{incident.updated_at ? formatRelativeTime(incident.updated_at) : 'N/A'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-xs text-muted-foreground">Duration</span>
              <span className="text-xs font-bold text-primary">{durationStr}</span>
            </div>
            {timeline.length > 0 && (
              <div className="flex justify-between">
                <span className="text-xs text-muted-foreground">First Event</span>
                <span className="text-xs font-medium text-foreground">{formatDateTime(timeline[timeline.length - 1]?.timestamp)}</span>
              </div>
            )}
          </CardContent>
        </Card>

        <AssignmentsPanel incidentId={incidentId} refreshKey={assignmentsKey} />
      </div>
    </div>
  )
}
