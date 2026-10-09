"use client"

/**
 * One dialog for every decision / response-action transition (W4-DEC).
 * Fields depend on the event; the version travels as `expected_version`.
 * In-app approval/authorization is offered only with `decisions:approve` /
 * `response_actions:authorize`; otherwise (or by choice) an external
 * approver/authorizer is recorded by name. The target-state checkbox on
 * execute needs `hosts:update` / `accounts:update`.
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
import { usePermissionCheck } from '@/components/auth/permission-gate'
import { decisionLog } from '@/lib/endpoints/decisions'
import { notifyError } from '@/lib/errors'
import type { Decision, DecisionEvent, ResponseAction, ResponseActionEvent } from '@/types'
import { TARGET_STATE_ACTIONS, label, reasonRequired } from './decision-helpers'

export type TransitionTarget =
  | { kind: 'decision'; record: Decision; event: DecisionEvent }
  | { kind: 'action'; record: ResponseAction; event: ResponseActionEvent }

interface Props {
  incidentId: string
  target: TransitionTarget | null
  /** Other decisions of the incident (supersede picker). */
  decisions?: Decision[]
  onOpenChange(open: boolean): void
  onDone?(): void
}

const HOST_STATES = ['active', 'compromised', 'isolated', 'contained', 'reimaged', 'cleaned', 'decommissioned']

export interface TransitionForm {
  reason: string
  external: boolean
  name: string
  at: string | null
  supersededBy: string
  applyState: boolean
  targetState: string
  result: string
  method: string
  notes: string
  restore: boolean
}

export const blankTransitionForm = (t: TransitionTarget | null): TransitionForm => ({
  reason: '',
  external: false,
  name: '',
  at: null,
  supersededBy: '',
  applyState: false,
  targetState: '',
  result: 'success',
  method: '',
  notes: '',
  restore: t?.kind === 'action' ? !!t.record.target_state_after : false,
})

/** The request body for an event, or an error message. */
export function transitionBody(t: TransitionTarget, f: TransitionForm): { body: Record<string, unknown> } | { error: string } {
  const body: Record<string, unknown> = {}
  const reason = f.reason.trim()
  if (reasonRequired(t.event, t.record.status) && !reason) return { error: 'A reason is required.' }
  if (reason) body.reason = reason
  const name = f.name.trim()
  if (t.event === 'approve' || t.event === 'authorize') {
    if (f.external) {
      if (!name) return { error: 'Enter who gave the approval.' }
      body[t.event === 'approve' ? 'approved_by_name' : 'authorized_by_name'] = name
      if (f.at) body[t.event === 'approve' ? 'approved_at' : 'authorized_at'] = f.at
    }
  } else if (t.event === 'supersede') {
    if (!f.supersededBy) return { error: 'Choose the decision that replaces this one.' }
    body.superseded_by_id = f.supersededBy
  } else if (t.event === 'execute') {
    if (f.at) body.executed_at = f.at
    if (name) body.executed_by_name = name
    if (f.applyState) {
      body.apply_target_state = true
      if (f.targetState) body.target_state = f.targetState
    }
  } else if (t.event === 'verify') {
    if (!f.method.trim()) return { error: 'Describe how the action was verified.' }
    body.verification_result = f.result
    body.verification_method = f.method.trim()
    if (f.notes.trim()) body.verification_notes = f.notes.trim()
    if (f.at) body.verified_at = f.at
    if (name) body.verified_by_name = name
  } else if (t.event === 'rollback') {
    body.restore_target_state = f.restore
  }
  return { body }
}

const TITLES: Record<DecisionEvent | ResponseActionEvent, string> = {
  approve: 'Approve decision',
  reject: 'Reject decision',
  reopen: 'Reopen decision',
  supersede: 'Supersede decision',
  authorize: 'Authorize action',
  start: 'Start action',
  execute: 'Record execution',
  fail: 'Mark action failed',
  verify: 'Record verification',
  rollback: 'Roll back action',
  cancel: 'Cancel action',
}

const check = 'h-4 w-4 rounded border-white/20 bg-slate-900 accent-sky-500'

