/**
 * Helpers shared by the command palette and the /dashboard/search page
 * (`GET /search`, contract in `types/search.ts`).
 */
import { safeDashboardHref } from './feature-stores'
import type { SearchResult, SearchResultType } from '@/types'

export const SEARCH_ENDPOINT = '/search'
/** The palette queries entities from this many characters on. */
export const PALETTE_MIN_QUERY = 3
/** The backend rejects shorter queries. */
export const SEARCH_MIN_QUERY = 2
export const SEARCH_MAX_QUERY = 200

/** Display order and labels of result groups. */
export const SEARCH_TYPE_ORDER: SearchResultType[] = [
  'incident',
  'host',
  'account',
  'network_ioc',
  'host_ioc',
  'malware',
  'timeline_event',
  'case_note',
]

export const SEARCH_TYPE_LABELS: Record<SearchResultType, string> = {
  incident: 'Incidents',
  timeline_event: 'Timeline events',
  host: 'Hosts',
  account: 'Accounts',
  network_ioc: 'Network IOCs',
  host_ioc: 'Host IOCs',
  malware: 'Malware & tools',
  case_note: 'Case notes',
}

const SAFE_SEGMENT = /^[A-Za-z0-9_-]+$/

/**
 * Deep link for a hit: `/dashboard/incidents/<id>?tab=<tab>&row=<row>`.
 * Ids and tab come from the server but are still validated, and the result
 * goes through the same internal-path guard as notification links.
 */
export function searchResultHref(r: Pick<SearchResult, 'incident_id' | 'link'>): string | null {
  const incidentId = r.link?.incident_id ?? r.incident_id
  if (typeof incidentId !== 'string' || !SAFE_SEGMENT.test(incidentId)) return null
  const params = new URLSearchParams()
  const tab = r.link?.tab
  const row = r.link?.row
  if (typeof tab === 'string' && SAFE_SEGMENT.test(tab) && tab !== 'overview') params.set('tab', tab)
  if (typeof row === 'string' && SAFE_SEGMENT.test(row)) {
    if (!params.has('tab') && tab) params.set('tab', tab)
    params.set('row', row)
  }
  const qs = params.toString()
  return safeDashboardHref(`/dashboard/incidents/${incidentId}${qs ? `?${qs}` : ''}`)
}

/** Strip control characters and clamp to the server's limit. */
export function normalizeSearchQuery(q: string): string {
  return q.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, SEARCH_MAX_QUERY)
}

/**
 * Split `text` around case-insensitive matches of `q` for highlighting.
 * Rendered as text + <mark> nodes by the caller (never as HTML).
 */
export function splitHighlight(text: string, q: string): { text: string; match: boolean }[] {
  const needle = q.trim().toLowerCase()
  if (!text || !needle) return text ? [{ text, match: false }] : []
  const parts: { text: string; match: boolean }[] = []
  const hay = text.toLowerCase()
  let from = 0
  let idx = hay.indexOf(needle, from)
  while (idx !== -1) {
    if (idx > from) parts.push({ text: text.slice(from, idx), match: false })
    parts.push({ text: text.slice(idx, idx + needle.length), match: true })
    from = idx + needle.length
    idx = hay.indexOf(needle, from)
  }
  if (from < text.length) parts.push({ text: text.slice(from), match: false })
  return parts
}

// ── Recent searches (sessionStorage, query text only) ─────────────────

export const RECENT_SEARCHES_KEY = 'sheetstorm-recent-searches'
export const RECENT_SEARCHES_MAX = 5

function storage(): Storage | null {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null
  } catch {
    return null
  }
}

export function loadRecentSearches(): string[] {
  try {
    const raw = storage()?.getItem(RECENT_SEARCHES_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((v): v is string => typeof v === 'string' && v.trim().length > 0)
      .slice(0, RECENT_SEARCHES_MAX)
  } catch {
    return []
  }
}

export function saveRecentSearch(q: string): string[] {
  const value = normalizeSearchQuery(q)
  if (value.length < SEARCH_MIN_QUERY) return loadRecentSearches()
  const next = [value, ...loadRecentSearches().filter((v) => v.toLowerCase() !== value.toLowerCase())].slice(
    0,
    RECENT_SEARCHES_MAX
  )
  try {
    storage()?.setItem(RECENT_SEARCHES_KEY, JSON.stringify(next))
  } catch {
    // Storage unavailable (private mode, quota): recents are a convenience.
  }
  return next
}
