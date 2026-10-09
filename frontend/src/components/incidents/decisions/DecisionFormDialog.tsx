"use client"

/**
 * Record or revise a decision (W4-DEC). A revision needs a reason and sends
 * `If-Match` (a stale version opens the global conflict dialog). Status only
 * changes through the transition dialog. The privileged flag is offered only
 * to users who can read privileged decisions.
 */
import { useState } from 'react'
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
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { usePermission } from '@/components/auth/permission-gate'
import { decisionLog } from '@/lib/endpoints/decisions'
import { notifyError } from '@/lib/errors'
import type { Decision, DecisionAlternative, DecisionCategory, DecisionInput } from '@/types'
import { CATEGORY_LABELS, DECISION_CATEGORIES } from './decision-helpers'

interface Props {
  incidentId: string
  open: boolean
  onOpenChange(open: boolean): void
  /** The decision being revised; null creates one. */
  decision?: Decision | null
  onSaved?(d: Decision): void
}

interface Form {
  title: string
  decision: string
  rationale: string
  category: DecisionCategory
  decidedAt: string | null
  decidedByName: string
  alternatives: string
  privileged: boolean
  reason: string
}

/** "Option — why not" per line <-> alternatives. */
export function parseAlternatives(text: string): DecisionAlternative[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [option, ...rest] = line.split(' — ')
      return { option: option.trim(), reason_not_chosen: rest.join(' — ').trim() || null }
    })
}

export const formatAlternatives = (alts: DecisionAlternative[] | undefined) =>
  (alts ?? []).map((a) => (a.reason_not_chosen ? `${a.option} — ${a.reason_not_chosen}` : a.option)).join('\n')

const fromDecision = (d?: Decision | null): Form => ({
  title: d?.title ?? '',
  decision: d?.decision ?? '',
  rationale: d?.rationale ?? '',
  category: d?.category ?? 'other',
  decidedAt: d?.decided_at ?? null,
  decidedByName: d?.decided_by_name ?? '',
  alternatives: formatAlternatives(d?.alternatives),
  privileged: d?.is_privileged ?? false,
  reason: '',
})

export function DecisionFormDialog({ incidentId, open, onOpenChange, decision, onSaved }: Props) {
  const editing = !!decision
  const canPrivileged = usePermission('decisions:read_privileged')
  const [form, setForm] = useState<Form>(() => fromDecision(decision))
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [lastOpen, setLastOpen] = useState(false)
  if (open !== lastOpen) {
    setLastOpen(open)
    if (open) {
      setForm(fromDecision(decision))
      setError(null)
    }
  }
  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
    setError(null)
  }

  const save = async () => {
    if (!form.title.trim() || !form.decision.trim()) {
      setError('A title and the decision are required.')
      return
    }
    if (editing && !form.reason.trim()) {
      setError('Say why the decision is being revised.')
      return
    }
    const input: DecisionInput = {
      title: form.title.trim(),
      decision: form.decision.trim(),
      rationale: form.rationale.trim() || null,
      category: form.category,
      alternatives: parseAlternatives(form.alternatives),
    }
    if (form.decidedAt) input.decided_at = form.decidedAt
    if (form.decidedByName.trim()) input.decided_by_name = form.decidedByName.trim()
    if (canPrivileged) input.is_privileged = form.privileged
    setSaving(true)
    try {
      const saved = decision
        ? await decisionLog.updateDecision(incidentId, decision.id, { ...input, reason: form.reason.trim() }, decision.version)
        : await decisionLog.createDecision(incidentId, input)
      onOpenChange(false)
      onSaved?.(saved)
    } catch (err) {
      notifyError(err, editing ? 'revise the decision' : 'record the decision')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{editing ? `Revise ${decision?.display_id}` : 'Record a decision'}</DialogTitle>
          <DialogDescription>
            Who decided what, when and why. Every revision is kept and signed; nothing is ever deleted.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="dec-title">Title</Label>
            <Input id="dec-title" value={form.title} maxLength={300} disabled={saving}
              onChange={(e) => set('title', e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="dec-decision">Decision</Label>
            <Textarea id="dec-decision" rows={3} value={form.decision} disabled={saving}
              onChange={(e) => set('decision', e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="dec-rationale">Rationale</Label>
            <Textarea id="dec-rationale" rows={2} value={form.rationale} disabled={saving}
              onChange={(e) => set('rationale', e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="dec-alternatives">Rejected alternatives (one per line: option — why not)</Label>
            <Textarea id="dec-alternatives" rows={2} value={form.alternatives} disabled={saving}
              onChange={(e) => set('alternatives', e.target.value)} />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="dec-category">Category</Label>
              <select id="dec-category" value={form.category} disabled={saving}
                onChange={(e) => set('category', e.target.value as DecisionCategory)}
                className="h-9 w-full rounded-md border border-white/10 bg-slate-900 px-2 text-sm">
                {DECISION_CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="dec-at">Decided at</Label>
              <DateTimeInput id="dec-at" value={form.decidedAt} step={60} disabled={saving}
                onChange={(iso) => set('decidedAt', iso)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="dec-by">Decided by (if not you)</Label>
              <Input id="dec-by" value={form.decidedByName} maxLength={255} placeholder="e.g. CISO" disabled={saving}
                onChange={(e) => set('decidedByName', e.target.value)} />
            </div>
          </div>
          {canPrivileged && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4 accent-amber-500" checked={form.privileged} disabled={saving}
                onChange={(e) => set('privileged', e.target.checked)} />
              Privileged (legal advice): only visible to holders of decisions:read_privileged, never in reports or AI
            </label>
          )}
          {editing && (
            <div className="space-y-1.5">
              <Label htmlFor="dec-reason">Reason for this revision</Label>
              <Input id="dec-reason" value={form.reason} maxLength={2000} disabled={saving}
                onChange={(e) => set('reason', e.target.value)} />
            </div>
          )}
          {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Cancel</Button>
          <Button onClick={save} disabled={saving}>
            {saving && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {editing ? 'Save revision' : 'Record decision'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
