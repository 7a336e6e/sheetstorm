"use client"

/**
 * Revoke flow: one `useConfirm` dialog that also collects an optional reason
 * (max 200 chars, recorded in the audit log). Revocation is immediate and
 * permanent; the row stays for audit.
 */
import { useCallback, useRef } from 'react'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { Input } from '@/components/ui/input'
import { notifySuccess } from '@/lib/errors'
import { API_KEYS_ENDPOINT, SERVICE_ACCOUNTS_ENDPOINT, apiKeys, notifyApiKeyError } from '@/lib/endpoints/api-keys'
import { invalidate } from '@/lib/query-cache'
import type { ApiKey } from '@/types'

export const MAX_REVOKE_REASON = 200

/** Own state, so typing never re-renders the (static) confirm description. */
function ReasonField({ onChange }: { onChange: (reason: string) => void }) {
  return (
    <span className="mt-3 block space-y-1">
      <label htmlFor="revoke-reason" className="block text-xs text-muted-foreground">
        Reason (optional, recorded in the audit log)
      </label>
      <Input
        id="revoke-reason"
        defaultValue=""
        maxLength={MAX_REVOKE_REASON}
        autoComplete="off"
        placeholder="e.g. Key leaked in a screenshot"
        onChange={(e) => onChange(e.target.value)}
      />
    </span>
  )
}

/** Returns `revoke(key)`: resolves true once the key was revoked. */
export function useRevokeApiKey(onRevoked?: (key: ApiKey) => void): (key: ApiKey) => Promise<boolean> {
  const confirm = useConfirm()
  const reasonRef = useRef('')
  return useCallback(
    async (key: ApiKey) => {
      reasonRef.current = ''
      const ok = await confirm({
        title: `Revoke ${key.name}?`,
        description: (
          <>
            Anything using <span className="font-mono">{key.prefix}</span> stops working immediately. This can&apos;t
            be undone; create a new key if you need access again.
            <ReasonField onChange={(v) => (reasonRef.current = v)} />
          </>
        ),
        confirmLabel: 'Revoke key',
        variant: 'destructive',
      })
      if (!ok) return false
      try {
        const reason = reasonRef.current.trim()
        await apiKeys.revoke(key.id, reason || undefined)
        invalidate(API_KEYS_ENDPOINT)
        invalidate(SERVICE_ACCOUNTS_ENDPOINT)
        notifySuccess('API key revoked', key.name)
        onRevoked?.(key)
        return true
      } catch (err) {
        notifyApiKeyError(err, 'revoke the API key')
        return false
      }
    },
    [confirm, onRevoked]
  )
}
