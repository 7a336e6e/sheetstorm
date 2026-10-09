"use client"

import { useEffect, useId, useState } from 'react'
import { ChevronDown, ChevronRight, ShieldHalf } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Timestamp } from '@/components/ui/timestamp'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { EntityPicker } from '@/components/ui/entity-picker'
import { usePermission } from '@/components/auth/permission-gate'
import { isAbortError, isApiError } from '@/lib/api'
import { describeError } from '@/lib/errors'
import { provenanceApi } from '@/lib/endpoints/provenance'
import type { NormalizePreview, ProvenanceFormValue } from '@/types'
import {
  COMMON_TIMEZONES,
  SOURCE_RECORD_TYPE_OPTIONS,
  TIMESTAMP_TYPE_OPTIONS,
  formatSkew,
  hasProvenance,
} from './provenance-form'

/** Debounce of the live "Normalized UTC" preview (a request per keystroke otherwise). */
export const PREVIEW_DEBOUNCE_MS = 400

const NONE = '__none__'
/** Computed vs entered timestamps within this many ms count as equal (server: 1 s). */
const SAME_MS = 1000

interface EvidenceOption {
  id: string
  evidence_number?: string
  title?: string
}

export interface ProvenanceSectionProps {
  incidentId: string
  value: ProvenanceFormValue
  onChange: (next: ProvenanceFormValue) => void
  /** The form's main timestamp (ISO, UTC) to compare with the computed value. */
  timestamp?: string | null
  /** "Use computed": fill the form's main timestamp field. */
  onUseComputed?: (utcIso: string) => void
  /** Selected host: its clock skew and time zone feed the preview. */
  hostId?: string | null
  /** Label of the current evidence item when editing (else fetched on demand). */
  evidenceLabel?: string
  /** Which timestamp the raw value stands for (shown in the hint). */
  timestampLabel?: string
  className?: string
}

/**
 * Collapsible provenance fields of an event / IOC form: source evidence item,
 * exact record reference (text only, never a link), the raw timestamp as found
 * plus its time zone and MACB type, and the extraction tool. A debounced
 * preview shows the UTC value the server will derive (raw + zone + host skew);
 * "Use computed" copies it into the form's timestamp field.
 */
