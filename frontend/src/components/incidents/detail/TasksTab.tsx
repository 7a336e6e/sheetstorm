"use client"

import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { TableEmpty } from '@/components/ui/table'
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
  Plus,
  CheckCircle2,
  Circle,
  Clock,
  Calendar,
  User,
  Server,
  CheckSquare,
  Key,
  Fingerprint,
  Bug,
  Edit2,
  Link2,
  X,
  MessageSquare,
  Trash2,
  Send,
  Search,
  Filter,
} from 'lucide-react'
import { PHASE_INFO } from '@/lib/design-tokens'
import { formatDateTime, formatRelativeTime } from '@/lib/utils'
import api from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import type { Task, CompromisedHost, CompromisedAccount, MalwareTool, HostBasedIndicator, User as UserType } from '@/types'

// ─── Tasks Tab (self-contained) ──────────────────────────────────────────

interface TasksTabProps {
  incidentId: string
  tasks: Task[]
  hosts: CompromisedHost[]
  onTasksChange: (tasks: Task[]) => void
}

export function TasksTab({ incidentId, tasks, hosts, onTasksChange }: TasksTabProps) {
  const { user } = useAuthStore()
  const isAdmin = user?.roles?.includes('Administrator') ?? false
  const canWrite = user?.permissions?.includes('tasks:update') ?? false

  // Modal state
  const [showTaskModal, setShowTaskModal] = useState(false)
  const [editingTask, setEditingTask] = useState<Task | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Task form
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

  // Filters
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [priorityFilter, setPriorityFilter] = useState<string>('all')
  const [assigneeFilter, setAssigneeFilter] = useState<string>('all')

  // Comments
  const [taskComments, setTaskComments] = useState<Record<string, any[]>>({})
  const [expandedTaskComments, setExpandedTaskComments] = useState<string | null>(null)
  const [newComment, setNewComment] = useState('')
  const [isAddingComment, setIsAddingComment] = useState(false)

  // ─── Handlers ──────────────────────────────────────────────

  const refreshTasks = async () => {
    try {
      const res = await api.get<{ items: Task[] }>(`/incidents/${incidentId}/tasks`)
      onTasksChange(res.items || [])
    } catch (error) {
      console.error('Failed to refresh tasks:', error)
    }
  }

  const loadTaskEntityData = async () => {
    try {
      const [accountsRes, malwareRes, hostIocsRes, usersRes] = await Promise.all([
        api.get<{ items: CompromisedAccount[] }>(`/incidents/${incidentId}/accounts`),
        api.get<{ items: MalwareTool[] }>(`/incidents/${incidentId}/malware`),
        api.get<{ items: HostBasedIndicator[] }>(`/incidents/${incidentId}/host-iocs`),
        api.get<{ items: UserType[] }>('/users').catch(() => ({ items: [] as UserType[] })),
      ])
      setTaskEntityData({
        accounts: accountsRes.items || [],
        malware: malwareRes.items || [],
        hostIndicators: hostIocsRes.items || [],
        users: usersRes.items || [],
      })
    } catch (error) {
      console.error('Failed to load entity data:', error)
    }
  }

  const handleOpenTaskModal = () => {
    setEditingTask(null)
    setTaskForm({
      title: '', description: '', priority: 'medium',
      assignee_id: '', due_date: '', phase: '', linked_entities: [],
    })
    setLinkEntityType('')
    loadTaskEntityData()
    setShowTaskModal(true)
  }

  const handleOpenEditTask = (task: Task) => {
    setEditingTask(task)
    setTaskForm({
      title: task.title,
      description: task.description || '',
      priority: task.priority,
      assignee_id: task.assignee?.id || '',
      due_date: task.due_date || '',
      phase: task.phase?.toString() || '',
      linked_entities: task.extra_data?.linked_entities || [],
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

  const handleSaveTask = async () => {
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
      if (editingTask) {
        await api.put(`/incidents/${incidentId}/tasks/${editingTask.id}`, payload)
      } else {
        await api.post(`/incidents/${incidentId}/tasks`, payload)
      }
      await refreshTasks()
      setShowTaskModal(false)
      setEditingTask(null)
    } catch (error) {
      console.error('Failed to save task:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteTask = async (taskId: string) => {
    try {
      await api.delete(`/incidents/${incidentId}/tasks/${taskId}`)
      onTasksChange(tasks.filter(t => t.id !== taskId))
    } catch (error) {
      console.error('Failed to delete task:', error)
    }
  }

  const handleToggleTaskStatus = async (task: Task) => {
    const nextStatus = task.status === 'completed' ? 'pending' : task.status === 'pending' ? 'in_progress' : 'completed'
    try {
      await api.put(`/incidents/${incidentId}/tasks/${task.id}`, { status: nextStatus })
      onTasksChange(tasks.map(t => t.id === task.id ? { ...t, status: nextStatus } : t))
    } catch (error) {
      console.error('Failed to toggle task status:', error)
    }
  }

  const handleToggleComments = async (taskId: string) => {
    if (expandedTaskComments === taskId) {
      setExpandedTaskComments(null)
      return
    }
    setExpandedTaskComments(taskId)
    if (!taskComments[taskId]) {
      try {
        const res = await api.get<{ items: any[] }>(`/incidents/${incidentId}/tasks/${taskId}/comments`)
        setTaskComments(prev => ({ ...prev, [taskId]: res.items || [] }))
      } catch (error) {
        console.error('Failed to load comments:', error)
      }
    }
  }

  const handleAddComment = async (taskId: string) => {
    if (!newComment.trim()) return
    setIsAddingComment(true)
    try {
      await api.post(`/incidents/${incidentId}/tasks/${taskId}/comments`, { content: newComment })
      const res = await api.get<{ items: any[] }>(`/incidents/${incidentId}/tasks/${taskId}/comments`)
      setTaskComments(prev => ({ ...prev, [taskId]: res.items || [] }))
      setNewComment('')
    } catch (error) {
      console.error('Failed to add comment:', error)
    } finally {
      setIsAddingComment(false)
    }
  }

  const handleDeleteComment = async (taskId: string, commentId: string) => {
    try {
      await api.delete(`/incidents/${incidentId}/tasks/${taskId}/comments/${commentId}`)
      setTaskComments(prev => ({
        ...prev,
        [taskId]: (prev[taskId] || []).filter(c => c.id !== commentId),
      }))
    } catch (error) {
      console.error('Failed to delete comment:', error)
    }
  }

  // ─── Task priority & status helpers ────────────────────────

  const priorityColors: Record<string, string> = {
    critical: 'border-red-500/20 bg-red-500/10 text-red-700 dark:text-red-400',
    high: 'border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-400',
    medium: 'border-yellow-500/20 bg-yellow-500/10 text-yellow-700 dark:text-yellow-400',
    low: 'border-teal-500/20 bg-teal-500/10 text-teal-700 dark:text-teal-400',
  }

  const statusInfo: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
    pending: { icon: <Circle className="w-5 h-5" />, color: 'text-muted-foreground', label: 'Pending' },
    in_progress: { icon: <Clock className="w-5 h-5" />, color: 'text-blue-600 dark:text-blue-400', label: 'In Progress' },
    completed: { icon: <CheckCircle2 className="w-5 h-5" />, color: 'text-emerald-600 dark:text-emerald-400', label: 'Completed' },
  }

  const entityIcons: Record<string, React.ReactNode> = {
    host: <Server className="w-3 h-3" />,
    account: <Key className="w-3 h-3" />,
    malware: <Bug className="w-3 h-3" />,
    host_indicator: <Fingerprint className="w-3 h-3" />,
  }

  // ─── Filtering ─────────────────────────────────────────────

  const uniqueAssignees = Array.from(
    new Map(tasks.filter(t => t.assignee).map(t => [t.assignee!.id, t.assignee!])).values()
  )

  const hasActiveFilters = search || statusFilter !== 'all' || priorityFilter !== 'all' || assigneeFilter !== 'all'

  const filteredTasks = tasks.filter(t => {
    if (statusFilter !== 'all' && t.status !== statusFilter) return false
    if (priorityFilter !== 'all' && t.priority !== priorityFilter) return false
    if (assigneeFilter !== 'all') {
      if (assigneeFilter === 'unassigned' && t.assignee) return false
      if (assigneeFilter !== 'unassigned' && t.assignee?.id !== assigneeFilter) return false
    }
    if (search) {
      const q = search.toLowerCase()
      return t.title.toLowerCase().includes(q) || (t.description?.toLowerCase().includes(q) ?? false)
    }
    return true
  })

  // ─── Render ────────────────────────────────────────────────

  return (
    <>
      <div className="space-y-4">
        {/* Filters & Action */}
        <Card>
          <CardContent className="p-4">
            <div className="flex flex-col lg:flex-row gap-4 justify-between">
              <div className="flex flex-col lg:flex-row gap-4 flex-1">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search tasks..."
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    className="pl-10"
                    variant="glass"
                  />
                </div>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-[160px]">
                    <Filter className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Statuses</SelectItem>
                    <SelectItem value="pending">Pending</SelectItem>
                    <SelectItem value="in_progress">In Progress</SelectItem>
                    <SelectItem value="completed">Completed</SelectItem>
                    <SelectItem value="blocked">Blocked</SelectItem>
                    <SelectItem value="cancelled">Cancelled</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={priorityFilter} onValueChange={setPriorityFilter}>
                  <SelectTrigger className="w-[160px]">
                    <Filter className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Priority" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Priorities</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="low">Low</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={assigneeFilter} onValueChange={setAssigneeFilter}>
                  <SelectTrigger className="w-[160px]">
                    <User className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Assignee" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Assignees</SelectItem>
                    <SelectItem value="unassigned">Unassigned</SelectItem>
                    {uniqueAssignees.map(a => (
                      <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {canWrite && (
                <Button onClick={handleOpenTaskModal}>
                  <Plus className="mr-2 h-4 w-4" /> Add Task
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Tasks List */}
        {filteredTasks.length === 0 ? (
          <Card>
            <CardContent className="p-0">
              <TableEmpty
                title={hasActiveFilters ? 'No matching tasks' : 'No tasks yet'}
                description={hasActiveFilters ? 'Try adjusting your search or filter criteria.' : 'Create tasks to track response actions, assignments, and progress for this incident.'}
                icon={<CheckSquare className="w-8 h-8" />}
                action={!hasActiveFilters && canWrite && (
                  <Button size="sm" variant="outline" onClick={handleOpenTaskModal}>
                    <Plus className="mr-2 h-3.5 w-3.5" /> Add Task
                  </Button>
                )}
              />
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {filteredTasks.map(task => {
                const linkedEntities = task.extra_data?.linked_entities
                const st = statusInfo[task.status] || statusInfo.pending
                const isExpanded = expandedTaskComments === task.id
                const comments = taskComments[task.id] || []

                return (
                  <div key={task.id} className="rounded-xl bg-muted/50 border border-border p-4">
                    <div className="flex gap-4">
                      {canWrite ? (
                        <button
                          onClick={() => handleToggleTaskStatus(task)}
                          className={`mt-0.5 ${st.color} hover:opacity-80 transition-opacity cursor-pointer`}
                          title={`Status: ${st.label} — Click to change`}
                        >
                          {st.icon}
                        </button>
                      ) : (
                        <span className={`mt-0.5 ${st.color}`} title={`Status: ${st.label}`}>
                          {st.icon}
                        </span>
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className={`font-medium ${task.status === 'completed' ? 'line-through text-muted-foreground' : 'text-foreground'}`}>
                            {task.title}
                          </h4>
                          <Badge className={`${priorityColors[task.priority] || ''} border text-[10px] px-1.5 py-0`}>
                            {task.priority}
                          </Badge>
                          <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${st.color}`}>
                            {st.label}
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
                              <span key={entity.id} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                                {entityIcons[entity.type] || null}
                                {entity.label}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex items-start gap-1 flex-shrink-0">
                        <Button variant="ghost" size="sm" onClick={() => handleToggleComments(task.id)} title="Comments">
                          <MessageSquare className="h-4 w-4" />
                          {comments.length > 0 && <span className="ml-1 text-xs">{comments.length}</span>}
                        </Button>
                        {canWrite && (
                          <Button variant="ghost" size="sm" onClick={() => handleOpenEditTask(task)} title="Edit">
                            <Edit2 className="h-4 w-4" />
                          </Button>
                        )}
                        {isAdmin && (
                          <Button variant="ghost" size="sm" onClick={() => handleDeleteTask(task.id)} className="text-destructive hover:text-destructive/80" title="Delete">
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Expandable Comments */}
                    {isExpanded && (
                      <div className="mt-3 pt-3 border-t border-border ml-9">
                        {comments.length === 0 ? (
                          <p className="text-xs text-muted-foreground mb-2">No comments yet</p>
                        ) : (
                          <div className="space-y-2 mb-3">
                            {comments.map((comment: any) => (
                              <div key={comment.id} className="flex items-start gap-2 text-sm">
                                <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center text-primary-foreground text-[10px] font-medium flex-shrink-0">
                                  {comment.author?.name?.charAt(0) || '?'}
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs font-medium text-foreground">{comment.author?.name || 'Unknown'}</span>
                                    <span className="text-[10px] text-muted-foreground">{formatRelativeTime(comment.created_at)}</span>
                                  </div>
                                  <p className="text-xs text-muted-foreground mt-0.5">{comment.content}</p>
                                </div>
                                {isAdmin && (
                                  <Button variant="ghost" size="sm" onClick={() => handleDeleteComment(task.id, comment.id)} className="h-6 w-6 p-0 text-destructive hover:text-destructive/80">
                                    <X className="h-3 w-3" />
                                  </Button>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                        {canWrite && (
                          <div className="flex items-center gap-2">
                            <Input
                              placeholder="Add a comment..."
                              value={newComment}
                              onChange={e => setNewComment(e.target.value)}
                              className="text-xs h-8"
                              onKeyDown={e => { if (e.key === 'Enter') handleAddComment(task.id) }}
                            />
                            <Button size="sm" onClick={() => handleAddComment(task.id)} disabled={isAddingComment || !newComment.trim()} className="h-8">
                              <Send className="h-3 w-3" />
                            </Button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
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
        hosts={hosts}
        linkEntityType={linkEntityType}
        setLinkEntityType={setLinkEntityType}
        addLinkedEntity={addLinkedEntity}
        removeLinkedEntity={removeLinkedEntity}
      />
    </>
  )
}

// ─── Task Form Modal (internal) ──────────────────────────────────────────

interface TaskFormModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editingTask: Task | null
  taskForm: {
    title: string
    description: string
    priority: string
    assignee_id: string
    due_date: string
    phase: string
    linked_entities: { type: string; id: string; label: string }[]
  }
  setTaskForm: (form: any) => void
  onSave: () => void
  isSubmitting: boolean
  taskEntityData: {
    accounts: CompromisedAccount[]
    malware: MalwareTool[]
    hostIndicators: HostBasedIndicator[]
    users: UserType[]
  }
  hosts: CompromisedHost[]
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
  hosts,
  linkEntityType,
  setLinkEntityType,
  addLinkedEntity,
  removeLinkedEntity,
}: TaskFormModalProps) {
  const entityIcons: Record<string, React.ReactNode> = {
    host: <Server className="w-3 h-3" />,
    account: <Key className="w-3 h-3" />,
    malware: <Bug className="w-3 h-3" />,
    host_indicator: <Fingerprint className="w-3 h-3" />,
  }

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
              <Select value={taskForm.assignee_id} onValueChange={v => setTaskForm({ ...taskForm, assignee_id: v })}>
                <SelectTrigger><SelectValue placeholder="Unassigned" /></SelectTrigger>
                <SelectContent>
                  {taskEntityData.users.map(u => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Due Date</Label>
              <Input type="datetime-local" value={taskForm.due_date} onChange={e => setTaskForm({ ...taskForm, due_date: e.target.value })} />
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
                    <button onClick={() => removeLinkedEntity(entity.id)} className="ml-1 hover:text-destructive">
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
                  const host = hosts.find(h => h.id === v)
                  if (host) addLinkedEntity('host', host.id, host.hostname)
                }}>
                  <SelectTrigger><SelectValue placeholder="Select host..." /></SelectTrigger>
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
