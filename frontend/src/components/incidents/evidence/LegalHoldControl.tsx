"use client"

/**
 * Legal hold on an evidence item or a stored artifact.
 *
 * Everyone who can read evidence sees the state (own hold, hold until a date,
 * or held through the parent item). Only holders of `artifacts:delete` get the
 * controls to place or release one, matching the API. A hold blocks dispose,
 * void, file deletion and permanent incident deletion, and covers an item's
 * derived items and stored copies.
 *
 *   <LegalHoldControl kind="evidence" incidentId={…} id={item.id} item={item} />
 *   <LegalHoldControl kind="artifact" incidentId={…} id={artifact.id} item={artifact} compact />
 */
import { useState } from 'react'
import { Lock, LockOpen } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
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
import { useConfirm } from '@/components/ui/confirm-dialog'
import { DateTimeInput } from '@/components/ui/datetime-input'
import { Textarea } from '@/components/ui/input'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermissionIgnoringReadOnly } from '@/components/auth/permission-gate'
import { evidenceApi, evidenceBase, evidenceFilesApi } from '@/lib/endpoints/evidence'
import { notifyError, notifySuccess } from '@/lib/errors'
import { invalidate } from '@/lib/query-cache'
import { cn } from '@/lib/utils'
import { reportEvidenceError } from './evidence-errors'
import { Field, FormError } from './form-parts'

export interface HoldState {
  is_locked?: boolean | null
  legal_hold_until?: string | null
  /** Own hold or one inherited from the parent item. */
  under_legal_hold?: boolean
}

export const HOLD_PERMISSION = 'artifacts:delete'

export type HoldKind = 'indefinite' | 'until' | 'inherited' | 'none'

/** What kind of hold the row is under. `now` is injectable for tests. */
export function holdKind(s: HoldState, now = Date.now()): HoldKind {
  if (s.is_locked) return 'indefinite'
  if (s.legal_hold_until && new Date(s.legal_hold_until).getTime() > now) return 'until'
  return s.under_legal_hold ? 'inherited' : 'none'
}

export interface LegalHoldControlProps {
  kind: 'evidence' | 'artifact'
  incidentId: string
  id: string
  item: HoldState
  /** Label used in messages, e.g. `EV-0003` or the file name. */
  label?: string
  /** Badge and a single icon button only (table cells). */
  compact?: boolean
  onChanged?: () => void
  className?: string
}