export function ProvenanceSection({
  incidentId,
  value,
  onChange,
  timestamp,
  onUseComputed,
  hostId,
  evidenceLabel,
  timestampLabel = 'timestamp',
  className,
}: ProvenanceSectionProps) {
  const [open, setOpen] = useState(() => hasProvenance(value))
  const panelId = useId()
  const datalistId = useId()
  const canReadEvidence = usePermission('artifacts:read')
  const set = (patch: Partial<ProvenanceFormValue>) => onChange({ ...value, ...patch })

  const raw = value.raw_timestamp.trim()
  const zone = value.source_timezone.trim()
  const fold = value.fold
  // The latest answer, tagged with the request it belongs to so a stale one
  // (or one for a cleared field) is never shown.
  const requestKey = `${raw}|${zone}|${hostId ?? ''}|${fold}`
  const [answer, setAnswer] = useState<{
    key: string
    preview: NormalizePreview | null
    error: { message: string; ambiguous: boolean } | null
  } | null>(null)
  const current = open && raw && answer?.key === requestKey ? answer : null
  const preview = current?.preview ?? null
  const previewError = current?.error ?? null

  useEffect(() => {
    if (!open || !raw) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      provenanceApi
        .normalizePreview(
          incidentId,
          {
            raw_timestamp: raw,
            ...(zone ? { source_timezone: zone } : {}),
            ...(hostId ? { host_id: hostId } : {}),
            ...(fold === '0' || fold === '1' ? { fold: Number(fold) as 0 | 1 } : {}),
          },
          { signal: controller.signal },
        )
        .then((res) => setAnswer({ key: requestKey, preview: res, error: null }))
        .catch((err: unknown) => {
          if (isAbortError(err)) return
          setAnswer({
            key: requestKey,
            preview: null,
            error: {
              message: describeError(err).description,
              ambiguous: isApiError(err) && err.code === 'ambiguous_local_time',
            },
          })
        })
    }, PREVIEW_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [open, incidentId, raw, zone, hostId, fold, requestKey])

  const differs =
    !!preview && !!timestamp && Math.abs(new Date(preview.utc).getTime() - new Date(timestamp).getTime()) > SAME_MS

  return (
    <div className={className}>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="-ml-3 gap-2"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        <ShieldHalf className="h-4 w-4" />
        Provenance
        {!open && hasProvenance(value) && <span className="text-xs text-muted-foreground">(recorded)</span>}
      </Button>

      {open && (
        <fieldset id={panelId} className="mt-2 space-y-4 rounded-md border border-white/10 p-3">
          <legend className="sr-only">Provenance</legend>

          <div className="space-y-2">
            <Label>Source evidence item</Label>
            {canReadEvidence ? (
              <EntityPicker<EvidenceOption>
                value={value.source_evidence_id || null}
                onChange={(id) => set({ source_evidence_id: id ?? '' })}
                endpoint={`/incidents/${incidentId}/evidence`}
                getId={(i) => i.id}
                getLabel={(i) => [i.evidence_number, i.title].filter(Boolean).join(' ') || i.id}
                valueLabel={evidenceLabel}
                itemEndpoint={(id) => `/incidents/${incidentId}/evidence/${id}`}
                ariaLabel="Source evidence item"
                placeholder="Search registered evidence…"
              />
            ) : (
              <p className="text-xs text-muted-foreground">You need access to the evidence register to link a source.</p>
            )}
            {!value.source_evidence_id && value.source_artifact_id && (
              <p className="text-xs text-muted-foreground">Linked to an artifact (set through the API); kept as is.</p>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-[10rem_1fr]">
            <div className="space-y-2">
              <Label>Record type</Label>
              <Select
                value={value.source_record_type || NONE}
                onValueChange={(v) => set({ source_record_type: v === NONE ? '' : v })}
              >
                <SelectTrigger aria-label="Record type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>—</SelectItem>
                  {SOURCE_RECORD_TYPE_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor={`${panelId}-ref`}>Record reference</Label>
              <Input
                id={`${panelId}-ref`}
                value={value.source_record_ref}
                maxLength={1000}
                onChange={(e) => set({ source_record_ref: e.target.value })}
                placeholder="Security.evtx EventRecordID=48213, $MFT @0x1A2B00, line 4411…"
              />
              <p className="text-xs text-muted-foreground">Stored as text. URLs are never fetched or linked.</p>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="space-y-2 sm:col-span-1">
              <Label htmlFor={`${panelId}-raw`}>Raw timestamp</Label>
              <Input
                id={`${panelId}-raw`}
                value={value.raw_timestamp}
                maxLength={100}
                onChange={(e) => set({ raw_timestamp: e.target.value, fold: '' })}
                placeholder="2026-10-01 14:05:00"
                aria-describedby={`${panelId}-raw-help`}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={`${panelId}-tz`}>Source time zone</Label>
              <Input
                id={`${panelId}-tz`}
                value={value.source_timezone}
                maxLength={64}
                list={datalistId}
                onChange={(e) => set({ source_timezone: e.target.value, fold: '' })}
                placeholder="Europe/Berlin or UTC+05:30"
              />
              <datalist id={datalistId}>
                {COMMON_TIMEZONES.map((tz) => <option key={tz} value={tz} />)}
              </datalist>
            </div>
            <div className="space-y-2">
              <Label>Timestamp type</Label>
              <Select
                value={value.timestamp_type || NONE}
                onValueChange={(v) => set({ timestamp_type: v === NONE ? '' : v })}
              >
                <SelectTrigger aria-label="Timestamp type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>—</SelectItem>
                  {TIMESTAMP_TYPE_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <p id={`${panelId}-raw-help`} className="-mt-2 text-xs text-muted-foreground">
            Enter it exactly as found (ISO 8601 avoids day/month ambiguity). Without an offset the source time zone,
            or the host&apos;s, is required.
          </p>

          {raw && (
            <div className="space-y-2 rounded-md bg-white/[0.03] px-3 py-2 text-sm" aria-live="polite" data-testid="provenance-preview">
              {preview && (
                <p>
                  <span className="text-muted-foreground">Normalized UTC: </span>
                  <Timestamp value={preview.utc} mode="utc" className="font-medium" />
                  <span className="ml-2 text-xs text-muted-foreground">
                    {preview.timezone_used}
                    {preview.skew_applied ? `, host clock skew ${formatSkew(preview.skew_applied)} removed` : ''}
                  </span>
                </p>
              )}
              {previewError && <p className="text-amber-500">{previewError.message}</p>}
              {previewError?.ambiguous && (
                <div className="space-y-1">
                  <Label>This local time happens twice</Label>
                  <Select value={value.fold || NONE} onValueChange={(v) => set({ fold: v === NONE ? '' : v })}>
                    <SelectTrigger aria-label="Which occurrence"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>Choose…</SelectItem>
                      <SelectItem value="0">First (before the clocks went back)</SelectItem>
                      <SelectItem value="1">Second (after the clocks went back)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}
              {differs && preview && (
                <div className="space-y-2">
                  <p className="text-amber-500">
                    The {timestampLabel} above differs from the computed value.
                  </p>
                  <div className="flex flex-wrap items-center gap-3">
                    {onUseComputed && (
                      <Button type="button" size="sm" variant="outline" onClick={() => onUseComputed(preview.utc)}>
                        Use computed
                      </Button>
                    )}
                    <label className="flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={value.keep_manual}
                        onChange={(e) => set({ keep_manual: e.target.checked })}
                        className="rounded bg-white/10 border-white/20"
                      />
                      Keep my {timestampLabel} (record it as manual)
                    </label>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_10rem]">
            <div className="space-y-2">
              <Label htmlFor={`${panelId}-tool`}>Extraction tool</Label>
              <Input
                id={`${panelId}-tool`}
                value={value.extraction_tool}
                maxLength={150}
                onChange={(e) => set({ extraction_tool: e.target.value })}
                placeholder="EvtxECmd"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={`${panelId}-toolv`}>Tool version</Label>
              <Input
                id={`${panelId}-toolv`}
                value={value.extraction_tool_version}
                maxLength={50}
                onChange={(e) => set({ extraction_tool_version: e.target.value })}
                placeholder="1.5.0.0"
              />
            </div>
          </div>
        </fieldset>
      )}
    </div>
  )
}
