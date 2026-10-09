/**
 * Admin navigation: the one definition behind the sidebar's Admin section and
 * the command palette's admin "Go to" commands.
 *
 * Each item is shown to holders of ANY of `anyOf` (same sets as the route
 * guards in auth-provider.tsx). Permissions only, never role names; the gating
 * is cosmetic, the pages and the API enforce.
 */
import type { LucideIcon } from 'lucide-react'
import { Activity, Archive, Settings, Shield, Users, UsersRound } from 'lucide-react'

export interface AdminNavItem {
  /** Stable id; the palette command is `nav-<id>`. */
  id: string
  name: string
  href: string
  icon: LucideIcon
  anyOf: string[]
  /** Extra palette search terms. */
  keywords?: string
}

export const adminNavigation: AdminNavItem[] = [
  { id: 'activity', name: 'Activity', href: '/dashboard/activity', icon: Activity, anyOf: ['audit_logs:read'], keywords: 'audit log' },
  { id: 'archived', name: 'Archived Incidents', href: '/dashboard/admin/archived-incidents', icon: Archive, anyOf: ['incidents:archive'] },
  { id: 'users', name: 'Users', href: '/dashboard/admin/users', icon: Users, anyOf: ['users:create', 'users:update', 'users:manage'], keywords: 'admin accounts' },
  { id: 'roles', name: 'Roles', href: '/dashboard/admin/roles', icon: Shield, anyOf: ['roles:manage', 'users:read'], keywords: 'admin permissions' },
  { id: 'teams', name: 'Teams', href: '/dashboard/admin/teams', icon: UsersRound, anyOf: ['teams:create', 'teams:update', 'teams:delete'], keywords: 'admin groups' },
  {
    id: 'settings',
    name: 'Settings',
    href: '/dashboard/admin/settings',
    icon: Settings,
    anyOf: ['organizations:manage', 'integrations:read', 'admin:manage'],
    keywords: 'admin organization integrations',
  },
]

/** Admin items a user holding `permissions` may see. */
export function visibleAdminItems(permissions: readonly string[] | undefined) {
  const granted = permissions ?? []
  return adminNavigation.filter((item) => item.anyOf.some((p) => granted.includes(p)))
}
