"use client"

/**
 * Rotate an API key: same owner, name and scopes, new secret. The old key
 * stops at once, or after a grace period (0..1440 minutes) so clients can
 * switch over. The 201 body carries the new key's one-time secret, which goes
 * straight to `onRotated` (the parent shows `ApiKeySecretDialog`).
 */
import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { apiKeys, expiryOptions, fieldErrors } from '@/lib/endpoints/api-keys'
import type { ApiKey } from '@/types'
import { ApiKeyErrorAlert } from './ApiKeyErrorAlert'
import type { SecretResult } from './ApiKeySecretDialog'

/** Minutes the old key keeps working. All within the server's 0..1440. */
export const GRACE_OPTIONS: { value: number; label: string }[] = [
  { value: 0, label: 'Immediately (no grace)' },
  { value: 15, label: '15 minutes' },
  { value: 60, label: '1 hour' },
  { value: 240, label: '4 hours' },
  { value: 1440, label: '24 hours' },
]

const DEFAULT_EXPIRY = 'default'

export function RotateApiKeyDialog({
  apiKey,
  onOpenChange,
  onRotated,
}: {
  /** null = closed. */
  apiKey: ApiKey | null
  onOpenChange: (open: boolean) => void
  onRotated: (result: SecretResult) => void
}) {
  return (
    <Dialog open={apiKey !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        {apiKey && <RotateForm key={apiKey.id} apiKey={apiKey} onClose={() => onOpenChange(false)} onRotated={onRotated} />}
      </DialogContent>
    </Dialog>
  )
}

function RotateForm({
  apiKey,
  onClose,
  onRotated,
}: {
  apiKey: ApiKey
  onClose: () => void
  onRotated: (result: SecretResult) => void
}) {
  const [grace, setGrace] = useState(0)
  const [expiry, setExpiry] = useState<string>(DEFAULT_EXPIRY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const fields = fieldErrors(error)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const key = await apiKeys.rotate(apiKey.id, {
        grace_minutes: grace,
        expires_in_days: expiry === DEFAULT_EXPIRY ? undefined : Number(expiry),
      })
      onRotated({ key, mode: 'rotated', graceMinutes: grace })
      onClose()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <DialogHeader>
        <DialogTitle>Rotate {apiKey.name}?</DialogTitle>
        <DialogDescription>
          A new key with the same scopes is created and shown once. The current key{' '}
          <span className="font-mono">{apiKey.prefix}</span> stops working after the grace period.
        </DialogDescription>
      </DialogHeader>
      <ApiKeyErrorAlert error={error} />
      <div className="grid gap-2">
        <Label htmlFor="rotate-grace">Keep the old key working for</Label>
        <Select value={String(grace)} onValueChange={(v) => setGrace(Number(v))}>
          <SelectTrigger id="rotate-grace" aria-label="Grace period">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {GRACE_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={String(o.value)}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {fields.grace_minutes && <p className="text-xs text-red-400">{fields.grace_minutes}</p>}
      </div>
      <div className="grid gap-2">
        <Label htmlFor="rotate-expiry">New key expires in</Label>
        <Select value={expiry} onValueChange={setExpiry}>
          <SelectTrigger id="rotate-expiry" aria-label="New key expires in">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={DEFAULT_EXPIRY}>Organization default</SelectItem>
            {expiryOptions(365).map((d) => (
              <SelectItem key={d} value={String(d)}>
                {d} days
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {fields.expires_in_days && <p className="text-xs text-red-400">{fields.expires_in_days}</p>}
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button type="submit" disabled={busy}>
          {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Rotate key
        </Button>
      </DialogFooter>
    </form>
  )
}
