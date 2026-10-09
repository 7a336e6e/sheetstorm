/** @jest-environment node */
import { describe, expect, it } from '@jest/globals'
import type { AcquisitionHash, CustodyEntry } from '@/types'
import { HASH_LENGTHS } from '@/types'
import {
  activeHashes,
  entryHasProblem,
  guessAlgorithm,
  itemActions,
  normalizeHash,
  partyLabel,
  pendingAcknowledgments,
  primaryHash,
  shortHash,
  validateHash,
} from './evidence-helpers'
import { hashRowProblem, hashRowsInvalid, hashRowsToInput, newHashRow } from './HashEntry'

const hex = (n: number, ch = 'a') => ch.repeat(n)

describe('validateHash (per-algorithm length)', () => {
  it.each(Object.entries(HASH_LENGTHS))('%s needs exactly %i hex characters', (alg, len) => {
    const a = alg as keyof typeof HASH_LENGTHS
    expect(validateHash(a, hex(len))).toBeNull()
    expect(validateHash(a, hex(len - 1))).toMatch(new RegExp(`${len} characters \\(got ${len - 1}\\)`))
    expect(validateHash(a, hex(len + 1))).toMatch(/characters/)
  })

  it('rejects non-hex characters', () => {
    expect(validateHash('md5', 'g'.repeat(32))).toMatch(/hexadecimal/)
    expect(validateHash('sha256', 'z'.repeat(64))).toMatch(/hexadecimal/)
  })

  it('accepts upper case and surrounding whitespace (the server lower-cases)', () => {
    expect(validateHash('sha1', `  ${'AB'.repeat(20)}\n`)).toBeNull()
    expect(normalizeHash(`  ${'AB'.repeat(20)} `)).toBe('ab'.repeat(20))
  })

  it('treats empty as not entered unless required', () => {
    expect(validateHash('sha256', '')).toBeNull()
    expect(validateHash('sha256', '   ', { required: true })).toMatch(/Enter a SHA-256 value/)
  })

  it('does not accept a value of another algorithm’s length', () => {
    expect(validateHash('sha256', hex(40))).toMatch(/64 characters/)
    expect(validateHash('md5', hex(64))).toMatch(/32 characters/)
  })
})

describe('guessAlgorithm', () => {
  it('maps a length to the one algorithm it identifies', () => {
    expect(guessAlgorithm(hex(32))).toBe('md5')
    expect(guessAlgorithm(hex(40))).toBe('sha1')
    expect(guessAlgorithm(hex(64))).toBe('sha256')
    expect(guessAlgorithm(hex(128))).toBe('sha512')
  })
  it('returns null for odd lengths or non-hex', () => {
    expect(guessAlgorithm(hex(33))).toBeNull()
    expect(guessAlgorithm('xyz')).toBeNull()
    expect(guessAlgorithm('')).toBeNull()
  })
})

describe('hash rows', () => {
  const row = (algorithm: 'md5' | 'sha256', value: string) => ({ ...newHashRow(algorithm), value })

  it('ignores empty rows and normalizes the rest', () => {
    const rows = [row('sha256', hex(64, 'A')), row('md5', '')]
    expect(hashRowsInvalid(rows)).toBe(false)
    expect(hashRowsToInput(rows)).toEqual([{ algorithm: 'sha256', value: hex(64, 'a'), source: 'tool_reported' }])
  })

  it('flags a bad value and a second value for the same algorithm', () => {
    const bad = row('sha256', hex(10))
    expect(hashRowProblem(bad, [bad])).toMatch(/64 characters/)
    const a = row('md5', hex(32))
    const b = row('md5', hex(32, 'b'))
    expect(hashRowProblem(b, [a, b])).toMatch(/Only one MD5/)
    expect(hashRowsInvalid([a, b])).toBe(true)
  })
})

