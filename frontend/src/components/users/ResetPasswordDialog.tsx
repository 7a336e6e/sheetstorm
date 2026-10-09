'use client'

/**
 * Admin password reset: a one-time reset link, or a temporary password the
 * user must change at next sign-in. The result is shown once (copy dialog)
 * and dropped when the dialog closes.
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
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Timestamp } from '@/components/ui/timestamp'
import { absoluteLink, usersAdmin } from '@/lib/endpoints/users-admin'
import { usePermissionCatalog } from '@/hooks/use-permission-catalog'
import type { AdminResetResult, AdminUser, ResetPasswordMode } from '@/types'
import { UserErrorAlert } from './lifecycle-errors'
import { OneTimeSecret } from './OneTimeSecret'

type ResetTarget = Pick<AdminUser, 'id' | 'name' | 'email' | 'auth_provider'>

export function ResetPasswordDialog({
  user,
  open,
  onOpenChange,
  onDone,
}: {
  user: ResetTarget | null
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called after a successful reset (the list may show new state). */
  onDone?: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        {/* Content unmounts on close: the secret goes with it. */}
        {user && <ResetBody key={user.id} user={user} onClose={() => onOpenChange(false)} onDone={onDone} />}
      </DialogContent>
    </Dialog>
  )
}

function ResetBody({ user, onClose, onDone }: { user: ResetTarget; onClose: () => void; onDone?: () => void }) {
  const [mode, setMode] = useState<ResetPasswordMode>('link')
  const [revokeSessions, setRevokeSessions] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  // The secret: component state only, gone when the dialog closes.
  const [result, setResult] = useState<AdminResetResult | null>(null)
  const { labelOf } = usePermissionCatalog()

  const isExternal = !!user.auth_provider && user.auth_provider !== 'local'

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await usersAdmin.resetPassword(user.id, mode, mode === 'link' ? { revokeSessions } : {})
      setResult(res)
      onDone?.()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const who = user.name || user.email

  return (
    <>
      {result ? (
        <div className="space-y-4">
          <DialogHeader>
            <DialogTitle>{result.mode === 'link' ? 'Reset link created' : 'Temporary password set'}</DialogTitle>
            <DialogDescription>
              {result.mode === 'link' ? (
                <>
                  Send this link to {who} over a channel you trust. It works once and expires{' '}
                  <Timestamp value={result.expires_at} seconds={false} />.
                </>
              ) : (
                <>All sessions of {who} were signed out. They must choose a new password at next sign-in.</>
              )}
            </DialogDescription>
          </DialogHeader>
          {result.mode === 'link' ? (
            <OneTimeSecret
              label="Reset link"
              value={absoluteLink(result)}
              warning="Shown once. Anyone with this link can set this user's password."
            />
          ) : (
            <OneTimeSecret
              label="Temporary password"
              value={result.temp_password}
              warning="Shown once. It can't be retrieved again after you close this dialog."
            />
          )}
          <DialogFooter>
            <Button type="button" onClick={onClose}>
              Done
            </Button>
          </DialogFooter>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Reset password for {who}?</DialogTitle>
            <DialogDescription>The secret is shown once; nothing is emailed.</DialogDescription>
          </DialogHeader>
          <UserErrorAlert error={error} labelOf={labelOf} />
          <fieldset className="space-y-2">
            <legend className="sr-only">Reset method</legend>
            <label className="flex cursor-pointer gap-3 rounded-md border border-border p-3 has-[:checked]:border-primary/60">
              <input
                type="radio"
                name="reset-mode"
                value="link"
                checked={mode === 'link'}
                onChange={() => setMode('link')}
                className="mt-1 accent-primary"
              />
              <span>
                <span className="block text-sm font-medium">One-time reset link</span>
                <span className="block text-xs text-muted-foreground">
                  The user picks their own password. A newer link replaces this one.
                </span>
              </span>
            </label>
            <label className="flex cursor-pointer gap-3 rounded-md border border-border p-3 has-[:checked]:border-primary/60">
              <input
                type="radio"
                name="reset-mode"
                value="temp"
                checked={mode === 'temp'}
                onChange={() => setMode('temp')}
                className="mt-1 accent-primary"
              />
              <span>
                <span className="block text-sm font-medium">Temporary password</span>
                <span className="block text-xs text-muted-foreground">
                  Signs the user out everywhere and forces a password change at next sign-in.
                </span>
              </span>
            </label>
          </fieldset>
          {mode === 'link' && (
            <div className="flex items-center gap-2">
              <Checkbox
                id="reset-revoke"
                checked={revokeSessions}
                onCheckedChange={(v) => setRevokeSessions(v === true)}
              />
              <Label htmlFor="reset-revoke" className="text-sm font-normal">
                Sign the user out everywhere now
              </Label>
            </div>
          )}
          {isExternal && (
            <p className="text-xs text-amber-400">
              This user signs in with {user.auth_provider}. A reset also enables password sign-in for them.
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="destructive" disabled={busy}>
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Reset password
            </Button>
          </DialogFooter>
        </form>
      )}
    </>
  )
}
