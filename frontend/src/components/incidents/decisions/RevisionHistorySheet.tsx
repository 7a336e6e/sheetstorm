"use client"

/**
 * Revision history of one decision or response action (W4-DEC): every
 * revision with its diff, reason, actor and signature status, plus the
 * server's chain verification (intact / broken / compromised / unverifiable).
 */
import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, KeyRound, Loader2, ShieldAlert } from 'lucide-react'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Timestamp } from '@/components/ui/timestamp'
import { isAbortError } from '@/lib/api'
import { decisionLog } from '@/lib/endpoints/decisions'
import { describeError } from '@/lib/errors'
import type { DecisionChainStatus, DecisionRevisionsResponse, RevisionSignatureStatus } from '@/types'

export interface RevisionSubject {
  kind: 'decision' | 'action'
  id: string
  displayId: string
  title: string
}

const CHAIN_TEXT: Record<DecisionChainStatus, string> = {
  intact: 'Chain intact: every revision is present and correctly signed.',
  broken: 'Chain BROKEN: revisions are missing, reordered, or the record no longer matches its last revision.',
  compromised: 'COMPROMISED: a revision was altered after it was signed.',
  unverifiable: 'Unverifiable: revisions were signed with a different (rotated) key.',
}

export function SignatureIcon({ status }: { status: RevisionSignatureStatus }) {
  if (status === 'valid') return <CheckCircle2 aria-label="Signature valid" className="h-4 w-4 text-emerald-400" />
  if (status === 'key_mismatch') return <KeyRound aria-label="Signed with another key" className="h-4 w-4 text-amber-400" />
  return <ShieldAlert aria-label="Signature invalid" className="h-4 w-4 text-red-400" />
}

/** One line per changed field: `field: from → to` (lists: `+added −removed`). */
export function describeChanges(changes: DecisionRevisionsResponse['items'][number]['changes']): string[] {
  const show = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'string' ? v : JSON.stringify(v))
  return Object.entries(changes ?? {}).map(([field, c]) => {
    if (c && ('added' in c || 'removed' in c)) {
      const parts = [...(c.added ?? []).map((v) => `+${show(v)}`), ...(c.removed ?? []).map((v) => `−${show(v)}`)]
      return `${field}: ${parts.join(' ')}`
    }
    return `${field}: ${show(c?.from)} → ${show(c?.to)}`
  })
}

interface Props {
  incidentId: string
  subject: RevisionSubject | null
  onClose(): void
}

export function RevisionHistorySheet({ incidentId, subject, onClose }: Props) {
  // Results are keyed by subject id, so switching records never shows stale rows
  // (and no state is reset synchronously inside the effect).
  const [result, setResult] = useState<{ id: string; data?: DecisionRevisionsResponse; error?: string } | null>(null)
  useEffect(() => {
    if (!subject) return
    const controller = new AbortController()
    const load = subject.kind === 'decision' ? decisionLog.decisionRevisions : decisionLog.actionRevisions
    load(incidentId, subject.id, { signal: controller.signal })
      .then((data) => setResult({ id: subject.id, data }))
      .catch((err: unknown) => {
        if (!isAbortError(err)) setResult({ id: subject.id, error: describeError(err).description })
      })
    return () => controller.abort()
  }, [incidentId, subject])
  const current = subject && result?.id === subject.id ? result : null
  const data = current?.data ?? null
  const error = current?.error ?? null

  const status = data?.verification.status
  return (
    <Sheet open={!!subject} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="flex w-full flex-col gap-4 overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Revision history · {subject?.displayId}</SheetTitle>
          <SheetDescription>{subject?.title}</SheetDescription>
        </SheetHeader>
        {!data && !error && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-label="Loading" />}
        {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
        {status && (
          <div
            role="status"
            className={`flex items-start gap-2 rounded-md border p-3 text-sm ${
              status === 'intact' ? 'border-emerald-500/30 text-emerald-300' : 'border-red-500/30 text-red-300'
            }`}
          >
            {status === 'intact' ? <CheckCircle2 className="mt-0.5 h-4 w-4" /> : <AlertTriangle className="mt-0.5 h-4 w-4" />}
            {CHAIN_TEXT[status]}
          </div>
        )}
        <ol className="space-y-3">
          {data?.items.map((r) => (
            <li key={r.id} className="rounded-md border border-white/10 bg-slate-900/60 p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">
                  #{r.seq} · {r.event.replace(/_/g, ' ')}
                  {r.self_approved && <span className="ml-2 text-xs text-amber-300">self-approved</span>}
                </span>
                <SignatureIcon status={r.signature_status} />
              </div>
              <div className="text-xs text-muted-foreground">
                <Timestamp value={r.created_at} /> · {r.actor_email ?? 'system'}
              </div>
              {r.reason && <p className="mt-1 text-sm">Reason: {r.reason}</p>}
              {describeChanges(r.changes).length > 0 && (
                <ul className="mt-1 space-y-0.5 font-mono text-xs text-slate-300">
                  {describeChanges(r.changes).map((line) => <li key={line}>{line}</li>)}
                </ul>
              )}
            </li>
          ))}
        </ol>
      </SheetContent>
    </Sheet>
  )
}
