"use client"

import { useState } from 'react'
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
import { DateTimeInput } from '@/components/ui/datetime-input'
import { Timestamp } from '@/components/ui/timestamp'
import { DataTable, FilterSelect, type DataTableColumn } from '@/components/ui/data-table'
import { EntityPicker, UserPicker } from '@/components/ui/entity-picker'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { usePermission, usePermissionCheck } from '@/components/auth/permission-gate'
import { useAllPages, usePaginatedQuery } from '@/hooks/use-paginated-query'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import {
  CheckCircle2,
  Circle,
  Clock,
  Calendar,
  User,
  Edit2,
  Link2,
  X,
  MessageSquare,
  Trash2,
  Send,
  Loader2,
} from 'lucide-react'
import { PHASE_INFO } from '@/lib/design-tokens'
import { cn, formatRelativeTime } from '@/lib/utils'
import api from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { notifyError } from '@/lib/errors'
import { useAuthStore } from '@/lib/store'
import type { DfirTask, TaskEvidence, VersionedRow } from '@/types'
import { FocusNotice, type IncidentTabBaseProps } from '../table-helpers'
import {
  EVIDENCE_TYPES,
  EvidenceChips,
  LeadOutcomeBadge,
  LeadsView,
  OUTCOME_OPTIONS,
  evidenceLabel,
  taskEvidence,
  useOpenEvidence,
} from './LeadsView'

// ─── Types ───────────────────────────────────────────────────────────────

interface TaskComment {
  id: string
  content: string
  author?: { id: string; name: string } | null
  created_at: string
  version?: number
}

type TaskRow = VersionedRow<DfirTask> & { comments?: TaskComment[] }

interface TaskForm {
  title: string
  description: string
  priority: string
  task_type: string
  lead_outcome: string
  investigation_direction: string
  assignee_id: string
  due_date: string
  phase: string
  /** Linked evidence (labels for display only; only refs are sent). */
  evidence: TaskEvidence[]
}

const EMPTY_FORM: TaskForm = {
  title: '', description: '', priority: 'medium',
  task_type: 'action_item', lead_outcome: '', investigation_direction: '',
  assignee_id: '', due_date: '', phase: '', evidence: [],
}

const TASK_TYPE_OPTIONS = [
  { value: 'action_item', label: 'Action Item' },
  { value: 'investigative_lead', label: 'Investigative Lead' },
  { value: 'verification', label: 'Verification' },
  { value: 'documentation', label: 'Documentation' },
  { value: 'reporting', label: 'Reporting' },
]

/** Evidence the link picker offers: list endpoint + server-searched labels. */
interface LinkSource {
  type: string
  path: string
  label: (item: Record<string, unknown>) => string
  description?: (item: Record<string, unknown>) => string | undefined
}

const str = (v: unknown) => (v === null || v === undefined ? '' : String(v))

const LINK_SOURCES: LinkSource[] = [
  { type: 'host', path: 'hosts', label: (i) => str(i.hostname), description: (i) => str(i.ip_address) || undefined },
  { type: 'account', path: 'accounts', label: (i) => (i.domain ? `${str(i.domain)}\\${str(i.account_name)}` : str(i.account_name)) },
  { type: 'malware', path: 'malware', label: (i) => str(i.file_name) },
  { type: 'host_ioc', path: 'host-iocs', label: (i) => `${str(i.artifact_type)}: ${str(i.artifact_value).slice(0, 60)}` },
  { type: 'network_ioc', path: 'network-iocs', label: (i) => str(i.dns_ip) },
  { type: 'timeline_event', path: 'timeline', label: (i) => str(i.activity).slice(0, 80), description: (i) => str(i.timestamp) || undefined },
  { type: 'artifact', path: 'artifacts', label: (i) => str(i.original_filename || i.filename) },
]

/** `?tasks.view=leads` switches the tab to the lead queue (deep-linkable). */
export const TASKS_VIEW_PARAM = 'tasks.view'

const STATUS_OPTIONS = [
  { value: 'pending', label: 'Pending' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'completed', label: 'Completed' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'cancelled', label: 'Cancelled' },
]

const PRIORITY_OPTIONS = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
]

const priorityColors: Record<string, string> = {
  critical: 'border-red-500/20 bg-red-500/10 text-red-400',
  high: 'border-amber-500/20 bg-amber-500/10 text-amber-400',
  medium: 'border-yellow-500/20 bg-yellow-500/10 text-yellow-400',
  low: 'border-teal-500/20 bg-teal-500/10 text-teal-400',
}

