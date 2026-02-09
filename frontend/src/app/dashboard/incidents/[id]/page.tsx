"use client"

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogBody,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  GlassTable,
  TableEmpty,
} from '@/components/ui/table'
import { SkeletonTableRow, Skeleton } from '@/components/ui/skeleton'
import { useIncidentStore } from '@/lib/store'
import { formatDateTime, formatRelativeTime } from '@/lib/utils'
import api from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import type { TimelineEvent, CompromisedHost, Task, CompromisedAccount, MalwareTool, HostBasedIndicator, User as UserType } from '@/types'
import {
  ArrowLeft,
  Plus,
  MoreHorizontal,
  CheckCircle2,
  Circle,
  Clock,
  Calendar,
  User,
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
  ChevronRight,
  Link2,
  X,
  AlertTriangle,
  FileText,
  Download,
  Loader2,
} from 'lucide-react'

// Import new Tab Components
import { CompromisedAccountsTab } from '@/components/incidents/CompromisedAccountsTab'
import { MalwareToolsTab } from '@/components/incidents/MalwareToolsTab'
import { NetworkIOCsTab } from '@/components/incidents/NetworkIOCsTab'
import { HostBasedIOCsTab } from '@/components/incidents/HostBasedIOCsTab'
import { ArtifactsTab } from '@/components/incidents/ArtifactsTab'
import { EventsTable } from '@/components/incidents/EventsTable'
import { IOCVisualTimeline } from '@/components/incidents/IOCVisualTimeline'

import { AttackGraphViewer } from '@/components/attack-graph/AttackGraphViewer'
import { ImportWizardModal } from '@/components/incidents/import-wizard/ImportWizardModal'

// --- Types & Constants ---
const PHASE_INFO = [
  { number: 1, name: 'Preparation', short: 'Prep', color: 'from-blue-500 to-cyan-500' },
  { number: 2, name: 'Identification', short: 'Ident', color: 'from-cyan-500 to-teal-500' },
  { number: 3, name: 'Containment', short: 'Cont', color: 'from-teal-500 to-green-500' },
  { number: 4, name: 'Eradication', short: 'Erad', color: 'from-green-500 to-yellow-500' },
  { number: 5, name: 'Recovery', short: 'Recov', color: 'from-yellow-500 to-orange-500' },
  { number: 6, name: 'Lessons Learned', short: 'Review', color: 'from-orange-500 to-red-500' },
]

const STATUS_OPTIONS = [
  { value: 'open', label: 'Open', color: 'bg-green-500', phase: 1, phaseName: 'Preparation' },
  { value: 'investigating', label: 'Investigating', color: 'bg-blue-500', phase: 2, phaseName: 'Identification' },
  { value: 'contained', label: 'Contained', color: 'bg-orange-500', phase: 3, phaseName: 'Containment' },
  { value: 'eradicated', label: 'Eradicated', color: 'bg-yellow-500', phase: 4, phaseName: 'Eradication' },
  { value: 'recovered', label: 'Recovered', color: 'bg-purple-500', phase: 5, phaseName: 'Recovery' },
  { value: 'closed', label: 'Closed', color: 'bg-slate-500', phase: 6, phaseName: 'Lessons Learned' },
]

// --- Helper Components ---
function StatCard({ title, value, icon, description }: any) {
  return (
    <div className="p-4 rounded-xl bg-white/5 border border-white/10 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-muted-foreground">{title}</span>
        <div className="text-cyan-400">{icon}</div>
      </div>
      <div className="text-2xl font-bold text-foreground">{value}</div>
      {description && <div className="text-xs text-muted-foreground mt-1">{description}</div>}
    </div>
  )
}

function SkeletonStatCard() {
  return (
    <div className="rounded-xl border border-border bg-white/5 p-4 space-y-3">
      <Skeleton className="h-3 w-1/3" />
      <Skeleton className="h-7 w-1/2" />
    </div>
  )
}

function SkeletonPage() {
  return (
    <div className="space-y-6">
      {/* Title + badges */}
      <div className="space-y-3">
        <Skeleton className="h-5 w-20" />
        <Skeleton className="h-8 w-2/3" />
        <div className="flex gap-2">
          <Skeleton className="h-6 w-24 rounded-full" />
          <Skeleton className="h-6 w-20 rounded-full" />
          <Skeleton className="h-6 w-28 rounded-full" />
        </div>
      </div>
      {/* Summary card */}
      <div className="rounded-xl border border-border bg-white/5 p-6 space-y-3">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-2/3" />
      </div>
      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <SkeletonStatCard key={i} />
        ))}
      </div>
      {/* Tab bar + table */}
      <div className="space-y-4">
        <div className="flex gap-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-9 w-24 rounded-md" />
          ))}
        </div>
        <div className="rounded-xl border border-border bg-white/5">
          <div className="p-4 space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex gap-4">
                <Skeleton className="h-4 w-1/6" />
                <Skeleton className="h-4 w-2/6" />
                <Skeleton className="h-4 w-1/6" />
                <Skeleton className="h-4 w-1/6" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function SeverityBadge({ severity }: { severity: 'low' | 'medium' | 'high' | 'critical' }) {
  const styles = {
    critical: 'bg-red-500/20 text-red-400 border-red-500/30',
    high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    low: 'bg-green-500/20 text-green-400 border-green-500/30',
  }
  return (
    <Badge className={`${styles[severity]} border capitalize`}>
      {severity} Severity
    </Badge>
  )
}

