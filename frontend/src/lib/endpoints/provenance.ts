/**
 * Record provenance + clock-skew endpoints (W3-PROV). Create/update of events
 * and IOCs carry the provenance keys in their normal bodies.
 */
import { api } from '@/lib/api'
import type {
  ClockSkewReapplyResult,
  ClockSkewUpdate,
  CompromisedHost,
  NormalizePreview,
  NormalizePreviewRequest,
  ProvenanceRecordKind,
} from '@/types'

const base = (incidentId: string) => `/incidents/${incidentId}`

export const provenanceApi = {
  /** Second-analyst verification (400 `same_analyst` for the creator). */
  verify: (incidentId: string, kind: ProvenanceRecordKind, recordId: string, version?: number) =>
    api.post<unknown>(`${base(incidentId)}/provenance/verify`, {
      record_type: kind,
      record_id: recordId,
      ...(version === undefined ? {} : { expected_version: version }),
    }),

  /** Withdraw a verification (the verifier, or an organization manager). */
  unverify: (incidentId: string, kind: ProvenanceRecordKind, recordId: string, version?: number) =>
    api.delete<unknown>(`${base(incidentId)}/provenance/verify`, {
      record_type: kind,
      record_id: recordId,
      ...(version === undefined ? {} : { expected_version: version }),
    }),

  /** UTC value for a raw timestamp (nothing is stored). */
  normalizePreview: (incidentId: string, body: NormalizePreviewRequest, opts?: { signal?: AbortSignal }) =>
    api.post<NormalizePreview>(`${base(incidentId)}/provenance/normalize-preview`, body, opts),

  setClockSkew: (incidentId: string, hostId: string, body: ClockSkewUpdate, version?: number) =>
    api.put<CompromisedHost>(`${base(incidentId)}/hosts/${hostId}/clock-skew`, body, { ifMatch: version }),

  /** Dry run (default) lists the records that would move; `dryRun: false` applies. */
  reapplyClockSkew: (incidentId: string, hostId: string, dryRun = true, version?: number) =>
    api.post<ClockSkewReapplyResult>(
      `${base(incidentId)}/hosts/${hostId}/clock-skew/reapply`,
      { dry_run: dryRun, ...(!dryRun && version !== undefined ? { expected_version: version } : {}) },
    ),
}
