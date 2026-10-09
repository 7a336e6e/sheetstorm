/**
 * @jest-environment node
 */
import { describe, expect, it } from '@jest/globals'
import {
  MAX_RANGE_DAYS,
  barPercent,
  controlRefProblem,
  formatSeconds,
  groupLabel,
  isOverdue,
  presetRange,
  rangeProblem,
} from './post-incident'

describe('formatSeconds', () => {
  it('formats durations and shows a dash for unknown values', () => {
    expect(formatSeconds(null)).toBe('—')
    expect(formatSeconds(undefined)).toBe('—')
    expect(formatSeconds(45)).toBe('45s')
    expect(formatSeconds(2 * 3600 + 15 * 60)).toBe('2h 15m')
    expect(formatSeconds(3 * 86400 + 4 * 3600)).toBe('3d 4h')
    expect(formatSeconds(0)).toBe('0s')
  })
})

describe('barPercent', () => {
  it('scales to the maximum, keeps tiny values visible, and ignores empty data', () => {
    expect(barPercent(50, 100)).toBe(50)
    expect(barPercent(1, 100000)).toBe(2)
    expect(barPercent(500, 100)).toBe(100)
    expect(barPercent(null, 100)).toBe(0)
    expect(barPercent(0, 100)).toBe(0)
    expect(barPercent(10, 0)).toBe(0)
  })
})

describe('date ranges', () => {
  it('builds presets that end today (UTC) and cover the requested days', () => {
    const now = new Date('2026-10-09T23:30:00Z')
    expect(presetRange(30, now)).toEqual({ from: '2026-09-10', to: '2026-10-09' })
    expect(presetRange(1, now)).toEqual({ from: '2026-10-09', to: '2026-10-09' })
  })

  it('validates custom ranges like the server (731 days max, ordered)', () => {
    expect(rangeProblem('2026-01-01', '2026-03-01')).toBeNull()
    expect(rangeProblem('', '2026-03-01')).toMatch(/start and an end/)
    expect(rangeProblem('2026-03-02', '2026-03-01')).toMatch(/before the start/)
    expect(rangeProblem('2024-03-30', '2026-03-30')).toBeNull() // exactly 731 days, inclusive
    expect(rangeProblem('2024-03-29', '2026-03-30')).toMatch(new RegExp(String(MAX_RANGE_DAYS)))
  })
})

describe('groupLabel', () => {
  it('labels group keys', () => {
    expect(groupLabel('severity', 'high')).toBe('High')
    expect(groupLabel('detection_source', 'threat_hunt')).toBe('Threat hunt')
    expect(groupLabel('detection_source', null)).toBe('No review yet')
    expect(groupLabel('classification', null)).toBe('Not set')
    expect(groupLabel('classification', 'ransomware')).toBe('ransomware')
  })
})

describe('isOverdue', () => {
  const now = Date.parse('2026-10-09T12:00:00Z')
  it('is true only for open actions past their due date', () => {
    expect(isOverdue({ status: 'open', due_date: '2026-10-08T00:00:00Z' }, now)).toBe(true)
    expect(isOverdue({ status: 'blocked', due_date: '2026-10-08T00:00:00Z' }, now)).toBe(true)
    expect(isOverdue({ status: 'done', due_date: '2026-10-08T00:00:00Z' }, now)).toBe(false)
    expect(isOverdue({ status: 'wont_fix', due_date: '2026-10-08T00:00:00Z' }, now)).toBe(false)
    expect(isOverdue({ status: 'open', due_date: '2026-10-10T00:00:00Z' }, now)).toBe(false)
    expect(isOverdue({ status: 'open', due_date: null }, now)).toBe(false)
  })
})

describe('controlRefProblem', () => {
  it('mirrors the server rules', () => {
    expect(controlRefProblem(null, '')).toBeNull()
    expect(controlRefProblem(null, 'RS.MA-01')).toMatch(/Choose a framework/)
    expect(controlRefProblem('nist_csf', 'RS.MA-01')).toBeNull()
    expect(controlRefProblem('nist_csf', 'ID.IM')).toBeNull()
    expect(controlRefProblem('nist_csf', 'bogus')).toMatch(/CSF/)
    expect(controlRefProblem('d3fend', 'D3-MFA')).toBeNull()
    expect(controlRefProblem('d3fend', 'mfa')).toMatch(/D3FEND/)
    expect(controlRefProblem('cis', 'anything goes')).toBeNull()
    expect(controlRefProblem('d3fend', '')).toBeNull()
  })
})
