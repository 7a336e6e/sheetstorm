"use client"

/**
 * Record a hash verification against the item's recorded hash.
 *
 * Lab: type the hash a tool produced from the physical or imaged evidence.
 * Stored copy: the server recomputes from the file held in SheetStorm (only
 * for copies whose content has not been purged). Either way a `verify` entry
 * is written with expected, observed and the verdict; a mismatch is also a
 * security event.
 */
import { useState } from 'react'
import { CheckCircle2, XCircle } from 'lucide-react'
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
import { evidenceApi, evidenceBase } from '@/lib/endpoints/evidence'
import { invalidate } from '@/lib/query-cache'
import type { EvidenceArtifact, EvidenceItem, EvidenceMutation, HashAlgorithm } from '@/types'
import { HASH_ALGORITHMS, HASH_LENGTHS } from '@/types'
import { HASH_LABELS, activeHashes, guessAlgorithm, normalizeHash, validateHash } from './evidence-helpers'
import { reportEvidenceError } from './evidence-errors'
import { Field, FormError, NativeSelect } from './form-parts'

type Mode = 'lab' | 'recompute'
const RECOMPUTE_ALGORITHMS = ['sha256', 'sha512', 'md5'] as const

export interface VerifyHashDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  incidentId: string
  item: EvidenceItem
  /** The item's stored copies (live ones with content can be recomputed). */
  artifacts?: EvidenceArtifact[]
  onDone?: () => void
}

export function VerifyHashDialog(props: VerifyHashDialogProps) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      {props.open && <VerifyForm key={props.item.id} {...props} />}
    </Dialog>
  )
}

