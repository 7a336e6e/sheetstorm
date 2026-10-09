"use client"

/**
 * Roles admin page.
 *
 * - The permission catalog comes from the server (`GET /permissions`), grouped
 *   and flagged (dangerous / privileged / platform-only), so UI and backend agree.
 * - System roles are global and immutable: View and Clone only.
 * - Custom roles: Edit / Delete only when the server marks them `editable`
 *   (caller holds roles:manage and every permission of the role).
 * - Permissions the caller lacks cannot be ticked (backend 403
 *   `privilege_escalation`); adding dangerous ones asks for typed confirmation.
 * Cosmetic only: `services/rbac_guard.py` enforces every rule.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { DataTable, type DataTableColumn, type RowAction } from '@/components/ui/data-table'
import { GuardErrorAlert } from '@/components/auth/guard-error-alert'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { Copy, Eye, Info, Loader2, Lock, Pencil, Shield, Trash2 } from 'lucide-react'
import type { PaginatedQuery } from '@/hooks/use-paginated-query'
import { usePermissionCatalog } from '@/hooks/use-permission-catalog'
import { ApiError, isApiError } from '@/lib/api'
import { describeError, notifyError, notifySuccess } from '@/lib/errors'
import { canGrant, groupCatalog, rbac, withImplied } from '@/lib/endpoints/rbac'
import { useAuthStore } from '@/lib/store'
import type { PermissionCatalog, PermissionDef, Role } from '@/types'

const NOOP = () => {}

/** Adapts an in-memory list (GET /roles is not paginated) to DataTable's query contract. */
function useStaticQuery<T>(items: T[], isLoading: boolean, error: unknown, refetch: () => Promise<void>): PaginatedQuery<T> {
  return useMemo(() => {
    const apiError = error
      ? isApiError(error)
        ? error
        : new ApiError(0, error instanceof Error ? error.message : 'Request failed')
      : null
    return {
      items,
      total: items.length,
      pages: 1,
      state: { page: 1, perPage: Math.max(items.length, 1), filters: {} },
      isLoading,
      isFetching: isLoading,
      error: apiError,
      setPage: NOOP,
      setPerPage: NOOP,
      setSort: NOOP,
      setQuery: NOOP,
      setFilter: NOOP,
      resetFilters: NOOP,
      refetch,
    }
  }, [items, isLoading, error, refetch])
}

function FlagBadges({ perm }: { perm: PermissionDef }) {
  return (
    <>
      {perm.dangerous && (
        <Badge variant="outline" className="text-amber-400 border-amber-500/30 text-[10px] px-1.5 py-0">
          Dangerous
        </Badge>
      )}
      {perm.privileged && (
        <Badge variant="outline" className="text-muted-foreground border-white/10 text-[10px] px-1.5 py-0" title="Part of the privileged (MFA) scope">
          Privileged
        </Badge>
      )}
      {perm.platform_only && (
        <Badge variant="outline" className="text-muted-foreground border-white/10 text-[10px] px-1.5 py-0" title="Only effective in the platform organization">
          Platform only
        </Badge>
      )}
    </>
  )
}

type EditorMode = 'create' | 'edit' | 'view'

