"use client"

/**
 * Lead queue (W2-DFIR-A, surface-dfir §3.4): every investigative lead of the
 * incident with its direction, outcome, linked evidence and owner. The
 * outcome is set inline (`tasks:update`); read-only users see a badge.
 *
 * Also exports the evidence-chip helpers shared with TasksTab: labels come
 * from the server (`task.evidence`); legacy `extra_data.linked_entities` is
 * only a display fallback.
 */
import { useEffect, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import type { LucideIcon } from 'lucide-react'
import { Bug, Clock, Edit2, FileText, Fingerprint, Globe, Key, Link2, Server, User } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DataTable, FilterSelect, type DataTableColumn } from '@/components/ui/data-table'
import { UserPicker } from '@/components/ui/entity-picker'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermission } from '@/components/auth/permission-gate'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import api, { isAbortError, withQuery } from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { notifyError } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { leadOutcomeColors, type LeadOutcomeKey } from '@/lib/design-tokens'
import type { DfirTask, LeadCounts, PaginatedResponse, TaskEvidence } from '@/types'
import { FocusNotice, type IncidentTabBaseProps } from '../table-helpers'

// ─── Evidence helpers (shared with TasksTab) ─────────────────────────────

export const EVIDENCE_TYPES: Record<string, { label: string; tab: string; icon: LucideIcon; permission: string }> = {
  timeline_event: { label: 'Event', tab: 'events', icon: Clock, permission: 'timeline:read' },
  host: { label: 'Host', tab: 'hosts', icon: Server, permission: 'hosts:read' },
  account: { label: 'Account', tab: 'accounts', icon: Key, permission: 'accounts:read' },
  network_ioc: { label: 'Network IOC', tab: 'network', icon: Globe, permission: 'network_iocs:read' },
  host_ioc: { label: 'Host IOC', tab: 'host-iocs', icon: Fingerprint, permission: 'host_iocs:read' },
  malware: { label: 'Malware', tab: 'malware', icon: Bug, permission: 'malware:read' },
  artifact: { label: 'Artifact', tab: 'evidence', icon: FileText, permission: 'artifacts:read' },
  evidence_item: { label: 'Evidence item', tab: 'evidence', icon: FileText, permission: 'artifacts:read' },
}

const TYPE_ALIASES: Record<string, string> = { host_indicator: 'host_ioc', network_indicator: 'network_ioc' }

export function canonicalEvidenceType(type: string): string {
  return TYPE_ALIASES[type] ?? type
}

/**
 * Evidence of a task for display: the server-resolved `evidence`, else the
 * stored `evidence_refs` (e.g. a live socket row), else legacy
 * `extra_data.linked_entities`. Legacy labels are only used as a fallback.
 */
export function taskEvidence(task: Pick<DfirTask, 'evidence' | 'evidence_refs' | 'extra_data'>): TaskEvidence[] {
  const legacy = task.extra_data?.linked_entities ?? []
  const legacyLabel = (id: string) => legacy.find((e) => e.id === id)?.label ?? null
  const fromServer = task.evidence ?? []
  if (fromServer.length > 0) {
    return fromServer.map((e) => (e.label || e.missing || e.restricted ? e : { ...e, label: legacyLabel(e.evidence_id) }))
  }
  if (task.evidence_refs?.length) {
    return task.evidence_refs.map((r) => ({
      evidence_type: canonicalEvidenceType(r.evidence_type),
      evidence_id: r.evidence_id,
      label: legacyLabel(r.evidence_id),
      missing: false,
    }))
  }
  return legacy.map((e) => ({
    evidence_type: canonicalEvidenceType(e.type),
    evidence_id: e.id,
    label: e.label ?? null,
    missing: false,
  }))
}

export function evidenceLabel(e: TaskEvidence): string {
  const type = EVIDENCE_TYPES[e.evidence_type]?.label ?? e.evidence_type
  if (e.missing) return `${type} (deleted)`
  if (e.restricted) return `${type} (restricted)`
  return e.label || `${type} ${e.evidence_id.slice(0, 8)}`
}

/** Opens the owning incident tab on the linked row (`?tab=&row=`). */
export function useOpenEvidence() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  return (e: TaskEvidence) => {
    const info = EVIDENCE_TYPES[e.evidence_type]
    if (!info || e.missing || e.restricted) return
    const next = new URLSearchParams(searchParams?.toString() ?? '')
    next.set('tab', info.tab)
    next.set('row', e.evidence_id)
    router.push(`${pathname}?${next.toString()}`, { scroll: false })
  }
}