const statusInfo: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  pending: { icon: <Circle className="w-5 h-5" />, color: 'text-muted-foreground', label: 'Pending' },
  in_progress: { icon: <Clock className="w-5 h-5" />, color: 'text-blue-400', label: 'In Progress' },
  completed: { icon: <CheckCircle2 className="w-5 h-5" />, color: 'text-emerald-400', label: 'Completed' },
  blocked: { icon: <Circle className="w-5 h-5" />, color: 'text-red-400', label: 'Blocked' },
  cancelled: { icon: <Circle className="w-5 h-5" />, color: 'text-muted-foreground', label: 'Cancelled' },
}

// ─── Tasks Tab ───────────────────────────────────────────────────────────

export function TasksTab({ incidentId, focusRowId }: IncidentTabBaseProps) {
  const confirm = useConfirm()
  const userId = useAuthStore((s) => s.user?.id)
  const canCreate = usePermission('tasks:create')
  const canUpdate = usePermission('tasks:update')
  const canDeleteAny = usePermission('tasks:delete')

  const endpoint = `/incidents/${incidentId}/tasks`
  const leadsView = useSearchParams()?.get(TASKS_VIEW_PARAM) === 'leads'
  const query = usePaginatedQuery<TaskRow>({
    endpoint,
    urlKey: 'tasks',
    focus: leadsView ? null : focusRowId,
    live: 'task',
    enabled: !leadsView,
  })

  // Modal state
  const [showTaskModal, setShowTaskModal] = useState(false)
  const [editingTask, setEditingTask] = useState<TaskRow | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [taskForm, setTaskForm] = useState<TaskForm>(EMPTY_FORM)
  const [linkEntityType, setLinkEntityType] = useState('')
  const openEvidence = useOpenEvidence()

  // ─── View: all tasks | leads (URL `tasks.view`) ────────────
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const view = searchParams?.get(TASKS_VIEW_PARAM) === 'leads' ? 'leads' : 'all'
  const setView = (next: 'all' | 'leads') => {
    const params = new URLSearchParams(searchParams?.toString() ?? '')
    if (next === 'leads') params.set(TASKS_VIEW_PARAM, 'leads')
    else params.delete(TASKS_VIEW_PARAM)
    params.delete('row')
    const qs = params.toString()
    router.replace(`${pathname}${qs ? `?${qs}` : ''}`, { scroll: false })
  }

  // ─── Handlers ──────────────────────────────────────────────

  const handleOpenTaskModal = () => {
    setEditingTask(null)
    setTaskForm(EMPTY_FORM)
    setLinkEntityType('')
    setShowTaskModal(true)
  }

  const handleOpenEditTask = (task: TaskRow) => {
    setEditingTask(task)
    setTaskForm({
      title: task.title,
      description: task.description || '',
      priority: task.priority,
      task_type: task.task_type || 'action_item',
      lead_outcome: task.lead_outcome || '',
      investigation_direction: task.investigation_direction || '',
      assignee_id: task.assignee?.id || '',
      due_date: task.due_date || '',
      phase: task.phase?.toString() || '',
      evidence: taskEvidence(task),
    })
    setLinkEntityType('')
    setShowTaskModal(true)
  }

  const addEvidence = (evidence_type: string, evidence_id: string, label: string) => {
    if (taskForm.evidence.some((e) => e.evidence_type === evidence_type && e.evidence_id === evidence_id)) return
    setTaskForm({
      ...taskForm,
      evidence: [...taskForm.evidence, { evidence_type, evidence_id, label, missing: false }],
    })
    setLinkEntityType('')
  }

  const removeEvidence = (e: TaskEvidence) => {
    setTaskForm({
      ...taskForm,
      evidence: taskForm.evidence.filter(
        (x) => !(x.evidence_type === e.evidence_type && x.evidence_id === e.evidence_id)
      ),
    })
  }

  const handleSaveTask = async () => {
    if (!taskForm.title) return
    setIsSubmitting(true)
    try {
      const payload = {
        title: taskForm.title,
        description: taskForm.description,
        priority: taskForm.priority,
        task_type: taskForm.task_type,
        lead_outcome: taskForm.task_type === 'investigative_lead' ? (taskForm.lead_outcome || null) : null,
        investigation_direction: taskForm.task_type === 'investigative_lead'
          ? (taskForm.investigation_direction.trim() || null)
          : (editingTask?.investigation_direction ?? null),
        assignee_id: taskForm.assignee_id || null,
        due_date: taskForm.due_date || null,
        phase: taskForm.phase ? parseInt(taskForm.phase) : null,
        // Server-validated refs; labels are resolved by the server on read.
        evidence_refs: taskForm.evidence.map(({ evidence_type, evidence_id }) => ({ evidence_type, evidence_id })),
      }
      if (editingTask) {
        await api.put(`${endpoint}/${editingTask.id}`, payload, { ifMatch: editingTask.version })
      } else {
        await api.post(endpoint, payload)
      }
      invalidate(endpoint)
      setShowTaskModal(false)
      setEditingTask(null)
    } catch (error) {
      notifyError(error, editingTask ? 'save the task' : 'add the task')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteTask = async (task: TaskRow) => {
    if (!(await confirmDelete(confirm, 'task', task.title))) return
    try {
      await api.delete(`${endpoint}/${task.id}`, undefined, { ifMatch: task.version })
      invalidate(endpoint)
    } catch (error) {
      notifyError(error, 'delete the task')
    }
  }

  const handleToggleTaskStatus = async (task: TaskRow) => {
    const nextStatus = task.status === 'completed' ? 'pending' : task.status === 'pending' ? 'in_progress' : 'completed'
    try {
      await api.put(`${endpoint}/${task.id}`, { status: nextStatus }, { ifMatch: task.version })
      invalidate(endpoint)
    } catch (error) {
      notifyError(error, 'change the task status')
    }
  }

  // ─── Columns ───────────────────────────────────────────────

  const columns: DataTableColumn<TaskRow>[] = [
    {
      id: 'toggle',
      header: <span className="sr-only">Toggle status</span>,
      className: 'w-10 px-2',
      cell: (task) => {
        const st = statusInfo[task.status] || statusInfo.pending
        return canUpdate ? (
          <button
            type="button"
            onClick={() => handleToggleTaskStatus(task)}
            className={`${st.color} hover:opacity-80 transition-opacity cursor-pointer`}
            title={`Status: ${st.label} — Click to change`}
            aria-label={`Change status of ${task.title} (now ${st.label})`}
          >
            {st.icon}
          </button>
        ) : (
          <span className={st.color} title={`Status: ${st.label}`}>
            {st.icon}
          </span>
        )
      },
    },
    {
      id: 'title',
      header: 'Task',
      sortKey: 'order_index',
      cell: (task) => {
        const evidence = taskEvidence(task)
        const type = task.task_type || 'action_item'
        return (
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className={`font-medium ${task.status === 'completed' ? 'line-through text-muted-foreground' : 'text-foreground'}`}>
                {task.title}
              </span>
              {type !== 'action_item' && (
                <Badge variant="outline" className="px-1.5 py-0 text-[10px] text-muted-foreground">
                  {TASK_TYPE_OPTIONS.find((o) => o.value === type)?.label ?? type}
                </Badge>
              )}
              {type === 'investigative_lead' && <LeadOutcomeBadge outcome={task.lead_outcome} />}
            </div>
            {task.description && <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{task.description}</p>}
            <EvidenceChips evidence={evidence} onOpen={openEvidence} className="mt-2" />
          </div>
        )
      },
    },
    {
      id: 'priority',
      header: 'Priority',
      sortKey: 'priority',
      cell: (task) => (
        <Badge className={`${priorityColors[task.priority] || ''} border text-[10px] px-1.5 py-0`}>
          {task.priority}
        </Badge>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      sortKey: 'status',
      hideBelow: 'sm',
      cell: (task) => {
        const st = statusInfo[task.status] || statusInfo.pending
        return (
          <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${st.color}`}>
            {st.label}
          </Badge>
        )
      },
    },
    {
      id: 'assignee',
      header: 'Assignee',
      hideBelow: 'md',
      cell: (task) =>
        task.assignee ? (
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <User className="w-3 h-3" /> {task.assignee.name}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground/60">Unassigned</span>
        ),
    },
    {
      id: 'due_date',
      header: 'Due',
      sortKey: 'due_date',
      hideBelow: 'md',
      cell: (task) =>
        task.due_date ? (
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <Calendar className="w-3 h-3" /> <Timestamp value={task.due_date} seconds={false} />
          </span>
        ) : (
          <span className="text-xs text-muted-foreground/60">-</span>
        ),
    },
    {
      id: 'comments',
      header: <MessageSquare className="h-3.5 w-3.5" aria-label="Comments" />,
      hideBelow: 'lg',
      className: 'w-12 text-xs text-muted-foreground tabular-nums',
      cell: (task) => (task.comments?.length ? task.comments.length : ''),
    },
  ]

  // ─── Render ────────────────────────────────────────────────

  return (
    <>
      <div className="space-y-4">
        <div role="group" aria-label="Tasks view" className="inline-flex h-8 items-center rounded-md border border-white/10 bg-slate-900 p-0.5 text-xs">
          {(['all', 'leads'] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={view === v}
              onClick={() => setView(v)}
              className={cn(
                'h-full rounded px-3 transition-colors',
                view === v ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {v === 'all' ? 'All tasks' : 'Leads'}
            </button>
          ))}
        </div>
        {view === 'leads' ? (
          <LeadsView incidentId={incidentId} focusRowId={focusRowId} onEdit={(t) => handleOpenEditTask(t as TaskRow)} />
        ) : (
        <>
        <FocusNotice focusRowId={focusRowId} focusFound={query.focusFound} noun="task" />
        <DataTable
          query={query}
          columns={columns}
          getRowId={(t) => t.id}
          ariaLabel="Tasks"
          searchPlaceholder="Search tasks..."
          toolbar={
            <>
              <FilterSelect
                label="Status"
                allLabel="All statuses"
                value={query.state.filters.status}
                onChange={(v) => query.setFilter('status', v)}
                options={STATUS_OPTIONS}
              />
              <FilterSelect
                label="Priority"
                allLabel="All priorities"
                value={query.state.filters.priority}
                onChange={(v) => query.setFilter('priority', v)}
                options={PRIORITY_OPTIONS}
              />
              <FilterSelect
                label="Type"
                allLabel="All types"
                value={query.state.filters.task_type}
                onChange={(v) => query.setFilter('task_type', v)}
                options={TASK_TYPE_OPTIONS}
              />
              <FilterSelect
                label="Lead outcome"
                allLabel="Any outcome"
                value={query.state.filters.lead_outcome}
                onChange={(v) => query.setFilter('lead_outcome', v)}
                options={OUTCOME_OPTIONS}
              />
              <UserPicker
                ariaLabel="Filter by assignee"
                placeholder="Any assignee"
                className="w-[200px]"
                value={query.state.filters.assignee_id ?? null}
                onChange={(id) => query.setFilter('assignee_id', id ?? undefined)}
              />
            </>
          }
          primaryAction={{ label: 'Add Task', onSelect: handleOpenTaskModal, permission: 'tasks:create' }}
          rowActions={(task) => [
            { label: 'Edit', icon: Edit2, onSelect: () => handleOpenEditTask(task), permission: 'tasks:update' },
            { label: 'Delete', icon: Trash2, destructive: true, onSelect: () => void handleDeleteTask(task), permission: 'tasks:delete' },
          ]}
          renderExpanded={(task) => (
            <TaskComments
              endpoint={`${endpoint}/${task.id}/comments`}
              canComment={canUpdate}
              canDeleteComment={(c) => canUpdate && (canDeleteAny || (!!userId && c.author?.id === userId))}
            />
          )}
          focusedRowId={focusRowId}
          empty={{
            title: 'No tasks yet',
            description: 'Create tasks to track response actions, assignments, and progress for this incident.',
            action: canCreate ? (
              <Button size="sm" variant="outline" onClick={handleOpenTaskModal}>
                Add Task
              </Button>
            ) : undefined,
          }}
        />
        </>
        )}
      </div>

      {/* Add/Edit Task Modal */}
      <TaskFormModal
        open={showTaskModal}
        onOpenChange={(open) => { if (!open) { setShowTaskModal(false); setEditingTask(null) } }}
        editingTask={editingTask}
        incidentId={incidentId}
        taskForm={taskForm}
        setTaskForm={setTaskForm}
        onSave={handleSaveTask}
        isSubmitting={isSubmitting}
        linkEntityType={linkEntityType}
        setLinkEntityType={setLinkEntityType}
        addEvidence={addEvidence}
        removeEvidence={removeEvidence}
      />
    </>
  )
}

// ─── Comments (expanded row) ─────────────────────────────────────────────

function TaskComments({
  endpoint,
  canComment,
  canDeleteComment,
}: {
  endpoint: string
  canComment: boolean
  canDeleteComment: (c: TaskComment) => boolean
}) {
  const confirm = useConfirm()
  // The full comment list (oldest first); the task row only embeds the latest 20.
  const comments = useAllPages<TaskComment>(endpoint, { live: 'task_comment' })
  const [newComment, setNewComment] = useState('')
  const [isAdding, setIsAdding] = useState(false)

  const handleAdd = async () => {
    if (!newComment.trim()) return
    setIsAdding(true)
    try {
      await api.post(endpoint, { content: newComment })
      setNewComment('')
      invalidate(endpoint)
    } catch (error) {
      notifyError(error, 'add the comment')
    } finally {
      setIsAdding(false)
    }
  }

  const handleDelete = async (comment: TaskComment) => {
    if (!(await confirmDelete(confirm, 'comment'))) return
    try {
      await api.delete(
        `${endpoint}/${comment.id}`,
        undefined,
        comment.version !== undefined ? { ifMatch: comment.version } : undefined
      )
      invalidate(endpoint)
    } catch (error) {
      notifyError(error, 'delete the comment')
    }
  }

  return (
    <div className="pl-2">
      {comments.isLoading ? (
        <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
          <Loader2 className="h-3 w-3 animate-spin" /> Loading comments…
        </p>
      ) : comments.error ? (
        <p role="alert" className="text-xs text-destructive mb-2">
          Couldn&apos;t load comments.{' '}
          <button type="button" className="underline" onClick={() => void comments.refetch()}>Retry</button>
        </p>
      ) : comments.items.length === 0 ? (
        <p className="text-xs text-muted-foreground mb-2">No comments yet</p>
      ) : (
        <div className="space-y-2 mb-3">
          {comments.items.map((comment) => (
            <div key={comment.id} className="flex items-start gap-2 text-sm">
              <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center text-primary-foreground text-[10px] font-medium flex-shrink-0">
                {comment.author?.name?.charAt(0) || '?'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-foreground">{comment.author?.name || 'Unknown'}</span>
                  <span className="text-[10px] text-muted-foreground">{formatRelativeTime(comment.created_at)}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 whitespace-pre-wrap">{comment.content}</p>
              </div>
              {canDeleteComment(comment) && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDelete(comment)}
                  aria-label="Delete comment"
                  className="h-6 w-6 p-0 text-destructive hover:text-destructive/80"
                >
                  <X className="h-3 w-3" />
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
      {canComment && (
        <div className="flex items-center gap-2">
          <Input
            placeholder="Add a comment..."
            aria-label="Add a comment"
            value={newComment}
            onChange={e => setNewComment(e.target.value)}
            className="text-xs h-8"
            onKeyDown={e => { if (e.key === 'Enter') void handleAdd() }}
          />
          <Button size="sm" onClick={handleAdd} disabled={isAdding || !newComment.trim()} className="h-8" aria-label="Send comment">
            <Send className="h-3 w-3" />
          </Button>
        </div>
      )}
    </div>
  )
}

// ─── Task Form Modal (internal) ──────────────────────────────────────────

interface TaskFormModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editingTask: TaskRow | null
  incidentId: string
  taskForm: TaskForm
  setTaskForm: (form: TaskForm) => void
  onSave: () => void
  isSubmitting: boolean
  linkEntityType: string
  setLinkEntityType: (type: string) => void
  addEvidence: (type: string, id: string, label: string) => void
  removeEvidence: (e: TaskEvidence) => void
}

function TaskFormModal({
  open,
  onOpenChange,
  editingTask,
  incidentId,
  taskForm,
  setTaskForm,
  onSave,
  isSubmitting,
  linkEntityType,
  setLinkEntityType,
  addEvidence,
  removeEvidence,
}: TaskFormModalProps) {
  const can = usePermissionCheck()
  // Only offer evidence types the user can read (artifacts need artifacts:read).
  const sources = LINK_SOURCES.filter((s) => can(EVIDENCE_TYPES[s.type]?.permission ?? 'incidents:read'))
  const source = sources.find((s) => s.type === linkEntityType)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editingTask ? 'Edit Task' : 'Add Task'}</DialogTitle>
          <DialogDescription>{editingTask ? 'Update this response task' : 'Create a response task and link it to incident entities'}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4 max-h-[60vh] overflow-y-auto">
          <div className="space-y-2">
            <Label>Title *</Label>
            <Input value={taskForm.title} onChange={e => setTaskForm({ ...taskForm, title: e.target.value })} placeholder="Task title..." />
          </div>
          <div className="space-y-2">
            <Label>Description</Label>
            <Textarea value={taskForm.description} onChange={e => setTaskForm({ ...taskForm, description: e.target.value })} placeholder="Describe the task..." />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Type</Label>
              <Select value={taskForm.task_type} onValueChange={v => setTaskForm({ ...taskForm, task_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="action_item">Action Item</SelectItem>
                  <SelectItem value="investigative_lead">Investigative Lead</SelectItem>
                  <SelectItem value="verification">Verification</SelectItem>
                  <SelectItem value="documentation">Documentation</SelectItem>
                  <SelectItem value="reporting">Reporting</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {taskForm.task_type === 'investigative_lead' && (
              <div className="space-y-2">
                <Label>Lead Outcome</Label>
                <Select value={taskForm.lead_outcome || 'open'} onValueChange={v => setTaskForm({ ...taskForm, lead_outcome: v === 'open' ? '' : v })}>
                  <SelectTrigger><SelectValue placeholder="Open / unresolved" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="open">Open / unresolved</SelectItem>
                    <SelectItem value="false_positive">False Positive</SelectItem>
                    <SelectItem value="confirmed_malicious">Confirmed Malicious</SelectItem>
                    <SelectItem value="inconclusive">Inconclusive</SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
          {taskForm.task_type === 'investigative_lead' && (
            <div className="space-y-2">
              <Label htmlFor="task-direction">Investigation Direction</Label>
              <Textarea
                id="task-direction"
                maxLength={5000}
                value={taskForm.investigation_direction}
                onChange={e => setTaskForm({ ...taskForm, investigation_direction: e.target.value })}
                placeholder="What is this lead trying to prove or disprove?"
              />
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Priority</Label>
              <Select value={taskForm.priority} onValueChange={v => setTaskForm({ ...taskForm, priority: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
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
                <SelectTrigger><SelectValue placeholder="Select phase..." /></SelectTrigger>
                <SelectContent>
                  {Object.values(PHASE_INFO).map(p => (
                    <SelectItem key={p.number} value={String(p.number)}>{p.number}. {p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Assignee</Label>
              <UserPicker
                ariaLabel="Assignee"
                placeholder="Unassigned"
                value={taskForm.assignee_id || null}
                valueLabel={editingTask?.assignee && editingTask.assignee.id === taskForm.assignee_id ? editingTask.assignee.name : undefined}
                onChange={(id) => setTaskForm({ ...taskForm, assignee_id: id ?? '' })}
              />
            </div>
            <div className="space-y-2">
              <Label>Due Date</Label>
              <DateTimeInput step={60} value={taskForm.due_date} onChange={iso => setTaskForm({ ...taskForm, due_date: iso ?? '' })} />
            </div>
          </div>

          {/* Linked evidence (server-validated refs) */}
          <div className="space-y-2">
            <Label className="flex items-center gap-2">
              <Link2 className="w-4 h-4" /> Linked Evidence
            </Label>
            {taskForm.evidence.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {taskForm.evidence.map((e) => {
                  const Icon = EVIDENCE_TYPES[e.evidence_type]?.icon
                  const label = evidenceLabel(e)
                  return (
                    <span key={`${e.evidence_type}:${e.evidence_id}`} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-primary/10 text-primary border border-primary/20">
                      {Icon && <Icon className="w-3 h-3" aria-hidden />}
                      {label}
                      <button type="button" aria-label={`Unlink ${label}`} onClick={() => removeEvidence(e)} className="ml-1 hover:text-destructive">
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  )
                })}
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              <Select value={linkEntityType} onValueChange={setLinkEntityType}>
                <SelectTrigger aria-label="Evidence type"><SelectValue placeholder="Evidence type..." /></SelectTrigger>
                <SelectContent>
                  {sources.map((s) => (
                    <SelectItem key={s.type} value={s.type}>{EVIDENCE_TYPES[s.type]?.label ?? s.type}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {source ? (
                <EntityPicker<Record<string, unknown>>
                  key={source.type}
                  ariaLabel={`Link ${EVIDENCE_TYPES[source.type]?.label ?? source.type}`}
                  placeholder={`Search ${(EVIDENCE_TYPES[source.type]?.label ?? source.type).toLowerCase()}…`}
                  endpoint={`/incidents/${incidentId}/${source.path}`}
                  value={null}
                  getId={(i) => str(i.id)}
                  getLabel={source.label}
                  getDescription={source.description}
                  onChange={(id, item) => {
                    if (id && item) addEvidence(source.type, id, source.label(item))
                  }}
                />
              ) : (
                <div />
              )}
            </div>
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onSave} loading={isSubmitting}>{editingTask ? 'Update Task' : 'Add Task'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
