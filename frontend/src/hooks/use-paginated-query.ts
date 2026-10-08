"use client"

/**
 * Server-paginated list state (page / per_page / sort / q / filters / focus)
 * against the backend pagination contract (`utils/pagination.py`):
 *   request:  ?page&per_page&sort=-field[,field2]&q&<filter>=…&focus=<uuid>
 *   response: { items, total, page, per_page, pages, sort, focus_found? }
 *
 * - Stale-while-revalidate through `lib/query-cache`: cached pages render
 *   instantly and refetch in the background; `invalidate(endpoint)` anywhere
 *   makes every reader of that endpoint refetch.
 * - In-flight requests are aborted when the params change or on unmount.
 * - Errors land in `error` (DataTable renders them); they are not toasted.
 * - With `urlKey`, state is mirrored in the URL as `<urlKey>.page`, `.per`,
 *   `.sort`, `.q` and `.f.<name>` (only non-default values), so lists are
 *   shareable and survive reloads. The component must render inside a
 *   <Suspense> boundary (Next requires it for `useSearchParams`).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import api, { ApiError, isAbortError, isApiError, withQuery } from '@/lib/api'
import { getCached, invalidate, setCached, subscribe } from '@/lib/query-cache'
import { useSocket } from '@/hooks/use-socket'
import type { PaginatedResponse } from '@/types'

export interface ListState {
  page: number
  perPage: number
  sort?: string
  q?: string
  filters: Record<string, string>
}

export interface PaginatedQuery<T> {
  items: T[]
  total: number
  pages: number
  state: ListState
  /** First load: nothing to show yet. */
  isLoading: boolean
  /** Any request in flight (including background revalidation). */
  isFetching: boolean
  error: ApiError | null
  setPage(n: number): void
  setPerPage(n: number): void
  setSort(s?: string): void
  /** Debounced 300ms (immediate when cleared); resets to page 1. */
  setQuery(q: string): void
  /** Resets to page 1. `undefined` / '' removes the filter. */
  setFilter(k: string, v?: string): void
  /** Clears q and every filter at once (page 1). */
  resetFilters(): void
  refetch(): Promise<void>
  /** Result of the `focus` lookup, once the server answered it. */
  focusFound?: boolean
}

export interface PaginatedQueryOptions {
  /** e.g. `/incidents/${id}/hosts`; may already carry fixed query params. */
  endpoint: string
  defaults?: Partial<ListState>
  urlKey?: string
  /** Row id to land on: the server returns the page containing it (sent once). */
  focus?: string | null
  enabled?: boolean
  /** 'append' accumulates pages ("load more"); page is not URL-synced. */
  mode?: 'page' | 'append'
  /** Socket event names that invalidate this endpoint. */
  invalidateOn?: string[]
  /** Realtime entity for live merge. Reserved: no-op until W2-RT-FE. */
  live?: string
}

export const DEFAULT_PER_PAGE = 50
export const MAX_PER_PAGE = 200
export const QUERY_DEBOUNCE_MS = 300
/** Cache entries younger than this are not revalidated on mount/param change. */
export const FRESH_MS = 2000

type ParamsLike = Pick<URLSearchParams, 'get' | 'forEach'>

function normalizeDefaults(d?: Partial<ListState>): ListState {
  return {
    page: d?.page ?? 1,
    perPage: d?.perPage ?? DEFAULT_PER_PAGE,
    sort: d?.sort || undefined,
    q: d?.q || undefined,
    filters: { ...(d?.filters ?? {}) },
  }
}

function toInt(v: string | null, min: number, max: number): number | undefined {
  if (v === null || !/^\d+$/.test(v)) return undefined
  const n = parseInt(v, 10)
  return n >= min && n <= max ? n : undefined
}

