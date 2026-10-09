'use client'

/**
 * Invite a user (no SMTP): the one-time link is shown once, to be sent over
 * any channel. Picking roles needs roles:manage and roles above your own
 * permissions are disabled (backend 403 privilege_escalation); without a role
 * the invitee gets Viewer. Re-issuing an invite for the same email
 * supersedes the pending one.
 */
import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import {
  Dialog,
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { usePermission } from '@/components/auth/permission-gate'
import { usePermissionCatalog } from '@/hooks/use-permission-catalog'
import { api } from '@/lib/api'
import { canGrant, rbac } from '@/lib/endpoints/rbac'
import { absoluteLink, usersAdmin } from '@/lib/endpoints/users-admin'
import { useAuthStore } from '@/lib/store'
import type { InviteCreateInput, Role, Team } from '@/types'
import { UserErrorAlert } from './lifecycle-errors'
import { OneTimeSecret } from './OneTimeSecret'

export interface InvitePrefill {
  email: string
  name?: string | null
  role_ids?: string[]
  team_ids?: string[]
  organizational_role?: string | null
}

const EXPIRY_DAYS = [1, 2, 3, 5, 7]

export function InviteUserModal({
  open,
  onOpenChange,
  onSuccess,
  prefill,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
  /** Re-issue: start from an existing invite. */
  prefill?: InvitePrefill | null
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        {/* Content unmounts on close: the one-time link goes with it. */}
        <InviteBody prefill={prefill ?? null} onClose={() => onOpenChange(false)} onSuccess={onSuccess} />
      </DialogContent>
    </Dialog>
  )
}

function InviteBody({
  prefill,
  onClose,
  onSuccess,
}: {
  prefill: InvitePrefill | null
  onClose: () => void
  onSuccess: () => void
}) {
  const granted = useAuthStore((s) => s.user?.permissions) ?? []
  const canAssignRoles = usePermission('roles:manage')
  const { labelOf } = usePermissionCatalog()

  const [email, setEmail] = useState(prefill?.email ?? '')
  const [name, setName] = useState(prefill?.name ?? '')
  const [orgRole, setOrgRole] = useState(prefill?.organizational_role ?? '')
  const [roleIds, setRoleIds] = useState<string[]>(prefill?.role_ids ?? [])
  const [teamIds, setTeamIds] = useState<string[]>(prefill?.team_ids ?? [])
  const [days, setDays] = useState('7')
  const [roles, setRoles] = useState<Role[]>([])
  const [teams, setTeams] = useState<Team[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  // The one-time link: component state only, gone when the dialog closes.
  const [link, setLink] = useState<{ url: string; email: string; superseded: boolean } | null>(null)

  useEffect(() => {
    let cancelled = false
    if (canAssignRoles) {
      rbac
        .listRoles()
        .then((r) => !cancelled && setRoles(r.items))
        .catch(() => {
          /* no role list: the invitee gets Viewer */
        })
    }
    api
      .get<{ items: Team[] }>('/teams')
      .then((r) => !cancelled && setTeams(r.items))
      .catch(() => {
        /* teams are optional */
      })
    return () => {
      cancelled = true
    }
  }, [canAssignRoles])

  const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const body: InviteCreateInput = {
      email: email.trim(),
      expires_in_days: Number(days),
      ...(name.trim() ? { name: name.trim() } : {}),
      ...(orgRole.trim() ? { organizational_role: orgRole.trim() } : {}),
      // Without roles:manage the server refuses role_ids; the invitee gets Viewer.
      ...(canAssignRoles && roleIds.length > 0 ? { role_ids: roleIds } : {}),
      ...(teamIds.length > 0 ? { team_ids: teamIds } : {}),
    }
    try {
      const res = await usersAdmin.invites.create(body)
      setLink({ url: absoluteLink(res), email: res.invite.email, superseded: !!res.superseded_invite_id })
      onSuccess()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {link ? (
        <div className="space-y-4">
          <DialogHeader>
            <DialogTitle>Invite created</DialogTitle>
            <DialogDescription>
              Send this link to {link.email} over a channel you trust.
              {link.superseded && ' The previous pending invite for this email was revoked.'}
            </DialogDescription>
          </DialogHeader>
          <OneTimeSecret
            label="Invite link"
            value={link.url}
            warning={`Shown once. Anyone with this link can join as ${link.email}.`}
          />
          <DialogFooter>
            <Button type="button" onClick={onClose}>
              Done
            </Button>
          </DialogFooter>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{prefill ? 'Re-issue invite' : 'Invite user'}</DialogTitle>
            <DialogDescription>
              Creates a one-time link. The invitee sets their own name and password.
            </DialogDescription>
          </DialogHeader>
          <UserErrorAlert error={error} labelOf={labelOf} />

          <div className="grid gap-2">
            <Label htmlFor="invite-email">Email Address</Label>
            <Input
              id="invite-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@company.com"
              required
              maxLength={255}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="invite-name">Name (optional)</Label>
            <Input id="invite-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={255} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="invite-org-role">Organisational Role (optional)</Label>
            <Input
              id="invite-org-role"
              value={orgRole}
              onChange={(e) => setOrgRole(e.target.value)}
              placeholder="e.g. Senior Analyst"
              maxLength={150}
            />
          </div>

          <div className="grid gap-2 border-t pt-4">
            <Label>Roles</Label>
            {!canAssignRoles ? (
              <p className="text-xs text-muted-foreground">
                The invitee gets the Viewer role. Assigning other roles requires the Manage roles permission.
              </p>
            ) : (
              <div className="grid gap-1.5" role="group" aria-label="Roles">
                {roles.length === 0 && <p className="text-xs text-muted-foreground">Loading roles…</p>}
                {roles.map((r) => {
                  const exceeds = !canGrant(granted, r.permissions)
                  const id = `invite-role-${r.id}`
                  return (
                    <div key={r.id} className="flex items-center gap-2">
                      <Checkbox
                        id={id}
                        checked={roleIds.includes(r.id)}
                        disabled={exceeds}
                        onCheckedChange={() => setRoleIds((prev) => toggle(prev, r.id))}
                      />
                      <Label htmlFor={id} className={exceeds ? 'font-normal text-muted-foreground' : 'font-normal'}>
                        {r.name}
                        {exceeds ? ' (exceeds your permissions)' : ''}
                      </Label>
                    </div>
                  )
                })}
                <p className="text-xs text-muted-foreground">No role selected: the invitee gets Viewer.</p>
              </div>
            )}
          </div>

          {teams.length > 0 && (
            <div className="grid gap-2 border-t pt-4">
              <Label>Teams</Label>
              <div className="grid gap-1.5" role="group" aria-label="Teams">
                {teams.map((t) => {
                  const id = `invite-team-${t.id}`
                  return (
                    <div key={t.id} className="flex items-center gap-2">
                      <Checkbox
                        id={id}
                        checked={teamIds.includes(t.id)}
                        onCheckedChange={() => setTeamIds((prev) => toggle(prev, t.id))}
                      />
                      <Label htmlFor={id} className="font-normal">
                        {t.name}
                      </Label>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          <div className="grid gap-2 border-t pt-4">
            <Label htmlFor="invite-expiry">Link expires after</Label>
            <Select value={days} onValueChange={setDays}>
              <SelectTrigger id="invite-expiry" aria-label="Link expires after">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EXPIRY_DAYS.map((d) => (
                  <SelectItem key={d} value={String(d)}>
                    {d} {d === 1 ? 'day' : 'days'}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy || !email.trim()}>
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create invite
            </Button>
          </DialogFooter>
        </form>
      )}
    </>
  )
}
