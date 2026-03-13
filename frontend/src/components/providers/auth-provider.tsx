"use client"

import { createContext, useContext, useEffect, ReactNode } from 'react'
import { useAuthStore } from '@/lib/store'
import { useRouter, usePathname } from 'next/navigation'

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

const publicPaths = ['/', '/login', '/register']

/**
 * Route-level authorization rules.
 * Maps route prefixes to required permissions or roles.
 * If the user lacks the required access, they are redirected to /dashboard.
 */
const routeGuards: { path: string; permission?: string; roles?: string[] }[] = [
  // Admin pages — only Administrators
  { path: '/dashboard/admin/users', permission: 'users:manage' },
  { path: '/dashboard/admin/roles', permission: 'users:manage' },
  { path: '/dashboard/admin/teams', permission: 'users:manage' },
  { path: '/dashboard/admin/security', roles: ['Administrator'] },
  { path: '/dashboard/admin/settings', roles: ['Administrator'] },
  { path: '/dashboard/admin/organization', roles: ['Administrator'] },
  { path: '/dashboard/admin/sso', roles: ['Administrator'] },
  { path: '/dashboard/activity', permission: 'audit_logs:read' },
  // Reports — requires reports:read
  { path: '/dashboard/reports', permission: 'reports:read' },
  // Create incident — requires incidents:create
  { path: '/dashboard/incidents/new', permission: 'incidents:create' },
]

export function AuthProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading, checkAuth, user } = useAuthStore()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  useEffect(() => {
    if (!isLoading) {
      const isPublicPath = publicPaths.includes(pathname)

      if (!isAuthenticated && !isPublicPath) {
        router.push('/login')
      } else if (isAuthenticated && (pathname === '/login' || pathname === '/register')) {
        router.push('/dashboard')
      } else if (isAuthenticated && user) {
        // Check route-level authorization
        for (const guard of routeGuards) {
          if (pathname === guard.path || pathname.startsWith(guard.path + '/')) {
            let authorized = true

            if (guard.permission) {
              authorized = user.permissions?.includes(guard.permission) ?? false
            }
            if (guard.roles && authorized) {
              authorized = guard.roles.some(role => user.roles?.includes(role))
            }

            // Administrators always have access
            if (user.roles?.includes('Administrator')) {
              authorized = true
            }

            if (!authorized) {
              router.replace('/dashboard')
              return
            }
            break
          }
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
