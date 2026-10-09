import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, render, screen, within } from '@testing-library/react'
import type { AdminOverview, SystemStatus } from '@/types'

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/dashboard/admin/overview',
  useRouter: () => ({ push: () => {}, replace: () => {} }),
}))

type PageMod = typeof import('./page')
let OverviewPage: PageMod['default']
let api: typeof import('@/lib/api').default
let useAuthStore: typeof import('@/lib/store').useAuthStore
let isRouteAllowed: typeof import('@/components/providers/auth-provider').isRouteAllowed
let navConfig: typeof import('@/components/layout/nav-config')

beforeAll(async () => {
  ;({ default: OverviewPage } = await import('./page'))
  ;({ default: api } = await import('@/lib/api'))
  ;({ useAuthStore } = await import('@/lib/store'))
  ;({ isRouteAllowed } = await import('@/components/providers/auth-provider'))
  navConfig = await import('@/components/layout/nav-config')
})

const OVERVIEW: AdminOverview = {
  users: {
    total: 12, active: 10, disabled: 2, by_role: { Administrator: 1, Analyst: 7 },
    mfa_enabled: 6, mfa_adoption_pct: 60, admins_without_mfa: 1, locked: null, pending_invites: null,
  },
  active_admin_count: 1,
  last_admin_warning: true,
  recent_admin_actions: [
    {
      id: 'a1', action: 'update_role', resource_type: 'role', resource_id: 'r-1',
      user_email: 'admin@x', created_at: '2026-10-09T08:00:00+00:00', has_changes: true,
    },
  ],
  registration_enabled: false,
}

const ORG_STATUS: SystemStatus = {
  infra_visible: false,
  storage: { backend: 'local' },
  ai_providers: [{ provider: 'ollama', source: 'integration', last_tested_at: null, last_test_ok: true }],
  integrations: [],
  counts: { users: 12, active_users: 10, incidents: 4, open_incidents: 2, artifacts: 3, artifact_bytes: 2048 },
  audit: {
    retention_days: null, legal_hold: false, total_rows: 900, oldest_entry_at: '2025-01-01T00:00:00+00:00',
    chain: { head_seq: 880, head_hash: 'ffeeddccbbaa99887766', purged_through_seq: 0, last_verified_at: null, last_verify_ok: null, legacy_unchained: 20 },
  },
  generated_at: '2026-10-09T12:00:00+00:00',
}

const INFRA_STATUS: SystemStatus = {
  ...ORG_STATUS,
  infra_visible: true,
  storage: { backend: 'local', disk: { ok: true, total_bytes: 1024 ** 3 * 100, free_bytes: 1024 ** 3 * 40, used_pct: 60 } },
  app: { version: '2.4.0', commit: 'abc123def4567890', environment: 'production' },
  database: { ok: true, latency_ms: 1.2, server_version: '16.4' },
  alembic: { ok: true, current: ['user_lifecycle'], head: ['user_lifecycle'], up_to_date: true },
  redis: { ok: false, error: 'unavailable' },
  rate_limiting: { enabled: true, storage: 'redis', default_limit: '600 per minute' },
}

let getSpy: jest.SpiedFunction<typeof import('@/lib/api').default.get>

function mockApi(overview: AdminOverview, status: SystemStatus) {
  getSpy = jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    if (endpoint === '/admin/overview') return overview
    if (endpoint === '/admin/system-status') return status
    throw new Error(`unexpected GET ${endpoint}`)
  }) as unknown as typeof api.get)
}

function signIn(permissions: string[]) {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions },
      isAuthenticated: true,
    })
  })
}

async function renderPage() {
  await act(async () => {
    render(<OverviewPage />)
  })
}

beforeEach(() => mockApi(OVERVIEW, ORG_STATUS))

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

