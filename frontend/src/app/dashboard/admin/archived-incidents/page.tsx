"use client"

import { Suspense, useMemo } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Card, CardContent } from '@/components/ui/card'
import { SeverityBadge, StatusBadge } from '@/components/ui/badge'
import { DataTable, FilterSelect, type DataTableColumn, type RowAction } from '@/components/ui/data-table'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import { useIncidentStore } from '@/lib/store'
import { notifyError, notifySuccess } from '@/lib/errors'
import { formatRelativeTime } from '@/lib/utils'
import type { Incident } from '@/types'
import { ArchiveRestore, Eye, Trash2, AlertTriangle } from 'lucide-react'
import { useConfirm } from '@/components/ui/confirm-dialog'

type ArchivedIncident = Incident & { archived_at?: string | null }

const SEVERITY_OPTIONS = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
]

export default function ArchivedIncidentsPage() {
  return (
    <Suspense fallback={null}>
      <ArchivedIncidentsList />
    </Suspense>
  )
}

function ArchivedIncidentsList() {
  const { unarchiveIncident, permanentDeleteIncident } = useIncidentStore()
  const confirm = useConfirm()
  const router = useRouter()

  const query = usePaginatedQuery<ArchivedIncident>({
    endpoint: '/incidents/archived',
    urlKey: 'arch',
    defaults: { sort: '-archived_at' },
  })

  const handleRestore = async (id: string) => {
    const confirmed = await confirm({
      title: 'Restore Incident',
      description: 'This will restore the incident and make it visible again to all users with access.',
      confirmLabel: 'Restore',
    })
    if (!confirmed) return

    try {
      await unarchiveIncident(id)
      notifySuccess("Incident Restored", "The incident has been restored from the archive.")
    } catch (error) {
      notifyError(error, 'restore the incident')
    }
  }

  const handlePermanentDelete = async (id: string) => {
    const confirmed = await confirm({
      title: 'Permanently Delete Incident',
      description: 'WARNING: This action is irreversible. All data associated with this incident — including timeline events, IOCs, compromised assets, case notes, artifacts, tasks, and reports — will be permanently destroyed. This may have legal and compliance implications. Ensure you have exported any required data before proceeding.',
      confirmLabel: 'Permanently Delete',
      variant: 'destructive',
    })
    if (!confirmed) return

    try {
      await permanentDeleteIncident(id)
      notifySuccess("Incident Permanently Deleted", "The incident and all associated data have been permanently destroyed.")
    } catch (error) {
      notifyError(error, 'permanently delete the incident')
    }
  }

  const columns = useMemo<DataTableColumn<ArchivedIncident>[]>(
    () => [
      {
        id: 'number',
        header: 'ID',
        sortKey: 'incident_number',
        className: 'w-[100px]',
        cell: (i) => <span className="font-mono text-sm text-muted-foreground">#{i.incident_number}</span>,
      },
      {
        id: 'title',
        header: 'Incident',
        sortKey: 'title',
        cell: (i) => (
          <div className="min-w-0">
            <Link
              href={`/dashboard/incidents/${i.id}`}
              className="block truncate font-medium text-foreground hover:text-primary hover:underline"
            >
              {i.title}
            </Link>
            {i.description && (
              <p className="mt-0.5 max-w-[400px] truncate text-xs text-muted-foreground">{i.description}</p>
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
        hideBelow: 'sm',
        cell: (i) => <StatusBadge status={i.status} />,
      },
      {
        id: 'archived',
        header: 'Archived',
        sortKey: 'archived_at',
        className: 'w-[140px]',
        hideBelow: 'sm',
        cell: (i) => (
          <span className="text-sm text-muted-foreground">
            {formatRelativeTime(i.archived_at || i.updated_at || i.created_at)}
          </span>
        ),
      },
    ],
    []
  )

  const rowActions = (i: ArchivedIncident): RowAction[] => [
    {
      label: 'Open (read-only)',
      icon: Eye,
      permission: 'incidents:archive',
      onSelect: () => router.push(`/dashboard/incidents/${i.id}`),
    },
    {
      label: 'Restore',
      icon: ArchiveRestore,
      permission: 'incidents:archive',
      onSelect: () => void handleRestore(i.id),
    },
    {
      label: 'Permanently delete',
      icon: Trash2,
      destructive: true,
      permission: 'incidents:purge',
      onSelect: () => void handlePermanentDelete(i.id),
    },
  ]

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold text-foreground">Archived Incidents</h1>
          <p className="text-muted-foreground mt-1">View and restore archived incidents. Requires the Archive incidents permission; permanent deletion also requires Permanently delete incidents.</p>
        </div>
      </div>

      {/* Warning Banner */}
      <Card className="border-amber-500/30 bg-amber-500/5">
        <CardContent className="p-4 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium text-amber-500">Archive Management</p>
            <p className="text-muted-foreground mt-1">
              Archived incidents are hidden from all users. Restoring an incident will make it visible again.
              Permanent deletion is irreversible and may have legal implications.
            </p>
          </div>
        </CardContent>
      </Card>

      <DataTable
        query={query}
        columns={columns}
        getRowId={(i) => i.id}
        ariaLabel="Archived incidents"
        searchPlaceholder="Search archived incidents…"
        toolbar={
          <FilterSelect
            label="Severities"
            value={query.state.filters.severity}
            onChange={(v) => query.setFilter('severity', v)}
            options={SEVERITY_OPTIONS}
          />
        }
        rowActions={rowActions}
        empty={{ title: 'No archived incidents', description: 'Archived incidents will appear here.' }}
      />
    </div>
  )
}
