"use client"

/**
 * "Decisions & Actions" incident tab (W4-DEC): who decided what, when and on
 * what basis, and who carried it out. Two server-paginated lists with live
 * updates (`decision`, `decision_privileged`, `response_action`), lifecycle
 * transitions, signed revision history and exports. Gating is cosmetic (the
 * API enforces); a Viewer sees everything read-only.
 */
import { useEffect, useMemo, useState } from 'react'
import { History, Lock, Pencil, Plus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DataTable, FilterSelect, type DataTableColumn, type RowAction } from '@/components/ui/data-table'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermission, usePermissionCheck } from '@/components/auth/permission-gate'
import { usePaginatedQuery, type PaginatedQuery } from '@/hooks/use-paginated-query'
import { decisionsEndpoint, responseActionsEndpoint } from '@/lib/endpoints/decisions'
import { invalidate } from '@/lib/query-cache'
import { subscribeEntity } from '@/lib/realtime/live'
import type { Decision, DecisionEvent, ResponseAction, ResponseActionEvent, TaskEvidence } from '@/types'
import { FocusNotice } from '../table-helpers'
import {
  ACTION_STATUSES,
  CATEGORY_LABELS,
  DECISION_CATEGORIES,
  DECISION_STATUSES,
  actionEvents,
  actorLabel,
  decisionEvents,
  label,
  options,
  statusTone,
} from './decision-helpers'
import { DecisionFormDialog } from './DecisionFormDialog'
import { DecisionLogExportMenu } from './DecisionLogExportMenu'
import { ResponseActionFormDialog } from './ResponseActionFormDialog'
import { RevisionHistorySheet, type RevisionSubject } from './RevisionHistorySheet'
import { TransitionDialog, type TransitionTarget } from './TransitionDialog'

export interface DecisionsActionsTabProps {
  incidentId: string
  focusRowId?: string | null
  incident?: { incident_number?: number }
  onNavigate?: (tab: string, row?: string | null) => void
}

/** Incident tab that shows each evidence type (for link chips). */
export const LINK_TABS: Record<string, string> = {
  timeline_event: 'events',
  host: 'hosts',
  account: 'accounts',
  network_ioc: 'network',
  host_ioc: 'host-iocs',
  malware: 'malware',
  artifact: 'evidence',
  evidence_item: 'evidence',
  case_note: 'notes',
  task: 'tasks',
  decision: 'decisions',
  response_action: 'decisions',
}

const EVENT_LABELS: Record<DecisionEvent | ResponseActionEvent, string> = {
  approve: 'Approve…',
  reject: 'Reject…',
  reopen: 'Reopen…',
  supersede: 'Supersede…',
  authorize: 'Authorize…',
  start: 'Start',
  execute: 'Record execution…',
  fail: 'Mark failed…',
  verify: 'Record verification…',
  rollback: 'Roll back…',
  cancel: 'Cancel…',
}

