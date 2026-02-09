/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuthStore } from '@/lib/store'
import { supabase } from '@/lib/supabase'
import { Button } from '@/components/ui/button'
import { Input, PasswordInput } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/components/ui/use-toast'
import { Shield, ArrowRight, Loader2, CheckCircle2, KeyRound, Github } from 'lucide-react'

export default function LoginPage() {
  const router = useRouter()
  const { login } = useAuthStore()
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mfaRequired, setMfaRequired] = useState(false)
  const [mfaCode, setMfaCode] = useState('')
  const [githubLoading, setGithubLoading] = useState(false)

  const handleGitHubLogin = async () => {
    setGithubLoading(true)
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'github',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
        },
      })
      if (error) {
        toast({
          title: 'GitHub SSO unavailable',
          description: error.message,
          variant: 'destructive',
        })
      }
    } catch {
      toast({
        title: 'GitHub SSO unavailable',
        description: 'Could not initiate GitHub sign-in.',
        variant: 'destructive',
      })
    } finally {
      setGithubLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)

    try {
      await login(email, password, mfaRequired ? mfaCode : undefined)
      toast({
        title: 'Welcome back!',
        description: 'You have successfully logged in.',
      })
      router.push('/dashboard')
    } catch (error: any) {
      // Check if this is an MFA challenge
      if (error?.mfa_required || error?.error === 'mfa_required') {
        setMfaRequired(true)
        toast({
          title: 'MFA Required',
          description: 'Enter the code from your authenticator app.',
        })
      } else {
        toast({
          title: 'Login failed',
          description: error instanceof Error ? error.message : 'Invalid credentials',
          variant: 'destructive',
        })
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-background">
      {/* Left Side: Brand Panel */}
      <div className="hidden md:flex md:w-1/2 lg:w-3/5 bg-slate-950 relative overflow-hidden items-center justify-center p-12">
        {/* Abstract Background Elements */}
        <div className="absolute top-[-10%] -left-10 w-96 h-96 bg-primary/10 rounded-full blur-3xl" />
        <div className="absolute bottom-[-10%] -right-10 w-96 h-96 bg-secondary/10 rounded-full blur-3xl" />
        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-10" />
        
        <div className="relative z-10 max-w-xl">
          <div className="flex items-center gap-3 mb-8">
            <div className="p-3 bg-primary/10 rounded-xl border border-primary/20 backdrop-blur-sm shadow-[0_0_20px_-5px_rgba(6,182,212,0.3)]">
              <Shield className="h-10 w-10 text-primary" />
            </div>
            <h1 className="text-4xl font-bold tracking-tight text-white">SheetStorm</h1>
          </div>
          
          <h2 className="text-3xl font-semibold text-white mb-6 leading-tight">
            Enterprise-grade Incident Response <br/>
            <span className="text-primary">Accelerated by Intelligence.</span>
          </h2>
          
          <p className="text-lg text-slate-400 mb-10 leading-relaxed">
            The unified platform for security teams to visualize, analyze, and automate threat containment in real-time.
          </p>
          
          <div className="space-y-4">
            {[
              "Automated Attack Path Visualization",
              "Incident Response Lifecycle Workflow",
              "Real-time Team Collaboration",
              "Secure Artifact \u0026 Chain of Custody"
            ].map((feature, i) => (
              <div key={i} className="flex items-center gap-3 text-slate-300">
                <CheckCircle2 className="h-5 w-5 text-primary" />
                <span className="font-medium">{feature}</span>
              </div>
            ))}
          </div>
        </div>
        
        {/* Footer info on brand side */}
        <div className="absolute bottom-8 left-12 text-slate-500 text-sm">
          &copy; 2026 SheetStorm Systems. All rights reserved.
        </div>
      </div>

      {/* Right Side: Login Form */}
      <div className="flex-1 flex items-center justify-center p-8 md:p-12 lg:p-24 bg-background">
        <div className="w-full max-w-[400px] space-y-8">
          {/* Mobile Logo */}
          <div className="md:hidden flex items-center gap-2 mb-8 justify-center">
            <Shield className="h-8 w-8 text-primary" />
            <span className="text-2xl font-bold">SheetStorm</span>
          </div>

          <div className="space-y-2">
            <h3 className="text-3xl font-bold tracking-tight">Sign in</h3>
            <p className="text-muted-foreground">
              Enter your credentials to access your security dashboard
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email">Work Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={isLoading}
                className="h-12"
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
                <Link
                  href="/forgot-password"
                  className="text-sm font-medium text-primary hover:text-primary/80 transition-colors"
                >
                  Forgot password?
                </Link>
              </div>
              <PasswordInput
                id="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isLoading}
                className="h-12"
              />
            </div>

            {mfaRequired && (
              <div className="space-y-2">
                <Label htmlFor="mfa-code" className="flex items-center gap-2">
                  <KeyRound className="h-4 w-4" />
                  Authenticator Code
                </Label>
                <Input
                  id="mfa-code"
                  type="text"
                  inputMode="numeric"
                  placeholder="000000"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  required
                  disabled={isLoading}
                  className="h-12 font-mono text-center text-lg tracking-widest"
                  autoComplete="one-time-code"
                  autoFocus
                />
              </div>
            )}

            <Button type="submit" className="w-full h-12 text-base font-semibold shadow-[0_0_20px_-5px_rgba(6,182,212,0.4)]" disabled={isLoading}>
              {isLoading ? (
                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              ) : (
                <>
                  Sign in to Dashboard
                  <ArrowRight className="ml-2 h-5 w-5" />
                </>
              )}
            </Button>
          </form>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-background px-4 text-muted-foreground font-medium">Corporate SSO</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <Button
              variant="outline"
              className="h-11 border-primary/10 hover:border-primary/30 bg-primary/5"
              onClick={handleGitHubLogin}
              disabled={githubLoading || isLoading}
            >
              {githubLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Github className="mr-2 h-4 w-4" />
              )}
              GitHub
            </Button>
            <Button variant="outline" className="h-11 border-primary/10 hover:border-primary/30 bg-primary/5" disabled>
              Azure AD
            </Button>
            <Button variant="outline" className="h-11 border-primary/10 hover:border-primary/30 bg-primary/5" disabled>
              Okta
            </Button>
          </div>

          <p className="text-center text-sm text-muted-foreground">
            Don't have an account?{' '}
            <Link href="/register" className="text-primary font-semibold hover:underline">
              Contact Administrator
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}