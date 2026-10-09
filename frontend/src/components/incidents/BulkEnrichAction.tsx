"use client"

/**
 * "Enrich (n)" bulk action for the Network IOCs and Malware tabs (W3-DFIR-C).
 *
 * Enrichment sends indicator values to third-party providers configured for
 * the organization, so it goes through a confirmation that shows the
 * incident's TLP (server-side block: `services/egress_policy.py`):
 * - TLP:RED: shown as blocked, never sent (no setting unblocks it);
 * - TLP:AMBER+STRICT: blocked unless the organization allows it; when allowed
 *   a destructive dialog with an explicit acknowledgement checkbox;
 * - otherwise a plain confirmation.
 * The result dialog lists value / status / summary per indicator.
 */
import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ShieldOff, Sparkles } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { isAbortError } from '@/lib/api'
import { buildEnrichItems, enrichmentGate, exportsApi, TLP_LABELS } from '@/lib/endpoints/exports'
import { organization } from '@/lib/endpoints/rbac'
import { notifyError } from '@/lib/errors'
import { useIncidentStore } from '@/lib/store'
import type { BulkEnrichResponse, EnrichResult } from '@/types'

interface Props {
  incidentId: string
  /** Indicator values of the selected rows (hashes, IPs, domains, ...). */
  values: Array<string | null | undefined>
  /** Singular noun for the dialog copy, e.g. `network IOC`. */
  noun: string
  /** Called after a successful run (clears the selection). */
  onDone?: () => void
}

const STATUS_LABEL: Record<EnrichResult['status'], string> = {
  success: 'Enriched',
  error: 'Failed',
  blocked: 'Blocked',
}

export function BulkEnrichAction({ incidentId, values, noun, onDone }: Props) {
  const tlp = useIncidentStore((s) => (s.currentIncident?.id === incidentId ? s.currentIncident.tlp : undefined))
  const { items, skipped } = useMemo(() => buildEnrichItems(values), [values])
  const [open, setOpen] = useState(false)
  const [allowStrict, setAllowStrict] = useState<boolean | null>(null)
  const [acknowledged, setAcknowledged] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BulkEnrichResponse | null>(null)

  // The organization setting that lets AMBER+STRICT values be enriched (readable by every user).
  useEffect(() => {
    if (!open || allowStrict !== null || tlp !== 'amber_strict') return
    let cancelled = false
    organization
      .get()
      .then((org) => {
        if (!cancelled) setAllowStrict(org.settings?.enrichment_allow_amber_strict === true)
      })
      .catch((err) => {
        if (!cancelled && !isAbortError(err)) setAllowStrict(false) // fail closed; the server decides anyway
      })
    return () => {
      cancelled = true
    }
  }, [open, allowStrict, tlp])

  // An unknown TLP is treated like AMBER+STRICT (acknowledge); the server has the last word.
  const gate = enrichmentGate(tlp ?? 'amber_strict', allowStrict === true)
  const checkingPolicy = open && tlp === 'amber_strict' && allowStrict === null
  const tlpText = tlp ? TLP_LABELS[tlp] ?? tlp.toUpperCase() : 'the incident TLP'

  const openDialog = () => {
    setAcknowledged(false)
    setOpen(true)
  }

  const run = async () => {
    setRunning(true)
    try {
      const res = await exportsApi.bulkEnrich(incidentId, items)
      setOpen(false)
      setResult(res)
    } catch (err) {
      notifyError(err, `enrich the selected ${noun}s`)
      setOpen(false)
    } finally {
      setRunning(false)
    }
  }

  // The selection (and with it this bar) is cleared only once the results were seen.
  const closeResult = () => {
    setResult(null)
    onDone?.()
  }

  const destructive = gate === 'acknowledge'
  const canSend = items.length > 0 && !checkingPolicy && gate !== 'blocked' && (!destructive || acknowledged)

  return (
    <>
      <Button size="sm" variant="outline" onClick={openDialog} disabled={values.length === 0}>
        <Sparkles className="mr-2 h-4 w-4" />
        Enrich ({values.length})
      </Button>

      <Dialog open={open} onOpenChange={(o) => !running && setOpen(o)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {gate === 'blocked' ? (
                <ShieldOff className="h-5 w-5 text-destructive" />
              ) : destructive ? (
                <AlertTriangle className="h-5 w-5 text-destructive" />
              ) : null}
              {gate === 'blocked' ? 'Enrichment blocked' : `Enrich ${items.length} ${noun}${items.length === 1 ? '' : 's'}?`}
            </DialogTitle>
            <DialogDescription>
              Incident TLP: <strong className="font-medium text-foreground">{tlpText}</strong>
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-3 text-sm">
            {checkingPolicy && <p className="text-muted-foreground">Checking your organization&apos;s policy…</p>}

            {gate === 'blocked' && !checkingPolicy && (
              <p role="alert">
                {tlp === 'red'
                  ? 'TLP:RED data is never sent to external services. This cannot be changed in settings.'
                  : `Your organization does not allow ${tlpText} indicator values to be sent to external enrichment services.`}
              </p>
            )}

            {gate !== 'blocked' && !checkingPolicy && (
              <>
                <p>
                  The {items.length} value{items.length === 1 ? '' : 's'} will be sent to the third-party
                  threat-intelligence providers configured for your organization (for example VirusTotal or
                  AbuseIPDB). Values that also appear in a TLP-restricted incident are left out by the server.
                </p>
                {skipped > 0 && (
                  <p className="text-muted-foreground">
                    {skipped} selected value{skipped === 1 ? ' is' : 's are'} not an IP, domain, e-mail or hash and will be skipped.
                  </p>
                )}
                {destructive && (
                  <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3">
                    <Checkbox
                      id="enrich-ack"
                      checked={acknowledged}
                      onCheckedChange={(c) => setAcknowledged(c === true)}
                      className="mt-0.5"
                    />
                    <Label htmlFor="enrich-ack" className="cursor-pointer text-sm font-normal leading-snug">
                      I understand these {tlpText} indicator values will leave the organization and be sent to
                      third parties.
                    </Label>
                  </div>
                )}
              </>
            )}
          </DialogBody>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={running}>
              {gate === 'blocked' && !checkingPolicy ? 'Close' : 'Cancel'}
            </Button>
            {gate !== 'blocked' && (
              <Button
                variant={destructive ? 'destructive' : 'default'}
                onClick={() => void run()}
                disabled={!canSend}
                loading={running}
              >
                {destructive ? 'Send for enrichment' : 'Enrich'}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={result !== null} onOpenChange={(o) => !o && closeResult()}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Enrichment results</DialogTitle>
            {result && (
              <DialogDescription>
                {result.enriched} enriched, {result.failed} failed, {result.blocked} blocked
                {result.providers.length > 0 && <> · providers: {result.providers.join(', ')}</>}
              </DialogDescription>
            )}
          </DialogHeader>
          <DialogBody>
            {result && (
              <table className="w-full text-sm" aria-label="Enrichment results">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">Value</th>
                    <th className="py-2 pr-3 font-medium">Status</th>
                    <th className="py-2 font-medium">Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {result.results.map((r) => (
                    <tr key={`${r.type}:${r.value}`} className="border-b border-border/50 align-top">
                      <td className="py-2 pr-3 font-mono text-xs break-all">{r.value}</td>
                      <td className="py-2 pr-3">
                        <Badge variant={r.status === 'success' ? 'success' : r.status === 'blocked' ? 'warning' : 'destructive'}>{STATUS_LABEL[r.status]}</Badge>
                      </td>
                      <td className="py-2 text-muted-foreground">{r.summary ?? r.error ?? '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={closeResult}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
