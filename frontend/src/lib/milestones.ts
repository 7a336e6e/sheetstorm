/**
 * IR milestone helpers (pure, no React) for the Overview milestone strip.
 *
 * The client check mirrors the server (`incidents.py::validate_milestones`,
 * C20) so most mistakes are caught before the PUT; the server stays
 * authoritative and its 400 is shown inline as well.
 * - A value more than 5 minutes in the future is rejected.
 * - Order first malicious ≤ detected ≤ contained ≤ eradicated ≤ recovered ≤
 *   closed. Only *changed* values are checked (against every other set
 *   value), so a legacy out-of-order pair never blocks an unrelated edit.
 * - `responded_at` sits outside that chain: it must not precede `detected_at`.
 */
import { parseTs } from '@/lib/time'
import type { MilestoneField } from '@/types'

/** Every editable lifecycle timestamp, in display order. */
export const MILESTONES: readonly { field: MilestoneField; label: string }[] = [
  { field: 'first_malicious_at', label: 'First malicious activity' },
  { field: 'detected_at', label: 'Detected' },
  { field: 'responded_at', label: 'Responded' },
  { field: 'contained_at', label: 'Contained' },
  { field: 'eradicated_at', label: 'Eradicated' },
  { field: 'recovered_at', label: 'Recovered' },
  { field: 'closed_at', label: 'Closed' },
]

/** The strictly ordered chain (`responded_at` is checked against `detected_at` only). */
export const MILESTONE_ORDER: readonly MilestoneField[] = MILESTONES.map((m) => m.field).filter(
  (f) => f !== 'responded_at'
)

export const MILESTONE_FUTURE_TOLERANCE_MS = 5 * 60 * 1000

export type MilestoneValues = Partial<Record<MilestoneField, string | null | undefined>>

export interface MilestoneIssue {
  field: MilestoneField
  message: string
}

const labelOf = (field: MilestoneField) => MILESTONES.find((m) => m.field === field)?.label ?? field
const ms = (v: string | null | undefined) => parseTs(v)?.getTime() ?? null

/** Fields whose instant differs between `values` and `original` (`null` = cleared). */
export function changedMilestones(values: MilestoneValues, original: MilestoneValues): Partial<Record<MilestoneField, string | null>> {
  const out: Partial<Record<MilestoneField, string | null>> = {}
  for (const { field } of MILESTONES) {
    const next = ms(values[field])
    if (next !== ms(original[field])) out[field] = next === null ? null : new Date(next).toISOString()
  }
  return out
}

/** The first problem with the edited milestones, or null. */
export function validateMilestones(
  values: MilestoneValues,
  original: MilestoneValues,
  now: number = Date.now(),
): MilestoneIssue | null {
  const changed = changedMilestones(values, original)
  for (const { field } of MILESTONES) {
    const v = ms(changed[field])
    if (v !== null && v > now + MILESTONE_FUTURE_TOLERANCE_MS) {
      return { field, message: `${labelOf(field)} cannot be more than 5 minutes in the future.` }
    }
  }
  if ('responded_at' in changed || 'detected_at' in changed) {
    const responded = ms(values.responded_at)
    const detected = ms(values.detected_at)
    if (responded !== null && detected !== null && detected > responded) {
      const field: MilestoneField = 'responded_at' in changed ? 'responded_at' : 'detected_at'
      return { field, message: `${labelOf('detected_at')} must not be after ${labelOf('responded_at')}.` }
    }
  }
  const order = MILESTONE_ORDER
  for (const field of order) {
    if (!(field in changed)) continue
    const v = ms(values[field])
    if (v === null) continue
    const pos = order.indexOf(field)
    for (const other of order) {
      const o = ms(values[other])
      if (other === field || o === null) continue
      const before = order.indexOf(other) < pos
      if (before ? o > v : v > o) {
        const [earlier, later] = before ? [other, field] : [field, other]
        return { field, message: `${labelOf(earlier)} must not be after ${labelOf(later)}.` }
      }
    }
  }
  return null
}

export interface MilestoneStep {
  key: 'first_activity' | MilestoneField
  label: string
  value: string | null
  /** ms since the previous set step (null when this or every earlier step is unset). */
  deltaMs: number | null
  /** "Dwell" for first activity → detected. */
  deltaLabel: string | null
}

/** The strip: first known activity (timeline), then every milestone. */
export function milestoneSteps(firstActivity: string | null | undefined, values: MilestoneValues): MilestoneStep[] {
  const raw: { key: MilestoneStep['key']; label: string; value: string | null }[] = [
    { key: 'first_activity', label: 'First activity', value: firstActivity ?? null },
    ...MILESTONES.map(({ field, label }) => ({ key: field, label, value: values[field] ?? null })),
  ]
  let prev: { key: MilestoneStep['key']; at: number } | null = null
  return raw.map((step) => {
    const at = ms(step.value)
    let deltaMs: number | null = null
    let deltaLabel: string | null = null
    if (at !== null) {
      if (prev) {
        deltaMs = at - prev.at
        deltaLabel =
          (prev.key === 'first_activity' || prev.key === 'first_malicious_at') && step.key === 'detected_at'
            ? 'Dwell'
            : null
      }
      prev = { key: step.key, at }
    }
    return { ...step, value: at === null ? null : step.value, deltaMs, deltaLabel }
  })
}
