import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, render, screen } from '@testing-library/react'
import type { User } from '@/lib/store'

jest.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
  useRouter: () => ({ push: () => {}, replace: () => {} }),
  // NotificationPanel (W1-LST) pages through usePaginatedQuery.
  useSearchParams: () => new URLSearchParams(),
}))

type Mod = typeof import('./sidebar')
let Sidebar: Mod['Sidebar']
let visibleAdminItems: Mod['visibleAdminItems']
let useAuthStore: typeof import('@/lib/store').useAuthStore
let api: typeof import('@/lib/api').default

beforeAll(async () => {
  ;({ Sidebar, visibleAdminItems } = await import('./sidebar'))
  ;({ useAuthStore } = await import('@/lib/store'))
  ;({ default: api } = await import('@/lib/api'))
})

function signIn(roles: string[], permissions: string[]) {
  const u: User = { id: 'u1', email: 'u@example.test', name: 'U', roles, permissions }
  act(() => {
    useAuthStore.setState({ user: u, isAuthenticated: true, isLoading: false })
  })
}

beforeEach(() => {
  jest.spyOn(api, 'get').mockResolvedValue({ unread_count: 0, items: [] } as never)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

const adminLinks = () => {
  const heading = screen.queryByText('Admin')
  if (!heading) return []
  return Array.from(heading.parentElement!.querySelectorAll('a')).map((a) => a.textContent)
}

describe('Sidebar admin section', () => {
  it('is absent for an Analyst', async () => {
    signIn(['Analyst'], ['incidents:read', 'incidents:read_team', 'reports:read', 'teams:read'])
    await act(async () => {
      render(<Sidebar />)
    })
    expect(screen.queryByText('Admin')).toBeNull()
  })

  it('shows exactly the items the permissions allow', async () => {
    // A Manager-like custom role: audit log + archive + read users/roles.
    signIn(['Ops lead'], ['audit_logs:read', 'incidents:archive', 'users:read'])
    await act(async () => {
      render(<Sidebar />)
    })
    expect(adminLinks()).toEqual(['Activity', 'Archived Incidents', 'Roles'])
  })

  it('does not depend on the Administrator role name', async () => {
    signIn(['Administrator'], ['incidents:read'])
    await act(async () => {
      render(<Sidebar />)
    })
    expect(screen.queryByText('Admin')).toBeNull()
  })

  it('lists every item for a full administrator', () => {
    const all = visibleAdminItems([
      'audit_logs:read', 'incidents:archive', 'users:manage', 'roles:manage', 'teams:create', 'organizations:manage',
    ])
    expect(all.map((i) => i.name)).toEqual(['Overview', 'Activity', 'Archived Incidents', 'Users', 'Roles', 'Teams', 'Settings'])
  })
})

describe('Sidebar main navigation (W3-RT-POST)', () => {
  const mainLinks = async () => {
    await act(async () => {
      render(<Sidebar />)
    })
    return screen.getAllByRole('link').map((a) => a.textContent)
  }

  it('shows Metrics and Improvements only to holders of metrics:read / improvements:read', async () => {
    signIn(['Analyst'], ['incidents:read', 'improvements:read'])
    const links = await mainLinks()
    expect(links).toContain('Improvements')
    expect(links).not.toContain('Metrics')
  })

  it('shows both for a manager-like role, and neither for a user with neither permission', async () => {
    signIn(['Manager'], ['incidents:read', 'metrics:read', 'improvements:read'])
    expect(await mainLinks()).toEqual(expect.arrayContaining(['Metrics', 'Improvements']))
    cleanup()
    signIn(['Nobody'], ['incidents:read'])
    const links = await mainLinks()
    expect(links).not.toContain('Metrics')
    expect(links).not.toContain('Improvements')
  })

  it('links to the guarded routes', async () => {
    signIn(['Manager'], ['metrics:read', 'improvements:read'])
    await act(async () => {
      render(<Sidebar />)
    })
    expect(screen.getByRole('link', { name: 'Metrics' })).toHaveAttribute('href', '/dashboard/metrics')
    expect(screen.getByRole('link', { name: 'Improvements' })).toHaveAttribute('href', '/dashboard/improvements')
  })
})
