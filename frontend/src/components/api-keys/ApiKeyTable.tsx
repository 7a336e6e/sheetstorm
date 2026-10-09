"use client"

/**
 * API keys as a server-paged DataTable (search, status filter, sorting).
 *
 * `scope="mine"` lists the caller's own keys (`?mine=true`); `scope="org"`
 * lists every key of the organization (needs `api_keys:manage`, otherwise the
 * server narrows the list to the caller's keys anyway). Row actions follow the
 * server rules: your own key needs `api_keys:own` (or manage); with
 * `api_keys:manage` any key can be revoked but only a service account's can
 * be rotated. Cosmetic; the backend answers 403/404 otherwise.
 */
import { RefreshCw, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { DataTable, FilterSelect, type DataTableColumn, type RowAction } from '@/components/ui/data-table'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermission } from '@/components/auth/permission-gate'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import { API_KEYS_ENDPOINT, daysUntil, expiresSoon } from '@/lib/endpoints/api-keys'
import { useAuthStore } from '@/lib/store'
import type { ApiKey, ApiKeyStatus } from '@/types'

export type ApiKeyTableScope = 'mine' | 'org'

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'expired', label: 'Expired' },
  { value: 'revoked', label: 'Revoked' },
]

const STATUS_VARIANT: Record<ApiKeyStatus, 'recovered' | 'high' | 'default'> = {
  active: 'recovered',
  expired: 'high',
  revoked: 'default',
}

/** An active key whose revocation is scheduled (rotation with a grace period). */
export function isRotatingOut(key: Pick<ApiKey, 'status' | 'revoked_at'>): boolean {
  return key.status === 'active' && !!key.revoked_at
}

function StatusBadge({ apiKey }: { apiKey: ApiKey }) {
  if (isRotatingOut(apiKey)) {
    return (
      <Badge variant="contained" title={`Stops working at ${new Date(apiKey.revoked_at!).toISOString()}`}>
        Rotating out
      </Badge>
    )
  }
  return (
    <Badge variant={STATUS_VARIANT[apiKey.status]} title={apiKey.revoked_reason ?? undefined}>
      {apiKey.status === 'active' ? 'Active' : apiKey.status === 'expired' ? 'Expired' : 'Revoked'}
    </Badge>
  )
}

function ExpiryCell({ apiKey }: { apiKey: ApiKey }) {
  const days = daysUntil(apiKey.expires_at)
  return (
    <div className="flex flex-col items-start gap-1">
      <Timestamp value={apiKey.expires_at} seconds={false} className="text-xs" />
      {expiresSoon(apiKey) && days !== null && (
        <Badge variant="high">{days <= 0 ? 'Expires today' : `Expires in ${days} ${days === 1 ? 'day' : 'days'}`}</Badge>
      )}
    </div>
  )
}

export function ApiKeyDetails({ apiKey }: { apiKey: ApiKey }) {
  return (
    <dl className="grid gap-x-6 gap-y-2 text-xs sm:grid-cols-2">
      {apiKey.description && (
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground">Description</dt>
          <dd>{apiKey.description}</dd>
        </div>
      )}
      <div className="sm:col-span-2">
        <dt className="text-muted-foreground">Scopes ({apiKey.scopes.length})</dt>
        <dd className="mt-1 flex flex-wrap gap-1">
          {apiKey.scopes.map((s) => (
            <code key={s} className="rounded border border-border bg-muted/40 px-1.5 py-0.5 font-mono">
              {s}
            </code>
          ))}
        </dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Used</dt>
        <dd>
          {apiKey.use_count} {apiKey.use_count === 1 ? 'time' : 'times'}
          {apiKey.last_used_ip && <span className="font-mono"> · last from {apiKey.last_used_ip}</span>}
        </dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Created</dt>
        <dd>
          <Timestamp value={apiKey.created_at} />
        </dd>
      </div>
      {apiKey.revoked_at && (
        <div>
          <dt className="text-muted-foreground">{apiKey.status === 'revoked' ? 'Revoked' : 'Revokes at'}</dt>
          <dd>
            <Timestamp value={apiKey.revoked_at} />
            {apiKey.revoked_reason && <span> · {apiKey.revoked_reason}</span>}
          </dd>
        </div>
      )}
      {apiKey.rotated_from_id && (
        <div>
          <dt className="text-muted-foreground">Rotated from</dt>
          <dd className="font-mono">{apiKey.rotated_from_id}</dd>
        </div>
      )}
    </dl>
  )
}

