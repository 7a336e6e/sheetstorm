import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { useSyncExternalStore } from 'react'

// ── next/navigation stand-in: a tiny URL store ─────────────────────────
let mockSearch = ''
const mockListeners = new Set<() => void>()
const mockReplace = jest.fn((url: string) => {
  const i = url.indexOf('?')
  mockSearch = i === -1 ? '' : url.slice(i + 1)
  window.history.replaceState(null, '', url)
  mockListeners.forEach((l) => l())
})
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace }),
  usePathname: () => '/dashboard/list',
  useSearchParams: () => {
    const search = useSyncExternalStore(
      (cb) => {
        mockListeners.add(cb)
        return () => mockListeners.delete(cb)
      },
      () => mockSearch
    )
    return new URLSearchParams(search)
  },
}))

type Mod = typeof import('./use-paginated-query')
let usePaginatedQuery: Mod['usePaginatedQuery']
let useAllPages: Mod['useAllPages']
let parseListState: Mod['parseListState']
let serializeListState: Mod['serializeListState']
let api: typeof import('@/lib/api').default
let ApiError: typeof import('@/lib/api').ApiError
let cache: typeof import('@/lib/query-cache')

beforeAll(async () => {
  ;({ usePaginatedQuery, useAllPages, parseListState, serializeListState } = await import('./use-paginated-query'))
  ;({ default: api, ApiError } = await import('@/lib/api'))
  cache = await import('@/lib/query-cache')
})

type Row = { id: string }
type GetFn = (endpoint: string, opts?: { signal?: AbortSignal }) => Promise<unknown>
let getSpy: jest.Mock<GetFn>

function envelope(page: number, per = 50, total = 120, extra: Record<string, unknown> = {}) {
  return {
    items: [{ id: `r${page}` }],
    total,
    page,
    per_page: per,
    pages: Math.ceil(total / per),
    ...extra,
  }
}

function params(endpoint: string) {
  return new URLSearchParams(endpoint.split('?')[1] ?? '')
}

