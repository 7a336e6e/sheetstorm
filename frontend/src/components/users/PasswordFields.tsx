'use client'

/**
 * New-password + confirm fields with the password-policy checklist (backend
 * `security_policy.validate_password`; `rules` from usePasswordPolicy, code
 * defaults otherwise), and the centered card the public account pages
 * (invite, reset, forced change) render in.
 */
import type { ReactNode } from 'react'
import { Label } from '@/components/ui/label'
import { PasswordInput } from '@/components/ui/input'
import { SheetStormLogo } from '@/components/landing/SheetStormLogo'
import { PasswordChecklist } from '@/components/settings/PasswordChecklist'
import type { PasswordRules } from '@/types'

export function PasswordFields({
  password,
  confirm,
  onPassword,
  onConfirm,
  disabled,
  label = 'New password',
  rules,
}: {
  password: string
  confirm: string
  onPassword: (v: string) => void
  onConfirm: (v: string) => void
  disabled?: boolean
  label?: string
  rules?: PasswordRules
}) {
  const mismatch = confirm.length > 0 && confirm !== password
  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="new-password">{label}</Label>
        <PasswordInput
          id="new-password"
          value={password}
          onChange={(e) => onPassword(e.target.value)}
          autoComplete="new-password"
          required
          disabled={disabled}
          className="h-11"
        />
        {password.length > 0 && <PasswordChecklist password={password} rules={rules} />}
      </div>
      <div className="space-y-2">
        <Label htmlFor="confirm-password">Confirm password</Label>
        <PasswordInput
          id="confirm-password"
          value={confirm}
          onChange={(e) => onConfirm(e.target.value)}
          autoComplete="new-password"
          required
          disabled={disabled}
          className="h-11"
        />
        {mismatch && <p className="mt-1 text-xs text-destructive">Passwords do not match</p>}
      </div>
    </>
  )
}

export function AccountCard({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-[420px] space-y-6">
        <div className="flex items-center justify-center gap-2">
          <SheetStormLogo size={32} />
          <span className="text-2xl font-bold">SheetStorm</span>
        </div>
        <div className="space-y-6 rounded-lg border border-white/10 bg-slate-900/60 p-6">
          <div className="space-y-1.5">
            <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
            {subtitle && <div className="text-sm text-muted-foreground">{subtitle}</div>}
          </div>
          {children}
        </div>
      </div>
    </div>
  )
}
