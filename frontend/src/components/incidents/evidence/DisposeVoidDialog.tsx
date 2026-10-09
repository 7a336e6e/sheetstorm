"use client"

/**
 * Dispose of an item (terminal custody state) or void it (tombstone for an
 * item entered in error; the EV number is never reused). Both are
 * irreversible ledger entries, so after the form the user must type the EV
 * number to confirm (`useConfirm` + `requireText`).
 *
 * Dispose and void are refused under legal hold (409 `legal_hold`), and void
 * with live derived items; the server's message is shown here.
 */
import { useState } from 'react'
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
import { Input, Textarea } from '@/components/ui/input'
import { evidenceApi, evidenceBase } from '@/lib/endpoints/evidence'
import { notifySuccess } from '@/lib/errors'
import { invalidate } from '@/lib/query-cache'
import type { DisposeMethod, EvidenceItem } from '@/types'
import { DISPOSE_METHODS } from '@/types'
import { DISPOSE_METHOD_LABELS } from './evidence-helpers'
import { reportEvidenceError } from './evidence-errors'
import { Field, FormError, NativeSelect, optionsFrom } from './form-parts'

export type DisposeVoidMode = 'dispose' | 'void'

export interface DisposeVoidDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  incidentId: string
  item: EvidenceItem
  mode: DisposeVoidMode
  onDone?: () => void
}

export function DisposeVoidDialog(props: DisposeVoidDialogProps) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      {props.open && <DisposeVoidForm key={`${props.item.id}:${props.mode}`} {...props} />}
    </Dialog>
  )
}

function DisposeVoidForm({ onOpenChange, incidentId, item, mode, onDone }: DisposeVoidDialogProps) {
  const confirm = useConfirm()
  const [method, setMethod] = useState<DisposeMethod>('returned_to_owner')
  const [reason, setReason] = useState('')
  const [witness, setWitness] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const dispose = mode === 'dispose'
  const reasonError = attempted && !reason.trim() ? (dispose ? 'Give the reason for disposal' : 'Say why this entry is being voided') : null

  const submit = async () => {
    setAttempted(true)
    setServerError(null)
    if (!reason.trim()) return
    const ok = await confirm({
      title: dispose ? `Dispose of ${item.evidence_number}?` : `Void ${item.evidence_number}?`,
      description: dispose
        ? `${item.evidence_number} will be marked disposed (${DISPOSE_METHOD_LABELS[method].toLowerCase()}). This is final: the item can never be checked out again.`
        : `${item.evidence_number} will be voided as entered in error. The record, its number and its ledger stay, but it can no longer be used.`,
      confirmLabel: dispose ? 'Dispose' : 'Void',
      variant: 'destructive',
      requireText: item.evidence_number,
    })
    if (!ok) return
    setBusy(true)
    try {
      if (dispose) {
        await evidenceApi.dispose(incidentId, item.id, {
          method,
          reason: reason.trim(),
          witness_name: witness.trim() || undefined,
        })
      } else {
        await evidenceApi.void(incidentId, item.id, reason.trim())
      }
      invalidate(evidenceBase(incidentId))
      notifySuccess(dispose ? `${item.evidence_number} disposed` : `${item.evidence_number} voided`)
      onDone?.()
      onOpenChange(false)
    } catch (e) {
      reportEvidenceError(e, dispose ? 'dispose of the evidence' : 'void the evidence item', setServerError)
    } finally {
      setBusy(false)
    }
  }

  return (
    <DialogContent className="max-w-lg">
      <DialogHeader>
        <DialogTitle>
          {dispose ? 'Dispose of' : 'Void'} {item.evidence_number}
        </DialogTitle>
        <DialogDescription>
          {dispose
            ? 'Record the final disposition of the evidence (returned, destroyed or released). This ends its chain of custody.'
            : 'Use only for an item registered by mistake. Items that exist are disposed of, not voided.'}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="space-y-4 px-1">
        {item.under_legal_hold && (
          <p role="alert" className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm">
            This item is under legal hold, so the server will refuse this. Release the hold first.
          </p>
        )}
        {dispose && (
          <Field label="Method" required>
            {({ id }) => (
              <NativeSelect
                id={id}
                value={method}
                onValueChange={(v) => setMethod(v as DisposeMethod)}
                options={optionsFrom(DISPOSE_METHOD_LABELS).filter((o) => DISPOSE_METHODS.includes(o.value))}
              />
            )}
          </Field>
        )}
        <Field label="Reason" required error={reasonError}>
          {({ id, describedBy, invalid }) => (
            <Textarea
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid || undefined}
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={20000}
            />
          )}
        </Field>
        {dispose && (
          <Field label="Witness" hint="Optional: who observed the disposal.">
            {({ id, describedBy }) => (
              <Input id={id} aria-describedby={describedBy} value={witness} onChange={(e) => setWitness(e.target.value)} maxLength={255} />
            )}
          </Field>
        )}
        <FormError message={serverError} />
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
          Cancel
        </Button>
        <Button variant="destructive" onClick={() => void submit()} loading={busy}>
          {dispose ? 'Dispose…' : 'Void…'}
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
