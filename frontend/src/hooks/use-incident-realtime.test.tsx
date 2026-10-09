import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'

// ── Fake socket.io client ──────────────────────────────────────────────
type Handler = (payload?: unknown) => void
class MockSocket {
  connected = true
  handlers = new Map<string, Set<Handler>>()
  emitted: Array<[string, unknown]> = []
  on(event: string, fn: Handler) {
    if (!this.handlers.has(event)) this.handlers.set(event, new Set())
    this.handlers.get(event)!.add(fn)
    return this
  }
  off(event: string, fn: Handler) {
    this.handlers.get(event)?.delete(fn)
    return this
  }
  emit(event: string, payload?: unknown) {
    this.emitted.push([event, payload])
    return this
  }
  fire(event: string, payload?: unknown) {
    Array.from(this.handlers.get(event) ?? []).forEach((fn) => fn(payload))
  }
  sent(event: string) {
    return this.emitted.filter(([e]) => e === event).map(([, p]) => p)
  }
}
const mockSocket = new MockSocket()
jest.mock('@/hooks/use-socket', () => ({
  useSocket: () => ({ socket: mockSocket, status: 'connected', isConnected: true }),
}))

const mockPush = jest.fn()
const mockRouter = { push: mockPush, replace: jest.fn() }
jest.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  usePathname: () => '/dashboard/incidents/x',
  useSearchParams: () => new URLSearchParams(''),
}))

type RT = typeof import('./use-incident-realtime')
type PQ = typeof import('./use-paginated-query')
let useIncidentRealtime: RT['useIncidentRealtime']
let usePaginatedQuery: PQ['usePaginatedQuery']
let useAllPages: PQ['useAllPages']
let api: typeof import('@/lib/api').default
let cache: typeof import('@/lib/query-cache')
let live: typeof import('@/lib/realtime/live')
let useIncidentStore: typeof import('@/lib/store').useIncidentStore

beforeAll(async () => {
  ;({ useIncidentRealtime } = await import('./use-incident-realtime'))
  ;({ usePaginatedQuery, useAllPages } = await import('./use-paginated-query'))
  ;({ default: api } = await import('@/lib/api'))
  cache = await import('@/lib/query-cache')
  live = await import('@/lib/realtime/live')
  ;({ useIncidentStore } = await import('@/lib/store'))
})

const INC = '11111111-1111-4111-8111-111111111111'
const HOSTS = `/incidents/${INC}/hosts`

type Row = { id: string; version?: number; hostname?: string; created_at?: string }
type GetFn = (endpoint: string, opts?: { signal?: AbortSignal }) => Promise<unknown>
let getSpy: jest.Mock<GetFn>
let serverRows: Row[]

function hostsGets() {
  return getSpy.mock.calls.filter(([ep]) => ep.startsWith(HOSTS)).length
}

