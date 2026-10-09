/**
 * Record provenance + host clock skew (W3-PROV).
 *
 * Mirrors backend `models/provenance.py` (the four record types share these
 * columns) and `services/provenance_service.py`. `ProvenanceFields` is mixed
 * into `TimelineEvent`, `NetworkIndicator`, `HostBasedIndicator` and
 * `MalwareTool` in `types/index.ts`.
 */

export type SourceRecordType =
  | 'file_path'
  | 'evtx_record'
  | 'offset'
  | 'log_line'
  | 'url'
  | 'registry_key'
  | 'db_row'
  | 'other'

/** MACB + log semantics. */
export type ProvenanceTimestampType =
  | 'modified'
  | 'accessed'
  | 'changed'
  | 'born'
  | 'logged'
  | 'first_seen'
  | 'last_seen'
  | 'observed'
  | 'other'

/** How the normalized UTC value was obtained. null = legacy, read as `manual`. */
export type TimestampDerivation = 'manual' | 'computed' | 'imported'

export type ProvenanceLevel = 'none' | 'partial' | 'full' | 'verified'

/** Record kinds the verify endpoint accepts. */
export type ProvenanceRecordKind = 'timeline_event' | 'network_ioc' | 'host_ioc' | 'malware'

export interface ProvenanceFields {
  source_artifact_id?: string | null
  /** FK evidence_items; preferred over the artifact link in the UI. */
  source_evidence_id?: string | null
  source_record_type?: SourceRecordType | null
  /** Stored and shown as text; never fetched or rendered as a link. */
  source_record_ref?: string | null
  /** The timestamp exactly as found in the source. */
  raw_timestamp?: string | null
  /** IANA key, `UTC` or `UTC±HH:MM`. */
  source_timezone?: string | null
  timestamp_type?: ProvenanceTimestampType | null
  timestamp_derivation?: TimestampDerivation | null
  /** Snapshot of the host skew used when the UTC value was computed. */
  clock_skew_applied_seconds?: number | null
  extraction_tool?: string | null
  extraction_tool_version?: string | null
  provenance_verified_by?: string | null
  provenance_verified_at?: string | null
  provenance_level?: ProvenanceLevel
  provenance_verifier?: { id: string; name: string | null } | null
}

/** Form state of `ProvenanceSection` (empty string = not set). */
export interface ProvenanceFormValue {
  source_artifact_id: string
  source_evidence_id: string
  source_record_type: string
  source_record_ref: string
  raw_timestamp: string
  source_timezone: string
  timestamp_type: string
  extraction_tool: string
  extraction_tool_version: string
  /** DST-ambiguous local time: '0' = first occurrence, '1' = second, '' = unset. */
  fold: string
  /** Keep the entered timestamp although it differs from the computed one. */
  keep_manual: boolean
}

/** `POST /incidents/<id>/provenance/normalize-preview` */
export interface NormalizePreview {
  utc: string
  skew_applied: number
  timezone_used: string
  offset_seconds: number
}

export interface NormalizePreviewRequest {
  raw_timestamp: string
  source_timezone?: string
  host_id?: string
  fold?: 0 | 1
}

/** One row of a clock-skew re-normalization (dry run or applied). */
export interface ClockSkewChange {
  kind: ProvenanceRecordKind
  id: string
  field: string
  old: string
  new: string
  old_skew: number
  new_skew: number
}

export interface ClockSkewReapplyResult {
  dry_run: boolean
  count: number
  changes: ClockSkewChange[]
  truncated: boolean
}

export interface ClockSkewUpdate {
  /** Host clock minus true UTC, seconds, within ±604800; null clears. */
  clock_skew_seconds?: number | null
  clock_skew_basis?: string | null
  /** IANA key or `UTC±HH:MM`; null clears. */
  timezone?: string | null
}

/** Skew fields on a host (also see `CompromisedHost`). */
export interface HostClockSkew {
  clock_skew_seconds?: number | null
  clock_skew_basis?: string | null
  clock_skew_measured_by?: string | null
  clock_skew_measured_at?: string | null
  clock_skew_measurer?: { id: string; name: string | null } | null
  timezone?: string | null
}
