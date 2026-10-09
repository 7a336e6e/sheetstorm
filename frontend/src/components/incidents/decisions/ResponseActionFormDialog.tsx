"use client"

/**
 * Plan (or retroactively record) a response action (W4-DEC), or revise its
 * descriptive fields. The target is picked from this incident's hosts,
 * accounts, IOCs or malware; the server snapshots its label. Target-state
 * changes happen only on execute (transition dialog), never here.
 */
import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
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
import api, { isAbortError, withQuery } from '@/lib/api'
import { decisionLog } from '@/lib/endpoints/decisions'
import { notifyError } from '@/lib/errors'
import type { Decision, ResponseAction, ResponseActionType, ResponseTargetType } from '@/types'
import { ACTION_TYPES, TARGET_TYPES, label } from './decision-helpers'

/** Where each target type's options come from and how they are labelled. */
export const TARGET_SOURCES: Partial<Record<ResponseTargetType, { path: string; label: (r: Record<string, unknown>) => string }>> = {
  host: { path: 'hosts', label: (r) => String(r.hostname ?? r.id) },
  account: { path: 'accounts', label: (r) => String(r.account_name ?? r.id) },
  network_ioc: { path: 'network-iocs', label: (r) => String(r.dns_ip ?? r.id) },
  host_ioc: { path: 'host-iocs', label: (r) => String(r.artifact_value ?? r.id) },
  malware: { path: 'malware', label: (r) => String(r.file_name ?? r.id) },
}

/** Default target type for an action type. */
export function defaultTargetType(t: ResponseActionType): ResponseTargetType {
  if (t.endsWith('_host')) return 'host'
  if (['disable_account', 'reset_credentials', 'revoke_sessions', 'delete_account'].includes(t)) return 'account'
  if (t === 'block_ioc' || t === 'sinkhole_domain') return 'network_ioc'
  if (t === 'quarantine_file') return 'malware'
  if (t === 'notify_party') return 'external'
  return 'none'
}

function useTargetOptions(incidentId: string, type: ResponseTargetType, enabled: boolean) {
  const [items, setItems] = useState<{ id: string; label: string }[]>([])
  const source = TARGET_SOURCES[type]
  useEffect(() => {
    if (!enabled || !source) return
    const controller = new AbortController()
    api
      .get<{ items: Record<string, unknown>[] }>(withQuery(`/incidents/${incidentId}/${source.path}`, { per_page: 200 }), {
        signal: controller.signal,
      })
      .then((res) => setItems((res.items ?? []).map((r) => ({ id: String(r.id), label: source.label(r) }))))
      .catch((err: unknown) => {
        if (!isAbortError(err)) setItems([])
      })
    return () => controller.abort()
  }, [incidentId, source, enabled])
  return source ? items : []
}

interface Props {
  incidentId: string
  open: boolean
  onOpenChange(open: boolean): void
  /** The action being revised (descriptive fields only); null plans a new one. */
  action?: ResponseAction | null
  decisions?: Decision[]
  onSaved?(a: ResponseAction): void
}

interface Form {
  actionType: ResponseActionType
  title: string
  description: string
  targetType: ResponseTargetType
  targetId: string
  targetLabel: string
  decisionId: string
  rollbackPlan: string
  reason: string
}

const fromAction = (a?: ResponseAction | null): Form => ({
  actionType: a?.action_type ?? 'isolate_host',
  title: a?.title ?? '',
  description: a?.description ?? '',
  targetType: a?.target_type ?? 'host',
  targetId: a?.target_id ?? '',
  targetLabel: a?.target_label ?? '',
  decisionId: a?.decision_id ?? '',
  rollbackPlan: a?.rollback_plan ?? '',
  reason: '',
})

const selectClass = 'h-9 w-full rounded-md border border-white/10 bg-slate-900 px-2 text-sm'

