"use client"

/**
 * Cross-incident IOC correlation for one incident: which of its indicators
 * (network IOC values, malware hashes, host IOC values, hostnames) also appear
 * in other incidents the user can access. Opened from the incident header's
 * Export menu (`ExportMenu`).
 *
 * `POST /correlate-iocs {incident_id}`; the server only ever lists incidents the
 * caller may see, and the current incident is left out of each match here.
 */
import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { Badge } from '@/components/ui/badge'
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
import { describeError } from '@/lib/errors'
import { isAbortError } from '@/lib/api'
import { exportsApi } from '@/lib/endpoints/exports'
import type { IOCCorrelation } from '@/types'

/** `network_ioc` -> `network ioc`, `host_ioc:file` -> `host ioc: file`. */
export function correlationTypeLabel(type: string): string {
  return type.replace(/_/g, ' ').replace(':', ': ')
}

/** Matches with the current incident taken out; a match with no other incident left is dropped. */
export function otherIncidentMatches(correlations: IOCCorrelation[], currentIncidentId: string) {
  return correlations
    .map((c) => ({ ...c, others: c.incidents.filter((i) => i.id !== currentIncidentId) }))
    .filter((c) => c.others.length > 0)
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  incidentId: string
}

export function IOCCorrelationDialog({ open, onOpenChange, incidentId }: Props) {
  const [matches, setMatches] = useState<ReturnType<typeof otherIncidentMatches> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const loading = open && matches === null && error === null

  useEffect(() => {
    if (!open) return
    let cancelled = false
    exportsApi
      .correlate(incidentId)
      .then((res) => {
        if (!cancelled) setMatches(otherIncidentMatches(res.correlations ?? [], incidentId))
      })
      .catch((err) => {
        if (cancelled || isAbortError(err)) return
        setError(describeError(err).description)
      })
    return () => {
      // Closing (or retrying) drops the previous answer so the next open starts clean.
      cancelled = true
      setMatches(null)
      setError(null)
    }
  }, [open, incidentId, reloadKey])

  const total = useMemo(() => matches?.length ?? 0, [matches])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>IOC correlation</DialogTitle>
          <DialogDescription>
            Indicators of this incident that also appear in other incidents you can access.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3">
          {loading && <p className="text-sm text-muted-foreground">Checking other incidents…</p>}

          {error && (
            <div role="alert" className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
              <span>{error}</span>
              <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setReloadKey((k) => k + 1)}>
                Retry
              </Button>
            </div>
          )}

          {!loading && !error && matches && total === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No indicator of this incident appears in another incident you can access.
            </p>
          )}

          {!loading && !error && total > 0 && (
            <ul className="divide-y divide-border rounded-md border border-border" aria-label="Correlated indicators">
              {matches!.map((c) => (
                <li key={`${c.ioc_type}:${c.ioc_value}`} className="space-y-2 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="break-all font-mono text-sm">{c.ioc_value}</code>
                    <Badge variant="outline" className="text-xs">{correlationTypeLabel(c.ioc_type)}</Badge>
                    <span className="ml-auto text-xs text-muted-foreground">
                      also in {c.others.length} other incident{c.others.length === 1 ? '' : 's'}
                    </span>
                  </div>
                  <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                    {c.others.map((i) => (
                      <li key={i.id}>
                        <Link
                          href={`/dashboard/incidents/${i.id}`}
                          className="text-primary underline-offset-2 hover:underline"
                          onClick={() => onOpenChange(false)}
                        >
                          {i.title}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
