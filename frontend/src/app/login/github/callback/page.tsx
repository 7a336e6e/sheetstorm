"use client"

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuthStore } from '@/lib/store'
import api from '@/lib/api'
import { Shield, Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function GitHubCallbackPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [error, setError] = useState<string | null>(null)

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

        if (!res.ok) {
          setError(data.message || 'GitHub authentication failed.')
          return
        }

        // Store tokens and update auth state
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
      } catch {
        setError('Could not reach the authentication server.')
      }
    }

    exchangeCode()
  }, [searchParams, router])

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-sm text-center space-y-6">
        <div className="flex items-center justify-center gap-2 mb-4">
          <Shield className="h-8 w-8 text-primary" />
          <span className="text-2xl font-bold">SheetStorm</span>
        </div>

        {error ? (
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
