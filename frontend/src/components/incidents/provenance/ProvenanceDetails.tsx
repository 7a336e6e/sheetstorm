"use client"

import { ShieldCheck } from 'lucide-react'
import { Timestamp } from '@/components/ui/timestamp'
import type { ProvenanceFields } from '@/types'
import { LEVEL_LABELS, SOURCE_RECORD_TYPE_OPTIONS, TIMESTAMP_TYPE_OPTIONS, formatSkew } from './provenance-form'

const label = (list: { value: string; label: string }[], v?: string | null) =>
  list.find((o) => o.value === v)?.label ?? v

/**
 * Read-only provenance block for an expanded row. Every value is rendered as
 * text (a URL reference is never a link).
 */
export function ProvenanceDetails({ record }: { record: ProvenanceFields }) {
  const level = record.provenance_level ?? 'none'
  const rows: [string, React.ReactNode][] = []
  if (record.source_evidence_id) rows.push(['Source', 'Evidence item (see the evidence register)'])
  else if (record.source_artifact_id) rows.push(['Source', 'Artifact'])
  if (record.source_record_ref || record.source_record_type) {
    rows.push([
      'Record',
      <span key="ref" className="break-all">
        {label(SOURCE_RECORD_TYPE_OPTIONS, record.source_record_type)}
        {record.source_record_ref ? <span className="font-mono">{record.source_record_type ? ': ' : ''}{record.source_record_ref}</span> : null}
      </span>,
    ])
  }
  if (record.raw_timestamp) {
    rows.push([
      'Raw timestamp',
      <span key="raw" className="font-mono">
        {record.raw_timestamp}
        {record.source_timezone ? ` (${record.source_timezone})` : ''}
        {record.timestamp_type ? ` · ${label(TIMESTAMP_TYPE_OPTIONS, record.timestamp_type)}` : ''}
      </span>,
    ])
  }
  if (record.timestamp_derivation) {
    rows.push([
      'Derivation',
      record.timestamp_derivation === 'computed' && record.clock_skew_applied_seconds
        ? `computed, host skew ${formatSkew(record.clock_skew_applied_seconds)} removed`
        : record.timestamp_derivation,
    ])
  }
  if (record.extraction_tool) {
    rows.push(['Tool', `${record.extraction_tool}${record.extraction_tool_version ? ` ${record.extraction_tool_version}` : ''}`])
  }

  return (
    <div>
      <h4 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <ShieldCheck className="h-3 w-3" aria-hidden="true" />
        Provenance · {LEVEL_LABELS[level]}
      </h4>
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[8rem_1fr]">
        {rows.map(([name, value]) => (
          <div key={name} className="contents">
            <dt className="text-xs text-muted-foreground">{name}</dt>
            <dd className="min-w-0">{value}</dd>
          </div>
        ))}
        {level === 'verified' && (
          <div className="contents">
            <dt className="text-xs text-muted-foreground">Verified by</dt>
            <dd>
              {record.provenance_verifier?.name ?? 'a second analyst'}
              {record.provenance_verified_at && (<> · <Timestamp value={record.provenance_verified_at} /></>)}
            </dd>
          </div>
        )}
      </dl>
    </div>
  )
}
