import { describe, expect, it } from '@jest/globals'
import { displayCustomValue, parseCustomValue } from './CustomFieldsCard'
import type { CustomFieldDef } from '@/types'

const def = (type: CustomFieldDef['type']): CustomFieldDef => ({ key: 'k', label: 'K', type })

describe('custom field values', () => {
  it('parses form input per type', () => {
    expect(parseCustomValue(def('number'), ' 42 ')).toBe(42)
    expect(parseCustomValue(def('number'), 'x')).toBeNull()
    expect(parseCustomValue(def('text'), '  ')).toBeNull()
    expect(parseCustomValue(def('text'), ' a ')).toBe('a')
    expect(parseCustomValue(def('boolean'), true)).toBe(true)
    expect(parseCustomValue(def('select'), 'EU')).toBe('EU')
  })

  it('displays values', () => {
    expect(displayCustomValue(def('boolean'), false)).toBe('No')
    expect(displayCustomValue(def('boolean'), true)).toBe('Yes')
    expect(displayCustomValue(def('text'), null)).toBe('—')
    expect(displayCustomValue(def('number'), 0)).toBe('0')
  })
})