/** Read `<urlKey>.*` params over `defaults`. Invalid values fall back to defaults. */
export function parseListState(params: ParamsLike, urlKey: string, defaults: ListState): ListState {
  const p = `${urlKey}.`
  const filters: Record<string, string> = { ...defaults.filters }
  params.forEach((value, key) => {
    if (key.startsWith(`${p}f.`)) {
      const name = key.slice(p.length + 2)
      if (!name) return
      if (value === '') delete filters[name]
      else filters[name] = value
    }
  })
  const sortParam = params.get(`${p}sort`)
  const qParam = params.get(`${p}q`)
  return {
    page: toInt(params.get(`${p}page`), 1, Number.MAX_SAFE_INTEGER) ?? defaults.page,
    perPage: toInt(params.get(`${p}per`), 1, MAX_PER_PAGE) ?? defaults.perPage,
    sort: sortParam === null ? defaults.sort : sortParam || undefined,
    q: qParam === null ? defaults.q : qParam || undefined,
    filters,
  }
}

/**
 * Write `state` into a copy of `base` under `<urlKey>.*`, keeping unrelated
 * params. Values equal to the defaults are omitted; a default filter or sort
 * that was cleared is written as an empty value so it stays cleared.
 */
export function serializeListState(
  base: ParamsLike,
  urlKey: string,
  state: ListState,
  defaults: ListState,
  opts: { includePage?: boolean } = {}
): URLSearchParams {
  const p = `${urlKey}.`
  const out = new URLSearchParams()
  base.forEach((value, key) => {
    if (!key.startsWith(p)) out.append(key, value)
  })
  const includePage = opts.includePage ?? true
  if (includePage && state.page !== defaults.page) out.set(`${p}page`, String(state.page))
  if (state.perPage !== defaults.perPage) out.set(`${p}per`, String(state.perPage))
  if ((state.sort ?? '') !== (defaults.sort ?? '')) out.set(`${p}sort`, state.sort ?? '')
  if ((state.q ?? '') !== (defaults.q ?? '')) out.set(`${p}q`, state.q ?? '')
  const names = new Set([...Object.keys(defaults.filters), ...Object.keys(state.filters)])
  Array.from(names)
    .sort()
    .forEach((name) => {
      const v = state.filters[name] ?? ''
      if (v !== (defaults.filters[name] ?? '')) out.set(`${p}f.${name}`, v)
    })
  return out
}

/** Contract query params for a list state. */
export function listParams(state: ListState): Record<string, string | number | undefined> {
  return {
    ...state.filters,
    page: state.page,
    per_page: state.perPage,
    sort: state.sort,
    q: state.q,
  }
}

function pathOf(endpoint: string): string {
  const i = endpoint.indexOf('?')
  return i === -1 ? endpoint : endpoint.slice(0, i)
}

/** Resolve pending refetch() promises. */
function settle(ref: { current: Array<() => void> }) {
  const w = ref.current
  ref.current = []
  w.forEach((fn) => fn())
}

function asApiError(err: unknown): ApiError {
  if (isApiError(err)) return err
  return new ApiError(0, err instanceof Error ? err.message : 'Request failed', { code: 'client_error' })
}