export function EvidenceChips({
  evidence,
  onOpen,
  className,
}: {
  evidence: TaskEvidence[]
  onOpen?: (e: TaskEvidence) => void
  className?: string
}) {
  if (evidence.length === 0) return null
  return (
    <div className={cn('flex flex-wrap items-center gap-1.5', className)}>
      <Link2 className="h-3 w-3 text-muted-foreground" aria-hidden />
      {evidence.map((e) => {
        const Icon = EVIDENCE_TYPES[e.evidence_type]?.icon
        const label = evidenceLabel(e)
        const clickable = !!onOpen && !e.missing && !e.restricted && !!EVIDENCE_TYPES[e.evidence_type]
        const chipClass = cn(
          'inline-flex max-w-[220px] items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px]',
          e.missing || e.restricted
            ? 'border-border bg-muted text-muted-foreground line-through decoration-muted-foreground/50'
            : 'border-primary/20 bg-primary/10 text-primary'
        )
        const content = (
          <>
            {Icon && <Icon className="h-3 w-3 shrink-0" aria-hidden />}
            <span className="truncate">{label}</span>
          </>
        )
        return clickable ? (
          <button
            key={`${e.evidence_type}:${e.evidence_id}`}
            type="button"
            className={cn(chipClass, 'hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring')}
            title={`Open ${label}`}
            aria-label={`Open ${label}`}
            onClick={(ev) => {
              ev.stopPropagation()
              onOpen!(e)
            }}
          >
            {content}
          </button>
        ) : (
          <span key={`${e.evidence_type}:${e.evidence_id}`} className={chipClass} title={label}>
            {content}
          </span>
        )
      })}
    </div>
  )
}

// ─── Outcome ─────────────────────────────────────────────────────────────

export const OUTCOME_OPTIONS = (Object.keys(leadOutcomeColors) as LeadOutcomeKey[]).map((k) => ({
  value: k,
  label: leadOutcomeColors[k].label,
}))

export function LeadOutcomeBadge({ outcome }: { outcome?: string | null }) {
  const key = (outcome || 'open') as LeadOutcomeKey
  const c = leadOutcomeColors[key] ?? leadOutcomeColors.open
  return (
    <Badge variant="outline" className={cn('border px-1.5 py-0 text-[10px]', c.bg, c.text, c.border)}>
      {c.label}
    </Badge>
  )
}

const STATUS_OPTIONS = [
  { value: 'pending', label: 'Pending' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'completed', label: 'Completed' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'cancelled', label: 'Cancelled' },
]

// ─── Leads view ──────────────────────────────────────────────────────────

export interface LeadsViewProps extends IncidentTabBaseProps {
  /** Opens the task editor (TasksTab's modal). */
  onEdit?: (task: DfirTask) => void
}

