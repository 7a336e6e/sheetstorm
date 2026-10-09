/**
 * Pure helpers for the investigative questions board (W4-QST-UI): labels and
 * color tokens, progress, grouping, and the client-side mirror of the server's
 * status-transition rules (the server stays authoritative).
 */
import type {
  InvestigativeQuestion,
  QuestionConfidence,
  QuestionPriority,
  QuestionStatus,
  QuestionSummary,
} from '@/types'

interface Token {
  label: string
  bg: string
  text: string
  border: string
}

export const QUESTION_STATUSES: QuestionStatus[] = ['open', 'in_progress', 'answered', 'unanswerable']
export const QUESTION_CONFIDENCES: QuestionConfidence[] = ['low', 'medium', 'high', 'confirmed']
export const QUESTION_PRIORITIES: QuestionPriority[] = ['critical', 'high', 'medium', 'low']

export const statusTokens: Record<QuestionStatus, Token> = {
  open: { label: 'Open', bg: 'bg-blue-500/10', text: 'text-blue-600 dark:text-blue-400', border: 'border-blue-500/20' },
  in_progress: { label: 'In progress', bg: 'bg-amber-500/10', text: 'text-amber-600 dark:text-amber-400', border: 'border-amber-500/20' },
  answered: { label: 'Answered', bg: 'bg-emerald-500/10', text: 'text-emerald-600 dark:text-emerald-400', border: 'border-emerald-500/20' },
  unanswerable: { label: 'Unanswerable', bg: 'bg-muted', text: 'text-muted-foreground', border: 'border-border' },
}

export const confidenceTokens: Record<QuestionConfidence, Token> = {
  low: { label: 'Low', bg: 'bg-muted', text: 'text-muted-foreground', border: 'border-border' },
  medium: { label: 'Medium', bg: 'bg-amber-500/10', text: 'text-amber-600 dark:text-amber-400', border: 'border-amber-500/20' },
  high: { label: 'High', bg: 'bg-blue-500/10', text: 'text-blue-600 dark:text-blue-400', border: 'border-blue-500/20' },
  confirmed: { label: 'Confirmed', bg: 'bg-emerald-500/10', text: 'text-emerald-600 dark:text-emerald-400', border: 'border-emerald-500/20' },
}

export const priorityTokens: Record<QuestionPriority, Token> = {
  critical: { label: 'Critical', bg: 'bg-red-500/10', text: 'text-red-700 dark:text-red-400', border: 'border-red-500/20' },
  high: { label: 'High', bg: 'bg-orange-500/10', text: 'text-orange-700 dark:text-orange-400', border: 'border-orange-500/20' },
  medium: { label: 'Medium', bg: 'bg-amber-500/10', text: 'text-amber-600 dark:text-amber-400', border: 'border-amber-500/20' },
  low: { label: 'Low', bg: 'bg-muted', text: 'text-muted-foreground', border: 'border-border' },
}

export const statusLabel = (s: string): string => statusTokens[s as QuestionStatus]?.label ?? s
export const confidenceLabel = (c: string): string => confidenceTokens[c as QuestionConfidence]?.label ?? c
export const priorityLabel = (p: string): string => priorityTokens[p as QuestionPriority]?.label ?? p

export const QUESTION_SOURCE_LABEL: Record<string, string> = {
  manual: 'Manual',
  core: 'SheetStorm core',
  dfiq: 'DFIQ',
  template: 'Template',
}

/** Answered or unanswerable: the question counts toward progress. */
export const isResolved = (s: QuestionStatus): boolean => s === 'answered' || s === 'unanswerable'

/** Whole-number percentage of resolved questions (0 when there are none). */
export function progressPercent(summary: Pick<QuestionSummary, 'total' | 'resolved'> | null | undefined): number {
  if (!summary || summary.total <= 0) return 0
  return Math.round((summary.resolved / summary.total) * 100)
}