export function usePaginatedQuery<T>(opts: PaginatedQueryOptions): PaginatedQuery<T> {
  const { endpoint, urlKey, mode = 'page', invalidateOn } = opts
  const enabled = opts.enabled ?? true
  const append = mode === 'append'
  const endpointPath = pathOf(endpoint)

  const defaultsSig = JSON.stringify(opts.defaults ?? {})
  const defaults = useMemo(() => normalizeDefaults(JSON.parse(defaultsSig)), [defaultsSig])

  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  // ── List state: URL-backed (urlKey) or local ─────────────────────────
  const [localState, setLocalState] = useState<ListState>(defaults)
  const urlStateSig = urlKey && searchParams ? JSON.stringify(parseListState(searchParams, urlKey, defaults)) : ''
  const urlState = useMemo<ListState | null>(
    () => (urlStateSig ? (JSON.parse(urlStateSig) as ListState) : null),
    [urlStateSig]
  )
  // In append mode the page is local even when the rest is in the URL.
  const [appendPage, setAppendPage] = useState(1)
  const state = useMemo<ListState>(() => {
    const s = urlState ?? localState
    return append ? { ...s, page: appendPage } : s
  }, [urlState, localState, append, appendPage])

  const stateRef = useRef(state)
  useEffect(() => {
    stateRef.current = state
  }, [state])

  const update = useCallback(
    (fn: (s: ListState) => ListState) => {
      const next = fn(stateRef.current)
      stateRef.current = next
      if (append) setAppendPage(next.page)
      if (urlKey) {
        const base = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : new URLSearchParams()
        const qs = serializeListState(base, urlKey, next, defaults, { includePage: !append }).toString()
        router.replace(`${pathname}${qs ? `?${qs}` : ''}`, { scroll: false })
      } else {
        setLocalState(next)
      }
    },
    [append, urlKey, defaults, router, pathname]
  )

  // ── Focus (deep link): sent once per new value ───────────────────────
  const [focusPending, setFocusPending] = useState<string | null>(opts.focus ?? null)
  const [prevFocus, setPrevFocus] = useState(opts.focus ?? null)
  if ((opts.focus ?? null) !== prevFocus) {
    setPrevFocus(opts.focus ?? null)
    setFocusPending(opts.focus ?? null)
  }
  const [focusFound, setFocusFound] = useState<boolean | undefined>(undefined)

  // ── Fetching ─────────────────────────────────────────────────────────
  const requestKey = enabled
    ? withQuery(endpoint, { ...listParams(state), focus: focusPending ?? undefined })
    : null

  const [result, setResult] = useState<{ key: string; data: PaginatedResponse<T> } | null>(null)
  const [pagesAcc, setPagesAcc] = useState<{ base: string; pages: Record<number, T[]> } | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [isFetching, setIsFetching] = useState(false)
  const [tick, setTick] = useState(0)
  const forceRef = useRef(false)
  const waitersRef = useRef<Array<() => void>>([])

  const accept = useCallback(
    (key: string, data: PaginatedResponse<T>) => {
      setResult({ key, data })
      if (append) {
        const base = withQuery(endpoint, { ...listParams({ ...stateRef.current, page: 0 }) })
        setPagesAcc((prev) => {
          const pages = prev && prev.base === base && data.page !== 1 ? { ...prev.pages } : {}
          pages[data.page] = data.items
          return { base, pages }
        })
      }
    },
    [append, endpoint]
  )

  const settleWaiters = () => settle(waitersRef)

  useEffect(() => {
    if (!requestKey) {
      settleWaiters()
      return
    }
    const force = forceRef.current
    forceRef.current = false
    const cached = getCached<PaginatedResponse<T>>(requestKey)
    if (cached) accept(requestKey, cached.data)
    if (cached && !force && Date.now() - cached.ts < FRESH_MS) {
      settleWaiters()
      return
    }

    const ctrl = new AbortController()
    const focusing = focusPending
    setIsFetching(true)
    api
      .get<PaginatedResponse<T>>(requestKey, { signal: ctrl.signal })
      .then((data) => {
        if (ctrl.signal.aborted) return
        setError(null)
        if (focusing) {
          // Store under the plain key of the page the server chose, then
          // move there; that key is fresh, so no second request is made.
          const landed = { ...stateRef.current, page: data.page || 1 }
          const plainKey = withQuery(endpoint, listParams(landed))
          setCached(plainKey, data)
          accept(plainKey, data)
          setFocusFound(data.focus_found ?? true)
          setFocusPending(null)
          if (landed.page !== stateRef.current.page) update(() => landed)
        } else {
          setCached(requestKey, data)
          accept(requestKey, data)
        }
      })
      .catch((err) => {
        if (isAbortError(err) || ctrl.signal.aborted) return
        setError(asApiError(err))
        if (focusing) setFocusPending(null)
      })
      .finally(() => {
        if (!ctrl.signal.aborted) {
          setIsFetching(false)
          settleWaiters()
        }
      })

    return () => {
      ctrl.abort()
      setIsFetching(false)
    }
    // `tick` forces a refetch of the same key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey, tick])

  useEffect(() => () => settle(waitersRef), [])

  const refetch = useCallback((): Promise<void> => {
    return new Promise<void>((resolve) => {
      waitersRef.current.push(resolve)
      forceRef.current = true
      setTick((t) => t + 1)
    })
  }, [])

  // ── Cache events: invalidation and live updates ─────────────────────
  const requestKeyRef = useRef(requestKey)
  useEffect(() => {
    requestKeyRef.current = requestKey
  }, [requestKey])

  useEffect(() => {
    return subscribe(endpointPath, (ev) => {
      if (ev.type === 'invalidate') {
        if (append && stateRef.current.page !== 1) update((s) => ({ ...s, page: 1 }))
        forceRef.current = true
        setTick((t) => t + 1)
      } else if (ev.key === requestKeyRef.current) {
        const entry = getCached<PaginatedResponse<T>>(ev.key)
        if (entry) accept(ev.key, entry.data)
      }
    })
  }, [endpointPath, append, update, accept])

  // ── Socket events → invalidate ───────────────────────────────────────
  const { socket } = useSocket()
  const eventsSig = (invalidateOn ?? []).join('|')
  useEffect(() => {
    if (!socket || !eventsSig) return
    const events = eventsSig.split('|')
    const handler = () => invalidate(endpointPath)
    events.forEach((e) => socket.on(e, handler))
    return () => {
      events.forEach((e) => socket.off(e, handler))
    }
  }, [socket, eventsSig, endpointPath])

  // ── Setters ──────────────────────────────────────────────────────────
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    },
    []
  )

  const setPage = useCallback((n: number) => update((s) => ({ ...s, page: Math.max(1, Math.floor(n)) })), [update])
  const setPerPage = useCallback(
    (n: number) => update((s) => ({ ...s, perPage: Math.min(MAX_PER_PAGE, Math.max(1, Math.floor(n))), page: 1 })),
    [update]
  )
  const setSort = useCallback((sort?: string) => update((s) => ({ ...s, sort: sort || undefined, page: 1 })), [update])
  const setQuery = useCallback(
    (q: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      const apply = () => update((s) => ((s.q ?? '') === q.trim() ? s : { ...s, q: q.trim() || undefined, page: 1 }))
      if (!q.trim()) apply()
      else debounceRef.current = setTimeout(apply, QUERY_DEBOUNCE_MS)
    },
    [update]
  )
  const setFilter = useCallback(
    (k: string, v?: string) =>
      update((s) => {
        const filters = { ...s.filters }
        if (v === undefined || v === '') delete filters[k]
        else filters[k] = v
        return { ...s, filters, page: 1 }
      }),
    [update]
  )
  const resetFilters = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    update((s) => ({ ...s, q: undefined, filters: {}, page: 1 }))
  }, [update])

  // ── Derived output ───────────────────────────────────────────────────
  // Keep showing the previous page of the same endpoint while the next loads.
  const current =
    result && (result.key === requestKey || pathOf(result.key) === endpointPath) ? result.data : null

  let items: T[] = current?.items ?? []
  if (append && pagesAcc) {
    items = Object.keys(pagesAcc.pages)
      .map(Number)
      .sort((a, b) => a - b)
      .filter((p) => p <= state.page)
      .flatMap((p) => pagesAcc.pages[p])
  }

  return {
    items,
    total: current?.total ?? 0,
    pages: current?.pages ?? 0,
    state,
    isLoading: enabled && !current && !error,
    isFetching,
    error,
    setPage,
    setPerPage,
    setSort,
    setQuery,
    setFilter,
    resetFilters,
    refetch,
    focusFound,
  }
}

