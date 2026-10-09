"use client"

import { createContext, useContext, useEffect, ReactNode } from 'react'
import { useAuthStore } from '@/lib/store'
import { useRouter, usePathname } from 'next/navigation'
import { isPublicPath } from '@/lib/api'

interface AuthContextType {
  isAuthenticated: boolean
  isLoading: boolean
}

const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  isLoading: true,
})

export function useAuth() {
  return useContext(AuthContext)
}

/**
 * Route-level authorization rules: the user needs ANY of `anyOf`.
 * Permissions only, never role names (there is no Administrator bypass).
 * Cosmetic: every endpoint behind these pages enforces its own permission.
 * The first matching prefix wins; a user lacking access goes to /dashboard.
 */
export interface RouteGuard {
  path: string
  anyOf: string[]
}

export const routeGuards: RouteGuard[] = [
  { path: '/dashboard/admin/users', anyOf: ['users:create', 'users:update', 'users:manage'] },
  { path: '/dashboard/admin/roles', anyOf: ['roles:manage', 'users:read'] },
  { path: '/dashboard/admin/teams', anyOf: ['teams:create', 'teams:update', 'teams:delete'] },
  { path: '/dashboard/admin/settings', anyOf: ['organizations:manage', 'integrations:read', 'admin:manage'] },
  { path: '/dashboard/admin/archived-incidents', anyOf: ['incidents:archive'] },
  { path: '/dashboard/admin/overview', anyOf: ['organizations:manage'] },
  { path: '/dashboard/admin/templates', anyOf: ['templates:manage'] },
  { path: '/dashboard/activity', anyOf: ['audit_logs:read'] },
  { path: '/dashboard/metrics', anyOf: ['metrics:read'] },
  { path: '/dashboard/improvements', anyOf: ['improvements:read'] },
  { path: '/dashboard/reports', anyOf: ['reports:read'] },
  { path: '/dashboard/incidents/new', anyOf: ['incidents:create'] },
]

/** Whether a user holding `permissions` may open `pathname` (true when no guard matches). */
export function isRouteAllowed(pathname: string, permissions: readonly string[] | undefined): boolean {
  const guard = routeGuards.find((g) => pathname === g.path || pathname.startsWith(g.path + '/'))
  if (!guard) return true
  const granted = permissions ?? []
  return guard.anyOf.some((p) => granted.includes(p))
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading, checkAuth, user } = useAuthStore()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  useEffect(() => {
    if (!isLoading) {
      if (!isAuthenticated && !isPublicPath(pathname)) {
        router.push('/login')
      } else if (isAuthenticated && (pathname === '/login' || pathname === '/register')) {
        router.push('/dashboard')
      } else if (isAuthenticated && user) {
        if (!isRouteAllowed(pathname, user.permissions)) {
          router.replace('/dashboard')
        }
      }
    }
  }, [isAuthenticated, isLoading, pathname, router, user])

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading }}>
      {children}
    </AuthContext.Provider>
  )
}
