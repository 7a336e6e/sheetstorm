"use client"

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuthStore } from '@/lib/store'
import api from '@/lib/api'
import { Shield, Loader2, AlertCircle, KeyRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export default function GitHubCallbackPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [error, setError] = useState<string | null>(null)
  const [mfaRequired, setMfaRequired] = useState(false)
  const [mfaCode, setMfaCode] = useState('')
  const [preAuthToken, setPreAuthToken] = useState('')
  const [userName, setUserName] = useState('')
  const [isVerifying, setIsVerifying] = useState(false)

  useEffect(() => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    const ghError = searchParams.get('error')

    if (ghError) {
      setError(searchParams.get('error_description') || 'GitHub authorization was denied.')
      return
    }

    if (!code) {
      setError('No authorization code received from GitHub.')
      return
    }

    const exchangeCode = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000/api/v1'
        const res = await fetch(`${apiUrl}/auth/github/callback`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code, state }),
        })

        const data = await res.json()

        if (res.status === 403 && data.mfa_required) {
          setMfaRequired(true)
          setPreAuthToken(data.pre_auth_token)
          setUserName(data.user?.name || data.user?.email || '')
          return
        }

        if (!res.ok) {
          setError(data.message || 'GitHub authentication failed.')
          return
        }

        completeLogin(data)
      } catch {
        setError('Could not reach the authentication server.')
      }
    }

    exchangeCode()
  }, [searchParams, router])

  const completeLogin = (data: { access_token: string; refresh_token?: string; user: any }) => {
    api.setToken(data.access_token)
    localStorage.setItem('access_token', data.access_token)
    if (data.refresh_token) {
      localStorage.setItem('refresh_token', data.refresh_token)
    }
    useAuthStore.setState({
      user: data.user,
      isAuthenticated: true,
      isLoading: false,
    })
    router.push('/dashboard')
  }

  const handleMfaVerify = async () => {
    if (!mfaCode || mfaCode.length < 6) return
    setIsVerifying(true)
    setError(null)

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000/api/v1'
      const res = await fetch(`${apiUrl}/auth/mfa/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pre_auth_token: preAuthToken, mfa_code: mfaCode }),
      })

      const data = await res.json()

      if (!res.ok) {
        setError(data.message || 'MFA verification failed.')
        setMfaCode('')
        return
      }

      completeLogin(data)
    } catch {
      setError('Could not reach the authentication server.')
    } finally {
      setIsVerifying(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-sm text-center space-y-6">
        <div className="flex items-center justify-center gap-2 mb-4">
          <Shield className="h-8 w-8 text-primary" />
          <span className="text-2xl font-bold">SheetStorm</span>
        </div>

        {error && !mfaRequired ? (
          <div className="space-y-4">
            <div className="flex items-center justify-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              <p className="font-medium">Authentication Failed</p>
            </div>
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button variant="outline" onClick={() => router.push('/login')} className="w-full">
              Back to Sign In
            </Button>
          </div>
        ) : mfaRequired ? (
          <div className="space-y-6 text-left">
            <div className="text-center space-y-2">
              <KeyRound className="h-8 w-8 text-primary mx-auto" />
              <h2 className="text-xl font-semibold">Two-Factor Authentication</h2>
              {userName && (
                <p className="text-sm text-muted-foreground">
                  Welcome back, {userName}
                </p>
              )}
              <p className="text-sm text-muted-foreground">
                Enter the code from your authenticator app to continue.
              </p>
            </div>

            {error && (
              <div className="p-3 text-sm text-red-500 bg-red-50 dark:bg-red-900/10 rounded-md border border-red-200 dark:border-red-900/20">
                {error}
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="mfa-code">Authenticator Code</Label>
              <Input
                id="mfa-code"
                type="text"
                inputMode="numeric"
                placeholder="000000"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
                className="h-12 font-mono text-center text-lg tracking-widest"
                autoComplete="one-time-code"
                autoFocus
                onKeyDown={(e) => e.key === 'Enter' && handleMfaVerify()}
              />
              <p className="text-xs text-muted-foreground">
                You can also enter a backup code.
              </p>
            </div>

            <Button
              onClick={handleMfaVerify}
              disabled={isVerifying || mfaCode.length < 6}
              className="w-full h-12"
            >
              {isVerifying ? (
                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              ) : null}
              Verify & Sign In
            </Button>

            <Button
              variant="ghost"
              onClick={() => router.push('/login')}
              className="w-full"
            >
              Cancel
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto" />
            <p className="text-muted-foreground">Signing in with GitHub…</p>
          </div>
        )}
      </div>
    </div>
  )
}
