'use client'

/**
 * Bulk actions over the selected users (`POST /users/bulk`, ≤100 ids). Each
 * item succeeds or is skipped on its own (guard codes such as `self_action`,
 * `insufficient_privilege`, `last_admin`); the result dialog lists every
 * skipped and failed item with its code. Needs users:manage; role actions
 * also need roles:manage.
 */
import { useState } from 'react'
import { ChevronDown, Loader2 } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { usePermission } from '@/components/auth/permission-gate'
import { BULK_ACTION_LABEL, usersAdmin } from '@/lib/endpoints/users-admin'
import type { BulkUserAction, BulkUserRequest, BulkUserResponse, Role, Team } from '@/types'
import { notifyUserError, UserErrorAlert } from './lifecycle-errors'
import { MAX_REASON } from './DisableUserDialog'

export const BULK_MAX = 100

type ParamAction = Extract<BulkUserAction, 'disable' | 'add_role' | 'remove_role' | 'add_team'>

export function BulkActionBar({
  ids,
  roles,
  teams,
  onResult,
}: {
  ids: string[]
  roles: Role[]
  teams: Team[]
  /** After a run: the parent refreshes, clears the selection and shows <BulkResultDialog>. */
  onResult: (result: BulkUserResponse) => void
}) {
  const confirm = useConfirm()
  const canManage = usePermission('users:manage')
  const canRoles = usePermission(['users:manage', 'roles:manage'])

  const [paramAction, setParamAction] = useState<ParamAction | null>(null)
  const [reason, setReason] = useState('')
  const [targetId, setTargetId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  const openParams = (action: ParamAction) => {
    setReason('')
    setTargetId('')
    setError(null)
    setParamAction(action)
  }

  if (!canManage) return null

  const tooMany = ids.length > BULK_MAX
  const n = ids.length
  const usersLabel = `${n} ${n === 1 ? 'user' : 'users'}`

  const run = async (body: Omit<BulkUserRequest, 'user_ids'>): Promise<boolean> => {
    setBusy(true)
    setError(null)
    try {
      const res = await usersAdmin.bulk({ ...body, user_ids: ids })
      onResult(res)
      return true
    } catch (err) {
      if (paramAction) setError(err)
      else notifyUserError(err, `${BULK_ACTION_LABEL[body.action].toLowerCase()} the selected users`)
      return false
    } finally {
      setBusy(false)
    }
  }

  const simple = async (action: 'enable' | 'force_logout') => {
    const ok = await confirm(
      action === 'force_logout'
        ? {
            title: `Force logout ${usersLabel}?`,
            description: 'Every session and live connection of the selected users is ended now.',
            confirmLabel: 'Force logout',
            variant: 'destructive',
          }
        : {
            title: `Enable ${usersLabel}?`,
            description: 'The selected users can sign in again. Old sessions stay revoked.',
            confirmLabel: 'Enable',
          }
    )
    if (!ok) return
    await run({ action })
  }

  const submitParams = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!paramAction) return
    const body: Omit<BulkUserRequest, 'user_ids'> =
      paramAction === 'disable'
        ? { action: 'disable', reason: reason.trim() }
        : paramAction === 'add_team'
          ? { action: 'add_team', team_id: targetId }
          : { action: paramAction, role_id: targetId }
    if (await run(body)) setParamAction(null)
  }

  const paramValid =
    paramAction === 'disable' ? reason.trim().length > 0 && reason.trim().length <= MAX_REASON : !!targetId
  const options = paramAction === 'add_team' ? teams.map((t) => ({ id: t.id, name: t.name })) : roles

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="sm" variant="outline" disabled={tooMany || busy}>
            {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
            Bulk actions
            <ChevronDown className="ml-1.5 h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onSelect={() => void simple('enable')}>Enable</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => openParams('add_team')} disabled={teams.length === 0}>
            Add to team…
          </DropdownMenuItem>
          {canRoles && <DropdownMenuItem onSelect={() => openParams('add_role')}>Add role…</DropdownMenuItem>}
          <DropdownMenuSeparator />
          {canRoles && (
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              onSelect={() => openParams('remove_role')}
            >
              Remove role…
            </DropdownMenuItem>
          )}
          <DropdownMenuItem
            className="text-destructive focus:text-destructive"
            onSelect={() => void simple('force_logout')}
          >
            Force logout
          </DropdownMenuItem>
          <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => openParams('disable')}>
            Disable…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {tooMany && <span className="text-xs text-amber-400">At most {BULK_MAX} users per bulk action</span>}

      {/* Parameters (reason / role / team) */}
      <Dialog open={paramAction !== null} onOpenChange={(o) => !o && setParamAction(null)}>
        <DialogContent className="max-w-md">
          <form onSubmit={submitParams} className="space-y-4">
            <DialogHeader>
              <DialogTitle>
                {paramAction ? BULK_ACTION_LABEL[paramAction] : ''} — {usersLabel}
              </DialogTitle>
              <DialogDescription>
                {paramAction === 'disable'
                  ? 'The selected users are signed out everywhere and cannot sign in until re-enabled.'
                  : paramAction === 'remove_role'
                    ? 'Users who do not hold the role are skipped. The last administrator is never removed.'
                    : 'Users you cannot manage are skipped and listed afterwards.'}
              </DialogDescription>
            </DialogHeader>
            <UserErrorAlert error={error} />
            {paramAction === 'disable' ? (
              <div className="grid gap-2">
                <Label htmlFor="bulk-reason">Reason</Label>
                <Textarea
                  id="bulk-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={MAX_REASON}
                  rows={3}
                  required
                />
              </div>
            ) : (
              <div className="grid gap-2">
                <Label htmlFor="bulk-target">{paramAction === 'add_team' ? 'Team' : 'Role'}</Label>
                <Select value={targetId} onValueChange={setTargetId}>
                  <SelectTrigger id="bulk-target" aria-label={paramAction === 'add_team' ? 'Team' : 'Role'}>
                    <SelectValue placeholder="Choose…" />
                  </SelectTrigger>
                  <SelectContent>
                    {options.map((o) => (
                      <SelectItem key={o.id} value={o.id}>
                        {o.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setParamAction(null)} disabled={busy}>
                Cancel
              </Button>
              <Button
                type="submit"
                variant={paramAction === 'disable' || paramAction === 'remove_role' ? 'destructive' : 'default'}
                disabled={!paramValid || busy}
              >
                {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Apply to {usersLabel}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}

/** Per-item results of a bulk run: every skipped and failed user with its code. */
export function BulkResultDialog({
  result,
  labelFor,
  onClose,
}: {
  result: BulkUserResponse | null
  /** Display label (email) of a user id. */
  labelFor: (id: string) => string
  onClose: () => void
}) {
  const problems = result?.results.filter((r) => r.status !== 'ok') ?? []
  return (
    <Dialog open={result !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{result ? BULK_ACTION_LABEL[result.action] : ''}: results</DialogTitle>
          <DialogDescription>
            {result && (
              <span data-testid="bulk-summary">
                {result.summary.ok} succeeded, {result.summary.skipped} skipped, {result.summary.failed} failed
              </span>
            )}
          </DialogDescription>
        </DialogHeader>
        {problems.length > 0 && (
          <ul className="max-h-64 space-y-1.5 overflow-y-auto text-sm" aria-label="Skipped and failed users">
            {problems.map((r) => (
              <li key={r.user_id} className="rounded-md border border-border px-3 py-2">
                <span className="font-medium">{labelFor(r.user_id)}</span>
                <span className={r.status === 'error' ? 'ml-2 text-red-400' : 'ml-2 text-amber-400'}>
                  {r.status === 'error' ? 'failed' : 'skipped'}
                  {r.code ? ` (${r.code})` : ''}
                </span>
                {r.message && <p className="text-xs text-muted-foreground">{r.message}</p>}
              </li>
            ))}
          </ul>
        )}
        <DialogFooter>
          <Button type="button" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
