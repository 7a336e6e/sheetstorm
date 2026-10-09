import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import type { AuditLogEntry } from '@/types'

let mockSearch = ''
const mockReplace = jest.fn()
jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(mockSearch),
  usePathname: () => '/dashboard/activity',
  useRouter: () => ({ push: () => {}, replace: (url: string) => mockReplace(url) }),
}))

type PageMod = typeof import('./page')
let ActivityPage: PageMod['default']
let api: typeof import('@/lib/api').default
let useAuthStore: typeof import('@/lib/store').useAuthStore
let clearCache: typeof import('@/lib/query-cache').clearCache

beforeAll(async () => {
  ;({ default: ActivityPage } = await import('./page'))
  ;({ default: api } = await import('@/lib/api'))
  ;({ useAuthStore } = await import('@/lib/store'))
  ;({ clearCache } = await import('@/lib/query-cache'))
})

const ROW: AuditLogEntry = {
  id: 'log-1',
  event_type: 'admin_action',
  action: 'update_role',
  resource_type: 'role',
  resource_id: 'r-1',
  user_email: 'admin@x',
  request_method: 'PUT',
  status_code: 200,
  ip_address: '10.0.0.5',
  created_at: '2026-10-09T08:00:00+00:00',
  chain_seq: 42,
  row_hash: 'aa'.repeat(32),
  details: {
    changes: {
      permissions: { added: ['audit_logs:export'], removed: [] },
      'settings.ai_tlp_policy.red': { from: 'local_only', to: 'block' },
    },
    target_name: 'Analyst',
  },
}

let getSpy: jest.SpiedFunction<typeof import('@/lib/api').default.get>

function signIn(permissions: string[]) {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions },
      isAuthenticated: true,
    })
  })
}

beforeEach(() => {
  clearCache()
  mockReplace.mockClear()
  getSpy = jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    const path = endpoint.split('?')[0]
    if (path === '/audit-logs') return { items: [ROW], total: 1, page: 1, per_page: 50, pages: 1, sort: '-created_at' }
    if (path === '/audit-logs/facets') return { actions: ['update_role'], resource_types: ['role'], event_types: [] }
    if (path === '/audit-logs/stats') return { by_event_type: { security_event: 3 }, by_day: {}, total: 1 }
    throw new Error(`unexpected GET ${endpoint}`)
  }) as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

async function renderPage() {
  await act(async () => {
    render(<ActivityPage />)
  })
}

const calls = (path: string) =>
  getSpy.mock.calls.map((c) => c[0] as string).filter((e) => e.split('?')[0] === path)

describe('activity page: URL ↔ filters', () => {
  it('sends the URL filters, sort and page size to the list and the stats', async () => {
    mockSearch = 'audit.f.event_type=admin_action&audit.f.has_changes=true&audit.sort=-chain_seq&audit.per=100'
    signIn(['audit_logs:read'])
    await renderPage()
    const list = new URL(calls('/audit-logs')[0], 'http://x').searchParams
    expect(Object.fromEntries(list)).toEqual({
      event_type: 'admin_action',
      has_changes: 'true',
      page: '1',
      per_page: '100',
      sort: '-chain_seq',
    })
    const stats = new URL(calls('/audit-logs/stats')[0], 'http://x').searchParams
    expect(Object.fromEntries(stats)).toEqual({ event_type: 'admin_action', has_changes: 'true' })
    // Filters are active: the filter bar starts open and reflects them.
    const bar = screen.getByTestId('audit-filter-bar')
    expect(within(bar).getByRole('button', { name: 'Admin action' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(bar).getByRole('switch')).toHaveAttribute('data-state', 'checked')
  })

  it('writes filter changes back to the URL', async () => {
    mockSearch = 'audit.f.event_type=admin_action'
    signIn(['audit_logs:read'])
    await renderPage()
    const bar = screen.getByTestId('audit-filter-bar')
    act(() => {
      fireEvent.click(within(bar).getByRole('button', { name: 'Security event' }))
    })
    expect(mockReplace).toHaveBeenLastCalledWith('/dashboard/activity?audit.f.event_type=admin_action%2Csecurity_event')

    const ip = within(bar).getByLabelText('IP / CIDR')
    fireEvent.change(ip, { target: { value: '10.0.0.0/8' } })
    expect(mockReplace).toHaveBeenCalledTimes(1) // not per keystroke
    act(() => {
      fireEvent.keyDown(ip, { key: 'Enter' })
    })
    expect(mockReplace).toHaveBeenLastCalledWith(
      '/dashboard/activity?audit.f.event_type=admin_action%2Csecurity_event&audit.f.ip=10.0.0.0%2F8'
    )
  })

  it('rewrites legacy plain params (old links) into the audit.* form', async () => {
    const original = window.location.href
    window.history.replaceState(null, '', '/dashboard/activity?event_type=admin_action&has_changes=true')
    mockSearch = ''
    signIn(['audit_logs:read'])
    try {
      await renderPage()
      expect(mockReplace).toHaveBeenCalledWith('/dashboard/activity?audit.f.event_type=admin_action&audit.f.has_changes=true')
    } finally {
      window.history.replaceState(null, '', original)
    }
  })
})

describe('activity page: rows, diff and export gating', () => {
  it('expands a row into its details and the before/after diff', async () => {
    mockSearch = ''
    signIn(['audit_logs:read'])
    await renderPage()
    const table = screen.getByRole('grid', { name: 'Audit log' })
    expect(within(table).getByText('Update Role')).toBeInTheDocument()
    expect(within(table).getByText('diff')).toBeInTheDocument()
    act(() => {
      fireEvent.click(within(table).getByRole('button', { name: 'Expand row' }))
    })
    const detail = screen.getByTestId('audit-log-detail')
    const changes = within(detail).getByRole('table', { name: 'Changes' })
    expect(within(changes).getByText('audit_logs:export')).toBeInTheDocument()
    expect(within(changes).getByText('block')).toBeInTheDocument()
    expect(within(detail).getByText('#42')).toBeInTheDocument()
    // `changes` is rendered by the diff viewer, not dumped as raw JSON.
    expect(within(detail).queryByText('Changes:')).toBeNull()
    expect(within(detail).getByText('Target Name:')).toBeInTheDocument()
  })

  it('hides Export without audit_logs:export and shows it with it', async () => {
    mockSearch = ''
    signIn(['audit_logs:read'])
    await renderPage()
    expect(screen.queryByRole('button', { name: /^export$/i })).toBeNull()
    cleanup()
    signIn(['audit_logs:read', 'audit_logs:export'])
    await renderPage()
    expect(screen.getByRole('button', { name: /^export$/i })).toBeInTheDocument()
  })
})
