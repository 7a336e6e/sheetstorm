/**
 * Decision & response-action log (W4-DEC).
 * Backend: `models/decision_log.py`, `services/decision_log_service.py`,
 * `endpoints/decision_log.py`. Links use the shared evidence-ref shape.
 */
import type { EvidenceRef, TaskEvidence } from './dfir'

export type DecisionCategory =
  | 'containment'
  | 'eradication'
  | 'recovery'
  | 'notification'
  | 'ransom_legal'
  | 'scope'
  | 'communication'
  | 'evidence'
  | 'other'

export type DecisionStatus = 'proposed' | 'approved' | 'rejected' | 'superseded'

export type ResponseActionType =
  | 'isolate_host'
  | 'release_host'
  | 'contain_host'
  | 'reimage_host'
  | 'decommission_host'
  | 'disable_account'
  | 'reset_credentials'
  | 'revoke_sessions'
  | 'delete_account'
  | 'block_ioc'
  | 'sinkhole_domain'
  | 'quarantine_file'
  | 'remove_persistence'
  | 'patch'
  | 'notify_party'
  | 'other'

export type ResponseTargetType = 'host' | 'account' | 'network_ioc' | 'host_ioc' | 'malware' | 'external' | 'none'

export type ResponseActionStatus =
  | 'requested'
  | 'authorized'
  | 'in_progress'
  | 'executed'
  | 'verified'
  | 'failed'
  | 'rolled_back'
  | 'cancelled'

export type ActionVerificationResult = 'success' | 'partial' | 'failed'

export type DecisionEvent = 'approve' | 'reject' | 'reopen' | 'supersede'
export type ResponseActionEvent = 'authorize' | 'start' | 'execute' | 'fail' | 'verify' | 'rollback' | 'cancel'

export interface DecisionUserRef {
  id: string
  name: string
}

export interface DecisionAlternative {
  option: string
  reason_not_chosen: string | null
}

export interface Decision {
  id: string
  incident_id: string
  number: number
  display_id: string
  record_type: 'decision'
  title: string
  decision: string
  rationale: string | null
  alternatives: DecisionAlternative[]
  category: DecisionCategory
  status: DecisionStatus
  status_reason: string | null
  is_privileged: boolean
  decided_at: string
  decided_by_user_id: string | null
  decided_by_name: string | null
  approved_by_user_id: string | null
  approved_by_name: string | null
  approved_at: string | null
  self_approved: boolean
  superseded_by_id: string | null
  superseded_by?: { id: string; display_id: string; title: string } | null
  links: TaskEvidence[]
  created_at: string
  created_by: string | null
  updated_at: string | null
  version: number
  revision_count?: number
  users?: Record<string, DecisionUserRef | null>
}

export interface ResponseAction {
  id: string
  incident_id: string
  number: number
  display_id: string
  record_type: 'response_action'
  action_type: ResponseActionType
  title: string
  description: string | null
  target_type: ResponseTargetType
  target_id: string | null
  target_label: string | null
  decision_id: string | null
  decision?: { id: string; display_id: string; title: string; status: DecisionStatus } | null
  decision_restricted?: boolean
  status: ResponseActionStatus
  status_reason: string | null
  requested_by_user_id: string | null
  requested_at: string
  authorized_by_user_id: string | null
  authorized_by_name: string | null
  authorized_at: string | null
  self_approved: boolean
  executed_by_user_id: string | null
  executed_by_name: string | null
  executed_at: string | null
  verified_by_user_id: string | null
  verified_by_name: string | null
  verified_at: string | null
  verification_method: string | null
  verification_result: ActionVerificationResult | null
  verification_notes: string | null
  self_verified: boolean
  rollback_plan: string | null
  rolled_back_at: string | null
  rollback_reason: string | null
  target_state_before: { field: string; value: string | null } | null
  target_state_after: { field: string; value: string | null } | null
  links: TaskEvidence[]
  created_at: string
  updated_at: string | null
  version: number
  revision_count?: number
  users?: Record<string, DecisionUserRef | null>
}

export type RevisionSignatureStatus = 'valid' | 'invalid' | 'key_mismatch'
export type DecisionChainStatus = 'intact' | 'broken' | 'compromised' | 'unverifiable'

export interface DecisionLogRevision {
  id: string
  record_type: 'decision' | 'response_action'
  record_id: string
  seq: number
  event: string
  snapshot: Record<string, unknown>
  /** `{field: {from, to}}` (lists: `{added, removed}`). */
  changes: Record<string, { from?: unknown; to?: unknown; added?: unknown[]; removed?: unknown[] }>
  reason: string | null
  actor_id: string | null
  actor_email: string | null
  self_approved: boolean
  entry_hash: string
  prev_hash: string
  created_at: string
  signature_status: RevisionSignatureStatus
}

export interface DecisionRevisionsResponse {
  items: DecisionLogRevision[]
  verification: {
    status: DecisionChainStatus
    length: number
    breaks: { seq: number | null; id: string | null; reason: string }[]
    signatures: Record<RevisionSignatureStatus, number>
  }
}

export interface DecisionInput {
  title?: string
  decision?: string
  rationale?: string | null
  category?: DecisionCategory
  decided_at?: string | null
  decided_by_name?: string | null
  is_privileged?: boolean
  links?: EvidenceRef[]
  alternatives?: DecisionAlternative[]
  reason?: string
}

export interface ResponseActionInput {
  action_type?: ResponseActionType
  title?: string
  description?: string | null
  target_type?: ResponseTargetType
  target_id?: string | null
  target_label?: string | null
  decision_id?: string | null
  rollback_plan?: string | null
  links?: EvidenceRef[]
  reason?: string
}

/** Body of a transition: event-specific fields plus `reason` (all optional client-side). */
export type DecisionTransitionInput = Record<string, unknown>

/** A virtual row of `GET /incidents/<id>/response-timeline`. */
export interface VirtualTimelineRow {
  kind: 'response' | 'decision'
  id: string
  display_id: string
  timestamp: string | null
  activity: string
  title: string
  status: string
  target_type?: ResponseTargetType
  host_id?: string | null
  category?: DecisionCategory
  is_privileged?: boolean
}
