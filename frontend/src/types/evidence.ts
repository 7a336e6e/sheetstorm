/**
 * Evidence register and custody ledger (W3-EVD-UI), mirroring the backend
 * `models/evidence.py`, `models/artifact.py::ChainOfCustody` and
 * `api/v1/endpoints/evidence.py`.
 *
 * Items carry the optimistic-concurrency `version` (ETag / `If-Match`).
 * Custody entries are append-only and never carry one.
 */
import type { Versioned } from './incident-tables'

export const EVIDENCE_TYPES = [
  'disk_image',
  'memory_capture',
  'triage_package',
  'logical_collection',
  'mobile_device',
  'storage_media',
  'computer_system',
  'network_capture',
  'cloud_export',
  'log_export',
  'document',
  'digital_file',
  'other',
] as const
export type EvidenceType = (typeof EVIDENCE_TYPES)[number]

export const CUSTODY_STATES = ['in_storage', 'checked_out', 'transferred', 'disposed'] as const
export type CustodyState = (typeof CUSTODY_STATES)[number]

/** Hex length per algorithm (backend `HASH_ALGORITHMS`). */
export const HASH_LENGTHS = { md5: 32, sha1: 40, sha256: 64, sha512: 128 } as const
export type HashAlgorithm = keyof typeof HASH_LENGTHS
export const HASH_ALGORITHMS = Object.keys(HASH_LENGTHS) as HashAlgorithm[]

export const HASH_SOURCES = ['tool_reported', 'computed_on_upload', 'computed_in_lab'] as const
export type HashSource = (typeof HASH_SOURCES)[number]

export const TRANSFER_METHODS = [
  'hand_delivery',
  'courier',
  'registered_mail',
  'secure_file_transfer',
  'internal',
  'other',
] as const
export type TransferMethod = (typeof TRANSFER_METHODS)[number]

export const PARTY_ROLES = [
  'counsel',
  'law_enforcement',
  'third_party_lab',
  'insurer',
  'client',
  'regulator',
  'courier',
  'other',
] as const
export type PartyRole = (typeof PARTY_ROLES)[number]

export const DISPOSE_METHODS = ['returned_to_owner', 'destroyed', 'released', 'other'] as const
export type DisposeMethod = (typeof DISPOSE_METHODS)[number]

/** One recorded acquisition hash (`acquisition_hashes[]`). */
export interface AcquisitionHash {
  algorithm: HashAlgorithm
  value: string
  source: HashSource
  recorded_at?: string
  recorded_by?: string
  /** The value this record replaces (a correction, never an edit). */
  supersedes?: string
  /** Set on the replaced record. */
  superseded?: boolean
}

export interface EvidenceHolder {
  type: 'user' | 'party' | 'storage'
  id: string | null
  name: string | null
}

export interface EvidenceItemSummary {
  id: string
  evidence_number: string
  title: string
  evidence_type: EvidenceType
  voided: boolean
}

export type VerificationResult = 'match' | 'mismatch'

export interface EvidenceItem extends Versioned {
  id: string
  organization_id: string
  incident_id: string
  sequence_number: number
  /** `EV-0007` */
  evidence_number: string
  /** `CASE-12/EV-0007` */
  display_id: string
  evidence_type: EvidenceType
  title: string
  description: string | null
  condition_notes: string | null
  media_type: string | null
  make: string | null
  model: string | null
  serial_number: string | null
  capacity_bytes: number | null
  seal_number: string | null
  bag_number: string | null
  storage_location: string | null
  acquired_at: string | null
  acquired_by_user_id: string | null
  acquired_by_name: string | null
  acquired_from: string | null
  acquisition_method: string | null
  acquisition_tool: string | null
  acquisition_tool_version: string | null
  source_host_id: string | null
  source_host_label: string | null
  acquisition_hashes: AcquisitionHash[]
  parent_id: string | null
  parent: EvidenceItemSummary | null
  derivation_note: string | null
  custody_state: CustodyState
  holder: EvidenceHolder
  current_holder_user_id: string | null
  current_holder_party_id: string | null
  expected_return_at: string | null
  last_verified_at: string | null
  last_verification_result: VerificationResult | null
  legal_hold_until: string | null
  is_locked: boolean
  /** Own hold or an ancestor's. */
  under_legal_hold: boolean
  weak_hashes_only: boolean
  voided_at: string | null
  voided_by: string | null
  void_reason: string | null
  created_by: string
  creator: { id: string; name: string } | null
  created_at: string
  updated_at: string | null
}

