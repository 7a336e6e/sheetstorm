/**
 * Pure helpers for the Evidence tab: labels, hash validation, and the
 * custody state machine as the UI sees it (the server stays authoritative and
 * answers 409 `invalid_custody_transition` / `legal_hold`).
 */
import {
  HASH_LENGTHS,
  type AcquisitionHash,
  type ChainStatus,
  type CustodyEntry,
  type CustodyPartySnapshot,
  type CustodyState,
  type DisposeMethod,
  type EvidenceItem,
  type EvidenceType,
  type HashAlgorithm,
  type HashSource,
  type PartyRole,
  type TransferMethod,
} from '@/types'

export const EVIDENCE_TYPE_LABELS: Record<EvidenceType, string> = {
  disk_image: 'Disk image',
  memory_capture: 'Memory capture',
  triage_package: 'Triage package',
  logical_collection: 'Logical collection',
  mobile_device: 'Mobile device',
  storage_media: 'Storage media',
  computer_system: 'Computer system',
  network_capture: 'Network capture',
  cloud_export: 'Cloud export',
  log_export: 'Log export',
  document: 'Document',
  digital_file: 'Digital file',
  other: 'Other',
}

export const CUSTODY_STATE_LABELS: Record<CustodyState, string> = {
  in_storage: 'In storage',
  checked_out: 'Checked out',
  transferred: 'Transferred',
  disposed: 'Disposed',
}

export const TRANSFER_METHOD_LABELS: Record<TransferMethod, string> = {
  hand_delivery: 'Hand delivery',
  courier: 'Courier',
  registered_mail: 'Registered mail',
  secure_file_transfer: 'Secure file transfer',
  internal: 'Internal',
  other: 'Other',
}

export const PARTY_ROLE_LABELS: Record<PartyRole, string> = {
  counsel: 'Counsel',
  law_enforcement: 'Law enforcement',
  third_party_lab: 'Third-party lab',
  insurer: 'Insurer',
  client: 'Client',
  regulator: 'Regulator',
  courier: 'Courier',
  other: 'Other',
}

export const DISPOSE_METHOD_LABELS: Record<DisposeMethod, string> = {
  returned_to_owner: 'Returned to owner',
  destroyed: 'Destroyed',
  released: 'Released',
  other: 'Other',
}

export const HASH_SOURCE_LABELS: Record<HashSource, string> = {
  tool_reported: 'Tool reported',
  computed_on_upload: 'Computed on upload',
  computed_in_lab: 'Computed in lab',
}

export const HASH_LABELS: Record<HashAlgorithm, string> = {
  md5: 'MD5',
  sha1: 'SHA-1',
  sha256: 'SHA-256',
  sha512: 'SHA-512',
}

export const ACTION_LABELS: Record<string, string> = {
  register: 'Registered',
  upload: 'File uploaded',
  view: 'Viewed',
  download: 'File downloaded',
  transfer: 'Transferred',
  check_out: 'Checked out',
  check_in: 'Checked in',
  acknowledge: 'Acknowledged',
  verify: 'Hash verified',
  update: 'Details edited',
  add_hash: 'Hash recorded',
  derive: 'Derived item created',
  export: 'Exported',
  delete: 'File deleted',
  void: 'Voided',
  dispose: 'Disposed',
  legal_hold: 'Legal hold',
}

export const CHAIN_STATUS_LABELS: Record<ChainStatus, string> = {
  intact: 'Chain verified',
  intact_with_unsigned_legacy: 'Verified, legacy entries unsigned',
  unverifiable: 'Cannot verify (signing key changed)',
  broken: 'Chain broken',
  compromised: 'Tampering detected',
}

const label = <K extends string>(map: Record<K, string>, key: string | null | undefined, fallback = '—'): string =>
  key ? map[key as K] ?? key.replace(/_/g, ' ') : fallback

export const evidenceTypeLabel = (t?: string | null) => label(EVIDENCE_TYPE_LABELS, t)
export const custodyStateLabel = (s?: string | null) => label(CUSTODY_STATE_LABELS, s)
export const transferMethodLabel = (m?: string | null) => label(TRANSFER_METHOD_LABELS, m)
export const partyRoleLabel = (r?: string | null) => label(PARTY_ROLE_LABELS, r)
export const actionLabel = (a?: string | null) => label(ACTION_LABELS, a)

// ── Hashes ───────────────────────────────────────────────────────────────

const HEX = /^[0-9a-f]+$/

