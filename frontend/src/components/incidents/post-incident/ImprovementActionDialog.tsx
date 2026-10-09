"use client"

/**
 * Create / edit one improvement action (W3-RT-POST). Create needs
 * `improvements:create`; edit sends `If-Match` with the row version (a stale
 * version opens the global conflict dialog). D3FEND control references
 * autocomplete from the knowledge base.
 */
import { useEffect, useId, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DateTimeInput } from '@/components/ui/datetime-input'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { UserPicker } from '@/components/ui/entity-picker'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import api, { isAbortError, withQuery } from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { notifyError } from '@/lib/errors'
import { postIncident, IMPROVEMENT_ACTIONS_ENDPOINT, incidentActionsEndpoint } from '@/lib/endpoints/post-incident'
import {
  CATEGORY_OPTIONS,
  FRAMEWORK_OPTIONS,
  PRIORITY_OPTIONS,
  STATUS_OPTIONS,
  controlRefProblem,
} from '@/lib/post-incident'
import type {
  ActionPriority,
  ActionStatus,
  ContributingCategory,
  ControlFramework,
  ImprovementAction,
} from '@/types'

const NONE = '__none__'

interface D3fendTechnique {
  id: string
  name: string
}

interface Props {
  open: boolean
  onOpenChange(open: boolean): void
  /** Needed to create; an edit may pass null (the action's incident was deleted). */
  incidentId: string | null
  /** The row being edited; null/undefined creates a new action. */
  action?: ImprovementAction | null
  /** Called after a successful save (lists are already invalidated). */
  onSaved?(saved: ImprovementAction): void
}

interface Form {
  title: string
  description: string
  ownerId: string | null
  ownerName: string | undefined
  dueDate: string | null
  status: ActionStatus
  priority: ActionPriority
  category: ContributingCategory | typeof NONE
  framework: ControlFramework | typeof NONE
  controlRef: string
}

const blank = (): Form => ({
  title: '',
  description: '',
  ownerId: null,
  ownerName: undefined,
  dueDate: null,
  status: 'open',
  priority: 'medium',
  category: NONE,
  framework: NONE,
  controlRef: '',
})

const fromAction = (a: ImprovementAction): Form => ({
  title: a.title,
  description: a.description ?? '',
  ownerId: a.owner_id,
  ownerName: a.owner?.name,
  dueDate: a.due_date,
  status: a.status,
  priority: a.priority,
  category: a.category ?? NONE,
  framework: a.control_framework ?? NONE,
  controlRef: a.control_ref ?? '',
})

/** D3FEND technique suggestions for `term` (>= 2 characters), debounced. */
function useD3fendSuggestions(enabled: boolean, term: string): D3fendTechnique[] {
  const [items, setItems] = useState<D3fendTechnique[]>([])
  const query = term.trim()
  const active = enabled && query.length >= 2
  useEffect(() => {
    if (!active) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      api
        .get<{ items: D3fendTechnique[] }>(withQuery('/knowledge-base/d3fend', { search: query }), {
          signal: controller.signal,
        })
        .then((res) => setItems((res.items ?? []).slice(0, 15)))
        .catch((err: unknown) => {
          if (!isAbortError(err)) setItems([])
        })
    }, 250)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [active, query])
  return active ? items : []
}