function RoleEditorDialog({
  mode,
  role,
  catalog,
  granted,
  labelOf,
  onClose,
  onSaved,
}: {
  mode: EditorMode
  role: Role | null
  catalog: PermissionCatalog | null
  granted: readonly string[]
  labelOf: (k: string) => string
  onClose: () => void
  onSaved: () => void
}) {
  const confirm = useConfirm()
  const readOnly = mode === 'view'
  const [name, setName] = useState(role?.name ?? '')
  const [description, setDescription] = useState(role?.description ?? '')
  const [perms, setPerms] = useState<Set<string>>(() => new Set(role?.permissions ?? []))
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  const have = useMemo(() => withImplied(granted), [granted])
  const groups = useMemo(() => groupCatalog(catalog), [catalog])
  const byKey = useMemo(() => new Map((catalog?.items ?? []).map((p) => [p.key, p])), [catalog])
  const total = catalog?.items.length ?? 0

  const toggle = (key: string, on: boolean) =>
    setPerms((prev) => {
      const next = new Set(prev)
      if (on) next.add(key)
      else next.delete(key)
      return next
    })

  const toggleGroup = (items: PermissionDef[]) => {
    const grantable = items.filter((p) => have.has(p.key))
    const allOn = grantable.every((p) => perms.has(p.key))
    setPerms((prev) => {
      const next = new Set(prev)
      grantable.forEach((p) => (allOn ? next.delete(p.key) : next.add(p.key)))
      return next
    })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (readOnly) return
    setError(null)
    const trimmed = name.trim()
    if (!trimmed) {
      setError(new Error('Role name is required'))
      return
    }
    const before = new Set(role?.permissions ?? [])
    const addedDangerous = Array.from(perms).filter((k) => !before.has(k) && byKey.get(k)?.dangerous)
    if (addedDangerous.length > 0) {
      const ok = await confirm({
        title: 'Grant dangerous permissions?',
        description: (
          <span className="block space-y-2">
            <span className="block">
              Every holder of &quot;{trimmed}&quot; will be able to:
            </span>
            <span className="block">
              {addedDangerous.map((k) => (
                <span key={k} className="block">
                  {labelOf(k)} <span className="font-mono text-xs">({k})</span>
                </span>
              ))}
            </span>
          </span>
        ),
        confirmLabel: 'Grant',
        variant: 'destructive',
        requireText: trimmed,
      })
      if (!ok) return
    }

    setSaving(true)
    try {
      const payload = {
        name: trimmed,
        description: description.trim(),
        permissions: Array.from(perms).sort(),
      }
      if (mode === 'edit' && role) {
        await rbac.updateRole(role.id, payload)
        notifySuccess('Role updated', `"${trimmed}" has been updated.`)
      } else {
        await rbac.createRole(payload)
        notifySuccess('Role created', `"${trimmed}" has been created.`)
      }
      onSaved()
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  const title =
    mode === 'view' ? `${role?.name ?? ''}: permissions` : mode === 'edit' ? `Edit role: ${role?.name ?? ''}` : 'Create role'

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {role?.is_system && <Lock className="h-4 w-4 text-muted-foreground" aria-hidden />}
              {title}
            </DialogTitle>
            <DialogDescription>
              {readOnly
                ? role?.is_system
                  ? 'Built-in role. It cannot be changed; clone it to customise a copy.'
                  : role?.description || 'No description.'
                : 'Users get the union of all their roles’ permissions. You can only grant permissions you hold.'}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <GuardErrorAlert error={error} labelOf={labelOf} />

            {!readOnly && (
              <>
                <div className="grid gap-2">
                  <Label htmlFor="role-name">Name</Label>
                  <Input
                    id="role-name"
                    value={name}
                    maxLength={100}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Analyst (no IOC delete)"
                    required
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="role-description">Description</Label>
                  <Textarea
                    id="role-description"
                    value={description}
                    maxLength={500}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What this role is for"
                    rows={2}
                  />
                </div>
              </>
            )}

            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <Label>Permissions</Label>
                <span className="text-xs text-muted-foreground">
                  {perms.size} of {total} selected
                </span>
              </div>
              {!catalog ? (
                <div className="flex justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <TooltipProvider delayDuration={200}>
                  <div className="border border-white/10 rounded-md divide-y divide-white/10 max-h-[45vh] overflow-y-auto">
                    {groups.map((group) => {
                      const items = readOnly ? group.items.filter((p) => perms.has(p.key)) : group.items
                      if (items.length === 0) return null
                      const selected = group.items.filter((p) => perms.has(p.key)).length
                      const grantable = group.items.filter((p) => have.has(p.key))
                      const allOn = grantable.length > 0 && grantable.every((p) => perms.has(p.key))
                      const someOn = !allOn && grantable.some((p) => perms.has(p.key))
                      return (
                        <section key={group.key} className="p-3" aria-label={group.label}>
                          <div className="flex items-center gap-2 mb-2">
                            {!readOnly && (
                              <Checkbox
                                aria-label={`Select all grantable ${group.label} permissions`}
                                checked={allOn ? true : someOn ? 'indeterminate' : false}
                                disabled={grantable.length === 0}
                                onCheckedChange={() => toggleGroup(group.items)}
                              />
                            )}
                            <h3 className="text-sm font-medium">{group.label}</h3>
                            <Badge variant="outline" className="text-xs ml-auto">
                              {selected}/{group.items.length}
                            </Badge>
                          </div>
                          <ul className="grid gap-1.5 pl-6">
                            {items.map((perm) => {
                              const lacking = !have.has(perm.key)
                              const checked = perms.has(perm.key)
                              const disabled = readOnly || (lacking && !checked)
                              const id = `perm-${perm.key.replace(/[^a-z0-9_-]/gi, '-')}`
                              return (
                                <li key={perm.key} className="flex flex-wrap items-center gap-2 text-sm">
                                  {!readOnly && (
                                    <Checkbox
                                      id={id}
                                      checked={checked}
                                      disabled={disabled}
                                      title={lacking ? "You don't hold this permission" : undefined}
                                      onCheckedChange={(v) => toggle(perm.key, v === true)}
                                    />
                                  )}
                                  <label
                                    htmlFor={readOnly ? undefined : id}
                                    className={lacking && !readOnly ? 'text-muted-foreground/60' : 'text-muted-foreground'}
                                    title={lacking && !readOnly ? "You don't hold this permission" : undefined}
                                  >
                                    {perm.label}
                                  </label>
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <button
                                        type="button"
                                        className="text-muted-foreground/60 hover:text-foreground"
                                        aria-label={`About ${perm.label}`}
                                      >
                                        <Info className="h-3.5 w-3.5" aria-hidden />
                                      </button>
                                    </TooltipTrigger>
                                    <TooltipContent className="max-w-xs">
                                      <p>{perm.description}</p>
                                      <p className="mt-1 font-mono text-xs text-muted-foreground">{perm.key}</p>
                                    </TooltipContent>
                                  </Tooltip>
                                  <FlagBadges perm={perm} />
                                </li>
                              )
                            })}
                          </ul>
                        </section>
                      )
                    })}
                  </div>
                </TooltipProvider>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
              {readOnly ? 'Close' : 'Cancel'}
            </Button>
            {!readOnly && (
              <Button type="submit" disabled={saving || !catalog}>
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {mode === 'edit' ? 'Save changes' : 'Create role'}
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function CloneRoleDialog({
  source,
  labelOf,
  onClose,
  onCloned,
}: {
  source: Role
  labelOf: (k: string) => string
  onClose: () => void
  onCloned: () => void
}) {
  const [name, setName] = useState(`${source.name} (copy)`)
  const [description, setDescription] = useState(source.description ?? '')
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      const res = await rbac.cloneRole(source.id, { name: name.trim(), description: description.trim() })
      const dropped = res.dropped_permissions ?? []
      notifySuccess(
        'Role cloned',
        dropped.length
          ? `"${res.name}" was created without platform-only permissions: ${dropped.map(labelOf).join(', ')}.`
          : `"${res.name}" was created from "${source.name}".`
      )
      onCloned()
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Clone role: {source.name}</DialogTitle>
            <DialogDescription>
              Creates a custom role in your organization with the same {source.permissions.length} permissions. Edit the copy
              afterwards; the original stays unchanged.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <GuardErrorAlert error={error} labelOf={labelOf} />
            <div className="grid gap-2">
              <Label htmlFor="clone-name">Name</Label>
              <Input id="clone-name" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="clone-description">Description</Label>
              <Textarea
                id="clone-description"
                value={description}
                maxLength={500}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving || !name.trim()}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Clone
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default function RolesPage() {
  const confirm = useConfirm()
  const granted = useAuthStore((s) => s.user?.permissions) ?? []
  const { catalog, error: catalogError, lookup, labelOf, reload: reloadCatalog } = usePermissionCatalog()
  const [roles, setRoles] = useState<Role[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [editor, setEditor] = useState<{ mode: EditorMode; role: Role | null } | null>(null)
  const [cloneSource, setCloneSource] = useState<Role | null>(null)

  const loadRoles = useCallback(async () => {
    try {
      const res = await rbac.listRoles()
      setRoles(res.items)
      setLoadError(null)
    } catch (err) {
      setLoadError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadRoles()
  }, [loadRoles])

  const query = useStaticQuery(roles, loading, loadError, loadRoles)

  const handleDelete = async (role: Role) => {
    if (!(await confirmDelete(confirm, 'role', role.name))) return
    try {
      await rbac.deleteRole(role.id)
      notifySuccess('Role deleted', `"${role.name}" has been deleted.`)
      await loadRoles()
    } catch (err) {
      notifyError(err, 'delete the role')
    }
  }

  const dangerousCount = (role: Role) => role.permissions.filter((k) => lookup(k)?.dangerous).length

  const columns: DataTableColumn<Role>[] = [
    {
      id: 'name',
      header: 'Name',
      cell: (role) => (
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {role.is_system && <Lock className="h-3.5 w-3.5 text-muted-foreground shrink-0" aria-label="Built-in role" />}
            <span className="font-medium">{role.name}</span>
          </div>
          {role.description && (
            <p className="text-xs text-muted-foreground truncate max-w-[360px]">{role.description}</p>
          )}
        </div>
      ),
    },
    {
      id: 'permissions',
      header: 'Permissions',
      cell: (role) => {
        const dangerous = dangerousCount(role)
        return (
          <div className="flex items-center gap-1.5">
            <Badge variant="outline">{role.permissions.length}</Badge>
            {dangerous > 0 && (
              <Badge variant="outline" className="text-amber-400 border-amber-500/30" title="Dangerous permissions">
                {dangerous} dangerous
              </Badge>
            )}
          </div>
        )
      },
    },
    {
      id: 'users',
      header: 'Users',
      hideBelow: 'sm',
      cell: (role) => <span className="tabular-nums text-muted-foreground">{role.user_count ?? 0}</span>,
    },
    {
      id: 'type',
      header: 'Type',
      cell: (role) => (
        <Badge variant={role.is_system ? 'default' : 'outline'}>{role.is_system ? 'System' : 'Custom'}</Badge>
      ),
    },
  ]

  const rowActions = (role: Role): RowAction[] => {
    const actions: RowAction[] = [
      { label: 'View permissions', icon: Eye, onSelect: () => setEditor({ mode: 'view', role }) },
    ]
    if (!role.is_system && role.editable) {
      actions.push({
        label: 'Edit role',
        icon: Pencil,
        permission: 'roles:manage',
        onSelect: () => setEditor({ mode: 'edit', role }),
      })
    }
    actions.push({
      label: 'Clone',
      icon: Copy,
      permission: 'roles:manage',
      // The server refuses clones carrying permissions the caller lacks.
      disabled: !canGrant(granted, role.permissions),
      onSelect: () => setCloneSource(role),
    })
    if (!role.is_system && role.editable) {
      actions.push({
        label: 'Delete role',
        icon: Trash2,
        permission: 'roles:manage',
        destructive: true,
        onSelect: () => void handleDelete(role),
      })
    }
    return actions
  }

  const systemCount = roles.filter((r) => r.is_system).length

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Roles</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {roles.length} roles · {systemCount} built-in · {roles.length - systemCount} custom
        </p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield className="h-5 w-5" />
            How roles work
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              <li>
                Permissions are additive: a user holds the union of all their roles. No role restricts another; to
                restrict a user, remove a role.
              </li>
              <li>Built-in roles are shared by every organization and cannot be changed. Clone one to customise it.</li>
              <li>You can only grant permissions you hold yourself, and only edit roles within your own permissions.</li>
            </ul>
        </CardContent>
      </Card>

      {catalogError ? (
        <div role="alert" className="flex items-center justify-between rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          <span>Couldn&apos;t load the permission catalog: {describeError(catalogError).description}</span>
          <Button variant="outline" size="sm" onClick={reloadCatalog}>
            Retry
          </Button>
        </div>
      ) : null}

      <DataTable
        query={query}
        columns={columns}
        getRowId={(r) => r.id}
        ariaLabel="Roles"
        primaryAction={{ label: 'Create role', permission: 'roles:manage', onSelect: () => setEditor({ mode: 'create', role: null }) }}
        rowActions={rowActions}
        onRowClick={(role) => setEditor({ mode: 'view', role })}
        empty={{ title: 'No roles', description: 'Create a custom role to get started.' }}
        pageSizes={[Math.max(roles.length, 1)]}
      />

      {editor && (
        <RoleEditorDialog
          key={`${editor.mode}-${editor.role?.id ?? 'new'}`}
          mode={editor.mode}
          role={editor.role}
          catalog={catalog}
          granted={granted}
          labelOf={labelOf}
          onClose={() => setEditor(null)}
          onSaved={() => {
            setEditor(null)
            void loadRoles()
          }}
        />
      )}
      {cloneSource && (
        <CloneRoleDialog
          source={cloneSource}
          labelOf={labelOf}
          onClose={() => setCloneSource(null)}
          onCloned={() => {
            setCloneSource(null)
            void loadRoles()
          }}
        />
      )}
    </div>
  )
}
