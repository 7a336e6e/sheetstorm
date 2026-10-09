"use client"

/**
 * IR milestone strip (W2-DFIR-B, C20): First activity (timeline) → First
 * malicious → Detected → Responded → Contained → Eradicated → Recovered →
 * Closed, each with its timestamp and the raw delta from the previous set
 * step ("Dwell" for the step into Detected). Durations and anomalies live in
 * the metrics card (IncidentMetricsCard, which can open this editor through
 * `EDIT_LIFECYCLE_EVENT`). `first_malicious_at` and `responded_at` are the
 * W3-RT-POST additions; there is no separate modal for them.
 *
 * Edit (gated on `incidents:update`) PUTs the changed milestones with
 * If-Match. Order / future problems are caught client-side and the server's
 * 400 `invalid_milestones` is shown inline too.
 */
import { useEffect, useState } from 'react'
import { AlertTriangle, Edit2, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { DateTimeInput } from '@/components/ui/datetime-input'
import { Label } from '@/components/ui/label'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermission } from '@/components/auth/permission-gate'
import { isApiError } from '@/lib/api'
import { notifyError } from '@/lib/errors'
import { formatDuration } from '@/lib/time'
import {
  MILESTONES,
  changedMilestones,
  milestoneSteps,
  validateMilestones,
  type MilestoneValues,
} from '@/lib/milestones'
import { incidentOverview } from '@/lib/endpoints/incident-overview'
import type { Incident, MilestoneField, Versioned } from '@/types'

/** `window` event the metrics card dispatches to open the milestone editor. */
export const EDIT_LIFECYCLE_EVENT = 'sheetstorm:edit-lifecycle'

interface IRMilestoneStripProps {
  incident: Incident & Versioned
  /** `summary.first_event_at`: earliest timeline event (null when unknown). */
  firstActivity?: string | null
  /** The incident changed on the server: refetch it. */
  onSaved: () => void
}

const pick = (incident: Incident): MilestoneValues =>
  Object.fromEntries(MILESTONES.map(({ field }) => [field, incident[field] ?? null]))

/** Server 400 `invalid_milestones` → readable text (labels, not field names). */
function serverMessage(err: unknown): string | null {
  if (!isApiError(err) || err.status !== 400) return null
  const pair = err.details?.pair
  if (err.code === 'invalid_milestones' && Array.isArray(pair) && pair.length === 2) {
    const label = (f: unknown) => MILESTONES.find((m) => m.field === f)?.label ?? String(f)
    return `${label(pair[0])} must not be after ${label(pair[1])}.`
  }
  return err.message
}

export function IRMilestoneStrip({ incident, firstActivity, onSaved }: IRMilestoneStripProps) {
  const canEdit = usePermission('incidents:update')
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<MilestoneValues>({})
  const [error, setError] = useState<{ field?: MilestoneField; message: string } | null>(null)
  const [saving, setSaving] = useState(false)

  const original = pick(incident)
  const steps = milestoneSteps(firstActivity, original)

  const startEdit = () => {
    setDraft(original)
    setError(null)
    setOpen(true)
  }

  // "Edit lifecycle times" in the metrics card.
  useEffect(() => {
    if (!canEdit) return
    const handler = () => {
      setDraft(pick(incident))
      setError(null)
      setOpen(true)
    }
    window.addEventListener(EDIT_LIFECYCLE_EVENT, handler)
    return () => window.removeEventListener(EDIT_LIFECYCLE_EVENT, handler)
  }, [canEdit, incident])

  const save = async () => {
    const issue = validateMilestones(draft, original)
    if (issue) {
      setError(issue)
      return
    }
    const changes = changedMilestones(draft, original)
    if (Object.keys(changes).length === 0) {
      setOpen(false)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await incidentOverview.update(incident.id, changes, incident.version)
      setOpen(false)
      onSaved()
    } catch (err) {
      const inline = serverMessage(err)
      if (inline) {
        const field = isApiError(err) ? (err.details?.field as MilestoneField | undefined) : undefined
        setError({ field, message: inline })
      } else {
        notifyError(err, 'save the milestones')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg">IR Milestones</CardTitle>
        {canEdit && (
          <Button variant="ghost" size="sm" onClick={startEdit} aria-label="Edit milestones">
            <Edit2 className="mr-1 h-3.5 w-3.5" /> Edit
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <ol className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8" aria-label="IR milestones">
          {steps.map((step) => {
            const negative = step.deltaMs !== null && step.deltaMs < 0
            return (
              <li
                key={step.key}
                data-testid={`milestone-${step.key}`}
                className="rounded-lg border border-border bg-muted/50 px-3 py-2"
              >
                <div className="text-xs text-muted-foreground">{step.label}</div>
                <div className="mt-1 text-xs font-medium text-foreground">
                  <Timestamp value={step.value} seconds={false} />
                </div>
                {step.deltaMs !== null && (
                  <div
                    className={`mt-1 flex items-center gap-1 text-[11px] ${negative ? 'text-amber-400' : 'text-muted-foreground'}`}
                    title={negative ? 'Earlier than the previous milestone (legacy data)' : undefined}
                  >
                    {negative && <AlertTriangle className="h-3 w-3" aria-label="out of order" />}
                    {step.deltaLabel ? `${step.deltaLabel} ` : '+'}
                    {formatDuration(step.deltaMs)}
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      </CardContent>

      <Dialog open={open} onOpenChange={(next) => !saving && setOpen(next)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit IR milestones</DialogTitle>
            <DialogDescription>
              Milestones must be in order and not in the future. Clear a field to unset it.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            {MILESTONES.map(({ field, label }) => (
              <div key={field} className="space-y-1.5">
                <Label htmlFor={`milestone-${field}`}>{label}</Label>
                <DateTimeInput
                  id={`milestone-${field}`}
                  value={draft[field] ?? null}
                  onChange={(iso) => {
                    setDraft((d) => ({ ...d, [field]: iso }))
                    setError(null)
                  }}
                  disabled={saving}
                  aria-invalid={error?.field === field || undefined}
                />
              </div>
            ))}
            {error && (
              <p role="alert" className="text-sm text-red-400">
                {error.message}
              </p>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={() => void save()} disabled={saving}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save milestones
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