beforeEach(() => {
  cache.clearCache()
  mockSocket.handlers.clear()
  mockSocket.emitted = []
  mockSocket.connected = true
  serverRows = [
    { id: 'h2', version: 1, hostname: 'WS-2', created_at: '2026-01-02T00:00:00Z' },
    { id: 'h1', version: 1, hostname: 'WS-1', created_at: '2026-01-01T00:00:00Z' },
  ]
  getSpy = jest.fn<GetFn>(async (endpoint) => {
    if (endpoint.startsWith(HOSTS)) {
      return { items: serverRows.slice(), total: serverRows.length, page: 1, per_page: 50, pages: 1, sort: '-created_at' }
    }
    return { items: [], total: 0, page: 1, per_page: 50, pages: 0 }
  })
  jest.spyOn(api, 'get').mockImplementation(getSpy as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  jest.useRealTimers()
  act(() => useIncidentStore.setState({ currentIncident: null }))
})

function joinAck(seq: Record<string, number | null> = { hosts: 1, incident: 1 }, presence: unknown[] = []) {
  act(() => mockSocket.fire('incident:joined', { incident_id: INC, scopes: Object.keys(seq), seq, presence }))
}

function changed(payload: Record<string, unknown>) {
  act(() => mockSocket.fire('entity:changed', { incident_id: INC, entity: 'host', scope: 'hosts', ...payload }))
}

function renderLive() {
  return renderHook(() => {
    const rt = useIncidentRealtime(INC)
    const list = usePaginatedQuery<Row>({ endpoint: HOSTS, live: 'host' })
    return { rt, list }
  })
}

describe('useIncidentRealtime: rooms', () => {
  it('joins on mount and on every reconnect, and leaves on unmount', () => {
    const { unmount } = renderHook(() => useIncidentRealtime(INC))
    expect(mockSocket.sent('incident:join')).toEqual([{ incident_id: INC }])
    act(() => mockSocket.fire('connect'))
    expect(mockSocket.sent('incident:join')).toHaveLength(2)
    joinAck()
    unmount()
    expect(mockSocket.sent('incident:leave')).toEqual([{ incident_id: INC }])
  })

  it('reports live only once the join is acknowledged', () => {
    const { result } = renderHook(() => useIncidentRealtime(INC))
    expect(result.current.status).toBe('connecting')
    joinAck()
    expect(result.current.status).toBe('live')
    act(() => mockSocket.fire('disconnect'))
    expect(result.current.status).toBe('connecting')
  })
})

describe('live merge into usePaginatedQuery', () => {
  it('merges created / updated / deleted without refetching, ignoring stale versions', async () => {
    const { result } = renderLive()
    await waitFor(() => expect(result.current.list.items).toHaveLength(2))
    joinAck()
    const before = hostsGets()

    changed({ op: 'created', id: 'h3', version: 1, seq: 2, data: { id: 'h3', version: 1, hostname: 'WS-3', created_at: '2026-01-03T00:00:00Z' } })
    expect(result.current.list.items.map((r) => r.id)).toEqual(['h3', 'h2', 'h1'])
    expect(result.current.list.total).toBe(3)

    changed({ op: 'updated', id: 'h1', version: 2, seq: 3, data: { id: 'h1', version: 2, hostname: 'DC-1', created_at: '2026-01-01T00:00:00Z' } })
    expect(result.current.list.items[2]).toMatchObject({ id: 'h1', hostname: 'DC-1', version: 2 })

    // Stale (older) and echoed (same) versions are no-ops.
    changed({ op: 'updated', id: 'h1', version: 1, seq: 4, data: { id: 'h1', version: 1, hostname: 'OLD' } })
    changed({ op: 'updated', id: 'h1', version: 2, seq: 5, data: { id: 'h1', version: 2, hostname: 'ECHO' } })
    expect(result.current.list.items[2].hostname).toBe('DC-1')

    changed({ op: 'deleted', id: 'h2', version: 2, seq: 6 })
    expect(result.current.list.items.map((r) => r.id)).toEqual(['h3', 'h1'])
    expect(result.current.list.total).toBe(2)

    // Other incidents' events are ignored.
    act(() =>
      mockSocket.fire('entity:changed', {
        incident_id: '99999999-9999-4999-8999-999999999999', entity: 'host', op: 'deleted', id: 'h1', seq: 7,
      })
    )
    expect(result.current.list.items).toHaveLength(2)

    await new Promise((r) => setTimeout(r, 650))
    expect(hostsGets()).toBe(before)
  })

  it('coalesces a burst of seq gaps into one refetch', async () => {
    const { result } = renderLive()
    await waitFor(() => expect(result.current.list.items).toHaveLength(2))
    joinAck({ hosts: 1 })
    const before = hostsGets()
    serverRows = [{ id: 'h9', version: 1, created_at: '2026-01-09T00:00:00Z' }, ...serverRows]

    changed({ op: 'updated', id: 'h1', version: 2, seq: 5, data: { id: 'h1', version: 2 } }) // 2..4 missed
    changed({ op: 'updated', id: 'h1', version: 3, seq: 9, data: { id: 'h1', version: 3 } }) // 6..8 missed
    changed({ op: 'updated', id: 'h1', version: 4, seq: 12, data: { id: 'h1', version: 4 } })

    await waitFor(() => expect(result.current.list.items.map((r) => r.id)).toContain('h9'), { timeout: 2000 })
    await new Promise((r) => setTimeout(r, 650))
    expect(hostsGets() - before).toBe(1)
  })

  it('refetches the listed scopes on incident:resync, once per burst', async () => {
    const { result } = renderLive()
    await waitFor(() => expect(result.current.list.items).toHaveLength(2))
    joinAck()
    const before = hostsGets()

    act(() => {
      mockSocket.fire('incident:resync', { incident_id: INC, scopes: ['hosts'], reason: 'import' })
      mockSocket.fire('incident:resync', { incident_id: INC, scopes: ['hosts'], reason: 'import' })
      mockSocket.fire('incident:resync', { incident_id: INC, scopes: ['tasks'], reason: 'import' })
    })
    await waitFor(() => expect(hostsGets() - before).toBe(1), { timeout: 2000 })
    await new Promise((r) => setTimeout(r, 650))
    expect(hostsGets() - before).toBe(1)
  })

  it('resyncs scopes whose counter moved while disconnected', async () => {
    const { result } = renderLive()
    await waitFor(() => expect(result.current.list.items).toHaveLength(2))
    joinAck({ hosts: 1, tasks: 4 })
    const before = hostsGets()
    act(() => {
      mockSocket.fire('disconnect')
      mockSocket.fire('connect')
    })
    joinAck({ hosts: 3, tasks: 4 })
    await waitFor(() => expect(hostsGets() - before).toBe(1), { timeout: 2000 })
  })

  it('stops merging when the list unmounts', async () => {
    const { result, unmount } = renderLive()
    await waitFor(() => expect(result.current.list.items).toHaveLength(2))
    expect(live.liveReaderCount()).toBe(1)
    unmount()
    expect(live.liveReaderCount()).toBe(0)
  })
})

describe('useIncidentRealtime: incident, revocation, presence', () => {
  it('merges an incident update into the open incident (version-guarded)', () => {
    act(() =>
      useIncidentStore.setState({ currentIncident: { id: INC, title: 'Old', version: 3 } as never })
    )
    renderHook(() => useIncidentRealtime(INC))
    joinAck()
    act(() =>
      mockSocket.fire('entity:changed', {
        incident_id: INC, entity: 'incident', scope: 'incident', op: 'updated', id: INC, version: 4,
        data: { id: INC, title: 'New', version: 4 },
      })
    )
    expect(useIncidentStore.getState().currentIncident).toMatchObject({ title: 'New', version: 4 })
    act(() =>
      mockSocket.fire('entity:changed', {
        incident_id: INC, entity: 'incident', scope: 'incident', op: 'updated', id: INC, version: 2,
        data: { id: INC, title: 'Stale', version: 2 },
      })
    )
    expect(useIncidentStore.getState().currentIncident).toMatchObject({ title: 'New' })
  })

  it('navigates away with a notice when access is revoked', () => {
    renderHook(() => useIncidentRealtime(INC))
    joinAck()
    act(() => mockSocket.fire('incident:access_revoked', { incident_id: 'someone-else' }))
    expect(mockPush).not.toHaveBeenCalled()
    act(() => mockSocket.fire('incident:access_revoked', { incident_id: INC, reason: 'archived' }))
    expect(mockPush).toHaveBeenCalledWith('/dashboard/incidents')
  })

  it('tracks presence and sends focus changes debounced', async () => {
    const { result } = renderHook(() => useIncidentRealtime(INC))
    joinAck({ hosts: 1 }, [{ pid: 'p1', user_id: 'u1', name: 'Dana', focus: null, mode: 'viewing' }])
    expect(result.current.presence).toHaveLength(1)
    act(() =>
      mockSocket.fire('presence:state', {
        incident_id: INC,
        users: [
          { pid: 'p1', user_id: 'u1', name: 'Dana', focus: { entity: 'task', id: 't1' }, mode: 'editing' },
          { pid: 'p2', user_id: 'u2', name: 'Ari', focus: null, mode: 'viewing' },
          { bogus: true },
        ],
      })
    )
    expect(result.current.presence.map((u) => u.pid)).toEqual(['p1', 'p2'])

    act(() => {
      result.current.setFocus({ entity: 'task', id: 't1' }, 'editing')
      result.current.setFocus({ entity: 'task', id: 't2' }, 'editing')
    })
    await waitFor(() => expect(mockSocket.sent('presence:update')).toHaveLength(1))
    expect(mockSocket.sent('presence:update')[0]).toEqual({
      incident_id: INC, focus: { entity: 'task', id: 't2' }, mode: 'editing',
    })
  })

  it('relays node drags in both directions', () => {
    const { result } = renderHook(() => useIncidentRealtime(INC))
    joinAck({ attack_graph: 1 })
    act(() => result.current.sendNodeDrag('n1', 10, 20))
    expect(mockSocket.sent('graph:node_drag')).toEqual([{ incident_id: INC, node_id: 'n1', x: 10, y: 20 }])
    const seen: unknown[] = []
    const off = result.current.onNodeDrag((ev) => seen.push(ev))
    act(() => mockSocket.fire('graph:node_drag', { incident_id: INC, node_id: 'n2', x: 1, y: 2, user_id: 'u2' }))
    act(() => mockSocket.fire('graph:node_drag', { incident_id: INC, node_id: 'n2', x: 'bad', y: 2 }))
    off()
    expect(seen).toEqual([{ incident_id: INC, node_id: 'n2', x: 1, y: 2, user_id: 'u2' }])
  })
})

describe('useAllPages', () => {
  it('returns the same empty array on every render while loading', () => {
    getSpy.mockImplementation(() => new Promise(() => {}))
    const { result, rerender } = renderHook(() => useAllPages<Row>(HOSTS, { live: 'host' }))
    const first = result.current.items
    rerender()
    rerender()
    expect(result.current.isLoading).toBe(true)
    expect(result.current.items).toBe(first)
  })

  it('merges live changes into all-pages lists', async () => {
    const { result } = renderHook(() => {
      useIncidentRealtime(INC)
      return useAllPages<Row>(HOSTS, { live: 'host' })
    })
    await waitFor(() => expect(result.current.items).toHaveLength(2))
    joinAck()
    changed({ op: 'created', id: 'h3', version: 1, seq: 2, data: { id: 'h3', version: 1 } })
    expect(result.current.items.map((r) => r.id)).toEqual(['h2', 'h1', 'h3'])
    expect(result.current.total).toBe(3)
  })
})

describe('live merge: unplaceable changes', () => {
  it('refetches once (debounced) when a created row cannot be placed (search active)', async () => {
    const { result } = renderHook(() => {
      useIncidentRealtime(INC)
      return usePaginatedQuery<Row>({ endpoint: HOSTS, live: 'host', defaults: { q: 'ws' } })
    })
    await waitFor(() => expect(result.current.items).toHaveLength(2))
    joinAck()
    const before = hostsGets()
    changed({ op: 'created', id: 'h3', version: 1, seq: 2, data: { id: 'h3', version: 1, created_at: '2026-01-03T00:00:00Z' } })
    changed({ op: 'created', id: 'h4', version: 1, seq: 3, data: { id: 'h4', version: 1, created_at: '2026-01-04T00:00:00Z' } })
    // The rows stay visible while the refetch runs; nothing is guessed in.
    expect(result.current.items.map((r) => r.id)).toEqual(['h2', 'h1'])
    await waitFor(() => expect(hostsGets() - before).toBe(1), { timeout: 2000 })
    await new Promise((r) => setTimeout(r, 500))
    expect(hostsGets() - before).toBe(1)
  })
})
