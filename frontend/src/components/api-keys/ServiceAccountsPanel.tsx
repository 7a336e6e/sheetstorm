"use client"

/**
 * Service accounts of the organization (needs `api_keys:manage`): create with
 * roles under your ceiling, edit name / roles, create a key for one, and
 * disable / re-enable. Disabling revokes every key of the account and ends
 * its sessions (server side); the row stays for audit attribution.
 */
import { useState } from 'react'
import { KeyRound, Pencil, Plus, Power, PowerOff } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DataTable, FilterSelect, type DataTableColumn, type RowAction } from '@/components/ui/data-table'
import { Timestamp } from '@/components/ui/timestamp'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import {
  API_KEYS_ENDPOINT,
  SERVICE_ACCOUNTS_ENDPOINT,
  notifyApiKeyError,
  serviceAccounts,
} from '@/lib/endpoints/api-keys'
import { notifySuccess } from '@/lib/errors'
import { invalidate } from '@/lib/query-cache'
import type { ServiceAccount } from '@/types'
import { ServiceAccountDialog } from './ServiceAccountDialog'

const ACTIVE_OPTIONS = [
  { value: 'true', label: 'Active' },
  { value: 'false', label: 'Disabled' },
]

export function ServiceAccountsPanel({
  onCreateKey,
  urlKey,
}: {
  /** Open the create-key dialog for this account. */
  onCreateKey?: (account: ServiceAccount) => void
  urlKey?: string
}) {
  const confirm = useConfirm()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<ServiceAccount | null>(null)

  const query = usePaginatedQuery<ServiceAccount>({
    endpoint: SERVICE_ACCOUNTS_ENDPOINT,
    urlKey,
    defaults: { perPage: 25, sort: 'name' },
  })

  const refresh = () => {
    invalidate(SERVICE_ACCOUNTS_ENDPOINT)
    invalidate(API_KEYS_ENDPOINT)
  }

  const setActive = async (account: ServiceAccount, active: boolean) => {
    if (!active) {
      const ok = await confirm({
        title: `Disable ${account.name}?`,
        description: `Every API key of this service account is revoked now (${account.active_key_count} active). Re-enabling the account does not restore them.`,
        confirmLabel: 'Disable',
        variant: 'destructive',
      })
      if (!ok) return
    }
    try {
      await serviceAccounts.update(account.id, { is_active: active })
      refresh()
      notifySuccess(active ? 'Service account enabled' : 'Service account disabled', account.name)
    } catch (err) {
      notifyApiKeyError(err, active ? 'enable the service account' : 'disable the service account')
    }
  }

  const columns: DataTableColumn<ServiceAccount>[] = [
    {
      id: 'name',
      header: 'Name',
      sortKey: 'name',
      cell: (a) => <span className="font-medium">{a.name}</span>,
    },
    {
      id: 'roles',
      header: 'Roles',
      hideBelow: 'md',
      cell: (a) =>
        a.roles.length ? (
          <div className="flex flex-wrap gap-1">
            {a.roles.map((r) => (
              <Badge key={r.id} variant="outline">
                {r.name}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">None</span>
        ),
    },
    {
      id: 'keys',
      header: 'Active keys',
      cell: (a) => <span className="tabular-nums">{a.active_key_count}</span>,
    },
    {
      id: 'created',
      header: 'Created',
      sortKey: 'created_at',
      hideBelow: 'lg',
      cell: (a) => <Timestamp value={a.created_at} seconds={false} className="text-xs" />,
    },
    {
      id: 'status',
      header: 'Status',
      cell: (a) => (
        <Badge variant={a.is_active ? 'recovered' : 'default'}>{a.is_active ? 'Active' : 'Disabled'}</Badge>
      ),
    },
  ]

  const rowActions = (a: ServiceAccount): RowAction[] => [
    ...(a.is_active && onCreateKey
      ? [{ label: 'Create key', icon: KeyRound, onSelect: () => onCreateKey(a) } satisfies RowAction]
      : []),
    {
      label: 'Edit',
      icon: Pencil,
      onSelect: () => {
        setEditing(a)
        setDialogOpen(true)
      },
    },
    a.is_active
      ? { label: 'Disable', icon: PowerOff, destructive: true, onSelect: () => void setActive(a, false) }
      : { label: 'Enable', icon: Power, onSelect: () => void setActive(a, true) },
  ]

  return (
    <>
      <DataTable<ServiceAccount>
        query={query}
        columns={columns}
        getRowId={(a) => a.id}
        ariaLabel="Service accounts"
        searchPlaceholder="Search service accounts"
        toolbar={
          <>
            <FilterSelect
              label="Status"
              value={query.state.filters.is_active}
              onChange={(v) => query.setFilter('is_active', v)}
              options={ACTIVE_OPTIONS}
            />
            {/* A plain button, not the table's `n` primary action: the keys table next to it owns that. */}
            <Button
              size="sm"
              className="ml-auto"
              onClick={() => {
                setEditing(null)
                setDialogOpen(true)
              }}
            >
              <Plus className="h-4 w-4" />
              Create service account
            </Button>
          </>
        }
        rowActions={rowActions}
        empty={{
          title: 'No service accounts',
          description: 'A service account owns API keys for automation and outlives any one person.',
        }}
      />
      <ServiceAccountDialog
        open={dialogOpen}
        account={editing}
        onOpenChange={setDialogOpen}
        onSaved={(account, created) => {
          refresh()
          notifySuccess(created ? 'Service account created' : 'Service account updated', account.name)
        }}
      />
    </>
  )
}
