/** @jest-environment node */
import { describe, expect, it } from '@jest/globals'
import {
  TAB_EXPORTS,
  buildEnrichItems,
  csvEndpoint,
  enrichTypeFor,
  enrichmentGate,
  exportParamsFromUrl,
} from './exports'

const url = (qs: string) => new URLSearchParams(qs)

describe('exportParamsFromUrl (the active tab list state -> CSV params)', () => {
  it('carries the tab search, sort and filters, never paging', () => {
    const params = url(
      'tab=hosts&hosts.q=ws&hosts.sort=-first_seen&hosts.f.triage_status=compromised&hosts.f.acquisition=memory_captured&hosts.page=4&hosts.per=100'
    )
    expect(exportParamsFromUrl(params, 'hosts')).toEqual({
      triage_status: 'compromised',
      acquisition: 'memory_captured',
      q: 'ws',
      sort: '-first_seen',
    })
  })

  it('ignores other tabs, unrelated params and cleared filters', () => {
    const params = url('tab=network&events.q=other&network.f.direction=&network.f.protocol=TCP&row=abc')
    expect(exportParamsFromUrl(params, 'network')).toEqual({ protocol: 'TCP' })
    expect(exportParamsFromUrl(params, 'events')).toEqual({ q: 'other' })
    expect(exportParamsFromUrl(url(''), 'hosts')).toEqual({})
  })

  it('Tasks tab in the Leads view exports leads with the Leads view defaults', () => {
    expect(exportParamsFromUrl(url('tab=tasks&tasks.view=leads'), 'tasks')).toEqual({
      lead_outcome: 'open',
      task_type: 'investigative_lead',
      sort: '-updated_at',
    })
    // an outcome chosen in the Leads view wins over the default
    expect(
      exportParamsFromUrl(url('tasks.view=leads&leads.f.lead_outcome=false_positive&leads.q=rdp'), 'tasks')
    ).toEqual({ lead_outcome: 'false_positive', task_type: 'investigative_lead', sort: '-updated_at', q: 'rdp' })
    // the plain Tasks list uses its own state
    expect(exportParamsFromUrl(url('tasks.f.status=pending'), 'tasks')).toEqual({ status: 'pending' })
  })
})

describe('tab -> export entity', () => {
  it('maps the seven exportable tabs to the backend entities', () => {
    expect(Object.fromEntries(Object.entries(TAB_EXPORTS).map(([tab, t]) => [tab, t.entity]))).toEqual({
      events: 'timeline',
      hosts: 'hosts',
      accounts: 'accounts',
      network: 'network-iocs',
      'host-iocs': 'host-iocs',
      malware: 'malware',
      tasks: 'tasks',
    })
    expect(Object.values(TAB_EXPORTS).filter((t) => t.ioc).map((t) => t.entity)).toEqual([
      'network-iocs',
      'host-iocs',
      'malware',
    ])
  })

  it('builds the endpoint with the params', () => {
    expect(csvEndpoint('i1', 'hosts')).toBe('/incidents/i1/export/hosts')
    expect(csvEndpoint('i1', 'network-iocs', { defang: 'true', q: 'a b' })).toBe(
      '/incidents/i1/export/network-iocs?defang=true&q=a+b'
    )
  })
})

describe('enrichment TLP gate', () => {
  it('RED is always blocked', () => {
    expect(enrichmentGate('red', true)).toBe('blocked')
    expect(enrichmentGate('red', false)).toBe('blocked')
  })
  it('AMBER+STRICT needs the org setting and then an explicit acknowledgement', () => {
    expect(enrichmentGate('amber_strict', false)).toBe('blocked')
    expect(enrichmentGate('amber_strict', true)).toBe('acknowledge')
  })
  it('the other levels only need a confirmation', () => {
    for (const tlp of ['white', 'green', 'amber']) expect(enrichmentGate(tlp, false)).toBe('confirm')
  })
})

describe('enrich values', () => {
  it('classifies values the way the server validates them', () => {
    expect(enrichTypeFor('203.0.113.9')).toBe('ip')
    expect(enrichTypeFor('999.1.1.1')).toBe('domain') // not an IPv4, still a dotted name
    expect(enrichTypeFor('evil.example.com')).toBe('domain')
    expect(enrichTypeFor('a'.repeat(32))).toBe('md5')
    expect(enrichTypeFor('b'.repeat(40))).toBe('sha1')
    expect(enrichTypeFor('C'.repeat(64))).toBe('sha256')
    expect(enrichTypeFor('who@evil.example')).toBe('email')
    expect(enrichTypeFor('../../etc/passwd')).toBeNull()
    expect(enrichTypeFor('C:\\Windows\\a.exe')).toBeNull()
    expect(enrichTypeFor('a/b?x=1.example')).toBeNull()
    expect(enrichTypeFor('')).toBeNull()
    expect(enrichTypeFor(null)).toBeNull()
  })

  it('dedupes case-insensitively and counts what cannot be enriched', () => {
    const { items, skipped } = buildEnrichItems([
      'Evil.example',
      'evil.example',
      '203.0.113.9',
      null,
      '',
      'not a value',
      'a'.repeat(64),
    ])
    expect(items).toEqual([
      { value: 'Evil.example', type: 'domain' },
      { value: '203.0.113.9', type: 'ip' },
      { value: 'a'.repeat(64), type: 'sha256' },
    ])
    expect(skipped).toBe(1)
  })
})
