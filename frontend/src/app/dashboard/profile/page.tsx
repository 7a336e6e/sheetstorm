"use client"

/**
 * Profile: account details, password change (org password policy hints),
 * MFA (enrollment forced by the org security policy after its grace period:
 * `?enroll_mfa=1` opens the setup), and the user's own sign-in sessions.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useAuthStore } from '@/lib/store'
import api from '@/lib/api'
import { usePasswordPolicy } from '@/hooks/use-password-policy'
import { meetsPasswordRules } from '@/lib/endpoints/security'
import { PasswordChecklist, PasswordRulesHint } from '@/components/settings/PasswordChecklist'
import { SessionsCard } from '@/components/settings/SessionsCard'
import { Timestamp } from '@/components/ui/timestamp'
import QRCode from 'qrcode'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogBody,
} from '@/components/ui/dialog'
import { useToast } from '@/components/ui/use-toast'
import { TimeModeToggle } from '@/components/ui/time-mode-toggle'
import {
  User as UserIcon,
  Mail,
  Shield,
  ShieldCheck,
  ShieldOff,
  Clock,
  Key,
  Eye,
  EyeOff,
  Check,
  AlertCircle,
  Building,
  UsersRound,
  Copy,
  Loader2,
  Globe,
  AlertTriangle,
} from 'lucide-react'
import type { SecurityStatus, User } from '@/types'

type ProfileUser = User & { mfa_enabled?: boolean; security?: SecurityStatus }

/** Whether the page was opened to enroll MFA (`?enroll_mfa=1`). */
function enrollRequested(): boolean {
  if (typeof window === 'undefined') return false
  return new URLSearchParams(window.location.search).get('enroll_mfa') === '1'
}

interface MFASetupData {
  secret: string
  provisioning_uri: string
  backup_codes: string[]
}

