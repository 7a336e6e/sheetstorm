"use client"

/**
 * Improvement actions across the organization (W3-RT-POST,
 * `improvements:read`): filterable by status, priority, owner (me) and
 * overdue; status changes inline with If-Match. Actions outlive their
 * incident: once it is deleted the row shows the saved "#<n> <title>" label
 * instead of a link. `?id=<action>` (reminder links) lands on that row.
 */
import { Suspense, useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Pencil, Trash2 } from 'lucide-react'
import { DataTable, FilterSelect, type DataTableColumn, type RowAction } from '@/components/ui/data-table'
import { Button } from '@/components/ui/button'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { usePermission } from '@/components/auth/permission-gate'
import {
  ActionStatusSelect,
  DueCell,
  PriorityBadge,
  controlText,
} from '@/components/incidents/post-incident/ActionCells'
import { ImprovementActionDialog } from '@/components/incidents/post-incident/ImprovementActionDialog'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import { IMPROVEMENT_ACTIONS_ENDPOINT, postIncident } from '@/lib/endpoints/post-incident'
import { notifyError } from '@/lib/errors'
import { invalidate } from '@/lib/query-cache'
import { PRIORITY_OPTIONS, STATUS_OPTIONS } from '@/lib/post-incident'
import { useAuthStore } from '@/lib/store'
import type { ImprovementAction } from '@/types'

export default function ImprovementsPage() {
  return (
    <Suspense fallback={null}>
      <ImprovementsList />
    </Suspense>
  )
}

function ImprovementsList() {
  const focus = useSearchParams()?.get('id') ?? null
  const userId = useAuthStore((s) => s.user?.id)
  const canCreate = usePermission('improvements:create')
  const canUpdate = usePermission('improvements:update')
  const confirm = useConfirm()
  const query = usePaginatedQuery<ImprovementAction>({
    endpoint: IMPROVEMENT_ACTIONS_ENDPOINT,
    urlKey: 'ia',
    focus,
    live: 'improvement_action',
  })
  const [editing, setEditing] = useState<ImprovementAction | null>(null)

  const mayChange = (a: ImprovementAction) =>
    canUpdate && (canCreate || a.owner_id === userId || a.created_by === userId)

  const columns = useMemo<DataTableColumn<ImprovementAction>[]>(
    () => [
      {
        id: 'title',
        header: 'Action',
        sortKey: 'title',
        cell: (a) => (
          <div className="min-w-[14rem]">
            <div className="font-medium">{a.title}</div>
            {controlText(a) && <div className="text-xs text-muted-foreground">{controlText(a)}</div>}
          </div>
        ),
      },
      {
        id: 'incident',
        header: 'Incident',
        hideBelow: 'md',
        cell: (a) =>
          a.incident ? (
            <Link
              href={`/dashboard/incidents/${a.incident.id}?tab=review`}
              className="text-primary hover:underline"
            >
              #{a.incident.incident_number} {a.incident.title}
            </Link>
          ) : a.incident_ref ? (
            <span className="text-muted-foreground" title={a.incident_id ? undefined : 'This incident was deleted'}>
              {a.incident_ref}
              {!a.incident_id && ' (deleted)'}
            </span>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        id: 'owner',
        header: 'Owner',
        hideBelow: 'md',
        cell: (a) => a.owner?.name ?? <span className="text-muted-foreground">Unassigned</span>,
      },
      { id: 'priority', header: 'Priority', sortKey: 'priority', hideBelow: 'sm', cell: (a) => <PriorityBadge priority={a.priority} /> },
      { id: 'due', header: 'Due', sortKey: 'due_date', cell: (a) => <DueCell action={a} /> },
      {
        id: 'status',
        header: 'Status',
        sortKey: 'status',
        cell: (a) => <ActionStatusSelect action={a} canChange={mayChange(a)} />,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canUpdate, canCreate, userId]
  )

  const rowActions = (a: ImprovementAction): RowAction[] => [
    {
      label: 'Edit',
      icon: Pencil,
      permission: 'improvements:update',
      disabled: !mayChange(a),
      onSelect: () => setEditing(a),
    },
    {
      label: 'Delete',
      icon: Trash2,
      destructive: true,
      permission: 'improvements:delete',
      onSelect: async () => {
        if (!(await confirmDelete(confirm, 'improvement action', a.title))) return
        try {
          await postIncident.deleteAction(a.id, a.version)
          invalidate(IMPROVEMENT_ACTIONS_ENDPOINT)
        } catch (err) {
          notifyError(err, 'delete the improvement action')
        }
      },
    },
  ]

  const filters = query.state.filters
  const toggle = (name: string, on: boolean) => query.setFilter(name, on ? 'true' : undefined)

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Improvement actions</h1>
        <p className="text-sm text-muted-foreground">
          Follow-ups from post-incident reviews, across every incident you can access.
        </p>
      </div>
      <DataTable<ImprovementAction>
        query={query}
        columns={columns}
        getRowId={(a) => a.id}
        ariaLabel="Improvement actions"
        searchPlaceholder="Search actions…"
        focusedRowId={focus}
        rowActions={rowActions}
        toolbar={
          <>
            <FilterSelect
              label="Status"
              allLabel="All statuses"
              value={filters.status}
              onChange={(v) => query.setFilter('status', v)}
              options={STATUS_OPTIONS}
            />
            <FilterSelect
              label="Priority"
              allLabel="All priorities"
              value={filters.priority}
              onChange={(v) => query.setFilter('priority', v)}
              options={PRIORITY_OPTIONS}
            />
            <Button
              variant={filters.owner_id === 'me' ? 'default' : 'outline'}
              size="sm"
              aria-pressed={filters.owner_id === 'me'}
              onClick={() => query.setFilter('owner_id', filters.owner_id === 'me' ? undefined : 'me')}
            >
              Mine
            </Button>
            <Button
              variant={filters.overdue === 'true' ? 'default' : 'outline'}
              size="sm"
              aria-pressed={filters.overdue === 'true'}
              onClick={() => toggle('overdue', filters.overdue !== 'true')}
            >
              Overdue
            </Button>
          </>
        }
        empty={{
          title: 'No improvement actions',
          description: 'Actions added in an incident’s Post-Incident Review tab appear here.',
        }}
      />
      <ImprovementActionDialog
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
        incidentId={editing?.incident_id ?? null}
        action={editing}
      />
    </div>
  )
}
