"use client"

/**
 * Create an API key: name, description, owner, expiry and scopes.
 *
 * - Owner: me (`api_keys:own`), or a service account (`api_keys:manage`);
 *   admins never mint keys for other people. The scope list is the owner's
 *   grantable scopes (and, for another owner, also bounded by the caller).
 * - Expiry choices are capped by the org's `api_key_max_lifetime_days`.
 * - The 201 body carries the one-time secret; it goes straight to
 *   `onCreated` (the parent shows `ApiKeySecretDialog`) and is not kept here.
 */
import { useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { usePermission } from '@/components/auth/permission-gate'
import { ApiError, isAbortError } from '@/lib/api'
import {
  apiKeys,
  defaultExpiry,
  expiryOptions,
  fieldErrors,
  notifyApiKeyError,
  serviceAccounts,
} from '@/lib/endpoints/api-keys'
import type { ApiKeyScopesResponse, ServiceAccount } from '@/types'
import { ApiKeyErrorAlert } from './ApiKeyErrorAlert'
import { ScopePicker } from './ScopePicker'
import type { SecretResult } from './ApiKeySecretDialog'

const SELF = '__self__'
const MAX_NAME = 100
const MAX_DESCRIPTION = 500

export function CreateApiKeyDialog({
  open,
  onOpenChange,
  onCreated,
  defaultOwnerId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Receives the one-time secret. */
  onCreated: (result: SecretResult) => void
  /** Preselect a service account (manager only). */
  defaultOwnerId?: string
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        {/* Content unmounts on close, so every opening starts with an empty form. */}
        {open && (
          <CreateForm defaultOwnerId={defaultOwnerId} onClose={() => onOpenChange(false)} onCreated={onCreated} />
        )}
      </DialogContent>
    </Dialog>
  )
}

function CreateForm({
  defaultOwnerId,
  onClose,
  onCreated,
}: {
  defaultOwnerId?: string
  onClose: () => void
  onCreated: (result: SecretResult) => void
}) {
  const canOwn = usePermission('api_keys:own')
  const canManage = usePermission('api_keys:manage')

  const [accounts, setAccounts] = useState<ServiceAccount[]>([])
  const [owner, setOwner] = useState<string>(defaultOwnerId ?? (canOwn ? SELF : ''))
  const [scopeInfo, setScopeInfo] = useState<ApiKeyScopesResponse | null>(null)
  const [scopeError, setScopeError] = useState<unknown>(null)
  const [loadingScopes, setLoadingScopes] = useState(false)

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [days, setDays] = useState<number | null>(null)
  const [scopes, setScopes] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  // Active service accounts (managers only) for the owner select.
  useEffect(() => {
    if (!canManage) return
    const ctrl = new AbortController()
    serviceAccounts
      .list({ is_active: true, sort: 'name', per_page: 200 }, { signal: ctrl.signal })
      .then((res) => {
        setAccounts(res.items)
        setOwner((cur) => cur || res.items.find((a) => a.id === defaultOwnerId)?.id || '')
      })
      .catch((err) => {
        if (!isAbortError(err)) notifyApiKeyError(err, 'load service accounts')
      })
    return () => ctrl.abort()
  }, [canManage, defaultOwnerId])

  // Grantable scopes of the chosen owner.
  useEffect(() => {
    if (!owner) return
    const ctrl = new AbortController()
    setLoadingScopes(true)
    setScopeError(null)
    apiKeys
      .scopes(owner === SELF ? undefined : owner, { signal: ctrl.signal })
      .then((res) => {
        setScopeInfo(res)
        setScopes([])
        setDays((cur) => (cur !== null && cur <= res.max_lifetime_days ? cur : defaultExpiry(res.max_lifetime_days)))
      })
      .catch((err) => {
        if (!isAbortError(err)) setScopeError(err)
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoadingScopes(false)
      })
    return () => ctrl.abort()
  }, [owner])

  const max = scopeInfo?.max_lifetime_days ?? 365
  const options = useMemo(() => expiryOptions(max), [max])
  const fields = fieldErrors(error)
  const trimmed = name.trim()
  const disabledOrg = scopeInfo?.api_keys_enabled === false
  const valid =
    !!owner && !!scopeInfo && !loadingScopes && !disabledOrg && trimmed.length >= 1 && trimmed.length <= MAX_NAME && scopes.length > 0 && days !== null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid || days === null) return
    setBusy(true)
    setError(null)
    try {
      const key = await apiKeys.create({
        name: trimmed,
        description: description.trim() || undefined,
        scopes,
        expires_in_days: days,
        owner_id: owner === SELF ? undefined : owner,
      })
      onCreated({ key, mode: 'created' })
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
        <DialogTitle>Create API key</DialogTitle>
        <DialogDescription>
          A key lets a script or an MCP client act with only the scopes you select, even when MFA is on. It expires
          and can be revoked at any time. Scopes cannot be changed later; create a new key instead.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="space-y-4">
        <ApiKeyErrorAlert error={error ?? scopeError} />
        {disabledOrg && (
          <ApiKeyErrorAlert error={new ApiError(403, 'API keys are disabled', { code: 'api_keys_disabled' })} />
        )}

        <div className="grid gap-2">
          <Label htmlFor="api-key-name">Name</Label>
          <Input
            id="api-key-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={MAX_NAME}
            placeholder="e.g. Local MCP bridge"
            autoComplete="off"
            required
            autoFocus
            aria-invalid={!!fields.name}
          />
          {fields.name && <p className="text-xs text-red-400">{fields.name}</p>}
        </div>

        <div className="grid gap-2">
          <Label htmlFor="api-key-description">Description (optional)</Label>
          <Textarea
            id="api-key-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={MAX_DESCRIPTION}
            rows={2}
            placeholder="What uses this key"
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {canManage && (
            <div className="grid gap-2">
              <Label htmlFor="api-key-owner">Owner</Label>
              <Select value={owner} onValueChange={setOwner}>
                <SelectTrigger id="api-key-owner" aria-label="Owner">
                  <SelectValue placeholder="Choose an owner" />
                </SelectTrigger>
                <SelectContent>
                  {canOwn && <SelectItem value={SELF}>Me</SelectItem>}
                  {accounts.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.name} (service account)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {!canOwn && accounts.length === 0 && (
                <p className="text-xs text-muted-foreground">Create a service account first.</p>
              )}
            </div>
          )}
          <div className="grid gap-2">
            <Label htmlFor="api-key-expiry">Expires in</Label>
            <Select value={days === null ? '' : String(days)} onValueChange={(v) => setDays(Number(v))}>
              <SelectTrigger id="api-key-expiry" aria-label="Expires in">
                <SelectValue placeholder="Choose" />
              </SelectTrigger>
              <SelectContent>
                {options.map((d) => (
                  <SelectItem key={d} value={String(d)}>
                    {d} days
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">Your organization allows up to {max} days.</p>
            {fields.expires_in_days && <p className="text-xs text-red-400">{fields.expires_in_days}</p>}
          </div>
        </div>

        <div className="grid gap-2">
          <Label>Scopes</Label>
          {loadingScopes && !scopeInfo ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading scopes…
            </p>
          ) : owner && scopeInfo ? (
            <ScopePicker groups={scopeInfo.groups} value={scopes} onChange={setScopes} disabled={busy} />
          ) : (
            <p className="text-sm text-muted-foreground">Choose an owner to see the scopes it can grant.</p>
          )}
        </div>
      </DialogBody>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button type="submit" disabled={!valid || busy}>
          {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Create key
        </Button>
      </DialogFooter>
    </form>
  )
}
