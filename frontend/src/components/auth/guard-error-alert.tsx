"use client"

/**
 * Inline alert for a failed admin mutation. Shows the described error (the
 * server's message for RBAC guard codes such as `privilege_escalation`,
 * `insufficient_privilege`, `last_admin`, `self_lockout`) plus the permission
 * keys the guard named, as catalog labels when a `labelOf` is given.
 */
import { describeError } from '@/lib/errors'
import { permissionsFromError } from '@/lib/endpoints/rbac'

export function GuardErrorAlert({
  error,
  labelOf = (k) => k,
}: {
  error: unknown
  labelOf?: (key: string) => string
}) {
  if (!error) return null
  const { title, description } = describeError(error)
  const keys = permissionsFromError(error)
  return (
    <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
      <p className="font-medium">{title}</p>
      <p className="mt-0.5">{description}</p>
      {keys.length > 0 && (
        <ul className="mt-2 list-disc pl-5" aria-label="Permissions involved">
          {keys.map((k) => (
            <li key={k}>
              {labelOf(k)}
              {labelOf(k) !== k && <span className="ml-1 font-mono text-xs opacity-70">({k})</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
