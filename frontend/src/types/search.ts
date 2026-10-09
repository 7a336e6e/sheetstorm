/**
 * Global search (`GET /search`). Contract owned by W0-PG
 * (search-pagination §3.2); keep in sync with `services/search_service.py`.
 */

export type SearchResultType =
  | 'incident'
  | 'timeline_event'
  | 'host'
  | 'account'
  | 'network_ioc'
  | 'host_ioc'
  | 'malware'
  | 'case_note'

export type SearchSort = 'relevance' | '-timestamp' | 'timestamp'

/** Where a hit lives: `/dashboard/incidents/<incident_id>?tab=<tab>&row=<row>`. */
export interface SearchResultLink {
  incident_id: string
  tab: string
  row?: string | null
}

export interface SearchResult {
  type: SearchResultType
  id: string
  incident_id: string
  incident_title?: string
  incident_number?: number
  title: string
  snippet?: string | null
  timestamp?: string | null
  link: SearchResultLink
}

export interface SearchResponse {
  results: SearchResult[]
  total: number
  page: number
  per_page: number
  pages: number
  facets: Partial<Record<SearchResultType, number>>
}