export function TransitionDialog({ incidentId, target, decisions = [], onOpenChange, onDone }: Props) {
  const can = usePermissionCheck()
  const [form, setForm] = useState<TransitionForm>(() => blankTransitionForm(target))
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [lastTarget, setLastTarget] = useState<TransitionTarget | null>(null)
  if (target !== lastTarget) {
    setLastTarget(target)
    const fresh = blankTransitionForm(target)
    // Without the in-app permission only an external attestation is possible.
    if (target?.event === 'approve') fresh.external = !can('decisions:approve')
    if (target?.event === 'authorize') fresh.external = !can('response_actions:authorize')
    setForm(fresh)
    setError(null)
  }
  if (!target) return null
  const { event } = target
  const set = <K extends keyof TransitionForm>(key: K, value: TransitionForm[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
    setError(null)
  }
  const stateTarget = target.kind === 'action' ? TARGET_STATE_ACTIONS[target.record.action_type] : undefined
  const canApplyState =
    target.kind === 'action' &&
    !!stateTarget &&
    target.record.target_type === stateTarget &&
    !!target.record.target_id &&
    can(stateTarget === 'host' ? 'hosts:update' : 'accounts:update')
  const inAppPerm = event === 'approve' ? 'decisions:approve' : 'response_actions:authorize'
  const showReason = event !== 'verify' && event !== 'execute'

  const submit = async () => {
    const built = transitionBody(target, form)
    if ('error' in built) {
      setError(built.error)
      return
    }
    setSaving(true)
    try {
      if (target.kind === 'decision') {
        await decisionLog.transitionDecision(incidentId, target.record.id, target.event, built.body, target.record.version)
      } else {
        await decisionLog.transitionAction(incidentId, target.record.id, target.event, built.body, target.record.version)
      }
      onOpenChange(false)
      onDone?.()
    } catch (err) {
      notifyError(err, TITLES[event].toLowerCase())
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{TITLES[event]}</DialogTitle>
          <DialogDescription>
            {target.record.display_id} · {target.record.title}. Every change is kept as a signed revision.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {(event === 'approve' || event === 'authorize') && (
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className={check}
                  checked={form.external}
                  disabled={saving || !can(inAppPerm)}
                  onChange={(e) => set('external', e.target.checked)}
                />
                Record an approval given outside SheetStorm
              </label>
              {!form.external && <p className="text-xs text-muted-foreground">Recorded as approved by you, now.</p>}
              {form.external && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="tr-name">{event === 'approve' ? 'Approved by' : 'Authorized by'}</Label>
                    <Input id="tr-name" value={form.name} maxLength={255} placeholder="e.g. General Counsel"
                      onChange={(e) => set('name', e.target.value)} disabled={saving} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="tr-at">When</Label>
                    <DateTimeInput id="tr-at" value={form.at} step={60} onChange={(iso) => set('at', iso)} disabled={saving} />
                  </div>
                </div>
              )}
            </div>
          )}
          {event === 'supersede' && (
            <div className="space-y-1.5">
              <Label htmlFor="tr-superseded-by">Replaced by</Label>
              <select id="tr-superseded-by" value={form.supersededBy} disabled={saving}
                onChange={(e) => set('supersededBy', e.target.value)}
                className="h-9 w-full rounded-md border border-white/10 bg-slate-900 px-2 text-sm">
                <option value="">Choose a decision…</option>
                {decisions.filter((d) => d.id !== target.record.id).map((d) => (
                  <option key={d.id} value={d.id}>{d.display_id} · {d.title}</option>
                ))}
              </select>
            </div>
          )}
          {(event === 'execute' || event === 'verify') && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="tr-at">{event === 'execute' ? 'Executed at' : 'Verified at'}</Label>
                <DateTimeInput id="tr-at" value={form.at} step={60} onChange={(iso) => set('at', iso)} disabled={saving} />
                <p className="text-xs text-muted-foreground">Leave empty for now.</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tr-name">{event === 'execute' ? 'Executed by (if not you)' : 'Verified by (if not you)'}</Label>
                <Input id="tr-name" value={form.name} maxLength={255} placeholder="e.g. MSSP on-call"
                  onChange={(e) => set('name', e.target.value)} disabled={saving} />
              </div>
            </div>
          )}
          {event === 'execute' && stateTarget && (
            <div className="space-y-2 rounded-md border border-white/10 p-3">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className={check} checked={form.applyState} disabled={saving || !canApplyState}
                  onChange={(e) => set('applyState', e.target.checked)} />
                Also update the {stateTarget}&apos;s state ({label(target.kind === 'action' ? target.record.target_label : '')})
              </label>
              {!canApplyState && (
                <p className="text-xs text-muted-foreground">
                  Needs {stateTarget === 'host' ? 'hosts:update' : 'accounts:update'} and a {stateTarget} target.
                </p>
              )}
              {form.applyState && target.kind === 'action' && target.record.action_type === 'release_host' && (
                <select aria-label="New host state" value={form.targetState} disabled={saving}
                  onChange={(e) => set('targetState', e.target.value)}
                  className="h-9 w-full rounded-md border border-white/10 bg-slate-900 px-2 text-sm">
                  <option value="">Choose the new state…</option>
                  {HOST_STATES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
                </select>
              )}
            </div>
          )}
          {event === 'verify' && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="tr-result">Result</Label>
                <select id="tr-result" value={form.result} disabled={saving} onChange={(e) => set('result', e.target.value)}
                  className="h-9 w-full rounded-md border border-white/10 bg-slate-900 px-2 text-sm">
                  {['success', 'partial', 'failed'].map((r) => <option key={r} value={r}>{label(r)}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tr-method">Method</Label>
                <Input id="tr-method" value={form.method} maxLength={255} placeholder="e.g. EDR console shows isolated"
                  onChange={(e) => set('method', e.target.value)} disabled={saving} />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="tr-notes">Notes</Label>
                <Textarea id="tr-notes" rows={2} value={form.notes} onChange={(e) => set('notes', e.target.value)} disabled={saving} />
              </div>
            </div>
          )}
          {event === 'rollback' && target.kind === 'action' && target.record.target_state_after && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className={check} checked={form.restore} disabled={saving}
                onChange={(e) => set('restore', e.target.checked)} />
              Restore the target to {label(String(target.record.target_state_before?.value ?? ''))}
            </label>
          )}
          {showReason && (
            <div className="space-y-1.5">
              <Label htmlFor="tr-reason">
                Reason{reasonRequired(event, target.record.status) ? '' : ' (optional)'}
              </Label>
              <Textarea id="tr-reason" rows={2} value={form.reason} maxLength={2000}
                onChange={(e) => set('reason', e.target.value)} disabled={saving} />
            </div>
          )}
          {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Cancel</Button>
          <Button onClick={submit} disabled={saving}>
            {saving && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {TITLES[event]}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
