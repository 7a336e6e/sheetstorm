/**
 * Pure helpers for the provenance form section (W3-PROV): form value <-> API
 * payload, option lists and the clock-skew formatters.
 */
import type {
  ProvenanceFields,
  ProvenanceFormValue,
  ProvenanceLevel,
  ProvenanceRecordKind,
  ProvenanceTimestampType,
  SourceRecordType,
} from '@/types'

export const SOURCE_RECORD_TYPE_OPTIONS: { value: SourceRecordType; label: string }[] = [
  { value: 'file_path', label: 'File path' },
  { value: 'evtx_record', label: 'EVTX record' },
  { value: 'offset', label: 'Offset' },
  { value: 'log_line', label: 'Log line' },
  { value: 'url', label: 'URL' },
  { value: 'registry_key', label: 'Registry key' },
  { value: 'db_row', label: 'Database row' },
  { value: 'other', label: 'Other' },
]

export const TIMESTAMP_TYPE_OPTIONS: { value: ProvenanceTimestampType; label: string }[] = [
  { value: 'modified', label: 'Modified (M)' },
  { value: 'accessed', label: 'Accessed (A)' },
  { value: 'changed', label: 'Changed (C)' },
  { value: 'born', label: 'Born / created (B)' },
  { value: 'logged', label: 'Logged' },
  { value: 'first_seen', label: 'First seen' },
  { value: 'last_seen', label: 'Last seen' },
  { value: 'observed', label: 'Observed' },
  { value: 'other', label: 'Other' },
]

/** Suggestions for the time zone input (any IANA key or `UTC±HH:MM` is accepted). */
export const COMMON_TIMEZONES = [
  'UTC',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Paris',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Australia/Sydney',
  'UTC-05:00',
  'UTC+01:00',
  'UTC+05:30',
] as const

export const LEVEL_LABELS: Record<ProvenanceLevel, string> = {
  none: 'No provenance',
  partial: 'Partial provenance',
  full: 'Full provenance',
  verified: 'Verified provenance',
}

export const KIND_UPDATE_PERMISSION: Record<ProvenanceRecordKind, string> = {
  timeline_event: 'timeline:update',
  network_ioc: 'network_iocs:update',
  host_ioc: 'host_iocs:update',
  malware: 'malware:update',
}

/** Same bound as the backend (`CompromisedHost.CLOCK_SKEW_LIMIT_SECONDS`). */
export const CLOCK_SKEW_LIMIT_SECONDS = 604800

type Text = Exclude<keyof ProvenanceFormValue, 'keep_manual'>
const TEXT_FIELDS: Text[] = [
  'source_artifact_id',
  'source_evidence_id',
  'source_record_type',
  'source_record_ref',
  'raw_timestamp',
  'source_timezone',
  'timestamp_type',
  'extraction_tool',
  'extraction_tool_version',
  'fold',
]

export function emptyProvenance(): ProvenanceFormValue {
  return {
    source_artifact_id: '',
    source_evidence_id: '',
    source_record_type: '',
    source_record_ref: '',
    raw_timestamp: '',
    source_timezone: '',
    timestamp_type: '',
    extraction_tool: '',
    extraction_tool_version: '',
    fold: '',
    keep_manual: false,
  }
}

export function provenanceFromRecord(record: ProvenanceFields | null | undefined): ProvenanceFormValue {
  const v = emptyProvenance()
  if (!record) return v
  for (const key of TEXT_FIELDS) {
    if (key === 'fold') continue
    const value = record[key as keyof ProvenanceFields]
    if (typeof value === 'string') v[key] = value
  }
  return v
}

/** Anything entered? (decides whether the section starts expanded). */
export function hasProvenance(v: ProvenanceFormValue): boolean {
  return TEXT_FIELDS.some((k) => k !== 'fold' && v[k].trim() !== '')
}

/**
 * API keys for the provenance part of a create/update body.
 *
 * Only fields that differ from `initial` are sent (every field on create), so
 * editing an unrelated column never re-runs the server's timestamp derivation.
 * Cleared fields are sent as null. `keep_manual` records the entered
 * timestamp as the analyst's own (`timestamp_derivation: 'manual'`).
 */
export function provenancePayload(
  value: ProvenanceFormValue,
  initial?: ProvenanceFormValue,
): Record<string, string | number | null> {
  const out: Record<string, string | number | null> = {}
  for (const key of TEXT_FIELDS) {
    if (key === 'fold') continue
    const next = value[key].trim()
    if (initial ? next !== initial[key].trim() : next !== '') out[key] = next === '' ? null : next
  }
  if (value.fold === '0' || value.fold === '1') out.fold = Number(value.fold)
  if (value.keep_manual) out.timestamp_derivation = 'manual'
  return out
}

/** `+5m 0s`, `-1h 2m 3s`, `0s`; '' for null. Sign = host clock minus true UTC. */
export function formatSkew(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return ''
  const sign = seconds < 0 ? '-' : seconds > 0 ? '+' : ''
  const total = Math.abs(Math.trunc(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const parts = [h ? `${h}h` : '', h || m ? `${m}m` : '', `${s}s`].filter(Boolean)
  return `${sign}${parts.join(' ')}`
}

/** Seconds from the editor's sign + h/m/s inputs; NaN when any part is invalid. */
export function skewFromParts(sign: 1 | -1, hours: string, minutes: string, seconds: string): number {
  const parts = [hours, minutes, seconds].map((p) => (p.trim() === '' ? 0 : Number(p)))
  if (parts.some((p) => !Number.isInteger(p) || p < 0)) return NaN
  const total = parts[0] * 3600 + parts[1] * 60 + parts[2]
  return total === 0 ? 0 : sign * total
}

export function skewToParts(seconds: number | null | undefined): {
  sign: 1 | -1
  hours: string
  minutes: string
  seconds: string
} {
  const value = seconds ?? 0
  const total = Math.abs(Math.trunc(value))
  return {
    sign: value < 0 ? -1 : 1,
    hours: String(Math.floor(total / 3600)),
    minutes: String(Math.floor((total % 3600) / 60)),
    seconds: String(total % 60),
  }
}