/** Stored copy of an item (a row of `/artifacts`, as embedded in the item detail). */
export interface EvidenceArtifact {
  id: string
  evidence_item_id: string
  original_filename: string
  file_size: number
  mime_type?: string | null
  storage_type: 'local' | 's3' | 'google_drive'
  md5: string
  sha256: string
  sha512: string
  purpose: 'evidence' | 'custody_receipt' | string
  is_verified: boolean
  verification_status: 'verified' | 'mismatch' | 'pending'
  under_legal_hold?: boolean
  is_locked?: boolean
  legal_hold_until?: string | null
  deleted_at: string | null
  deletion_reason: string | null
  content_purged: boolean
  uploader?: { id: string; name: string } | null
  created_at: string
}

export type ChainStatus =
  | 'intact'
  | 'intact_with_unsigned_legacy'
  | 'unverifiable'
  | 'broken'
  | 'compromised'

export interface ChainSummary {
  status: ChainStatus
  head_seq: number | null
  head_hash: string | null
}

export interface EvidenceItemDetail extends EvidenceItem {
  artifacts: EvidenceArtifact[]
  children: EvidenceItemSummary[]
  chain_summary: ChainSummary
}

export type SignatureStatus = 'valid' | 'unsigned_legacy' | 'invalid' | 'key_mismatch' | 'not_checked'

export type CustodyAction =
  | 'register'
  | 'upload'
  | 'view'
  | 'download'
  | 'transfer'
  | 'check_out'
  | 'check_in'
  | 'acknowledge'
  | 'verify'
  | 'update'
  | 'add_hash'
  | 'derive'
  | 'export'
  | 'delete'
  | 'void'
  | 'dispose'
  | 'legal_hold'

export interface CustodyPartySnapshot {
  id?: string
  name?: string
  organization_name?: string | null
  role?: PartyRole | string
  email?: string | null
  phone?: string | null
}

export interface CustodyEntry {
  id: string
  evidence_item_id: string
  incident_id: string
  artifact_id: string | null
  /** Per-item sequence; null on legacy (unchained) rows. */
  seq: number | null
  incident_seq: number | null
  entry_hash: string | null
  chain_version: number | null
  action: CustodyAction | string
  performed_by: string
  performer: { id: string; name: string } | null
  recipient: { id: string; name: string } | null
  external_party: CustodyPartySnapshot | null
  transfer_method: TransferMethod | null
  purpose: string | null
  verification_result: VerificationResult | null
  created_at: string
  extra_data: Record<string, unknown> | null
  signature_status: SignatureStatus | null
  /** `ok`, `legacy`, or the verifier's reasons joined by `,` (e.g. `prev_hash_mismatch`). */
  link_status: string
  /** The `acknowledge` entry that answered this transfer / check-out. */
  acknowledged_by_entry_id: string | null
}

export interface ChainBreak {
  seq: number | null
  id: string | null
  reason: string
  chain?: 'item' | 'incident'
  evidence_item_id?: string
}

export interface ChainHead {
  length: number
  head_seq: number | null
  head_hash: string | null
  genesis?: string
}

export interface CustodyAnchorInfo {
  id: string
  anchor_type: 'rfc3161' | 'export_manifest'
  status: 'granted' | 'failed'
  incident_seq: number
  head_hash: string
  created_at: string
  covers_current_head: boolean
}

/** `GET …/custody/verify` (item or incident scope). */
export interface ChainVerification {
  scope: 'item' | 'incident'
  incident_id: string
  evidence_item_id?: string
  status: ChainStatus
  breaks: ChainBreak[]
  warnings: ChainBreak[]
  projection_drift: Array<Record<string, unknown>>
  notes: string[]
  signatures: Record<string, number>
  legacy: { count: number; sealed: boolean }
  item_chain?: ChainHead
  incident_chain?: ChainHead
  /** Incident scope: per-item chain heads and breaks, keyed by item id. */
  items?: Record<string, ChainHead & { evidence_number: string; breaks: ChainBreak[] }>
  anchors: CustodyAnchorInfo[]
}

