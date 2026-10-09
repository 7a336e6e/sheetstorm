'use client'

/**
 * Accept an invitation. The token arrives in the URL fragment
 * (`/auth/invite#token=…`), so it never reaches server logs or a Referer; it
 * is read once, stripped from the address bar and kept in memory only.
 * Every invalid state (unknown, expired, revoked, used) shows one message.
 */
import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowRight, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Timestamp } from '@/components/ui/timestamp'
import { isApiError } from '@/lib/api'
import { accountPublic, isPasswordValid, takeHashToken } from '@/lib/endpoints/users-admin'
import { clearCache } from '@/lib/query-cache'
import { useAuthStore } from '@/lib/store'
import type { InviteLookup } from '@/types'
import { AccountCard, PasswordFields } from '@/components/users/PasswordFields'
import { describeUserError } from '@/components/users/lifecycle-errors'

const INVALID = 'This invitation is invalid or has expired. Ask your administrator for a new link.'

export default function InvitePage() {
  const router = useRouter()
  const tokenRef = useRef<string | null>(null)
  const [state, setState] = useState<'loading' | 'invalid' | 'ready'>('loading')
  const [invite, setInvite] = useState<InviteLookup | null>(null)
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const readRef = useRef(false)

  useEffect(() => {
    // Once per mount (refs survive the dev StrictMode effect replay; the hash is gone by then).
    if (!readRef.current) {
      readRef.current = true
      tokenRef.current = takeHashToken()
    }
    const token = tokenRef.current
    if (!token) {
      setState('invalid')
      return
    }
    let cancelled = false
    accountPublic
      .lookupInvite(token)
      .then((res) => {
        if (cancelled) return
        setInvite(res)
        setName(res.name ?? '')
        setState('ready')
      })
      .catch(() => !cancelled && setState('invalid'))
    return () => {
      cancelled = true
    }
  }, [])

  const canSubmit = name.trim().length > 0 && isPasswordValid(password) && password === confirm && !busy

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const token = tokenRef.current
    if (!token || !canSubmit) return
    setBusy(true)
    setError(null)
    // A new session starts: drop anything cached for a previous one.
    clearCache()
    try {
      await accountPublic.acceptInvite({ token, name: name.trim(), password })
      tokenRef.current = null
      await useAuthStore.getState().checkAuth()
      router.replace('/dashboard')
    } catch (err) {
      if (isApiError(err) && err.code === 'invite_invalid') {
        tokenRef.current = null
        setState('invalid')
      } else {
        setError(describeUserError(err).description)
      }
    } finally {
      setBusy(false)
    }
  }

  if (state === 'loading') {
    return (
      <AccountCard title="Join SheetStorm">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-label="Checking invitation" />
      </AccountCard>
    )
  }

  if (state === 'invalid' || !invite) {
    return (
      <AccountCard title="Invitation not valid">
        <p role="alert" className="text-sm text-muted-foreground">
          {INVALID}
        </p>
        <Link href="/login" className="text-sm text-primary hover:underline">
          Go to sign in
        </Link>
      </AccountCard>
    )
  }

  return (
    <AccountCard
      title="Join SheetStorm"
      subtitle={
        <>
          You were invited to{' '}
          <span className="font-medium text-foreground">{invite.organization_name ?? 'SheetStorm'}</span> as{' '}
          <span className="font-medium text-foreground">{invite.email}</span>. The invitation expires{' '}
          <Timestamp value={invite.expires_at} seconds={false} />.
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {error && (
          <p role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
            {error}
          </p>
        )}
        <div className="space-y-2">
          <Label htmlFor="invite-email-ro">Email</Label>
          <Input id="invite-email-ro" value={invite.email} readOnly disabled className="h-11" />
        </div>
        <div className="space-y-2">
          <Label htmlFor="invite-full-name">Full name</Label>
          <Input
            id="invite-full-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={255}
            required
            autoComplete="name"
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
          label="Password"
        />
        <Button type="submit" className="h-11 w-full" disabled={!canSubmit}>
          {busy ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : null}
          Create account
          {!busy && <ArrowRight className="ml-2 h-5 w-5" />}
        </Button>
      </form>
    </AccountCard>
  )
}
