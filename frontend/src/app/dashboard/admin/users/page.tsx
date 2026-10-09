'use client'

/**
 * Users admin: org-wide stats, a server-paged user list (filters, sort and
 * paging in the URL), per-user lifecycle actions, bulk actions and invites.
 *
 * Every action is permission-gated (cosmetic; the backend enforces it):
 * users:create (Add), users:update (Edit), users:manage (Invite, Sync,
 * Disable/Enable, Force logout, Unlock, Reset password/MFA, bulk, invites),
 * users:delete (Delete), roles:manage (role bulk actions). Account actions are
 * never offered on your own row (backend self rules).
 */
import { Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import {
  Cloud,
  Eye,
  KeyRound,
  Loader2,
  LogOut,
  Mail,
  Pencil,
  ShieldOff,
  Trash2,
  Unlock,
  UserCheck,
  UserPlus,
  UserX,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge, RoleBadge } from '@/components/ui/badge'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DataTable, FilterSelect, type DataTableColumn, type RowAction } from '@/components/ui/data-table'
import { Timestamp } from '@/components/ui/timestamp'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { usePermission } from '@/components/auth/permission-gate'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import { api, isApiError } from '@/lib/api'
import { describeError, notifySuccess } from '@/lib/errors'
import { invalidate } from '@/lib/query-cache'
import { rbac } from '@/lib/endpoints/rbac'
import { USERS_ENDPOINT, usersAdmin } from '@/lib/endpoints/users-admin'
import { useAuthStore } from '@/lib/store'
import type { AdminUser, BulkUserResponse, Role, Team, UserStats } from '@/types'
import { AddUserModal } from '@/components/users/AddUserModal'
import { EditUserModal } from '@/components/users/EditUserModal'
import { InviteUserModal, type InvitePrefill } from '@/components/users/InviteUserModal'
import { PendingInvitesTable } from '@/components/users/PendingInvitesTable'
import { DisableUserDialog } from '@/components/users/DisableUserDialog'
import { ResetPasswordDialog } from '@/components/users/ResetPasswordDialog'
import { BulkActionBar, BulkResultDialog } from '@/components/users/BulkActionBar'
import { UserDetailDrawer } from '@/components/users/UserDetailDrawer'
import { UserStatusBadges } from '@/components/users/UserStatusBadges'
import { notifyUserError } from '@/components/users/lifecycle-errors'

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'disabled', label: 'Disabled' },
  { value: 'locked', label: 'Locked' },
  { value: 'must_change_password', label: 'Must change password' },
]

const MFA_OPTIONS = [
  { value: 'true', label: 'MFA on' },
  { value: 'false', label: 'MFA off' },
]

export default function UsersPage() {
  return (
    <Suspense fallback={null}>
      <UsersAdmin />
    </Suspense>
  )
}

function StatCard({ label, value, hint }: { label: string; value: number | undefined; hint?: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription title={hint}>{label}</CardDescription>
        <CardTitle className="text-2xl tabular-nums">{value ?? '—'}</CardTitle>
      </CardHeader>
    </Card>
  )
}

