/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useAuthStore } from '@/lib/store'
import { supabase } from '@/lib/supabase'
import { Button } from '@/components/ui/button'
import { Input, PasswordInput } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { useToast } from '@/components/ui/use-toast'
import { ArrowRight, Loader2, CheckCircle2, KeyRound, Github, ShieldCheck } from 'lucide-react'
import { SheetStormLogo } from '@/components/landing/SheetStormLogo'
import { readSessionRevokedReason, sessionRevokedMessage } from '@/components/users/session-revoked'
import { PasswordChecklist, PasswordRulesHint } from '@/components/settings/PasswordChecklist'
import { meetsPasswordRules } from '@/lib/endpoints/security'
import { usePasswordPolicy } from '@/hooks/use-password-policy'
import { ssoProviders, ssoStartHref } from '@/lib/endpoints/sso'
import { safeNextPath, ssoErrorMessage } from '@/lib/sso'
import { api } from '@/lib/api'
import type { SsoLoginProviders, User } from '@/types'

/** Muted notices for `/login?reason=…` (e.g. after the socket `session:revoked` event). */
const LOGIN_NOTICES: Record<string, string> = {
  session_revoked: 'Your session was ended by an administrator. Sign in again to continue.',
}

function LoginPageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { login, register } = useAuthStore()
  const { toast } = useToast()

  // Registration enabled status
  const [registrationEnabled, setRegistrationEnabled] = useState(true)

  useEffect(() => {
    fetch('/api/v1/auth/registration-status')
      .then(res => res.json())
      .then(data => setRegistrationEnabled(data.registration_enabled !== false))
      .catch(() => setRegistrationEnabled(true))
  }, [])

  const initialTab = searchParams.get('tab') === 'register' && registrationEnabled ? 'register' : 'login'
  const reasonParam = searchParams.get('reason') ?? ''
  // Per-reason copy for a live session revocation (stored before the redirect).
  // This component renders client-side only (useSearchParams under Suspense).
  const [revokedCopy] = useState(() => {
    if (reasonParam !== 'session_revoked') return null
    const reason = readSessionRevokedReason()
    return reason ? sessionRevokedMessage(reason) : null
  })
  const notice = revokedCopy ?? LOGIN_NOTICES[reasonParam]
  // Single sign-on: refused sign-ins come back as ?sso_error=<code>; with
  // SheetStorm TOTP enrolled the callback sends ?sso=mfa (the pre-auth token
  // is an httpOnly cookie, so only the code is posted).
  const ssoError = ssoErrorMessage(searchParams.get('sso_error'))
  const ssoMfa = searchParams.get('sso') === 'mfa'
  const nextPath = safeNextPath(searchParams.get('next'))
  const [ssoOptions, setSsoOptions] = useState<SsoLoginProviders>({ providers: [], github: false })
  const [ssoMfaCode, setSsoMfaCode] = useState('')
  const [ssoMfaBusy, setSsoMfaBusy] = useState(false)
  const supabaseGithub = !!process.env.NEXT_PUBLIC_SUPABASE_URL
  const showGithub = ssoOptions.github || supabaseGithub

  useEffect(() => {
    ssoProviders.loginOptions().then(setSsoOptions).catch(() => {})
  }, [])

  // Login state
  const [isLoading, setIsLoading] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mfaRequired, setMfaRequired] = useState(false)
  const [mfaCode, setMfaCode] = useState('')
  const [githubLoading, setGithubLoading] = useState(false)

  // Register state
  const [regLoading, setRegLoading] = useState(false)
  const [regName, setRegName] = useState('')
  const [regEmail, setRegEmail] = useState('')
  const [regPassword, setRegPassword] = useState('')
  const [regConfirmPassword, setRegConfirmPassword] = useState('')

  // Password rules for registration: the platform organization's security
  // policy (hints; the server validates).
  const passwordRules = usePasswordPolicy(registrationEnabled)
  const isPasswordValid = meetsPasswordRules(regPassword, passwordRules)
  const passwordsMatch = regPassword === regConfirmPassword && regConfirmPassword.length > 0

  const handleGitHubLogin = async () => {
    setGithubLoading(true)
    if (ssoOptions.github) {
      try {
        const { url } = await api.get<{ url: string }>('/auth/github')
        window.location.assign(url)
      } catch {
        toast({ title: 'GitHub SSO unavailable', description: 'Could not initiate GitHub sign-in.', variant: 'destructive' })
        setGithubLoading(false)
      }
      return
    }
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

  const handleSsoMfa = async (e: React.FormEvent) => {
    e.preventDefault()
    setSsoMfaBusy(true)
    try {
      const res = await api.post<{ user: User }>('/auth/mfa/complete', { mfa_code: ssoMfaCode })
      useAuthStore.setState({ user: res.user, isAuthenticated: true, isLoading: false })
      router.push(nextPath)
    } catch (error) {
      setSsoMfaCode('')
      toast({
        title: 'Verification failed',
        description: error instanceof Error ? error.message : 'Invalid code. If it keeps failing, sign in again.',
        variant: 'destructive',
      })
    } finally {
      setSsoMfaBusy(false)
    }
  }

  const handleLogin = async (e: React.FormEvent) => {
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

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!isPasswordValid) {
      toast({
        title: 'Password requirements not met',
        description: 'Please ensure your password meets all requirements.',
        variant: 'destructive',
      })
      return
    }

    if (!passwordsMatch) {
      toast({
        title: 'Passwords do not match',
        description: 'Please make sure your passwords match.',
        variant: 'destructive',
      })
      return
    }

    setRegLoading(true)

    try {
      await register(regEmail, regPassword, regName)
      toast({
        title: 'Account created!',
        description: 'Welcome to SheetStorm.',
      })
      router.push('/dashboard')
    } catch (error) {
      toast({
        title: 'Registration failed',
        description: error instanceof Error ? error.message : 'Could not create account',
        variant: 'destructive',
      })
    } finally {
      setRegLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-background">
      {/* Left Side: Brand Panel */}
      <div className="hidden md:flex md:w-1/2 lg:w-3/5 bg-slate-950 relative overflow-hidden items-center justify-center p-12">
        {/* Abstract Background Elements */}
        <div className="absolute top-[-10%] -left-10 w-96 h-96 bg-primary/10 rounded-full blur-3xl" />
        <div className="absolute bottom-[-10%] -right-10 w-96 h-96 bg-secondary/10 rounded-full blur-3xl" />
        {/* Carbon-fibre texture as a CSS pattern (no third-party image request) */}
        <div
          className="absolute inset-0 opacity-10"
          style={{
            backgroundImage:
              'repeating-linear-gradient(45deg, rgba(255,255,255,0.35) 0 1px, transparent 1px 4px), repeating-linear-gradient(-45deg, rgba(0,0,0,0.6) 0 1px, transparent 1px 4px)',
          }}
        />
        
        <div className="relative z-10 max-w-xl">
          <div className="flex items-center gap-3 mb-8">
            <SheetStormLogo size={44} />
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
        

      </div>

      {/* Right Side: Auth Forms */}
      <div className="flex-1 flex items-center justify-center p-8 md:p-12 lg:p-24 bg-background">
        <div className="w-full max-w-[420px] space-y-6">
          {/* Mobile Logo */}
          <div className="md:hidden flex items-center gap-2 mb-8 justify-center">
            <SheetStormLogo size={32} />
            <span className="text-2xl font-bold">SheetStorm</span>
          </div>

          {notice && (
            <p role="status" className="rounded-md border border-white/10 bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
              {notice}
            </p>
          )}
          {ssoError && !ssoMfa && (
            <p role="alert" data-testid="sso-error" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {ssoError}
            </p>
          )}

          {ssoMfa ? (
            <form onSubmit={handleSsoMfa} className="space-y-4" data-testid="sso-mfa-form">
              <div className="space-y-2">
                <h3 className="text-2xl font-bold tracking-tight">Two-step verification</h3>
                <p className="text-sm text-muted-foreground">
                  Your identity provider signed you in. Enter the code from your authenticator app (or a backup code)
                  to finish.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="sso-mfa-code" className="flex items-center gap-2">
                  <KeyRound className="h-4 w-4" />
                  Authenticator Code
                </Label>
                <Input
                  id="sso-mfa-code"
                  type="text"
                  value={ssoMfaCode}
                  onChange={(e) => setSsoMfaCode(e.target.value.replace(/[^0-9A-Fa-f]/g, '').slice(0, 8))}
                  required
                  disabled={ssoMfaBusy}
                  className="h-11 font-mono text-center text-lg tracking-widest"
                  autoComplete="one-time-code"
                  autoFocus
                />
              </div>
              <Button type="submit" className="w-full h-11" disabled={ssoMfaBusy || ssoMfaCode.length < 6}>
                {ssoMfaBusy ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : 'Verify and continue'}
              </Button>
              <Button type="button" variant="link" className="w-full" onClick={() => router.replace('/login')}>
                Start over
              </Button>
            </form>
          ) : (

          <Tabs defaultValue={initialTab} className="w-full">
            {registrationEnabled ? (
              <TabsList className="grid w-full grid-cols-2 mb-6">
                <TabsTrigger value="login">Sign In</TabsTrigger>
                <TabsTrigger value="register">Create Account</TabsTrigger>
              </TabsList>
            ) : (
              <TabsList className="grid w-full grid-cols-1 mb-6">
                <TabsTrigger value="login">Sign In</TabsTrigger>
              </TabsList>
            )}

            {/* ─── Login Tab ─── */}
            <TabsContent value="login">
              <div className="space-y-6">
                <div className="space-y-2">
                  <h3 className="text-2xl font-bold tracking-tight">Welcome back</h3>
                  <p className="text-sm text-muted-foreground">
                    Enter your credentials to access your security dashboard
                  </p>
                </div>

                <form onSubmit={handleLogin} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="login-email">Work Email</Label>
                    <Input
                      id="login-email"
                      type="email"
                      placeholder="name@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      disabled={isLoading}
                      className="h-11"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="login-password">Password</Label>
                    <PasswordInput
                      id="login-password"
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      disabled={isLoading}
                      className="h-11"
                    />
                    <p className="text-xs text-muted-foreground">
                      Forgot your password? Contact your administrator to reset your password.
                    </p>
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
                        className="h-11 font-mono text-center text-lg tracking-widest"
                        autoComplete="one-time-code"
                        autoFocus
                      />
                    </div>
                  )}

                  <Button
                    type="submit"
                    className="w-full h-11 text-base font-semibold shadow-[0_0_20px_-5px_rgba(6,182,212,0.4)]"
                    disabled={isLoading}
                  >
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

                {(showGithub || ssoOptions.providers.length > 0) && (
                  <>
                    <div className="relative">
                      <div className="absolute inset-0 flex items-center">
                        <div className="w-full border-t border-border" />
                      </div>
                      <div className="relative flex justify-center text-xs uppercase">
                        <span className="bg-background px-4 text-muted-foreground font-medium">Single sign-on</span>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="sso-buttons">
                      {ssoOptions.providers.map((p) => (
                        <Button
                          key={p.slug}
                          asChild
                          variant="outline"
                          className="h-10 border-primary/10 hover:border-primary/30 bg-primary/5"
                        >
                          <a href={ssoStartHref(p.start_url, searchParams.get('next'))}>
                            <ShieldCheck className="mr-2 h-4 w-4" />
                            <span className="truncate">{p.name}</span>
                          </a>
                        </Button>
                      ))}
                      {showGithub && (
                        <Button
                          variant="outline"
                          className="h-10 border-primary/10 hover:border-primary/30 bg-primary/5"
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
                      )}
                    </div>
                  </>
                )}
              </div>
            </TabsContent>

            {/* ─── Register Tab ─── */}
            {registrationEnabled && (
            <TabsContent value="register">
              <div className="space-y-6">
                <div className="space-y-2">
                  <h3 className="text-2xl font-bold tracking-tight">Create your account</h3>
                  <p className="text-sm text-muted-foreground">
                    Get started with SheetStorm in minutes
                  </p>
                </div>

                <form onSubmit={handleRegister} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="reg-name">Full Name</Label>
                    <Input
                      id="reg-name"
                      type="text"
                      placeholder="John Doe"
                      value={regName}
                      onChange={(e) => setRegName(e.target.value)}
                      required
                      disabled={regLoading}
                      className="h-11"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="reg-email">Work Email</Label>
                    <Input
                      id="reg-email"
                      type="email"
                      placeholder="name@company.com"
                      value={regEmail}
                      onChange={(e) => setRegEmail(e.target.value)}
                      required
                      disabled={regLoading}
                      className="h-11"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="reg-password">Password</Label>
                    <PasswordInput
                      id="reg-password"
                      placeholder="Create a secure password"
                      value={regPassword}
                      onChange={(e) => setRegPassword(e.target.value)}
                      required
                      disabled={regLoading}
                      className="h-11"
                    />
                    {regPassword.length > 0 ? (
                      <PasswordChecklist password={regPassword} rules={passwordRules} />
                    ) : (
                      <PasswordRulesHint rules={passwordRules} />
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="reg-confirm-password">Confirm Password</Label>
                    <PasswordInput
                      id="reg-confirm-password"
                      placeholder="Confirm your password"
                      value={regConfirmPassword}
                      onChange={(e) => setRegConfirmPassword(e.target.value)}
                      required
                      disabled={regLoading}
                      className="h-11"
                      error={regConfirmPassword.length > 0 && !passwordsMatch}
                    />
                    {regConfirmPassword.length > 0 && !passwordsMatch && (
                      <p className="text-destructive text-xs mt-1">Passwords do not match</p>
                    )}
                  </div>

                  <Button
                    type="submit"
                    className="w-full h-11 text-base font-semibold shadow-[0_0_20px_-5px_rgba(6,182,212,0.4)]"
                    disabled={!isPasswordValid || !passwordsMatch || regLoading}
                  >
                    {regLoading ? (
                      <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    ) : (
                      <>
                        Create Account
                        <ArrowRight className="ml-2 h-5 w-5" />
                      </>
                    )}
                  </Button>
                </form>

                <p className="text-center text-xs text-muted-foreground">
                  By creating an account, you agree to our{' '}
                  <Link href="#" className="underline hover:text-foreground">Terms of Service</Link>
                  {' '}and{' '}
                  <Link href="#" className="underline hover:text-foreground">Privacy Policy</Link>
                </p>
              </div>
            </TabsContent>
            )}
          </Tabs>
          )}
        </div>
      </div>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginPageInner />
    </Suspense>
  )
}