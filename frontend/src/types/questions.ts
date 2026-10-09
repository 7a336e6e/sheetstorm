/**
 * Investigative questions, case templates and custom fields (W4-QST-UI).
 * Mirrors backend `models/question.py`, `schemas/case_template.py` and
 * `endpoints/{questions,case_templates,playbooks}.py`.
 */
import type { EvidenceRef, TaskEvidence } from './dfir'
import type { PlaybookDefinition, TLPLevel } from './index'
import type { Versioned } from './incident-tables'

export type QuestionStatus = 'open' | 'in_progress' | 'answered' | 'unanswerable'
export type QuestionConfidence = 'low' | 'medium' | 'high' | 'confirmed'
export type QuestionPriority = 'low' | 'medium' | 'high' | 'critical'
export type QuestionSource = 'manual' | 'dfiq' | 'core' | 'template'

export interface QuestionGuidance {
  name: string
  description?: string
  references?: string[]
}

export interface InvestigativeQuestion extends Versioned {
  id: string
  incident_id: string
  question: string
  description?: string | null
  facet?: string | null
  status: QuestionStatus
  /** Markdown source; always rendered as plain text. */
  answer?: string | null
  confidence?: QuestionConfidence | null
  priority: QuestionPriority
  phase?: number | null
  owner_id?: string | null
  owner?: { id: string; name: string; avatar_url?: string | null } | null
  evidence_refs: EvidenceRef[]
  /** Server-resolved labels (absent on live socket payloads). */
  evidence?: TaskEvidence[]
  source: QuestionSource
  source_ref?: string | null
  guidance?: QuestionGuidance[]
  order_index: number
  answered_at?: string | null
  answered_by_user?: { id: string; name: string } | null
  is_archived: boolean
  lead_ids: string[]
  created_at: string
  updated_at?: string | null
}

export interface QuestionSummary {
  total: number
  open: number
  in_progress: number
  answered: number
  unanswerable: number
  resolved: number
  /** resolved / total, 0-1. */
  progress: number
  open_high_priority: number
  top_open: { id: string; question: string; priority: QuestionPriority; status: QuestionStatus; phase?: number | null }[]
}

/** Body of POST (manual or `library_ref`) and PUT on a question. */
export interface QuestionInput {
  question?: string
  description?: string | null
  facet?: string | null
  status?: QuestionStatus
  answer?: string | null
  confidence?: QuestionConfidence | null
  priority?: QuestionPriority
  phase?: number | null
  owner_id?: string | null
  evidence_refs?: EvidenceRef[]
  library_ref?: string
}

export interface QuestionLibraryQuestion {
  ref: string
  source: 'core' | 'dfiq'
  question: string
  facet?: string | null
  phase?: number | null
  priority: QuestionPriority
}

export interface QuestionLibraryFacet {
  ref: string
  name: string
  questions: QuestionLibraryQuestion[]
}

export interface QuestionLibraryGroup {
  ref: string
  kind: 'core' | 'scenario'
  name: string
  source: 'core' | 'dfiq'
  facets: QuestionLibraryFacet[]
}

export interface QuestionLibrarySource {
  key: string
  name: string
  license: string
  attribution?: string | null
  url?: string | null
}

export interface QuestionLibraryTree {
  groups: QuestionLibraryGroup[]
  sources: QuestionLibrarySource[]
  total: number
}

export interface BulkAddResult {
  created: InvestigativeQuestion[]
  skipped: { ref: string; reason: string; existing_id?: string | null }[]
}

// ── Case templates ───────────────────────────────────────────────────────

export type CustomFieldType = 'text' | 'number' | 'boolean' | 'date' | 'select'

export interface CustomFieldDef {
  key: string
  label: string
  type: CustomFieldType
  options?: string[]
  required?: boolean
}

export type CustomFieldValue = string | number | boolean | null

export interface CustomFieldsResponse extends Versioned {
  definitions: CustomFieldDef[]
  values: Record<string, CustomFieldValue>
}

