/**
 * Client-side checks of a case template definition (W4-QST-UI), mirroring the
 * cross-field rules of backend `schemas/case_template.py`. The server is
 * authoritative and re-validates everything (types, lengths, refs); this only
 * catches mistakes before a round trip.
 */
import type { CaseTemplate, CaseTemplateDefinition } from '@/types'

export const TEMPLATE_KEY_RE = /^[a-z0-9][a-z0-9-]{1,63}$/
const ENTRY_KEY_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/
const FIELD_KEY_RE = /^[a-z][a-z0-9_]{0,62}$/
const LIBRARY_REF_RE = /^(ss|dfiq):[A-Za-z0-9_-]{1,32}$/

export const EMPTY_DEFINITION: CaseTemplateDefinition = {
  schema_version: 1,
  defaults: {},
  questions: [],
  leads: [],
  playbook: null,
  custom_fields: [],
}

export interface DefinitionCheck {
  definition: CaseTemplateDefinition | null
  errors: string[]
}

/** Parse the editor JSON and list every problem found (empty = OK to send). */
export function checkDefinition(source: string): DefinitionCheck {
  let raw: unknown
  try {
    raw = JSON.parse(source)
  } catch (e) {
    return { definition: null, errors: [`Not valid JSON: ${(e as Error).message}`] }
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return { definition: null, errors: ['The definition must be a JSON object.'] }
  }
  const def = raw as CaseTemplateDefinition
  const errors: string[] = []
  if (def.schema_version !== 1) errors.push('schema_version must be 1.')

  const ids = new Set<string>()
  ;(def.questions ?? []).forEach((q, i) => {
    const where = `questions[${i}]`
    if (q.ref) {
      if (!LIBRARY_REF_RE.test(q.ref)) errors.push(`${where}: ref "${q.ref}" is not a library reference (ss:… or dfiq:…).`)
      if (q.key || q.question) errors.push(`${where}: use either ref, or key + question, not both.`)
    } else {
      if (!q.key || !ENTRY_KEY_RE.test(q.key)) errors.push(`${where}: a local question needs a key (a-z, 0-9, _ or -).`)
      if (!q.question || q.question.trim().length < 3) errors.push(`${where}: question text is required.`)
    }
    const id = q.ref || q.key
    if (id) {
      if (ids.has(id)) errors.push(`${where}: "${id}" appears twice.`)
      ids.add(id)
    }
  })

  const leadKeys = new Set<string>()
  ;(def.leads ?? []).forEach((l, i) => {
    const where = `leads[${i}]`
    if (!l.key || !ENTRY_KEY_RE.test(l.key)) errors.push(`${where}: key is required (a-z, 0-9, _ or -).`)
    else if (leadKeys.has(l.key)) errors.push(`${where}: key "${l.key}" appears twice.`)
    else leadKeys.add(l.key)
    if (!l.title || l.title.trim().length < 3) errors.push(`${where}: title is required.`)
    for (const a of l.answers ?? []) {
      if (!ids.has(a)) errors.push(`${where}: answers "${a}", which is not a question of this template.`)
    }
  })

  const fieldKeys = new Set<string>()
  ;(def.custom_fields ?? []).forEach((f, i) => {
    const where = `custom_fields[${i}]`
    if (!f.key || !FIELD_KEY_RE.test(f.key)) errors.push(`${where}: key must start with a letter (a-z, 0-9, _).`)
    else if (fieldKeys.has(f.key)) errors.push(`${where}: key "${f.key}" appears twice.`)
    else fieldKeys.add(f.key)
    if (!f.label?.trim()) errors.push(`${where}: label is required.`)
    if (f.type === 'select' && !(f.options && f.options.length)) errors.push(`${where}: a select field needs options.`)
    if (f.type !== 'select' && f.options) errors.push(`${where}: only select fields take options.`)
  })

  const pb = def.playbook as Record<string, unknown> | null | undefined
  if (pb && Object.keys(pb).length !== 1) errors.push('playbook: give exactly one of builtin or playbook_id.')

  return { definition: errors.length ? null : def, errors }
}

export const formatDefinition = (def: CaseTemplateDefinition | undefined): string =>
  JSON.stringify(def ?? EMPTY_DEFINITION, null, 2)

/** `5 questions · 3 leads · playbook` for a template row. */
export function templateSummaryText(t: Pick<CaseTemplate, 'summary'>): string {
  const s = t.summary
  const parts = [`${s.questions} questions`, `${s.leads} leads`]
  if (s.custom_fields) parts.push(`${s.custom_fields} custom fields`)
  if (s.playbook) parts.push('playbook')
  return parts.join(' · ')
}

/**
 * A complete, valid example (shown in the editor). Library refs are SheetStorm
 * core questions (`ss:SSQ-…`); `dfiq:Q…` refs work once DFIQ is imported.
 */
export const EXAMPLE_DEFINITION: CaseTemplateDefinition = {
  schema_version: 1,
  defaults: { severity: 'high', tlp: 'amber', classification: 'phishing' },
  questions: [
    { ref: 'ss:SSQ-001' },
    { ref: 'ss:SSQ-005', priority: 'critical' },
    {
      key: 'bec-mailbox-rules',
      question: 'Were mailbox forwarding or inbox rules created by the attacker?',
      facet: 'Email',
      phase: 2,
      priority: 'high',
    },
  ],
  leads: [
    {
      key: 'review-mailbox-audit',
      title: 'Review the mailbox audit log of the affected users',
      phase: 2,
      priority: 'high',
      task_type: 'investigative_lead',
      investigation_direction: 'Look for new inbox rules, forwarding and logins from new countries.',
      answers: ['ss:SSQ-001', 'bec-mailbox-rules'],
    },
  ],
  playbook: { builtin: 'picerl-generic' },
  custom_fields: [
    { key: 'ticket_id', label: 'Ticket ID', type: 'text' },
    { key: 'business_unit', label: 'Business unit', type: 'select', options: ['Finance', 'HR', 'IT'], required: true },
    { key: 'notified_regulator', label: 'Regulator notified', type: 'boolean' },
  ],
}

/** One line per field for the editor's format reference. */
export const DEFINITION_REFERENCE: { field: string; text: string }[] = [
  { field: 'schema_version', text: 'Always 1.' },
  { field: 'defaults', text: 'Optional severity (low…critical), tlp (white, green, amber, amber_strict, red) and classification, applied when chosen for a new incident.' },
  { field: 'questions[]', text: 'Either { "ref": "ss:SSQ-001" } from the question library (or "dfiq:Q…" once DFIQ is imported), or your own { "key", "question" }. Optional facet, phase (1–6), priority.' },
  { field: 'leads[]', text: 'Starter tasks: key, title, optional phase, priority, task_type, investigation_direction, and "answers": the question refs/keys the lead helps answer.' },
  { field: 'playbook', text: '{ "builtin": "picerl-generic" | "ransomware" }, { "playbook_id": "<uuid>" } for one of your playbooks, or null.' },
  { field: 'custom_fields[]', text: 'Extra incident fields: key (a-z, 0-9, _), label, type (text, number, boolean, date, select), options for select, required.' },
]
