"use client"

/**
 * Question progress (W4-QST-UI): `useQuestionSummary` reads the `summary`
 * extra of the incident's question list; `QuestionProgress` is the bar shown
 * on the Questions tab; `QuestionsSummaryCard` fills the Overview
 * `questionsSlot` (C21) with progress and the top open questions.
 */
import { useEffect, useState } from 'react'
import { ArrowRight, CircleHelp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { incidentQuestionsEndpoint } from '@/lib/endpoints/questions'
import { subscribe } from '@/lib/query-cache'
import { phaseText, priorityTokens, progressLabel, progressPercent } from '@/lib/questions'
import type { QuestionSummary } from '@/types'

export function useQuestionSummary(incidentId: string): QuestionSummary | null {
  const [summary, setSummary] = useState<QuestionSummary | null>(null)
  const [tick, setTick] = useState(0)
  const endpoint = incidentQuestionsEndpoint(incidentId)

  useEffect(() => subscribe(endpoint, () => setTick((t) => t + 1)), [endpoint])

  useEffect(() => {
    const ctrl = new AbortController()
    api
      .get<{ summary?: QuestionSummary }>(`${endpoint}?per_page=1`, { signal: ctrl.signal })
      .then((r) => setSummary(r.summary ?? null))
      .catch(() => {
        /* the tab/list shows load errors; the summary just stays empty */
      })
    return () => ctrl.abort()
  }, [endpoint, tick])

  return summary
}

export function QuestionProgress({ summary }: { summary: QuestionSummary | null }) {
  if (!summary || summary.total === 0) return null
  const pct = progressPercent(summary)
  return (
    <div className="space-y-1.5" aria-label="Question progress">
      <div className="flex items-center justify-between text-sm">
        <span>{progressLabel(summary)}</span>
        <span className="text-muted-foreground">
          {summary.open_high_priority > 0 ? `${summary.open_high_priority} high-priority open` : `${pct}%`}
        </span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <div className="h-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function QuestionsSummaryCard({ incidentId, onOpen }: { incidentId: string; onOpen: () => void }) {
  const summary = useQuestionSummary(incidentId)
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <CircleHelp className="h-4 w-4" /> Investigative questions
        </CardTitle>
        <Button variant="ghost" size="sm" onClick={onOpen}>
          Open <ArrowRight className="ml-1 h-3.5 w-3.5" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {!summary || summary.total === 0 ? (
          <p className="text-sm text-muted-foreground">No questions yet. Add them from the library or a case template.</p>
        ) : (
          <>
            <QuestionProgress summary={summary} />
            {summary.top_open.length > 0 && (
              <ul className="space-y-1">
                {summary.top_open.map((q) => (
                  <li key={q.id} className="flex items-start gap-2 text-sm">
                    <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${priorityTokens[q.priority].bg.replace('/10', '')}`} />
                    <span className="flex-1">{q.question}</span>
                    <span className="text-xs text-muted-foreground">{phaseText(q.phase)}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
