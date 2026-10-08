/**
 * @jest-environment node
 */
import { beforeEach, describe, expect, it, jest } from '@jest/globals'
import {
  clearCache,
  getCached,
  invalidate,
  matchesPrefix,
  removeItem,
  setCached,
  subscribe,
  upsertItem,
} from './query-cache'

beforeEach(() => clearCache())

describe('matchesPrefix', () => {
  it('matches by path segment, ignoring the query', () => {
    expect(matchesPrefix('/incidents/42/hosts?page=2', '/incidents/42/hosts')).toBe(true)
    expect(matchesPrefix('/incidents/42/hosts?page=2', '/incidents/42')).toBe(true)
    expect(matchesPrefix('/incidents?page=1', '/incidents')).toBe(true)
    expect(matchesPrefix('/incidents/420/hosts', '/incidents/42')).toBe(false)
    expect(matchesPrefix('/incidents-archived', '/incidents')).toBe(false)
    expect(matchesPrefix('/incidents/42', '/incidents/42/')).toBe(true)
  })

  it('treats a prefix with ? as a raw prefix', () => {
    expect(matchesPrefix('/x?a=1&b=2', '/x?a=1')).toBe(true)
    expect(matchesPrefix('/x?a=2', '/x?a=1')).toBe(false)
  })
})

describe('cache', () => {
  it('stores and returns entries with a timestamp', () => {
    setCached('/a?page=1', { v: 1 })
    const e = getCached<{ v: number }>('/a?page=1')
    expect(e?.data.v).toBe(1)
    expect(typeof e?.ts).toBe('number')
  })

  it('invalidates by prefix and notifies related subscribers only', () => {
    setCached('/incidents/1/hosts?page=1', 1)
    setCached('/incidents/1/hosts?page=2', 2)
    setCached('/incidents/1/timeline?page=1', 3)
    setCached('/incidents/2/hosts?page=1', 4)
    const hosts1 = jest.fn()
    const hosts2 = jest.fn()
    const incident1 = jest.fn()
    subscribe('/incidents/1/hosts', hosts1)
    subscribe('/incidents/2/hosts', hosts2)
    subscribe('/incidents/1', incident1)

    invalidate('/incidents/1/hosts')

    expect(getCached('/incidents/1/hosts?page=1')).toBeUndefined()
    expect(getCached('/incidents/1/hosts?page=2')).toBeUndefined()
    expect(getCached('/incidents/1/timeline?page=1')).toBeDefined()
    expect(getCached('/incidents/2/hosts?page=1')).toBeDefined()
    expect(hosts1).toHaveBeenCalledWith({ type: 'invalidate', prefix: '/incidents/1/hosts' })
    expect(incident1).toHaveBeenCalled() // parent subscriber hears about a child invalidation
    expect(hosts2).not.toHaveBeenCalled()
  })

  it('a broad invalidate reaches narrower subscribers', () => {
    const cb = jest.fn()
    subscribe('/incidents/1/hosts', cb)
    invalidate('/incidents')
    expect(cb).toHaveBeenCalledTimes(1)
  })

  it('unsubscribe stops notifications', () => {
    const cb = jest.fn()
    const off = subscribe('/a', cb)
    off()
    invalidate('/a')
    expect(cb).not.toHaveBeenCalled()
  })

  it('notifies subscribers of set events', () => {
    const cb = jest.fn()
    subscribe('/a', cb)
    setCached('/a?page=1', 1)
    expect(cb).toHaveBeenCalledWith({ type: 'set', key: '/a?page=1' })
  })
})

describe('upsertItem / removeItem', () => {
  const page = (ids: string[]) => ({ items: ids.map((id) => ({ id, name: id })), total: ids.length })

  it('replaces an item in every cached list under the prefix', () => {
    setCached('/h?page=1', page(['a', 'b']))
    setCached('/h?q=b', page(['b']))
    expect(upsertItem('/h', { id: 'b', name: 'B2' })).toBe(true)
    expect(getCached<ReturnType<typeof page>>('/h?page=1')?.data.items[1].name).toBe('B2')
    expect(getCached<ReturnType<typeof page>>('/h?q=b')?.data.items[0].name).toBe('B2')
  })

  it('invalidates when the item is not cached anywhere', () => {
    setCached('/h?page=1', page(['a']))
    const cb = jest.fn()
    subscribe('/h', cb)
    expect(upsertItem('/h', { id: 'z', name: 'Z' })).toBe(false)
    expect(getCached('/h?page=1')).toBeUndefined()
    expect(cb).toHaveBeenCalledWith({ type: 'invalidate', prefix: '/h' })
  })

  it('removes an item and decrements total', () => {
    setCached('/h?page=1', page(['a', 'b']))
    removeItem('/h', 'a')
    const data = getCached<ReturnType<typeof page>>('/h?page=1')?.data
    expect(data?.items.map((x) => x.id)).toEqual(['b'])
    expect(data?.total).toBe(1)
  })
})
