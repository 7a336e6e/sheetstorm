/**
 * Time handling helpers (pure, no React).
 *
 * Contract with the backend:
 * - The API always returns timestamps as ISO 8601 with an offset (`+00:00`).
 * - The API treats an offset-less ISO string as UTC. We mirror that here:
 *   `parseTs('2026-10-08T14:03:22')` is 14:03:22 **UTC**, never browser-local.
 * - Everything we send is produced by `fromInputValue` and always ends in `Z`.
 *
 * `TimeMode` decides how wall-clock values are shown and how a
 * `datetime-local` value is interpreted: `utc` = the digits are UTC,
 * `local` = the digits are the browser's local time zone (DST-aware).
 */

export type TimeMode = 'local' | 'utc'

export const TIME_MODES: readonly TimeMode[] = ['utc', 'local'] as const

export function isTimeMode(value: unknown): value is TimeMode {
  return value === 'utc' || value === 'local'
}

const pad = (n: number, width = 2) => String(Math.abs(n)).padStart(width, '0')

// ISO with optional time, fraction and offset. Groups: date, time, fraction, offset.
const ISO_RE =
  /^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?)(?:[.,](\d+))?)?\s*(Z|z|[+-]\d{2}(?::?\d{2})?)?$/

/**
 * Parse an API timestamp. Accepts Date, ISO strings with `Z` / `±hh:mm` /
 * `±hhmm` / `±hh`, microsecond fractions, and offset-less strings (= UTC).
 * Returns null for empty or unparseable input.
 */
export function parseTs(value: string | Date | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value !== 'string') return null
  const m = ISO_RE.exec(value.trim())
  if (!m) return null
  const [, date, time = '00:00:00', fraction, rawOffset] = m
  const hms = time.length === 5 ? `${time}:00` : time
  const ms = fraction ? `.${fraction.slice(0, 3).padEnd(3, '0')}` : ''
  let offset = 'Z'
  if (rawOffset && rawOffset.toUpperCase() !== 'Z') {
    const sign = rawOffset[0]
    const digits = rawOffset.slice(1).replace(':', '')
    offset = `${sign}${digits.slice(0, 2)}:${(digits.slice(2) || '00').padEnd(2, '0')}`
  }
  const d = new Date(`${date}T${hms}${ms}${offset}`)
  return Number.isNaN(d.getTime()) ? null : d
}

/** `UTC+02:00` / `UTC-05:30` / `UTC+00:00` for the local zone at `date` (default now). */
export function formatOffset(date: Date = new Date()): string {
  const minutes = -date.getTimezoneOffset()
  const sign = minutes < 0 ? '-' : '+'
  return `UTC${sign}${pad(Math.floor(Math.abs(minutes) / 60))}:${pad(Math.abs(minutes) % 60)}`
}

interface Parts {
  y: number
  mo: number
  d: number
  h: number
  mi: number
  s: number
}

function partsOf(date: Date, mode: TimeMode): Parts {
  return mode === 'utc'
    ? {
        y: date.getUTCFullYear(), mo: date.getUTCMonth() + 1, d: date.getUTCDate(),
        h: date.getUTCHours(), mi: date.getUTCMinutes(), s: date.getUTCSeconds(),
      }
    : {
        y: date.getFullYear(), mo: date.getMonth() + 1, d: date.getDate(),
        h: date.getHours(), mi: date.getMinutes(), s: date.getSeconds(),
      }
}

export interface FormatTsOptions {
  /** Include seconds (default true: DFIR timelines need them). */
  seconds?: boolean
  /** Append the zone (`Z` / `UTC+02:00`). Default true. */
  zone?: boolean
}

/**
 * Render a timestamp for display.
 * - utc:   `2026-10-08 14:03:22Z`
 * - local: `2026-10-08 16:03:22 UTC+02:00` (offset valid at that instant)
 * Returns '' for empty/invalid input.
 */
export function formatTs(
  value: string | Date | null | undefined,
  mode: TimeMode,
  { seconds = true, zone = true }: FormatTsOptions = {},
): string {
  const date = parseTs(value)
  if (!date) return ''
  const p = partsOf(date, mode)
  const base = `${pad(p.y, 4)}-${pad(p.mo)}-${pad(p.d)} ${pad(p.h)}:${pad(p.mi)}${seconds ? `:${pad(p.s)}` : ''}`
  if (!zone) return base
  return mode === 'utc' ? `${base}Z` : `${base} ${formatOffset(date)}`
}

/**
 * Value for an `<input type="datetime-local">`: `YYYY-MM-DDTHH:mm:ss`
 * (or `…THH:mm` with `seconds: false`) in the given mode. Accepts any ISO
 * string with an offset, which is what the API returns. '' for empty/invalid.
 */
export function toInputValue(
  value: string | Date | null | undefined,
  mode: TimeMode,
  { seconds = true }: { seconds?: boolean } = {},
): string {
  const date = parseTs(value)
  if (!date) return ''
  const p = partsOf(date, mode)
  return `${pad(p.y, 4)}-${pad(p.mo)}-${pad(p.d)}T${pad(p.h)}:${pad(p.mi)}${seconds ? `:${pad(p.s)}` : ''}`
}

const INPUT_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?$/

/**
 * Convert a `datetime-local` value to an ISO string in UTC (`…Z`), or null.
 * local mode interprets the digits in the browser's zone. In a DST gap the
 * browser rule applies (the clock moves forward, e.g. 02:30 → 03:30 CEST);
 * an ambiguous fall-back time resolves to the earlier (summer-time) instant.
 */
export function fromInputValue(value: string | null | undefined, mode: TimeMode): string | null {
  if (!value) return null
  const m = INPUT_RE.exec(value.trim())
  if (!m) return null
  const [y, mo, d, h, mi, s, ms] = m.slice(1).map((v, i) =>
    v === undefined ? 0 : i === 6 ? Number(v.padEnd(3, '0')) : Number(v),
  )
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || s > 59) return null
  const date = mode === 'utc'
    ? new Date(Date.UTC(y, mo - 1, d, h, mi, s, ms))
    : new Date(y, mo - 1, d, h, mi, s, ms)
  if (Number.isNaN(date.getTime())) return null
  // Reject roll-over (Feb 30 → Mar 2) and the 0-99 → 19xx year mapping.
  const check = partsOf(date, mode)
  if (check.y !== y || check.mo !== mo || check.d !== d) return null
  return date.toISOString()
}

/**
 * Human duration: `3d 4h`, `5h 12m`, `12m`, `45s`, `-5m`. '' for null/NaN.
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return ''
  const sign = ms < 0 ? '-' : ''
  const total = Math.floor(Math.abs(ms) / 1000)
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  let out: string
  if (days > 0) out = hours ? `${days}d ${hours}h` : `${days}d`
  else if (hours > 0) out = minutes ? `${hours}h ${minutes}m` : `${hours}h`
  else if (minutes > 0) out = `${minutes}m`
  else out = `${secs}s`
  return `${sign}${out}`
}

/**
 * Dwell time = detection − occurrence, in ms. Negative means "detected
 * before it happened" (bad data). null if either side is missing.
 */
export function dwellMs(
  eventIso: string | Date | null | undefined,
  detectionIso: string | Date | null | undefined,
): number | null {
  const ev = parseTs(eventIso)
  const det = parseTs(detectionIso)
  if (!ev || !det) return null
  return det.getTime() - ev.getTime()
}
