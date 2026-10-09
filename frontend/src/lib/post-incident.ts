/**
 * Pure helpers for the metrics and post-incident review UI (W3-RT-POST):
 * metric definitions, duration formatting, date presets and option lists.
 */
import { formatDuration } from '@/lib/time'
import type {
  ActionPriority,
  ActionStatus,
  ContributingCategory,
  ControlFramework,
  DetectionSource,
  ImprovementAction,
  MetricName,
  MetricsGroupBy,
} from '@/types'

export interface MetricDef {
  key: MetricName
  label: string
  /** What it measures, for the tooltip. */
  hint: string
}

export const METRIC_DEFS: readonly MetricDef[] = [
  { key: 'dwell_time', label: 'Dwell time', hint: 'First malicious activity to detection' },
  { key: 'time_to_respond', label: 'Time to respond', hint: 'Detection to first response' },
  { key: 'time_to_contain', label: 'Time to contain', hint: 'Detection to containment' },
  { key: 'contain_to_eradicate', label: 'Contain to eradicate', hint: 'Containment to eradication' },
  { key: 'eradicate_to_recover', label: 'Eradicate to recover', hint: 'Eradication to recovery' },
  { key: 'recover_to_close', label: 'Recover to close', hint: 'Recovery to closure' },
  { key: 'total_open', label: 'Total open', hint: 'Detection to closure (or now, while open)' },
]

export const METRIC_LABELS = Object.fromEntries(METRIC_DEFS.map((m) => [m.key, m.label])) as Record<MetricName, string>

/** `3d 4h` for a number of seconds; an em dash when unknown. */
export function formatSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—'
  return formatDuration(seconds * 1000)
}

/** Bar width in percent (0..100, at least 2 for a visible non-zero bar). */
export function barPercent(value: number | null | undefined, max: number): number {
  if (value === null || value === undefined || !Number.isFinite(value) || max <= 0) return 0
  if (value <= 0) return 0
  return Math.min(100, Math.max(2, Math.round((value / max) * 100)))
}

// ─── Date ranges (org metrics) ───────────────────────────────────────────

export const MAX_RANGE_DAYS = 731

export const RANGE_PRESETS = [
  { id: '30', label: 'Last 30 days', days: 30 },
  { id: '90', label: 'Last 90 days', days: 90 },
  { id: '365', label: 'Last 12 months', days: 365 },
] as const

const DAY_MS = 86_400_000
const ymd = (d: Date) => d.toISOString().slice(0, 10)

/** `{from, to}` as UTC dates (`YYYY-MM-DD`), `to` = today, covering `days` days. */
export function presetRange(days: number, now: Date = new Date()): { from: string; to: string } {
  return { from: ymd(new Date(now.getTime() - (days - 1) * DAY_MS)), to: ymd(now) }
}

/** Why a custom range cannot be requested, or null. */
export function rangeProblem(from: string, to: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) return 'Pick a start and an end date.'
  const start = Date.parse(`${from}T00:00:00Z`)
  const end = Date.parse(`${to}T00:00:00Z`)
  if (Number.isNaN(start) || Number.isNaN(end)) return 'Pick a start and an end date.'
  if (end < start) return 'The end date must not be before the start date.'
  if ((end - start) / DAY_MS + 1 > MAX_RANGE_DAYS) return `The range may not exceed ${MAX_RANGE_DAYS} days.`
  return null
}

export const GROUP_BY_OPTIONS: { value: MetricsGroupBy; label: string }[] = [
  { value: 'none', label: 'No grouping' },
  { value: 'severity', label: 'Severity' },
  { value: 'classification', label: 'Classification' },
  { value: 'detection_source', label: 'Detection source' },
]

// ─── Option lists ────────────────────────────────────────────────────────

export const CATEGORY_OPTIONS: { value: ContributingCategory; label: string }[] = [
  { value: 'people', label: 'People' },
  { value: 'process', label: 'Process' },
  { value: 'technology', label: 'Technology' },
  { value: 'detection', label: 'Detection' },
  { value: 'communication', label: 'Communication' },
  { value: 'third_party', label: 'Third party' },
  { value: 'other', label: 'Other' },
]

export const DETECTION_SOURCE_OPTIONS: { value: DetectionSource; label: string }[] = [
  { value: 'internal_alert', label: 'Internal alert' },
  { value: 'threat_hunt', label: 'Threat hunt' },
  { value: 'user_report', label: 'User report' },
  { value: 'third_party', label: 'Third party' },
  { value: 'law_enforcement', label: 'Law enforcement' },
  { value: 'other', label: 'Other' },
]

export const STATUS_OPTIONS: { value: ActionStatus; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'done', label: 'Done' },
  { value: 'wont_fix', label: "Won't fix" },
]

export const PRIORITY_OPTIONS: { value: ActionPriority; label: string }[] = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
]

export const FRAMEWORK_OPTIONS: { value: ControlFramework; label: string; example: string }[] = [
  { value: 'nist_csf', label: 'NIST CSF 2.0', example: 'RS.MA-01' },
  { value: 'd3fend', label: 'MITRE D3FEND', example: 'D3-MFA' },
  { value: 'cis', label: 'CIS Controls', example: '5.2' },
  { value: 'iso27001', label: 'ISO 27001', example: 'A.8.5' },
  { value: 'other', label: 'Other', example: '' },
]

export const labelOf = <T extends string>(options: { value: T; label: string }[], value: T | null | undefined) =>
  options.find((o) => o.value === value)?.label ?? (value ?? '—')

/** Human label of a metrics group key (`null` = not set). */
export function groupLabel(groupBy: MetricsGroupBy, key: string | null): string {
  if (key === null || key === undefined) return groupBy === 'detection_source' ? 'No review yet' : 'Not set'
  if (groupBy === 'detection_source') return labelOf(DETECTION_SOURCE_OPTIONS, key as DetectionSource)
  if (groupBy === 'severity') return key.charAt(0).toUpperCase() + key.slice(1)
  return key
}

// ─── Improvement actions ─────────────────────────────────────────────────

const OPEN_STATUSES: ActionStatus[] = ['open', 'in_progress', 'blocked']

export function isOpenAction(a: Pick<ImprovementAction, 'status'>): boolean {
  return OPEN_STATUSES.includes(a.status)
}

/** Open and past its due date. */
export function isOverdue(a: Pick<ImprovementAction, 'status' | 'due_date'>, now: number = Date.now()): boolean {
  if (!a.due_date || !isOpenAction(a)) return false
  const due = Date.parse(a.due_date)
  return !Number.isNaN(due) && due < now
}

const CSF_REF = /^[A-Z]{2}\.[A-Z]{2}(-\d{2})?$/
const D3FEND_REF = /^D3-[A-Z]+$/

/** Client mirror of the server's control-reference check (the server is authoritative). */
export function controlRefProblem(framework: ControlFramework | null | undefined, ref: string): string | null {
  const value = ref.trim()
  if (value && !framework) return 'Choose a framework for this control reference.'
  if (!framework || !value) return null
  if (framework === 'nist_csf' && !CSF_REF.test(value)) return 'Use a CSF 2.0 id such as RS.MA-01 or ID.IM.'
  if (framework === 'd3fend' && !D3FEND_REF.test(value)) return 'Use a D3FEND id such as D3-MFA.'
  if (value.length > 100) return 'The control reference is too long.'
  return null
}
