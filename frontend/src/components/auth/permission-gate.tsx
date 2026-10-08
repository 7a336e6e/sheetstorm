"use client"

/**
 * Permission-based UI gating. Cosmetic only: the backend decorators
 * (`@require_permission`, `@require_incident_access`) stay authoritative.
 * Use permissions, never role names.
 */
import * as React from 'react'
import { useAuthStore } from '@/lib/store'

export type PermissionMode = 'all' | 'any'
export type PermissionRequirement = string | string[]

const EMPTY: readonly string[] = []

/** Pure check. An empty requirement means "no requirement" and passes. */
export function checkPermission(
  granted: readonly string[] | undefined,
  perm: PermissionRequirement,
  mode: PermissionMode = 'all'
): boolean {
  const required = Array.isArray(perm) ? perm : [perm]
  if (required.length === 0) return true
  const have = granted ?? EMPTY
  return mode === 'any'
    ? required.some((p) => have.includes(p))
    : required.every((p) => have.includes(p))
}

function useGranted(): readonly string[] {
  return useAuthStore((s) => s.user?.permissions) ?? EMPTY
}

/** Whether the current user holds `perm` (all of them, or any with mode='any'). */
export function usePermission(perm: PermissionRequirement, mode: PermissionMode = 'all'): boolean {
  return checkPermission(useGranted(), perm, mode)
}

/** A checker bound to the current user, for filtering lists (row actions, menus). */
export function usePermissionCheck(): (perm: PermissionRequirement, mode?: PermissionMode) => boolean {
  const granted = useGranted()
  return React.useCallback(
    (perm: PermissionRequirement, mode: PermissionMode = 'all') => checkPermission(granted, perm, mode),
    [granted]
  )
}

export function PermissionGate({
  permission,
  mode = 'all',
  fallback = null,
  children,
}: {
  permission: PermissionRequirement
  mode?: PermissionMode
  fallback?: React.ReactNode
  children: React.ReactNode
}) {
  const allowed = usePermission(permission, mode)
  return <>{allowed ? children : fallback}</>
}
