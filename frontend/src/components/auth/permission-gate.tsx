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

/**
 * Inside a read-only scope (an archived incident) only reading permissions
 * count, so every mutation control gated through this module disappears.
 * The backend refuses the writes anyway (409 `incident_archived`).
 */
const ReadOnlyContext = React.createContext(false)

const READ_ONLY_ALLOWED = /:(read|read_[a-z_]+|export|download|reveal)$/

export function isReadOnlyPermission(perm: string): boolean {
  return READ_ONLY_ALLOWED.test(perm)
}

export function ReadOnlyScope({ active, children }: { active: boolean; children: React.ReactNode }) {
  return <ReadOnlyContext.Provider value={active}>{children}</ReadOnlyContext.Provider>
}

export function useReadOnlyScope(): boolean {
  return React.useContext(ReadOnlyContext)
}

function useGranted(): readonly string[] {
  const granted = useAuthStore((s) => s.user?.permissions) ?? EMPTY
  const readOnly = React.useContext(ReadOnlyContext)
  return React.useMemo(
    () => (readOnly ? granted.filter(isReadOnlyPermission) : granted),
    [granted, readOnly]
  )
}

/** Whether the current user holds `perm` (all of them, or any with mode='any'). */
export function usePermission(perm: PermissionRequirement, mode: PermissionMode = 'all'): boolean {
  return checkPermission(useGranted(), perm, mode)
}

/**
 * Like `usePermission` but ignoring an archived incident's read-only scope.
 * Only for records-management controls the API allows on archived incidents
 * (`allow_archived_writes`: legal holds).
 */
export function usePermissionIgnoringReadOnly(perm: PermissionRequirement, mode: PermissionMode = 'all'): boolean {
  const granted = useAuthStore((s) => s.user?.permissions) ?? EMPTY
  return checkPermission(granted, perm, mode)
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