/** Lower-cased, surrounding whitespace removed (what the server stores). */
export function normalizeHash(value: string): string {
  return value.trim().toLowerCase()
}

/**
 * Client-side mirror of the server rule: `value` must be exactly the
 * algorithm's length in hexadecimal characters. Returns the problem, or null
 * when valid. An empty value is "not entered", not an error (use `required`).
 */
export function validateHash(algorithm: HashAlgorithm, value: string, opts: { required?: boolean } = {}): string | null {
  const v = normalizeHash(value)
  if (!v) return opts.required ? `Enter a ${HASH_LABELS[algorithm]} value` : null
  const want = HASH_LENGTHS[algorithm]
  if (!HEX.test(v)) return `${HASH_LABELS[algorithm]} must be hexadecimal (0-9, a-f)`
  if (v.length !== want) return `${HASH_LABELS[algorithm]} must be ${want} characters (got ${v.length})`
  return null
}

/** The algorithm a hex string's length points at, if exactly one does. */
export function guessAlgorithm(value: string): HashAlgorithm | null {
  const v = normalizeHash(value)
  if (!HEX.test(v)) return null
  const hit = (Object.keys(HASH_LENGTHS) as HashAlgorithm[]).find((a) => HASH_LENGTHS[a] === v.length)
  return hit ?? null
}

/** Hashes that are still in force (not replaced by a correction). */
export function activeHashes(item: Pick<EvidenceItem, 'acquisition_hashes'>): AcquisitionHash[] {
  return (item.acquisition_hashes ?? []).filter((h) => !h.superseded)
}

const PRIMARY_ORDER: HashAlgorithm[] = ['sha256', 'sha512', 'sha1', 'md5']

/** The strongest recorded hash, for the register's single hash column. */
export function primaryHash(item: Pick<EvidenceItem, 'acquisition_hashes'>): AcquisitionHash | null {
  const active = activeHashes(item)
  for (const alg of PRIMARY_ORDER) {
    const hit = active.find((h) => h.algorithm === alg)
    if (hit) return hit
  }
  return null
}

/** `d41d8cd9…8427e` for narrow cells. */
export function shortHash(value: string, head = 10, tail = 6): string {
  return value.length <= head + tail + 1 ? value : `${value.slice(0, head)}…${value.slice(-tail)}`
}

// ── Custody state machine (UI side) ──────────────────────────────────────

export type CustodyMode = 'check_out' | 'check_in' | 'transfer'

export interface ItemActions {
  checkOut: boolean
  checkIn: boolean
  transfer: boolean
  dispose: boolean
  void: boolean
  edit: boolean
  addHash: boolean
  verify: boolean
}

export const isVoided = (item: Pick<EvidenceItem, 'voided_at'>) => !!item.voided_at

/**
 * What the state machine allows right now (permissions are applied by the
 * caller). `in_storage -> checked_out|transferred`, `checked_out ->
 * in_storage|transferred`, `transferred -> in_storage`; dispose is terminal and
 * refused under a hold; void is refused under a hold (and with live children,
 * which only the server knows).
 */
export function itemActions(
  item: Pick<EvidenceItem, 'custody_state' | 'voided_at' | 'under_legal_hold'>
): ItemActions {
  const live = !item.voided_at
  const disposed = item.custody_state === 'disposed'
  const active = live && !disposed
  return {
    checkOut: active && item.custody_state === 'in_storage',
    checkIn: active && (item.custody_state === 'checked_out' || item.custody_state === 'transferred'),
    transfer: active && (item.custody_state === 'in_storage' || item.custody_state === 'checked_out'),
    dispose: active && !item.under_legal_hold,
    void: live && !item.under_legal_hold,
    edit: live,
    addHash: live,
    verify: live,
  }
}

/** Transfers / check-outs (chained rows) that nobody has acknowledged yet. */
export function pendingAcknowledgments(entries: CustodyEntry[]): CustodyEntry[] {
  return entries.filter(
    (e) => (e.action === 'transfer' || e.action === 'check_out') && e.chain_version != null && !e.acknowledged_by_entry_id
  )
}

export function partyLabel(p: CustodyPartySnapshot | null | undefined): string {
  if (!p) return ''
  const name = p.name || 'Unnamed party'
  return p.organization_name ? `${name} (${p.organization_name})` : name
}

/** True when the entry's signature or link check failed. */
export function entryHasProblem(e: Pick<CustodyEntry, 'signature_status' | 'link_status'>): boolean {
  return e.signature_status === 'invalid' || (e.link_status !== 'ok' && e.link_status !== 'legacy')
}
