"use client"

/**
 * Create or edit a service account: a name and the roles it holds. Roles
 * above your own permissions (the role ceiling) are listed but cannot be
 * selected; the server enforces the same rule (`privilege_escalation`).
 * A service account cannot sign in; it only owns API keys, whose scopes are
 * always limited to what its roles grant.
 */
import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { isAbortError } from '@/lib/api'
import { fieldErrors, serviceAccounts } from '@/lib/endpoints/api-keys'
import { canGrant, rbac } from '@/lib/endpoints/rbac'
import { describeError } from '@/lib/errors'
import { useAuthStore } from '@/lib/store'
import type { Role, ServiceAccount, ServiceAccountUpdateInput } from '@/types'
import { ApiKeyErrorAlert } from './ApiKeyErrorAlert'

const MAX_NAME = 100
const MAX_ROLES = 20

export function ServiceAccountDialog({
  open,
  account,
  onOpenChange,
  onSaved,
}: {
  open: boolean
  /** Set to edit; null to create. */
  account: ServiceAccount | null
  onOpenChange: (open: boolean) => void
  onSaved: (account: ServiceAccount, created: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        {/* Unmounts on close: every opening starts from the account's current state. */}
        {open && (
          <AccountForm
            key={account?.id ?? 'new'}
            account={account}
            onClose={() => onOpenChange(false)}
            onSaved={onSaved}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

/** Only what changed: an untouched role set is not re-checked against the caller's ceiling. */
export function changes(account: ServiceAccount, name: string, roleIds: string[]): ServiceAccountUpdateInput {
  const before = account.roles.map((r) => r.id).sort()
  const after = [...roleIds].sort()
  const sameRoles = before.length === after.length && before.every((id, i) => id === after[i])
  return {
    ...(name !== account.name ? { name } : {}),
    ...(sameRoles ? {} : { role_ids: roleIds }),
  }
}

function AccountForm({
  account,
  onClose,
  onSaved,
}: {
  account: ServiceAccount | null
  onClose: () => void
  onSaved: (account: ServiceAccount, created: boolean) => void
}) {
  const granted = useAuthStore((s) => s.user?.permissions)
  const [roles, setRoles] = useState<Role[] | null>(null)
  const [rolesError, setRolesError] = useState<unknown>(null)
  const [name, setName] = useState(account?.name ?? '')
  const [roleIds, setRoleIds] = useState<string[]>(() => account?.roles.map((r) => r.id) ?? [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    let cancelled = false
    rbac
      .listRoles()
      .then((res) => {
        if (!cancelled) setRoles(res.items)
      })
      .catch((err) => {
        if (!cancelled && !isAbortError(err)) setRolesError(err)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const trimmed = name.trim()
  const fields = fieldErrors(error)
  const valid = trimmed.length >= 1 && trimmed.length <= MAX_NAME && roleIds.length <= MAX_ROLES

  const toggle = (id: string, on: boolean) =>
    setRoleIds((cur) => (on ? Array.from(new Set([...cur, id])) : cur.filter((r) => r !== id)))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    setBusy(true)
    setError(null)
    try {
      const saved = account
        ? await serviceAccounts.update(account.id, changes(account, trimmed, roleIds))
        : await serviceAccounts.create({ name: trimmed, role_ids: roleIds })
      onSaved(saved, !account)
      onClose()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <DialogHeader>
        <DialogTitle>{account ? `Edit ${account.name}` : 'Create service account'}</DialogTitle>
        <DialogDescription>
          A service account owns API keys for automation and survives staff turnover. It cannot sign in. Its keys can
          only be scoped to what its roles allow.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="space-y-4">
        <ApiKeyErrorAlert error={error} />
        <div className="grid gap-2">
          <Label htmlFor="sa-name">Name</Label>
          <Input
            id="sa-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={MAX_NAME}
            placeholder="e.g. ingest-bot"
            autoComplete="off"
            required
            autoFocus
            aria-invalid={!!fields.name}
          />
          {fields.name && <p className="text-xs text-red-400">{fields.name}</p>}
        </div>

        <fieldset className="grid gap-2">
          <legend className="text-sm font-medium">Roles</legend>
          {rolesError ? (
            <p role="alert" className="text-xs text-red-400">
              {describeError(rolesError).description}
            </p>
          ) : roles === null ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading roles…
            </p>
          ) : roles.length === 0 ? (
            <p className="text-sm text-muted-foreground">No roles available.</p>
          ) : (
            <ul className="space-y-1.5 rounded-md border border-border p-3">
              {roles.map((role) => {
                const selected = roleIds.includes(role.id)
                const allowed = canGrant(granted, role.permissions)
                // Above the ceiling: cannot be added, but an existing one can be removed.
                const disabled = !allowed && !selected
                return (
                  <li key={role.id} className="flex items-start gap-2">
                    <Checkbox
                      id={`sa-role-${role.id}`}
                      className="mt-0.5"
                      checked={selected}
                      disabled={disabled || busy}
                      onCheckedChange={(v) => toggle(role.id, v === true)}
                    />
                    <div className="text-sm">
                      <Label htmlFor={`sa-role-${role.id}`} className="font-normal">
                        {role.name}
                      </Label>
                      <p className="text-xs text-muted-foreground">
                        {role.permissions.length} permissions
                        {!allowed && ' · exceeds your permissions'}
                      </p>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
          <p className="text-xs text-muted-foreground">
            With no role, the account holds no permissions and cannot own a key with scopes.
          </p>
        </fieldset>
      </DialogBody>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button type="submit" disabled={!valid || busy}>
          {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {account ? 'Save changes' : 'Create service account'}
        </Button>
      </DialogFooter>
    </form>
  )
}
