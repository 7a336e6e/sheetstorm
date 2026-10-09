"use client"

/**
 * Vertical timeline of an item's custody ledger (oldest first).
 *
 * Each entry shows what happened and who did it, a signature mark (valid /
 * legacy-unsigned / signing key changed / TAMPERED), a marker when the hash
 * link to the previous entry did not verify, and, for a transfer or check-out
 * nobody has acknowledged, an "awaiting acknowledgment" chip that opens the
 * acknowledge dialog for users allowed to record one.
 */
import {
  ArrowRightLeft,
  CheckCircle2,
  ClipboardCheck,
  Download,
  Eye,
  FilePlus2,
  FileText,
  GitBranch,
  Hash,
  LogIn,
  LogOut,
  Lock,
  Pencil,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  ShieldX,
  Trash2,
  Upload,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Timestamp } from '@/components/ui/timestamp'
import { cn } from '@/lib/utils'
import type { CustodyEntry, SignatureStatus } from '@/types'
import {
  HASH_LABELS,
  actionLabel,
  custodyStateLabel,
  entryHasProblem,
  partyLabel,
  shortHash,
  transferMethodLabel,
  DISPOSE_METHOD_LABELS,
} from './evidence-helpers'

const ACTION_ICONS: Record<string, LucideIcon> = {
  register: FilePlus2,
  upload: Upload,
  view: Eye,
  download: Download,
  transfer: ArrowRightLeft,
  check_out: LogOut,
  check_in: LogIn,
  acknowledge: ClipboardCheck,
  verify: CheckCircle2,
  update: Pencil,
  add_hash: Hash,
  derive: GitBranch,
  export: FileText,
  delete: Trash2,
  void: Trash2,
  dispose: Trash2,
  legal_hold: Lock,
}

const SIGNATURE_MARKS: Record<string, { label: string; Icon: LucideIcon; className: string }> = {
  valid: { label: 'Signature valid', Icon: ShieldCheck, className: 'text-emerald-600 dark:text-emerald-400' },
  unsigned_legacy: {
    label: 'Recorded before signing existed (unsigned)',
    Icon: ShieldQuestion,
    className: 'text-muted-foreground',
  },
  key_mismatch: {
    label: 'Signed with a different key (key rotated): cannot be checked here',
    Icon: ShieldQuestion,
    className: 'text-amber-600 dark:text-amber-400',
  },
  invalid: { label: 'TAMPERED: signature does not match', Icon: ShieldX, className: 'text-destructive' },
  not_checked: { label: 'Signature not checked', Icon: ShieldQuestion, className: 'text-muted-foreground' },
}

export function SignatureMark({ status }: { status: SignatureStatus | null | undefined }) {
  const mark = SIGNATURE_MARKS[status ?? 'not_checked'] ?? SIGNATURE_MARKS.not_checked
  const { Icon } = mark
  return (
    <span title={mark.label} className={cn('inline-flex', mark.className)} data-signature={status ?? 'not_checked'}>
      <Icon className="h-4 w-4" aria-hidden />
      <span className="sr-only">{mark.label}</span>
    </span>
  )
}

const asString = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v : null)
const asRecord = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null

