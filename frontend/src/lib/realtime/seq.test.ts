/** @jest-environment node */
import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { gapsAfterJoin, trackSeq } from './seq'
import { createCoalescer } from './coalesce'

describe('trackSeq', () => {
  it('detects a gap per scope and ignores duplicates and nulls', () => {
    let s = {}
    let r = trackSeq(s, 'hosts', 5)
    expect(r.gap).toBe(false)
    s = r.state
    r = trackSeq(s, 'hosts', 6)
    expect(r.gap).toBe(false)
    s = r.state
    r = trackSeq(s, 'hosts', 6) // duplicate
    expect(r.gap).toBe(false)
    expect(r.state).toBe(s)
    r = trackSeq(s, 'hosts', 9) // 7 and 8 missed
    expect(r.gap).toBe(true)
    s = r.state
    expect(s).toEqual({ hosts: 9 })
    expect(trackSeq(s, 'hosts', null)).toEqual({ state: s, gap: false })
    // Scopes are independent.
    expect(trackSeq(s, 'tasks', 100).gap).toBe(false)
  })
})

describe('gapsAfterJoin', () => {
  it('records the counters on the first join without gaps', () => {
    const r = gapsAfterJoin({}, { scopes: ['hosts', 'tasks'], seq: { hosts: 3, tasks: null } }, false)
    expect(r.gaps).toEqual([])
    expect(r.state).toEqual({ hosts: 3 })
  })

  it('keeps a higher seq seen before the first ack', () => {
    expect(gapsAfterJoin({ hosts: 5 }, { scopes: ['hosts'], seq: { hosts: 4 } }, false).state).toEqual({ hosts: 5 })
  })

  it('reports scopes that moved, reset or lack a counter on a rejoin', () => {
    const r = gapsAfterJoin(
      { hosts: 3, tasks: 7, notes: 2 },
      { scopes: ['hosts', 'tasks', 'notes', 'timeline'], seq: { hosts: 3, tasks: 9, notes: 1 } },
      true
    )
    expect(r.gaps).toEqual(['tasks', 'notes', 'timeline'])
    expect(r.state).toEqual({ hosts: 3, tasks: 9, notes: 1 })
  })
})

describe('createCoalescer', () => {
  beforeEach(() => jest.useFakeTimers())
  afterEach(() => jest.useRealTimers())

  it('coalesces a burst into one run per key', async () => {
    const run = jest.fn(async (_key: string) => {})
    const c = createCoalescer(run, 500)
    c.request('hosts')
    c.request('hosts')
    c.request('tasks')
    c.request('hosts')
    expect(run).not.toHaveBeenCalled()
    await jest.advanceTimersByTimeAsync(500)
    expect(run.mock.calls.map((x) => x[0]).sort()).toEqual(['hosts', 'tasks'])
  })

  it('runs exactly one trailing call for requests during a flight', async () => {
    let finish: () => void = () => {}
    const run = jest.fn(
      (_key: string) =>
        new Promise<void>((resolve) => {
          finish = resolve
        })
    )
    const c = createCoalescer(run, 500)
    c.request('hosts')
    await jest.advanceTimersByTimeAsync(500)
    expect(run).toHaveBeenCalledTimes(1)
    c.request('hosts')
    c.request('hosts')
    c.request('hosts')
    await jest.advanceTimersByTimeAsync(2000)
    expect(run).toHaveBeenCalledTimes(1) // still in flight
    finish()
    await jest.advanceTimersByTimeAsync(0)
    await jest.advanceTimersByTimeAsync(500)
    expect(run).toHaveBeenCalledTimes(2)
    finish()
    await jest.advanceTimersByTimeAsync(5000)
    expect(run).toHaveBeenCalledTimes(2)
  })

  it('does nothing after dispose', async () => {
    const run = jest.fn()
    const c = createCoalescer(run, 500)
    c.request('hosts')
    c.dispose()
    c.request('tasks')
    await jest.advanceTimersByTimeAsync(1000)
    expect(run).not.toHaveBeenCalled()
  })
})