export function ImprovementActionDialog({ open, onOpenChange, incidentId, action, onSaved }: Props) {
  const editing = !!action
  const [form, setForm] = useState<Form>(blank)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const listId = useId()

  // Reset the form each time the dialog opens (for the row being edited).
  const [lastOpen, setLastOpen] = useState(false)
  if (open !== lastOpen) {
    setLastOpen(open)
    if (open) {
      setForm(action ? fromAction(action) : blank())
      setError(null)
    }
  }

  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
    setError(null)
  }

  const suggestions = useD3fendSuggestions(open && form.framework === 'd3fend', form.controlRef)
  const framework = form.framework === NONE ? null : form.framework
  const example = FRAMEWORK_OPTIONS.find((f) => f.value === framework)?.example

  const save = async () => {
    const title = form.title.trim()
    if (!title) {
      setError('A title is required.')
      return
    }
    const refProblem = controlRefProblem(framework, form.controlRef)
    if (refProblem) {
      setError(refProblem)
      return
    }
    const input = {
      title,
      description: form.description.trim() || null,
      owner_id: form.ownerId,
      due_date: form.dueDate,
      priority: form.priority,
      category: form.category === NONE ? null : form.category,
      control_framework: framework,
      control_ref: framework ? form.controlRef.trim() || null : null,
    }
    setSaving(true)
    setError(null)
    try {
      if (!action && !incidentId) throw new Error('An incident is required to add an improvement action')
      const saved = action
        ? await postIncident.updateAction(action.id, { ...input, status: form.status }, action.version)
        : await postIncident.createAction(incidentId as string, { ...input, status: form.status })
      if (incidentId) invalidate(incidentActionsEndpoint(incidentId))
      invalidate(IMPROVEMENT_ACTIONS_ENDPOINT)
      onOpenChange(false)
      onSaved?.(saved)
    } catch (err) {
      notifyError(err, editing ? 'save the improvement action' : 'add the improvement action')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{editing ? 'Edit improvement action' : 'Add improvement action'}</DialogTitle>
          <DialogDescription>
            A follow-up from the review. It stays listed organization-wide after the incident closes.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="ia-title">Title</Label>
            <Input
              id="ia-title"
              value={form.title}
              maxLength={500}
              onChange={(e) => set('title', e.target.value)}
              disabled={saving}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ia-description">Description</Label>
            <Textarea
              id="ia-description"
              value={form.description}
              rows={3}
              maxLength={10000}
              onChange={(e) => set('description', e.target.value)}
              disabled={saving}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Owner</Label>
              <UserPicker
                value={form.ownerId}
                valueLabel={form.ownerName}
                ariaLabel="Owner"
                placeholder="Search users…"
                disabled={saving}
                onChange={(id, user) => {
                  setForm((f) => ({ ...f, ownerId: id, ownerName: user?.name ?? f.ownerName }))
                  setError(null)
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ia-due">Due</Label>
              <DateTimeInput
                id="ia-due"
                value={form.dueDate}
                step={60}
                onChange={(iso) => set('dueDate', iso)}
                disabled={saving}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Status</Label>
              <Select value={form.status} onValueChange={(v) => set('status', v as ActionStatus)} disabled={saving}>
                <SelectTrigger aria-label="Status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Priority</Label>
              <Select value={form.priority} onValueChange={(v) => set('priority', v as ActionPriority)} disabled={saving}>
                <SelectTrigger aria-label="Priority">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRIORITY_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Category</Label>
              <Select
                value={form.category}
                onValueChange={(v) => set('category', v as Form['category'])}
                disabled={saving}
              >
                <SelectTrigger aria-label="Category">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>No category</SelectItem>
                  {CATEGORY_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Control framework</Label>
              <Select
                value={form.framework}
                onValueChange={(v) => set('framework', v as Form['framework'])}
                disabled={saving}
              >
                <SelectTrigger aria-label="Control framework">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>None</SelectItem>
                  {FRAMEWORK_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          {framework && (
            <div className="space-y-1.5">
              <Label htmlFor="ia-control-ref">Control reference</Label>
              <Input
                id="ia-control-ref"
                value={form.controlRef}
                maxLength={100}
                placeholder={example ? `e.g. ${example}` : undefined}
                list={framework === 'd3fend' ? listId : undefined}
                onChange={(e) => set('controlRef', e.target.value)}
                disabled={saving}
              />
              {framework === 'd3fend' && (
                <datalist id={listId}>
                  {suggestions.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </datalist>
              )}
            </div>
          )}
          {error && (
            <p role="alert" className="text-sm text-red-400">
              {error}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {editing ? 'Save action' : 'Add action'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
