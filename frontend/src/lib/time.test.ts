/**
 * @jest-environment node
 *
 * Expectations for `local` mode are computed with the JS Date constructors,
 * so the suite holds in any TZ (run it with e.g. TZ=America/New_York,
 * TZ=Asia/Kolkata, TZ=UTC). The DST cases find a transition in the current
 * zone and are skipped in zones without DST.
 */
import { describe, expect, it } from '@jest/globals'
import {
  dwellMs,
  formatDuration,
  formatOffset,
  formatTs,
  fromInputValue,
  isTimeMode,
  parseTs,
  toInputValue,
} from './time'

const pad = (n: number) => String(n).padStart(2, '0')
const localInput = (d: Date) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`

describe('parseTs', () => {
  it.each([
    ['2026-10-08T14:03:22Z', '2026-10-08T14:03:22.000Z'],
    ['2026-10-08T14:03:22+00:00', '2026-10-08T14:03:22.000Z'],
    ['2026-10-08T16:03:22+02:00', '2026-10-08T14:03:22.000Z'],
    ['2026-10-08T09:33:22-04:30', '2026-10-08T14:03:22.000Z'],
    ['2026-10-08T16:03:22+0200', '2026-10-08T14:03:22.000Z'],
    ['2026-10-08T16:03:22+02', '2026-10-08T14:03:22.000Z'],
    ['2026-10-08T14:03:22.123456+00:00', '2026-10-08T14:03:22.123Z'],
    ['2026-10-08 14:03:22', '2026-10-08T14:03:22.000Z'],
    ['2026-10-08T14:03', '2026-10-08T14:03:00.000Z'],
    ['2026-10-08', '2026-10-08T00:00:00.000Z'],
  ])('%s → %s', (input, expected) => {
    expect(parseTs(input)?.toISOString()).toBe(expected)
  })

  it('treats offset-less strings as UTC (backend contract), not browser-local', () => {
    expect(parseTs('2026-01-15T10:00:00')?.toISOString()).toBe('2026-01-15T10:00:00.000Z')
  })

  it.each([null, undefined, '', 'garbage', '10/08/2026', '2026-13-45T99:99'])('rejects %p', (input) => {
    expect(parseTs(input as string | null | undefined)).toBeNull()
  })

  it('passes valid Dates through and rejects invalid ones', () => {
    const d = new Date('2026-10-08T14:03:22Z')
    expect(parseTs(d)).toBe(d)
    expect(parseTs(new Date('nope'))).toBeNull()
  })
})

describe('formatTs', () => {
  const iso = '2026-10-08T14:03:22.789+00:00'

  it('renders UTC with a Z suffix', () => {
    expect(formatTs(iso, 'utc')).toBe('2026-10-08 14:03:22Z')
    expect(formatTs(iso, 'utc', { seconds: false })).toBe('2026-10-08 14:03Z')
    expect(formatTs(iso, 'utc', { zone: false })).toBe('2026-10-08 14:03:22')
  })

  it('renders local with the offset valid at that instant', () => {
    const d = new Date(iso)
    expect(formatTs(iso, 'local')).toBe(`${localInput(d).replace('T', ' ')} ${formatOffset(d)}`)
  })

  it('renders an offset input converted to the target mode', () => {
    expect(formatTs('2026-10-08T16:03:22+02:00', 'utc')).toBe('2026-10-08 14:03:22Z')
  })

  it('returns empty string for empty/invalid input', () => {
    expect(formatTs(null, 'utc')).toBe('')
    expect(formatTs('x', 'local')).toBe('')
  })
})

describe('formatOffset', () => {
  it('formats the local offset as UTC±hh:mm', () => {
    const d = new Date('2026-01-01T00:00:00Z')
    const minutes = -d.getTimezoneOffset()
    const sign = minutes < 0 ? '-' : '+'
    const abs = Math.abs(minutes)
    expect(formatOffset(d)).toBe(`UTC${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`)
    expect(formatOffset(d)).toMatch(/^UTC[+-]\d{2}:\d{2}$/)
  })
})

describe('toInputValue', () => {
  it('produces UTC digits in utc mode from any offset', () => {
    expect(toInputValue('2026-10-08T16:03:22+02:00', 'utc')).toBe('2026-10-08T14:03:22')
    expect(toInputValue('2026-10-08T16:03:22+02:00', 'utc', { seconds: false })).toBe('2026-10-08T14:03')
  })

  it('produces local digits in local mode', () => {
    const iso = '2026-10-08T14:03:22+00:00'
    expect(toInputValue(iso, 'local')).toBe(localInput(new Date(iso)))
  })

  it('no longer blanks full ISO strings with offsets (host first_seen / task due_date bug)', () => {
    // These used to be fed raw into datetime-local, which rendered blank.
    for (const iso of ['2026-03-01T08:15:00+00:00', '2026-03-01T08:15:00.123456+00:00', '2026-03-01T08:15:00Z']) {
      expect(toInputValue(iso, 'utc')).toBe('2026-03-01T08:15:00')
      expect(toInputValue(iso, 'local')).not.toBe('')
    }
  })

  it('returns empty string for empty/invalid input', () => {
    expect(toInputValue('', 'utc')).toBe('')
    expect(toInputValue(null, 'local')).toBe('')
    expect(toInputValue('bogus', 'utc')).toBe('')
  })
})

describe('fromInputValue', () => {
  it('interprets digits as UTC in utc mode', () => {
    expect(fromInputValue('2026-10-08T14:03:22', 'utc')).toBe('2026-10-08T14:03:22.000Z')
    expect(fromInputValue('2026-10-08T14:03', 'utc')).toBe('2026-10-08T14:03:00.000Z')
    expect(fromInputValue('2026-10-08T14:03:22.5', 'utc')).toBe('2026-10-08T14:03:22.500Z')
  })

  it('interprets digits as browser-local in local mode (the "stored as UTC" bug)', () => {
    expect(fromInputValue('2026-10-08T14:03:22', 'local')).toBe(new Date(2026, 9, 8, 14, 3, 22).toISOString())
  })

  it('always emits an ISO string ending in Z', () => {
    expect(fromInputValue('2026-01-15T10:00', 'local')).toMatch(/Z$/)
  })

  it.each(['', null, undefined, 'garbage', '2026-02-30T10:00', '2026-13-01T10:00', '2026-01-01T24:00', '0099-01-01T00:00'])(
    'rejects %p',
    (input) => {
      expect(fromInputValue(input as string | null | undefined, 'utc')).toBeNull()
      expect(fromInputValue(input as string | null | undefined, 'local')).toBeNull()
    },
  )
})

describe('round-trip', () => {
  const samples = [
    '2026-10-08T14:03:22Z',
    '2026-01-15T00:00:00Z',
    '2026-06-30T23:59:59Z',
    '2024-02-29T12:00:00Z',
    '2026-12-31T23:30:00+00:00',
  ]

  it.each(samples)('%s survives toInputValue → fromInputValue in both modes', (iso) => {
    const canonical = new Date(iso).toISOString()
    for (const mode of ['utc', 'local'] as const) {
      expect(fromInputValue(toInputValue(iso, mode), mode)).toBe(canonical)
    }
  })

  it('switching mode re-renders the same instant (edit form pre-fill bug)', () => {
    // Create in local mode, then edit in UTC mode: the instant is preserved.
    const sent = fromInputValue('2026-10-08T09:30:00', 'local')!
    const utcDigits = toInputValue(sent, 'utc')
    expect(fromInputValue(utcDigits, 'utc')).toBe(sent)
    expect(toInputValue(sent, 'local')).toBe('2026-10-08T09:30:00')
  })
})

interface Transition { before: Date; after: Date; deltaMin: number }

// DST transitions of 2026 in the current zone (hourly scan; empty without DST).
function findTransitions(): Transition[] {
  const out: Transition[] = []
  let prev = new Date(Date.UTC(2026, 0, 1))
  for (let h = 1; h < 24 * 366; h++) {
    const cur = new Date(Date.UTC(2026, 0, 1, h))
    if (cur.getTimezoneOffset() !== prev.getTimezoneOffset()) {
      out.push({ before: prev, after: cur, deltaMin: prev.getTimezoneOffset() - cur.getTimezoneOffset() })
    }
    prev = cur
  }
  return out
}

const transitions = findTransitions()
const forward = transitions.find((t) => t.deltaMin > 0)
const backward = transitions.find((t) => t.deltaMin < 0)
const HOUR = 3600_000

describe('DST', () => {
  ;(transitions.length ? it : it.skip)('round-trips instants around each transition in local mode', () => {
    for (const { before, after } of transitions) {
      for (const d of [new Date(before.getTime() - 2 * HOUR), new Date(after.getTime() + 2 * HOUR)]) {
        const iso = d.toISOString()
        expect(fromInputValue(toInputValue(iso, 'local'), 'local')).toBe(iso)
      }
    }
  })

  ;(transitions.length ? it : it.skip)('labels each side with the offset valid at that instant', () => {
    for (const { before, after } of transitions) {
      expect(formatOffset(before)).not.toBe(formatOffset(after))
      expect(formatTs(before, 'local').endsWith(formatOffset(before))).toBe(true)
      expect(formatTs(after, 'local').endsWith(formatOffset(after))).toBe(true)
    }
  })

  ;(forward ? it : it.skip)('a non-existent local time (spring-forward gap) still yields a UTC instant', () => {
    const { after, deltaMin } = forward!
    // Local wall clock of `after` minus half the jump: skipped by the switch.
    const wallMs = after.getTime() - after.getTimezoneOffset() * 60_000 - (deltaMin / 2) * 60_000
    const w = new Date(wallMs)
    const wall = `${w.getUTCFullYear()}-${pad(w.getUTCMonth() + 1)}-${pad(w.getUTCDate())}T${pad(w.getUTCHours())}:${pad(w.getUTCMinutes())}`
    const out = fromInputValue(wall, 'local')
    expect(out).toMatch(/Z$/)
    expect(Math.abs(new Date(out!).getTime() - after.getTime())).toBeLessThanOrEqual(HOUR)
  })

  ;(backward ? it : it.skip)('an ambiguous local time (fall-back overlap) resolves to the earlier instant', () => {
    const { after, deltaMin } = backward!
    const wall = toInputValue(after, 'local')
    // The same digits also occurred |delta| minutes earlier, before the switch.
    expect(fromInputValue(wall, 'local')).toBe(new Date(after.getTime() + deltaMin * 60_000).toISOString())
  })

  it('utc mode is unaffected by DST', () => {
    expect(fromInputValue('2026-03-29T02:30', 'utc')).toBe('2026-03-29T02:30:00.000Z')
    expect(fromInputValue('2026-11-01T01:30', 'utc')).toBe('2026-11-01T01:30:00.000Z')
  })
})

describe('formatDuration', () => {
  it.each([
    [0, '0s'],
    [45_000, '45s'],
    [12 * 60_000, '12m'],
    [5 * 3600_000, '5h'],
    [5 * 3600_000 + 12 * 60_000, '5h 12m'],
    [3 * 86400_000 + 4 * 3600_000, '3d 4h'],
    [2 * 86400_000, '2d'],
    [-5 * 60_000, '-5m'],
    [-(26 * 3600_000), '-1d 2h'],
  ])('%p ms → %p', (ms, expected) => {
    expect(formatDuration(ms)).toBe(expected)
  })

  it('returns empty string for null/NaN', () => {
    expect(formatDuration(null)).toBe('')
    expect(formatDuration(undefined)).toBe('')
    expect(formatDuration(Number.NaN)).toBe('')
  })
})

describe('dwellMs', () => {
  it('is detection minus occurrence', () => {
    expect(dwellMs('2026-10-08T10:00:00Z', '2026-10-08T12:30:00+00:00')).toBe(2.5 * 3600_000)
  })

  it('is negative when detected before it happened', () => {
    const ms = dwellMs('2026-10-08T12:00:00Z', '2026-10-08T11:55:00Z')
    expect(ms).toBe(-5 * 60_000)
    expect(formatDuration(ms)).toBe('-5m')
  })

  it('is null when a side is missing', () => {
    expect(dwellMs(null, '2026-10-08T12:00:00Z')).toBeNull()
    expect(dwellMs('2026-10-08T12:00:00Z', undefined)).toBeNull()
  })
})

describe('isTimeMode', () => {
  it('accepts only utc/local', () => {
    expect(isTimeMode('utc')).toBe(true)
    expect(isTimeMode('local')).toBe(true)
    expect(isTimeMode('UTC')).toBe(false)
    expect(isTimeMode(undefined)).toBe(false)
  })
})
