/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { useState, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useAuthStore } from '@/lib/store'
import { supabase } from '@/lib/supabase'
import { Button } from '@/components/ui/button'
import { Input, PasswordInput } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { useToast } from '@/components/ui/use-toast'
import { ArrowRight, Loader2, CheckCircle2, KeyRound, Github, Check, X } from 'lucide-react'
import { SheetStormLogo } from '@/components/landing/SheetStormLogo'
import { cn } from '@/lib/utils'

function PasswordCheck({ met, label }: { met: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      {met ? (
        <Check className="h-3 w-3 text-green-600 dark:text-green-400" />
      ) : (
        <X className="h-3 w-3 text-muted-foreground" />
      )}
      <span className={cn(met ? 'text-green-600 dark:text-green-400' : 'text-muted-foreground')}>
        {label}
      </span>
    </div>
  )
}

function LoginPageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const initialTab = searchParams.get('tab') === 'register' ? 'register' : 'login'
  const { login, register } = useAuthStore()
  const { toast } = useToast()

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

  // Password validation for registration
  const passwordChecks = {
    length: regPassword.length >= 12,
    uppercase: /[A-Z]/.test(regPassword),
    lowercase: /[a-z]/.test(regPassword),
    number: /[0-9]/.test(regPassword),
    special: /[^A-Za-z0-9]/.test(regPassword),
  }
  const isPasswordValid = Object.values(passwordChecks).every(Boolean)
  const passwordsMatch = regPassword === regConfirmPassword && regConfirmPassword.length > 0

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
        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-10" />
        
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

          <Tabs defaultValue={initialTab} className="w-full">
            <TabsList className="grid w-full grid-cols-2 mb-6">
              <TabsTrigger value="login">Sign In</TabsTrigger>
              <TabsTrigger value="register">Create Account</TabsTrigger>
            </TabsList>

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
                    <div className="flex items-center justify-between">
                      <Label htmlFor="login-password">Password</Label>
                      <Link
                        href="/forgot-password"
                        className="text-xs font-medium text-primary hover:text-primary/80 transition-colors"
                      >
                        Forgot password?
                      </Link>
                    </div>
                    <PasswordInput
                      id="login-password"
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      disabled={isLoading}
                      className="h-11"
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

                {/* SSO Divider */}
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
                  <Button variant="outline" className="h-10 border-primary/10 hover:border-primary/30 bg-primary/5" disabled>
                    Azure AD
                  </Button>
                  <Button variant="outline" className="h-10 border-primary/10 hover:border-primary/30 bg-primary/5" disabled>
                    Okta
                  </Button>
                </div>
              </div>
            </TabsContent>

            {/* ─── Register Tab ─── */}
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
                    {regPassword.length > 0 && (
                      <div className="grid grid-cols-2 gap-1.5 mt-2 text-xs">
                        <PasswordCheck met={passwordChecks.length} label="12+ characters" />
                        <PasswordCheck met={passwordChecks.uppercase} label="Uppercase" />
                        <PasswordCheck met={passwordChecks.lowercase} label="Lowercase" />
                        <PasswordCheck met={passwordChecks.number} label="Number" />
                        <PasswordCheck met={passwordChecks.special} label="Special char" />
                      </div>
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
          </Tabs>
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