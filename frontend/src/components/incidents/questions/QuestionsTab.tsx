"use client"

/**
 * Investigative questions of an incident (W4-QST-UI): the questions the
 * investigation must answer, with status, answer and confidence. Server-paged
 * DataTable (filters in the URL, live `question` merges), progress summary,
 * add manually or from the library, apply a case template, archive.
 */
import { useState } from 'react'
import { Archive, BookOpen, FileStack, Pencil, Plus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DataTable, FilterSelect, type DataTableColumn } from '@/components/ui/data-table'
import { Timestamp } from '@/components/ui/timestamp'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { PermissionGate } from '@/components/auth/permission-gate'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import { incidentQuestionsEndpoint, questionsApi } from '@/lib/endpoints/questions'
import { notifyError } from '@/lib/errors'
import { invalidate } from '@/lib/query-cache'
import {
  QUESTION_PRIORITIES,
  QUESTION_STATUSES,
  confidenceTokens,
  phaseText,
  priorityLabel,
  priorityTokens,
  statusLabel,
  statusTokens,
} from '@/lib/questions'
import type { InvestigativeQuestion } from '@/types'
import { FocusNotice, type IncidentTabBaseProps } from '../table-helpers'
import { QuestionDialog } from './QuestionDialog'
import { LibraryDialog } from './LibraryDialog'
import { ApplyTemplateDialog } from './ApplyTemplateDialog'
import { QuestionProgress, useQuestionSummary } from './QuestionsSummaryCard'

const WRITE = 'incidents:update'

function TokenBadge({ token }: { token: { label: string; bg: string; text: string; border: string } }) {
  return <Badge variant="outline" className={`${token.bg} ${token.text} ${token.border}`}>{token.label}</Badge>
}

export function QuestionsTab({ incidentId, focusRowId }: IncidentTabBaseProps) {
  const confirm = useConfirm()
  const endpoint = incidentQuestionsEndpoint(incidentId)
  const query = usePaginatedQuery<InvestigativeQuestion>({
    endpoint,
    urlKey: 'questions',
    focus: focusRowId,
    live: 'question',
    defaults: { sort: 'order_index' },
  })
  const summary = useQuestionSummary(incidentId)
  const [editing, setEditing] = useState<InvestigativeQuestion | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [templateOpen, setTemplateOpen] = useState(false)

  const refresh = () => invalidate(endpoint)

  const openQuestion = (q: InvestigativeQuestion | null) => {
    setEditing(q)
    setDialogOpen(true)
  }

  const archive = async (q: InvestigativeQuestion) => {
    const ok = await confirm({
      title: 'Archive question?',
      description: 'It leaves the board and is not re-added by templates or the library.',
      confirmLabel: 'Archive',
      variant: 'destructive',
    })
    if (!ok) return
    try {
      await questionsApi.archive(incidentId, q.id, q.version)
      refresh()
    } catch (err) {
      notifyError(err, 'archive the question')
    }
  }

  const columns: DataTableColumn<InvestigativeQuestion>[] = [
    {
      id: 'question',
      header: 'Question',
      sortKey: 'order_index',
      cell: (q) => (
        <div className="min-w-0 space-y-0.5">
          <p className="font-medium">{q.question}</p>
          {q.answer && <p className="line-clamp-2 whitespace-pre-wrap text-xs text-muted-foreground">{q.answer}</p>}
          <p className="text-xs text-muted-foreground">
            {[q.facet, phaseText(q.phase)].filter(Boolean).join(' · ')}
          </p>
        </div>
      ),
    },
    { id: 'status', header: 'Status', sortKey: 'status', cell: (q) => <TokenBadge token={statusTokens[q.status]} /> },
    { id: 'priority', header: 'Priority', sortKey: 'priority', cell: (q) => <TokenBadge token={priorityTokens[q.priority]} />, hideBelow: 'sm' },
    {
      id: 'confidence',
      header: 'Confidence',
      cell: (q) => (q.confidence ? <TokenBadge token={confidenceTokens[q.confidence]} /> : <span className="text-muted-foreground">-</span>),
      hideBelow: 'md',
    },
    {
      id: 'updated',
      header: 'Updated',
      sortKey: 'updated_at',
      cell: (q) => <Timestamp value={q.answered_at || q.updated_at || q.created_at} />,
      hideBelow: 'lg',
    },
  ]

  return (
    <div className="space-y-4">
      <QuestionProgress summary={summary} />
      <FocusNotice focusRowId={focusRowId} focusFound={query.focusFound} noun="question" />
      <DataTable
        query={query}
        columns={columns}
        getRowId={(q) => q.id}
        ariaLabel="Investigative questions"
        searchPlaceholder="Search questions and answers"
        focusedRowId={focusRowId}
        onRowClick={(q) => openQuestion(q)}
        primaryAction={{ label: 'Add question', onSelect: () => openQuestion(null), permission: WRITE }}
        rowActions={(q) => [
          { label: 'Answer / edit', icon: Pencil, onSelect: () => openQuestion(q), permission: WRITE },
          { label: 'Archive', icon: Archive, onSelect: () => archive(q), permission: WRITE, destructive: true },
        ]}
        toolbar={
          <>
            <FilterSelect
              label="Status"
              value={query.state.filters.status}
              onChange={(v) => query.setFilter('status', v)}
              options={QUESTION_STATUSES.map((s) => ({ value: s, label: statusLabel(s) }))}
            />
            <FilterSelect
              label="Priority"
              value={query.state.filters.priority}
              onChange={(v) => query.setFilter('priority', v)}
              options={QUESTION_PRIORITIES.map((p) => ({ value: p, label: priorityLabel(p) }))}
            />
            <PermissionGate permission={WRITE}>
              <Button variant="outline" size="sm" onClick={() => setLibraryOpen(true)}>
                <BookOpen className="mr-1.5 h-4 w-4" /> From library
              </Button>
              <Button variant="outline" size="sm" onClick={() => setTemplateOpen(true)}>
                <FileStack className="mr-1.5 h-4 w-4" /> Apply template
              </Button>
            </PermissionGate>
          </>
        }
        empty={{
          title: 'No questions yet',
          description: 'Questions track what the investigation must answer. Add them manually, from the library or with a case template.',
          action: (
            <PermissionGate permission={WRITE}>
              <Button size="sm" onClick={() => setLibraryOpen(true)}>
                <Plus className="mr-1.5 h-4 w-4" /> Add from library
              </Button>
            </PermissionGate>
          ),
        }}
      />
      <QuestionDialog
        incidentId={incidentId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        question={editing}
        onSaved={refresh}
      />
      <LibraryDialog incidentId={incidentId} open={libraryOpen} onOpenChange={setLibraryOpen} onAdded={refresh} />
      <ApplyTemplateDialog
        incidentId={incidentId}
        open={templateOpen}
        onOpenChange={setTemplateOpen}
        onApplied={() => invalidate(`/incidents/${incidentId}`)}
      />
    </div>
  )
}