/** A question in a template: a library `ref`, or a template-local `key` + text. */
export interface TemplateQuestionEntry {
  ref?: string
  key?: string
  question?: string
  description?: string
  facet?: string
  phase?: number
  priority?: QuestionPriority
}

export interface TemplateLeadEntry {
  key: string
  title: string
  description?: string
  phase?: number
  priority?: QuestionPriority
  task_type?: 'action_item' | 'investigative_lead' | 'verification' | 'documentation' | 'reporting'
  investigation_direction?: string
  /** Question refs/keys this lead answers. */
  answers: string[]
}

export type TemplatePlaybookRef = { builtin: string } | { playbook_id: string } | null

export interface CaseTemplateDefinition {
  schema_version: 1
  defaults?: { severity?: 'low' | 'medium' | 'high' | 'critical'; tlp?: TLPLevel; classification?: string }
  questions?: TemplateQuestionEntry[]
  leads?: TemplateLeadEntry[]
  playbook?: TemplatePlaybookRef
  custom_fields?: CustomFieldDef[]
  report_template?: string | null
}

export interface CaseTemplateCounts {
  questions: number
  leads: number
  custom_fields: number
  playbook: string | null
}

export interface CaseTemplate extends Versioned {
  /** `builtin:<key>` for built-ins, a UUID for organization templates. */
  id: string
  key: string
  name: string
  description?: string | null
  incident_type?: string | null
  is_builtin: boolean
  builtin_key?: string | null
  is_active: boolean
  cloned_from?: string | null
  definition?: CaseTemplateDefinition
  summary: CaseTemplateCounts
  creator?: { id: string; name: string } | null
  created_at?: string | null
  updated_at?: string | null
  /** Detail only: names behind the refs. */
  resolved?: {
    questions: { ref?: string; key?: string; question: string | null; facet?: string | null; phase?: number | null; priority?: string | null; source?: string | null }[]
    playbook: { kind: 'builtin' | 'org'; id: string; name: string | null } | null
  }
}

export interface CaseTemplateWriteInput {
  key?: string
  name?: string
  description?: string | null
  incident_type?: string | null
  is_active?: boolean
  definition?: CaseTemplateDefinition
}

export type ApplyPart = 'questions' | 'leads' | 'playbook' | 'custom_fields'

export interface ApplyTemplateOptions {
  apply_defaults?: boolean
  include?: ApplyPart[]
  dry_run?: boolean
  run_auto_actions?: boolean
}

export interface CaseTemplateApplyResult {
  created: { questions: number; leads: number; links: number }
  skipped: { kind: string; ref: string; reason: string }[]
  playbook: { status: 'activated' | 'already_active' | 'existing_playbook'; name: string } | null
  defaults_applied: { field: string; from: unknown; to: unknown }[]
  custom_fields_added: number
  dry_run: boolean
  template?: { ref: string; key: string; name: string; version: number }
  actions_executed?: unknown[]
}

/** One row of `GET /incidents/<id>/case-templates` (application ledger). */
export interface IncidentCaseTemplateRow {
  id: string
  template_key: string
  template_name: string
  template_version: number
  builtin_key?: string | null
  applied_at?: string | null
  applied_by_user?: { id: string; name: string } | null
  result: Partial<CaseTemplateApplyResult>
}

/** `GET /questions/library/dfiq`: the DFIQ library imported into this instance. */
export interface DfiqStatus {
  imported: boolean
  commit: string | null
  sha256: string | null
  method: 'download' | 'upload' | null
  imported_at: string | null
  imported_by: { id: string; name: string } | null
  counts: { scenarios: number; facets: number; questions: number } | null
  version: number
  pinned_commit: string
  pinned_sha256: string
  download_url: string
  source: string
  license: string
  attribution: string
  /** DFIQ files baked into the image (they take precedence over an import). */
  vendored_files: boolean
  can_import: boolean
}