/** `GET …/{item}/custody` */
export interface CustodyList {
  evidence_item_id: string
  evidence_number: string
  status: ChainStatus
  item_chain: ChainHead
  entries: CustodyEntry[]
}

export interface CustodyParty extends Versioned {
  id: string
  organization_id: string
  name: string
  organization_name: string | null
  role: PartyRole
  email: string | null
  phone: string | null
  address: string | null
  notes: string | null
  is_active: boolean
  created_at: string
}

// ── Request bodies ───────────────────────────────────────────────────────

export interface NewHashInput {
  algorithm: HashAlgorithm
  value: string
  source: HashSource
}

export interface EvidenceFields {
  title: string
  evidence_type: EvidenceType
  description?: string | null
  condition_notes?: string | null
  media_type?: string | null
  make?: string | null
  model?: string | null
  serial_number?: string | null
  capacity_bytes?: number | null
  seal_number?: string | null
  bag_number?: string | null
  storage_location?: string | null
  acquired_at?: string | null
  acquired_by_user_id?: string | null
  acquired_by_name?: string | null
  acquired_from?: string | null
  acquisition_method?: string | null
  acquisition_tool?: string | null
  acquisition_tool_version?: string | null
  source_host_id?: string | null
  derivation_note?: string | null
}

export interface RegisterEvidenceInput extends EvidenceFields {
  parent_id?: string | null
  acquisition_hashes?: NewHashInput[]
}

/** PATCH body: descriptive fields only (hashes, parent, holder, location are not patchable). */
export type UpdateEvidenceInput = Partial<Omit<EvidenceFields, 'storage_location'>>

export interface NewPartyInput {
  name: string
  role?: PartyRole
  organization_name?: string | null
  email?: string | null
  phone?: string | null
  address?: string | null
  notes?: string | null
}

/** Exactly one of the three is sent. */
export interface RecipientInput {
  to_user_id?: string
  to_party_id?: string
  new_party?: NewPartyInput
}

export interface CheckOutInput extends RecipientInput {
  purpose: string
  transfer_method?: TransferMethod
  expected_return_at?: string | null
}

export interface TransferInput extends RecipientInput {
  transfer_method: TransferMethod
  reason: string
  tracking_number?: string | null
  seal_number?: string | null
}

export interface CheckInInput {
  storage_location: string
  seal_intact: boolean
  condition_notes?: string | null
  seal_number?: string | null
  received_from_party_id?: string | null
}

export interface AcknowledgeInput {
  typed_name: string
  statement?: string | null
  stated_at?: string | null
  receipt_artifact_id?: string | null
}

export interface DisposeInput {
  method: DisposeMethod
  reason: string
  witness_name?: string | null
}

export interface LegalHoldInput {
  hold: boolean
  /** Future ISO-8601; omitted = indefinite. */
  until?: string | null
  reason?: string | null
}

/** Lab verification, or a recompute from a stored copy. */
export type VerifyHashInput =
  | { algorithm: HashAlgorithm; observed_hash: string; method?: string | null; tool?: string | null; notes?: string | null }
  | { recompute: true; artifact_id: string; algorithm?: 'md5' | 'sha256' | 'sha512'; notes?: string | null }

export interface AddHashInput extends NewHashInput {
  /** The recorded value this one replaces; needs `reason`. */
  supersedes?: string
  reason?: string
}

/** A mutating response: the item plus the ledger entries the call appended. */
export interface EvidenceMutation extends EvidenceItem {
  ledger_entries: CustodyEntry[]
  verification?: {
    algorithm: HashAlgorithm
    expected_hash: string
    observed_hash: string
    match: boolean
  }
}

export type ItemExportFormat = 'json' | 'csv' | 'pdf' | 'form' | 'bundle'
export type RegisterExportFormat = 'csv' | 'pdf' | 'bundle'
