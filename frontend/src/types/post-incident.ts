/**
 * Response metrics, after-action review and improvement actions (W3-RT-POST).
 * Backend: `endpoints/metrics.py`, `models/post_incident.py`.
 */
import type { Versioned } from './incident-tables'

// ─── Metrics ─────────────────────────────────────────────────────────────

export type MetricName =
  | 'dwell_time'
  | 'time_to_respond'
  | 'time_to_contain'
  | 'contain_to_eradicate'
  | 'eradicate_to_recover'
  | 'recover_to_close'
  | 'total_open'

export type MetricTimestampName =
  | 'first_malicious'
  | 'detected'
  | 'responded'
  | 'contained'
  | 'eradicated'
  | 'recovered'
  | 'closed'

/** Where the dwell start came from: manual override, timeline, or hidden (no `timeline:read`). */
export type FirstMaliciousSource = 'override' | 'timeline' | 'restricted' | null

export interface MetricAnomaly {
  metric: MetricName
  reason: 'negative'
  /** The (negative) interval in seconds. */
  seconds: number
}

/** `GET /incidents/<id>/metrics`; durations are seconds, null when unknown. */
export interface IncidentMetrics {
  incident_id: string
  timestamps: Record<MetricTimestampName, string | null>
  durations: Record<MetricName, number | null>
  anomalies: MetricAnomaly[]
  sources: { first_malicious: FirstMaliciousSource }
}

export type MetricsGroupBy = 'none' | 'severity' | 'classification' | 'detection_source'
export type MetricsDateField = 'detected_at' | 'closed_at'

export interface MetricStat {
  /** Seconds; null with fewer than `min_group_size` values. */
  median: number | null
  p90: number | null
  n: number
  /** Incidents whose interval was negative (excluded from median / p90). */
  anomalies: number
}

export type MetricStats = Record<MetricName, MetricStat>

export interface OrgMetricsGroup {
  key: string | null
  n: number
  metrics: MetricStats
}

/** `GET /metrics/incidents`. */
export interface OrgMetrics {
  range: { from: string; to: string; date_field: MetricsDateField }
  group_by: MetricsGroupBy
  metrics: MetricName[]
  min_group_size: number
  overall: { n: number; metrics: MetricStats }
  groups: OrgMetricsGroup[]
}

export interface OrgMetricsParams {
  from: string
  to: string
  group_by?: MetricsGroupBy
  date_field?: MetricsDateField
}

// ─── After-action review ─────────────────────────────────────────────────

export type ContributingCategory =
  | 'people'
  | 'process'
  | 'technology'
  | 'detection'
  | 'communication'
  | 'third_party'
  | 'other'

export type DetectionSource =
  | 'internal_alert'
  | 'threat_hunt'
  | 'user_report'
  | 'third_party'
  | 'law_enforcement'
  | 'other'

export type ReviewStatus = 'draft' | 'final'

export interface ContributingFactor {
  category: ContributingCategory
  description: string
}

export interface IncidentReview extends Versioned {
  id: string
  incident_id: string
  what_went_well: string | null
  what_went_wrong: string | null
  root_cause: string | null
  contributing_factors: ContributingFactor[]
  detection_source: DetectionSource | null
  /** YYYY-MM-DD */
  review_date: string | null
  participants: string[]
  participant_users: { id: string; name: string }[]
  status: ReviewStatus
  finalized_at: string | null
  finalized_by: string | null
  finalized_by_user?: { id: string; name: string } | null
  created_at: string
  updated_at: string | null
}

/** `GET /incidents/<id>/review`. */
export interface ReviewResponse {
  review: IncidentReview | null
  /** The old free-text `lessons_learned`, shown read-only. */
  legacy_lessons_learned: string | null
  /** May finalize / reopen / edit a final review. */
  can_manage: boolean
}

export interface ReviewInput {
  what_went_well?: string | null
  what_went_wrong?: string | null
  root_cause?: string | null
  contributing_factors?: ContributingFactor[]
  detection_source?: DetectionSource | null
  review_date?: string | null
  participants?: string[]
  status?: ReviewStatus
}

// ─── Improvement actions ─────────────────────────────────────────────────

export type ActionStatus = 'open' | 'in_progress' | 'blocked' | 'done' | 'wont_fix'
export type ActionPriority = 'low' | 'medium' | 'high' | 'critical'
export type ControlFramework = 'nist_csf' | 'd3fend' | 'cis' | 'iso27001' | 'other'

export interface ImprovementAction extends Versioned {
  id: string
  incident_id: string | null
  /** "#<n> <title>" snapshot; the only link left once the incident is deleted. */
  incident_ref: string | null
  /** The incident, only when the caller can see it. */
  incident: { id: string; title: string; incident_number: number } | null
  review_id: string | null
  title: string
  description: string | null
  owner_id: string | null
  owner: { id: string; name: string } | null
  team_id: string | null
  due_date: string | null
  status: ActionStatus
  priority: ActionPriority
  category: ContributingCategory | null
  control_framework: ControlFramework | null
  control_ref: string | null
  completed_at: string | null
  created_by: string | null
  created_at: string
  updated_at: string | null
}

export interface ImprovementActionInput {
  title?: string
  description?: string | null
  owner_id?: string | null
  due_date?: string | null
  status?: ActionStatus
  priority?: ActionPriority
  category?: ContributingCategory | null
  control_framework?: ControlFramework | null
  control_ref?: string | null
}
