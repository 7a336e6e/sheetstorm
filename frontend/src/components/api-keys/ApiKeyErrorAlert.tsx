"use client"

/**
 * Inline alert for a failed API-key / service-account mutation. API-key codes
 * (`api_keys_disabled`, `invalid_scopes`, `api_key_limit`, ...) get their own
 * copy; everything else, including the RBAC guard codes of a service-account
 * role change, goes through `GuardErrorAlert` with catalog labels.
 */
import { GuardErrorAlert } from '@/components/auth/guard-error-alert'
import { usePermissionCatalog } from '@/hooks/use-permission-catalog'
import { describeApiKeyError, isApiKeyCode } from '@/lib/endpoints/api-keys'

function Guard({ error }: { error: unknown }) {
  const { labelOf } = usePermissionCatalog()
  return <GuardErrorAlert error={error} labelOf={labelOf} />
}

export function ApiKeyErrorAlert({ error }: { error: unknown }) {
  if (!error) return null
  if (!isApiKeyCode(error)) return <Guard error={error} />
  const { title, description } = describeApiKeyError(error)
  return (
    <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
      <p className="font-medium">{title}</p>
      <p className="mt-0.5">{description}</p>
    </div>
  )
}
