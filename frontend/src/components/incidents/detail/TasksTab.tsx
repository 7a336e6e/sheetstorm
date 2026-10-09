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
import { UserPicker } from '@/components/ui/entity-picker'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { usePermission } from '@/components/auth/permission-gate'
import { useAllPages, usePaginatedQuery } from '@/hooks/use-paginated-query'
import {
  CheckCircle2,
  Circle,
  Clock,
  Calendar,
  User,
  Server,
  Key,
  Fingerprint,
  Bug,
  Edit2,
  Link2,
  X,
  MessageSquare,
  Trash2,
  Send,
  Loader2,
} from 'lucide-react'
import { PHASE_INFO } from '@/lib/design-tokens'
import { formatRelativeTime } from '@/lib/utils'
import api from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { notifyError } from '@/lib/errors'
import { useAuthStore } from '@/lib/store'
import type {
  Task,
  CompromisedHost,
  CompromisedAccount,
  MalwareTool,
  HostBasedIndicator,
  VersionedRow,
} from '@/types'
import { FocusNotice, type IncidentTabBaseProps } from '../table-helpers'

// ─── Types ───────────────────────────────────────────────────────────────

interface TaskComment {
  id: string
  content: string
  author?: { id: string; name: string } | null
  created_at: string
  version?: number
}

type TaskRow = VersionedRow<Task> & { comments?: TaskComment[] }

interface TaskForm {
  title: string
  description: string
  priority: string
  task_type: string
  lead_outcome: string
  assignee_id: string
  due_date: string
  phase: string
  linked_entities: { type: string; id: string; label: string }[]
}

interface TaskEntityData {
  hosts: CompromisedHost[]
  accounts: CompromisedAccount[]
  malware: MalwareTool[]
  hostIndicators: HostBasedIndicator[]
}

const EMPTY_FORM: TaskForm = {
  title: '', description: '', priority: 'medium',
  task_type: 'action_item', lead_outcome: '',
  assignee_id: '', due_date: '', phase: '', linked_entities: [],
}

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

const entityIcons: Record<string, React.ReactNode> = {
  host: <Server className="w-3 h-3" />,
  account: <Key className="w-3 h-3" />,
  malware: <Bug className="w-3 h-3" />,
  host_indicator: <Fingerprint className="w-3 h-3" />,
}

// ─── Tasks Tab ───────────────────────────────────────────────────────────

export function TasksTab({ incidentId, focusRowId }: IncidentTabBaseProps) {
  const confirm = useConfirm()
  const userId = useAuthStore((s) => s.user?.id)
  const canCreate = usePermission('tasks:create')
  const canUpdate = usePermission('tasks:update')
  const canDeleteAny = usePermission('tasks:delete')

  const endpoint = `/incidents/${incidentId}/tasks`
  const query = usePaginatedQuery<TaskRow>({
    endpoint,
    urlKey: 'tasks',
    focus: focusRowId,
    live: 'task',
  })

  // Modal state
  const [showTaskModal, setShowTaskModal] = useState(false)
  const [editingTask, setEditingTask] = useState<TaskRow | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [taskForm, setTaskForm] = useState<TaskForm>(EMPTY_FORM)
  const [linkEntityType, setLinkEntityType] = useState('')

  // Entities that can be linked: loaded (all pages) only while the modal is open.
  const hosts = useAllPages<CompromisedHost>(`/incidents/${incidentId}/hosts`, { live: 'host', enabled: showTaskModal })
  const accounts = useAllPages<CompromisedAccount>(`/incidents/${incidentId}/accounts`, { live: 'account', enabled: showTaskModal })
  const malware = useAllPages<MalwareTool>(`/incidents/${incidentId}/malware`, { live: 'malware', enabled: showTaskModal })
  const hostIndicators = useAllPages<HostBasedIndicator>(`/incidents/${incidentId}/host-iocs`, { live: 'host_ioc', enabled: showTaskModal })
  const taskEntityData: TaskEntityData = {
    hosts: hosts.items,
    accounts: accounts.items,
    malware: malware.items,
    hostIndicators: hostIndicators.items,
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
      assignee_id: task.assignee?.id || '',
      due_date: task.due_date || '',
      phase: task.phase?.toString() || '',
      linked_entities: task.extra_data?.linked_entities || [],
    })
    setLinkEntityType('')
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
        assignee_id: taskForm.assignee_id || null,
        due_date: taskForm.due_date || null,
        phase: taskForm.phase ? parseInt(taskForm.phase) : null,
        extra_data: {
          linked_entities: taskForm.linked_entities.length > 0 ? taskForm.linked_entities : undefined,
        },
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
        const linkedEntities = task.extra_data?.linked_entities
        return (
          <div className="min-w-0">
            <span className={`font-medium ${task.status === 'completed' ? 'line-through text-muted-foreground' : 'text-foreground'}`}>
              {task.title}
            </span>
            {task.description && <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{task.description}</p>}
            {linkedEntities && linkedEntities.length > 0 && (
              <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                <Link2 className="w-3 h-3 text-muted-foreground" />
                {linkedEntities.map((entity) => (
                  <span key={entity.id} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                    {entityIcons[entity.type] || null}
                    {entity.label}
                  </span>
                ))}
              </div>
            )}
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
      </div>

      {/* Add/Edit Task Modal */}
      <TaskFormModal
        open={showTaskModal}
        onOpenChange={(open) => { if (!open) { setShowTaskModal(false); setEditingTask(null) } }}
        editingTask={editingTask}
        taskForm={taskForm}
        setTaskForm={setTaskForm}
        onSave={handleSaveTask}
        isSubmitting={isSubmitting}
        taskEntityData={taskEntityData}
        linkEntityType={linkEntityType}
        setLinkEntityType={setLinkEntityType}
        addLinkedEntity={addLinkedEntity}
        removeLinkedEntity={removeLinkedEntity}
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
  taskForm: TaskForm
  setTaskForm: (form: TaskForm) => void
  onSave: () => void
  isSubmitting: boolean
  taskEntityData: TaskEntityData
  linkEntityType: string
  setLinkEntityType: (type: string) => void
  addLinkedEntity: (type: string, id: string, label: string) => void
  removeLinkedEntity: (id: string) => void
}

