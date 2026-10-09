/** @jest-environment node */
import { describe, expect, it } from '@jest/globals'
import { EMPTY_DEFINITION, TEMPLATE_KEY_RE, checkDefinition, formatDefinition, templateSummaryText } from './template-definition'

const valid = {
  schema_version: 1,
  questions: [{ ref: 'ss:Q1001' }, { key: 'local-1', question: 'Which accounts were used?' }],
  leads: [{ key: 'l1', title: 'Review VPN logs', answers: ['ss:Q1001', 'local-1'] }],
  custom_fields: [{ key: 'ticket', label: 'Ticket', type: 'text' }, { key: 'region', label: 'Region', type: 'select', options: ['EU'] }],
  playbook: { builtin: 'ransomware' },
}

describe('checkDefinition', () => {
  it('accepts a valid definition and the empty skeleton', () => {
    expect(checkDefinition(JSON.stringify(valid))).toEqual({ definition: valid, errors: [] })
    expect(checkDefinition(formatDefinition(undefined)).errors).toEqual([])
    expect(JSON.parse(formatDefinition(undefined))).toEqual(EMPTY_DEFINITION)
  })

  it('reports bad JSON and non-objects', () => {
    expect(checkDefinition('{').errors[0]).toMatch(/Not valid JSON/)
    expect(checkDefinition('[]').errors).toEqual(['The definition must be a JSON object.'])
  })

  it('reports cross-field problems', () => {
    const bad = {
      schema_version: 2,
      questions: [{ ref: 'nope' }, { key: 'k', question: 'ok?', ref: 'ss:Q1' }, { key: 'dup', question: 'one?' }, { key: 'dup', question: 'two?' }],
      leads: [{ key: 'l', title: 'Lead', answers: ['missing'] }, { key: 'l', title: 'x', answers: [] }],
      custom_fields: [{ key: '1bad', label: 'X', type: 'text' }, { key: 's', label: 'S', type: 'select' }, { key: 't', label: 'T', type: 'text', options: ['a'] }],
      playbook: { builtin: 'a', playbook_id: 'b' },
    }
    const { definition, errors } = checkDefinition(JSON.stringify(bad))
    expect(definition).toBeNull()
    const text = errors.join('\n')
    for (const needle of [
      'schema_version must be 1',
      'is not a library reference',
      'not both',
      '"dup" appears twice',
      'answers "missing"',
      'key "l" appears twice',
      'title is required',
      'must start with a letter',
      'a select field needs options',
      'only select fields take options',
      'exactly one of builtin or playbook_id',
    ]) {
      expect(text).toContain(needle)
    }
  })
})

it('template keys and summaries', () => {
  expect(TEMPLATE_KEY_RE.test('bec-investigation')).toBe(true)
  expect(TEMPLATE_KEY_RE.test('Bad Key')).toBe(false)
  expect(templateSummaryText({ summary: { questions: 5, leads: 3, custom_fields: 2, playbook: 'builtin:x' } })).toBe(
    '5 questions · 3 leads · 2 custom fields · playbook'
  )
})