function VerifyForm({ onOpenChange, incidentId, item, artifacts = [], onDone }: VerifyHashDialogProps) {
  const copies = artifacts.filter((a) => !a.deleted_at && !a.content_purged && a.purpose === 'evidence')
  const recorded = activeHashes(item)
  const [mode, setMode] = useState<Mode>('lab')
  const [algorithm, setAlgorithm] = useState<HashAlgorithm>(recorded[0]?.algorithm ?? 'sha256')
  const [observed, setObserved] = useState('')
  const [method, setMethod] = useState('')
  const [tool, setTool] = useState('')
  const [notes, setNotes] = useState('')
  const [artifactId, setArtifactId] = useState(copies[0]?.id ?? '')
  const [recomputeAlg, setRecomputeAlg] = useState<(typeof RECOMPUTE_ALGORITHMS)[number]>('sha256')
  const [attempted, setAttempted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const [result, setResult] = useState<EvidenceMutation['verification'] | null>(null)

  const observedError = mode === 'lab' ? validateHash(algorithm, observed, { required: true }) : null
  const copyError = mode === 'recompute' && !artifactId ? 'Choose the stored file to recompute' : null

  const onObserved = (v: string) => {
    setObserved(v)
    const guessed = guessAlgorithm(v)
    if (guessed && guessed !== algorithm && recorded.some((h) => h.algorithm === guessed)) setAlgorithm(guessed)
  }

  const submit = async () => {
    setAttempted(true)
    setServerError(null)
    if (observedError || copyError) return
    setBusy(true)
    try {
      const res =
        mode === 'lab'
          ? await evidenceApi.verifyHash(incidentId, item.id, {
              algorithm,
              observed_hash: normalizeHash(observed),
              method: method.trim() || undefined,
              tool: tool.trim() || undefined,
              notes: notes.trim() || undefined,
            })
          : await evidenceApi.verifyHash(incidentId, item.id, {
              recompute: true,
              artifact_id: artifactId,
              algorithm: recomputeAlg,
              notes: notes.trim() || undefined,
            })
      invalidate(evidenceBase(incidentId))
      onDone?.()
      setResult(res.verification ?? null)
      if (!res.verification) onOpenChange(false)
    } catch (e) {
      reportEvidenceError(e, 'record the verification', setServerError)
    } finally {
      setBusy(false)
    }
  }

  if (result) {
    return (
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {result.match ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-500" aria-hidden />
            ) : (
              <XCircle className="h-5 w-5 text-destructive" aria-hidden />
            )}
            {result.match ? 'Hashes match' : 'Hash mismatch'}
          </DialogTitle>
          <DialogDescription>
            {result.match
              ? `The ${HASH_LABELS[result.algorithm]} value agrees with the recorded one. The verification is in the ledger.`
              : `The ${HASH_LABELS[result.algorithm]} value does NOT match the recorded one. This is logged as an integrity event; the evidence may have been altered or the wrong value was entered.`}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-2 font-mono text-xs">
          <p className="break-all"><span className="text-muted-foreground">Recorded </span>{result.expected_hash}</p>
          <p className="break-all"><span className="text-muted-foreground">Observed </span>{result.observed_hash}</p>
        </DialogBody>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    )
  }

  return (
    <DialogContent className="max-w-xl">
      <DialogHeader>
        <DialogTitle>Verify hash of {item.evidence_number}</DialogTitle>
        <DialogDescription>Compare an observed hash with the one recorded for this item.</DialogDescription>
      </DialogHeader>
      <DialogBody className="space-y-4 px-1">
        {copies.length > 0 && (
          <div role="radiogroup" aria-label="Verification source" className="inline-flex rounded-md border border-border p-0.5">
            {(['lab', 'recompute'] as const).map((m) => (
              <label
                key={m}
                className={`cursor-pointer rounded px-3 py-1 text-sm ${mode === m ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}
              >
                <input type="radio" name="verify-mode" className="sr-only" checked={mode === m} onChange={() => setMode(m)} />
                {m === 'lab' ? 'Enter a hash' : 'Recompute stored file'}
              </label>
            ))}
          </div>
        )}

        {mode === 'lab' ? (
          <>
            <div className="grid gap-4 sm:grid-cols-[140px_1fr]">
              <Field label="Algorithm" required>
                {({ id }) => (
                  <NativeSelect
                    id={id}
                    value={algorithm}
                    onValueChange={(v) => setAlgorithm(v as HashAlgorithm)}
                    options={HASH_ALGORITHMS.map((a) => ({ value: a, label: HASH_LABELS[a] }))}
                  />
                )}
              </Field>
              <Field label="Observed hash" required error={attempted ? observedError : null} hint={`${HASH_LENGTHS[algorithm]} hexadecimal characters`}>
                {({ id, describedBy, invalid }) => (
                  <Input
                    id={id}
                    aria-describedby={describedBy}
                    aria-invalid={invalid || undefined}
                    value={observed}
                    onChange={(e) => onObserved(e.target.value)}
                    className="font-mono text-xs"
                    spellCheck={false}
                    autoComplete="off"
                  />
                )}
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Method">
                {({ id }) => <Input id={id} value={method} onChange={(e) => setMethod(e.target.value)} maxLength={100} placeholder="e.g. Re-hash of image" />}
              </Field>
              <Field label="Tool">
                {({ id }) => <Input id={id} value={tool} onChange={(e) => setTool(e.target.value)} maxLength={150} />}
              </Field>
            </div>
          </>
        ) : (
          <div className="grid gap-4 sm:grid-cols-[1fr_140px]">
            <Field label="Stored file" required error={attempted ? copyError : null}>
              {({ id }) => (
                <NativeSelect
                  id={id}
                  value={artifactId}
                  onValueChange={setArtifactId}
                  options={copies.map((a) => ({ value: a.id, label: a.original_filename }))}
                />
              )}
            </Field>
            <Field label="Algorithm">
              {({ id }) => (
                <NativeSelect
                  id={id}
                  value={recomputeAlg}
                  onValueChange={(v) => setRecomputeAlg(v as (typeof RECOMPUTE_ALGORITHMS)[number])}
                  options={RECOMPUTE_ALGORITHMS.map((a) => ({ value: a, label: HASH_LABELS[a] }))}
                />
              )}
            </Field>
          </div>
        )}
        <Field label="Notes">
          {({ id }) => <Textarea id={id} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={20000} />}
        </Field>
        <FormError message={serverError} />
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
          Cancel
        </Button>
        <Button onClick={() => void submit()} loading={busy}>
          Verify
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