export function ApiKeyTable({
  scope,
  onCreate,
  onRotate,
  onRevoke,
  urlKey,
  className,
}: {
  scope: ApiKeyTableScope
  /** Shows the create button (and the `n` shortcut) when set. */
  onCreate?: () => void
  onRotate: (key: ApiKey) => void
  onRevoke: (key: ApiKey) => void
  urlKey?: string
  className?: string
}) {
  const me = useAuthStore((s) => s.user?.id)
  const canOwn = usePermission('api_keys:own')
  const canManage = usePermission('api_keys:manage')
  const org = scope === 'org'

  const query = usePaginatedQuery<ApiKey>({
    endpoint: scope === 'mine' ? `${API_KEYS_ENDPOINT}?mine=true` : API_KEYS_ENDPOINT,
    urlKey,
    defaults: { perPage: 25, sort: '-created_at' },
  })

  /** Server rules. Revoke: your own key (own|manage) or, with manage, any key of the org. */
  const canRevoke = (key: ApiKey): boolean => (key.owner_user_id === me ? canOwn || canManage : canManage)
  /** Rotate: your own key, or (manage) a service account's; a person's key is revoked instead. */
  const canRotate = (key: ApiKey): boolean =>
    key.owner_user_id === me ? canOwn || canManage : canManage && key.owner?.is_service_account === true

  const columns: DataTableColumn<ApiKey>[] = [
    {
      id: 'name',
      header: 'Name',
      sortKey: 'name',
      cell: (k) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{k.name}</p>
          <p className="font-mono text-xs text-muted-foreground">{k.prefix}</p>
        </div>
      ),
    },
    ...(org
      ? [
          {
            id: 'owner',
            header: 'Owner',
            hideBelow: 'md',
            cell: (k) => (
              <div className="flex items-center gap-1.5 text-sm">
                <span className="truncate">{k.owner?.name ?? '—'}</span>
                {k.owner?.is_service_account && <Badge variant="outline">Service</Badge>}
              </div>
            ),
          } satisfies DataTableColumn<ApiKey>,
        ]
      : []),
    {
      id: 'scopes',
      header: 'Scopes',
      hideBelow: 'md',
      cell: (k) => (
        <span className="tabular-nums" title={k.scopes.join(', ')}>
          {k.scopes.length}
        </span>
      ),
    },
    {
      id: 'expires',
      header: 'Expires',
      sortKey: 'expires_at',
      cell: (k) => <ExpiryCell apiKey={k} />,
    },
    {
      id: 'last_used',
      header: 'Last used',
      sortKey: 'last_used_at',
      hideBelow: 'lg',
      cell: (k) =>
        k.last_used_at ? (
          <div className="text-xs">
            <Timestamp value={k.last_used_at} seconds={false} />
            {k.last_used_ip && <p className="font-mono text-muted-foreground">{k.last_used_ip}</p>}
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">Never</span>
        ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (k) => <StatusBadge apiKey={k} />,
    },
  ]

  const rowActions = (k: ApiKey): RowAction[] => {
    if (k.status === 'revoked') return []
    const actions: RowAction[] = []
    if (k.status === 'active' && !isRotatingOut(k) && canRotate(k)) {
      actions.push({ label: 'Rotate', icon: RefreshCw, onSelect: () => onRotate(k) })
    }
    if (canRevoke(k)) {
      actions.push({ label: 'Revoke', icon: Trash2, destructive: true, onSelect: () => onRevoke(k) })
    }
    return actions
  }

  return (
    <DataTable<ApiKey>
      className={className}
      query={query}
      columns={columns}
      getRowId={(k) => k.id}
      ariaLabel={org ? 'API keys of the organization' : 'My API keys'}
      searchPlaceholder="Search by name or prefix"
      toolbar={
        <FilterSelect
          label="Status"
          value={query.state.filters.status}
          onChange={(v) => query.setFilter('status', v)}
          options={STATUS_OPTIONS}
        />
      }
      primaryAction={onCreate ? { label: 'Create API key', onSelect: onCreate, permission: [] } : undefined}
      rowActions={rowActions}
      renderExpanded={(k) => <ApiKeyDetails apiKey={k} />}
      empty={{
        title: 'No API keys',
        description: org
          ? 'Keys created by you and by service accounts appear here.'
          : 'Create a key to give a script or an MCP client scoped access.',
      }}
    />
  )
}
