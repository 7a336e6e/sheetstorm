"use client"

/**
 * Record an acquisition hash on an existing item. A hash is never edited: when
 * the algorithm already has a value, the new one supersedes it and a reason is
 * mandatory (both stay visible in the ledger).
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
import { Textarea } from '@/components/ui/input'
import { evidenceApi, evidenceBase } from '@/lib/endpoints/evidence'
import { invalidate } from '@/lib/query-cache'
import type { EvidenceItem } from '@/types'
import { HASH_LABELS, activeHashes, normalizeHash, shortHash } from './evidence-helpers'
import { reportEvidenceError } from './evidence-errors'
import { Field, FormError } from './form-parts'
import { HashEntry, hashRowProblem, newHashRow, type HashRow } from './HashEntry'

export interface AddHashDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  incidentId: string
  item: EvidenceItem
  onSaved?: () => void
}

export function AddHashDialog(props: AddHashDialogProps) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      {props.open && <AddHashForm key={props.item.id} {...props} />}
    </Dialog>
  )
}

function AddHashForm({ onOpenChange, incidentId, item, onSaved }: AddHashDialogProps) {
  const [rows, setRows] = useState<HashRow[]>(() => [{ ...newHashRow('sha256'), source: 'computed_in_lab' }])
  const [reason, setReason] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const row = rows[0]
  const existing = row ? activeHashes(item).find((h) => h.algorithm === row.algorithm) : undefined
  const rowProblem = row ? hashRowProblem(row, rows) : null
  const empty = !row || !normalizeHash(row.value)
  const reasonError = attempted && existing && !reason.trim() ? 'Say why the recorded value is being replaced' : null

  const submit = async () => {
    setAttempted(true)
    setServerError(null)
    if (!row || empty || rowProblem || (existing && !reason.trim())) return
    setBusy(true)
    try {
      await evidenceApi.addHash(incidentId, item.id, {
        algorithm: row.algorithm,
        value: normalizeHash(row.value),
        source: row.source,
        supersedes: existing?.value,
        reason: reason.trim() || undefined,
      })
      invalidate(evidenceBase(incidentId))
      onSaved?.()
      onOpenChange(false)
    } catch (e) {
      reportEvidenceError(e, 'record the hash', setServerError)
    } finally {
      setBusy(false)
    }
  }

  return (
    <DialogContent className="max-w-2xl">
      <DialogHeader>
        <DialogTitle>Record hash for {item.evidence_number}</DialogTitle>
        <DialogDescription>
          Hashes are write-once. To correct a recorded value, enter the new one and give a reason: both stay in the
          custody ledger.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="space-y-4 px-1">
        <HashEntry rows={rows} onChange={setRows} showErrors={attempted || !!row?.value} max={1} />
        {attempted && empty && <p className="text-xs text-destructive">Enter a hash value</p>}
        {existing && (
          <>
            <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm">
              {HASH_LABELS[row.algorithm]} <span className="font-mono">{shortHash(existing.value)}</span> is already
              recorded. This entry will supersede it.
            </p>
            <Field label="Reason for the correction" required error={reasonError}>
              {({ id, describedBy, invalid }) => (
                <Textarea
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={invalid || undefined}
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={20000}
                />
              )}
            </Field>
          </>
        )}
        <FormError message={serverError} />
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
          Cancel
        </Button>
        <Button onClick={() => void submit()} loading={busy}>
          {existing ? 'Supersede hash' : 'Record hash'}
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
