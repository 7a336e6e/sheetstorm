"use client"

/**
 * Global search results (`GET /search`): every record type the user may
 * read, across the incidents they can access. URL state: `q`, `types`,
 * `incident_id`, `sort`, `page`, `per` — shareable and reload-safe; the
 * command palette's "See all results" lands here with `?q=`.
 *
 * `/search` answers `{results, facets, …}` rather than the list envelope, so
 * this page adapts it to the `PaginatedQuery` shape DataTable renders.
 */
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { DataTable, FilterSelect, type DataTableColumn } from '@/components/ui/data-table'
import { IncidentPicker } from '@/components/ui/entity-picker'
import { Timestamp } from '@/components/ui/timestamp'
import api, { ApiError, isAbortError, isApiError, withQuery } from '@/lib/api'
import { getCached, setCached } from '@/lib/query-cache'
import type { ListState, PaginatedQuery } from '@/hooks/use-paginated-query'
import {
  normalizeSearchQuery,
  saveRecentSearch,
  SEARCH_ENDPOINT,
  SEARCH_MIN_QUERY,
  SEARCH_TYPE_LABELS,
  SEARCH_TYPE_ORDER,
  searchResultHref,
  splitHighlight,
} from '@/lib/global-search'
import { cn } from '@/lib/utils'
import type { SearchResponse, SearchResult, SearchResultType } from '@/types'

const PER_PAGE_DEFAULT = 25
const PER_PAGE_MAX = 50
const DEBOUNCE_MS = 300
const FILTER_KEYS = ['types', 'incident_id'] as const

const SORT_OPTIONS = [
  { value: '-timestamp', label: 'Newest first' },
  { value: 'timestamp', label: 'Oldest first' },
]

function toInt(v: string | null, min: number, max: number, fallback: number): number {
  if (!v || !/^\d+$/.test(v)) return fallback
  const n = parseInt(v, 10)
  return n >= min && n <= max ? n : fallback
}

function readState(params: Pick<URLSearchParams, 'get'>): ListState {
  const filters: Record<string, string> = {}
  FILTER_KEYS.forEach((k) => {
    const v = params.get(k)
    if (v) filters[k] = v
  })
  const q = normalizeSearchQuery(params.get('q') ?? '')
  const sort = params.get('sort')
  return {
    page: toInt(params.get('page'), 1, Number.MAX_SAFE_INTEGER, 1),
    perPage: toInt(params.get('per'), 1, PER_PAGE_MAX, PER_PAGE_DEFAULT),
    sort: sort === '-timestamp' || sort === 'timestamp' ? sort : undefined,
    q: q || undefined,
    filters,
  }
}

function writeState(s: ListState): string {
  const p = new URLSearchParams()
  if (s.q) p.set('q', s.q)
  FILTER_KEYS.forEach((k) => {
    if (s.filters[k]) p.set(k, s.filters[k])
  })
  if (s.sort) p.set('sort', s.sort)
  if (s.page > 1) p.set('page', String(s.page))
  if (s.perPage !== PER_PAGE_DEFAULT) p.set('per', String(s.perPage))
  return p.toString()
}

type SearchQuery = PaginatedQuery<SearchResult> & { facets: SearchResponse['facets'] }

function useSearchQuery(): SearchQuery {
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  const sig = params?.toString() ?? ''
  const state = useMemo(() => readState(new URLSearchParams(sig)), [sig])
  const stateRef = useRef(state)
  useEffect(() => {
    stateRef.current = state
  }, [state])

  const update = useCallback(
    (fn: (s: ListState) => ListState) => {
      const next = fn(stateRef.current)
      stateRef.current = next
      const qs = writeState(next)
      router.replace(`${pathname}${qs ? `?${qs}` : ''}`, { scroll: false })
    },
    [router, pathname]
  )

  const enabled = (state.q?.length ?? 0) >= SEARCH_MIN_QUERY
  const key = enabled
    ? withQuery(SEARCH_ENDPOINT, {
        q: state.q,
        types: state.filters.types,
        incident_id: state.filters.incident_id,
        sort: state.sort ?? 'relevance',
        page: state.page,
        per_page: state.perPage,
      })
    : null

  const [result, setResult] = useState<{ key: string; data: SearchResponse } | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [isFetching, setIsFetching] = useState(false)
  const [tick, setTick] = useState(0)
  const waiters = useRef<Array<() => void>>([])
  const settle = () => {
    const w = waiters.current
    waiters.current = []
    w.forEach((fn) => fn())
  }

  useEffect(() => {
    if (!key) {
      settle()
      return
    }
    const ctrl = new AbortController()
    setIsFetching(true)
    api
      .get<SearchResponse>(key, { signal: ctrl.signal })
      .then((data) => {
        if (ctrl.signal.aborted) return
        setError(null)
        setCached(key, data)
        setResult({ key, data })
      })
      .catch((err) => {
        if (isAbortError(err) || ctrl.signal.aborted) return
        setError(isApiError(err) ? err : new ApiError(0, 'Request failed', { code: 'client_error' }))
      })
      .finally(() => {
        if (!ctrl.signal.aborted) {
          setIsFetching(false)
          settle()
        }
      })
    return () => {
      ctrl.abort()
      setIsFetching(false)
    }
  }, [key, tick])

  // Remember queries that were actually run.
  useEffect(() => {
    if (enabled && state.q) saveRecentSearch(state.q)
  }, [enabled, state.q])

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    },
    []
  )

  // Exact answer, else a cached one (stale-while-revalidate), else keep the
  // previous results on screen (dimmed) while the next query loads.
  const data = !key
    ? null
    : result?.key === key
      ? result.data
      : (getCached<SearchResponse>(key)?.data ?? result?.data ?? null)

  return {
    items: data?.results ?? [],
    total: data?.total ?? 0,
    pages: data?.pages ?? 0,
    facets: data?.facets ?? {},
    state,
    isLoading: !!key && !data && !error,
    isFetching,
    error: key ? error : null,
    setPage: (n) => update((s) => ({ ...s, page: Math.max(1, Math.floor(n)) })),
    setPerPage: (n) => update((s) => ({ ...s, perPage: Math.min(PER_PAGE_MAX, Math.max(1, Math.floor(n))), page: 1 })),
    setSort: (sort) =>
      update((s) => ({ ...s, sort: sort === '-timestamp' || sort === 'timestamp' ? sort : undefined, page: 1 })),
    setQuery: (q) => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      const apply = () => update((s) => ({ ...s, q: normalizeSearchQuery(q) || undefined, page: 1 }))
      if (!q.trim()) apply()
      else debounceRef.current = setTimeout(apply, DEBOUNCE_MS)
    },
    setFilter: (k, v) =>
      update((s) => {
        const filters = { ...s.filters }
        if (v) filters[k] = v
        else delete filters[k]
        return { ...s, filters, page: 1 }
      }),
    resetFilters: () => update((s) => ({ ...s, q: undefined, filters: {}, page: 1 })),
    refetch: () =>
      new Promise<void>((resolve) => {
        waiters.current.push(resolve)
        setTick((t) => t + 1)
      }),
  }
}

