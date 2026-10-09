/** @jest-environment node */
import { describe, expect, it } from '@jest/globals'
import {
  emptyProvenance,
  formatSkew,
  hasProvenance,
  provenanceFromRecord,
  provenancePayload,
  skewFromParts,
  skewToParts,
} from './provenance-form'

describe('provenancePayload', () => {
  it('sends only non-empty fields on create', () => {
    const v = { ...emptyProvenance(), source_record_ref: ' Security.evtx#1 ', raw_timestamp: '2026-10-01 14:05:00', source_timezone: 'Europe/Berlin' }
    expect(provenancePayload(v)).toEqual({
      source_record_ref: 'Security.evtx#1',
      raw_timestamp: '2026-10-01 14:05:00',
      source_timezone: 'Europe/Berlin',
    })
    expect(provenancePayload(emptyProvenance())).toEqual({})
  })

  it('sends only changed fields on edit and null for cleared ones', () => {
    const initial = provenanceFromRecord({
      raw_timestamp: '2026-10-01 14:05:00',
      source_timezone: 'Europe/Berlin',
      extraction_tool: 'EvtxECmd',
    })
    expect(provenancePayload(initial, initial)).toEqual({})
    const edited = { ...initial, extraction_tool: '', source_timezone: 'UTC' }
    expect(provenancePayload(edited, initial)).toEqual({ extraction_tool: null, source_timezone: 'UTC' })
  })

  it('adds fold and the manual derivation only when chosen', () => {
    const v = { ...emptyProvenance(), raw_timestamp: 'x', fold: '1', keep_manual: true }
    expect(provenancePayload(v)).toEqual({ raw_timestamp: 'x', fold: 1, timestamp_derivation: 'manual' })
    expect(provenancePayload({ ...emptyProvenance(), fold: '' })).toEqual({})
  })
})

describe('provenanceFromRecord / hasProvenance', () => {
  it('maps null and missing columns to empty strings', () => {
    const v = provenanceFromRecord({ source_record_ref: null, raw_timestamp: undefined, source_evidence_id: 'ev1' })
    expect(v.source_record_ref).toBe('')
    expect(v.source_evidence_id).toBe('ev1')
    expect(hasProvenance(v)).toBe(true)
    expect(hasProvenance(provenanceFromRecord(null))).toBe(false)
  })
})

describe('clock skew formatting', () => {
  it('formats the signed offset', () => {
    expect(formatSkew(300)).toBe('+5m 0s')
    expect(formatSkew(-3723)).toBe('-1h 2m 3s')
    expect(formatSkew(0)).toBe('0s')
    expect(formatSkew(45)).toBe('+45s')
    expect(formatSkew(null)).toBe('')
  })

  it('round-trips through the h/m/s editor parts', () => {
    expect(skewFromParts(1, '1', '2', '3')).toBe(3723)
    expect(skewFromParts(-1, '0', '5', '')).toBe(-300)
    expect(skewFromParts(-1, '0', '0', '0')).toBe(0)
    expect(skewFromParts(1, '1.5', '0', '0')).toBeNaN()
    expect(skewFromParts(1, '-1', '0', '0')).toBeNaN()
    expect(skewToParts(-3723)).toEqual({ sign: -1, hours: '1', minutes: '2', seconds: '3' })
    expect(skewToParts(null)).toEqual({ sign: 1, hours: '0', minutes: '0', seconds: '0' })
  })
})
