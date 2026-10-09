"use client"

/**
 * Incident Overview (layout owned by W2-DFIR-B, C21).
 *
 * Two slots are filled by later work packages without touching this layout:
 * - `questionsSlot`: top of the left column (investigative questions, QST-UI)
 * - `metricsSlot`:   directly below the milestone strip (metrics card, RT-POST)
 * Counts come from the server (`incident.counts`, `incident.summary`), never
 * from truncated lists.
 */
import type { ReactNode } from 'react'
import { usePathname, useRouter } from 'next/navigation'
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
  Search,
  Microscope,
} from 'lucide-react'
import { formatRelativeTime } from '@/lib/utils'
import { parseTs } from '@/lib/time'
import { Timestamp } from '@/components/ui/timestamp'
import { StatCard } from './StatCard'
import { IRMilestoneStrip } from './IRMilestoneStrip'
import { IncidentNarrativeCard } from './IncidentNarrativeCard'
import { LeadResponderSelector } from './LeadResponderSelector'
import { AssignmentsPanel } from '@/components/incidents/AssignmentsPanel'
import { MitreTTPAnalytics } from '@/components/incidents/MitreTTPAnalytics'
import { useAllPages } from '@/hooks/use-paginated-query'
import type { TimelineEvent, Task, Incident, IncidentOverviewFields, Versioned } from '@/types'

// Query param of the Tasks tab's "All tasks | Leads" view: single source in
// TasksTab (W2-DFIR-A), so the Overview deep link always matches it.
import { TASKS_VIEW_PARAM } from './TasksTab'
export { TASKS_VIEW_PARAM }

// ─── Overview Tab ────────────────────────────────────────────────────────

export interface OverviewTabProps {
  incident: Incident & Versioned & IncidentOverviewFields
  incidentId: string
  onViewEvents: () => void
  onIncidentUpdated: () => void
  /** Open the Tasks tab on its Leads view (default: `?tab=tasks&tasks.view=leads`). */
  onOpenLeads?: () => void
  /** Slot: investigative questions panel (QST-UI), top of the left column. */
  questionsSlot?: ReactNode
  /** Slot: incident metrics card (RT-POST), below the milestone strip. */
  metricsSlot?: ReactNode
}

