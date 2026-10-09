'use client'

/**
 * Disable a user with a required reason (1..500 chars). The server revokes
 * every session and socket of the user; guard refusals (self_action,
 * insufficient_privilege, last_admin) and 503 revocation_failed are shown inline.
 */
import { useState } from 'react'
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
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { usersAdmin } from '@/lib/endpoints/users-admin'
import { usePermissionCatalog } from '@/hooks/use-permission-catalog'
import type { AdminUser } from '@/types'
import { UserErrorAlert } from './lifecycle-errors'

export const MAX_REASON = 500

export function DisableUserDialog({
  user,
  open,
  onOpenChange,
  onDone,
}: {
  user: Pick<AdminUser, 'id' | 'name' | 'email'> | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onDone: (user: AdminUser) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        {/* Content unmounts on close, so every opening starts with an empty form. */}
        {user && <DisableForm key={user.id} user={user} onClose={() => onOpenChange(false)} onDone={onDone} />}
      </DialogContent>
    </Dialog>
  )
}

function DisableForm({
  user,
  onClose,
  onDone,
}: {
  user: Pick<AdminUser, 'id' | 'name' | 'email'>
  onClose: () => void
  onDone: (user: AdminUser) => void
}) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const { labelOf } = usePermissionCatalog()

  const trimmed = reason.trim()
  const valid = trimmed.length > 0 && trimmed.length <= MAX_REASON

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    setBusy(true)
    setError(null)
    try {
      const res = await usersAdmin.disable(user.id, trimmed)
      onDone(res.user)
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
        <DialogTitle>Disable {user.name || user.email}?</DialogTitle>
        <DialogDescription>
          The user is signed out everywhere and can&apos;t sign in until re-enabled. Their records are kept.
        </DialogDescription>
      </DialogHeader>
      <UserErrorAlert error={error} labelOf={labelOf} />
      <div className="grid gap-2">
        <Label htmlFor="disable-reason">Reason</Label>
        <Textarea
          id="disable-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Suspected credential compromise (IR-2026-014)"
          maxLength={MAX_REASON}
          rows={3}
          required
          autoFocus
        />
        <p className="text-xs text-muted-foreground">
          Recorded in the audit log. {trimmed.length}/{MAX_REASON}
        </p>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button type="submit" variant="destructive" disabled={!valid || busy}>
          {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Disable user
        </Button>
      </DialogFooter>
    </form>
  )
}
