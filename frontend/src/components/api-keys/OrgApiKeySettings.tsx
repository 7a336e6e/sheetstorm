"use client"

/**
 * Organization switches for API keys: enable / disable them for everyone,
 * and cap a key's lifetime (1..365 days). Both are written through
 * `PUT /organization`, which needs `organizations:manage`; holders of only
 * `api_keys:manage` see the current values read-only.
 *
 * Turning keys off rejects every key exchange at once (existing access
 * tokens expire within minutes) and blocks creating or rotating keys.
 */
import { useCallback, useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { usePermission } from '@/components/auth/permission-gate'
import { API_KEY_MAX_LIFETIME_DEFAULT, apiKeyOrgSettings, notifyApiKeyError } from '@/lib/endpoints/api-keys'
import { describeError, notifySuccess } from '@/lib/errors'

export const MIN_LIFETIME_DAYS = 1
export const MAX_LIFETIME_DAYS = 365

/** Whole days 1..365, else null. */
export function parseLifetime(text: string): number | null {
  if (!/^\d{1,3}$/.test(text.trim())) return null
  const n = Number(text)
  return n >= MIN_LIFETIME_DAYS && n <= MAX_LIFETIME_DAYS ? n : null
}

export function OrgApiKeySettings() {
  const canEdit = usePermission('organizations:manage')
  const confirm = useConfirm()
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [enabled, setEnabled] = useState(true)
  const [maxDays, setMaxDays] = useState(API_KEY_MAX_LIFETIME_DEFAULT)
  const [draft, setDraft] = useState(String(API_KEY_MAX_LIFETIME_DEFAULT))
  const [saving, setSaving] = useState<'enabled' | 'lifetime' | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const s = await apiKeyOrgSettings.get()
      setEnabled(s.api_keys_enabled)
      setMaxDays(s.api_key_max_lifetime_days)
      setDraft(String(s.api_key_max_lifetime_days))
    } catch (err) {
      setLoadError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const toggleEnabled = async (next: boolean) => {
    if (!next) {
      const ok = await confirm({
        title: 'Disable API keys?',
        description:
          'No key can be exchanged for access while keys are disabled, and keys cannot be created or rotated. Existing access tokens expire within minutes. Keys are kept and work again when you re-enable them.',
        confirmLabel: 'Disable API keys',
        variant: 'destructive',
      })
      if (!ok) return
    }
    setSaving('enabled')
    try {
      await apiKeyOrgSettings.update({ api_keys_enabled: next })
      setEnabled(next)
      notifySuccess(next ? 'API keys enabled' : 'API keys disabled')
    } catch (err) {
      notifyApiKeyError(err, 'update the API key setting')
    } finally {
      setSaving(null)
    }
  }

  const parsed = parseLifetime(draft)
  const dirty = parsed !== null && parsed !== maxDays

  const saveLifetime = async (e: React.FormEvent) => {
    e.preventDefault()
    if (parsed === null || !dirty) return
    setSaving('lifetime')
    try {
      await apiKeyOrgSettings.update({ api_key_max_lifetime_days: parsed })
      setMaxDays(parsed)
      notifySuccess('Maximum key lifetime updated', `${parsed} days`)
    } catch (err) {
      notifyApiKeyError(err, 'update the maximum key lifetime')
    } finally {
      setSaving(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Organization policy</CardTitle>
        <CardDescription>Switch API keys on or off and cap how long a key may live.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </p>
        ) : loadError ? (
          <div role="alert" className="flex items-center gap-3 text-sm text-red-400">
            <span>{describeError(loadError).description}</span>
            <Button variant="outline" size="sm" onClick={() => void load()}>
              Retry
            </Button>
          </div>
        ) : (
          <>
            <div className="flex items-start justify-between gap-4">
              <div>
                <Label htmlFor="api-keys-enabled">Allow API keys</Label>
                <p className="text-xs text-muted-foreground">
                  When off, API keys stop working for the whole organization.
                </p>
              </div>
              <Switch
                id="api-keys-enabled"
                checked={enabled}
                disabled={!canEdit || saving !== null}
                onCheckedChange={(v) => void toggleEnabled(v)}
              />
            </div>

            <form onSubmit={saveLifetime} className="flex flex-wrap items-end gap-3">
              <div className="grid gap-1.5">
                <Label htmlFor="api-key-max-lifetime">Maximum key lifetime (days)</Label>
                <Input
                  id="api-key-max-lifetime"
                  inputMode="numeric"
                  className="w-32"
                  value={draft}
                  disabled={!canEdit || saving !== null}
                  onChange={(e) => setDraft(e.target.value)}
                  aria-invalid={parsed === null}
                />
                <p className={parsed === null ? 'text-xs text-red-400' : 'text-xs text-muted-foreground'}>
                  {parsed === null
                    ? `Enter a whole number from ${MIN_LIFETIME_DAYS} to ${MAX_LIFETIME_DAYS}.`
                    : 'Applies to new and rotated keys; existing keys keep their expiry.'}
                </p>
              </div>
              {canEdit && (
                <Button type="submit" size="sm" disabled={!dirty || saving !== null}>
                  {saving === 'lifetime' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Save
                </Button>
              )}
            </form>

            {!canEdit && (
              <p className="text-xs text-muted-foreground">
                Changing these settings requires the organization settings permission.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