describe('admin overview gating', () => {
  it('needs organizations:manage: no data is requested without it', async () => {
    signIn(['audit_logs:read', 'users:manage'])
    await renderPage()
    expect(screen.getByText(/don't have access to the admin overview/i)).toBeInTheDocument()
    expect(getSpy).not.toHaveBeenCalled()
  })

  it('route guard and nav entry follow organizations:manage (no role names)', () => {
    expect(isRouteAllowed('/dashboard/admin/overview', ['organizations:manage'])).toBe(true)
    expect(isRouteAllowed('/dashboard/admin/overview', ['audit_logs:read', 'users:manage'])).toBe(false)
    const ids = (perms: string[]) => navConfig.visibleAdminItems(perms).map((i) => i.id)
    expect(ids(['organizations:manage'])[0]).toBe('overview')
    expect(ids(['audit_logs:read'])).not.toContain('overview')
    expect(navConfig.adminNavigation[0]).toMatchObject({ href: '/dashboard/admin/overview', anyOf: ['organizations:manage'] })
  })

  it('/dashboard/admin lands on the first page the user may open', () => {
    expect(navConfig.adminLandingHref(['organizations:manage', 'audit_logs:read'])).toBe('/dashboard/admin/overview')
    expect(navConfig.adminLandingHref(['audit_logs:read'])).toBe('/dashboard/activity')
    expect(navConfig.adminLandingHref(['incidents:read'])).toBe('/dashboard')
  })
})

describe('admin overview content', () => {
  it('shows users, the last-admin warning and recent admin actions', async () => {
    signIn(['organizations:manage'])
    await renderPage()
    expect(screen.getByText('Only one active administrator')).toBeInTheDocument()
    const users = screen.getByTestId('overview-users')
    expect(within(users).getByText('Total').nextSibling).toHaveTextContent('12')
    expect(within(users).getByText('60%')).toBeInTheDocument()
    expect(within(users).getByText('1 administrator without MFA')).toBeInTheDocument()
    expect(within(users).getByText(/Self-registration is closed/)).toBeInTheDocument()
    // locked / pending_invites are null: hidden, not shown as 0.
    expect(within(users).queryByText('Locked')).toBeNull()
    expect(within(users).queryByText('Pending invites')).toBeNull()

    const recent = screen.getByTestId('overview-recent-actions')
    expect(within(recent).getByText('Update Role')).toBeInTheDocument()
    const all = within(recent).getByRole('link', { name: /All admin changes/ })
    expect(all).toHaveAttribute('href', '/dashboard/activity?audit.f.event_type=admin_action&audit.f.has_changes=true')
    expect(within(recent).getByRole('link', { name: /Update Role/ })).toHaveAttribute(
      'href',
      '/dashboard/activity?audit.f.event_type=admin_action&audit.f.resource_id=r-1'
    )
  })

  it('shows locked and pending invite counts once the backend reports them', async () => {
    mockApi({ ...OVERVIEW, last_admin_warning: false, users: { ...OVERVIEW.users, locked: 2, pending_invites: 3 } }, ORG_STATUS)
    signIn(['organizations:manage'])
    await renderPage()
    const users = screen.getByTestId('overview-users')
    expect(within(users).getByText('Locked').nextSibling).toHaveTextContent('2')
    expect(within(users).getByText('Pending invites').nextSibling).toHaveTextContent('3')
    expect(screen.queryByText('Only one active administrator')).toBeNull()
  })

  it('hides the infra sections when the backend does not return them', async () => {
    signIn(['organizations:manage'])
    await renderPage()
    expect(screen.getByTestId('status-storage')).toHaveTextContent('local')
    expect(screen.getByTestId('status-counts')).toHaveTextContent('2 open / 4')
    expect(screen.queryByTestId('status-infra')).toBeNull()
    expect(screen.queryByTestId('status-database')).toBeNull()
    const audit = screen.getByTestId('overview-audit')
    expect(audit).toHaveTextContent('Keep forever')
    expect(within(audit).getByText('Not verified yet')).toBeInTheDocument()
  })

  it('shows infra sections for platform admins, with failed probes as unavailable', async () => {
    mockApi(OVERVIEW, INFRA_STATUS)
    signIn(['organizations:manage', 'system:manage'])
    await renderPage()
    expect(screen.getByTestId('status-infra')).toBeInTheDocument()
    expect(screen.getByTestId('status-app')).toHaveTextContent('2.4.0')
    expect(screen.getByTestId('status-database')).toHaveTextContent('16.4')
    expect(screen.getByTestId('status-alembic')).toHaveTextContent('Up to date')
    expect(screen.getByTestId('status-redis')).toHaveTextContent('Unavailable')
    expect(screen.getByTestId('status-rate-limiting')).toHaveTextContent('600 per minute')
    expect(screen.getByTestId('status-storage')).toHaveTextContent('40 GB of 100 GB')
  })

  it('reports a failed section without hiding the rest', async () => {
    getSpy.mockImplementation((async (endpoint: string) => {
      if (endpoint === '/admin/overview') return OVERVIEW
      const { ApiError } = await import('@/lib/api')
      throw new ApiError(429, 'rate limited', { code: 'rate_limited' })
    }) as unknown as typeof api.get)
    signIn(['organizations:manage'])
    await renderPage()
    expect(screen.getByTestId('overview-users')).toBeInTheDocument()
    expect(screen.getByText('Too many requests — try again shortly.')).toBeInTheDocument()
  })
})
