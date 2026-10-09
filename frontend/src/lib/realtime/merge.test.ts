/** @jest-environment node */
import { describe, expect, it } from '@jest/globals'
import {
  applyChange,
  applyToObject,
  compareRows,
  matchesFilters,
  matchesParents,
  mergeIntoList,
  pathAcceptsIncident,
} from './merge'
import type { EntityChange } from './types'

const INC = '11111111-1111-4111-8111-111111111111'
const TASK = '22222222-2222-4222-8222-222222222222'

type Row = { id: string; version?: number; name?: string; status?: string; created_at?: string; task_id?: string }

function change(op: EntityChange['op'], id: string, data?: Row, version?: number | null): EntityChange {
  return { incident_id: INC, entity: 'host', op, id, version: version ?? data?.version ?? null, data }
}

describe('applyChange', () => {
  const list: Row[] = [
    { id: 'a', version: 2, name: 'A' },
    { id: 'b', version: 1, name: 'B' },
  ]

  it('upserts a created row once (the echo of an existing row is a no-op)', () => {
    const next = applyChange(list, change('created', 'c', { id: 'c', version: 1, name: 'C' }))
    expect(next.map((r) => r.id)).toEqual(['a', 'b', 'c'])
    expect(applyChange(list, change('created', 'a', { id: 'a', version: 2, name: 'A' }))).toBe(list)
  })

  it('replaces only when the version is newer', () => {
    const next = applyChange(list, change('updated', 'a', { id: 'a', version: 3, name: 'A2' }))
    expect(next[0]).toEqual({ id: 'a', version: 3, name: 'A2' })
    expect(applyChange(list, change('updated', 'a', { id: 'a', version: 2, name: 'echo' }))).toBe(list)
    expect(applyChange(list, change('updated', 'a', { id: 'a', version: 1, name: 'old' }))).toBe(list)
  })

  it('applies an update when either side has no version', () => {
    const next = applyChange([{ id: 'a', name: 'A' }], change('updated', 'a', { id: 'a', name: 'A2' }))
    expect(next[0].name).toBe('A2')
  })

  it('ignores an update for a row it does not hold', () => {
    expect(applyChange(list, change('updated', 'z', { id: 'z', version: 5 }))).toBe(list)
  })

  it('removes a deleted row', () => {
    expect(applyChange(list, change('deleted', 'a')).map((r) => r.id)).toEqual(['b'])
    expect(applyChange(list, change('deleted', 'zz'))).toBe(list)
  })
})

describe('applyToObject', () => {
  it('merges a newer update and ignores stale or foreign ones', () => {
    const obj = { id: 'a', version: 4, title: 'x' }
    expect(applyToObject(obj, change('updated', 'a', { id: 'a', version: 5, name: 'n' }))).toMatchObject({ version: 5, name: 'n' })
    expect(applyToObject(obj, change('updated', 'a', { id: 'a', version: 4 }))).toBe(obj)
    expect(applyToObject(obj, change('updated', 'b', { id: 'b', version: 9 }))).toBe(obj)
    expect(applyToObject(obj, change('deleted', 'a'))).toBeNull()
  })
})

describe('helpers', () => {
  it('matches equality filters, unknown fields are undefined', () => {
    const p = new URLSearchParams('page=1&status=open,closed&sort=-x')
    expect(matchesFilters({ status: 'open' }, p)).toBe(true)
    expect(matchesFilters({ status: 'draft' }, p)).toBe(false)
    expect(matchesFilters({ other: 1 }, p)).toBeUndefined()
    expect(matchesFilters({ is_ioc: true }, new URLSearchParams('is_ioc=true'))).toBe(true)
  })

  it('checks parent ids in nested paths', () => {
    const path = `/incidents/${INC}/tasks/${TASK}/comments`
    expect(matchesParents({ task_id: TASK }, path)).toBe(true)
    expect(matchesParents({ task_id: 'other' }, path)).toBe(false)
    expect(matchesParents({}, path)).toBeUndefined()
    expect(matchesParents({}, `/incidents/${INC}/hosts`)).toBe(true)
  })

  it('routes by incident id', () => {
    expect(pathAcceptsIncident(`/incidents/${INC}/hosts`, INC)).toBe(true)
    expect(pathAcceptsIncident(`/incidents/${TASK}/hosts`, INC)).toBe(false)
    expect(pathAcceptsIncident('/incidents', INC)).toBe(true)
  })

  it('sorts NULLS LAST in both directions with an id tiebreaker', () => {
    const rows = [
      { id: 'b', n: 2 },
      { id: 'a', n: null },
      { id: 'c', n: 2 },
      { id: 'd', n: 5 },
    ]
    expect(rows.slice().sort((x, y) => compareRows(x, y, '-n')).map((r) => r.id)).toEqual(['d', 'b', 'c', 'a'])
    expect(rows.slice().sort((x, y) => compareRows(x, y, 'n')).map((r) => r.id)).toEqual(['b', 'c', 'd', 'a'])
  })
})