function StatusBadge({ status }: { status: 'open' | 'closed' | 'investigating' | 'contained' | 'eradicated' | 'recovered' }) {
  const styles = {
    open: 'bg-green-500/20 text-green-400 border-green-500/30',
    closed: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
    investigating: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    contained: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    eradicated: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    recovered: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  }
  return (
    <Badge className={`${styles[status]} border capitalize`}>
      {status}
    </Badge>
  )
}

function PhaseBadge({ phase }: { phase: number }) {
  const info = PHASE_INFO.find((p) => p.number === phase)
  if (!info) return null
  return (
    <Badge variant="outline" className="bg-white/5">
      Phase {phase}: {info.name}
    </Badge>
  )
}

// --- Main Page Component ---
export default function IncidentDetailPage() {
  const params = useParams()
  const incidentId = params.id as string
  const { currentIncident, fetchIncident } = useIncidentStore()
  const [activeTab, setActiveTab] = useState('overview')
  const [isLoadingData, setIsLoadingData] = useState(true)
  const [tasks, setTasks] = useState<Task[]>([])
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [hosts, setHosts] = useState<CompromisedHost[]>([])

  // Modal States
  const [showEditModal, setShowEditModal] = useState(false)
  const [showStatusModal, setShowStatusModal] = useState(false)
  const [showHostModal, setShowHostModal] = useState(false)
  const [editingHost, setEditingHost] = useState<CompromisedHost | null>(null)
  const [showTaskModal, setShowTaskModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Report generation state
  const [showReportModal, setShowReportModal] = useState(false)
  const [selectedReportType, setSelectedReportType] = useState('executive')
  const [isGeneratingReport, setIsGeneratingReport] = useState(false)
  const { toast } = useToast()

  // Edit Forms
  const [editForm, setEditForm] = useState({
    title: '',
    description: '',
    severity: 'medium',
    classification: '',
  })

  const [hostForm, setHostForm] = useState({
    hostname: '',
    ip_address: '',
    system_type: 'workstation',
    os_version: '',
    containment_status: 'active',
    first_seen: '',
    evidence: '',
  })

  const [taskForm, setTaskForm] = useState({
    title: '',
    description: '',
    priority: 'medium',
    assignee_id: '',
    due_date: '',
    phase: '',
    linked_entities: [] as { type: string; id: string; label: string }[],
  })

  // Entity data for task linking
  const [taskEntityData, setTaskEntityData] = useState<{
    accounts: CompromisedAccount[]
    malware: MalwareTool[]
    hostIndicators: HostBasedIndicator[]
    users: UserType[]
  }>({ accounts: [], malware: [], hostIndicators: [], users: [] })
  const [linkEntityType, setLinkEntityType] = useState('')

  useEffect(() => {
    if (incidentId) {
      loadIncidentData()
    }
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

  // --- Handlers ---

  const openEditModal = () => {
    if (!currentIncident) return
    setEditForm({
      title: currentIncident.title,
      description: currentIncident.description || '',
      severity: currentIncident.severity,
      classification: currentIncident.classification || '',
    })
    setShowEditModal(true)
  }

  const handleEditIncident = async () => {
    if (!editForm.title) return
    setIsSubmitting(true)
    try {
      // 1. Update general details
      await api.put(`/incidents/${incidentId}`, {
        title: editForm.title,
        description: editForm.description,
        severity: editForm.severity,
        classification: editForm.classification
      })

      await fetchIncident(incidentId)
      setShowEditModal(false)
    } catch (error) {
      console.error('Failed to update incident:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleUpdateStatus = async (newStatus: string) => {
    const statusOpt = STATUS_OPTIONS.find(s => s.value === newStatus)
    if (!statusOpt) return
    setIsSubmitting(true)
    try {
      await api.patch(`/incidents/${incidentId}/status`, { status: newStatus, phase: statusOpt.phase })
      await fetchIncident(incidentId)
      setShowStatusModal(false)
      toast({ title: 'Status updated', description: `Moved to Phase ${statusOpt.phase}: ${statusOpt.phaseName}` })
    } catch (error) {
      console.error('Failed to update status:', error)
      toast({ title: 'Error', description: 'Failed to update incident status.', variant: 'destructive' })
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleOpenHostModal = (host?: CompromisedHost) => {
    if (host) {
      setEditingHost(host)
      setHostForm({
        hostname: host.hostname,
        ip_address: host.ip_address || '',
        system_type: host.system_type || 'workstation',
        os_version: host.os_version || '',
        containment_status: host.containment_status || 'active',
        first_seen: host.first_seen || '',
        evidence: host.evidence || '',
      })
    } else {
      setEditingHost(null)
      setHostForm({ hostname: '', ip_address: '', system_type: 'workstation', os_version: '', containment_status: 'active', first_seen: '', evidence: '' })
    }
    setShowHostModal(true)
  }

  const handleSubmitHost = async () => {
    if (!hostForm.hostname) return
    setIsSubmitting(true)
    try {
      const payload = hostForm
      if (editingHost) {
        await api.put(`/incidents/${incidentId}/hosts/${editingHost.id}`, payload)
      } else {
        await api.post(`/incidents/${incidentId}/hosts`, payload)
      }

      const hostsRes = await api.get<{ items: CompromisedHost[] }>(`/incidents/${incidentId}/hosts`)
      setHosts(hostsRes.items || [])
      setShowHostModal(false)
      setEditingHost(null)
      setHostForm({ hostname: '', ip_address: '', system_type: 'workstation', os_version: '', containment_status: 'active', first_seen: '', evidence: '' })
    } catch (error) {
      console.error('Failed to save host:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const loadTaskEntityData = async () => {
    try {
      const [accountsRes, malwareRes, hostIocsRes, usersRes] = await Promise.all([
        api.get<{ items: CompromisedAccount[] }>(`/incidents/${incidentId}/accounts`),
        api.get<{ items: MalwareTool[] }>(`/incidents/${incidentId}/malware`),
        api.get<{ items: HostBasedIndicator[] }>(`/incidents/${incidentId}/host-iocs`),
        api.get<{ items: UserType[] }>('/users').catch(() => ({ items: [] })),
      ])
      setTaskEntityData({
        accounts: accountsRes.items || [],
        malware: malwareRes.items || [],
        hostIndicators: hostIocsRes.items || [],
        users: usersRes.items || [],
      })
    } catch (error) {
      console.error('Failed to load entity data for tasks:', error)
    }
  }

  const handleOpenTaskModal = () => {
    setTaskForm({
      title: '',
      description: '',
      priority: 'medium',
      assignee_id: '',
      due_date: '',
      phase: '',
      linked_entities: [],
    })
    setLinkEntityType('')
    loadTaskEntityData()
    setShowTaskModal(true)
  }

  const addLinkedEntity = (type: string, id: string, label: string) => {
    if (taskForm.linked_entities.some((e) => e.id === id)) return
    setTaskForm({
      ...taskForm,
      linked_entities: [...taskForm.linked_entities, { type, id, label }],
    })
    setLinkEntityType('')
  }

  const removeLinkedEntity = (id: string) => {
    setTaskForm({
      ...taskForm,
      linked_entities: taskForm.linked_entities.filter((e) => e.id !== id),
    })
  }

  const handleAddTask = async () => {
    if (!taskForm.title) return
    setIsSubmitting(true)
    try {
      const payload = {
        title: taskForm.title,
        description: taskForm.description,
        priority: taskForm.priority,
        assignee_id: taskForm.assignee_id || null,
        due_date: taskForm.due_date || null,
        phase: taskForm.phase ? parseInt(taskForm.phase) : null,
        extra_data: {
          linked_entities: taskForm.linked_entities.length > 0 ? taskForm.linked_entities : undefined,
        },
      }
      await api.post(`/incidents/${incidentId}/tasks`, payload)
      const tasksRes = await api.get<{ items: Task[] }>(`/incidents/${incidentId}/tasks`)
      setTasks(tasksRes.items || [])
      setShowTaskModal(false)
    } catch (error) {
      console.error('Failed to add task:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const REPORT_TYPE_OPTIONS = [
    { id: 'executive', label: 'Executive Summary', description: 'High-level overview for stakeholders' },
    { id: 'metrics', label: 'Incident Metrics', description: 'Statistical analysis and response metrics' },
    { id: 'ioc', label: 'IOC Analysis', description: 'Indicators of compromise breakdown' },
    { id: 'trends', label: 'Trend Report', description: 'Patterns and emerging threat analysis' },
  ]

  const handleGenerateReport = async () => {
    setIsGeneratingReport(true)
    const typeName = REPORT_TYPE_OPTIONS.find(r => r.id === selectedReportType)?.label || 'Report'
    toast({ title: 'Generating Report', description: `AI is generating ${typeName}...` })
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000/api/v1'
      const token = api.getToken()
      const response = await fetch(`${API_URL}/incidents/${incidentId}/reports/generate-pdf`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ report_type: selectedReportType }),
      })
      if (!response.ok) {
        const errData = await response.json().catch(() => ({ message: 'Generation failed' }))
        throw new Error(errData.message || 'Report generation failed')
      }
      const pdfBlob = await response.blob()
      const url = URL.createObjectURL(pdfBlob)
      const a = document.createElement('a')
      a.href = url
      a.download = `incident_${currentIncident?.incident_number ?? 'report'}_${selectedReportType}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast({ title: 'Report Generated', description: `${typeName} has been downloaded.` })
      setShowReportModal(false)
    } catch (err) {
      toast({
        title: 'Generation Failed',
        description: err instanceof Error ? err.message : 'An error occurred while generating the report.',
        variant: 'destructive',
      })
    } finally {
      setIsGeneratingReport(false)
    }
  }


  if (isLoadingData && !currentIncident) {
    return <div className="p-8"><SkeletonPage /></div>
  }

  if (!currentIncident) return <div>Incident not found</div>

  const incident = currentIncident
  const completedTasks = tasks.filter((t) => t.status === 'completed').length
  const taskProgress = tasks.length > 0 ? Math.round((completedTasks / tasks.length) * 100) : 0

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
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-mono text-sm text-muted-foreground">
                  #{incident.incident_number}
                </span>
                <SeverityBadge severity={incident.severity as any} />
                <StatusBadge status={incident.status as any} />
                <PhaseBadge phase={incident.phase} />
              </div>
              <h1 className="text-2xl lg:text-3xl font-bold text-foreground">{incident.title}</h1>
              {incident.description && (
                <p className="text-muted-foreground max-w-2xl">{incident.description}</p>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button variant="outline" onClick={() => setShowReportModal(true)}>
                <Download className="mr-2 h-4 w-4" /> Generate Report
              </Button>
              <Button variant="outline" onClick={() => setShowImportModal(true)}>
                <Upload className="mr-2 h-4 w-4" /> Import
              </Button>
              <Button variant="outline" onClick={openEditModal}>
                <Edit2 className="mr-2 h-4 w-4" /> Edit
              </Button>
              <Button onClick={() => setShowStatusModal(true)}>
                <Zap className="mr-2 h-4 w-4" /> Update Status
              </Button>
            </div>
          </div>
        </div>

        {/* Phase Progress */}
        <Card className="overflow-hidden">
          <CardContent className="p-6 relative">
            {/* Background grid pattern */}
            <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: 'linear-gradient(rgba(6,182,212,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(6,182,212,0.5) 1px, transparent 1px)', backgroundSize: '20px 20px' }} />
            <div className="relative flex items-center w-full">
              {PHASE_INFO.map((phase, index) => {
                const isCompleted = phase.number < incident.phase
                const isCurrent = phase.number === incident.phase
                const isUpcoming = phase.number > incident.phase
                return (
                  <div key={phase.number} className="flex items-center flex-1 last:flex-none">
                    {/* Node */}
                    <div className="flex flex-col items-center z-10">
                      <div
                        className={`relative w-9 h-9 lg:w-11 lg:h-11 rounded-full flex items-center justify-center font-semibold text-sm transition-all duration-500 ${
                          isCompleted
                            ? `bg-gradient-to-r ${phase.color} text-white shadow-lg shadow-cyan-500/20`
                            : isCurrent
                              ? `bg-gradient-to-r ${phase.color} text-white animate-phase-pulse`
                              : 'bg-white/[0.06] text-white/30 border border-white/[0.08]'
                        }`}
                      >
                        {/* Scan ring for current phase — centered on circle */}
                        {isCurrent && (
                          <div className="absolute inset-0 -m-2 rounded-full animate-phase-scan pointer-events-none">
                            <div className="w-full h-full rounded-full" style={{ background: 'conic-gradient(from 0deg, transparent 0%, rgba(6,182,212,0.4) 30%, transparent 60%)' }} />
                          </div>
                        )}
                        {isCompleted ? (
                          <CheckCircle2 className="h-5 w-5" />
                        ) : (
                          <span className={isCurrent ? 'drop-shadow-[0_0_6px_rgba(255,255,255,0.5)]' : ''}>{phase.number}</span>
                        )}
                      </div>
                      <span className={`text-[10px] lg:text-xs mt-2.5 text-center font-medium transition-colors duration-300 ${
                        isCompleted ? 'text-cyan-400' : isCurrent ? 'text-cyan-300' : 'text-white/30'
                      }`}>
                        {phase.short}
                      </span>
                    </div>
                    {/* Connector line */}
                    {index < PHASE_INFO.length - 1 && (
                      <div className="flex-1 mx-1.5 lg:mx-3 relative" style={{ height: '2px', marginBottom: '20px' }}>
                        {/* Track */}
                        <div className="absolute inset-0 bg-white/[0.06] rounded-full" />
                        {/* Filled portion */}
                        {(isCompleted || isCurrent) && (
                          <div
                            className={`absolute inset-y-0 left-0 rounded-full animate-line-fill ${
                              isCompleted
                                ? 'bg-gradient-to-r from-cyan-500 to-cyan-400 w-full shadow-[0_0_8px_rgba(6,182,212,0.3)]'
                                : 'bg-gradient-to-r from-cyan-500/80 to-cyan-500/20 w-full'
                            }`}
                          />
                        )}
                        {/* Data flow particles on completed lines */}
                        {isCompleted && (
                          <div className="absolute inset-0 overflow-hidden rounded-full">
                            <div
                              className="absolute w-2 h-full bg-gradient-to-r from-transparent via-white/60 to-transparent rounded-full animate-data-flow"
                              style={{ animationDelay: `${index * 0.4}s` }}
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList variant="underline" className="w-full justify-start flex-wrap h-auto gap-y-2">
            <TabsTrigger variant="underline" value="overview" className="gap-2">
              <Activity className="h-4 w-4" /> Overview
            </TabsTrigger>
            <TabsTrigger variant="underline" value="events" className="gap-2">
              <LayoutList className="h-4 w-4" /> Events
            </TabsTrigger>
            <TabsTrigger variant="underline" value="timeline" className="gap-2">
              <Clock className="h-4 w-4" /> Timeline
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
            <TabsTrigger variant="underline" value="artifacts" className="gap-2">
              <FileText className="h-4 w-4" /> Artifacts
            </TabsTrigger>
          </TabsList>

          {/* Overview TabContent */}
          <TabsContent value="overview">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 space-y-6">
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                  <StatCard title="Events" value={incident.counts?.timeline_events || 0} icon={<Clock className="h-5 w-5" />} />
                  <StatCard title="Hosts" value={incident.counts?.compromised_hosts || 0} icon={<Server className="h-5 w-5" />} />
                  <StatCard title="Artifacts" value={incident.counts?.artifacts || 0} icon={<FileText className="h-5 w-5" />} />
                  <StatCard title="Tasks" value={incident.counts?.tasks || 0} description={`${taskProgress}% Done`} icon={<CheckSquare className="h-5 w-5" />} />
                </div>

                <Card>
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-lg">Recent Activity</CardTitle>
                    <Button variant="ghost" size="sm" onClick={() => setActiveTab('events')}>View all <ChevronRight className="ml-1 h-4 w-4" /></Button>
                  </CardHeader>
                  <CardContent>
                    {timeline.length === 0 ? (
                      <div className="text-center py-8 text-muted-foreground">No recent activity</div>
                    ) : (
                      <div className="space-y-4">
                        {timeline.slice(0, 5).map(event => (
                          <div key={event.id} className="flex gap-4 p-3 rounded-lg hover:bg-white/5 transition-colors">
                            <div className="text-xs text-muted-foreground w-24 shrink-0 pt-0.5">{formatRelativeTime(event.timestamp)}</div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm text-foreground truncate">{event.activity}</p>
                              {event.hostname && <span className="text-xs text-muted-foreground flex items-center gap-1 mt-1"><Server className="h-3 w-3" />{event.hostname}</span>}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>

              <div className="space-y-6">
                <Card>
                  <CardHeader><CardTitle className="text-lg">Details</CardTitle></CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Classification</p>
                      <p className="font-medium text-foreground">{incident.classification || 'Not classified'}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Lead Responder</p>
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-gradient-to-r from-cyan-500 to-blue-500 flex items-center justify-center text-white text-xs font-medium">
                          {incident.lead_responder?.name?.charAt(0) || '?'}
                        </div>
                        <span className="font-medium text-foreground">{incident.lead_responder?.name || 'Unassigned'}</span>
                      </div>
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
              </div>
            </div>
          </TabsContent>

          {/* Events Tab */}
          <TabsContent value="events">
            <EventsTable incidentId={incidentId} />
          </TabsContent>

          {/* Timeline Tab */}
          <TabsContent value="timeline">
            <IOCVisualTimeline incidentId={incidentId} />
          </TabsContent>

          {/* Hosts Tab */}
          <TabsContent value="hosts">
            <Card>
              <CardHeader className="flex items-center justify-between">
                <div>
                  <CardTitle>Compromised Hosts</CardTitle>
                  <CardDescription>Systems affected by this incident</CardDescription>
                </div>
                <Button onClick={() => handleOpenHostModal()}><Plus className="mr-2 h-4 w-4" /> Add Host</Button>
              </CardHeader>
              <CardContent className="p-0">
                <GlassTable className="border-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Hostname</TableHead>
                        <TableHead>IP</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Containment</TableHead>
                        <TableHead>First Seen</TableHead>
                        <TableHead className="w-[50px]"></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {hosts.length === 0 ? (
                        <TableRow><TableCell colSpan={4}><TableEmpty title="No hosts" icon={<Server className="w-10 h-10" />} /></TableCell></TableRow>
                      ) : (
                        hosts.map(host => (
                          <TableRow key={host.id} className="group">
                            <TableCell className="font-medium">{host.hostname}</TableCell>
                            <TableCell>{host.ip_address}</TableCell>
                            <TableCell>{host.system_type}</TableCell>
                            <TableCell>
                              <Badge variant={host.containment_status === 'isolated' ? 'default' : 'destructive'}>
                                {host.containment_status || 'Active'}
                              </Badge>
                            </TableCell>
                            <TableCell>{host.first_seen ? formatDateTime(host.first_seen) : '-'}</TableCell>
                            <TableCell>
                              <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100" onClick={() => handleOpenHostModal(host)}>
                                <MoreHorizontal className="w-4 h-4" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </GlassTable>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tasks Tab */}
          <TabsContent value="tasks">
            <Card>
              <CardHeader className="flex items-center justify-between">
                <div>
                  <CardTitle>Tasks</CardTitle>
                  <CardDescription>Response checklist</CardDescription>
                </div>
                <Button onClick={handleOpenTaskModal}><Plus className="mr-2 h-4 w-4" /> Add Task</Button>
              </CardHeader>
              <CardContent>
                {tasks.length === 0 ? <TableEmpty title="No tasks" icon={<CheckSquare className="w-10 h-10" />} /> : (
                  <div className="space-y-3">
                    {tasks.map(task => {
                      const linkedEntities = task.extra_data?.linked_entities
                      const priorityColors: Record<string, string> = {
                        critical: 'bg-red-500/20 text-red-400 border-red-500/30',
                        high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
                        medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
                        low: 'bg-green-500/20 text-green-400 border-green-500/30',
                      }
                      const entityIcons: Record<string, React.ReactNode> = {
                        host: <Server className="w-3 h-3" />,
                        account: <Key className="w-3 h-3" />,
                        malware: <Bug className="w-3 h-3" />,
                        host_indicator: <Fingerprint className="w-3 h-3" />,
                      }
                      return (
                        <div key={task.id} className="rounded-xl bg-white/5 border border-white/10 p-4 flex gap-4">
                          <div className={`mt-0.5 ${task.status === 'completed' ? 'text-green-400' : 'text-muted-foreground'}`}>
                            {task.status === 'completed' ? <CheckCircle2 className="w-5 h-5" /> : <Circle className="w-5 h-5" />}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h4 className={`font-medium ${task.status === 'completed' ? 'line-through text-muted-foreground' : 'text-foreground'}`}>{task.title}</h4>
                              <Badge className={`${priorityColors[task.priority] || ''} border text-[10px] px-1.5 py-0`}>
                                {task.priority}
                              </Badge>
                            </div>
                            {task.description && <p className="text-sm text-muted-foreground mt-1">{task.description}</p>}
                            <div className="flex items-center gap-3 mt-2 flex-wrap">
                              {task.assignee && (
                                <span className="text-xs text-muted-foreground flex items-center gap-1">
                                  <User className="w-3 h-3" /> {task.assignee.name}
                                </span>
                              )}
                              {task.due_date && (
                                <span className="text-xs text-muted-foreground flex items-center gap-1">
                                  <Calendar className="w-3 h-3" /> {formatDateTime(task.due_date)}
                                </span>
                              )}
                            </div>
                            {linkedEntities && linkedEntities.length > 0 && (
                              <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                                <Link2 className="w-3 h-3 text-muted-foreground" />
                                {linkedEntities.map((entity) => (
                                  <span key={entity.id} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                                    {entityIcons[entity.type] || null}
                                    {entity.label}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Other Tabs */}
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
            <ArtifactsTab incidentId={incidentId} />
          </TabsContent>

        </Tabs>
      </div>

      {/* Edit Modal */}
      <Dialog open={showEditModal} onOpenChange={setShowEditModal}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit Incident</DialogTitle></DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-2">
              <Label>Title</Label>
              <Input value={editForm.title} onChange={e => setEditForm({ ...editForm, title: e.target.value })} variant="glass" />
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea value={editForm.description} onChange={e => setEditForm({ ...editForm, description: e.target.value })} variant="glass" />
            </div>
            <div className="space-y-2">
              <Label>Severity</Label>
              <Select value={editForm.severity} onValueChange={v => setEditForm({ ...editForm, severity: v })}>
                <SelectTrigger variant="glass"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Low</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Classification</Label>
              <Input value={editForm.classification} onChange={e => setEditForm({ ...editForm, classification: e.target.value })} variant="glass" />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditModal(false)}>Cancel</Button>
            <Button onClick={handleEditIncident} loading={isSubmitting}>Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Update Status Modal */}
      <Dialog open={showStatusModal} onOpenChange={setShowStatusModal}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Update Status & Phase</DialogTitle></DialogHeader>
          <DialogBody className="space-y-2">
            {STATUS_OPTIONS.map(opt => (
              <button key={opt.value} onClick={() => handleUpdateStatus(opt.value)}
                disabled={isSubmitting}
                className={`w-full flex items-center gap-3 p-3 rounded-lg border transition-colors ${incident.status === opt.value ? 'bg-cyan-500/10 border-cyan-500/50' : 'border-white/10 hover:bg-white/5'} disabled:opacity-50`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold bg-gradient-to-r ${PHASE_INFO[opt.phase - 1].color}`}>
                  {opt.phase}
                </div>
                <div className="flex flex-col items-start">
                  <span className="font-medium text-foreground">{opt.label}</span>
                  <span className="text-xs text-muted-foreground">{opt.phaseName}</span>
                </div>
                {incident.status === opt.value && <CheckCircle2 className="h-4 w-4 text-cyan-400 ml-auto" />}
              </button>
            ))}
          </DialogBody>
        </DialogContent>
      </Dialog>

      {/* Add Host Modal */}
      <Dialog open={showHostModal} onOpenChange={setShowHostModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{editingHost ? 'Edit' : 'Add'} Host</DialogTitle></DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-2">
              <Label>Hostname</Label>
              <Input value={hostForm.hostname} onChange={e => setHostForm({ ...hostForm, hostname: e.target.value })} variant="glass" />
            </div>
            <div className="space-y-2">
              <Label>IP Address</Label>
              <Input value={hostForm.ip_address} onChange={e => setHostForm({ ...hostForm, ip_address: e.target.value })} variant="glass" />
            </div>
            <div className="space-y-2">
              <Label>System Type</Label>
              <Select value={hostForm.system_type} onValueChange={v => setHostForm({ ...hostForm, system_type: v })}>
                <SelectTrigger variant="glass"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="workstation">Workstation</SelectItem>
                  <SelectItem value="server">Server</SelectItem>
                  <SelectItem value="domain_controller">Domain Controller</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>OS Version</Label>
              <Input value={hostForm.os_version} onChange={e => setHostForm({ ...hostForm, os_version: e.target.value })} variant="glass" />
            </div>
            <div className="space-y-2">
              <Label>Containment Status</Label>
              <Select value={hostForm.containment_status} onValueChange={v => setHostForm({ ...hostForm, containment_status: v })}>
                <SelectTrigger variant="glass"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="isolated">Isolated</SelectItem>
                  <SelectItem value="reimaged">Reimaged</SelectItem>
                  <SelectItem value="decommissioned">Decommissioned</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Evidence / Notes</Label>
              <Textarea value={hostForm.evidence} onChange={e => setHostForm({ ...hostForm, evidence: e.target.value })} variant="glass" />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowHostModal(false)}>Cancel</Button>
            <Button onClick={handleSubmitHost} loading={isSubmitting}>{editingHost ? 'Save Changes' : 'Add Host'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Task Modal */}
      <Dialog open={showTaskModal} onOpenChange={setShowTaskModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Add Task</DialogTitle>
            <DialogDescription>Create a response task and link it to incident entities</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4 max-h-[60vh] overflow-y-auto">
            <div className="space-y-2">
              <Label>Title *</Label>
              <Input value={taskForm.title} onChange={e => setTaskForm({ ...taskForm, title: e.target.value })} placeholder="Task title..." variant="glass" />
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea value={taskForm.description} onChange={e => setTaskForm({ ...taskForm, description: e.target.value })} placeholder="Describe the task..." variant="glass" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Priority</Label>
                <Select value={taskForm.priority} onValueChange={v => setTaskForm({ ...taskForm, priority: v })}>
                  <SelectTrigger variant="glass"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Phase</Label>
                <Select value={taskForm.phase} onValueChange={v => setTaskForm({ ...taskForm, phase: v })}>
                  <SelectTrigger variant="glass"><SelectValue placeholder="Select phase..." /></SelectTrigger>
                  <SelectContent>
                    {PHASE_INFO.map(p => <SelectItem key={p.number} value={String(p.number)}>{p.number}. {p.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Assignee</Label>
                <Select value={taskForm.assignee_id} onValueChange={v => setTaskForm({ ...taskForm, assignee_id: v })}>
                  <SelectTrigger variant="glass"><SelectValue placeholder="Unassigned" /></SelectTrigger>
                  <SelectContent>
                    {taskEntityData.users.map(u => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Due Date</Label>
                <Input type="datetime-local" value={taskForm.due_date} onChange={e => setTaskForm({ ...taskForm, due_date: e.target.value })} variant="glass" />
              </div>
            </div>

            {/* Linked Entities */}
            <div className="space-y-2">
              <Label className="flex items-center gap-2">
                <Link2 className="w-4 h-4" /> Linked Entities
              </Label>
              {taskForm.linked_entities.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {taskForm.linked_entities.map((entity) => {
                    const iconMap: Record<string, React.ReactNode> = {
                      host: <Server className="w-3 h-3" />,
                      account: <Key className="w-3 h-3" />,
                      malware: <Bug className="w-3 h-3" />,
                      host_indicator: <Fingerprint className="w-3 h-3" />,
                    }
                    return (
                      <span key={entity.id} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                        {iconMap[entity.type] || null}
                        {entity.label}
                        <button onClick={() => removeLinkedEntity(entity.id)} className="ml-1 hover:text-red-400">
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    )
                  })}
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <Select value={linkEntityType} onValueChange={setLinkEntityType}>
                  <SelectTrigger variant="glass"><SelectValue placeholder="Entity type..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="host">Host</SelectItem>
                    <SelectItem value="account">Account</SelectItem>
                    <SelectItem value="malware">Malware</SelectItem>
                    <SelectItem value="host_indicator">Host Indicator</SelectItem>
                  </SelectContent>
                </Select>
                {linkEntityType === 'host' && (
                  <Select onValueChange={(v) => {
                    const host = hosts.find(h => h.id === v)
                    if (host) addLinkedEntity('host', host.id, host.hostname)
                  }}>
                    <SelectTrigger variant="glass"><SelectValue placeholder="Select host..." /></SelectTrigger>
                    <SelectContent>
                      {hosts.map(h => <SelectItem key={h.id} value={h.id}>{h.hostname} ({h.ip_address})</SelectItem>)}
                    </SelectContent>
                  </Select>
                )}
                {linkEntityType === 'account' && (
                  <Select onValueChange={(v) => {
                    const acc = taskEntityData.accounts.find(a => a.id === v)
                    if (acc) addLinkedEntity('account', acc.id, `${acc.domain ? acc.domain + '\\' : ''}${acc.account_name}`)
                  }}>
                    <SelectTrigger variant="glass"><SelectValue placeholder="Select account..." /></SelectTrigger>
                    <SelectContent>
                      {taskEntityData.accounts.map(a => <SelectItem key={a.id} value={a.id}>{a.domain ? `${a.domain}\\` : ''}{a.account_name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                )}
                {linkEntityType === 'malware' && (
                  <Select onValueChange={(v) => {
                    const mal = taskEntityData.malware.find(m => m.id === v)
                    if (mal) addLinkedEntity('malware', mal.id, mal.file_name)
                  }}>
                    <SelectTrigger variant="glass"><SelectValue placeholder="Select malware..." /></SelectTrigger>
                    <SelectContent>
                      {taskEntityData.malware.map(m => <SelectItem key={m.id} value={m.id}>{m.file_name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                )}
                {linkEntityType === 'host_indicator' && (
                  <Select onValueChange={(v) => {
                    const ioc = taskEntityData.hostIndicators.find(i => i.id === v)
                    if (ioc) addLinkedEntity('host_indicator', ioc.id, `${ioc.artifact_type}: ${ioc.artifact_value.slice(0, 40)}`)
                  }}>
                    <SelectTrigger variant="glass"><SelectValue placeholder="Select indicator..." /></SelectTrigger>
                    <SelectContent>
                      {taskEntityData.hostIndicators.map(i => <SelectItem key={i.id} value={i.id}>{i.artifact_type}: {i.artifact_value.slice(0, 50)}</SelectItem>)}
                    </SelectContent>
                  </Select>
                )}
                {!linkEntityType && <div />}
              </div>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowTaskModal(false)}>Cancel</Button>
            <Button onClick={handleAddTask} loading={isSubmitting}>Add Task</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Report Generation Modal */}
      <Dialog open={showReportModal} onOpenChange={setShowReportModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Generate Report</DialogTitle>
            <DialogDescription>
              Select a report type to generate an AI-powered PDF report for this incident.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <div className="space-y-3">
              {REPORT_TYPE_OPTIONS.map((type) => (
                <label
                  key={type.id}
                  className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${selectedReportType === type.id
                      ? 'border-cyan-500/50 bg-cyan-500/10'
                      : 'border-white/10 hover:border-white/20 hover:bg-white/5'
                    }`}
                >
                  <input
                    type="radio"
                    name="reportType"
                    value={type.id}
                    checked={selectedReportType === type.id}
                    onChange={(e) => setSelectedReportType(e.target.value)}
                    className="mt-1 accent-cyan-500"
                  />
                  <div>
                    <p className="font-medium text-sm">{type.label}</p>
                    <p className="text-xs text-muted-foreground">{type.description}</p>
                  </div>
                </label>
              ))}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowReportModal(false)} disabled={isGeneratingReport}>
              Cancel
            </Button>
            <Button onClick={handleGenerateReport} disabled={isGeneratingReport}>
              {isGeneratingReport ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating...
                </>
              ) : (
                <>
                  <Download className="mr-2 h-4 w-4" /> Generate PDF
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Import Wizard Modal */}
      <ImportWizardModal
        isOpen={showImportModal}
        onOpenChange={setShowImportModal}
        incidentId={incidentId}
        onComplete={loadIncidentData}
      />
    </>
  )
}