function Highlight({ text, q }: { text: string; q: string }) {
  return (
    <>
      {splitHighlight(text, q).map((part, i) =>
        part.match ? (
          <mark key={i} className="rounded-sm bg-cyan-500/20 text-cyan-200">
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        )
      )}
    </>
  )
}

function SearchPageContent() {
  const router = useRouter()
  const query = useSearchQuery()
  const q = query.state.q ?? ''
  const typeFilter = query.state.filters.types as SearchResultType | undefined

  const columns = useMemo<DataTableColumn<SearchResult>[]>(
    () => [
      {
        id: 'type',
        header: 'Type',
        className: 'w-[140px]',
        cell: (r) => (
          <span className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[11px] text-muted-foreground">
            {SEARCH_TYPE_LABELS[r.type] ?? r.type}
          </span>
        ),
      },
      {
        id: 'result',
        header: 'Result',
        cell: (r) => (
          <div className="min-w-0">
            <p className="truncate font-medium text-foreground">
              <Highlight text={r.title || '(untitled)'} q={q} />
            </p>
            {r.snippet && (
              <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                <Highlight text={r.snippet} q={q} />
              </p>
            )}
          </div>
        ),
      },
      {
        id: 'incident',
        header: 'Incident',
        className: 'w-[240px]',
        hideBelow: 'md',
        cell: (r) => <span className="line-clamp-2 text-sm text-muted-foreground">{r.incident_title ?? '—'}</span>,
      },
      {
        id: 'timestamp',
        header: 'Time',
        className: 'w-[200px]',
        hideBelow: 'lg',
        cell: (r) => <Timestamp value={r.timestamp} className="text-sm text-muted-foreground" />,
      },
    ],
    [q]
  )

  const facetTypes = SEARCH_TYPE_ORDER.filter((t) => (query.facets[t] ?? 0) > 0)

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground lg:text-3xl">Search</h1>
        <p className="mt-1 text-muted-foreground">
          Search incidents, timeline events, hosts, accounts, IOCs, malware and case notes you have access to.
        </p>
      </div>

      {facetTypes.length > 0 && !typeFilter && (
        <div className="flex flex-wrap gap-2" aria-label="Results by type">
          {facetTypes.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => query.setFilter('types', t)}
              className={cn(
                'rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-white/10 hover:text-foreground'
              )}
            >
              {SEARCH_TYPE_LABELS[t]} <span className="tabular-nums text-foreground">{query.facets[t]}</span>
            </button>
          ))}
        </div>
      )}

      <DataTable
        query={query}
        columns={columns}
        getRowId={(r) => `${r.type}:${r.id}`}
        ariaLabel="Search results"
        searchPlaceholder="Search (IP, hash, hostname, text…)"
        pageSizes={[10, 25, 50]}
        toolbar={
          <>
            <FilterSelect
              label="Types"
              value={typeFilter}
              onChange={(v) => query.setFilter('types', v)}
              options={SEARCH_TYPE_ORDER.map((t) => ({ value: t, label: SEARCH_TYPE_LABELS[t] }))}
            />
            <IncidentPicker
              ariaLabel="Incident"
              placeholder="Any incident"
              value={query.state.filters.incident_id ?? null}
              onChange={(id) => query.setFilter('incident_id', id ?? undefined)}
              className="w-[240px]"
            />
            <FilterSelect
              label="Order"
              allLabel="Best match"
              value={query.state.sort}
              onChange={(v) => query.setSort(v)}
              options={SORT_OPTIONS}
            />
          </>
        }
        onRowClick={(r) => {
          const href = searchResultHref(r)
          if (href) router.push(href)
        }}
        empty={{
          title: 'Search across your incidents',
          description: `Type at least ${SEARCH_MIN_QUERY} characters. Press Ctrl+K (⌘K) anywhere for quick search.`,
        }}
      />
    </div>
  )
}

export default function SearchPage() {
  return (
    <Suspense fallback={null}>
      <SearchPageContent />
    </Suspense>
  )
}
