'use client'

/**
 * Complete an admin-issued password reset. The token arrives in the URL
 * fragment (`/auth/reset-password#token=…`): read once, stripped from the
 * address bar, kept in memory only. Success revokes every session of the
 * user; they then sign in with the new password.
 */
import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { isApiError } from '@/lib/api'
import { accountPublic, isPasswordValid, takeHashToken } from '@/lib/endpoints/users-admin'
import { AccountCard, PasswordFields } from '@/components/users/PasswordFields'
import { describeUserError } from '@/components/users/lifecycle-errors'

const INVALID = 'This reset link is invalid or has expired. Ask your administrator for a new one.'

export default function ResetPasswordPage() {
  const tokenRef = useRef<string | null>(null)
  const readRef = useRef(false)
  const [state, setState] = useState<'loading' | 'invalid' | 'ready' | 'done'>('loading')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!readRef.current) {
      readRef.current = true
      tokenRef.current = takeHashToken()
    }
    // The link is only checked on submit (single use, consumed atomically).
    setState(tokenRef.current ? 'ready' : 'invalid')
  }, [])

  const canSubmit = isPasswordValid(password) && password === confirm && !busy

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const token = tokenRef.current
    if (!token || !canSubmit) return
    setBusy(true)
    setError(null)
    try {
      await accountPublic.completePasswordReset({ token, new_password: password })
      tokenRef.current = null
      setPassword('')
      setConfirm('')
      setState('done')
    } catch (err) {
      if (isApiError(err) && err.code === 'reset_invalid') {
        tokenRef.current = null
        setState('invalid')
      } else {
        // Policy errors (400 bad_request): the link was not consumed, retry.
        setError(describeUserError(err).description)
      }
    } finally {
      setBusy(false)
    }
  }

  if (state === 'loading') {
    return (
      <AccountCard title="Reset password">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-label="Loading" />
      </AccountCard>
    )
  }

  if (state === 'invalid') {
    return (
      <AccountCard title="Reset link not valid">
        <p role="alert" className="text-sm text-muted-foreground">
          {INVALID}
        </p>
        <Link href="/login" className="text-sm text-primary hover:underline">
          Go to sign in
        </Link>
      </AccountCard>
    )
  }

  if (state === 'done') {
    return (
      <AccountCard title="Password updated">
        <p role="status" className="text-sm text-muted-foreground">
          Your password has been reset and every existing session was signed out. Sign in with your new password.
        </p>
        <Button asChild className="w-full">
          <Link href="/login">Sign in</Link>
        </Button>
      </AccountCard>
    )
  }

  return (
    <AccountCard title="Choose a new password" subtitle="This link works once.">
      <form onSubmit={submit} className="space-y-4">
        {error && (
          <p role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
            {error}
          </p>
        )}
        <PasswordFields
          password={password}
          confirm={confirm}
          onPassword={setPassword}
          onConfirm={setConfirm}
          disabled={busy}
        />
        <Button type="submit" className="h-11 w-full" disabled={!canSubmit}>
          {busy && <Loader2 className="mr-2 h-5 w-5 animate-spin" />}
          Set password
        </Button>
      </form>
    </AccountCard>
  )
}
