"use client"

/**
 * The key list with its create / rotate / revoke flows and the one-time
 * secret dialog. Shared by Settings > API Keys (`scope="org"`) and the
 * profile card (`scope="mine"`).
 *
 * The secret of a create / rotate response is held in this component's state
 * only until the secret dialog is closed.
 */
import { useCallback, useState } from 'react'
import { usePermission } from '@/components/auth/permission-gate'
import { API_KEYS_ENDPOINT, SERVICE_ACCOUNTS_ENDPOINT } from '@/lib/endpoints/api-keys'
import { notifySuccess } from '@/lib/errors'
import { invalidate } from '@/lib/query-cache'
import type { ApiKey } from '@/types'
import { ApiKeySecretDialog, type SecretResult } from './ApiKeySecretDialog'
import { ApiKeyTable, type ApiKeyTableScope } from './ApiKeyTable'
import { CreateApiKeyDialog } from './CreateApiKeyDialog'
import { RotateApiKeyDialog } from './RotateApiKeyDialog'
import { useRevokeApiKey } from './useRevokeApiKey'

export function ApiKeysPanel({
  scope,
  urlKey,
  createOpen: controlledCreateOpen,
  onCreateOpenChange,
  defaultOwnerId,
}: {
  scope: ApiKeyTableScope
  urlKey?: string
  /** Lets a parent open the create dialog (e.g. from a service-account row). */
  createOpen?: boolean
  onCreateOpenChange?: (open: boolean) => void
  defaultOwnerId?: string
}) {
  const canOwn = usePermission('api_keys:own')
  const canManage = usePermission('api_keys:manage')
  const canCreate = scope === 'mine' ? canOwn : canOwn || canManage

  const [localCreateOpen, setLocalCreateOpen] = useState(false)
  const createOpen = controlledCreateOpen ?? localCreateOpen
  const setCreateOpen = onCreateOpenChange ?? setLocalCreateOpen
  const [rotating, setRotating] = useState<ApiKey | null>(null)
  const [secret, setSecret] = useState<SecretResult | null>(null)

  const refresh = useCallback(() => {
    invalidate(API_KEYS_ENDPOINT)
    invalidate(SERVICE_ACCOUNTS_ENDPOINT)
  }, [])

  const revoke = useRevokeApiKey()

  return (
    <>
      <ApiKeyTable
        scope={scope}
        urlKey={urlKey}
        onCreate={canCreate ? () => setCreateOpen(true) : undefined}
        onRotate={setRotating}
        onRevoke={(k) => void revoke(k)}
      />
      <CreateApiKeyDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        defaultOwnerId={defaultOwnerId}
        onCreated={(result) => {
          refresh()
          setSecret(result)
          notifySuccess('API key created', result.key.name)
        }}
      />
      <RotateApiKeyDialog
        apiKey={rotating}
        onOpenChange={(open) => !open && setRotating(null)}
        onRotated={(result) => {
          refresh()
          setSecret(result)
        }}
      />
      <ApiKeySecretDialog result={secret} onClose={() => setSecret(null)} />
    </>
  )
}