/** The sentence(s) under an entry's heading. Pure; tested. */
export function entryDetails(e: CustodyEntry): string[] {
  const ed = e.extra_data ?? {}
  const lines: string[] = []
  const to = e.external_party ? partyLabel(e.external_party) : e.recipient?.name
  const after = asRecord(ed.state_after)

  switch (e.action) {
    case 'check_out':
      if (to) lines.push(`To ${to}`)
      if (e.purpose) lines.push(`Purpose: ${e.purpose}`)
      if (e.transfer_method) lines.push(`Method: ${transferMethodLabel(e.transfer_method)}`)
      break
    case 'transfer':
      if (to) lines.push(`To ${to}`)
      if (e.transfer_method) lines.push(`Method: ${transferMethodLabel(e.transfer_method)}`)
      if (e.purpose) lines.push(`Reason: ${e.purpose}`)
      if (asString(ed.tracking_number)) lines.push(`Tracking: ${ed.tracking_number}`)
      break
    case 'check_in': {
      const location = asString(after?.storage_location)
      if (location) lines.push(`Stored at ${location}`)
      if (typeof ed.seal_intact === 'boolean') lines.push(ed.seal_intact ? 'Seal intact' : 'Seal broken or missing')
      if (asString(ed.condition_notes)) lines.push(`Condition: ${ed.condition_notes}`)
      if (e.external_party) lines.push(`Returned by ${partyLabel(e.external_party)}`)
      break
    }
    case 'acknowledge':
      if (asString(ed.typed_name)) lines.push(`Acknowledged by ${ed.typed_name}`)
      if (asString(ed.statement)) lines.push(`Statement: ${ed.statement}`)
      if (asRecord(ed.receipt)?.filename) lines.push(`Receipt: ${asRecord(ed.receipt)?.filename}`)
      break
    case 'verify': {
      const alg = asString(ed.algorithm)
      const label = alg ? HASH_LABELS[alg as keyof typeof HASH_LABELS] ?? alg : 'Hash'
      lines.push(`${label} ${e.verification_result === 'match' ? 'matches' : 'does NOT match'} the recorded value`)
      if (asString(ed.method)) lines.push(`Method: ${ed.method}`)
      if (asString(ed.tool)) lines.push(`Tool: ${ed.tool}`)
      break
    }
    case 'add_hash': {
      const h = asRecord(ed.hash)
      if (h && asString(h.value)) {
        const alg = String(h.algorithm)
        lines.push(`${HASH_LABELS[alg as keyof typeof HASH_LABELS] ?? alg} ${shortHash(String(h.value))}`)
        if (asString(h.supersedes)) lines.push(`Supersedes ${shortHash(String(h.supersedes))}`)
      }
      if (e.purpose) lines.push(`Reason: ${e.purpose}`)
      break
    }
    case 'update': {
      const changes = asRecord(ed.changes)
      if (changes) lines.push(`Changed: ${Object.keys(changes).map((k) => k.replace(/_/g, ' ')).join(', ')}`)
      break
    }
    case 'dispose': {
      const m = asString(ed.method)
      if (m) lines.push(`Method: ${DISPOSE_METHOD_LABELS[m as keyof typeof DISPOSE_METHOD_LABELS] ?? m}`)
      if (e.purpose) lines.push(`Reason: ${e.purpose}`)
      if (asString(ed.witness_name)) lines.push(`Witness: ${ed.witness_name}`)
      break
    }
    case 'void':
      if (e.purpose) lines.push(`Reason: ${e.purpose}`)
      break
    case 'legal_hold':
      lines.push(ed.hold === false ? 'Hold released' : 'Hold placed')
      if (asString(ed.legal_hold_until)) lines.push(`Until ${ed.legal_hold_until}`)
      if (e.purpose) lines.push(`Reason: ${e.purpose}`)
      break
    case 'export':
      if (asString(ed.format)) lines.push(`Format: ${String(ed.format).toUpperCase()}`)
      break
    case 'register': {
      const st = asRecord(ed.state_after)
      if (st && asString(st.custody_state)) lines.push(`Entered as ${custodyStateLabel(String(st.custody_state)).toLowerCase()}`)
      break
    }
    default:
      if (e.purpose) lines.push(e.purpose)
  }
  return lines
}

export function CustodyTimeline({
  entries,
  canAcknowledge,
  onAcknowledge,
  className,
}: {
  entries: CustodyEntry[]
  canAcknowledge?: boolean
  onAcknowledge?: (entry: CustodyEntry) => void
  className?: string
}) {
  if (entries.length === 0) {
    return <p className="py-6 text-center text-sm text-muted-foreground">No custody entries yet.</p>
  }
  return (
    <ol className={cn('space-y-0', className)} aria-label="Chain of custody">
      {entries.map((e, i) => {
        const Icon = ACTION_ICONS[e.action] ?? FileText
        const problem = entryHasProblem(e)
        const pending =
          (e.action === 'transfer' || e.action === 'check_out') && e.chain_version != null && !e.acknowledged_by_entry_id
        const last = i === entries.length - 1
        const linkBroken = e.link_status !== 'ok' && e.link_status !== 'legacy'
        return (
          <li key={e.id} className="relative flex gap-3 pb-4" data-entry-action={e.action}>
            {!last && <span className="absolute left-[15px] top-8 bottom-0 w-px bg-border" aria-hidden />}
            <span
              className={cn(
                'relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border',
                problem ? 'border-destructive/50 bg-destructive/10 text-destructive' : 'border-border bg-muted text-muted-foreground'
              )}
            >
              <Icon className="h-4 w-4" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-sm font-medium">{actionLabel(e.action)}</span>
                {e.seq != null && <span className="text-xs tabular-nums text-muted-foreground">#{e.seq}</span>}
                <SignatureMark status={e.signature_status} />
                {e.action === 'verify' && e.verification_result && (
                  <span
                    className={cn(
                      'text-xs font-medium',
                      e.verification_result === 'match' ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'
                    )}
                  >
                    {e.verification_result === 'match' ? 'Match' : 'Mismatch'}
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {e.performer?.name ?? 'System'} · <Timestamp value={e.created_at} />
              </p>
              {entryDetails(e).map((line, j) => (
                <p key={j} className="text-sm">
                  {line}
                </p>
              ))}
              {linkBroken && (
                <p role="alert" className="mt-1 flex items-center gap-1 text-xs font-medium text-destructive">
                  <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
                  Chain link not verified: {e.link_status.replace(/_/g, ' ').replace(/,/g, ', ')}
                </p>
              )}
              {pending &&
                (canAcknowledge && onAcknowledge ? (
                  <Button variant="outline" size="sm" className="mt-1.5 h-7 text-xs" onClick={() => onAcknowledge(e)}>
                    Awaiting acknowledgment · Acknowledge
                  </Button>
                ) : (
                  <span className="mt-1.5 inline-block rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-400">
                    Awaiting acknowledgment
                  </span>
                ))}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
