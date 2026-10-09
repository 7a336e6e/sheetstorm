'use client'

/**
 * Invites of the org (`GET /users/invites`), pending by default. Revoke a
 * pending invite; re-issue any invite (a new one-time link that supersedes a
 * pending one for the same email). Requires users:manage.
 */
import { useMemo } from 'react'
import { Ban, RotateCw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { DataTable, type DataTableColumn, type RowAction } from '@/components/ui/data-table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Timestamp } from '@/components/ui/timestamp'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import { notifySuccess } from '@/lib/errors'
import { invalidate } from '@/lib/query-cache'
import { INVITES_ENDPOINT, usersAdmin } from '@/lib/endpoints/users-admin'
import type { InviteStatus, InviteStatusFilter, UserInvite } from '@/types'
import { notifyUserError } from './lifecycle-errors'
import type { InvitePrefill } from './InviteUserModal'

const STATUS_OPTIONS: { value: InviteStatusFilter; label: string }[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'expired', label: 'Expired' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'revoked', label: 'Revoked' },
  { value: 'all', label: 'All invites' },
]

const STATUS_VARIANT: Record<InviteStatus, 'info' | 'warning' | 'success' | 'default'> = {
  pending: 'info',
  expired: 'warning',
  accepted: 'success',
  revoked: 'default',
}

export function PendingInvitesTable({
  onReissue,
  onChanged,
}: {
  onReissue: (prefill: InvitePrefill) => void
  /** After a revoke (stats refresh). */
  onChanged?: () => void
}) {
  const confirm = useConfirm()
  const query = usePaginatedQuery<UserInvite>({
    endpoint: INVITES_ENDPOINT,
    urlKey: 'inv',
    defaults: { perPage: 25, sort: '-created_at' },
  })
  const status = (query.state.filters.status as InviteStatusFilter | undefined) ?? 'pending'

  const revoke = async (inv: UserInvite) => {
    const ok = await confirm({
      title: 'Revoke invite?',
      description: `The link sent to ${inv.email} stops working immediately.`,
      confirmLabel: 'Revoke',
      variant: 'destructive',
    })
    if (!ok) return
    try {
      await usersAdmin.invites.revoke(inv.id)
      notifySuccess('Invite revoked', inv.email)
      invalidate(INVITES_ENDPOINT)
      onChanged?.()
    } catch (err) {
      notifyUserError(err, 'revoke the invite')
    }
  }

  const columns = useMemo<DataTableColumn<UserInvite>[]>(
    () => [
      {
        id: 'email',
        header: 'Email',
        sortKey: 'email',
        cell: (i) => (
          <div className="min-w-0">
            <p className="truncate font-medium text-foreground">{i.email}</p>
            {i.name && <p className="truncate text-xs text-muted-foreground">{i.name}</p>}
          </div>
        ),
      },
      {
        id: 'roles',
        header: 'Roles',
        hideBelow: 'md',
        cell: (i) =>
          i.roles.length ? (
            <div className="flex flex-wrap gap-1">
              {i.roles.map((r) => (
                <Badge key={r.id} variant="outline">
                  {r.name}
                </Badge>
              ))}
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">Viewer (default)</span>
          ),
      },
      {
        id: 'teams',
        header: 'Teams',
        hideBelow: 'lg',
        cell: (i) =>
          i.teams.length ? (
            <span className="text-sm text-muted-foreground">{i.teams.map((t) => t.name).join(', ')}</span>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        id: 'status',
        header: 'Status',
        cell: (i) => (
          <Badge variant={STATUS_VARIANT[i.status]}>{i.status === 'pending' ? 'Pending invite' : i.status}</Badge>
        ),
      },
      {
        id: 'expires',
        header: 'Expires',
        sortKey: 'expires_at',
        hideBelow: 'sm',
        cell: (i) => <Timestamp value={i.expires_at} seconds={false} className="text-sm text-muted-foreground" />,
      },
      {
        id: 'by',
        header: 'Invited by',
        hideBelow: 'lg',
        cell: (i) => <span className="text-sm text-muted-foreground">{i.created_by?.name ?? '—'}</span>,
      },
      {
        id: 'created',
        header: 'Created',
        sortKey: 'created_at',
        hideBelow: 'md',
        cell: (i) => <Timestamp value={i.created_at} seconds={false} className="text-sm text-muted-foreground" />,
      },
    ],
    []
  )

  const rowActions = (i: UserInvite): RowAction[] => [
    {
      label: 'Re-issue link',
      icon: RotateCw,
      permission: 'users:manage',
      disabled: i.status === 'accepted',
      onSelect: () =>
        onReissue({
          email: i.email,
          name: i.name,
          role_ids: i.role_ids,
          team_ids: i.team_ids,
          organizational_role: i.organizational_role,
        }),
    },
    ...(i.status === 'pending'
      ? [
          {
            label: 'Revoke',
            icon: Ban,
            destructive: true,
            permission: 'users:manage',
            onSelect: () => void revoke(i),
          } satisfies RowAction,
        ]
      : []),
  ]

  return (
    <DataTable
      query={query}
      columns={columns}
      getRowId={(i) => i.id}
      ariaLabel="Invites"
      searchPlaceholder="Search invites…"
      toolbar={
        <Select value={status} onValueChange={(v) => query.setFilter('status', v === 'pending' ? undefined : v)}>
          <SelectTrigger aria-label="Invite status" className="h-9 w-[160px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
      rowActions={rowActions}
      pageSizes={[25, 50, 100]}
      empty={{ title: 'No pending invites', description: 'Invite users to send them a one-time join link.' }}
    />
  )
}
