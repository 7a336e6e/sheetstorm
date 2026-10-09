/**
 * Test-only fixtures for the evidence components. Never import from
 * application code.
 */
import type { ChainVerification, CustodyEntry, CustodyList, EvidenceItem, EvidenceItemDetail } from '@/types'

export const SHA256 = 'a'.repeat(64)

export const READ = ['incidents:read', 'artifacts:read']
export const RESPONDER = [...READ, 'artifacts:upload', 'artifacts:download', 'incidents:export']
export const ADMIN = [...RESPONDER, 'artifacts:delete']

export function makeItem(over: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    id: 'ev1',
    organization_id: 'o1',
    incident_id: 'i1',
    sequence_number: 1,
    evidence_number: 'EV-0001',
    display_id: 'CASE-1/EV-0001',
    evidence_type: 'disk_image',
    title: 'CFO laptop image',
    description: null,
    condition_notes: null,
    media_type: null,
    make: null,
    model: null,
    serial_number: 'SN-42',
    capacity_bytes: null,
    seal_number: null,
    bag_number: null,
    storage_location: 'Locker 3',
    acquired_at: null,
    acquired_by_user_id: null,
    acquired_by_name: null,
    acquired_from: null,
    acquisition_method: null,
    acquisition_tool: null,
    acquisition_tool_version: null,
    source_host_id: null,
    source_host_label: null,
    acquisition_hashes: [{ algorithm: 'sha256', value: SHA256, source: 'tool_reported' }],
    parent_id: null,
    parent: null,
    derivation_note: null,
    custody_state: 'in_storage',
    holder: { type: 'storage', id: null, name: 'Locker 3' },
    current_holder_user_id: null,
    current_holder_party_id: null,
    expected_return_at: null,
    last_verified_at: null,
    last_verification_result: null,
    legal_hold_until: null,
    is_locked: false,
    under_legal_hold: false,
    weak_hashes_only: false,
    voided_at: null,
    voided_by: null,
    void_reason: null,
    created_by: 'u1',
    creator: { id: 'u1', name: 'Ada' },
    created_at: '2026-01-01T00:00:00Z',
    updated_at: null,
    version: 3,
    ...over,
  }
}

export function makeEntry(over: Partial<CustodyEntry> = {}): CustodyEntry {
  return {
    id: 'c1',
    evidence_item_id: 'ev1',
    incident_id: 'i1',
    artifact_id: null,
    seq: 1,
    incident_seq: 1,
    entry_hash: 'f'.repeat(64),
    chain_version: 3,
    action: 'register',
    performed_by: 'u1',
    performer: { id: 'u1', name: 'Ada' },
    recipient: null,
    external_party: null,
    transfer_method: null,
    purpose: null,
    verification_result: null,
    created_at: '2026-01-01T00:00:00Z',
    extra_data: {},
    signature_status: 'valid',
    link_status: 'ok',
    acknowledged_by_entry_id: null,
    ...over,
  }
}

export function makeDetail(over: Partial<EvidenceItemDetail> = {}): EvidenceItemDetail {
  return {
    ...makeItem(),
    artifacts: [],
    children: [],
    chain_summary: { status: 'intact', head_seq: 1, head_hash: 'f'.repeat(64) },
    ...over,
  }
}

export function makeCustody(entries: CustodyEntry[] = [makeEntry()], status: CustodyList['status'] = 'intact'): CustodyList {
  return {
    evidence_item_id: 'ev1',
    evidence_number: 'EV-0001',
    status,
    item_chain: { length: entries.length, head_seq: entries.length, head_hash: 'f'.repeat(64) },
    entries,
  }
}

export function makeVerification(over: Partial<ChainVerification> = {}): ChainVerification {
  return {
    scope: 'incident',
    incident_id: 'i1',
    status: 'intact',
    breaks: [],
    warnings: [],
    projection_drift: [],
    notes: [],
    signatures: { valid: 1 },
    legacy: { count: 0, sealed: false },
    incident_chain: { length: 1, head_seq: 1, head_hash: 'f'.repeat(64) },
    items: {},
    anchors: [],
    ...over,
  }
}
