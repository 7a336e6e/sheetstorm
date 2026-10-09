/**
 * Metrics, after-action review and improvement actions (W3-RT-POST).
 *
 *   GET    /incidents/<id>/metrics               incidents:read
 *   GET    /metrics/incidents                    metrics:read (30/min)
 *   GET    /incidents/<id>/review                incidents:read
 *   PUT    /incidents/<id>/review                incidents:update (If-Match)
 *   POST   /incidents/<id>/improvement-actions   improvements:create
 *   GET    /improvement-actions                  improvements:read (org list)
 *   PUT    /improvement-actions/<id>             improvements:update (If-Match)
 *   DELETE /improvement-actions/<id>             improvements:delete (If-Match)
 *
 * The two action lists are paginated: read them with `usePaginatedQuery`
 * on the endpoints below.
 */
import { api, withQuery } from '@/lib/api'
import type {
  ImprovementAction,
  ImprovementActionInput,
  IncidentMetrics,
  IncidentReview,
  OrgMetrics,
  OrgMetricsParams,
  ReviewInput,
  ReviewResponse,
} from '@/types'

/** Org-wide improvement action list (paginated). */
export const IMPROVEMENT_ACTIONS_ENDPOINT = '/improvement-actions'

/** Improvement actions of one incident (paginated). */
export const incidentActionsEndpoint = (incidentId: string) => `/incidents/${incidentId}/improvement-actions`

export const postIncident = {
  incidentMetrics: (incidentId: string, opts?: { signal?: AbortSignal }) =>
    api.get<IncidentMetrics>(`/incidents/${incidentId}/metrics`, opts),

  orgMetrics: (params: OrgMetricsParams, opts?: { signal?: AbortSignal }) =>
    api.get<OrgMetrics>(withQuery('/metrics/incidents', { ...params }), opts),

  getReview: (incidentId: string, opts?: { signal?: AbortSignal }) =>
    api.get<ReviewResponse>(`/incidents/${incidentId}/review`, opts),

  /** Upsert; a stale `version` answers 409 `conflict`. */
  saveReview: (incidentId: string, data: ReviewInput, version?: number) =>
    api.put<IncidentReview>(`/incidents/${incidentId}/review`, data, { ifMatch: version }),

  createAction: (incidentId: string, data: ImprovementActionInput & { title: string }) =>
    api.post<ImprovementAction>(incidentActionsEndpoint(incidentId), data),

  updateAction: (id: string, data: ImprovementActionInput, version?: number) =>
    api.put<ImprovementAction>(`${IMPROVEMENT_ACTIONS_ENDPOINT}/${id}`, data, { ifMatch: version }),

  deleteAction: (id: string, version?: number) =>
    api.delete(`${IMPROVEMENT_ACTIONS_ENDPOINT}/${id}`, undefined, { ifMatch: version }),
}
