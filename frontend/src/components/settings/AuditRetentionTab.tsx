/**
 * Audit retention tab in Settings (organizations:manage).
 *
 * - Retention: keep forever or N days (min 365, server bounds). Shortening
 *   it answers 409 `confirmation_required` with `would_purge`; the user
 *   confirms by typing the new value, then the change is resent with
 *   `confirm: true`. Purges run from the scheduled job, never from here.
 * - Legal hold: blocks every purge; placing it needs a reason, releasing it
 *   asks for confirmation. Both are security events server side.
 * - Integrity: verify the audit hash chain on demand.
 */

"use client"

import { useCallback, useEffect, useId, useState } from 'react'
import { Gavel, Loader2, ScrollText, ShieldCheck } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Timestamp } from '@/components/ui/timestamp'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { usePermission } from '@/components/auth/permission-gate'
import { AuditIntegrityPanel } from '@/components/audit/AuditIntegrityPanel'
import { admin, retentionConflict } from '@/lib/endpoints/admin'
import { describeError, notifyError, notifySuccess } from '@/lib/errors'
import { cn } from '@/lib/utils'
import type { AuditSettings, AuditSettingsUpdate } from '@/types'

export const RETENTION_PRESETS: { days: number; label: string }[] = [
  { days: 365, label: '1 year' },
  { days: 730, label: '2 years' },
  { days: 1095, label: '3 years' },
  { days: 2555, label: '7 years' },
]

type Choice = 'forever' | 'custom' | `${number}`

export const LEGAL_HOLD_REASON_MAX = 500

function choiceFor(days: number | null): Choice {
  if (days === null) return 'forever'
  return RETENTION_PRESETS.some((p) => p.days === days) ? (String(days) as Choice) : 'custom'
}

