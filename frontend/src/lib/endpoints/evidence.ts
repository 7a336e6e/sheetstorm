/**
 * Evidence register + custody ledger endpoints (W3-EVD-UI).
 *
 * Everything lives under `/incidents/<id>/evidence`, plus the org-wide
 * `/custody-parties` address book. Item mutations send `If-Match` when the
 * caller passes the row's `version` (409 `conflict` -> ConflictProvider).
 * Mutations return the item plus the ledger entries they appended.
 *
 * Callers invalidate `evidenceBase(incidentId)` after a write: the register
 * list, the chain badge and any open drawer all subscribe to that prefix.
 */
import api, { downloadTo, withQuery } from '@/lib/api'
import type {
  AcknowledgeInput,
  AddHashInput,
  CheckInInput,
  CheckOutInput,
  ChainVerification,
  CustodyList,
  CustodyParty,
  DisposeInput,
  EvidenceItemDetail,
  EvidenceMutation,
  ItemExportFormat,
  LegalHoldInput,
  NewPartyInput,
  PaginatedResponse,
  RegisterEvidenceInput,
  RegisterExportFormat,
  TransferInput,
  UpdateEvidenceInput,
  VerifyHashInput,
} from '@/types'

export const evidenceBase = (incidentId: string) => `/incidents/${incidentId}/evidence`
export const evidenceItemPath = (incidentId: string, itemId: string) => `${evidenceBase(incidentId)}/${itemId}`
export const custodyPartiesPath = '/custody-parties'

type Opts = { signal?: AbortSignal }
type Write = { ifMatch?: number }

const ifMatch = (version?: number | null): Write | undefined =>
  typeof version === 'number' ? { ifMatch: version } : undefined

/** Server filename comes from Content-Disposition; this is only the fallback. */
function downloadName(incidentId: string, itemId: string | null, format: string): string {
  const ext = format === 'form' ? 'pdf' : format === 'bundle' ? 'zip' : format
  return itemId ? `custody-${itemId}.${ext}` : `evidence-register-${incidentId}.${ext}`
}

export const evidenceApi = {
  get: (incidentId: string, itemId: string, opts?: Opts) =>
    api.get<EvidenceItemDetail>(evidenceItemPath(incidentId, itemId), opts),

  register: (incidentId: string, data: RegisterEvidenceInput) =>
    api.post<EvidenceMutation>(evidenceBase(incidentId), data),

  update: (incidentId: string, itemId: string, data: UpdateEvidenceInput, version?: number | null) =>
    api.patch<EvidenceMutation>(evidenceItemPath(incidentId, itemId), data, ifMatch(version)),

  addHash: (incidentId: string, itemId: string, data: AddHashInput) =>
    api.post<EvidenceMutation>(`${evidenceItemPath(incidentId, itemId)}/hashes`, data),

  verifyHash: (incidentId: string, itemId: string, data: VerifyHashInput) =>
    api.post<EvidenceMutation>(`${evidenceItemPath(incidentId, itemId)}/verify`, data),

  checkOut: (incidentId: string, itemId: string, data: CheckOutInput) =>
    api.post<EvidenceMutation>(`${evidenceItemPath(incidentId, itemId)}/custody/check-out`, data),

  checkIn: (incidentId: string, itemId: string, data: CheckInInput) =>
    api.post<EvidenceMutation>(`${evidenceItemPath(incidentId, itemId)}/custody/check-in`, data),

  transfer: (incidentId: string, itemId: string, data: TransferInput) =>
    api.post<EvidenceMutation>(`${evidenceItemPath(incidentId, itemId)}/custody/transfer`, data),

  acknowledge: (incidentId: string, itemId: string, entryId: string, data: AcknowledgeInput) =>
    api.post<EvidenceMutation>(`${evidenceItemPath(incidentId, itemId)}/custody/${entryId}/acknowledge`, data),

  dispose: (incidentId: string, itemId: string, data: DisposeInput) =>
    api.post<EvidenceMutation>(`${evidenceItemPath(incidentId, itemId)}/dispose`, data),

  void: (incidentId: string, itemId: string, reason: string) =>
    api.post<EvidenceMutation>(`${evidenceItemPath(incidentId, itemId)}/void`, { reason }),

  legalHold: (incidentId: string, itemId: string, data: LegalHoldInput) =>
    api.post<EvidenceMutation>(`${evidenceItemPath(incidentId, itemId)}/legal-hold`, data),

  custody: (incidentId: string, itemId: string, opts?: Opts) =>
    api.get<CustodyList>(`${evidenceItemPath(incidentId, itemId)}/custody`, opts),

  verifyItemChain: (incidentId: string, itemId: string, opts?: Opts) =>
    api.get<ChainVerification>(`${evidenceItemPath(incidentId, itemId)}/custody/verify`, opts),

  verifyIncidentChain: (incidentId: string, opts?: Opts) =>
    api.get<ChainVerification>(`${evidenceBase(incidentId)}/custody/verify`, opts),

  /** Single-item custody paperwork. `bundle` also needs `incidents:export`. */
  exportItem: (incidentId: string, itemId: string, format: ItemExportFormat, blankRows?: number) =>
    downloadTo(
      withQuery(`${evidenceItemPath(incidentId, itemId)}/custody/export`, {
        format,
        blank_rows: format === 'form' ? blankRows : undefined,
      }),
      { fallbackName: downloadName(incidentId, itemId, format) }
    ),

  /** The incident's register. Needs `incidents:export` for every format. */
  exportRegister: (incidentId: string, format: RegisterExportFormat) =>
    downloadTo(withQuery(`${evidenceBase(incidentId)}/export`, { format }), {
      fallbackName: downloadName(incidentId, null, format),
    }),
}

export const custodyPartiesApi = {
  list: (params: { q?: string; include_inactive?: boolean } = {}, opts?: Opts) =>
    api.get<PaginatedResponse<CustodyParty>>(
      withQuery(custodyPartiesPath, { ...params, per_page: 20, sort: 'name' }),
      opts
    ),
  create: (data: NewPartyInput) => api.post<CustodyParty>(custodyPartiesPath, data),
}

/** A stored copy of an item (legacy artifact routes, unchanged). */
export const evidenceFilesApi = {
  download: (incidentId: string, artifactId: string, fallbackName: string) =>
    downloadTo(`/incidents/${incidentId}/artifacts/${artifactId}/download`, { fallbackName }),
  remove: (incidentId: string, artifactId: string, reason?: string) =>
    api.delete(`/incidents/${incidentId}/artifacts/${artifactId}`, reason ? { reason } : undefined),
  artifactHold: (incidentId: string, artifactId: string, data: { hold: boolean; until?: string | null; reason?: string | null }) =>
    api.post(`/incidents/${incidentId}/artifacts/${artifactId}/legal-hold`, data),
  upload: (incidentId: string, form: FormData) => api.uploadFile(`/incidents/${incidentId}/artifacts`, form),
}