function TaskFormModal({
  open,
  onOpenChange,
  editingTask,
  taskForm,
  setTaskForm,
  onSave,
  isSubmitting,
  taskEntityData,
  linkEntityType,
  setLinkEntityType,
  addLinkedEntity,
  removeLinkedEntity,
}: TaskFormModalProps) {
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

          {/* Linked Entities */}
          <div className="space-y-2">
            <Label className="flex items-center gap-2">
              <Link2 className="w-4 h-4" /> Linked Entities
            </Label>
            {taskForm.linked_entities.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {taskForm.linked_entities.map((entity) => (
                  <span key={entity.id} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-primary/10 text-primary border border-primary/20">
                    {entityIcons[entity.type] || null}
                    {entity.label}
                    <button type="button" aria-label={`Unlink ${entity.label}`} onClick={() => removeLinkedEntity(entity.id)} className="ml-1 hover:text-destructive">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              <Select value={linkEntityType} onValueChange={setLinkEntityType}>
                <SelectTrigger><SelectValue placeholder="Entity type..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="host">Host</SelectItem>
                  <SelectItem value="account">Account</SelectItem>
                  <SelectItem value="malware">Malware</SelectItem>
                  <SelectItem value="host_indicator">Host Indicator</SelectItem>
                </SelectContent>
              </Select>
              {linkEntityType === 'host' && (
                <Select onValueChange={(v) => {
                  const host = taskEntityData.hosts.find(h => h.id === v)
                  if (host) addLinkedEntity('host', host.id, host.hostname)
                }}>
                  <SelectTrigger><SelectValue placeholder="Select host..." /></SelectTrigger>
                  <SelectContent>
                    {taskEntityData.hosts.map(h => <SelectItem key={h.id} value={h.id}>{h.hostname}{h.ip_address ? ` (${h.ip_address})` : ''}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
              {linkEntityType === 'account' && (
                <Select onValueChange={(v) => {
                  const acc = taskEntityData.accounts.find(a => a.id === v)
                  if (acc) addLinkedEntity('account', acc.id, `${acc.domain ? acc.domain + '\\' : ''}${acc.account_name}`)
                }}>
                  <SelectTrigger><SelectValue placeholder="Select account..." /></SelectTrigger>
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
                  <SelectTrigger><SelectValue placeholder="Select malware..." /></SelectTrigger>
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
                  <SelectTrigger><SelectValue placeholder="Select indicator..." /></SelectTrigger>
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
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onSave} loading={isSubmitting}>{editingTask ? 'Update Task' : 'Add Task'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