beforeEach(() => {
  cache.clearCache()
  mockSearch = ''
  window.history.replaceState(null, '', '/dashboard/list')
  mockReplace.mockClear()
  getSpy = jest.fn<GetFn>(async (endpoint) => envelope(Number(params(endpoint).get('page') ?? 1)))
  jest.spyOn(api, 'get').mockImplementation(getSpy as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  jest.useRealTimers()
})

describe('list state (de)serialization', () => {
  const defaults = { page: 1, perPage: 50, sort: '-created_at', q: undefined, filters: { status: 'open' } }

  it('round-trips non-default values and keeps unrelated params', () => {
    const state = { page: 3, perPage: 100, sort: 'hostname', q: '10.0.0.', filters: { status: 'open', os: 'win' } }
    const out = serializeListState(new URLSearchParams('tab=hosts&row=x'), 'h', state, defaults)
    expect(out.get('tab')).toBe('hosts')
    expect(out.get('h.page')).toBe('3')
    expect(out.get('h.per')).toBe('100')
    expect(out.get('h.sort')).toBe('hostname')
    expect(out.get('h.q')).toBe('10.0.0.')
    expect(out.get('h.f.os')).toBe('win')
    expect(out.has('h.f.status')).toBe(false) // equal to default
    expect(parseListState(out, 'h', defaults)).toEqual(state)
  })

  it('writes cleared defaults as empty values and ignores junk', () => {
    const state = { page: 1, perPage: 50, sort: undefined, q: undefined, filters: {} }
    const out = serializeListState(new URLSearchParams(), 'h', state, defaults)
    expect(out.toString()).toBe('h.sort=&h.f.status=')
    expect(parseListState(out, 'h', defaults)).toEqual(state)
    const junk = parseListState(new URLSearchParams('h.page=-2&h.per=9999'), 'h', defaults)
    expect(junk.page).toBe(1)
    expect(junk.perPage).toBe(50)
  })
})

describe('usePaginatedQuery', () => {
  it('requests the contract params and exposes the envelope', async () => {
    const { result } = renderHook(() =>
      usePaginatedQuery<Row>({ endpoint: '/incidents/1/hosts', defaults: { sort: '-last_seen' } })
    )
    expect(result.current.isLoading).toBe(true)
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    const p = params(getSpy.mock.calls[0][0])
    expect(p.get('page')).toBe('1')
    expect(p.get('per_page')).toBe('50')
    expect(p.get('sort')).toBe('-last_seen')
    expect(result.current.items).toEqual([{ id: 'r1' }])
    expect(result.current.total).toBe(120)
    expect(result.current.pages).toBe(3)
  })

  it('syncs state to the URL under urlKey and reads it back', async () => {
    mockSearch = 'tab=hosts&h.page=2&h.f.containment_status=isolated'
    window.history.replaceState(null, '', `/dashboard/list?${mockSearch}`)
    const { result } = renderHook(() => usePaginatedQuery<Row>({ endpoint: '/incidents/1/hosts', urlKey: 'h' }))
    await waitFor(() => expect(result.current.items).toEqual([{ id: 'r2' }]))
    const p = params(getSpy.mock.calls[0][0])
    expect(p.get('page')).toBe('2')
    expect(p.get('containment_status')).toBe('isolated')

    act(() => result.current.setFilter('containment_status', 'contained'))
    const url = mockReplace.mock.calls.at(-1)![0] as string
    expect(url.startsWith('/dashboard/list?')).toBe(true)
    const written = params(url)
    expect(written.get('tab')).toBe('hosts')
    expect(written.get('h.f.containment_status')).toBe('contained')
    expect(written.has('h.page')).toBe(false) // filter change resets to page 1
    await waitFor(() => expect(result.current.state.filters.containment_status).toBe('contained'))
    expect(result.current.state.page).toBe(1)

    act(() => result.current.setSort('-hostname'))
    await waitFor(() => expect(result.current.state.sort).toBe('-hostname'))
    expect(params(getSpy.mock.calls.at(-1)![0]).get('sort')).toBe('-hostname')
  })

  it('aborts the in-flight request when params change', async () => {
    const signals: AbortSignal[] = []
    getSpy.mockImplementation((endpoint, opts) => {
      signals.push(opts!.signal!)
      return new Promise((resolve, reject) => {
        opts!.signal!.addEventListener('abort', () =>
          reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
        )
        setTimeout(() => resolve(envelope(Number(params(endpoint).get('page')))), 20)
      })
    })
    const { result } = renderHook(() => usePaginatedQuery<Row>({ endpoint: '/x' }))
    act(() => result.current.setPage(2))
    act(() => result.current.setPage(3))
    await waitFor(() => expect(result.current.items).toEqual([{ id: 'r3' }]))
    expect(signals).toHaveLength(3)
    expect(signals[0].aborted).toBe(true)
    expect(signals[1].aborted).toBe(true)
    expect(signals[2].aborted).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('debounces setQuery and resets the page', async () => {
    jest.useFakeTimers()
    const { result } = renderHook(() => usePaginatedQuery<Row>({ endpoint: '/x', defaults: { page: 2 } }))
    await act(async () => {
      await jest.advanceTimersByTimeAsync(0)
    })
    act(() => result.current.setQuery('evil'))
    act(() => result.current.setQuery('evil.exe'))
    expect(result.current.state.q).toBeUndefined()
    await act(async () => {
      await jest.advanceTimersByTimeAsync(300)
    })
    await act(async () => {
      await jest.advanceTimersByTimeAsync(0)
    })
    expect(result.current.state.q).toBe('evil.exe')
    expect(result.current.state.page).toBe(1)
    const queries = getSpy.mock.calls.map((c) => params(c[0]).get('q'))
    expect(queries).not.toContain('evil')
    act(() => result.current.setQuery(''))
    expect(result.current.state.q).toBeUndefined() // clearing is immediate
    await act(async () => {
      await jest.advanceTimersByTimeAsync(0)
    })
  })

  it('sends focus once and lands on the page the server chose', async () => {
    getSpy.mockImplementation(async (endpoint) => {
      const p = params(endpoint)
      return p.get('focus') ? envelope(3, 50, 120, { focus_found: true }) : envelope(Number(p.get('page')))
    })
    const { result } = renderHook(() => usePaginatedQuery<Row>({ endpoint: '/x', focus: 'row-9' }))
    await waitFor(() => expect(result.current.state.page).toBe(3))
    expect(result.current.focusFound).toBe(true)
    expect(params(getSpy.mock.calls[0][0]).get('focus')).toBe('row-9')
    expect(getSpy).toHaveBeenCalledTimes(1) // the landed page came from cache
    act(() => result.current.setPage(2))
    await waitFor(() => expect(result.current.items).toEqual([{ id: 'r2' }]))
    expect(params(getSpy.mock.calls.at(-1)![0]).has('focus')).toBe(false)
  })

  it('refetches when the endpoint is invalidated', async () => {
    const { result } = renderHook(() => usePaginatedQuery<Row>({ endpoint: '/incidents/1/hosts' }))
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(getSpy).toHaveBeenCalledTimes(1)
    act(() => cache.invalidate('/incidents/1'))
    await waitFor(() => expect(getSpy).toHaveBeenCalledTimes(2))
  })

  it('exposes errors without data and recovers on refetch', async () => {
    getSpy.mockRejectedValueOnce(new ApiError(500, 'boom'))
    const { result } = renderHook(() => usePaginatedQuery<Row>({ endpoint: '/x' }))
    await waitFor(() => expect(result.current.error?.status).toBe(500))
    expect(result.current.isLoading).toBe(false)
    let done = false
    act(() => {
      void result.current.refetch().then(() => {
        done = true
      })
    })
    await waitFor(() => expect(done).toBe(true))
    expect(result.current.error).toBeNull()
    expect(result.current.items).toEqual([{ id: 'r1' }])
  })

  it('does nothing while disabled', async () => {
    const { result } = renderHook(() => usePaginatedQuery<Row>({ endpoint: '/x', enabled: false }))
    await act(async () => undefined)
    expect(getSpy).not.toHaveBeenCalled()
    expect(result.current.isLoading).toBe(false)
  })

  it('append mode accumulates pages', async () => {
    const { result } = renderHook(() =>
      usePaginatedQuery<Row>({ endpoint: '/notifications', mode: 'append', defaults: { perPage: 20 } })
    )
    await waitFor(() => expect(result.current.items).toEqual([{ id: 'r1' }]))
    act(() => result.current.setPage(2))
    await waitFor(() => expect(result.current.items).toEqual([{ id: 'r1' }, { id: 'r2' }]))
  })
})

describe('useAllPages', () => {
  it('loads every page and flags truncation', async () => {
    getSpy.mockImplementation(async (endpoint) => envelope(Number(params(endpoint).get('page')), 200, 1000))
    const { result } = renderHook(() => useAllPages<Row>('/incidents/1/timeline', { maxPages: 3 }))
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.items.map((r) => r.id)).toEqual(['r1', 'r2', 'r3'])
    expect(result.current.total).toBe(1000)
    expect(result.current.truncated).toBe(true)
    expect(getSpy.mock.calls.every((c) => params(c[0]).get('per_page') === '200')).toBe(true)
  })

  it('shares one fetch between readers and refreshes on invalidate', async () => {
    getSpy.mockImplementation(async (endpoint) => envelope(Number(params(endpoint).get('page')), 200, 150))
    const a = renderHook(() => useAllPages<Row>('/incidents/1/timeline'))
    await waitFor(() => expect(a.result.current.items).toHaveLength(1))
    const b = renderHook(() => useAllPages<Row>('/incidents/1/timeline'))
    expect(b.result.current.items).toHaveLength(1)
    expect(getSpy).toHaveBeenCalledTimes(1)
    expect(a.result.current.truncated).toBe(false)
    act(() => cache.invalidate('/incidents/1/timeline'))
    await waitFor(() => expect(getSpy.mock.calls.length).toBeGreaterThanOrEqual(2))
  })
})
