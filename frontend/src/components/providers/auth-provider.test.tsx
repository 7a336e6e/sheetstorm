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

  it('guards the metrics and improvements pages by their read permissions', () => {
    expect(isRouteAllowed('/dashboard/metrics', ['metrics:read'])).toBe(true)
    expect(isRouteAllowed('/dashboard/metrics', ['improvements:read', 'incidents:read'])).toBe(false)
    expect(isRouteAllowed('/dashboard/improvements', ['improvements:read'])).toBe(true)
    expect(isRouteAllowed('/dashboard/improvements', ['metrics:read'])).toBe(false)
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

describe('account restrictions (W2-LIFE-UI)', () => {
  it('routes a 403 password_change_required to /auth/change-password', async () => {
    const { default: api, ApiError } = await import('@/lib/api')
    // jsdom has no Response: a minimal stand-in for what the client reads.
    const fetchMock = jest.fn(async () => ({
      ok: false,
      status: 403,
      json: async () => ({ error: 'password_change_required', message: 'Change it' }),
    }))
    const realFetch = global.fetch
    global.fetch = fetchMock as unknown as typeof fetch
    try {
      renderAt('/dashboard/incidents', user(['Viewer'], ['incidents:read']))
      await expect(api.get('/incidents')).rejects.toBeInstanceOf(ApiError)
      expect(replace).toHaveBeenCalledWith('/auth/change-password')
    } finally {
      global.fetch = realFetch
    }
  })

  it('ignores codes without a route and unregisters on unmount', async () => {
    const { default: api } = await import('@/lib/api')
    const spy = jest.spyOn(api, 'setRestrictionHandler')
    renderAt('/dashboard', user(['Viewer'], ['incidents:read']))
    const handler = spy.mock.calls.find(([h]) => typeof h === 'function')?.[0] as (code: string) => void
    handler('some_future_restriction')
    expect(replace).not.toHaveBeenCalled()
    cleanup()
    expect(spy).toHaveBeenLastCalledWith(null)
    spy.mockRestore()
  })

  it('sends a user who must change their password to /auth/change-password', () => {
    renderAt('/dashboard', { ...user(['Viewer'], ['incidents:read']), must_change_password: true } as User)
    expect(replace).toHaveBeenCalledWith('/auth/change-password')
  })

  it('does not loop on the change-password page itself', () => {
    renderAt('/auth/change-password', { ...user(['Viewer'], ['incidents:read']), must_change_password: true } as User)
    expect(replace).not.toHaveBeenCalled()
  })
})

describe('MFA enrollment required by the security policy (W3-SEC)', () => {
  const restricted = (over: Partial<User> = {}): User => ({
    ...user(['Analyst'], ['incidents:read']),
    security: {
      mfa_required: true,
      mfa_enrollment_required: true,
      mfa_grace_ends_at: '2026-10-01T00:00:00Z',
      password_change_required: false,
      password_expires_at: null,
    },
    ...over,
  })

  it('maps the 403 code to the profile enrollment page', async () => {
    const { RESTRICTION_ROUTES } = await import('./auth-provider')
    expect(RESTRICTION_ROUTES.mfa_enrollment_required).toBe('/dashboard/profile?enroll_mfa=1')
    const { default: api } = await import('@/lib/api')
    const spy = jest.spyOn(api, 'setRestrictionHandler')
    renderAt('/dashboard', user(['Viewer'], ['incidents:read']))
    const handler = spy.mock.calls.find(([h]) => typeof h === 'function')?.[0] as (code: string) => void
    handler('mfa_enrollment_required')
    expect(replace).toHaveBeenCalledWith('/dashboard/profile?enroll_mfa=1')
    spy.mockRestore()
  })

  it('keeps a restricted user on the profile enrollment page', () => {
    renderAt('/dashboard/incidents', restricted())
    expect(replace).toHaveBeenCalledWith('/dashboard/profile?enroll_mfa=1')
  })

  it('does not loop on the profile page itself', () => {
    renderAt('/dashboard/profile', restricted())
    expect(replace).not.toHaveBeenCalled()
  })

  it('does not redirect during the grace period or once enrolled', () => {
    const graced = restricted()
    graced.security = { ...graced.security!, mfa_enrollment_required: false }
    renderAt('/dashboard/incidents', graced)
    cleanup()
    renderAt('/dashboard/incidents', restricted({ mfa_enabled: true }))
    expect(replace).not.toHaveBeenCalled()
  })

  it('a forced password change comes first', () => {
    renderAt('/dashboard', restricted({ must_change_password: true }))
    expect(replace).toHaveBeenCalledWith('/auth/change-password')
    expect(replace).not.toHaveBeenCalledWith('/dashboard/profile?enroll_mfa=1')
  })
})