export function progressLabel(summary: Pick<QuestionSummary, 'total' | 'resolved'> | null | undefined): string {
  return summary ? `${summary.resolved}/${summary.total} answered` : '0/0 answered'
}

const PRIORITY_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 }

/** Sort key: priority, then phase (none last), then order. */
export function compareQuestions(a: InvestigativeQuestion, b: InvestigativeQuestion): number {
  return (
    (PRIORITY_RANK[a.priority] ?? 9) - (PRIORITY_RANK[b.priority] ?? 9) ||
    (a.phase ?? 99) - (b.phase ?? 99) ||
    (a.order_index ?? 0) - (b.order_index ?? 0)
  )
}

/** Questions bucketed by status, in board column order. */
export function groupByStatus<T extends Pick<InvestigativeQuestion, 'status'>>(items: T[]): Record<QuestionStatus, T[]> {
  const out: Record<QuestionStatus, T[]> = { open: [], in_progress: [], answered: [], unanswerable: [] }
  for (const q of items) (out[q.status] ?? out.open).push(q)
  return out
}

export interface FacetGroup<T> {
  facet: string
  items: T[]
}

export const NO_FACET = 'Uncategorized'

/** Group by facet, keeping first-seen order (the server sorts); no facet sorts last. */
export function groupByFacet<T extends Pick<InvestigativeQuestion, 'facet'>>(items: T[]): FacetGroup<T>[] {
  const groups = new Map<string, T[]>()
  for (const q of items) {
    const key = q.facet?.trim() || NO_FACET
    const list = groups.get(key)
    if (list) list.push(q)
    else groups.set(key, [q])
  }
  const named = Array.from(groups.entries()).filter(([k]) => k !== NO_FACET)
  const none = groups.get(NO_FACET)
  const ordered = none ? [...named, [NO_FACET, none] as [string, T[]]] : named
  return ordered.map(([facet, list]) => ({ facet, items: list }))
}

/**
 * Ids of the rows that start a new facet in a facet-sorted list, so the table
 * can print the facet name once per run. The first row always starts one.
 */
export function facetStarts(items: Pick<InvestigativeQuestion, 'id' | 'facet'>[]): Set<string> {
  const starts = new Set<string>()
  let prev: string | null = null
  for (const q of items) {
    const key = q.facet?.trim() || NO_FACET
    if (key !== prev) starts.add(q.id)
    prev = key
  }
  return starts
}

export interface AnswerDraft {
  status: QuestionStatus
  answer: string
  confidence: QuestionConfidence | ''
  evidenceCount: number
}

export type AnswerProblemCode = 'answer_required' | 'confidence_required' | 'evidence_required'

/**
 * Mirrors `question_service.apply_update`: answered needs an answer and a
 * confidence, unanswerable needs a rationale, `confirmed` needs evidence.
 * Returns the first problem or null.
 */
export function answerProblem(draft: AnswerDraft): { code: AnswerProblemCode; message: string } | null {
  const hasAnswer = draft.answer.trim().length > 0
  if (draft.status === 'answered') {
    if (!hasAnswer) return { code: 'answer_required', message: 'An answered question needs an answer.' }
    if (!draft.confidence) return { code: 'confidence_required', message: 'An answered question needs a confidence level.' }
  }
  if (draft.status === 'unanswerable' && !hasAnswer) {
    return { code: 'answer_required', message: 'An unanswerable question needs a rationale in the answer.' }
  }
  if (draft.confidence === 'confirmed' && draft.evidenceCount === 0) {
    return { code: 'evidence_required', message: 'Confirmed confidence needs at least one evidence reference.' }
  }
  return null
}

export const MAX_ANSWER_LENGTH = 20000
export const MAX_QUESTION_LENGTH = 1000

/** `1,2` style value of the server's comma-list status filter. */
export function statusFilterValue(statuses: QuestionStatus[]): string | undefined {
  return statuses.length ? statuses.join(',') : undefined
}

/** `Phase 2` / empty for none. */
export const phaseText = (phase: number | null | undefined): string => (phase ? `Phase ${phase}` : '')