function UsersAdmin() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const confirm = useConfirm()
  const me = useAuthStore((s) => s.user)

  const canCreate = usePermission('users:create')
  const canManage = usePermission('users:manage')

  const tab = searchParams.get('tab') === 'invites' && canManage ? 'invites' : 'users'
  const setTab = (next: string) => {
    const params = new URLSearchParams(searchParams.toString())
    if (next === 'invites') params.set('tab', 'invites')
    else params.delete('tab')
    const qs = params.toString()
    router.replace(`${pathname}${qs ? `?${qs}` : ''}`, { scroll: false })
  }

  // ── Reference data and stats ────────────────────────────────────────
  const [roles, setRoles] = useState<Role[]>([])
  const [teams, setTeams] = useState<Team[]>([])
  const [stats, setStats] = useState<UserStats | null>(null)
  const [statsVersion, setStatsVersion] = useState(0)

  useEffect(() => {
    rbac
      .listRoles()
      .then((r) => setRoles(r.items))
      .catch(() => setRoles([]))
    api
      .get<{ items: Team[] }>('/teams')
      .then((r) => setTeams(r.items))
      .catch(() => setTeams([]))
  }, [])

  useEffect(() => {
    let cancelled = false
    usersAdmin
      .stats()
      .then((s) => !cancelled && setStats(s))
      .catch(() => {
        /* cards show — */
      })
    return () => {
      cancelled = true
    }
  }, [statsVersion])

  const query = usePaginatedQuery<AdminUser>({
    endpoint: USERS_ENDPOINT,
    urlKey: 'users',
    defaults: { perPage: 25, sort: '-created_at' },
  })

  /** Refetch every /users list (incl. invites) and the stats. */
  const refresh = useCallback(() => {
    invalidate(USERS_ENDPOINT)
    setStatsVersion((v) => v + 1)
  }, [])

  // ── Dialog state ───────────────────────────────────────────────────
  const [addOpen, setAddOpen] = useState(false)
  const [invite, setInvite] = useState<{ open: boolean; prefill: InvitePrefill | null }>({ open: false, prefill: null })
  const [editUser, setEditUser] = useState<AdminUser | null>(null)
  const [disableUser, setDisableUser] = useState<AdminUser | null>(null)
  const [resetUser, setResetUser] = useState<AdminUser | null>(null)
  const [drawerUser, setDrawerUser] = useState<AdminUser | null>(null)
  const [bulkResult, setBulkResult] = useState<{ result: BulkUserResponse; labels: Map<string, string> } | null>(null)
  const [syncing, setSyncing] = useState(false)

  // ── Single-user actions ────────────────────────────────────────────
  const who = (u: AdminUser) => u.name || u.email

  const enable = async (u: AdminUser) => {
    try {
      await usersAdmin.enable(u.id)
      notifySuccess('User enabled', `${who(u)} can sign in again.`)
      refresh()
    } catch (err) {
      notifyUserError(err, 'enable the user')
    }
  }

  const forceLogout = async (u: AdminUser) => {
    const ok = await confirm({
      title: `Force logout ${who(u)}?`,
      description: 'Every session and live connection of this user is ended now. They can sign in again.',
      confirmLabel: 'Force logout',
      variant: 'destructive',
    })
    if (!ok) return
    try {
      await usersAdmin.forceLogout(u.id)
      notifySuccess('Sessions revoked', `${who(u)} was signed out everywhere.`)
    } catch (err) {
      notifyUserError(err, 'force logout the user')
    }
  }

  const unlock = async (u: AdminUser) => {
    try {
      await usersAdmin.unlock(u.id)
      notifySuccess('Account unlocked', `${who(u)} can try signing in again.`)
      refresh()
    } catch (err) {
      notifyUserError(err, 'unlock the user')
    }
  }

  const resetMfa = async (u: AdminUser) => {
    const ok = await confirm({
      title: `Reset MFA for ${who(u)}?`,
      description:
        'Removes their authenticator and backup codes and signs them out everywhere. They sign in with their password only until they enroll again.',
      confirmLabel: 'Reset MFA',
      variant: 'destructive',
    })
    if (!ok) return
    try {
      await usersAdmin.resetMfa(u.id)
      notifySuccess('MFA reset', `${who(u)} must enroll MFA again.`)
      refresh()
    } catch (err) {
      notifyUserError(err, 'reset MFA')
    }
  }

  const remove = async (u: AdminUser) => {
    const ok = await confirm({
      title: `Delete ${who(u)}?`,
      description:
        'The account is permanently deleted. Users who authored records (incidents, notes, evidence…) cannot be deleted; disable them instead.',
      confirmLabel: 'Delete',
      variant: 'destructive',
      requireText: u.email,
    })
    if (!ok) return
    try {
      await usersAdmin.remove(u.id)
      notifySuccess('User deleted', u.email)
      refresh()
    } catch (err) {
      if (isApiError(err) && err.status === 409 && err.code === 'user_has_records') {
        // Attribution-safe offboarding: offer to deactivate instead.
        const instead =
          u.is_active &&
          (await confirm({
            title: describeError(err).title,
            description: describeError(err).description,
            confirmLabel: 'Disable instead',
            variant: 'destructive',
          }))
        if (instead) setDisableUser(u)
        else if (!u.is_active) notifyUserError(err, 'delete the user')
        return
      }
      notifyUserError(err, 'delete the user')
    }
  }

  const syncSupabase = async () => {
    setSyncing(true)
    try {
      const res = await usersAdmin.syncSupabase()
      notifySuccess('Supabase sync complete', res.message)
      refresh()
    } catch (err) {
      notifyUserError(err, 'sync Supabase users')
    } finally {
      setSyncing(false)
    }
  }

  // ── Table ─────────────────────────────────────────────────────────
  const columns = useMemo<DataTableColumn<AdminUser>[]>(
    () => [
      {
        id: 'user',
        header: 'User',
        sortKey: 'name',
        cell: (u) => (
          <div className="flex min-w-0 items-center gap-3">
            <div
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-sm font-medium text-primary"
              aria-hidden
            >
              {(u.name || u.email).charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="truncate font-medium text-foreground">{u.name || 'No name'}</p>
              <p className="truncate text-xs text-muted-foreground">{u.email}</p>
            </div>
          </div>
        ),
      },
      {
        id: 'roles',
        header: 'Roles',
        cell: (u) => (
          <div className="flex flex-wrap gap-1">
            {u.roles.map((r) => (
              <RoleBadge key={r} role={r} />
            ))}
          </div>
        ),
      },
      {
        id: 'teams',
        header: 'Teams',
        hideBelow: 'lg',
        cell: (u) =>
          u.teams && u.teams.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {u.teams.map((t) => (
                <Badge key={t.id} variant="outline">
                  {t.name}
                </Badge>
              ))}
            </div>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      { id: 'status', header: 'Status', cell: (u) => <UserStatusBadges user={u} /> },
      {
        id: 'last_login',
        header: 'Last sign-in',
        sortKey: 'last_login',
        hideBelow: 'md',
        cell: (u) => (
          <Timestamp value={u.last_login} seconds={false} fallback="Never" className="text-sm text-muted-foreground" />
        ),
      },
      {
        id: 'created',
        header: 'Joined',
        sortKey: 'created_at',
        hideBelow: 'lg',
        cell: (u) => <Timestamp value={u.created_at} seconds={false} className="text-sm text-muted-foreground" />,
      },
    ],
    []
  )

  const rowActions = (u: AdminUser): RowAction[] => {
    const actions: RowAction[] = [
      { label: 'View details', icon: Eye, onSelect: () => setDrawerUser(u) },
      { label: 'Edit', icon: Pencil, permission: 'users:update', onSelect: () => setEditUser(u) },
    ]
    if (me?.id === u.id) return actions // self rules: no account actions on your own row
    if (u.is_locked) {
      actions.push({ label: 'Unlock', icon: Unlock, permission: 'users:manage', onSelect: () => void unlock(u) })
    }
    if (!u.is_active) {
      actions.push({ label: 'Enable', icon: UserCheck, permission: 'users:manage', onSelect: () => void enable(u) })
    } else if (u.is_service_account !== true) {
      // Service accounts authenticate with API keys only: no password to reset.
      actions.push({
        label: 'Reset password',
        icon: KeyRound,
        permission: 'users:manage',
        onSelect: () => setResetUser(u),
      })
    }
    actions.push({
      label: 'Force logout',
      icon: LogOut,
      destructive: true,
      permission: 'users:manage',
      onSelect: () => void forceLogout(u),
    })
    if (u.mfa_enabled) {
      actions.push({
        label: 'Reset MFA',
        icon: ShieldOff,
        destructive: true,
        permission: 'users:manage',
        onSelect: () => void resetMfa(u),
      })
    }
    if (u.is_active) {
      actions.push({
        label: 'Disable',
        icon: UserX,
        destructive: true,
        permission: 'users:manage',
        onSelect: () => setDisableUser(u),
      })
    }
    actions.push({
      label: 'Delete',
      icon: Trash2,
      destructive: true,
      permission: 'users:delete',
      onSelect: () => void remove(u),
    })
    return actions
  }

  const filters = query.state.filters
  const toolbar = (
    <>
      <FilterSelect
        label="Role"
        allLabel="All roles"
        value={filters.role_id}
        onChange={(v) => query.setFilter('role_id', v)}
        options={roles.map((r) => ({ value: r.id, label: r.name }))}
      />
      <FilterSelect
        label="Status"
        allLabel="Any status"
        value={filters.status}
        onChange={(v) => query.setFilter('status', v)}
        options={STATUS_OPTIONS}
      />
      {teams.length > 0 && (
        <FilterSelect
          label="Team"
          allLabel="All teams"
          value={filters.team_id}
          onChange={(v) => query.setFilter('team_id', v)}
          options={teams.map((t) => ({ value: t.id, label: t.name }))}
        />
      )}
      <FilterSelect
        label="MFA"
        allLabel="Any MFA"
        value={filters.mfa}
        onChange={(v) => query.setFilter('mfa', v)}
        options={MFA_OPTIONS}
        className="w-[130px]"
      />
    </>
  )

  const usersTable = (
    <DataTable
      query={query}
      columns={columns}
      getRowId={(u) => u.id}
      ariaLabel="Users"
      searchPlaceholder="Search name or email…"
      toolbar={toolbar}
      rowActions={rowActions}
      onRowClick={(u) => setDrawerUser(u)}
      selectable={canManage}
      bulkActions={(ids, clear) => (
        <BulkActionBar
          ids={ids}
          roles={roles}
          teams={teams}
          onResult={(result) => {
            setBulkResult({ result, labels: new Map(query.items.map((u) => [u.id, u.email])) })
            clear()
            refresh()
          }}
        />
      )}
      pageSizes={[25, 50, 100]}
      empty={{ title: 'No users yet', description: 'Invite or add your first team member.' }}
    />
  )

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Users</h1>
          <p className="mt-1 text-sm text-muted-foreground">Accounts, access, invites and account state</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canManage && (
            <Button variant="outline" onClick={() => void syncSupabase()} disabled={syncing}>
              {syncing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Cloud className="mr-2 h-4 w-4" />}
              Sync Supabase
            </Button>
          )}
          {canCreate && (
            <Button variant="outline" onClick={() => setAddOpen(true)}>
              <UserPlus className="mr-2 h-4 w-4" />
              Add user
            </Button>
          )}
          {canManage && (
            <Button onClick={() => setInvite({ open: true, prefill: null })}>
              <Mail className="mr-2 h-4 w-4" />
              Invite user
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6" aria-label="User statistics">
        <StatCard label="Total" value={stats?.total} />
        <StatCard label="Active" value={stats?.active} />
        <StatCard label="Disabled" value={stats?.disabled} />
        <StatCard label="Locked" value={stats?.locked} hint="Temporarily locked after failed sign-ins" />
        <StatCard label="MFA enabled" value={stats?.mfa_enabled} />
        <StatCard label="Pending invites" value={stats?.pending_invites} />
      </div>

      {canManage ? (
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="users">Users</TabsTrigger>
            <TabsTrigger value="invites">Pending invites</TabsTrigger>
          </TabsList>
          <TabsContent value="users" className="mt-4">
            {usersTable}
          </TabsContent>
          <TabsContent value="invites" className="mt-4">
            <PendingInvitesTable
              onReissue={(prefill) => setInvite({ open: true, prefill })}
              onChanged={() => setStatsVersion((v) => v + 1)}
            />
          </TabsContent>
        </Tabs>
      ) : (
        usersTable
      )}

      <AddUserModal open={addOpen} onOpenChange={setAddOpen} onSuccess={refresh} />
      <InviteUserModal
        open={invite.open}
        prefill={invite.prefill}
        onOpenChange={(open) => setInvite((s) => ({ ...s, open }))}
        onSuccess={refresh}
      />
      <EditUserModal
        user={editUser}
        open={editUser !== null}
        onOpenChange={(open) => !open && setEditUser(null)}
        onSuccess={refresh}
      />
      <DisableUserDialog
        user={disableUser}
        open={disableUser !== null}
        onOpenChange={(open) => !open && setDisableUser(null)}
        onDone={(u) => {
          notifySuccess('User disabled', `${who(u)} was signed out everywhere.`)
          refresh()
        }}
      />
      <ResetPasswordDialog
        user={resetUser}
        open={resetUser !== null}
        onOpenChange={(open) => !open && setResetUser(null)}
        onDone={refresh}
      />
      <UserDetailDrawer
        user={drawerUser}
        open={drawerUser !== null}
        onOpenChange={(open) => !open && setDrawerUser(null)}
      />
      <BulkResultDialog
        result={bulkResult?.result ?? null}
        labelFor={(id) => bulkResult?.labels.get(id) ?? id}
        onClose={() => setBulkResult(null)}
      />
    </div>
  )
}
