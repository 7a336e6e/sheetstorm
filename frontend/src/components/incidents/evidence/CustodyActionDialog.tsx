"use client"

/**
 * Check out / check in / transfer an evidence item (custody state machine).
 *
 *   check_out  in_storage            -> checked_out   to a colleague or party, purpose required
 *   transfer   in_storage|checked_out-> transferred   to a party (or colleague), method + reason required
 *   check_in   checked_out|transferred-> in_storage   location + seal state required
 *
 * Every submit appends one signed ledger entry. After a check-out or transfer
 * the dialog offers "Acknowledge now": the receiving person's typed-name
 * acknowledgment is a separate ledger entry (AcknowledgeDialog).
 */
import { useState } from 'react'
import { CheckCircle2 } from 'lucide-react'
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
import { DateTimeInput } from '@/components/ui/datetime-input'
import { EntityPicker } from '@/components/ui/entity-picker'
import { Input, Textarea } from '@/components/ui/input'
import { evidenceApi, evidenceBase } from '@/lib/endpoints/evidence'
import { invalidate } from '@/lib/query-cache'
import type { CustodyEntry, CustodyParty, EvidenceItem, TransferMethod } from '@/types'
import { TRANSFER_METHODS } from '@/types'
import { TRANSFER_METHOD_LABELS, partyRoleLabel, type CustodyMode } from './evidence-helpers'
import { reportEvidenceError } from './evidence-errors'
import { Field, FormError, NativeSelect, optionsFrom } from './form-parts'
import {
  RecipientPicker,
  emptyRecipient,
  recipientInput,
  recipientProblem,
  type RecipientState,
} from './RecipientPicker'

const TITLES: Record<CustodyMode, string> = {
  check_out: 'Check out',
  check_in: 'Check in',
  transfer: 'Transfer',
}

const DESCRIPTIONS: Record<CustodyMode, string> = {
  check_out: 'Record who is taking the evidence and why. The item stays accountable to them until it is checked in.',
  check_in: 'Record the item back into storage, with the seal and condition as you found them.',
  transfer: 'Hand the evidence to another party. The reason and method are written to the signed custody ledger.',
}

export interface CustodyActionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  incidentId: string
  item: EvidenceItem
  mode: CustodyMode
  /** The ledger entry was written (the item list / drawer should refresh). */
  onDone?: (entries: CustodyEntry[]) => void
  /** "Acknowledge now" after a check-out or transfer. */
  onAcknowledge?: (entry: CustodyEntry) => void
}

export function CustodyActionDialog(props: CustodyActionDialogProps) {
  // Re-mount the form for each open so fields never leak between uses.
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      {props.open && <CustodyActionForm key={`${props.item.id}:${props.mode}`} {...props} />}
    </Dialog>
  )
}