describe('mergeIntoList (cached list responses)', () => {
  const path = `/incidents/${INC}/hosts`
  const page1 = {
    items: [
      { id: 'h3', version: 1, created_at: '2026-01-03', status: 'open' },
      { id: 'h2', version: 1, created_at: '2026-01-02', status: 'open' },
    ],
    total: 4,
    page: 1,
    per_page: 2,
    pages: 2,
    sort: '-created_at',
  }
  const key1 = `${path}?page=1&per_page=2`

  it('inserts a created row at its sorted position on page 1 and trims the page', () => {
    const r = mergeIntoList(page1, change('created', 'h9', { id: 'h9', version: 1, created_at: '2026-01-09', status: 'open' }), key1)
    expect(r.stale).toBe(false)
    expect(r.data.items.map((x) => x.id)).toEqual(['h9', 'h3'])
    expect(r.data.total).toBe(5)
    expect(r.data.pages).toBe(3)
  })

  it('only counts a created row that sorts after page 1', () => {
    const r = mergeIntoList(page1, change('created', 'h0', { id: 'h0', version: 1, created_at: '2025-12-01', status: 'open' }), key1)
    expect(r.data.items.map((x) => x.id)).toEqual(['h3', 'h2'])
    expect(r.data.total).toBe(5)
  })

  it('marks later pages, searches and unknown sorts stale', () => {
    const row = { id: 'h9', version: 1, created_at: '2026-01-09', status: 'open' }
    expect(mergeIntoList({ ...page1, page: 2 }, change('created', 'h9', row), `${path}?page=2&per_page=2`).stale).toBe(true)
    expect(mergeIntoList(page1, change('created', 'h9', row), `${path}?page=1&per_page=2&q=dc`).stale).toBe(true)
    expect(mergeIntoList({ ...page1, sort: undefined }, change('created', 'h9', row), key1).stale).toBe(true)
    expect(mergeIntoList(page1, change('created', 'h9', { id: 'h9' }), key1).stale).toBe(true) // sort field missing
  })

  it('skips a created row that fails a filter, and is stale on an unknown filter field', () => {
    const row = { id: 'h9', version: 1, created_at: '2026-01-09', status: 'closed' }
    const r = mergeIntoList(page1, change('created', 'h9', row), `${key1}&status=open`)
    expect(r.changed).toBe(false)
    expect(r.stale).toBe(false)
    expect(mergeIntoList(page1, change('created', 'h9', row), `${key1}&containment=isolated`).stale).toBe(true)
  })

  it('replaces an updated row when newer and ignores a stale version', () => {
    const r = mergeIntoList(page1, change('updated', 'h2', { id: 'h2', version: 2, created_at: '2026-01-02', status: 'open', name: 'x' }), key1)
    expect(r.data.items[1]).toMatchObject({ id: 'h2', version: 2, name: 'x' })
    const stale = mergeIntoList(page1, change('updated', 'h2', { id: 'h2', version: 1, name: 'old' }), key1)
    expect(stale.changed).toBe(false)
    expect(stale.data).toBe(page1)
  })

  it('drops an updated row that no longer passes the filter', () => {
    const r = mergeIntoList(page1, change('updated', 'h2', { id: 'h2', version: 2, status: 'closed' }), `${key1}&status=open`)
    expect(r.data.items.map((x) => x.id)).toEqual(['h3'])
    expect(r.data.total).toBe(3)
  })

  it('removes a deleted row and decrements the total', () => {
    const r = mergeIntoList(page1, change('deleted', 'h3'), key1)
    expect(r.data.items.map((x) => x.id)).toEqual(['h2'])
    expect(r.data.total).toBe(3)
    expect(mergeIntoList(page1, change('deleted', 'nope'), key1).changed).toBe(false)
  })

  it('appends to all-pages lists, respecting parent ids', () => {
    const all = { items: [{ id: 'c1', task_id: TASK }], total: 1, truncated: false }
    const comments = `/incidents/${INC}/tasks/${TASK}/comments`
    const key = `${comments}?per_page=200&__all=50`
    const r = mergeIntoList(all, change('created', 'c2', { id: 'c2', task_id: TASK }), key)
    expect(r.data.items.map((x) => x.id)).toEqual(['c1', 'c2'])
    expect(r.data.total).toBe(2)
    expect(mergeIntoList(all, change('created', 'c3', { id: 'c3', task_id: 'other' }), key).changed).toBe(false)
  })
})
