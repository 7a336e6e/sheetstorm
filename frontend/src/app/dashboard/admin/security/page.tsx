"use client"

import { useState, useEffect } from 'react'
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
import { useAuthStore } from '@/lib/store'
import { useToast } from '@/components/ui/use-toast'
import api from '@/lib/api'
import {
  Shield,
  ShieldCheck,
  ShieldOff,
  Copy,
  Check,
  Loader2,
  ArrowLeft,
  KeyRound,
} from 'lucide-react'
import Link from 'next/link'

interface MFASetupData {
  secret: string
  provisioning_uri: string
  backup_codes: string[]
}

export default function MFASettingsPage() {
  const { user, refreshUser } = useAuthStore()
  const { toast } = useToast()
  const [mfaEnabled, setMfaEnabled] = useState(false)
  const [setupData, setSetupData] = useState<MFASetupData | null>(null)
  const [showSetupDialog, setShowSetupDialog] = useState(false)
  const [showDisableDialog, setShowDisableDialog] = useState(false)
  const [showBackupCodes, setShowBackupCodes] = useState(false)
  const [verifyCode, setVerifyCode] = useState('')
  const [disablePassword, setDisablePassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [copiedCode, setCopiedCode] = useState<string | null>(null)

  useEffect(() => {
    if (user) {
      setMfaEnabled(user.mfa_enabled || false)
    }
  }, [user])

  const handleSetup = async () => {
    setIsLoading(true)
    try {
      const data = await api.post<MFASetupData>('/auth/mfa/setup', {})
      setSetupData(data)
      setShowSetupDialog(true)
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to start MFA setup',
        variant: 'destructive',
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleVerify = async () => {
    if (!verifyCode || verifyCode.length < 6) {
      toast({
        title: 'Invalid Code',
        description: 'Please enter a 6-digit code from your authenticator app',
        variant: 'destructive',
      })
      return
    }
    setIsLoading(true)
    try {
      await api.post('/auth/mfa/verify', { code: verifyCode })
      setMfaEnabled(true)
      setShowSetupDialog(false)
      setShowBackupCodes(true)
      if (refreshUser) refreshUser()
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
      setIsLoading(false)
      setVerifyCode('')
    }
  }

  const handleDisable = async () => {
    if (!disablePassword) {
      toast({
        title: 'Password Required',
        description: 'Enter your password to disable MFA',
        variant: 'destructive',
      })
      return
    }
    setIsLoading(true)
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
      setIsLoading(false)
      setDisablePassword('')
    }
  }

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

  return (
    <div className="p-6 lg:p-8 max-w-2xl mx-auto space-y-6">
      <Link
        href="/dashboard/admin/settings"
        className="inline-flex items-center text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Settings
      </Link>

      <div>
        <h1 className="text-2xl font-semibold flex items-center gap-3">
          <KeyRound className="h-6 w-6" />
          Two-Factor Authentication
        </h1>
        <p className="text-muted-foreground mt-1">
          Add an extra layer of security to your account using a TOTP authenticator app.
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {mfaEnabled ? (
                <ShieldCheck className="h-8 w-8 text-green-400" />
              ) : (
                <ShieldOff className="h-8 w-8 text-muted-foreground" />
              )}
              <div>
                <CardTitle>Status</CardTitle>
                <CardDescription>
                  {mfaEnabled
                    ? 'MFA is enabled on your account'
                    : 'MFA is not yet configured'}
                </CardDescription>
              </div>
            </div>
            <Badge variant={mfaEnabled ? 'default' : 'outline'}>
              {mfaEnabled ? 'Enabled' : 'Disabled'}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          {mfaEnabled ? (
            <Button
              variant="destructive"
              onClick={() => setShowDisableDialog(true)}
            >
              <ShieldOff className="mr-2 h-4 w-4" />
              Disable MFA
            </Button>
          ) : (
            <Button onClick={handleSetup} disabled={isLoading}>
              {isLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Shield className="mr-2 h-4 w-4" />
              )}
              Set Up MFA
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Setup Dialog */}
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
                {/* QR Code */}
                <div className="flex justify-center">
                  <div className="bg-white p-4 rounded-lg">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(setupData.provisioning_uri)}`}
                      alt="MFA QR Code"
                      width={200}
                      height={200}
                    />
                  </div>
                </div>

                {/* Manual entry */}
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

                {/* Verification */}
                <div className="space-y-2">
                  <Label htmlFor="verify-code">Enter the 6-digit code from your app</Label>
                  <div className="flex gap-2">
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
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSetupDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleVerify} disabled={isLoading || verifyCode.length < 6}>
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
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
              Store these codes in a safe place. You can use them to access your account if you lose your authenticator device. Each code can only be used once.
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
              onClick={handleDisable}
              disabled={isLoading || !disablePassword}
            >
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Disable MFA
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
