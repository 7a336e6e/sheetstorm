"use client"

import { Shield, ShieldCheck, ShieldHalf, ShieldOff } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Timestamp } from '@/components/ui/timestamp'
import { cn } from '@/lib/utils'
import type { ProvenanceFields, ProvenanceLevel } from '@/types'
import { LEVEL_LABELS, SOURCE_RECORD_TYPE_OPTIONS, formatSkew } from './provenance-form'

const LEVEL_STYLE: Record<ProvenanceLevel, { icon: typeof Shield; className: string }> = {
  none: { icon: ShieldOff, className: 'text-muted-foreground/50' },
  partial: { icon: ShieldHalf, className: 'text-amber-400' },
  full: { icon: Shield, className: 'text-sky-400' },
  verified: { icon: ShieldCheck, className: 'text-emerald-400' },
}

const recordTypeLabel = (t?: string | null) => SOURCE_RECORD_TYPE_OPTIONS.find((o) => o.value === t)?.label ?? t

function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2 text-xs">
      <dt className="w-24 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

/**
 * Provenance level icon for a table row; the tooltip lists what is known
 * (record reference as plain text, raw timestamp + zone, derivation, skew,
 * tool, verifier). Verification itself is a row action, not a tooltip button.
 */
export function ProvenanceBadge({ record, className }: { record: ProvenanceFields; className?: string }) {
  const level: ProvenanceLevel = record.provenance_level ?? 'none'
  const { icon: Icon, className: tone } = LEVEL_STYLE[level]
  const label = LEVEL_LABELS[level]
  const derivation = record.timestamp_derivation
  const hasDetail = level !== 'none'

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={label}
            className={cn('inline-flex items-center rounded p-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', tone, className)}
            onClick={(e) => e.stopPropagation()}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-sm space-y-1.5">
          <p className="text-sm font-medium">{label}</p>
          {hasDetail && (
            <dl className="space-y-1">
              {(record.source_evidence_id || record.source_artifact_id) && (
                <Line label="Source">{record.source_evidence_id ? 'Evidence item linked' : 'Artifact linked'}</Line>
              )}
              {record.source_record_ref && (
                <Line label="Record">
                  {recordTypeLabel(record.source_record_type) ? `${recordTypeLabel(record.source_record_type)}: ` : ''}
                  <span className="font-mono">{record.source_record_ref}</span>
                </Line>
              )}
              {record.raw_timestamp && (
                <Line label="Raw time">
                  <span className="font-mono">{record.raw_timestamp}</span>
                  {record.source_timezone ? ` (${record.source_timezone})` : ''}
                </Line>
              )}
              {derivation && (
                <Line label="Derivation">
                  {derivation}
                  {derivation === 'computed' && record.clock_skew_applied_seconds
                    ? `, host skew ${formatSkew(record.clock_skew_applied_seconds)} removed`
                    : ''}
                </Line>
              )}
              {record.extraction_tool && (
                <Line label="Tool">
                  {record.extraction_tool}
                  {record.extraction_tool_version ? ` ${record.extraction_tool_version}` : ''}
                </Line>
              )}
              {level === 'verified' && (
                <Line label="Verified">
                  {record.provenance_verifier?.name ?? 'a second analyst'}
                  {record.provenance_verified_at && (
                    <>
                      {' · '}
                      <Timestamp value={record.provenance_verified_at} />
                    </>
                  )}
                </Line>
              )}
            </dl>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
