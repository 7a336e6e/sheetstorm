'use client'

/**
 * Active sign-in sessions of one user (`/users/:id/sessions`): device, IP,
 * sign-in method, created and last-seen times; revoke one, or sign out every
 * other device (self) / every session (admin). Revoking a session kills its
 * tokens at once; other sessions keep working.
 *
 * Self needs nothing extra; another user's sessions need users:manage in the
 * same organization (the server also requires outranking them to revoke).
 */
import { useCallback, useEffect, useState } from 'react'
import { Laptop, Loader2, LogOut, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Timestamp } from '@/components/ui/timestamp'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { describeUserAgent, sessions as sessionsApi } from '@/lib/endpoints/security'
import { describeError, notifyError, notifySuccess } from '@/lib/errors'
import type { UserSession } from '@/types'

const METHOD_LABELS: Record<string, string> = {
  password: 'Password',
  github: 'GitHub',
  supabase: 'Supabase',
  refresh: 'Restored',
}

export interface SessionsCardProps {
  userId: string
  /** The signed-in user's own sessions ("Sign out other devices"). */
  self?: boolean
  /** Shown in admin copy, e.g. the user's name. */
  userLabel?: string
  className?: string
}

export function SessionsCard({ userId, self = false, userLabel, className }: SessionsCardProps) {
  const confirm = useConfirm()
  const [items, setItems] = useState<UserSession[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const page = await sessionsApi.list(userId)
      setItems(page.items)
    } catch (err) {
      setItems(null)
      setError(describeError(err).description)
    }
  }, [userId])

  useEffect(() => {
    void load()
  }, [load])

  const revokeOne = async (session: UserSession) => {
    const ok = await confirm({
      title: session.current ? 'Sign out this session?' : 'Revoke session?',
      description: session.current
        ? 'This is the session you are using now; you will be signed out.'
        : `${describeUserAgent(session.user_agent)}${session.ip_address ? ` (${session.ip_address})` : ''} will be signed out immediately.`,
      confirmLabel: session.current ? 'Sign out' : 'Revoke',
      variant: 'destructive',
    })
    if (!ok) return
    setBusy(session.id)
    try {
      await sessionsApi.revoke(userId, session.id)
      notifySuccess('Session revoked')
      await load()
    } catch (err) {
      notifyError(err, 'revoke the session')
    } finally {
      setBusy(null)
    }
  }

  const revokeAll = async () => {
    const ok = await confirm({
      title: self ? 'Sign out other devices?' : 'Revoke all sessions?',
      description: self
        ? 'Every other browser and device signed in to your account is signed out. This session stays signed in.'
        : `Every session of ${userLabel ?? 'this user'} is signed out immediately.`,
      confirmLabel: self ? 'Sign out others' : 'Revoke all',
      variant: 'destructive',
    })
    if (!ok) return
    setBusy('all')
    try {
      const res = await sessionsApi.revokeAll(userId, { exceptCurrent: self })
      notifySuccess(res.revoked === 1 ? '1 session revoked' : `${res.revoked} sessions revoked`)
      await load()
    } catch (err) {
      notifyError(err, self ? 'sign out other devices' : 'revoke the sessions')
    } finally {
      setBusy(null)
    }
  }

  const others = (items ?? []).filter((s) => !s.current)

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">{self ? 'Your sessions' : 'Sessions'}</CardTitle>
            <CardDescription>
              {self
                ? 'Browsers and devices signed in to your account.'
                : `Active sign-ins of ${userLabel ?? 'this user'}.`}
            </CardDescription>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={() => void load()} aria-label="Refresh sessions">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && <p className="text-sm text-destructive">{error}</p>}
        {items === null && !error && (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Loading sessions" />
        )}
        {items !== null && items.length === 0 && (
          <p className="text-sm text-muted-foreground">No active sessions.</p>
        )}
        {items !== null && items.length > 0 && (
          <ul className="divide-y divide-white/10 rounded-md border border-white/10" aria-label="Active sessions">
            {items.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 p-3">
                <div className="flex min-w-0 items-start gap-3">
                  <Laptop className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                  <div className="min-w-0 space-y-0.5">
                    <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      <span className="truncate">{describeUserAgent(s.user_agent)}</span>
                      {s.current && <Badge variant="default" className="text-[10px]">This session</Badge>}
                      {s.auth_method && (
                        <Badge variant="outline" className="text-[10px]">
                          {METHOD_LABELS[s.auth_method] ?? s.auth_method}
                        </Badge>
                      )}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {s.ip_address ?? 'Unknown IP'} · signed in <Timestamp value={s.created_at} seconds={false} /> ·
                      last active <Timestamp value={s.last_seen_at} seconds={false} />
                    </p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void revokeOne(s)}
                  disabled={busy !== null}
                  aria-label={s.current ? 'Sign out this session' : `Revoke session ${describeUserAgent(s.user_agent)}`}
                >
                  {busy === s.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : s.current ? 'Sign out' : 'Revoke'}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {items !== null && (self ? others.length > 0 : items.length > 0) && (
          <Button variant="outline" className="w-full" onClick={() => void revokeAll()} disabled={busy !== null}>
            {busy === 'all' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <LogOut className="mr-2 h-4 w-4" />}
            {self ? 'Sign out other devices' : 'Revoke all sessions'}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
