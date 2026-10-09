"use client"

/**
 * Events-table toggle "Show response actions & decisions" (W4-DEC). The rows
 * come from `GET /incidents/<id>/response-timeline`: virtual, read-only rows
 * (never materialized as timeline events, so they never trigger MITRE or
 * graph automation). Privileged decisions are filtered by the server.
 */
import { useEffect, useState } from 'react'
import { Gavel, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermission } from '@/components/auth/permission-gate'
import { isAbortError } from '@/lib/api'
import { decisionLog } from '@/lib/endpoints/decisions'
import { describeError } from '@/lib/errors'
import type { VirtualTimelineRow } from '@/types'
import { label, statusTone } from './decision-helpers'

export function ResponseTimelineToggle({ incidentId }: { incidentId: string }) {
  const canSee = usePermission(['decisions:read', 'response_actions:read'], 'any')
  const [on, setOn] = useState(false)
  const [rows, setRows] = useState<VirtualTimelineRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!on) return
    const controller = new AbortController()
    decisionLog
      .responseTimeline(incidentId, { signal: controller.signal })
      .then((res) => setRows(res.items ?? []))
      .catch((err: unknown) => {
        if (!isAbortError(err)) setError(describeError(err).description)
      })
    return () => controller.abort()
  }, [on, incidentId])
  if (!canSee) return null

  return (
    <div className="space-y-2">
      <Button variant="outline" size="sm" aria-pressed={on} onClick={() => setOn((v) => !v)}>
        <ShieldCheck className="mr-1 h-4 w-4" />
        {on ? 'Hide response actions & decisions' : 'Show response actions & decisions'}
      </Button>
      {on && error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      {on && rows && (
        <ul aria-label="Response actions and decisions" className="divide-y divide-white/5 rounded-md border border-sky-500/20 bg-sky-950/20">
          {rows.length === 0 && <li className="px-3 py-2 text-sm text-muted-foreground">No response actions or decisions yet.</li>}
          {rows.map((r) => (
            <li key={`${r.kind}:${r.id}`} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
              <span className="w-40 shrink-0 text-xs text-muted-foreground">
                <Timestamp value={r.timestamp} seconds={false} />
              </span>
              <span className="inline-flex items-center gap-1 font-mono text-xs text-sky-300">
                {r.kind === 'decision' ? <Gavel className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />}
                {r.display_id}
              </span>
              <span className="min-w-0 flex-1 truncate">{r.kind === 'decision' ? r.title : `${label(r.activity.split(' ')[0])} · ${r.title}`}</span>
              <span className={`rounded-full border px-2 py-0.5 text-xs ${statusTone(r.status)}`}>{label(r.status)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
