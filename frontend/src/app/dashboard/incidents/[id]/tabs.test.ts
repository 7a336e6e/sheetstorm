import { describe, expect, it } from '@jest/globals'
import { DEFAULT_TAB, TAB_ALIASES, TAB_REGISTRY, resolveTab } from './tabs'

const all = () => true
const only = (...granted: string[]) => (perm: string | string[]) =>
  (Array.isArray(perm) ? perm : [perm]).every((p) => granted.includes(p))

describe('TAB_REGISTRY', () => {
  it('has unique ids and the documented shape', () => {
    const ids = TAB_REGISTRY.map((t) => t.id)
    expect(new Set(ids).size).toBe(ids.length)
    TAB_REGISTRY.forEach((t) => {
      expect(t.label).toBeTruthy()
      expect(t.permission).toBeTruthy()
      expect(typeof t.component).toBe('function')
      expect(typeof t.keepMounted).toBe('boolean')
    })
    expect(ids[0]).toBe(DEFAULT_TAB)
  })

  it('keeps list tabs mounted but unmounts the graph canvas', () => {
    const byId = Object.fromEntries(TAB_REGISTRY.map((t) => [t.id, t]))
    expect(byId.hosts.keepMounted).toBe(true)
    expect(byId.events.keepMounted).toBe(true)
    expect(byId.graph.keepMounted).toBe(false)
  })

  it('keeps the search deep-link tab ids', () => {
    const ids = TAB_REGISTRY.map((t) => t.id)
    ;['overview', 'events', 'hosts', 'accounts', 'network', 'host-iocs', 'malware', 'notes'].forEach((id) =>
      expect(ids).toContain(id)
    )
  })
})

describe('resolveTab', () => {
  it('defaults to overview', () => {
    expect(resolveTab(null, all)).toBe('overview')
    expect(resolveTab('', all)).toBe('overview')
  })

  it('accepts known tabs', () => {
    expect(resolveTab('hosts', all)).toBe('hosts')
  })

  it('aliases artifacts to evidence', () => {
    expect(TAB_ALIASES.artifacts).toBe('evidence')
    expect(resolveTab('artifacts', all)).toBe('evidence')
  })

  it('falls back for unknown tabs', () => {
    expect(resolveTab('nope', all)).toBe('overview')
  })

  it('falls back when the user may not see the tab', () => {
    expect(resolveTab('evidence', only('incidents:read'))).toBe('overview')
    expect(resolveTab('artifacts', only('incidents:read', 'artifacts:read'))).toBe('evidence')
  })
})