export function ResponseActionFormDialog({ incidentId, open, onOpenChange, action, decisions = [], onSaved }: Props) {
  const editing = !!action
  const [form, setForm] = useState<Form>(() => fromAction(action))
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [lastOpen, setLastOpen] = useState(false)
  if (open !== lastOpen) {
    setLastOpen(open)
    if (open) {
      setForm(fromAction(action))
      setError(null)
    }
  }
  const targets = useTargetOptions(incidentId, form.targetType, open && !editing)
  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
    setError(null)
  }
  const typed = !!TARGET_SOURCES[form.targetType]

  const save = async () => {
    if (!form.title.trim()) {
      setError('A title is required.')
      return
    }
    if (!editing && typed && !form.targetId) {
      setError(`Choose the ${label(form.targetType).toLowerCase()} this action targets.`)
      return
    }
    if (editing && !form.reason.trim()) {
      setError('Say why the action is being revised.')
      return
    }
    setSaving(true)
    try {
      let saved: ResponseAction
      if (action) {
        saved = await decisionLog.updateAction(incidentId, action.id, {
          title: form.title.trim(),
          description: form.description.trim() || null,
          rollback_plan: form.rollbackPlan.trim() || null,
          // Only a changed link is sent: a link to a decision this user may not
          // see (decision_restricted) must survive their edit.
          ...(!action.decision_restricted && form.decisionId !== (action.decision_id ?? '')
            ? { decision_id: form.decisionId || null }
            : {}),
          ...(typed ? {} : { target_label: form.targetLabel.trim() || null }),
          reason: form.reason.trim(),
        }, action.version)
      } else {
        saved = await decisionLog.createAction(incidentId, {
          action_type: form.actionType,
          title: form.title.trim(),
          description: form.description.trim() || null,
          target_type: form.targetType,
          target_id: typed ? form.targetId : null,
          target_label: typed ? null : form.targetLabel.trim() || null,
          decision_id: form.decisionId || null,
          rollback_plan: form.rollbackPlan.trim() || null,
        })
      }
      onOpenChange(false)
      onSaved?.(saved)
    } catch (err) {
      notifyError(err, editing ? 'revise the response action' : 'record the response action')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{editing ? `Revise ${action?.display_id}` : 'Plan a response action'}</DialogTitle>
          <DialogDescription>
            Actions move through requested → authorized → executed → verified; each step is signed and kept.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {!editing && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="ra-type">Action</Label>
                <select id="ra-type" className={selectClass} value={form.actionType} disabled={saving}
                  onChange={(e) => {
                    const t = e.target.value as ResponseActionType
                    setForm((f) => ({ ...f, actionType: t, targetType: defaultTargetType(t), targetId: '' }))
                  }}>
                  {ACTION_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ra-target-type">Target type</Label>
                <select id="ra-target-type" className={selectClass} value={form.targetType} disabled={saving}
                  onChange={(e) => setForm((f) => ({ ...f, targetType: e.target.value as ResponseTargetType, targetId: '' }))}>
                  {TARGET_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
                </select>
              </div>
            </div>
          )}
          {!editing && typed && (
            <div className="space-y-1.5">
              <Label htmlFor="ra-target">Target</Label>
              <select id="ra-target" className={selectClass} value={form.targetId} disabled={saving}
                onChange={(e) => set('targetId', e.target.value)}>
                <option value="">Choose…</option>
                {targets.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
              </select>
            </div>
          )}
          {!typed && form.targetType === 'external' && (
            <div className="space-y-1.5">
              <Label htmlFor="ra-target-label">Party / external target</Label>
              <Input id="ra-target-label" value={form.targetLabel} maxLength={500} placeholder="e.g. Data protection authority"
                disabled={saving} onChange={(e) => set('targetLabel', e.target.value)} />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="ra-title">Title</Label>
            <Input id="ra-title" value={form.title} maxLength={300} disabled={saving}
              onChange={(e) => set('title', e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ra-description">Description</Label>
            <Textarea id="ra-description" rows={2} value={form.description} disabled={saving}
              onChange={(e) => set('description', e.target.value)} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="ra-decision">Implements decision</Label>
              <select id="ra-decision" className={selectClass} value={form.decisionId}
                disabled={saving || !!action?.decision_restricted}
                onChange={(e) => set('decisionId', e.target.value)}>
                <option value="">None</option>
                {decisions.map((d) => <option key={d.id} value={d.id}>{d.display_id} · {d.title}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ra-rollback">Rollback plan</Label>
              <Input id="ra-rollback" value={form.rollbackPlan} disabled={saving}
                onChange={(e) => set('rollbackPlan', e.target.value)} />
            </div>
          </div>
          {editing && (
            <div className="space-y-1.5">
              <Label htmlFor="ra-reason">Reason for this revision</Label>
              <Input id="ra-reason" value={form.reason} maxLength={2000} disabled={saving}
                onChange={(e) => set('reason', e.target.value)} />
            </div>
          )}
          {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Cancel</Button>
          <Button onClick={save} disabled={saving}>
            {saving && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {editing ? 'Save revision' : 'Record action'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
