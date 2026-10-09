/** Exports, STIX, IOC correlation and bulk enrichment (W3-DFIR-C). */
import type { TLPLevel } from './index'

/** `GET /incidents/<id>/export/<entity>` (backend services/csv_export.py). */
export type ExportEntity =
  | 'timeline'
  | 'hosts'
  | 'accounts'
  | 'network-iocs'
  | 'host-iocs'
  | 'malware'
  | 'tasks'

export interface CorrelatedIncident {
  id: string
  title: string
}

/** One value that appears in more than one incident the caller can access. */
export interface IOCCorrelation {
  ioc_value: string
  ioc_type: string
  /** Includes the incident the dialog was opened from. */
  incident_count: number
  incidents: CorrelatedIncident[]
}

export interface IOCCorrelationResponse {
  correlations: IOCCorrelation[]
  total: number
  incident_id?: string
}

export type EnrichIOCType = 'ip' | 'domain' | 'hash' | 'md5' | 'sha1' | 'sha256' | 'email' | 'hostname'

export interface EnrichRequestItem {
  value: string
  type: EnrichIOCType
}

export type EnrichStatus = 'success' | 'error' | 'blocked'

export interface EnrichResult {
  value: string
  type: string
  status: EnrichStatus
  /** One line for the result table. */
  summary?: string
  error?: string
  enrichment?: Record<string, unknown>
}

export interface BulkEnrichResponse {
  results: EnrichResult[]
  total: number
  enriched: number
  failed: number
  blocked: number
  /** Providers that answered (e.g. `virustotal`). */
  providers: string[]
  incident_id?: string
  tlp?: TLPLevel
}

/** What the UI must do before values of an incident of this TLP are enriched. */
export type EnrichmentGate = 'confirm' | 'acknowledge' | 'blocked'
