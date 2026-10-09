'use client'

/**
 * Change your password (signed in). Used for the forced change after an
 * admin temporary-password reset or the seeded bootstrap admin: while
 * `must_change_password` is set, every other API call answers 403
 * `password_change_required` and the app routes here.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { PasswordInput } from '@/components/ui/input'
import { isApiError } from '@/lib/api'
import { accountPublic, isPasswordValid } from '@/lib/endpoints/users-admin'
import { useAuthStore } from '@/lib/store'
import type { AdminUser } from '@/types'
import { AccountCard, PasswordFields } from '@/components/users/PasswordFields'
import { describeUserError } from '@/components/users/lifecycle-errors'
import { usePasswordPolicy } from '@/hooks/use-password-policy'

export default function ChangePasswordPage() {
  const router = useRouter()
  const { user, isAuthenticated, isLoading, logout } = useAuthStore()
  const forced = !!(user as AdminUser | null)?.must_change_password

  const [current, setCurrent] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace('/login')
  }, [isLoading, isAuthenticated, router])

  // The signed-in user's org rules (allowed while password_change_required).
  const rules = usePasswordPolicy(isAuthenticated)
  const canSubmit =
    current.length > 0 && isPasswordValid(password, rules) && password === confirm && password !== current && !busy

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      await accountPublic.changePassword({ current_password: current, new_password: password })
      setCurrent('')
      setPassword('')
      setConfirm('')
      // The server cleared must_change_password and re-issued this session's cookies.
      await useAuthStore.getState().refreshUser()
      router.replace('/dashboard')
    } catch (err) {
      // A 401 after the client's silent refresh is "current password is incorrect".
      setError(isApiError(err) && err.status === 401 ? err.message : describeUserError(err).description)
    } finally {
      setBusy(false)
    }
  }

  const signOut = async () => {
    await logout()
    router.replace('/login')
  }

  if (isLoading || !isAuthenticated) {
    return (
      <AccountCard title="Change password">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-label="Loading" />
      </AccountCard>
    )
  }

  return (
    <AccountCard
      title={forced ? 'Set a new password' : 'Change password'}
      subtitle={
        forced
          ? 'Your administrator requires you to choose a new password before continuing.'
          : 'Every other session is signed out after the change.'
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {error && (
          <p role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
            {error}
          </p>
        )}
        <div className="space-y-2">
          <Label htmlFor="current-password">{forced ? 'Temporary password' : 'Current password'}</Label>
          <PasswordInput
            id="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
            required
            disabled={busy}
            className="h-11"
          />
        </div>
        <PasswordFields
          password={password}
          confirm={confirm}
          onPassword={setPassword}
          onConfirm={setConfirm}
          disabled={busy}
          rules={rules}
        />
        {password.length > 0 && password === current && (
          <p className="text-xs text-destructive">Choose a password different from the current one.</p>
        )}
        <Button type="submit" className="h-11 w-full" disabled={!canSubmit}>
          {busy && <Loader2 className="mr-2 h-5 w-5 animate-spin" />}
          Change password
        </Button>
        <Button type="button" variant="ghost" className="w-full" onClick={() => void signOut()}>
          Sign out
        </Button>
      </form>
    </AccountCard>
  )
}