export function OverviewTab({
  incident,
  incidentId,
  onViewEvents,
  onIncidentUpdated,
  onOpenLeads,
  questionsSlot,
  metricsSlot,
}: OverviewTabProps) {
  const router = useRouter()
  const pathname = usePathname()
  const summary = incident.summary ?? null
  const openLeads = summary?.leads?.open ?? null
  const hostsUnderAnalysis = summary?.hosts_by_triage ? summary.hosts_by_triage.under_analysis ?? 0 : null

  const openLeadsView = () => {
    if (onOpenLeads) return onOpenLeads()
    const params = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '')
    params.set('tab', 'tasks')
    params.set(TASKS_VIEW_PARAM, 'leads')
    params.delete('row')
    router.replace(`${pathname}?${params.toString()}`, { scroll: false })
  }

  // Whole-incident datasets, shared (one cached request) with the Events
  // views, MITRE and the graph; any `invalidate()` of them refreshes this.
  const { items: tasks } = useAllPages<Task>(`/incidents/${incidentId}/tasks`, { live: 'task' })
  const { items: timeline } = useAllPages<TimelineEvent>(`/incidents/${incidentId}/timeline`, { live: 'timeline_event' })

  const completedTasks = tasks.filter((t) => t.status === 'completed').length
  const pendingTasks = tasks.filter((t) => t.status === 'pending').length
  const inProgressTasks = tasks.filter((t) => t.status === 'in_progress').length
  const taskProgress = tasks.length > 0 ? Math.round((completedTasks / tasks.length) * 100) : 0

  // The API returns the timeline ascending; never rely on that order here.
  const tsMs = (e: TimelineEvent) => parseTs(e.timestamp)?.getTime() ?? 0
  const eventsNewestFirst = [...timeline].sort((a, b) => tsMs(b) - tsMs(a))

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
    <div className="space-y-6">
      <IRMilestoneStrip incident={incident} firstActivity={summary?.first_event_at} onSaved={onIncidentUpdated} />
      {metricsSlot && <div data-slot="overview-metrics">{metricsSlot}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {questionsSlot && <div data-slot="overview-questions">{questionsSlot}</div>}

          {/* Primary Stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard title="Events" value={incident.counts?.timeline_events || 0} icon={<Clock className="h-4 w-4" />} />
            <StatCard
              title="Hosts"
              value={incident.counts?.compromised_hosts || 0}
              icon={<Server className="h-4 w-4" />}
            />
            <StatCard title="Network IOCs" value={incident.counts?.network_indicators || 0} icon={<Globe className="h-4 w-4" />} />
            <StatCard title="Host IOCs" value={incident.counts?.host_indicators || 0} icon={<Fingerprint className="h-4 w-4" />} />
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard title="Tasks" value={incident.counts?.tasks ?? tasks.length} description={`${taskProgress}% complete`} icon={<CheckSquare className="h-4 w-4" />} />
            <StatCard title="Accounts" value={incident.counts?.compromised_accounts || 0} icon={<Key className="h-4 w-4" />} />
            <StatCard title="Malware" value={incident.counts?.malware_tools || 0} icon={<Bug className="h-4 w-4" />} />
            <StatCard title="Artifacts" value={incident.counts?.artifacts || 0} icon={<FileText className="h-4 w-4" />} />
          </div>
          {(openLeads !== null || hostsUnderAnalysis !== null) && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {openLeads !== null && (
                <button
                  type="button"
                  onClick={openLeadsView}
                  className="rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label={`Open leads: ${openLeads}. Show the lead queue`}
                >
                  <StatCard
                    title="Open leads"
                    value={openLeads}
                    description={`${summary?.leads?.total ?? 0} total`}
                    icon={<Search className="h-4 w-4" />}
                  />
                </button>
              )}
              {hostsUnderAnalysis !== null && (
                <StatCard
                  title="Hosts under analysis"
                  value={hostsUnderAnalysis}
                  icon={<Microscope className="h-4 w-4" />}
                />
              )}
            </div>
          )}

          <IncidentNarrativeCard incident={incident} onSaved={onIncidentUpdated} />

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

          {/* MITRE ATT&CK Coverage */}
          {timeline.length > 0 && <MitreTTPAnalytics events={timeline} />}

          {/* Latest timeline events (newest first) */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-lg">Latest timeline events</CardTitle>
              <Button variant="ghost" size="sm" onClick={onViewEvents}>
                View all <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent>
              {timeline.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">No timeline events yet</div>
              ) : (
                <div className="space-y-4">
                  {eventsNewestFirst.slice(0, 5).map(event => (
                    <div key={event.id} className="flex gap-4 p-3 rounded-lg hover:bg-muted/50 transition-colors">
                      <div className="text-xs text-muted-foreground w-40 shrink-0 pt-0.5">
                        <Timestamp value={event.timestamp} />
                      </div>
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
                  incidentVersion={incident.version}
                  currentLead={incident.lead_responder}
                  onUpdated={onIncidentUpdated}
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
                <span className="text-xs font-medium text-foreground"><Timestamp value={incident.created_at} seconds={false} fallback="N/A" /></span>
              </div>
              <div className="flex justify-between">
                <span className="text-xs text-muted-foreground">Last Updated</span>
                <span className="text-xs font-medium text-foreground">{incident.updated_at ? formatRelativeTime(incident.updated_at) : 'N/A'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-xs text-muted-foreground">Duration</span>
                <span className="text-xs font-bold text-primary">{durationStr}</span>
              </div>
              {summary?.first_event_at && (
                <div className="flex justify-between">
                  <span className="text-xs text-muted-foreground">First known activity</span>
                  <span className="text-xs font-medium text-foreground"><Timestamp value={summary.first_event_at} /></span>
                </div>
              )}
              {summary?.last_event_at && (
                <div className="flex justify-between">
                  <span className="text-xs text-muted-foreground">Latest event</span>
                  <span className="text-xs font-medium text-foreground"><Timestamp value={summary.last_event_at} /></span>
                </div>
              )}
            </CardContent>
          </Card>

          <AssignmentsPanel incidentId={incidentId} />
        </div>
      </div>
    </div>
  )
}
