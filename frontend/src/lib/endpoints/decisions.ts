/**
 * Decision & response-action log (W4-DEC).
 *
 *   GET  /incidents/<id>/decisions                     decisions:read (paginated)
 *   POST /incidents/<id>/decisions                     decisions:create
 *   PUT  /incidents/<id>/decisions/<did>               decisions:update (If-Match, reason)
 *   POST /incidents/<id>/decisions/<did>/<event>       approve | reject | reopen | supersede
 *   GET  /incidents/<id>/decisions/<did>/revisions
 *   GET  /incidents/<id>/response-actions              response_actions:read (paginated)
 *   POST /incidents/<id>/response-actions              response_actions:create
 *   PUT  /incidents/<id>/response-actions/<aid>        response_actions:update (If-Match, reason)
 *   POST /incidents/<id>/response-actions/<aid>/<event> authorize | start | execute | fail | verify | rollback | cancel
 *   GET  /incidents/<id>/response-actions/<aid>/revisions
 *   GET  /incidents/<id>/response-timeline             virtual Events-table rows
 *   GET  /incidents/<id>/decision-log/export           incidents:export (json | csv | pdf)
 *
 * Transitions are POSTs: the version travels as body `expected_version`
 * (the backend requires it, like If-Match on PUT).
 */
import { api, downloadTo, withQuery } from '@/lib/api'
import type {
  Decision,
  DecisionEvent,
  DecisionInput,
  ResponseAction,
  ResponseActionEvent,
  ResponseActionInput,
  DecisionRevisionsResponse,
  DecisionTransitionInput,
  VirtualTimelineRow,
} from '@/types'

export const decisionsEndpoint = (incidentId: string) => `/incidents/${incidentId}/decisions`
export const responseActionsEndpoint = (incidentId: string) => `/incidents/${incidentId}/response-actions`

export type DecisionLogExportFormat = 'json' | 'csv' | 'pdf'

export const decisionLog = {
  createDecision: (incidentId: string, data: DecisionInput) =>
    api.post<Decision>(decisionsEndpoint(incidentId), data),

  updateDecision: (incidentId: string, id: string, data: DecisionInput, version: number) =>
    api.put<Decision>(`${decisionsEndpoint(incidentId)}/${id}`, data, { ifMatch: version }),

  transitionDecision: (incidentId: string, id: string, event: DecisionEvent, data: DecisionTransitionInput, version: number) =>
    api.post<Decision>(`${decisionsEndpoint(incidentId)}/${id}/${event}`, { ...data, expected_version: version }),

  decisionRevisions: (incidentId: string, id: string, opts?: { signal?: AbortSignal }) =>
    api.get<DecisionRevisionsResponse>(`${decisionsEndpoint(incidentId)}/${id}/revisions`, opts),

  createAction: (incidentId: string, data: ResponseActionInput & Record<string, unknown>) =>
    api.post<ResponseAction>(responseActionsEndpoint(incidentId), data),

  updateAction: (incidentId: string, id: string, data: ResponseActionInput, version: number) =>
    api.put<ResponseAction>(`${responseActionsEndpoint(incidentId)}/${id}`, data, { ifMatch: version }),

  transitionAction: (
    incidentId: string,
    id: string,
    event: ResponseActionEvent,
    data: DecisionTransitionInput,
    version: number
  ) => api.post<ResponseAction>(`${responseActionsEndpoint(incidentId)}/${id}/${event}`, { ...data, expected_version: version }),

  actionRevisions: (incidentId: string, id: string, opts?: { signal?: AbortSignal }) =>
    api.get<DecisionRevisionsResponse>(`${responseActionsEndpoint(incidentId)}/${id}/revisions`, opts),

  responseTimeline: (incidentId: string, opts?: { signal?: AbortSignal }) =>
    api.get<{ items: VirtualTimelineRow[] }>(`/incidents/${incidentId}/response-timeline`, opts),

  exportLog: (
    incidentId: string,
    format: DecisionLogExportFormat,
    opts: { includePrivileged?: boolean; includeRevisions?: boolean; fallbackName: string }
  ) =>
    downloadTo(
      withQuery(`/incidents/${incidentId}/decision-log/export`, {
        format,
        include_privileged: opts.includePrivileged ? '1' : undefined,
        include_revisions: opts.includeRevisions ? '1' : undefined,
      }),
      { fallbackName: opts.fallbackName }
    ),
}