export function LegalHoldControl({ kind, incidentId, id, item, label, compact, onChanged, className }: LegalHoldControlProps) {
  // Holds stay manageable on archived (read-only) incidents: a hold must be
  // released before an archived incident can be purged.
  const canManage = usePermissionIgnoringReadOnly(HOLD_PERMISSION)
  const confirm = useConfirm()
  const [placing, setPlacing] = useState(false)
  const [busy, setBusy] = useState(false)
  const state = holdKind(item)
  const own = state === 'indefinite' || state === 'until'
  const name = label ?? (kind === 'evidence' ? 'this item' : 'this file')

  const send = async (data: { hold: boolean; until?: string | null; reason?: string | null }) => {
    if (kind === 'evidence') await evidenceApi.legalHold(incidentId, id, data)
    else await evidenceFilesApi.artifactHold(incidentId, id, data)
    invalidate(evidenceBase(incidentId))
    invalidate(`/incidents/${incidentId}/artifacts`)
    onChanged?.()
  }

  const release = async () => {
    const ok = await confirm({
      title: 'Release legal hold?',
      description: `${name[0].toUpperCase()}${name.slice(1)} can be disposed of${kind === 'artifact' ? ' or deleted' : ', voided'} again, and the incident can be permanently deleted. The release is written to the custody ledger.`,
      confirmLabel: 'Release hold',
    })
    if (!ok) return
    setBusy(true)
    try {
      await send({ hold: false })
      notifySuccess('Legal hold released')
    } catch (e) {
      notifyError(e, 'release the legal hold')
    } finally {
      setBusy(false)
    }
  }

  const badge =
    state === 'none' ? (
      <Badge variant="default" className="gap-1">
        <LockOpen className="h-3 w-3" aria-hidden />
        No hold
      </Badge>
    ) : (
      <Badge variant="warning" className="gap-1" data-hold={state}>
        <Lock className="h-3 w-3" aria-hidden />
        {state === 'indefinite' && 'Legal hold'}
        {state === 'until' && (
          <>
            Hold until <Timestamp value={item.legal_hold_until} seconds={false} />
          </>
        )}
        {state === 'inherited' && 'Held via parent item'}
      </Badge>
    )

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      {badge}
      {canManage && own && (
        <Button variant="outline" size="sm" onClick={() => void release()} loading={busy} aria-label={`Release legal hold on ${name}`}>
          {compact ? <LockOpen className="h-4 w-4" /> : 'Release hold'}
        </Button>
      )}
      {canManage && state !== 'indefinite' && state !== 'until' && (
        <Button variant="outline" size="sm" onClick={() => setPlacing(true)} aria-label={`Place legal hold on ${name}`}>
          {compact ? <Lock className="h-4 w-4" /> : 'Place hold…'}
        </Button>
      )}
      {canManage && state === 'until' && !compact && (
        <Button variant="ghost" size="sm" onClick={() => setPlacing(true)} aria-label={`Change legal hold on ${name}`}>
          Change…
        </Button>
      )}
      <Dialog open={placing} onOpenChange={setPlacing}>
        {placing && (
          <PlaceHoldForm
            name={name}
            onCancel={() => setPlacing(false)}
            onSubmit={async (data) => {
              await send({ hold: true, ...data })
              notifySuccess('Legal hold placed')
              setPlacing(false)
            }}
          />
        )}
      </Dialog>
    </div>
  )
}

function PlaceHoldForm({
  name,
  onCancel,
  onSubmit,
}: {
  name: string
  onCancel: () => void
  onSubmit: (data: { until?: string | null; reason?: string | null }) => Promise<void>
}) {
  const [timed, setTimed] = useState(false)
  const [until, setUntil] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [untilError, setUntilError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const submit = async () => {
    setServerError(null)
    const problem = !timed
      ? null
      : !until
        ? 'Choose when the hold ends'
        : new Date(until).getTime() <= Date.now()
          ? 'The end must be in the future'
          : null
    setUntilError(problem)
    if (problem) return
    setBusy(true)
    try {
      await onSubmit({ until: timed ? until : undefined, reason: reason.trim() || undefined })
    } catch (e) {
      reportEvidenceError(e, 'place the legal hold', setServerError)
    } finally {
      setBusy(false)
    }
  }

  return (
    <DialogContent className="max-w-md">
      <DialogHeader>
        <DialogTitle>Place legal hold</DialogTitle>
        <DialogDescription>
          While held, {name} cannot be disposed of, voided or deleted, and the incident cannot be permanently deleted.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="space-y-4 px-1">
        <div role="radiogroup" aria-label="Hold duration" className="space-y-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="hold-kind" checked={!timed} onChange={() => setTimed(false)} />
            Until released
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="hold-kind" checked={timed} onChange={() => setTimed(true)} />
            Until a date
          </label>
        </div>
        {timed && (
          <Field label="Hold ends" required error={untilError}>
            {({ id, describedBy, invalid }) => (
              <DateTimeInput id={id} aria-describedby={describedBy} aria-invalid={invalid || undefined} value={until} onChange={(iso) => { setUntil(iso); setUntilError(null) }} />
            )}
          </Field>
        )}
        <Field label="Reason" hint="Optional, e.g. the matter or case number that requires preservation.">
          {({ id, describedBy }) => (
            <Textarea id={id} aria-describedby={describedBy} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={20000} />
          )}
        </Field>
        <FormError message={serverError} />
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        <Button onClick={() => void submit()} loading={busy}>
          Place hold
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