export function StatusPill({ status }: { status: Decision['status'] | ResponseAction['status'] }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${statusTone(status)}`}>
      {label(status)}
    </span>
  )
}

function LinkChips({ links, onNavigate }: { links: TaskEvidence[]; onNavigate?: DecisionsActionsTabProps['onNavigate'] }) {
  if (!links?.length) return null
  return (
    <div className="flex flex-wrap gap-1.5">
      {links.map((l) => {
        const text = l.restricted ? `${label(l.evidence_type)} (restricted)` : l.missing ? `${label(l.evidence_type)} (deleted)` : l.label
        const tab = LINK_TABS[l.evidence_type]
        return (
          <button
            key={`${l.evidence_type}:${l.evidence_id}`}
            type="button"
            disabled={!tab || l.missing || !onNavigate}
            onClick={() => tab && onNavigate?.(tab, l.evidence_id)}
            className="rounded border border-white/10 bg-slate-800/60 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-60"
          >
            {text}
          </button>
        )
      })}
    </div>
  )
}

/** "Name · time" stamp for a lifecycle step, or a dash. */
function Stamp({ who, at }: { who: string | null; at: string | null }) {
  if (!who && !at) return <span className="text-muted-foreground">—</span>
  return (
    <span className="text-xs">
      {who ?? '—'}
      {at && (
        <>
          {' · '}
          <Timestamp value={at} seconds={false} />
        </>
      )}
    </span>
  )
}

interface SectionProps {
  incidentId: string
  focusRowId?: string | null
  onNavigate?: DecisionsActionsTabProps['onNavigate']
  onTransition(t: TransitionTarget): void
  onHistory(s: RevisionSubject): void
}

function DecisionsSection({
  query,
  onEdit,
  ...p
}: SectionProps & { query: PaginatedQuery<Decision>; onEdit(d: Decision | null): void }) {
  const can = usePermissionCheck()
  const columns = useMemo<DataTableColumn<Decision>[]>(
    () => [
      { id: 'number', header: 'ID', sortKey: 'number', cell: (d) => <span className="font-mono text-xs">{d.display_id}</span> },
      {
        id: 'title',
        header: 'Decision',
        cell: (d) => (
          <div className="min-w-[14rem]">
            <div className="flex items-center gap-2 font-medium">
              {d.title}
              {d.is_privileged && (
                <Badge variant="outline" className="border-amber-500/40 text-amber-300">
                  <Lock className="mr-1 h-3 w-3" /> Privileged
                </Badge>
              )}
            </div>
            <div className="line-clamp-1 text-xs text-muted-foreground">{d.decision}</div>
          </div>
        ),
      },
      { id: 'category', header: 'Category', sortKey: 'category', hideBelow: 'md', cell: (d) => CATEGORY_LABELS[d.category] },
      { id: 'status', header: 'Status', sortKey: 'status', cell: (d) => <StatusPill status={d.status} /> },
      {
        id: 'decided',
        header: 'Decided',
        sortKey: 'decided_at',
        hideBelow: 'sm',
        cell: (d) => <Stamp who={actorLabel(d, 'decided_by_user_id', d.decided_by_name)} at={d.decided_at} />,
      },
      {
        id: 'approved',
        header: 'Approved',
        hideBelow: 'lg',
        cell: (d) => <Stamp who={actorLabel(d, 'approved_by_user_id', d.approved_by_name)} at={d.approved_at} />,
      },
    ],
    []
  )

  const rowActions = (d: Decision): RowAction[] => [
    ...(can('decisions:update') ? [{ label: 'Revise…', icon: Pencil, onSelect: () => onEdit(d) }] : []),
    ...decisionEvents(d, can).map((event) => ({
      label: EVENT_LABELS[event],
      onSelect: () => p.onTransition({ kind: 'decision', record: d, event }),
    })),
    {
      label: `History (${d.revision_count ?? 0})`,
      icon: History,
      onSelect: () => p.onHistory({ kind: 'decision', id: d.id, displayId: d.display_id, title: d.title }),
    },
  ]

  return (
    <DataTable<Decision>
      query={query}
      columns={columns}
      getRowId={(d) => d.id}
      ariaLabel="Decisions"
      searchPlaceholder="Search decisions…"
      focusedRowId={p.focusRowId}
      rowActions={rowActions}
      toolbar={
        <>
          <FilterSelect label="Status" allLabel="All statuses" value={query.state.filters.status}
            onChange={(v) => query.setFilter('status', v)} options={options(DECISION_STATUSES)} />
          <FilterSelect label="Category" allLabel="All categories" value={query.state.filters.category}
            onChange={(v) => query.setFilter('category', v)} options={options(DECISION_CATEGORIES, CATEGORY_LABELS)} />
        </>
      }
      renderExpanded={(d) => (
        <div className="space-y-2 text-sm">
          <p className="whitespace-pre-wrap">{d.decision}</p>
          {d.rationale && <p className="whitespace-pre-wrap text-slate-300"><span className="text-muted-foreground">Rationale: </span>{d.rationale}</p>}
          {d.alternatives?.length > 0 && (
            <ul className="list-disc pl-5 text-slate-300">
              {d.alternatives.map((a, i) => (
                <li key={i}>{a.option}{a.reason_not_chosen ? ` — not chosen: ${a.reason_not_chosen}` : ''}</li>
              ))}
            </ul>
          )}
          {d.self_approved && <p className="text-xs text-amber-300">Approved by the person who recorded it.</p>}
          {d.superseded_by && <p className="text-xs">Superseded by {d.superseded_by.display_id} · {d.superseded_by.title}</p>}
          {d.status_reason && <p className="text-xs text-muted-foreground">Last status reason: {d.status_reason}</p>}
          <LinkChips links={d.links} onNavigate={p.onNavigate} />
        </div>
      )}
      empty={{ title: 'No decisions recorded', description: 'Record who decided what, when and why.' }}
    />
  )
}

function ActionsSection({
  query,
  onEdit,
  ...p
}: SectionProps & { query: PaginatedQuery<ResponseAction>; onEdit(a: ResponseAction | null): void }) {
  const can = usePermissionCheck()
  const columns = useMemo<DataTableColumn<ResponseAction>[]>(
    () => [
      { id: 'number', header: 'ID', sortKey: 'number', cell: (a) => <span className="font-mono text-xs">{a.display_id}</span> },
      {
        id: 'title',
        header: 'Action',
        cell: (a) => (
          <div className="min-w-[12rem]">
            <div className="font-medium">{a.title}</div>
            <div className="text-xs text-muted-foreground">
              {label(a.action_type)}
              {a.target_label ? ` · ${a.target_label}` : ''}
            </div>
          </div>
        ),
      },
      { id: 'status', header: 'Status', sortKey: 'status', cell: (a) => <StatusPill status={a.status} /> },
      {
        id: 'authorized',
        header: 'Authorized',
        hideBelow: 'md',
        cell: (a) => <Stamp who={actorLabel(a, 'authorized_by_user_id', a.authorized_by_name)} at={a.authorized_at} />,
      },
      {
        id: 'executed',
        header: 'Executed',
        sortKey: 'executed_at',
        hideBelow: 'sm',
        cell: (a) => <Stamp who={actorLabel(a, 'executed_by_user_id', a.executed_by_name)} at={a.executed_at} />,
      },
      {
        id: 'verified',
        header: 'Verified',
        hideBelow: 'lg',
        cell: (a) => (
          <Stamp
            who={a.verified_at ? `${actorLabel(a, 'verified_by_user_id', a.verified_by_name) ?? '—'} (${label(a.verification_result)})` : null}
            at={a.verified_at}
          />
        ),
      },
    ],
    []
  )

  const rowActions = (a: ResponseAction): RowAction[] => [
    ...(can('response_actions:update') ? [{ label: 'Revise…', icon: Pencil, onSelect: () => onEdit(a) }] : []),
    ...actionEvents(a, can).map((event) => ({
      label: EVENT_LABELS[event],
      onSelect: () => p.onTransition({ kind: 'action', record: a, event }),
    })),
    {
      label: `History (${a.revision_count ?? 0})`,
      icon: History,
      onSelect: () => p.onHistory({ kind: 'action', id: a.id, displayId: a.display_id, title: a.title }),
    },
  ]

  return (
    <DataTable<ResponseAction>
      query={query}
      columns={columns}
      getRowId={(a) => a.id}
      ariaLabel="Response actions"
      searchPlaceholder="Search actions…"
      focusedRowId={p.focusRowId}
      rowActions={rowActions}
      toolbar={
        <FilterSelect label="Status" allLabel="All statuses" value={query.state.filters.status}
          onChange={(v) => query.setFilter('status', v)} options={options(ACTION_STATUSES)} />
      }
      renderExpanded={(a) => (
        <div className="space-y-2 text-sm">
          {a.description && <p className="whitespace-pre-wrap">{a.description}</p>}
          {a.decision && <p className="text-xs">Implements {a.decision.display_id} · {a.decision.title}</p>}
          {a.decision_restricted && <p className="text-xs text-muted-foreground">Implements a privileged decision.</p>}
          {a.target_state_after && (
            <p className="text-xs">
              Target {a.target_state_after.field}: {label(String(a.target_state_before?.value ?? ''))} → {label(String(a.target_state_after.value ?? ''))}
            </p>
          )}
          {a.verification_method && <p className="text-xs">Verified by: {a.verification_method}{a.verification_notes ? ` — ${a.verification_notes}` : ''}</p>}
          {a.rollback_plan && <p className="text-xs text-muted-foreground">Rollback plan: {a.rollback_plan}</p>}
          {a.rollback_reason && <p className="text-xs text-muted-foreground">Rolled back: {a.rollback_reason}</p>}
          {(a.self_approved || a.self_verified) && (
            <p className="text-xs text-amber-300">
              {a.self_approved ? 'Authorized by the requester. ' : ''}{a.self_verified ? 'Verified by the executor.' : ''}
            </p>
          )}
          <LinkChips links={a.links} onNavigate={p.onNavigate} />
        </div>
      )}
      empty={{ title: 'No response actions recorded', description: 'Plan or record containment and notification steps.' }}
    />
  )
}

export function DecisionsActionsTab({ incidentId, focusRowId, incident, onNavigate }: DecisionsActionsTabProps) {
  const canReadDecisions = usePermission('decisions:read')
  const canReadActions = usePermission('response_actions:read')
  const canCreateDecision = usePermission('decisions:create')
  const canCreateAction = usePermission('response_actions:create')
  const dEndpoint = decisionsEndpoint(incidentId)
  const aEndpoint = responseActionsEndpoint(incidentId)
  const decisions = usePaginatedQuery<Decision>({
    endpoint: dEndpoint,
    urlKey: 'decisions',
    live: 'decision',
    focus: focusRowId,
    enabled: canReadDecisions,
  })
  const actions = usePaginatedQuery<ResponseAction>({
    endpoint: aEndpoint,
    urlKey: 'ractions',
    live: 'response_action',
    focus: focusRowId,
    enabled: canReadActions,
  })
  // Privileged decisions arrive on their own scope (C9): refetch to merge them.
  useEffect(() => subscribeEntity('decision_privileged', () => invalidate(dEndpoint)), [dEndpoint])

  const [decisionDialog, setDecisionDialog] = useState<{ open: boolean; decision: Decision | null }>({ open: false, decision: null })
  const [actionDialog, setActionDialog] = useState<{ open: boolean; action: ResponseAction | null }>({ open: false, action: null })
  const [transition, setTransition] = useState<TransitionTarget | null>(null)
  const [history, setHistory] = useState<RevisionSubject | null>(null)
  const refresh = () => {
    invalidate(dEndpoint)
    invalidate(aEndpoint)
  }
  const section = { incidentId, focusRowId, onNavigate, onTransition: setTransition, onHistory: setHistory }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Every change is kept as a hash-chained, signed revision. Nothing here is ever sent to AI providers.
        </p>
        <DecisionLogExportMenu incidentId={incidentId} incidentNumber={incident?.incident_number} />
      </div>
      {canReadDecisions && (
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Decisions</CardTitle>
              <CardDescription>Who decided what, when, on what basis — and who approved it.</CardDescription>
            </div>
            {canCreateDecision && (
              <Button onClick={() => setDecisionDialog({ open: true, decision: null })}>
                <Plus className="mr-1 h-4 w-4" /> Record decision
              </Button>
            )}
          </CardHeader>
          <CardContent>
            <FocusNotice focusRowId={focusRowId} focusFound={decisions.focusFound} noun="decision" />
            <DecisionsSection {...section} query={decisions} onEdit={(d) => setDecisionDialog({ open: true, decision: d })} />
          </CardContent>
        </Card>
      )}
      {canReadActions && (
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Response actions</CardTitle>
              <CardDescription>Requested → authorized → executed → verified, with rollback.</CardDescription>
            </div>
            {canCreateAction && (
              <Button onClick={() => setActionDialog({ open: true, action: null })}>
                <Plus className="mr-1 h-4 w-4" /> Plan action
              </Button>
            )}
          </CardHeader>
          <CardContent>
            <ActionsSection {...section} query={actions} onEdit={(a) => setActionDialog({ open: true, action: a })} />
          </CardContent>
        </Card>
      )}
      <DecisionFormDialog
        incidentId={incidentId}
        open={decisionDialog.open}
        decision={decisionDialog.decision}
        onOpenChange={(open) => setDecisionDialog((d) => ({ ...d, open }))}
        onSaved={refresh}
      />
      <ResponseActionFormDialog
        incidentId={incidentId}
        open={actionDialog.open}
        action={actionDialog.action}
        decisions={decisions.items}
        onOpenChange={(open) => setActionDialog((a) => ({ ...a, open }))}
        onSaved={refresh}
      />
      <TransitionDialog
        incidentId={incidentId}
        target={transition}
        decisions={decisions.items}
        onOpenChange={(open) => !open && setTransition(null)}
        onDone={refresh}
      />
      <RevisionHistorySheet incidentId={incidentId} subject={history} onClose={() => setHistory(null)} />
    </div>
  )
}
