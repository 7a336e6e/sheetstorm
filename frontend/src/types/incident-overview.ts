/**
 * Incident Overview and dashboard aggregates (W2-DFIR-B).
 *
 * `IncidentSummary` comes with `GET /incidents/<id>` only (never in lists).
 * Each part is null when the caller lacks the entity's read permission.
 */
import type { TLPLevel } from './index'

/**
 * IR milestones editable on the Overview, in the order they must occur.
 * `responded_at` (W3-RT-POST) is editable but outside the strict chain: it
 * must only not precede `detected_at`.
 */
export type MilestoneField =
  | 'first_malicious_at'
  | 'detected_at'
  | 'responded_at'
  | 'contained_at'
  | 'eradicated_at'
  | 'recovered_at'
  | 'closed_at'

export interface SummaryLeadCounts {
  total: number
  open: number
  /** `open` plus every lead outcome present. */
  by_outcome: Record<string, number>
}

export interface AcquisitionCounts {
  disk_imaged: number
  memory_captured: number
  logs_collected: number
  forensically_sound: number
}

export interface IncidentSummary {
  first_event_at: string | null
  last_event_at: string | null
  earliest_detection_at: string | null
  leads: SummaryLeadCounts | null
  hosts_by_triage: Record<string, number> | null
  acquisition: AcquisitionCounts | null
}

/** Extra fields of the single-incident GET. */
export interface IncidentOverviewFields {
  summary?: IncidentSummary | null
}

/** Body of `PUT /incidents/<id>` for the Overview editors. */
export type IncidentOverviewUpdate = Partial<Record<MilestoneField, string | null>> & {
  executive_summary?: string | null
  lessons_learned?: string | null
}

export interface DashboardMitreTactic {
  tactic: string
  count: number
  techniques: Record<string, number>
}

export interface DashboardMitreStats {
  events_total: number
  events_mapped: number
  tactics: DashboardMitreTactic[]
}

export interface DashboardStats {
  incidents: {
    total: number
    active: number
    closed: number
    critical: number
    created_7d: number
    created_30d: number
    by_severity: Record<string, number>
    by_status: Record<string, number>
    /** Non-closed incidents by phase number ('1'..'6'). */
    by_phase_open: Record<string, number>
    by_tlp: Partial<Record<TLPLevel, number>>
  }
  /** null without `timeline:read`. */
  mitre: DashboardMitreStats | null
  dfir: {
    /** null without `tasks:read`. */
    open_leads: number | null
    /** null without `hosts:read`. */
    hosts_by_triage: Record<string, number> | null
  }
}
