/**
 * DFIR columns, triage and leads (W2-DFIR-A).
 *
 * Evidence links use one shape everywhere (backend `services/evidence_refs.py`):
 * `{ evidence_type, evidence_id }`. Labels are resolved by the server per
 * request (`Task.evidence`); client-supplied labels are never stored.
 */
import type { LeadOutcome, Task, TriageStatus } from './index'

/** Evidence types a task may link to (aliases are normalised server-side). */
export type TaskEvidenceType =
  | 'timeline_event'
  | 'host'
  | 'account'
  | 'network_ioc'
  | 'host_ioc'
  | 'malware'
  | 'artifact'
  | 'evidence_item'

export interface EvidenceRef {
  evidence_type: TaskEvidenceType | string
  evidence_id: string
}

/** A server-resolved evidence ref. */
export interface TaskEvidence extends EvidenceRef {
  /** null when the record is missing or the user may not read its type. */
  label: string | null
  /** The record was deleted (or never existed in this incident). */
  missing: boolean
  /** The user lacks the read permission for this evidence type. */
  restricted?: boolean
}

/** A task row as served by `GET /incidents/<id>/tasks` (W2-DFIR-A fields). */
export type DfirTask = Task & {
  evidence?: TaskEvidence[]
  updated_at?: string | null
  parent_task_id?: string | null
  version?: number
}

/** `lead_outcome` filter values: `open` = no outcome yet. */
export type LeadOutcomeFilter = 'open' | LeadOutcome

/** `lead_counts=true` extra on the tasks list. */
export type LeadCounts = Record<LeadOutcomeFilter, number>

export type AcquisitionFlag = 'disk_imaged' | 'memory_captured' | 'logs_collected' | 'forensically_sound'

/** `PATCH /incidents/<id>/hosts/bulk` body (max 500 ids). */
export interface BulkHostUpdate {
  host_ids: string[]
  triage_status?: TriageStatus
  containment_status?: string
}

export interface BulkHostUpdateResult<H = unknown> {
  updated: number
  items: H[]
}
