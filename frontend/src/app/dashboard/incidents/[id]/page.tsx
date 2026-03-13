"use client"

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { SeverityBadge, StatusBadge, PhaseBadge, TLPBadge } from '@/components/ui/badge'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { useIncidentStore } from '@/lib/store'
import api from '@/lib/api'
import type { TimelineEvent, CompromisedHost, Task } from '@/types'
import {
  ArrowLeft,
  Activity,
  Server,
  Network,
  CheckSquare,
  Key,
  Globe,
  Fingerprint,
  Bug,
  LayoutList,
  Upload,
  Zap,
  Edit2,
  FileText,
  Download,
  MessageSquare,
  Clock,
  Star,
} from 'lucide-react'

// ─── Tab Components ──────────────────────────────────────────────────────
import { CompromisedAccountsTab } from '@/components/incidents/CompromisedAccountsTab'
import { MalwareToolsTab } from '@/components/incidents/MalwareToolsTab'
import { NetworkIOCsTab } from '@/components/incidents/NetworkIOCsTab'
import { HostBasedIOCsTab } from '@/components/incidents/HostBasedIOCsTab'
import { ArtifactsTab } from '@/components/incidents/ArtifactsTab'
import { EventsTable } from '@/components/incidents/EventsTable'
import { IOCVisualTimeline, PinnedEventsTable } from '@/components/incidents/timeline/IOCVisualTimeline'
import { HostsTab } from '@/components/incidents/HostsTab'
import { CaseNotesTab } from '@/components/incidents/CaseNotesTab'
import { IRPhaseTracker } from '@/components/incidents/IRPhaseTracker'
import { AttackGraphViewer } from '@/components/attack-graph/AttackGraphViewer'
import { ImportWizardModal } from '@/components/incidents/import-wizard/ImportWizardModal'

// ─── Extracted Detail Components ─────────────────────────────────────────
import { IncidentDetailSkeleton } from '@/components/incidents/detail/IncidentDetailSkeleton'
import { DescriptionBlock } from '@/components/incidents/detail/DescriptionBlock'
import { OverviewTab } from '@/components/incidents/detail/OverviewTab'
import { TasksTab } from '@/components/incidents/detail/TasksTab'
import { EditIncidentModal, UpdateStatusModal, ReportModal } from '@/components/incidents/detail/IncidentModals'

// ─── Main Page Component ─────────────────────────────────────────────────

