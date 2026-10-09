import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, render } from '@testing-library/react'
import type { User } from '@/lib/store'

// next/navigation stand-in (modules under test are imported after the mock).
const mockReplace = jest.fn()
const mockPush = jest.fn()
let mockPathname = '/dashboard'
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  usePathname: () => mockPathname,
}))

type Mod = typeof import('./auth-provider')
let AuthProvider: Mod['AuthProvider']
let isRouteAllowed: Mod['isRouteAllowed']
let routeGuards: Mod['routeGuards']
let useAuthStore: typeof import('@/lib/store').useAuthStore

beforeAll(async () => {
  ;({ AuthProvider, isRouteAllowed, routeGuards } = await import('./auth-provider'))
  ;({ useAuthStore } = await import('@/lib/store'))
})
const replace = mockReplace
const push = mockPush

function user(roles: string[], permissions: string[]): User {
  return { id: 'u1', email: 'u@example.test', name: 'U', roles, permissions }
}

function renderAt(path: string, u: User) {
  mockPathname = path
  act(() => {
    useAuthStore.setState({ user: u, isAuthenticated: true, isLoading: false, checkAuth: async () => {} })
  })
  render(
    <AuthProvider>
      <div />
    </AuthProvider>
  )
}

beforeEach(() => {
  replace.mockReset()
  push.mockReset()
})

afterEach(() => {
  cleanup()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: true })
  })
})

describe('route guards', () => {
  it('use permissions only (anyOf), never role names', () => {
    for (const guard of routeGuards) {
      expect(guard.anyOf.length).toBeGreaterThan(0)
      guard.anyOf.forEach((p) => expect(p).toMatch(/^[a-z_]+:[a-z_]+$/))
    }
    expect(routeGuards.some((g) => /sso|admin\/security|admin\/organization/.test(g.path))).toBe(false)
  })

  it('allows a route when any listed permission is held', () => {
    expect(isRouteAllowed('/dashboard/admin/users', ['users:update'])).toBe(true)
    expect(isRouteAllowed('/dashboard/admin/users/123', ['users:read'])).toBe(false)
    expect(isRouteAllowed('/dashboard/admin/settings', ['admin:manage'])).toBe(true)
    expect(isRouteAllowed('/dashboard/incidents/abc', [])).toBe(true)
  })

  it('redirects an "Administrator" by name who lacks the permission (no role bypass)', () => {
    renderAt('/dashboard/admin/users', user(['Administrator'], ['incidents:read', 'audit_logs:read']))
    expect(replace).toHaveBeenCalledWith('/dashboard')
  })

  it('lets a holder of incidents:archive reach archived incidents', () => {
    renderAt('/dashboard/admin/archived-incidents', user(['Archivist'], ['incidents:read', 'incidents:archive']))
    expect(replace).not.toHaveBeenCalled()
  })

  it('redirects an Analyst away from settings', () => {
    renderAt('/dashboard/admin/settings', user(['Analyst'], ['incidents:read', 'incidents:read_team', 'reports:read']))
    expect(replace).toHaveBeenCalledWith('/dashboard')
  })
})
