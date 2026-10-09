/** @jest-environment node */
import { describe, expect, it } from '@jest/globals'
import {
  answerProblem,
  compareQuestions,
  facetStarts,
  groupByFacet,
  groupByStatus,
  isResolved,
  progressLabel,
  progressPercent,
  statusFilterValue,
} from './questions'
import type { InvestigativeQuestion } from '@/types'

const q = (over: Partial<InvestigativeQuestion>): InvestigativeQuestion => ({
  id: 'q1',
  incident_id: 'i1',
  question: 'Which accounts were used?',
  status: 'open',
  priority: 'medium',
  evidence_refs: [],
  source: 'manual',
  order_index: 0,
  is_archived: false,
  lead_ids: [],
  created_at: '2026-01-01T00:00:00Z',
  ...over,
})

describe('progress', () => {
  it('is resolved/total as a rounded percentage', () => {
    expect(progressPercent({ total: 20, resolved: 12 })).toBe(60)
    expect(progressPercent({ total: 3, resolved: 1 })).toBe(33)
  })
  it('is 0 without questions or summary', () => {
    expect(progressPercent({ total: 0, resolved: 0 })).toBe(0)
    expect(progressPercent(null)).toBe(0)
    expect(progressLabel({ total: 20, resolved: 12 })).toBe('12/20 answered')
    expect(progressLabel(undefined)).toBe('0/0 answered')
  })
  it('counts answered and unanswerable as resolved', () => {
    expect(isResolved('answered')).toBe(true)
    expect(isResolved('unanswerable')).toBe(true)
    expect(isResolved('open')).toBe(false)
    expect(isResolved('in_progress')).toBe(false)
  })
})

describe('grouping', () => {
  const items = [
    q({ id: 'a', status: 'open', facet: 'Initial Access' }),
    q({ id: 'b', status: 'answered', facet: 'Initial Access' }),
    q({ id: 'c', status: 'in_progress', facet: 'Impact' }),
    q({ id: 'd', status: 'unanswerable', facet: null }),
    q({ id: 'e', status: 'open', facet: '  ' }),
  ]

  it('buckets by status in board order', () => {
    const g = groupByStatus(items)
    expect(g.open.map((x) => x.id)).toEqual(['a', 'e'])
    expect(g.in_progress.map((x) => x.id)).toEqual(['c'])
    expect(g.answered.map((x) => x.id)).toEqual(['b'])
    expect(g.unanswerable.map((x) => x.id)).toEqual(['d'])
  })

  it('groups by facet keeping first-seen order and putting no-facet last', () => {
    const groups = groupByFacet(items)
    expect(groups.map((g) => g.facet)).toEqual(['Initial Access', 'Impact', 'Uncategorized'])
    expect(groups[2].items.map((x) => x.id)).toEqual(['d', 'e'])
  })

  it('marks the first row of each facet run', () => {
    const sorted = [
      q({ id: 'a', facet: 'X' }),
      q({ id: 'b', facet: 'X' }),
      q({ id: 'c', facet: 'Y' }),
      q({ id: 'd', facet: null }),
    ]
    expect(Array.from(facetStarts(sorted))).toEqual(['a', 'c', 'd'])
    expect(facetStarts([]).size).toBe(0)
  })
})

describe('compareQuestions', () => {
  it('orders by priority, then phase (none last), then order', () => {
    const list = [
      q({ id: 'low', priority: 'low' }),
      q({ id: 'hi-nophase', priority: 'high', phase: null }),
      q({ id: 'hi-p2', priority: 'high', phase: 2, order_index: 5 }),
      q({ id: 'hi-p2-first', priority: 'high', phase: 2, order_index: 1 }),
      q({ id: 'crit', priority: 'critical' }),
    ]
    expect([...list].sort(compareQuestions).map((x) => x.id)).toEqual([
      'crit',
      'hi-p2-first',
      'hi-p2',
      'hi-nophase',
      'low',
    ])
  })
})

describe('answerProblem (mirrors the server transition rules)', () => {
  it('requires an answer and a confidence to answer', () => {
    expect(answerProblem({ status: 'answered', answer: ' ', confidence: 'high', evidenceCount: 0 })?.code).toBe('answer_required')
    expect(answerProblem({ status: 'answered', answer: 'x', confidence: '', evidenceCount: 0 })?.code).toBe('confidence_required')
    expect(answerProblem({ status: 'answered', answer: 'x', confidence: 'high', evidenceCount: 0 })).toBeNull()
  })
  it('requires a rationale for unanswerable', () => {
    expect(answerProblem({ status: 'unanswerable', answer: '', confidence: '', evidenceCount: 0 })?.code).toBe('answer_required')
    expect(answerProblem({ status: 'unanswerable', answer: 'logs rotated', confidence: '', evidenceCount: 0 })).toBeNull()
  })
  it('requires evidence for confirmed confidence', () => {
    expect(answerProblem({ status: 'answered', answer: 'x', confidence: 'confirmed', evidenceCount: 0 })?.code).toBe('evidence_required')
    expect(answerProblem({ status: 'answered', answer: 'x', confidence: 'confirmed', evidenceCount: 2 })).toBeNull()
  })
  it('lets open and in-progress questions stay unanswered', () => {
    expect(answerProblem({ status: 'open', answer: '', confidence: '', evidenceCount: 0 })).toBeNull()
    expect(answerProblem({ status: 'in_progress', answer: '', confidence: '', evidenceCount: 0 })).toBeNull()
  })
})

describe('statusFilterValue', () => {
  it('joins statuses for the server comma list', () => {
    expect(statusFilterValue(['open', 'in_progress'])).toBe('open,in_progress')
    expect(statusFilterValue([])).toBeUndefined()
  })
})