function CustodyActionForm({ onOpenChange, incidentId, item, mode, onDone, onAcknowledge }: CustodyActionDialogProps) {
  const [recipient, setRecipient] = useState<RecipientState>(() => emptyRecipient(mode === 'transfer' ? 'party' : 'user'))
  const [purpose, setPurpose] = useState('')
  const [reason, setReason] = useState('')
  const [method, setMethod] = useState<TransferMethod | ''>(mode === 'transfer' ? 'hand_delivery' : '')
  const [returnBy, setReturnBy] = useState<string | null>(null)
  const [tracking, setTracking] = useState('')
  const [sealNumber, setSealNumber] = useState(item.seal_number ?? '')
  const [location, setLocation] = useState('')
  const [sealIntact, setSealIntact] = useState<'' | 'yes' | 'no'>('')
  const [condition, setCondition] = useState('')
  const [fromParty, setFromParty] = useState<string | null>(null)

  const [attempted, setAttempted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const [recorded, setRecorded] = useState<CustodyEntry | null>(null)

  const recipientError = mode === 'check_in' ? null : recipientProblem(recipient)
  const problems = {
    recipient: recipientError,
    purpose: mode === 'check_out' && !purpose.trim() ? 'Say why the evidence is being checked out' : null,
    reason: mode === 'transfer' && !reason.trim() ? 'Give the reason for the transfer' : null,
    method: mode === 'transfer' && !method ? 'Choose how it is being delivered' : null,
    location: mode === 'check_in' && !location.trim() ? 'Where is the item stored now?' : null,
    seal: mode === 'check_in' && !sealIntact ? 'State whether the seal was intact' : null,
  }
  const invalid = Object.values(problems).some(Boolean)
  const show = (key: keyof typeof problems) => (attempted ? problems[key] : null)

  const submit = async () => {
    setAttempted(true)
    setServerError(null)
    if (invalid) return
    setBusy(true)
    try {
      let res
      if (mode === 'check_out') {
        res = await evidenceApi.checkOut(incidentId, item.id, {
          ...recipientInput(recipient),
          purpose: purpose.trim(),
          transfer_method: method || undefined,
          expected_return_at: returnBy,
        })
      } else if (mode === 'transfer') {
        res = await evidenceApi.transfer(incidentId, item.id, {
          ...recipientInput(recipient),
          transfer_method: method as TransferMethod,
          reason: reason.trim(),
          tracking_number: tracking.trim() || undefined,
          seal_number: sealNumber.trim() || undefined,
        })
      } else {
        res = await evidenceApi.checkIn(incidentId, item.id, {
          storage_location: location.trim(),
          seal_intact: sealIntact === 'yes',
          condition_notes: condition.trim() || undefined,
          seal_number: sealNumber.trim() || undefined,
          received_from_party_id: fromParty || undefined,
        })
      }
      invalidate(evidenceBase(incidentId))
      const entries = res.ledger_entries ?? []
      onDone?.(entries)
      if (mode === 'check_in' || !entries[0]) onOpenChange(false)
      else setRecorded(entries[0])
    } catch (err) {
      reportEvidenceError(err, `${TITLES[mode].toLowerCase()} the evidence`, setServerError)
    } finally {
      setBusy(false)
    }
  }

  if (recorded) {
    return (
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-emerald-500" aria-hidden />
            {item.evidence_number} {mode === 'transfer' ? 'transferred' : 'checked out'}
          </DialogTitle>
          <DialogDescription>
            The entry is in the signed custody ledger. The person receiving the evidence should acknowledge receipt
            with their typed name; until then the timeline shows it as awaiting acknowledgment.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Done
          </Button>
          {onAcknowledge && (
            <Button
              onClick={() => {
                onOpenChange(false)
                onAcknowledge(recorded)
              }}
            >
              Acknowledge now
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    )
  }

  return (
    <DialogContent className="max-w-xl">
      <DialogHeader>
        <DialogTitle>
          {TITLES[mode]} {item.evidence_number}
        </DialogTitle>
        <DialogDescription>{DESCRIPTIONS[mode]}</DialogDescription>
      </DialogHeader>
      <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto px-1">
        {mode !== 'check_in' && (
          <div className="space-y-1">
            <RecipientPicker value={recipient} onChange={setRecipient} />
            {show('recipient') && <p className="text-xs text-destructive">{show('recipient')}</p>}
          </div>
        )}

        {mode === 'check_out' && (
          <>
            <Field label="Purpose" required error={show('purpose')}>
              {({ id, describedBy, invalid: bad }) => (
                <Textarea
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={bad || undefined}
                  rows={2}
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}
                  maxLength={20000}
                  placeholder="e.g. Forensic imaging in the lab"
                />
              )}
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Transfer method">
                {({ id }) => (
                  <NativeSelect
                    id={id}
                    value={method}
                    placeholder="Not specified"
                    onValueChange={(v) => setMethod(v as TransferMethod | '')}
                    options={optionsFrom(TRANSFER_METHOD_LABELS).filter((o) => TRANSFER_METHODS.includes(o.value))}
                  />
                )}
              </Field>
              <Field label="Expected return">
                {({ id }) => <DateTimeInput id={id} value={returnBy} onChange={setReturnBy} />}
              </Field>
            </div>
          </>
        )}

        {mode === 'transfer' && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Transfer method" required error={show('method')}>
                {({ id, describedBy, invalid: bad }) => (
                  <NativeSelect
                    id={id}
                    aria-describedby={describedBy}
                    invalid={bad}
                    value={method}
                    placeholder="Choose…"
                    onValueChange={(v) => setMethod(v as TransferMethod | '')}
                    options={optionsFrom(TRANSFER_METHOD_LABELS).filter((o) => TRANSFER_METHODS.includes(o.value))}
                  />
                )}
              </Field>
              <Field label="Tracking number">
                {({ id }) => <Input id={id} value={tracking} onChange={(e) => setTracking(e.target.value)} maxLength={120} />}
              </Field>
            </div>
            <Field label="Reason" required error={show('reason')}>
              {({ id, describedBy, invalid: bad }) => (
                <Textarea
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={bad || undefined}
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={20000}
                  placeholder="e.g. Released to outside counsel for review"
                />
              )}
            </Field>
            <Field label="New seal number" hint="Leave blank if the seal is unchanged.">
              {({ id, describedBy }) => (
                <Input id={id} aria-describedby={describedBy} value={sealNumber} onChange={(e) => setSealNumber(e.target.value)} maxLength={120} />
              )}
            </Field>
          </>
        )}

        {mode === 'check_in' && (
          <>
            <Field label="Storage location" required error={show('location')}>
              {({ id, describedBy, invalid: bad }) => (
                <Input
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={bad || undefined}
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  maxLength={500}
                  placeholder="e.g. Evidence locker 3, shelf B"
                />
              )}
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Seal intact?" required error={show('seal')}>
                {({ id, describedBy, invalid: bad }) => (
                  <NativeSelect
                    id={id}
                    aria-describedby={describedBy}
                    invalid={bad}
                    value={sealIntact}
                    placeholder="Choose…"
                    onValueChange={(v) => setSealIntact(v as '' | 'yes' | 'no')}
                    options={[
                      { value: 'yes', label: 'Yes, seal intact' },
                      { value: 'no', label: 'No, seal broken or missing' },
                    ]}
                  />
                )}
              </Field>
              <Field label="Seal number now">
                {({ id }) => <Input id={id} value={sealNumber} onChange={(e) => setSealNumber(e.target.value)} maxLength={120} />}
              </Field>
            </div>
            <Field label="Condition notes">
              {({ id }) => (
                <Textarea id={id} rows={2} value={condition} onChange={(e) => setCondition(e.target.value)} maxLength={20000} />
              )}
            </Field>
            {item.custody_state === 'transferred' && (
              <Field label="Received from" hint="Optional: the external party handing it back.">
                {() => (
                  <EntityPicker<CustodyParty>
                    value={fromParty}
                    onChange={(id) => setFromParty(id)}
                    endpoint="/custody-parties"
                    params={{ sort: 'name' }}
                    getId={(p) => p.id}
                    getLabel={(p) => p.name}
                    getDescription={(p) => [p.organization_name, partyRoleLabel(p.role)].filter(Boolean).join(' · ') || undefined}
                    ariaLabel="Received from party"
                    placeholder="Search saved parties…"
                  />
                )}
              </Field>
            )}
          </>
        )}

        <FormError message={serverError} />
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
          Cancel
        </Button>
        <Button onClick={() => void submit()} loading={busy}>
          {TITLES[mode]}
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
