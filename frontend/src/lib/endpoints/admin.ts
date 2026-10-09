/**
 * Audit governance and admin overview endpoints (W1-AUD-BE):
 *
 *   GET  /audit-logs                  list (usePaginatedQuery on AUDIT_LOGS_ENDPOINT)
 *   GET  /audit-logs/<id>             one row (full details.changes)
 *   GET  /audit-logs/facets           distinct actions / resource types
 *   GET  /audit-logs/stats            counts for the same filters
 *   GET  /audit-logs/export           csv | jsonl (audit_logs:export, 10/h)
 *   GET  /admin/overview              organizations:manage
 *   GET  /admin/system-status         organizations:manage (infra only for platform admins)
 *   GET  /admin/audit-settings        organizations:manage
 *   PUT  /admin/audit-settings        organizations:manage (409 confirmation_required)
 *   GET  /admin/audit-integrity       organizations:manage (6/h)
 */
import { api, downloadTo, isApiError, withQuery } from '@/lib/api'
import type {
  AdminOverview,
  AuditExportFormat,
  AuditFacets,
  AuditIntegrityResult,
  AuditLogEntry,
  AuditLogFilters,
  AuditRetentionConflict,
  AuditSettings,
  AuditSettingsUpdate,
  AuditStats,
  SystemStatus,
} from '@/types'

export const AUDIT_LOGS_ENDPOINT = '/audit-logs'

type Filters = AuditLogFilters | Record<string, string | undefined>

export const auditLogsApi = {
  get: (id: string) => api.get<AuditLogEntry>(`${AUDIT_LOGS_ENDPOINT}/${encodeURIComponent(id)}`),
  facets: () => api.get<AuditFacets>(`${AUDIT_LOGS_ENDPOINT}/facets`),
  stats: (filters: Filters = {}, opts?: { signal?: AbortSignal }) =>
    api.get<AuditStats>(withQuery(`${AUDIT_LOGS_ENDPOINT}/stats`, { ...filters }), opts),
  /**
   * Download the filtered log. The server names the file
   * (`audit-<org>-<UTC stamp>.<ext>`); resolves to the name used. Rejects
   * with ApiError 422 `export_too_large` / 429 / 403 like any request.
   */
  exportFile: (filters: Filters, format: AuditExportFormat) =>
    downloadTo(withQuery(`${AUDIT_LOGS_ENDPOINT}/export`, { ...filters, format }), {
      fallbackName: `audit-log.${format}`,
    }),
}

export const admin = {
  getOverview: () => api.get<AdminOverview>('/admin/overview'),
  getSystemStatus: () => api.get<SystemStatus>('/admin/system-status'),
  getAuditSettings: () => api.get<AuditSettings>('/admin/audit-settings'),
  updateAuditSettings: (data: AuditSettingsUpdate) => api.put<AuditSettings>('/admin/audit-settings', data),
  verifyAuditIntegrity: () => api.get<AuditIntegrityResult>('/admin/audit-integrity'),
}

/** The 409 body of a retention change that needs `confirm: true`, else null. */
export function retentionConflict(err: unknown): AuditRetentionConflict | null {
  if (!isApiError(err) || err.status !== 409 || err.code !== 'confirmation_required') return null
  const d = err.details ?? {}
  return {
    error: 'confirmation_required',
    message: typeof d.message === 'string' ? d.message : err.message,
    would_purge: typeof d.would_purge === 'number' ? d.would_purge : 0,
    cutoff: typeof d.cutoff === 'string' ? d.cutoff : '',
  }
}