export default function IncidentDetailPage() {
  const params = useParams()
  const incidentId = params.id as string
  const { currentIncident, fetchIncident } = useIncidentStore()
  const { hasPermission } = useAuthStore()
  const canUpdateIncident = hasPermission('incidents:update')
  const canCreateTask = hasPermission('tasks:create')
  const canUpdateTask = hasPermission('tasks:update')
  const canDeleteTask = hasPermission('tasks:delete')
  const canGenerateReport = hasPermission('reports:generate')
  const canViewArtifacts = hasPermission('artifacts:read')
  const [activeTab, setActiveTab] = useState('overview')
  const [eventsView, setEventsView] = useState<'table' | 'timeline' | 'table-timeline'>('table')
  const [isLoadingData, setIsLoadingData] = useState(true)
  const [tasks, setTasks] = useState<Task[]>([])
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [hosts, setHosts] = useState<CompromisedHost[]>([])

  // Modal visibility
  const [showEditModal, setShowEditModal] = useState(false)
  const [showStatusModal, setShowStatusModal] = useState(false)
  const [showReportModal, setShowReportModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [assignmentsKey, setAssignmentsKey] = useState(0)

  useEffect(() => {
    if (incidentId) loadIncidentData()
  }, [incidentId])

  const loadIncidentData = async () => {
    setIsLoadingData(true)
    try {
      await fetchIncident(incidentId)
      const [tasksRes, timelineRes, hostsRes] = await Promise.all([
        api.get<{ items: Task[] }>(`/incidents/${incidentId}/tasks`),
        api.get<{ items: TimelineEvent[] }>(`/incidents/${incidentId}/timeline`),
        api.get<{ items: CompromisedHost[] }>(`/incidents/${incidentId}/hosts`),
      ])
      setTasks(tasksRes.items || [])
      setTimeline(timelineRes.items || [])
      setHosts(hostsRes.items || [])
    } catch (error) {
      console.error('Failed to load incident data:', error)
    } finally {
      setIsLoadingData(false)
    }
  }

  // ─── Loading / Not Found ───────────────────────────────────────────────

  if (isLoadingData && !currentIncident) {
    return <div className="p-8"><IncidentDetailSkeleton /></div>
  }

  if (!currentIncident) {
    return <div className="p-8 text-muted-foreground">Incident not found</div>
  }

  const incident = currentIncident

  // ─── Render ────────────────────────────────────────────────────────────

  return (
    <>
      <div className="p-6 lg:p-8 space-y-6">
        {/* Header */}
        <div>
          <Link
            href="/dashboard/incidents"
            className="inline-flex items-center text-muted-foreground hover:text-foreground transition-colors mb-4"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Incidents
          </Link>

          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
            <div className="space-y-3 min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-mono text-sm text-muted-foreground">
                  #{incident.incident_number}
                </span>
                <SeverityBadge severity={incident.severity as any} />
                <StatusBadge status={incident.status as any} />
                <PhaseBadge phase={incident.phase} />
                <TLPBadge tlp={incident.tlp || 'amber'} />
              </div>
              <h1 className="text-2xl lg:text-3xl font-bold text-foreground">{incident.title}</h1>
              {incident.description && (
                <DescriptionBlock text={incident.description} />
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {canGenerateReport && (
              <Button variant="outline" onClick={() => setShowReportModal(true)}>
                <Download className="mr-2 h-4 w-4" /> Generate Report
              </Button>
              )}
              {canUpdateIncident && (
              <>
              <Button variant="outline" onClick={() => setShowImportModal(true)}>
                <Upload className="mr-2 h-4 w-4" /> Import
              </Button>
              <Button variant="outline" onClick={() => setShowEditModal(true)}>
                <Edit2 className="mr-2 h-4 w-4" /> Edit
              </Button>
              <Button onClick={() => setShowStatusModal(true)}>
                <Zap className="mr-2 h-4 w-4" /> Update Status
              </Button>
              </>
              )}
            </div>
          </div>
        </div>

        {/* Phase Progress */}
        <IRPhaseTracker currentPhase={incident.phase} context="incident" />

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList variant="underline" className="w-full justify-start flex-wrap h-auto gap-y-2">
            <TabsTrigger variant="underline" value="overview" className="gap-2">
              <Activity className="h-4 w-4" /> Overview
            </TabsTrigger>
            <TabsTrigger variant="underline" value="events" className="gap-2">
              <LayoutList className="h-4 w-4" /> Events
            </TabsTrigger>
            <TabsTrigger variant="underline" value="hosts" className="gap-2">
              <Server className="h-4 w-4" /> Hosts
            </TabsTrigger>
            <TabsTrigger variant="underline" value="tasks" className="gap-2">
              <CheckSquare className="h-4 w-4" /> Tasks
            </TabsTrigger>
            <TabsTrigger variant="underline" value="graph" className="gap-2">
              <Network className="h-4 w-4" /> Attack Graph
            </TabsTrigger>
            <TabsTrigger variant="underline" value="accounts" className="gap-2">
              <Key className="h-4 w-4" /> Accounts
            </TabsTrigger>
            <TabsTrigger variant="underline" value="network" className="gap-2">
              <Globe className="h-4 w-4" /> Network IOCs
            </TabsTrigger>
            <TabsTrigger variant="underline" value="host-iocs" className="gap-2">
              <Fingerprint className="h-4 w-4" /> Host IOCs
            </TabsTrigger>
            <TabsTrigger variant="underline" value="malware" className="gap-2">
              <Bug className="h-4 w-4" /> Malware
            </TabsTrigger>
            {canViewArtifacts && (
              <TabsTrigger variant="underline" value="artifacts" className="gap-2">
                <FileText className="h-4 w-4" /> Artifacts
              </TabsTrigger>
            )}
            <TabsTrigger variant="underline" value="notes" className="gap-2">
              <MessageSquare className="h-4 w-4" /> Notes
            </TabsTrigger>
          </TabsList>

          {/* Overview */}
          <TabsContent value="overview">
            <OverviewTab
              incident={incident as any}
              incidentId={incidentId}
              tasks={tasks}
              hosts={hosts}
              timeline={timeline}
              assignmentsKey={assignmentsKey}
              onViewEvents={() => setActiveTab('events')}
              onIncidentUpdated={() => {
                fetchIncident(incidentId)
                setAssignmentsKey((k) => k + 1)
              }}
              onAssignmentsRefresh={() => setAssignmentsKey((k) => k + 1)}
            />
          </TabsContent>

          {/* Events */}
          <TabsContent value="events">
            <div className="mb-4 flex items-center gap-2">
              <Button
                variant={eventsView === 'table' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setEventsView('table')}
                className="gap-1.5"
              >
                <LayoutList className="h-3.5 w-3.5" /> Table
              </Button>
              <Button
                variant={eventsView === 'timeline' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setEventsView('timeline')}
                className="gap-1.5"
              >
                <Clock className="h-3.5 w-3.5" /> Visual Timeline
              </Button>
              <Button
                variant={eventsView === 'table-timeline' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setEventsView('table-timeline')}
                className="gap-1.5"
              >
                <Star className="h-3.5 w-3.5" /> Table Timeline
              </Button>
            </div>
            {eventsView === 'table' ? (
              <EventsTable incidentId={incidentId} />
            ) : eventsView === 'timeline' ? (
              <IOCVisualTimeline incidentId={incidentId} />
            ) : (
              <PinnedTimelineTab incidentId={incidentId} />
            )}
          </TabsContent>

          {/* Hosts */}
          <TabsContent value="hosts">
            <HostsTab incidentId={incidentId} onHostsChange={setHosts} />
          </TabsContent>

          {/* Tasks */}
          <TabsContent value="tasks">
            <TasksTab
              incidentId={incidentId}
              tasks={tasks}
              hosts={hosts}
              onTasksChange={setTasks}
            />
          </TabsContent>

          {/* Attack Graph */}
          <TabsContent value="graph">
            <Card>
              <CardHeader>
                <CardTitle>Attack Graph</CardTitle>
                <CardDescription>Auto-generated visualization of the attack path</CardDescription>
              </CardHeader>
              <CardContent>
                <AttackGraphViewer incidentId={incidentId} hosts={hosts} timeline={timeline} />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="accounts">
            <CompromisedAccountsTab incidentId={incidentId} />
          </TabsContent>

          <TabsContent value="network">
            <NetworkIOCsTab incidentId={incidentId} />
          </TabsContent>

          <TabsContent value="host-iocs">
            <HostBasedIOCsTab incidentId={incidentId} />
          </TabsContent>

          <TabsContent value="malware">
            <MalwareToolsTab incidentId={incidentId} />
          </TabsContent>

          <TabsContent value="artifacts">
            {canViewArtifacts && <ArtifactsTab incidentId={incidentId} />}
          </TabsContent>

          <TabsContent value="notes">
            <CaseNotesTab incidentId={incidentId} />
          </TabsContent>
        </Tabs>
      </div>

      {/* Modals */}
      <EditIncidentModal
        open={showEditModal}
        onOpenChange={setShowEditModal}
        incident={incident as any}
        incidentId={incidentId}
        onUpdated={() => fetchIncident(incidentId)}
      />

      <UpdateStatusModal
        open={showStatusModal}
        onOpenChange={setShowStatusModal}
        currentStatus={incident.status}
        incidentId={incidentId}
        onUpdated={() => {
          fetchIncident(incidentId)
          setAssignmentsKey((k) => k + 1)
        }}
      />

      <ReportModal
        open={showReportModal}
        onOpenChange={setShowReportModal}
        incidentId={incidentId}
        incidentNumber={incident.incident_number}
      />

      <ImportWizardModal
        isOpen={showImportModal}
        onOpenChange={setShowImportModal}
        incidentId={incidentId}
        onComplete={loadIncidentData}
      />
    </>
  )
}

// ─── Pinned Timeline Tab ─────────────────────────────────────────────────

function PinnedTimelineTab({ incidentId }: { incidentId: string }) {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setIsLoading(true)
      try {
        const res = await api.get<{ items: TimelineEvent[] }>(`/incidents/${incidentId}/timeline`)
        if (!cancelled) {
          const pinned = (res.items || [])
            .filter((e) => e.is_key_event)
            .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
          setEvents(pinned)
        }
      } catch (err) {
        console.error('Failed to load pinned timeline events:', err)
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [incidentId])

  if (isLoading) {
    return (
      <div className="py-16 text-center text-sm text-muted-foreground animate-pulse">
        <Clock className="h-6 w-6 mx-auto mb-2 opacity-30" />
        Loading pinned events...
      </div>
    )
  }

  if (events.length === 0) {
    return (
      <div className="py-16 text-center border border-dashed border-border rounded-lg">
        <Star className="w-8 h-8 mx-auto text-muted-foreground/30 mb-3" />
        <p className="text-sm font-medium text-foreground">No Pinned Events</p>
        <p className="text-xs text-muted-foreground mt-1">
          Pin events from the Table tab using the &#9733; icon to build your table timeline.
        </p>
      </div>
    )
  }

  return <PinnedEventsTable events={events} />
}