export function AuditRetentionTab() {
  const canManage = usePermission('organizations:manage')
  const confirm = useConfirm()
  const ids = { custom: useId(), hold: useId(), reason: useId() }

  const [settings, setSettings] = useState<AuditSettings | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [choice, setChoice] = useState<Choice>('forever')
  const [custom, setCustom] = useState('')
  const [saving, setSaving] = useState(false)
  const [holdDraft, setHoldDraft] = useState<string | null>(null)

  const apply = useCallback((s: AuditSettings) => {
    setSettings(s)
    setChoice(choiceFor(s.audit_retention_days))
    setCustom(s.audit_retention_days !== null ? String(s.audit_retention_days) : '')
  }, [])

  const load = useCallback(() => {
    admin
      .getAuditSettings()
      .then((s) => {
        setLoadError(null)
        apply(s)
      })
      .catch((err) => setLoadError(err))
  }, [apply])

  useEffect(() => {
    load()
  }, [load])

  if (loadError && !settings) {
    return (
      <Card>
        <CardContent className="flex items-center gap-3 pt-6 text-sm">
          <span>{describeError(loadError).description}</span>
          <Button variant="outline" size="sm" onClick={load}>
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }
  if (!settings) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading audit settings…
      </div>
    )
  }

  const min = settings.min_retention_days
  const max = settings.max_retention_days
  const customDays = /^\d+$/.test(custom.trim()) ? Number(custom.trim()) : NaN
  const customValid = Number.isInteger(customDays) && customDays >= min && customDays <= max
  const selectedDays: number | null | undefined =
    choice === 'forever' ? null : choice === 'custom' ? (customValid ? customDays : undefined) : Number(choice)
  const dirty = selectedDays !== undefined && selectedDays !== settings.audit_retention_days

  const put = async (data: AuditSettingsUpdate, action: string, success: string) => {
    setSaving(true)
    try {
      apply(await admin.updateAuditSettings(data))
      notifySuccess(success)
      return true
    } catch (err) {
      notifyError(err, action)
      return false
    } finally {
      setSaving(false)
    }
  }

  const saveRetention = async () => {
    if (selectedDays === undefined) return
    setSaving(true)
    try {
      apply(await admin.updateAuditSettings({ audit_retention_days: selectedDays }))
      notifySuccess('Audit retention updated')
      return
    } catch (err) {
      const conflict = retentionConflict(err)
      if (!conflict || selectedDays === null) {
        notifyError(err, 'update audit retention')
        return
      }
      setSaving(false)
      const ok = await confirm({
        title: 'Shorten audit retention?',
        description: (
          <span data-testid="would-purge">
            <strong className="text-foreground">{conflict.would_purge.toLocaleString()}</strong> audit{' '}
            {conflict.would_purge === 1 ? 'row is' : 'rows are'} older than the new cutoff
            {conflict.cutoff && (
              <>
                {' '}
                (<Timestamp value={conflict.cutoff} />)
              </>
            )}{' '}
            and will be permanently deleted at the next scheduled purge. This can&apos;t be undone.
          </span>
        ),
        confirmLabel: 'Shorten retention',
        variant: 'destructive',
        requireText: String(selectedDays),
      })
      if (!ok) return
      await put({ audit_retention_days: selectedDays, confirm: true }, 'update audit retention', 'Audit retention updated')
    } finally {
      setSaving(false)
    }
  }

  const placeHold = async () => {
    const reason = holdDraft?.trim()
    if (!reason) return
    if (await put({ legal_hold: true, legal_hold_reason: reason }, 'place the legal hold', 'Legal hold placed')) {
      setHoldDraft(null)
    }
  }

  const releaseHold = async () => {
    const ok = await confirm({
      title: 'Release the legal hold?',
      description: 'Retention purges resume at the next scheduled run and may delete audit rows older than the retention period.',
      confirmLabel: 'Release hold',
      variant: 'destructive',
    })
    if (ok) await put({ legal_hold: false }, 'release the legal hold', 'Legal hold released')
  }

  const onHoldToggle = (on: boolean) => {
    if (on) setHoldDraft('')
    else if (settings.legal_hold) void releaseHold()
    else setHoldDraft(null)
  }

  const options: { value: Choice; label: string; hint?: string }[] = [
    ...RETENTION_PRESETS.map((p) => ({ value: String(p.days) as Choice, label: p.label, hint: `${p.days} days` })),
    { value: 'forever', label: 'Keep forever', hint: 'never purged' },
    { value: 'custom', label: 'Custom' },
  ]

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ScrollText className="h-5 w-5" />
            Audit log retention
          </CardTitle>
          <CardDescription>
            Audit rows older than the retention period are deleted by the daily purge job (never below {min} days).
            Rows tied to incidents under legal hold are always kept.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm">
            Current:{' '}
            <span className="font-medium" data-testid="current-retention">
              {settings.audit_retention_days === null ? 'keep forever' : `${settings.audit_retention_days} days`}
            </span>
          </p>
          <fieldset className="space-y-2" disabled={!canManage || saving}>
            <legend className="sr-only">Retention period</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              {options.map((o) => (
                <label
                  key={o.value}
                  className={cn(
                    'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm',
                    choice === o.value ? 'border-primary/50 bg-primary/10' : 'border-white/10 hover:bg-white/5'
                  )}
                >
                  <input
                    type="radio"
                    name="audit-retention"
                    value={o.value}
                    checked={choice === o.value}
                    onChange={() => setChoice(o.value)}
                    className="accent-primary"
                  />
                  <span>{o.label}</span>
                  {o.hint && <span className="ml-auto text-xs text-muted-foreground">{o.hint}</span>}
                </label>
              ))}
            </div>
            {choice === 'custom' && (
              <div className="max-w-xs space-y-1.5">
                <Label htmlFor={ids.custom}>Retention (days)</Label>
                <Input
                  id={ids.custom}
                  type="number"
                  inputMode="numeric"
                  min={min}
                  max={max}
                  value={custom}
                  onChange={(e) => setCustom(e.target.value)}
                  aria-invalid={custom !== '' && !customValid}
                />
                {custom !== '' && !customValid && (
                  <p className="text-xs text-red-400">
                    Enter a whole number of days between {min} and {max}.
                  </p>
                )}
              </div>
            )}
          </fieldset>
          {canManage && (
            <Button onClick={() => void saveRetention()} disabled={!dirty || saving}>
              {saving && <Loader2 className="h-4 w-4 animate-spin" />}
              Save retention
            </Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Gavel className="h-5 w-5" />
            Legal hold
          </CardTitle>
          <CardDescription>
            While a legal hold is on, no audit row is purged regardless of the retention period.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <Switch
              id={ids.hold}
              checked={settings.legal_hold || holdDraft !== null}
              onCheckedChange={onHoldToggle}
              disabled={!canManage || saving}
            />
            <Label htmlFor={ids.hold}>{settings.legal_hold ? 'Legal hold is on' : 'Legal hold is off'}</Label>
          </div>

          {settings.legal_hold && (
            <dl className="grid gap-1 rounded-md border border-amber-500/25 bg-amber-500/5 p-3 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-4">
              <dt className="text-muted-foreground">Reason</dt>
              <dd className="break-words">{settings.legal_hold_reason || '—'}</dd>
              <dt className="text-muted-foreground">Placed</dt>
              <dd>
                <Timestamp value={settings.legal_hold_set_at} />
              </dd>
              {settings.legal_hold_set_by && (
                <>
                  <dt className="text-muted-foreground">By (user ID)</dt>
                  <dd className="font-mono text-xs">{settings.legal_hold_set_by}</dd>
                </>
              )}
            </dl>
          )}

          {!settings.legal_hold && holdDraft !== null && (
            <div className="space-y-2">
              <Label htmlFor={ids.reason}>Reason (required)</Label>
              <Textarea
                id={ids.reason}
                value={holdDraft}
                maxLength={LEGAL_HOLD_REASON_MAX}
                onChange={(e) => setHoldDraft(e.target.value)}
                placeholder="e.g. Litigation hold: matter 2026-014, counsel request of 2026-10-01"
                rows={3}
              />
              <p className="text-xs text-muted-foreground">
                {holdDraft.length}/{LEGAL_HOLD_REASON_MAX}
              </p>
              <div className="flex gap-2">
                <Button onClick={() => void placeHold()} disabled={!holdDraft.trim() || saving}>
                  {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                  Place legal hold
                </Button>
                <Button variant="ghost" onClick={() => setHoldDraft(null)} disabled={saving}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" />
            Integrity
          </CardTitle>
          <CardDescription>
            Every audit row is linked into a keyed hash chain. A check detects edited, deleted or reordered rows.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AuditIntegrityPanel />
        </CardContent>
      </Card>
    </div>
  )
}
