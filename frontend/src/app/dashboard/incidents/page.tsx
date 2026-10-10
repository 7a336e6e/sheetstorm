"use client"

/**
 * Incidents list: server-paged DataTable (`GET /incidents`), with search,
 * status/severity filters and sort mirrored in the URL (`inc.*` params).
 * Gating is by permission: create = `incidents:create`, archive =
 * `incidents:archive` (cosmetic; the backend decorators stay authoritative).
 */
import { Suspense, useMemo } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Archive } from 'lucide-react'
import { DataTable, FilterSelect, type DataTableColumn, type RowAction } from '@/components/ui/data-table'
import { SeverityBadge, StatusBadge, PhaseBadge } from '@/components/ui/badge'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import { useIncidentStore } from '@/lib/store'
import { notifyError, notifySuccess } from '@/lib/errors'
import { formatRelativeTime } from '@/lib/utils'
import type { Incident } from '@/types'

const INCIDENT_STATUS_OPTIONS = [
  { value: 'open', label: 'Open' },
  { value: 'contained', label: 'Contained' },
  { value: 'eradicated', label: 'Eradicated' },
  { value: 'recovered', label: 'Recovered' },
  { value: 'closed', label: 'Closed' },
]

const INCIDENT_SEVERITY_OPTIONS = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
]

const href = (i: Incident) => `/dashboard/incidents/${i.id}`

function IncidentsList() {
  const router = useRouter()
  const confirm = useConfirm()
  const archiveIncident = useIncidentStore((s) => s.archiveIncident)

  const query = usePaginatedQuery<Incident>({
    endpoint: '/incidents',
    urlKey: 'inc',
    defaults: { sort: '-created_at' },
    live: 'incident',
  })

  const handleArchive = async (incident: Incident) => {
    const ok = await confirm({
      title: 'Archive incident',
      description: `Archive #${incident.incident_number} "${incident.title}"? It is hidden from every list and can be restored from Archived Incidents.`,
      confirmLabel: 'Archive',
      variant: 'destructive',
    })
    if (!ok) return
    try {
      await archiveIncident(incident.id)
      notifySuccess('Incident archived', `#${incident.incident_number} was moved to the archive.`)
    } catch (err) {
      notifyError(err, 'archive the incident')
    }
  }

  const columns = useMemo<DataTableColumn<Incident>[]>(
    () => [
      {
        id: 'number',
        header: 'ID',
        sortKey: 'incident_number',
        className: 'w-[90px]',
        cell: (i) => <span className="font-mono text-sm text-muted-foreground">#{i.incident_number}</span>,
      },
      {
        id: 'title',
        header: 'Incident',
        sortKey: 'title',
        cell: (i) => (
          <div className="min-w-0">
            <Link
              href={href(i)}
              tabIndex={-1}
              onClick={(e) => e.stopPropagation()}
              className="block truncate font-medium text-foreground hover:text-cyan-400"
            >
              {i.title}
            </Link>
            {i.counts && (
              <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                <span>{i.counts.timeline_events} events</span>
                <span>{i.counts.compromised_hosts} hosts</span>
                <span>{i.counts.tasks} tasks</span>
              </div>
            )}
          </div>
        ),
      },
      {
        id: 'severity',
        header: 'Severity',
        sortKey: 'severity',
        className: 'w-[120px]',
        cell: (i) => <SeverityBadge severity={i.severity} />,
      },
      {
        id: 'status',
        header: 'Status',
        sortKey: 'status',
        className: 'w-[120px]',
        cell: (i) => <StatusBadge status={i.status} />,
      },
      {
        id: 'phase',
        header: 'Phase',
        sortKey: 'phase',
        className: 'w-[180px]',
        hideBelow: 'md',
        cell: (i) => <PhaseBadge phase={i.phase} />,
      },
      {
        id: 'created',
        header: 'Created',
        sortKey: 'created_at',
        className: 'w-[160px]',
        hideBelow: 'sm',
        cell: (i) => (
          <div>
            <span className="text-sm text-muted-foreground">{formatRelativeTime(i.created_at)}</span>
            {i.lead_responder && <p className="mt-0.5 text-xs text-muted-foreground">{i.lead_responder.name}</p>}
            {i.teams && i.teams.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {i.teams.map((team) => (
                  <span
                    key={team.id}
                    className="rounded border border-blue-500/20 bg-blue-500/10 px-1.5 py-0.5 text-[10px] text-blue-400"
                  >
                    {team.name}
                  </span>
                ))}
              </div>
            )}
          </div>
        ),
      },
    ],
    []
  )

  const rowActions = (i: Incident): RowAction[] => [
    {
      label: 'Archive',
      icon: Archive,
      destructive: true,
      permission: 'incidents:archive',
      onSelect: () => void handleArchive(i),
    },
  ]

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground lg:text-3xl">Incidents</h1>
        <p className="mt-1 text-muted-foreground">Manage and track security incidents</p>
      </div>

      <div data-tour="incidents-table">
      <DataTable
        query={query}
        columns={columns}
        getRowId={(i) => i.id}
        ariaLabel="Incidents"
        searchPlaceholder="Search title, description or number…"
        toolbar={
          <>
            <FilterSelect
              label="Statuses"
              value={query.state.filters.status}
              onChange={(v) => query.setFilter('status', v)}
              options={INCIDENT_STATUS_OPTIONS}
            />
            <FilterSelect
              label="Severities"
              value={query.state.filters.severity}
              onChange={(v) => query.setFilter('severity', v)}
              options={INCIDENT_SEVERITY_OPTIONS}
            />
          </>
        }
        primaryAction={{
          label: 'New incident',
          permission: 'incidents:create',
          onSelect: () => router.push('/dashboard/incidents/new'),
        }}
        rowActions={rowActions}
        onRowClick={(i) => router.push(href(i))}
        empty={{
          title: 'No incidents yet',
          description: 'Incidents you create or are assigned to appear here.',
        }}
      />
      </div>
    </div>
  )
}

export default function IncidentsPage() {
  return (
    <Suspense fallback={null}>
      <IncidentsList />
    </Suspense>
  )
}
