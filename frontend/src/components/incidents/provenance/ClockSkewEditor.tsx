"use client"

import { useId, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Timestamp } from '@/components/ui/timestamp'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { provenanceApi } from '@/lib/endpoints/provenance'
import { notifyError, notifySuccess } from '@/lib/errors'
import type { ClockSkewReapplyResult, CompromisedHost } from '@/types'
import {
  CLOCK_SKEW_LIMIT_SECONDS,
  COMMON_TIMEZONES,
  formatSkew,
  skewFromParts,
  skewToParts,
} from './provenance-form'

type HostRow = CompromisedHost & { version?: number }

export interface ClockSkewEditorProps {
  incidentId: string
  host: HostRow
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called after a save or an applied re-normalization (refresh the lists). */
  onSaved: () => void
}

const PREVIEW_ROWS = 8

/**
 * Per-host clock skew (host clock minus true UTC) with its basis and the
 * host's configured time zone. Saving never changes existing records: they
 * keep the skew they snapshotted. "Re-normalize" previews (dry run) and then
 * applies the difference to this host's records that were computed from a raw
 * timestamp; manual and imported records are left alone.
 */
export function ClockSkewEditor({ incidentId, host, open, onOpenChange, onSaved }: ClockSkewEditorProps) {
  const initial = skewToParts(host.clock_skew_seconds)
  const [sign, setSign] = useState<1 | -1>(initial.sign)
  const [hours, setHours] = useState(initial.hours)
  const [minutes, setMinutes] = useState(initial.minutes)
  const [seconds, setSeconds] = useState(initial.seconds)
  const [basis, setBasis] = useState(host.clock_skew_basis ?? '')
  const [timezone, setTimezone] = useState(host.timezone ?? '')
  const [saving, setSaving] = useState(false)
  // The version moves with every save; the re-normalize call needs the latest.
  const [version, setVersion] = useState(host.version)
  const [saved, setSaved] = useState(host.clock_skew_seconds ?? null)
  const [plan, setPlan] = useState<ClockSkewReapplyResult | null>(null)
  const [busy, setBusy] = useState<'preview' | 'apply' | null>(null)
  const ids = useId()
  const datalistId = useId()

  const total = skewFromParts(sign, hours, minutes, seconds)
  const invalid = Number.isNaN(total) || Math.abs(total) > CLOCK_SKEW_LIMIT_SECONDS
  const basisMissing = !invalid && total !== 0 && basis.trim() === ''

  const save = async () => {
    if (invalid || basisMissing) return
    setSaving(true)
    try {
      const updated = await provenanceApi.setClockSkew(
        incidentId,
        host.id,
        {
          clock_skew_seconds: total,
          clock_skew_basis: basis.trim() || null,
          timezone: timezone.trim() || null,
        },
        version,
      )
      setVersion((updated as HostRow).version)
      setSaved(updated.clock_skew_seconds ?? null)
      setPlan(null)
      notifySuccess('Clock skew saved', 'Existing records keep the skew they were computed with.')
      onSaved()
    } catch (err) {
      notifyError(err, 'save the clock skew')
    } finally {
      setSaving(false)
    }
  }

  const preview = async () => {
    setBusy('preview')
    try {
      setPlan(await provenanceApi.reapplyClockSkew(incidentId, host.id, true))
    } catch (err) {
      notifyError(err, 'preview the re-normalization')
    } finally {
      setBusy(null)
    }
  }

  const apply = async () => {
    setBusy('apply')
    try {
      const res = await provenanceApi.reapplyClockSkew(incidentId, host.id, false, version)
      notifySuccess(`Re-normalized ${res.count} record${res.count === 1 ? '' : 's'}`)
      setPlan(null)
      onSaved()
    } catch (err) {
      notifyError(err, 're-normalize the records')
    } finally {
      setBusy(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Clock skew: {host.hostname}</DialogTitle>
          <DialogDescription>
            Host clock minus true UTC. Positive means the host clock runs ahead; its timestamps are corrected by
            subtracting the skew.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Offset</legend>
            <div className="grid grid-cols-[8rem_1fr_1fr_1fr] items-end gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Direction</Label>
                <Select value={String(sign)} onValueChange={(v) => setSign(v === '-1' ? -1 : 1)}>
                  <SelectTrigger aria-label="Direction"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">Host ahead (+)</SelectItem>
                    <SelectItem value="-1">Host behind (−)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {([
                ['Hours', hours, setHours],
                ['Minutes', minutes, setMinutes],
                ['Seconds', seconds, setSeconds],
              ] as const).map(([label, val, setVal]) => (
                <div key={label} className="space-y-1">
                  <Label className="text-xs" htmlFor={`${ids}-${label}`}>{label}</Label>
                  <Input
                    id={`${ids}-${label}`}
                    type="number"
                    min={0}
                    step={1}
                    inputMode="numeric"
                    value={val}
                    onChange={(e) => setVal(e.target.value)}
                  />
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {invalid
                ? `Enter whole numbers; at most ±${CLOCK_SKEW_LIMIT_SECONDS} seconds (7 days).`
                : `Skew: ${formatSkew(total) || '0s'} (${total} seconds)`}
            </p>
          </fieldset>

          <div className="space-y-2">
            <Label htmlFor={`${ids}-basis`}>Basis {total !== 0 && '*'}</Label>
            <Textarea
              id={`${ids}-basis`}
              value={basis}
              maxLength={2000}
              onChange={(e) => setBasis(e.target.value)}
              placeholder="How it was measured, e.g. compared the host clock with the domain controller at triage"
            />
            {basisMissing && <p className="text-xs text-amber-500">A non-zero skew needs a basis.</p>}
          </div>

          <div className="space-y-2">
            <Label htmlFor={`${ids}-tz`}>Host time zone</Label>
            <Input
              id={`${ids}-tz`}
              value={timezone}
              maxLength={64}
              list={datalistId}
              onChange={(e) => setTimezone(e.target.value)}
              placeholder="Europe/Berlin or UTC+05:30"
            />
            <datalist id={datalistId}>
              {COMMON_TIMEZONES.map((tz) => <option key={tz} value={tz} />)}
            </datalist>
            <p className="text-xs text-muted-foreground">Default for this host&apos;s raw timestamps that carry no offset.</p>
          </div>

          <section className="space-y-2 rounded-md border border-white/10 p-3" aria-label="Re-normalize records">
            <h4 className="text-sm font-medium">Re-normalize records</h4>
            <p className="text-xs text-muted-foreground">
              Records computed from a raw timestamp under a different skew
              {saved !== null ? ` than ${formatSkew(saved) || '0s'}` : ''} can be re-derived. Manual and imported records are not touched.
              Save the skew first.
            </p>
            <Button type="button" size="sm" variant="outline" onClick={preview} loading={busy === 'preview'}>
              Preview changes
            </Button>
            {plan && (
              <div className="space-y-2" data-testid="skew-plan">
                <p className="text-sm">
                  {plan.count === 0 ? 'No records need re-normalizing.' : `${plan.count} record${plan.count === 1 ? '' : 's'} would change.`}
                </p>
                {plan.changes.length > 0 && (
                  <ul className="max-h-40 space-y-1 overflow-y-auto text-xs">
                    {plan.changes.slice(0, PREVIEW_ROWS).map((c) => (
                      <li key={`${c.kind}-${c.id}`} className="flex flex-wrap items-center gap-x-2">
                        <span className="text-muted-foreground">{c.kind.replace('_', ' ')}</span>
                        <Timestamp value={c.old} mode="utc" />
                        <span aria-hidden="true">→</span>
                        <Timestamp value={c.new} mode="utc" className="font-medium" />
                      </li>
                    ))}
                    {plan.count > PREVIEW_ROWS && <li className="text-muted-foreground">…and {plan.count - PREVIEW_ROWS} more</li>}
                  </ul>
                )}
                {plan.count > 0 && (
                  <Button type="button" size="sm" onClick={apply} loading={busy === 'apply'}>
                    Re-normalize {plan.count} record{plan.count === 1 ? '' : 's'}
                  </Button>
                )}
              </div>
            )}
          </section>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          <Button onClick={save} loading={saving} disabled={invalid || basisMissing}>Save skew</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
