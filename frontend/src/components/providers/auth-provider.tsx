"use client"

import { createContext, useContext, useEffect, ReactNode } from 'react'
import { needsMfaEnrollment, useAuthStore } from '@/lib/store'
import { useRouter, usePathname } from 'next/navigation'
import { isPublicPath, setRestrictionHandler } from '@/lib/api'

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
  { path: '/dashboard/admin/settings', anyOf: ['organizations:manage', 'integrations:read', 'admin:manage', 'users:manage'] },
  { path: '/dashboard/admin/archived-incidents', anyOf: ['incidents:archive'] },
  { path: '/dashboard/admin/overview', anyOf: ['organizations:manage'] },
  { path: '/dashboard/admin/templates', anyOf: ['templates:manage'] },
  { path: '/dashboard/activity', anyOf: ['audit_logs:read'] },
  { path: '/dashboard/metrics', anyOf: ['metrics:read'] },
  { path: '/dashboard/improvements', anyOf: ['improvements:read'] },
  { path: '/dashboard/reports', anyOf: ['reports:read'] },
  { path: '/dashboard/incidents/new', anyOf: ['incidents:create'] },
]

/**
 * Where each account restriction (403 from the backend `account_state` gate)
 * is lifted: a forced password change, and MFA enrollment required by the
 * org security policy after its grace period (W3-SEC).
 */
export const RESTRICTION_ROUTES: Record<string, string> = {
  password_change_required: '/auth/change-password',
  mfa_enrollment_required: '/dashboard/profile?enroll_mfa=1',
}

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

  // A request refused by an account restriction routes to the page that lifts it.
  useEffect(() => {
    setRestrictionHandler((code) => {
      const target = RESTRICTION_ROUTES[code]
      if (target && window.location.pathname !== target.split('?')[0]) router.replace(target)
    })
    return () => setRestrictionHandler(null)
  }, [router])

  const mustChangePassword = !!user?.must_change_password
  const mustEnrollMfa = needsMfaEnrollment(user)
  const mfaRoute = RESTRICTION_ROUTES.mfa_enrollment_required

  useEffect(() => {
    if (!isLoading) {
      if (!isAuthenticated && !isPublicPath(pathname)) {
        router.push('/login')
      } else if (isAuthenticated && mustChangePassword && pathname !== RESTRICTION_ROUTES.password_change_required) {
        router.replace(RESTRICTION_ROUTES.password_change_required)
      } else if (isAuthenticated && !mustChangePassword && mustEnrollMfa && pathname !== mfaRoute.split('?')[0]) {
        router.replace(mfaRoute)
      } else if (isAuthenticated && (pathname === '/login' || pathname === '/register')) {
        router.push('/dashboard')
      } else if (isAuthenticated && user) {
        if (!isRouteAllowed(pathname, user.permissions)) {
          router.replace('/dashboard')
        }
      }
    }
  }, [isAuthenticated, isLoading, mustChangePassword, mustEnrollMfa, mfaRoute, pathname, router, user])

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading }}>
      {children}
    </AuthContext.Provider>
  )
}
