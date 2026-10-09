/**
 * Incident Overview editors and dashboard aggregates (W2-DFIR-B).
 */
import { api } from '@/lib/api'
import type { DashboardStats, Incident, IncidentOverviewUpdate } from '@/types'

export const dashboardStatsEndpoint = '/dashboard/stats'

export const incidentOverview = {
  /** PUT with If-Match: a stale `version` answers 409 `conflict`. */
  update: (incidentId: string, data: IncidentOverviewUpdate, version?: number) =>
    api.put<Incident>(`/incidents/${incidentId}`, data, { ifMatch: version }),
  dashboardStats: (opts?: { signal?: AbortSignal }) => api.get<DashboardStats>(dashboardStatsEndpoint, opts),
}