export default function ProfilePage() {
  const { user: authUser, refreshUser } = useAuthStore()
  const { toast } = useToast()
  const [user, setUser] = useState<ProfileUser | null>(null)
  const [loading, setLoading] = useState(true)
  const passwordRules = usePasswordPolicy()

  // Change password state
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showCurrentPassword, setShowCurrentPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [passwordLoading, setPasswordLoading] = useState(false)
  const [passwordError, setPasswordError] = useState('')
  const [passwordSuccess, setPasswordSuccess] = useState('')

  // MFA state
  const [mfaEnabled, setMfaEnabled] = useState(false)
  const [setupData, setSetupData] = useState<MFASetupData | null>(null)
  // QR rendered locally — the provisioning URI contains the TOTP secret and
  // must never be sent to a third-party QR service.
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null)
  const [showSetupDialog, setShowSetupDialog] = useState(false)
  const [showDisableDialog, setShowDisableDialog] = useState(false)
  const [showBackupCodes, setShowBackupCodes] = useState(false)
  const [verifyCode, setVerifyCode] = useState('')
  const [disablePassword, setDisablePassword] = useState('')
  const [mfaLoading, setMfaLoading] = useState(false)
  const [copiedCode, setCopiedCode] = useState<string | null>(null)
  const autoSetupStarted = useRef(false)

  const fetchProfile = useCallback(async () => {
    try {
      const data = await api.get<ProfileUser>('/auth/me')
      setUser(data)
    } catch {
      if (authUser) setUser(authUser as ProfileUser)
    } finally {
      setLoading(false)
    }
  }, [authUser])

  useEffect(() => {
    fetchProfile()
  }, [fetchProfile])

  useEffect(() => {
    if (user) {
      setMfaEnabled(user.mfa_enabled || false)
    }
  }, [user])

  const security = user?.security
  const mfaRequired = !!security?.mfa_required
  const enrollmentRequired = !!security?.mfa_enrollment_required && !mfaEnabled
  const graceEndsAt = !mfaEnabled ? security?.mfa_grace_ends_at ?? null : null

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setPasswordError('')
    setPasswordSuccess('')

    if (newPassword !== confirmPassword) {
      setPasswordError('New passwords do not match')
      return
    }

    if (!meetsPasswordRules(newPassword, passwordRules)) {
      setPasswordError('The new password does not meet the password policy')
      return
    }

    setPasswordLoading(true)
    try {
      await api.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      setPasswordSuccess('Password changed successfully')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err: any) {
      setPasswordError(err?.message || 'Failed to change password')
    } finally {
      setPasswordLoading(false)
    }
  }

  // MFA handlers
  const handleMfaSetup = async () => {
    setMfaLoading(true)
    try {
      const data = await api.post<MFASetupData>('/auth/mfa/setup', {})
      setSetupData(data)
      setQrDataUrl(await QRCode.toDataURL(data.provisioning_uri, { width: 200, margin: 0 }).catch(() => null))
      setShowSetupDialog(true)
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to start MFA setup',
        variant: 'destructive',
      })
    } finally {
      setMfaLoading(false)
    }
  }

  const handleMfaVerify = async () => {
    if (!verifyCode || verifyCode.length < 6) {
      toast({
        title: 'Invalid Code',
        description: 'Please enter a 6-digit code from your authenticator app',
        variant: 'destructive',
      })
      return
    }
    setMfaLoading(true)
    try {
      await api.post('/auth/mfa/verify', { code: verifyCode })
      setMfaEnabled(true)
      setShowSetupDialog(false)
      setShowBackupCodes(true)
      if (enrollRequested()) window.history.replaceState(null, '', window.location.pathname)
      // The store's user.security lifts the forced-enrollment redirect.
      if (refreshUser) await refreshUser()
      void fetchProfile()
      toast({
        title: 'MFA Enabled',
        description: 'Two-factor authentication is now active on your account',
      })
    } catch (error) {
      toast({
        title: 'Verification Failed',
        description: error instanceof Error ? error.message : 'Invalid code. Try again.',
        variant: 'destructive',
      })
    } finally {
      setMfaLoading(false)
      setVerifyCode('')
    }
  }

  const handleMfaDisable = async () => {
    if (!disablePassword) {
      toast({
        title: 'Password Required',
        description: 'Enter your password to disable MFA',
        variant: 'destructive',
      })
      return
    }
    setMfaLoading(true)
    try {
      await api.post('/auth/mfa/disable', { password: disablePassword })
      setMfaEnabled(false)
      setSetupData(null)
      setShowDisableDialog(false)
      if (refreshUser) refreshUser()
      toast({
        title: 'MFA Disabled',
        description: 'Two-factor authentication has been removed from your account',
      })
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to disable MFA',
        variant: 'destructive',
      })
    } finally {
      setMfaLoading(false)
      setDisablePassword('')
    }
  }

  // Forced or requested enrollment opens the setup dialog once.
  useEffect(() => {
    if (loading || mfaEnabled || autoSetupStarted.current) return
    if (enrollmentRequired || enrollRequested()) {
      autoSetupStarted.current = true
      void handleMfaSetup()
    }
    // handleMfaSetup is stable enough for a one-shot start.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, mfaEnabled, enrollmentRequired])

  // The store may predate the policy (persisted user): refresh it so the
  // app-wide enrollment redirect sees the current status.
  useEffect(() => {
    if (enrollRequested() && refreshUser) void refreshUser()
  }, [refreshUser])

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedCode(text)
    setTimeout(() => setCopiedCode(null), 2000)
  }

  const copyAllBackupCodes = () => {
    if (!setupData) return
    navigator.clipboard.writeText(setupData.backup_codes.join('\n'))
    toast({ title: 'Copied', description: 'All backup codes copied to clipboard' })
  }

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '—'
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="grid gap-6 md:grid-cols-2">
          <div className="h-64 bg-muted animate-pulse rounded-lg" />
          <div className="h-64 bg-muted animate-pulse rounded-lg" />
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Profile</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage your account details, security settings, and password
        </p>
      </div>

      {enrollmentRequired && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm"
        >
          <AlertTriangle className="h-5 w-5 shrink-0 text-red-400" aria-hidden />
          <div>
            <p className="font-medium">Set up two-factor authentication to continue</p>
            <p className="text-muted-foreground">
              Your organization requires multi-factor authentication. Until you enroll, the rest of SheetStorm is
              unavailable.
            </p>
          </div>
        </div>
      )}
      {!enrollmentRequired && mfaRequired && graceEndsAt && (
        <div
          role="status"
          className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm"
        >
          <AlertTriangle className="h-5 w-5 shrink-0 text-amber-400" aria-hidden />
          <div>
            <p className="font-medium">Two-factor authentication is required</p>
            <p className="text-muted-foreground">
              Set it up before <Timestamp value={graceEndsAt} seconds={false} />; after that you can only enroll
              until you do.
            </p>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Account Information */}
        <Card className="lg:row-span-2">
          <CardHeader>
            <CardTitle className="text-base">Account Information</CardTitle>
            <CardDescription>Your personal and organizational details</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center text-2xl font-medium">
                {user?.name?.charAt(0).toUpperCase() || 'U'}
              </div>
              <div>
                <p className="font-medium text-lg">{user?.name}</p>
                <p className="text-sm text-muted-foreground">{user?.email}</p>
              </div>
            </div>

            <div className="border-t border-border" />

            <div className="space-y-3">
              <div className="flex items-center gap-3 text-sm">
                <Mail className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground w-24">Email</span>
                <span className="font-medium">{user?.email}</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <UserIcon className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground w-24">Name</span>
                <span className="font-medium">{user?.name}</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <Shield className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground w-24">Roles</span>
                <div className="flex flex-wrap gap-1">
                  {user?.roles?.map((role) => (
                    <Badge key={role} variant="default" className="text-xs">
                      {role}
                    </Badge>
                  ))}
                </div>
              </div>
              {user?.organizational_role && (
                <div className="flex items-center gap-3 text-sm">
                  <Building className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-muted-foreground w-24">Org Role</span>
                  <span className="font-medium">{user.organizational_role}</span>
                </div>
              )}
              {user?.teams && user.teams.length > 0 && (
                <div className="flex items-center gap-3 text-sm">
                  <UsersRound className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-muted-foreground w-24">Teams</span>
                  <div className="flex flex-wrap gap-1">
                    {user.teams.map((team) => (
                      <Badge key={team.id} variant="outline" className="text-xs">
                        {team.name}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {user?.auth_provider && (
                <div className="flex items-center gap-3 text-sm">
                  <Key className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-muted-foreground w-24">Auth</span>
                  <Badge variant="outline" className="text-xs capitalize">
                    {user.auth_provider}
                  </Badge>
                </div>
              )}
              <div className="flex items-center gap-3 text-sm">
                <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground w-24">Last Login</span>
                <span className="text-muted-foreground text-xs">
                  {formatDate(user?.last_login)}
                </span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground w-24">Member Since</span>
                <span className="text-muted-foreground text-xs">
                  {formatDate(user?.created_at)}
                </span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <Globe className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground w-24">Timestamps</span>
                <TimeModeToggle />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Change Password */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Change Password</CardTitle>
            <CardDescription>
              Update your password to keep your account secure
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleChangePassword} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="current-password">Current Password</Label>
                <div className="relative">
                  <Input
                    id="current-password"
                    type={showCurrentPassword ? 'text' : 'password'}
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="Enter current password"
                    required
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
                    onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                  >
                    {showCurrentPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="new-password">New Password</Label>
                <div className="relative">
                  <Input
                    id="new-password"
                    type={showNewPassword ? 'text' : 'password'}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Enter new password"
                    required
                    minLength={passwordRules.min_length}
                    autoComplete="new-password"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                  >
                    {showNewPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                {newPassword.length > 0 ? (
                  <PasswordChecklist password={newPassword} rules={passwordRules} />
                ) : (
                  <PasswordRulesHint rules={passwordRules} />
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm-password">Confirm New Password</Label>
                <Input
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm new password"
                  required
                  minLength={passwordRules.min_length}
                  autoComplete="new-password"
                />
              </div>

              {passwordError && (
                <div className="flex items-center gap-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {passwordError}
                </div>
              )}

              {passwordSuccess && (
                <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
                  <Check className="h-4 w-4 shrink-0" />
                  {passwordSuccess}
                </div>
              )}

              <Button
                type="submit"
                disabled={passwordLoading || !currentPassword || !newPassword || !confirmPassword}
                className="w-full"
              >
                {passwordLoading ? 'Changing...' : 'Change Password'}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Two-Factor Authentication */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">Two-Factor Authentication</CardTitle>
                <CardDescription>
                  Secure your account with a TOTP authenticator app
                </CardDescription>
              </div>
              <Badge variant={mfaEnabled ? 'default' : 'outline'}>
                {mfaEnabled ? 'Enabled' : 'Disabled'}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              {mfaEnabled ? (
                <ShieldCheck className="h-8 w-8 text-green-400" />
              ) : (
                <ShieldOff className="h-8 w-8 text-muted-foreground" />
              )}
              <p className="text-sm text-muted-foreground">
                {mfaEnabled
                  ? 'MFA is active. Your account has an extra layer of protection.'
                  : 'MFA is not configured. Enable it to add an extra security layer.'}
              </p>
            </div>
            {mfaEnabled && mfaRequired ? (
              <p className="text-xs text-muted-foreground">
                Your organization requires two-factor authentication, so it cannot be turned off.
              </p>
            ) : mfaEnabled ? (
              <Button
                variant="destructive"
                className="w-full"
                onClick={() => setShowDisableDialog(true)}
              >
                <ShieldOff className="mr-2 h-4 w-4" />
                Disable MFA
              </Button>
            ) : (
              <Button className="w-full" onClick={handleMfaSetup} disabled={mfaLoading}>
                {mfaLoading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Shield className="mr-2 h-4 w-4" />
                )}
                Set Up MFA
              </Button>
            )}
          </CardContent>
        </Card>
      </div>

      {user && !enrollmentRequired && <SessionsCard userId={user.id} self />}

      {/* MFA Setup Dialog */}
      <Dialog open={showSetupDialog} onOpenChange={setShowSetupDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Set Up Authenticator</DialogTitle>
            <DialogDescription>
              Scan the QR code with your authenticator app (Google Authenticator, Authy, 1Password, etc.)
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            {setupData && (
              <div className="space-y-6">
                <div className="flex justify-center">
                  <div className="bg-white p-4 rounded-lg">
                    {qrDataUrl ? (
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img src={qrDataUrl} alt="MFA QR Code" width={200} height={200} />
                    ) : (
                      <div className="h-[200px] w-[200px]" />
                    )}
                  </div>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">
                    Or enter this key manually:
                  </Label>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 px-3 py-2 bg-muted rounded text-sm font-mono break-all">
                      {setupData.secret}
                    </code>
                    <Button
                      variant="outline"
                      size="icon-sm"
                      onClick={() => copyToClipboard(setupData.secret)}
                    >
                      {copiedCode === setupData.secret ? (
                        <Check className="h-4 w-4 text-green-400" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="verify-code">Enter the 6-digit code from your app</Label>
                  <Input
                    id="verify-code"
                    value={verifyCode}
                    onChange={(e) => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    placeholder="000000"
                    maxLength={6}
                    className="font-mono text-center text-lg tracking-widest"
                    autoComplete="one-time-code"
                  />
                </div>
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSetupDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleMfaVerify} disabled={mfaLoading || verifyCode.length < 6}>
              {mfaLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Verify & Enable
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Backup Codes Dialog */}
      <Dialog open={showBackupCodes} onOpenChange={setShowBackupCodes}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Save Your Backup Codes</DialogTitle>
            <DialogDescription>
              Store these codes in a safe place. Each code can only be used once.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            {setupData && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2">
                  {setupData.backup_codes.map((code) => (
                    <div
                      key={code}
                      className="flex items-center justify-between px-3 py-2 bg-muted rounded font-mono text-sm"
                    >
                      {code}
                      <button
                        onClick={() => copyToClipboard(code)}
                        className="text-muted-foreground hover:text-foreground ml-2"
                      >
                        {copiedCode === code ? (
                          <Check className="h-3 w-3 text-green-400" />
                        ) : (
                          <Copy className="h-3 w-3" />
                        )}
                      </button>
                    </div>
                  ))}
                </div>
                <Button variant="outline" className="w-full" onClick={copyAllBackupCodes}>
                  <Copy className="mr-2 h-4 w-4" />
                  Copy All Codes
                </Button>
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button onClick={() => setShowBackupCodes(false)}>
              I&apos;ve saved my codes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Disable MFA Dialog */}
      <Dialog open={showDisableDialog} onOpenChange={setShowDisableDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Disable Two-Factor Authentication</DialogTitle>
            <DialogDescription>
              This will remove the extra security layer from your account. Enter your password to confirm.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <div className="space-y-2">
              <Label htmlFor="disable-password">Password</Label>
              <Input
                id="disable-password"
                type="password"
                value={disablePassword}
                onChange={(e) => setDisablePassword(e.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
              />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDisableDialog(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleMfaDisable}
              disabled={mfaLoading || !disablePassword}
            >
              {mfaLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Disable MFA
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
