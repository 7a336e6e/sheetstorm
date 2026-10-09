"use client"

/**
 * Typed-name acknowledgment of a transfer / check-out by the person who
 * received the evidence. One acknowledgment per entry. Server time is the
 * authoritative time; "Signed on paper at" is stored separately as the
 * recipient's own statement. An optional signed receipt (scanned) is uploaded
 * first as a `custody_receipt` copy of the item and linked by its hash.
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
import { DateTimeInput } from '@/components/ui/datetime-input'
import { Input, Textarea } from '@/components/ui/input'
import { Timestamp } from '@/components/ui/timestamp'
import { evidenceApi, evidenceBase, evidenceFilesApi } from '@/lib/endpoints/evidence'
import { invalidate } from '@/lib/query-cache'
import type { CustodyEntry, EvidenceArtifact, EvidenceItem } from '@/types'
import { actionLabel } from './evidence-helpers'
import { reportEvidenceError } from './evidence-errors'
import { Field, FormError } from './form-parts'

export interface AcknowledgeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  incidentId: string
  item: EvidenceItem
  /** The transfer / check-out entry being acknowledged. */
  entry: CustodyEntry | null
  /** The acknowledgment entry was written. */
  onDone?: () => void
}

export function AcknowledgeDialog(props: AcknowledgeDialogProps) {
  return (
    <Dialog open={props.open && !!props.entry} onOpenChange={props.onOpenChange}>
      {props.open && props.entry && <AcknowledgeForm key={props.entry.id} {...props} entry={props.entry} />}
    </Dialog>
  )
}

function AcknowledgeForm({
  onOpenChange,
  incidentId,
  item,
  entry,
  onDone,
}: AcknowledgeDialogProps & { entry: CustodyEntry }) {
  const [typedName, setTypedName] = useState('')
  const [statement, setStatement] = useState('')
  const [statedAt, setStatedAt] = useState<string | null>(null)
  const [receipt, setReceipt] = useState<File | null>(null)
  const [attempted, setAttempted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const nameError = attempted && !typedName.trim() ? 'The recipient types their full name to acknowledge' : null

  const submit = async () => {
    setAttempted(true)
    setServerError(null)
    if (!typedName.trim()) return
    setBusy(true)
    try {
      let receiptId: string | undefined
      if (receipt) {
        const form = new FormData()
        form.append('file', receipt)
        form.append('evidence_item_id', item.id)
        form.append('purpose', 'custody_receipt')
        form.append('description', `Signed custody receipt for ${item.evidence_number}`)
        const uploaded = (await evidenceFilesApi.upload(incidentId, form)) as EvidenceArtifact
        receiptId = uploaded.id
      }
      await evidenceApi.acknowledge(incidentId, item.id, entry.id, {
        typed_name: typedName.trim(),
        statement: statement.trim() || undefined,
        stated_at: statedAt,
        receipt_artifact_id: receiptId,
      })
      invalidate(evidenceBase(incidentId))
      onDone?.()
      onOpenChange(false)
    } catch (err) {
      reportEvidenceError(err, 'record the acknowledgment', setServerError)
    } finally {
      setBusy(false)
    }
  }

  const who = entry.recipient?.name ?? entry.external_party?.name ?? 'the recipient'

  return (
    <DialogContent className="max-w-lg">
      <DialogHeader>
        <DialogTitle>Acknowledge receipt of {item.evidence_number}</DialogTitle>
        <DialogDescription>
          {actionLabel(entry.action)} to {who} on <Timestamp value={entry.created_at} />. The person who received the
          evidence confirms it here; this is recorded in the signed ledger and cannot be edited.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="space-y-4 px-1">
        <Field label="Full name of the person acknowledging" required error={nameError}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid || undefined}
              value={typedName}
              onChange={(e) => setTypedName(e.target.value)}
              maxLength={255}
              autoComplete="off"
            />
          )}
        </Field>
        <Field label="Statement" hint="Optional, e.g. condition on receipt.">
          {({ id, describedBy }) => (
            <Textarea id={id} aria-describedby={describedBy} rows={2} value={statement} onChange={(e) => setStatement(e.target.value)} maxLength={20000} />
          )}
        </Field>
        <Field label="Signed on paper at" hint="Only if a paper receipt was signed at a different time.">
          {({ id, describedBy }) => <DateTimeInput id={id} aria-describedby={describedBy} value={statedAt} onChange={setStatedAt} />}
        </Field>
        <Field label="Signed receipt (scan)" hint="Optional. Stored as a copy of this item; its SHA-256 is written into the entry.">
          {({ id, describedBy }) => (
            <Input
              id={id}
              aria-describedby={describedBy}
              type="file"
              onChange={(e) => setReceipt(e.target.files?.[0] ?? null)}
            />
          )}
        </Field>
        <FormError message={serverError} />
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
          Cancel
        </Button>
        <Button onClick={() => void submit()} loading={busy}>
          Acknowledge
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
