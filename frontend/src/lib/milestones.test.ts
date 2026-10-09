/**
 * @jest-environment node
 */
import { describe, expect, it } from '@jest/globals'
import { changedMilestones, milestoneSteps, validateMilestones } from './milestones'

const NOW = Date.parse('2026-10-09T12:00:00Z')

describe('validateMilestones', () => {
  it('accepts ordered and equal values', () => {
    const values = {
      detected_at: '2026-10-01T00:00:00Z',
      contained_at: '2026-10-01T00:00:00Z',
      eradicated_at: '2026-10-02T00:00:00Z',
    }
    expect(validateMilestones(values, {}, NOW)).toBeNull()
  })

  it('rejects a value more than 5 minutes in the future, allows clock skew', () => {
    expect(validateMilestones({ closed_at: '2026-10-09T12:10:00Z' }, {}, NOW)).toEqual({
      field: 'closed_at',
      message: 'Closed cannot be more than 5 minutes in the future.',
    })
    expect(validateMilestones({ closed_at: '2026-10-09T12:04:00Z' }, {}, NOW)).toBeNull()
  })

  it('rejects out-of-order values, including non-adjacent ones', () => {
    const original = { detected_at: '2026-10-05T00:00:00Z' }
    expect(validateMilestones({ ...original, contained_at: '2026-10-04T00:00:00Z' }, original, NOW)).toEqual({
      field: 'contained_at',
      message: 'Detected must not be after Contained.',
    })
    expect(validateMilestones({ ...original, closed_at: '2026-10-01T00:00:00Z' }, original, NOW)?.message).toBe(
      'Detected must not be after Closed.'
    )
  })

  it('ignores a legacy out-of-order pair that is not being edited', () => {
    const legacy = { contained_at: '2026-10-05T00:00:00Z', eradicated_at: '2026-10-04T00:00:00Z' }
    expect(validateMilestones({ ...legacy, recovered_at: '2026-10-06T00:00:00Z' }, legacy, NOW)).toBeNull()
  })

  it('treats a cleared value as unset', () => {
    const original = { detected_at: '2026-10-05T00:00:00Z', contained_at: '2026-10-06T00:00:00Z' }
    expect(validateMilestones({ ...original, contained_at: null }, original, NOW)).toBeNull()
  })
})

describe('changedMilestones', () => {
  it('returns only changed instants, null for cleared, ignoring offset spelling', () => {
    const original = { detected_at: '2026-10-05T02:00:00+02:00', contained_at: '2026-10-06T00:00:00Z' }
    const values = { detected_at: '2026-10-05T00:00:00.000Z', contained_at: null, closed_at: '2026-10-07T00:00:00Z' }
    expect(changedMilestones(values, original)).toEqual({
      contained_at: null,
      closed_at: '2026-10-07T00:00:00.000Z',
    })
  })
})

describe('milestoneSteps', () => {
  it('computes deltas from the previous set step and labels dwell', () => {
    const steps = milestoneSteps('2026-10-01T00:00:00Z', {
      detected_at: '2026-10-03T00:00:00Z',
      eradicated_at: '2026-10-03T06:00:00Z',
    })
    expect(steps.map((s) => s.key)).toEqual([
      'first_activity', 'detected_at', 'contained_at', 'eradicated_at', 'recovered_at', 'closed_at',
    ])
    expect(steps[0].deltaMs).toBeNull()
    expect(steps[1]).toMatchObject({ deltaMs: 2 * 86400000, deltaLabel: 'Dwell' })
    expect(steps[2]).toMatchObject({ value: null, deltaMs: null })
    expect(steps[3]).toMatchObject({ deltaMs: 6 * 3600000, deltaLabel: null })
  })

  it('reports legacy negative intervals as negative deltas', () => {
    const steps = milestoneSteps(null, { contained_at: '2026-10-05T00:00:00Z', eradicated_at: '2026-10-04T00:00:00Z' })
    expect(steps[3].deltaMs).toBe(-86400000)
  })
})
