"use client"

/**
 * Audit hash-chain status + "Verify now" (`GET /admin/audit-integrity`,
 * organizations:manage, rate-limited 6/h). Shows the stored last
 * verification (from system status) until a check is run, then the result:
 * rows checked, failures (first ≤50 with seq + reason), rotated-key and
 * legacy (unchained) counts.
 */
import * as React from 'react'
import { CheckCircle2, Loader2, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermission } from '@/components/auth/permission-gate'
import { admin } from '@/lib/endpoints/admin'
import { notifyError } from '@/lib/errors'
import { cn } from '@/lib/utils'
import type { AuditChainStatus, AuditIntegrityResult } from '@/types'

const REASON_LABEL: Record<string, string> = {
  hash_mismatch: 'Row edited (hash mismatch)',
  prev_hash_mismatch: 'Broken link to previous row',
  gap: 'Missing row (sequence gap)',
  duplicate: 'Duplicate sequence number',
  head_mismatch: 'Chain head mismatch (rows removed from the end)',
}

export function shortHash(hash: string | null | undefined, n = 12): string {
  if (!hash) return '—'
  return hash.length > n ? `${hash.slice(0, n)}…` : hash
}

function StatusLine({ ok, children }: { ok: boolean | null | undefined; children: React.ReactNode }) {
  const Icon = ok === true ? ShieldCheck : ok === false ? ShieldAlert : ShieldQuestion
  return (
    <div
      className={cn(
        'flex items-center gap-2 text-sm font-medium',
        ok === true ? 'text-emerald-400' : ok === false ? 'text-red-400' : 'text-muted-foreground'
      )}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden />
      <span>{children}</span>
    </div>
  )
}

export function AuditIntegrityPanel({
  chain,
  onVerified,
  className,
}: {
  /** Stored head + last verification (system status `audit.chain`), if known. */
  chain?: AuditChainStatus | null
  onVerified?: (result: AuditIntegrityResult) => void
  className?: string
}) {
  const canVerify = usePermission('organizations:manage')
  const [result, setResult] = React.useState<AuditIntegrityResult | null>(null)
  const [running, setRunning] = React.useState(false)

  const verify = async () => {
    setRunning(true)
    try {
      const r = await admin.verifyAuditIntegrity()
      setResult(r)
      onVerified?.(r)
    } catch (err) {
      notifyError(err, 'verify the audit chain')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className={cn('space-y-3', className)} data-testid="audit-integrity">
      {result ? (
        <div className="space-y-2" role="status">
          <StatusLine ok={result.ok}>
            {result.ok
              ? 'Chain verified: no tampering detected'
              : `Chain verification failed: ${result.failure_count} problem${result.failure_count === 1 ? '' : 's'}`}
          </StatusLine>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
            <div>
              <dt className="text-muted-foreground">Rows checked</dt>
              <dd className="tabular-nums">{result.checked.toLocaleString()}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Head</dt>
              <dd className="font-mono" title={result.head_hash ?? undefined}>
                #{result.head_seq} {shortHash(result.head_hash)}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Legacy (unchained)</dt>
              <dd className="tabular-nums">{result.legacy_unchained.toLocaleString()}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Rotated key</dt>
              <dd className="tabular-nums">{result.unverifiable_rotated_key.toLocaleString()}</dd>
            </div>
          </dl>
          <p className="text-xs text-muted-foreground">
            Verified <Timestamp value={result.verified_at} />
            {result.purged_through_seq > 0 && <> · purged through #{result.purged_through_seq}</>}
          </p>
          {result.failures.length > 0 && (
            <div className="max-h-56 overflow-auto rounded-md border border-red-500/25">
              <table className="w-full text-left text-xs" aria-label="Chain failures">
                <thead className="border-b border-white/10 bg-slate-900/60">
                  <tr>
                    <th scope="col" className="px-3 py-1.5 font-medium text-muted-foreground">Seq</th>
                    <th scope="col" className="px-3 py-1.5 font-medium text-muted-foreground">Problem</th>
                    <th scope="col" className="px-3 py-1.5 font-medium text-muted-foreground">Row</th>
                  </tr>
                </thead>
                <tbody>
                  {result.failures.map((f, i) => (
                    <tr key={`${f.seq}-${f.reason}-${i}`} className="border-b border-white/5 last:border-0">
                      <td className="px-3 py-1.5 font-mono tabular-nums">{f.seq ?? '—'}</td>
                      <td className="px-3 py-1.5 text-red-300">{REASON_LABEL[f.reason] ?? f.reason}</td>
                      <td className="px-3 py-1.5 font-mono text-muted-foreground">{f.id ? shortHash(f.id, 8) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.failure_count > result.failures.length && (
                <p className="border-t border-white/10 px-3 py-1.5 text-xs text-muted-foreground">
                  Showing the first {result.failures.length} of {result.failure_count}.
                </p>
              )}
            </div>
          )}
        </div>
      ) : chain ? (
        <div className="space-y-1">
          <StatusLine ok={chain.last_verify_ok}>
            {chain.last_verify_ok === true
              ? 'Last verification passed'
              : chain.last_verify_ok === false
                ? 'Last verification FAILED'
                : 'Not verified yet'}
          </StatusLine>
          <p className="text-xs text-muted-foreground">
            Head #{chain.head_seq} <span className="font-mono">{shortHash(chain.head_hash)}</span>
            {chain.last_verified_at && (
              <>
                {' '}
                · checked <Timestamp value={chain.last_verified_at} />
              </>
            )}
            {chain.legacy_unchained > 0 && <> · {chain.legacy_unchained.toLocaleString()} legacy rows</>}
          </p>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">Run a check to verify the audit hash chain.</p>
      )}
      {canVerify && (
        <Button variant="outline" size="sm" onClick={() => void verify()} disabled={running}>
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
          Verify now
        </Button>
      )}
    </div>
  )
}
