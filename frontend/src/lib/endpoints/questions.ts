/**
 * Investigative questions, case templates, built-in playbooks and custom
 * fields (W4-QST-UI). Backend: `endpoints/{questions,case_templates,playbooks}.py`.
 *
 *   GET    /incidents/<id>/questions              incidents:read (paginated, `summary` extra)
 *   POST   /incidents/<id>/questions              incidents:update (manual or `library_ref`; 409 duplicate_question)
 *   POST   /incidents/<id>/questions/bulk         incidents:update ({refs} <= 100)
 *   PUT    /incidents/<id>/questions/<qid>        incidents:update (If-Match)
 *   DELETE /incidents/<id>/questions/<qid>        incidents:update (archive)
 *   PUT    /incidents/<id>/questions/<qid>/leads  incidents:update ({task_ids})
 *   GET    /incidents/<id>/question-links         incidents:read
 *   GET    /questions                             cross-incident queue
 *   GET    /questions/library[/<ref>]             incidents:read
 *   GET/POST/PUT/DELETE /case-templates[/<ref>]   read: incidents:read, write: templates:manage
 *   POST   /case-templates/<ref>/clone            templates:manage
 *   POST   /incidents/<id>/case-templates/<ref>/apply   incidents:update (20/min; 409 template_inactive)
 *   GET    /incidents/<id>/case-templates         application ledger
 *   GET/PUT /incidents/<id>/custom-fields         read / incidents:update
 *   GET/POST /playbooks/builtin/<key>[/clone]     read / templates:manage
 *   POST   /incidents/<id>/playbooks/builtin/<key>/activate   incidents:update
 */
import { api } from '@/lib/api'
import type {
  ApplyTemplateOptions,
  BulkAddResult,
  CaseTemplate,
  CaseTemplateApplyResult,
  CaseTemplateWriteInput,
  CustomFieldsResponse,
  CustomFieldValue,
  IncidentCaseTemplateRow,
  IncidentPlaybook,
  InvestigativeQuestion,
  Playbook,
  PlaybookDefinition,
  QuestionInput,
  QuestionLibraryTree,
} from '@/types'

/** Paginated question list of one incident. */
export const incidentQuestionsEndpoint = (incidentId: string) => `/incidents/${incidentId}/questions`

/** Paginated cross-incident question queue. */
export const QUESTIONS_QUEUE_ENDPOINT = '/questions'

export const CASE_TEMPLATES_ENDPOINT = '/case-templates'

export const questionsApi = {
  create: (incidentId: string, data: QuestionInput) =>
    api.post<InvestigativeQuestion>(incidentQuestionsEndpoint(incidentId), data),

  bulkAdd: (incidentId: string, refs: string[]) =>
    api.post<BulkAddResult>(`${incidentQuestionsEndpoint(incidentId)}/bulk`, { refs }),

  /** A stale `version` answers 409 `conflict` (ConflictDialog). */
  update: (incidentId: string, id: string, data: QuestionInput, version?: number) =>
    api.put<InvestigativeQuestion>(`${incidentQuestionsEndpoint(incidentId)}/${id}`, data, { ifMatch: version }),

  archive: (incidentId: string, id: string, version?: number) =>
    api.delete<{ message: string }>(`${incidentQuestionsEndpoint(incidentId)}/${id}`, undefined, { ifMatch: version }),

  setLeads: (incidentId: string, id: string, taskIds: string[], version?: number) =>
    api.put<InvestigativeQuestion>(
      `${incidentQuestionsEndpoint(incidentId)}/${id}/leads`,
      { task_ids: taskIds },
      { ifMatch: version }
    ),

  library: (opts?: { signal?: AbortSignal }) => api.get<QuestionLibraryTree>('/questions/library', opts),
}

export const caseTemplatesApi = {
  list: (opts: { includeInactive?: boolean; includeDefinition?: boolean; signal?: AbortSignal } = {}) => {
    const q = new URLSearchParams()
    if (opts.includeInactive) q.set('include_inactive', 'true')
    if (opts.includeDefinition) q.set('include_definition', 'true')
    const qs = q.toString()
    return api.get<{ items: CaseTemplate[]; total: number }>(`${CASE_TEMPLATES_ENDPOINT}${qs ? `?${qs}` : ''}`, {
      signal: opts.signal,
    })
  },

  get: (ref: string, opts?: { signal?: AbortSignal }) =>
    api.get<CaseTemplate>(`${CASE_TEMPLATES_ENDPOINT}/${encodeURIComponent(ref)}`, opts),

  create: (data: CaseTemplateWriteInput) => api.post<CaseTemplate>(CASE_TEMPLATES_ENDPOINT, data),

  update: (id: string, data: CaseTemplateWriteInput, version?: number) =>
    api.put<CaseTemplate>(`${CASE_TEMPLATES_ENDPOINT}/${id}`, data, { ifMatch: version }),

  remove: (id: string, version?: number) =>
    api.delete<{ message: string; id: string }>(`${CASE_TEMPLATES_ENDPOINT}/${id}`, undefined, { ifMatch: version }),

  clone: (ref: string, name?: string) =>
    api.post<CaseTemplate>(`${CASE_TEMPLATES_ENDPOINT}/${encodeURIComponent(ref)}/clone`, name ? { name } : {}),

  /** `dry_run: true` computes the merge and rolls it back (preview). */
  apply: (incidentId: string, ref: string, options: ApplyTemplateOptions) =>
    api.post<CaseTemplateApplyResult>(
      `/incidents/${incidentId}/case-templates/${encodeURIComponent(ref)}/apply`,
      options
    ),

  ledger: (incidentId: string, opts?: { signal?: AbortSignal }) =>
    api.get<{ items: IncidentCaseTemplateRow[]; total: number }>(`/incidents/${incidentId}/case-templates`, opts),
}

export const customFieldsApi = {
  get: (incidentId: string, opts?: { signal?: AbortSignal }) =>
    api.get<CustomFieldsResponse>(`/incidents/${incidentId}/custom-fields`, opts),

  /** `null` clears a key. The incident `version` guards against lost updates. */
  put: (incidentId: string, values: Record<string, CustomFieldValue>, version?: number) =>
    api.put<CustomFieldsResponse>(`/incidents/${incidentId}/custom-fields`, { values }, { ifMatch: version }),
}

export const playbooksApi = {
  list: (opts?: { signal?: AbortSignal }) => api.get<{ items: Playbook[]; total: number }>('/playbooks', opts),

  create: (data: { name: string; description?: string | null; incident_type?: string | null; definition: PlaybookDefinition }) =>
    api.post<Playbook>('/playbooks', data),

  update: (
    id: string,
    data: { name?: string; description?: string | null; incident_type?: string | null; definition?: PlaybookDefinition }
  ) => api.put<Playbook>(`/playbooks/${id}`, data),

  remove: (id: string) => api.delete<{ message: string }>(`/playbooks/${id}`),

  cloneBuiltin: (key: string, name?: string) =>
    api.post<Playbook>(`/playbooks/builtin/${encodeURIComponent(key)}/clone`, name ? { name } : {}),

  /** `id` is a UUID, or `builtin:<key>` for a built-in (routed to the builtin endpoint). */
  activate: (incidentId: string, id: string) => {
    const path = id.startsWith('builtin:')
      ? `playbooks/builtin/${encodeURIComponent(id.slice('builtin:'.length))}`
      : `playbooks/${id}`
    return api.post<{ incident_playbook: IncidentPlaybook; actions_executed: unknown[] }>(
      `/incidents/${incidentId}/${path}/activate`
    )
  },
}
