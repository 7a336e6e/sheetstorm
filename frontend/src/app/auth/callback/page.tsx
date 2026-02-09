"use client"

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import { useAuthStore } from '@/lib/store'
import api from '@/lib/api'
import { Shield, Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function AuthCallbackPage() {
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const handleCallback = async () => {
      try {
        // Supabase auto-parses the hash fragment and sets the session
        const { data, error: sessionError } = await supabase.auth.getSession()

        if (sessionError) {
          setError(sessionError.message)
          return
        }

        if (!data.session) {
          setError('No session received. Please try signing in again.')
          return
        }

        // Exchange Supabase token for backend JWT
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000/api/v1'
        const res = await fetch(`${apiUrl}/auth/supabase`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ access_token: data.session.access_token }),
        })

        const result = await res.json()

        if (!res.ok) {
          setError(result.message || 'Backend authentication failed.')
          return
        }

        // Store tokens and update auth state
        api.setToken(result.access_token)
        localStorage.setItem('access_token', result.access_token)
        if (result.refresh_token) {
          localStorage.setItem('refresh_token', result.refresh_token)
        }
        useAuthStore.setState({
          user: result.user,
          isAuthenticated: true,
          isLoading: false,
        })

        router.push('/dashboard')
      } catch {
        setError('An unexpected error occurred during sign-in.')
      }
    }

    handleCallback()
  }, [router])

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
            <p className="text-muted-foreground">Completing sign-in…</p>
          </div>
        )}
      </div>
    </div>
  )
}