describe('hashes on an item', () => {
  const h = (algorithm: AcquisitionHash['algorithm'], extra: Partial<AcquisitionHash> = {}): AcquisitionHash => ({
    algorithm,
    value: hex(HASH_LENGTHS[algorithm]),
    source: 'tool_reported',
    ...extra,
  })

  it('prefers SHA-256, skips superseded records', () => {
    const item = { acquisition_hashes: [h('md5'), h('sha256', { superseded: true }), h('sha512'), h('sha1')] }
    expect(activeHashes(item).map((x) => x.algorithm)).toEqual(['md5', 'sha512', 'sha1'])
    expect(primaryHash(item)?.algorithm).toBe('sha512')
    expect(primaryHash({ acquisition_hashes: [] })).toBeNull()
  })

  it('shortens long hashes only', () => {
    expect(shortHash(hex(64))).toBe(`${hex(10)}…${hex(6)}`)
    expect(shortHash('abc')).toBe('abc')
  })
})

describe('itemActions (custody state machine)', () => {
  const base = { voided_at: null, under_legal_hold: false }
  it('in storage: check out and transfer, not check in', () => {
    const a = itemActions({ ...base, custody_state: 'in_storage' })
    expect([a.checkOut, a.checkIn, a.transfer, a.dispose, a.void]).toEqual([true, false, true, true, true])
  })
  it('checked out: check in and transfer, not check out', () => {
    const a = itemActions({ ...base, custody_state: 'checked_out' })
    expect([a.checkOut, a.checkIn, a.transfer]).toEqual([false, true, true])
  })
  it('transferred: only check in', () => {
    const a = itemActions({ ...base, custody_state: 'transferred' })
    expect([a.checkOut, a.checkIn, a.transfer]).toEqual([false, true, false])
  })
  it('disposed is terminal but can still be voided', () => {
    const a = itemActions({ ...base, custody_state: 'disposed' })
    expect([a.checkOut, a.checkIn, a.transfer, a.dispose, a.void]).toEqual([false, false, false, false, true])
  })
  it('legal hold blocks dispose and void', () => {
    const a = itemActions({ ...base, custody_state: 'in_storage', under_legal_hold: true })
    expect([a.dispose, a.void, a.checkOut]).toEqual([false, false, true])
  })
  it('a voided item allows nothing', () => {
    const a = itemActions({ ...base, voided_at: '2026-01-01T00:00:00Z', custody_state: 'in_storage' })
    expect(Object.values(a).every((v) => v === false)).toBe(true)
  })
})

describe('ledger helpers', () => {
  const entry = (over: Partial<CustodyEntry>): CustodyEntry =>
    ({
      id: 'e',
      action: 'transfer',
      chain_version: 3,
      acknowledged_by_entry_id: null,
      signature_status: 'valid',
      link_status: 'ok',
      ...over,
    }) as CustodyEntry

  it('finds transfers and check-outs nobody acknowledged', () => {
    const list = [
      entry({ id: '1' }),
      entry({ id: '2', acknowledged_by_entry_id: 'x' }),
      entry({ id: '3', action: 'check_out' }),
      entry({ id: '4', action: 'check_in' }),
      entry({ id: '5', chain_version: null }), // legacy rows cannot be acknowledged
    ]
    expect(pendingAcknowledgments(list).map((e) => e.id)).toEqual(['1', '3'])
  })

  it('flags invalid signatures and broken links, not legacy rows', () => {
    expect(entryHasProblem(entry({}))).toBe(false)
    expect(entryHasProblem(entry({ signature_status: 'invalid' }))).toBe(true)
    expect(entryHasProblem(entry({ link_status: 'prev_hash_mismatch' }))).toBe(true)
    expect(entryHasProblem(entry({ signature_status: 'unsigned_legacy', link_status: 'legacy' }))).toBe(false)
  })

  it('labels a party with its organization', () => {
    expect(partyLabel({ name: 'Jane Roe', organization_name: 'Acme Labs' })).toBe('Jane Roe (Acme Labs)')
    expect(partyLabel(null)).toBe('')
  })
})