// ─────────────────────────────────────────────────────────────────────────

export interface AllPagesResult<T> {
  items: T[]
  total: number
  isLoading: boolean
  isFetching: boolean
  error: ApiError | null
  /** True when the list was cut at `maxPages × perPage` rows. */
  truncated: boolean
  refetch(): Promise<void>
}

interface AllPagesData<T> {
  items: T[]
  total: number
  truncated: boolean
}

export const ALL_PAGES_MAX_PAGES = 50

/**
 * Load every page of a list (graph / MITRE / visual timeline / pickers).
 * The only sanctioned "everything" loader: capped at `maxPages` pages of
 * `perPage` (default 50 × 200 = 10,000 rows); `truncated` says when the cap
 * was hit so the UI can warn. Shares the cache, so every caller of the same
 * endpoint gets one request and every `invalidate(endpoint)` refreshes all.
 */
export function useAllPages<T>(
  endpoint: string,
  opts: { perPage?: number; enabled?: boolean; maxPages?: number; live?: string } = {}
): AllPagesResult<T> {
  const perPage = Math.min(MAX_PER_PAGE, Math.max(1, opts.perPage ?? MAX_PER_PAGE))
  const maxPages = Math.max(1, opts.maxPages ?? ALL_PAGES_MAX_PAGES)
  const enabled = opts.enabled ?? true
  const endpointPath = pathOf(endpoint)
  const key = enabled ? withQuery(endpoint, { per_page: perPage, __all: maxPages }) : null

  const [result, setResult] = useState<{ key: string; data: AllPagesData<T> } | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [isFetching, setIsFetching] = useState(false)
  const [tick, setTick] = useState(0)
  const forceRef = useRef(false)
  const waitersRef = useRef<Array<() => void>>([])

  const settleWaiters = () => settle(waitersRef)

  useEffect(() => {
    if (!key) {
      settleWaiters()
      return
    }
    const force = forceRef.current
    forceRef.current = false
    const cached = getCached<AllPagesData<T>>(key)
    if (cached) setResult({ key, data: cached.data })
    if (cached && !force && Date.now() - cached.ts < FRESH_MS) {
      settleWaiters()
      return
    }

    const ctrl = new AbortController()
    const page = (n: number) =>
      api.get<PaginatedResponse<T>>(withQuery(endpoint, { page: n, per_page: perPage }), { signal: ctrl.signal })

    setIsFetching(true)
    ;(async () => {
      const first = await page(1)
      const last = Math.min(first.pages || 1, maxPages)
      const rest: T[][] = []
      // Bounded parallelism: 4 requests at a time.
      for (let start = 2; start <= last; start += 4) {
        const batch = []
        for (let n = start; n < start + 4 && n <= last; n++) batch.push(page(n))
        const pages = await Promise.all(batch)
        pages.forEach((p) => rest.push(p.items))
      }
      const data: AllPagesData<T> = {
        items: first.items.concat(...rest),
        total: first.total,
        truncated: (first.pages || 1) > maxPages,
      }
      return data
    })()
      .then((data) => {
        if (ctrl.signal.aborted) return
        setError(null)
        setCached(key, data)
        setResult({ key, data })
      })
      .catch((err) => {
        if (isAbortError(err) || ctrl.signal.aborted) return
        setError(asApiError(err))
      })
      .finally(() => {
        if (!ctrl.signal.aborted) {
          setIsFetching(false)
          settleWaiters()
        }
      })

    return () => {
      ctrl.abort()
      setIsFetching(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick])

  useEffect(() => () => settle(waitersRef), [])

  const keyRef = useRef(key)
  useEffect(() => {
    keyRef.current = key
  }, [key])

  useEffect(() => {
    return subscribe(endpointPath, (ev) => {
      if (ev.type === 'invalidate') {
        forceRef.current = true
        setTick((t) => t + 1)
      } else if (ev.key === keyRef.current) {
        const entry = getCached<AllPagesData<T>>(ev.key)
        if (entry) setResult({ key: ev.key, data: entry.data })
      }
    })
  }, [endpointPath])

  const refetch = useCallback((): Promise<void> => {
    return new Promise<void>((resolve) => {
      waitersRef.current.push(resolve)
      forceRef.current = true
      setTick((t) => t + 1)
    })
  }, [])

  const current = result && result.key === key ? result.data : null
  return {
    items: current?.items ?? [],
    total: current?.total ?? 0,
    isLoading: enabled && !current && !error,
    isFetching,
    error,
    truncated: current?.truncated ?? false,
    refetch,
  }
}