export function LeadsView({ incidentId, focusRowId, onEdit }: LeadsViewProps) {
  const canUpdate = usePermission('tasks:update')
  const openEvidence = useOpenEvidence()
  const tasksEndpoint = `/incidents/${incidentId}/tasks`
  const query = usePaginatedQuery<DfirTask>({
    endpoint: `${tasksEndpoint}?task_type=investigative_lead&include_comments=false`,
    urlKey: 'leads',
    focus: focusRowId,
    live: 'task',
    defaults: { sort: '-updated_at', filters: { lead_outcome: 'open' } },
  })
  const counts = useLeadCounts(tasksEndpoint, query.items)
  const [saving, setSaving] = useState<string | null>(null)

  const setOutcome = async (task: DfirTask, value: string) => {
    setSaving(task.id)
    try {
      await api.put(
        `${tasksEndpoint}/${task.id}`,
        { lead_outcome: value === 'open' ? null : value },
        { ifMatch: task.version }
      )
      invalidate(tasksEndpoint)
    } catch (error) {
      notifyError(error, 'set the lead outcome')
    } finally {
      setSaving(null)
    }
  }

  const columns: DataTableColumn<DfirTask>[] = [
    {
      id: 'title',
      header: 'Lead',
      className: 'min-w-[180px] font-medium',
      cell: (t) => <span className={t.status === 'completed' ? 'text-muted-foreground' : ''}>{t.title}</span>,
    },
    {
      id: 'direction',
      header: 'Direction',
      hideBelow: 'md',
      className: 'max-w-[280px] text-xs text-muted-foreground',
      cell: (t) =>
        t.investigation_direction ? (
          <span className="line-clamp-2" title={t.investigation_direction}>
            {t.investigation_direction}
          </span>
        ) : (
          <span className="text-muted-foreground/60">—</span>
        ),
    },
    {
      id: 'outcome',
      header: 'Outcome',
      cell: (t) =>
        canUpdate ? (
          <Select
            value={t.lead_outcome || 'open'}
            onValueChange={(v) => void setOutcome(t, v)}
            disabled={saving === t.id}
          >
            <SelectTrigger aria-label={`Outcome of ${t.title}`} className="h-8 w-[170px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {OUTCOME_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <LeadOutcomeBadge outcome={t.lead_outcome} />
        ),
    },
    {
      id: 'status',
      header: 'Status',
      sortKey: 'status',
      hideBelow: 'sm',
      cell: (t) => (
        <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
          {STATUS_OPTIONS.find((s) => s.value === t.status)?.label ?? t.status}
        </Badge>
      ),
    },
    {
      id: 'evidence',
      header: 'Evidence',
      hideBelow: 'md',
      cell: (t) => {
        const ev = taskEvidence(t)
        return ev.length ? <EvidenceChips evidence={ev} onOpen={openEvidence} /> : <span className="text-xs text-muted-foreground/60">—</span>
      },
    },
    {
      id: 'owner',
      header: 'Owner',
      hideBelow: 'lg',
      cell: (t) =>
        t.assignee ? (
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <User className="h-3 w-3" /> {t.assignee.name}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground/60">Unassigned</span>
        ),
    },
    {
      id: 'updated',
      header: 'Updated',
      sortKey: 'updated_at',
      hideBelow: 'lg',
      className: 'whitespace-nowrap text-xs text-muted-foreground',
      cell: (t) => <Timestamp value={t.updated_at || t.created_at} seconds={false} />,
    },
  ]

  const activeOutcome = query.state.filters.lead_outcome

  return (
    <div className="space-y-3">
      <FocusNotice focusRowId={focusRowId} focusFound={query.focusFound} noun="lead" />
      {counts && (
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Leads by outcome">
          {OUTCOME_OPTIONS.map((o) => {
            const c = leadOutcomeColors[o.value]
            const active = activeOutcome === o.value
            return (
              <button
                key={o.value}
                type="button"
                aria-pressed={active}
                onClick={() => query.setFilter('lead_outcome', active ? undefined : o.value)}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors',
                  c.border,
                  active ? cn(c.bg, c.text) : 'bg-transparent text-muted-foreground hover:bg-white/5'
                )}
              >
                {o.label}
                <span className="tabular-nums font-medium">{counts[o.value] ?? 0}</span>
              </button>
            )
          })}
        </div>
      )}
      <DataTable
        query={query}
        columns={columns}
        getRowId={(t) => t.id}
        ariaLabel="Investigative leads"
        searchPlaceholder="Search leads..."
        toolbar={
          <>
            <FilterSelect
              label="Outcome"
              allLabel="All outcomes"
              value={activeOutcome}
              onChange={(v) => query.setFilter('lead_outcome', v)}
              options={OUTCOME_OPTIONS}
            />
            <FilterSelect
              label="Status"
              allLabel="All statuses"
              value={query.state.filters.status}
              onChange={(v) => query.setFilter('status', v)}
              options={STATUS_OPTIONS}
            />
            <UserPicker
              ariaLabel="Filter by owner"
              placeholder="Any owner"
              className="w-[200px]"
              value={query.state.filters.assignee_id ?? null}
              onChange={(id) => query.setFilter('assignee_id', id ?? undefined)}
            />
          </>
        }
        rowActions={onEdit ? (t) => [{ label: 'Edit', icon: Edit2, onSelect: () => onEdit(t), permission: 'tasks:update' }] : undefined}
        focusedRowId={focusRowId}
        empty={{
          title: 'No investigative leads',
          description: 'Create a task of type "Investigative Lead" to track a hypothesis and record its outcome.',
        }}
      />
    </div>
  )
}

/** `lead_counts` for the header; refreshed whenever the list reloads. */
function useLeadCounts(tasksEndpoint: string, reloadSignal: unknown): LeadCounts | null {
  const [counts, setCounts] = useState<LeadCounts | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    api
      .get<PaginatedResponse<DfirTask> & { lead_counts?: LeadCounts }>(
        withQuery(tasksEndpoint, {
          task_type: 'investigative_lead',
          include_comments: 'false',
          lead_counts: 'true',
          per_page: 1,
        }),
        { signal: controller.signal }
      )
      .then((res) => setCounts(res.lead_counts ?? null))
      .catch((err) => {
        if (!isAbortError(err)) setCounts(null)
      })
    return () => controller.abort()
  }, [tasksEndpoint, reloadSignal])
  return counts
}
