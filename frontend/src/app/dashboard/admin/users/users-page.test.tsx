import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import '@testing-library/jest-dom/jest-globals'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useSyncExternalStore } from 'react'
import api, { ApiError } from '@/lib/api'
import { clearCache } from '@/lib/query-cache'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import type { AdminUser, Role, Team, UserStats } from '@/types'

// ── next/navigation stand-in backed by a tiny URL store ───────────────
let mockSearch = ''
const mockListeners = new Set<() => void>()
const mockReplace = jest.fn((url: string) => {
  const i = url.indexOf('?')
  mockSearch = i === -1 ? '' : url.slice(i + 1)
  window.history.replaceState(null, '', url)
  mockListeners.forEach((l) => l())
})
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: mockReplace }),
  usePathname: () => '/dashboard/admin/users',
  useSearchParams: () => {
    const search = useSyncExternalStore(
      (cb) => {
        mockListeners.add(cb)
        return () => mockListeners.delete(cb)
      },
      () => mockSearch
    )
    return new URLSearchParams(search)
  },
}))

let UsersPage: typeof import('./page').default
beforeAll(async () => {
  ;({ default: UsersPage } = await import('./page'))
})

const ADMIN_PERMS = [
  'users:read',
  'users:create',
  'users:update',
  'users:manage',
  'users:delete',
  'roles:manage',
  'audit_logs:read',
  'incidents:read',
]

const roles: Role[] = [
  { id: 'r-admin', name: 'Administrator', description: '', is_system: true, permissions: ADMIN_PERMS },
  { id: 'r-viewer', name: 'Viewer', description: '', is_system: true, permissions: ['incidents:read'] },
]
const teams: Team[] = [{ id: 't1', name: 'Blue Team', is_default: false, member_count: 1, created_at: '2026-01-01T00:00:00Z' }]

const alice: AdminUser = {
  id: 'u-alice',
  email: 'alice@x.test',
  name: 'Alice',
  roles: ['Viewer'],
  is_active: true,
  is_locked: true,
  locked_until: '2026-10-09T12:00:00Z',
  mfa_enabled: true,
  must_change_password: false,
  created_at: '2026-01-01T00:00:00Z',
}
const bob: AdminUser = {
  id: 'u-bob',
  email: 'bob@x.test',
  name: 'Bob',
  roles: ['Viewer'],
  is_active: false,
  deactivated_at: '2026-10-01T00:00:00Z',
  created_at: '2026-01-02T00:00:00Z',
}
const me: AdminUser = {
  id: 'u-admin',
  email: 'admin@x.test',
  name: 'Admin',
  roles: ['Administrator'],
  is_active: true,
  created_at: '2026-01-03T00:00:00Z',
}
const stats: UserStats = {
  total: 3,
  active: 2,
  disabled: 1,
  locked: 1,
  mfa_enabled: 1,
  must_change_password: 0,
  pending_invites: 4,
  by_role: { Viewer: 2, Administrator: 1 },
}

type GetFn = (endpoint: string, opts?: { signal?: AbortSignal }) => Promise<unknown>
type PostFn = (endpoint: string, data?: unknown) => Promise<unknown>
let getSpy: jest.Mock<GetFn>
let postSpy: jest.Mock<PostFn>
let deleteSpy: jest.Mock<PostFn>

function setPermissions(permissions: string[]) {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u-admin', email: 'admin@x.test', name: 'Admin', roles: ['Administrator'], permissions },
    })
  })
}

function renderPage() {
  return render(
    <ConfirmDialogProvider>
      <UsersPage />
    </ConfirmDialogProvider>
  )
}

function usersParams(): URLSearchParams {
  const calls = getSpy.mock.calls.filter(([e]) => e.startsWith('/users?'))
  return new URLSearchParams(calls[calls.length - 1][0].split('?')[1])
}

function called(spy: jest.Mock<PostFn>, endpoint: string): boolean {
  return spy.mock.calls.some(([e]) => e === endpoint)
}

function rowOf(text: string): HTMLElement {
  return screen.getAllByRole('row').find((r) => within(r).queryByText(text))!
}

async function openRowMenu(text: string): Promise<HTMLElement> {
  fireEvent.keyDown(rowOf(text), { key: '.' })
  return screen.findByRole('menu')
}

async function chooseOption(trigger: HTMLElement, name: string | RegExp) {
  fireEvent.keyDown(trigger, { key: 'ArrowDown' })
  fireEvent.click(await screen.findByRole('option', { name }))
}

beforeEach(() => {
  clearCache()
  mockSearch = ''
  window.history.replaceState(null, '', '/dashboard/admin/users')
  mockReplace.mockClear()
  getSpy = jest.fn<GetFn>(async (endpoint) => {
    const path = endpoint.split('?')[0]
    if (path === '/roles') return { items: roles }
    if (path === '/teams') return { items: teams }
    if (path === '/permissions') return { groups: [], items: [] }
    if (path === '/users/stats') return stats
    if (path === '/users/invites') return { items: [], total: 0, page: 1, per_page: 25, pages: 0 }
    if (path === '/users') return { items: [alice, bob, me], total: 3, page: 1, per_page: 25, pages: 1 }
    if (path.endsWith('/activity')) return { items: [], total: 0, page: 1, per_page: 20, pages: 0 }
    if (path.startsWith('/users/')) return alice
    throw new ApiError(404, 'not found')
  })
  postSpy = jest.fn<PostFn>(async () => ({}))
  deleteSpy = jest.fn<PostFn>(async () => ({}))
  jest.spyOn(api, 'get').mockImplementation(getSpy as unknown as typeof api.get)
  jest.spyOn(api, 'post').mockImplementation(postSpy as unknown as typeof api.post)
  jest.spyOn(api, 'delete').mockImplementation(deleteSpy as unknown as typeof api.delete)
})

afterEach(async () => {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0))
  })
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null })
  })
})

describe('Users admin page: gating', () => {
  it('hides lifecycle actions without users:manage / users:create / users:delete', async () => {
    setPermissions(['users:read', 'users:update'])
    renderPage()
    expect(await screen.findByText('alice@x.test')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /invite user/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /add user/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /sync supabase/i })).toBeNull()
    expect(screen.queryByRole('tab', { name: /pending invites/i })).toBeNull()
    expect(screen.queryByRole('checkbox', { name: /select all rows/i })).toBeNull()

    const menu = await openRowMenu('alice@x.test')
    const items = within(menu)
      .getAllByRole('menuitem')
      .map((i) => i.textContent)
    expect(items).toEqual(['View details', 'Edit'])
  })

  it('offers every action to an admin, but no account actions on your own row', async () => {
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('alice@x.test')
    expect(screen.getByRole('button', { name: /invite user/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add user/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sync supabase/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /pending invites/i })).toBeInTheDocument()

    let menu = await openRowMenu('alice@x.test')
    const names = within(menu)
      .getAllByRole('menuitem')
      .map((i) => i.textContent)
    expect(names).toEqual(
      expect.arrayContaining(['Unlock', 'Reset password', 'Force logout', 'Reset MFA', 'Disable', 'Delete'])
    )
    expect(names).not.toContain('Enable')
    fireEvent.keyDown(menu, { key: 'Escape' })

    menu = await openRowMenu('bob@x.test')
    const bobNames = within(menu)
      .getAllByRole('menuitem')
      .map((i) => i.textContent)
    expect(bobNames).toContain('Enable')
    expect(bobNames).not.toContain('Disable')
    expect(bobNames).not.toContain('Unlock')
    expect(bobNames).not.toContain('Reset MFA')
    fireEvent.keyDown(menu, { key: 'Escape' })

    menu = await openRowMenu('admin@x.test')
    expect(
      within(menu)
        .getAllByRole('menuitem')
        .map((i) => i.textContent)
    ).toEqual(['View details', 'Edit'])
  })

  it('badges service accounts and offers them no password reset', async () => {
    const bot: AdminUser = {
      id: 'u-bot',
      email: 'svc-siem@x.test',
      name: 'SIEM bot',
      roles: ['Viewer'],
      is_active: true,
      is_service_account: true,
      created_at: '2026-01-04T00:00:00Z',
    }
    getSpy.mockImplementation(async (endpoint) => {
      const path = endpoint.split('?')[0]
      if (path === '/users') return { items: [bot, alice], total: 2, page: 1, per_page: 25, pages: 1 }
      if (path === '/users/stats') return stats
      return { items: [] }
    })
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('svc-siem@x.test')
    expect(within(rowOf('svc-siem@x.test')).getByText('Service account')).toBeInTheDocument()
    expect(within(rowOf('alice@x.test')).queryByText('Service account')).toBeNull()

    let menu = await openRowMenu('svc-siem@x.test')
    const names = within(menu)
      .getAllByRole('menuitem')
      .map((i) => i.textContent)
    expect(names).not.toContain('Reset password')
    expect(names).toContain('Disable')
    fireEvent.keyDown(menu, { key: 'Escape' })
    menu = await openRowMenu('alice@x.test')
    expect(within(menu).getByRole('menuitem', { name: 'Reset password' })).toBeInTheDocument()
  })

  it('shows org-wide stats from /users/stats', async () => {
    setPermissions(ADMIN_PERMS)
    renderPage()
    const cards = await screen.findByLabelText('User statistics')
    await waitFor(() => expect(within(cards).getByText('Pending invites').parentElement).toHaveTextContent('4'))
    expect(within(cards).getByText('Locked').parentElement).toHaveTextContent('1')
  })
})

describe('Users admin page: filters and URL', () => {
  it('reads filters from the URL into the request', async () => {
    mockSearch = 'users.f.status=locked&users.f.mfa=true&users.f.team_id=t1&users.q=ali&users.sort=-last_login'
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('alice@x.test')
    const p = usersParams()
    expect(p.get('status')).toBe('locked')
    expect(p.get('mfa')).toBe('true')
    expect(p.get('team_id')).toBe('t1')
    expect(p.get('q')).toBe('ali')
    expect(p.get('sort')).toBe('-last_login')
    expect(p.get('per_page')).toBe('25')
  })

  it('writes a filter change to the URL and refetches', async () => {
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('alice@x.test')
    await chooseOption(screen.getByRole('combobox', { name: 'Status' }), 'Disabled')
    await waitFor(() => expect(mockReplace).toHaveBeenCalled())
    expect(new URLSearchParams(mockSearch).get('users.f.status')).toBe('disabled')
    await waitFor(() => expect(usersParams().get('status')).toBe('disabled'))

    await chooseOption(screen.getByRole('combobox', { name: 'Role' }), 'Viewer')
    await waitFor(() => expect(usersParams().get('role_id')).toBe('r-viewer'))
  })
})

describe('Users admin page: actions', () => {
  it('disables with a required reason', async () => {
    postSpy.mockImplementation(async () => ({ user: { ...alice, is_active: false } }))
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('alice@x.test')
    fireEvent.click(within(await openRowMenu('alice@x.test')).getByRole('menuitem', { name: 'Disable' }))
    const dialog = await screen.findByRole('dialog')
    const submit = within(dialog).getByRole('button', { name: 'Disable user' })
    expect(submit).toBeDisabled()
    fireEvent.change(within(dialog).getByLabelText('Reason'), { target: { value: '  Compromised laptop  ' } })
    fireEvent.click(submit)
    await waitFor(() => expect(postSpy).toHaveBeenCalledWith('/users/u-alice/disable', { reason: 'Compromised laptop' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('shows a guard refusal inside the disable dialog', async () => {
    postSpy.mockImplementation(async () => {
      throw new ApiError(409, 'This change would leave the organization without an administrator', {
        code: 'last_admin',
      })
    })
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('alice@x.test')
    fireEvent.click(within(await openRowMenu('alice@x.test')).getByRole('menuitem', { name: 'Disable' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Reason'), { target: { value: 'offboarding' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Disable user' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Last administrator')
  })

  it('shows a temporary password once and drops it on close', async () => {
    postSpy.mockImplementation(async () => ({ mode: 'temp', temp_password: 'Tmp-Secret-123!abc' }))
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('alice@x.test')
    fireEvent.click(within(await openRowMenu('alice@x.test')).getByRole('menuitem', { name: 'Reset password' }))
    let dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByLabelText(/temporary password/i))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reset password' }))
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/users/u-alice/reset-password', { mode: 'temp' })
    )
    expect(await within(dialog).findByDisplayValue('Tmp-Secret-123!abc')).toBeInTheDocument()
    expect(within(dialog).getByText(/shown once/i)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.queryByDisplayValue('Tmp-Secret-123!abc')).toBeNull()

    // Reopening starts from the form, not the old secret.
    fireEvent.click(within(await openRowMenu('alice@x.test')).getByRole('menuitem', { name: 'Reset password' }))
    dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByDisplayValue('Tmp-Secret-123!abc')).toBeNull()
    expect(within(dialog).getByRole('button', { name: 'Reset password' })).toBeInTheDocument()
  })

  it('builds a reset link from the current origin', async () => {
    postSpy.mockImplementation(async () => ({
      mode: 'link',
      token: 'tok',
      accept_path: '/auth/reset-password#token=tok',
      expires_at: '2026-10-10T00:00:00Z',
    }))
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('alice@x.test')
    fireEvent.click(within(await openRowMenu('alice@x.test')).getByRole('menuitem', { name: 'Reset password' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reset password' }))
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/users/u-alice/reset-password', { mode: 'link', revoke_sessions: true })
    )
    expect(
      await within(dialog).findByDisplayValue(`${window.location.origin}/auth/reset-password#token=tok`)
    ).toBeInTheDocument()
  })

  it('force logout and reset MFA confirm first', async () => {
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('alice@x.test')
    fireEvent.click(within(await openRowMenu('alice@x.test')).getByRole('menuitem', { name: 'Force logout' }))
    let dialog = await screen.findByRole('dialog')
    expect(postSpy).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Force logout' }))
    await waitFor(() => expect(called(postSpy, '/users/u-alice/force-logout')).toBe(true))

    fireEvent.click(within(await openRowMenu('alice@x.test')).getByRole('menuitem', { name: 'Reset MFA' }))
    dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(called(postSpy, '/users/u-alice/reset-mfa')).toBe(false)
  })

  it('unlocks and enables without a confirm', async () => {
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('alice@x.test')
    fireEvent.click(within(await openRowMenu('alice@x.test')).getByRole('menuitem', { name: 'Unlock' }))
    await waitFor(() => expect(called(postSpy, '/users/u-alice/unlock')).toBe(true))
    fireEvent.click(within(await openRowMenu('bob@x.test')).getByRole('menuitem', { name: 'Enable' }))
    await waitFor(() => expect(called(postSpy, '/users/u-bob/enable')).toBe(true))
  })

  it('delete needs the email typed, and offers "Disable instead" on 409 user_has_records', async () => {
    deleteSpy.mockImplementation(async () => {
      throw new ApiError(409, 'This user is referenced by records they authored; deactivate the user instead', {
        code: 'user_has_records',
        details: { error: 'user_has_records', counts: { incidents: 2, case_notes: 1 }, hint: 'deactivate' },
      })
    })
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('alice@x.test')
    fireEvent.click(within(await openRowMenu('alice@x.test')).getByRole('menuitem', { name: 'Delete' }))
    let dialog = await screen.findByRole('dialog')
    const del = within(dialog).getByRole('button', { name: 'Delete' })
    expect(del).toBeDisabled()
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'alice@x.test' } })
    fireEvent.click(del)
    await waitFor(() => expect(called(deleteSpy, '/users/u-alice')).toBe(true))

    dialog = await screen.findByRole('dialog', { name: /authored records/i })
    expect(dialog).toHaveTextContent('2 incidents, 1 case notes')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Disable instead' }))
    const disable = await screen.findByRole('dialog', { name: /disable alice/i })
    expect(within(disable).getByLabelText('Reason')).toBeInTheDocument()
  })

  it('runs a bulk force logout and lists skipped users with their codes', async () => {
    postSpy.mockImplementation(async (endpoint) => {
      if (endpoint !== '/users/bulk') return {}
      return {
        action: 'force_logout',
        bulk_request_id: 'b1',
        results: [
          { user_id: 'u-alice', status: 'ok' },
          { user_id: 'u-admin', status: 'skipped', code: 'self_action', message: 'You cannot do that to yourself' },
        ],
        summary: { ok: 1, skipped: 1, failed: 0 },
      }
    })
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('alice@x.test')
    fireEvent.click(within(rowOf('alice@x.test')).getByRole('checkbox', { name: 'Select row' }))
    fireEvent.click(within(rowOf('admin@x.test')).getByRole('checkbox', { name: 'Select row' }))
    expect(screen.getByText('2 selected')).toBeInTheDocument()

    const trigger = screen.getByRole('button', { name: /bulk actions/i })
    fireEvent.keyDown(trigger, { key: 'ArrowDown' })
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Force logout' }))
    const confirmDialog = await screen.findByRole('dialog')
    fireEvent.click(within(confirmDialog).getByRole('button', { name: 'Force logout' }))

    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/users/bulk', {
        action: 'force_logout',
        user_ids: ['u-alice', 'u-admin'],
      })
    )
    const result = await screen.findByRole('dialog', { name: /results/i })
    expect(within(result).getByTestId('bulk-summary')).toHaveTextContent('1 succeeded, 1 skipped, 0 failed')
    expect(within(result).getByText('admin@x.test')).toBeInTheDocument()
    expect(within(result).getByText(/self_action/)).toBeInTheDocument()
    expect(screen.queryByText('2 selected')).toBeNull()
  })

  it('bulk disable asks for a reason', async () => {
    postSpy.mockImplementation(async () => ({
      action: 'disable',
      bulk_request_id: 'b2',
      results: [{ user_id: 'u-alice', status: 'ok' }],
      summary: { ok: 1, skipped: 0, failed: 0 },
    }))
    setPermissions(ADMIN_PERMS)
    renderPage()
    await screen.findByText('alice@x.test')
    fireEvent.click(within(rowOf('alice@x.test')).getByRole('checkbox', { name: 'Select row' }))
    fireEvent.keyDown(screen.getByRole('button', { name: /bulk actions/i }), { key: 'ArrowDown' })
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Disable…' }))
    const dialog = await screen.findByRole('dialog')
    const apply = within(dialog).getByRole('button', { name: 'Apply to 1 user' })
    expect(apply).toBeDisabled()
    fireEvent.change(within(dialog).getByLabelText('Reason'), { target: { value: 'Contractor offboarding' } })
    fireEvent.click(apply)
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/users/bulk', {
        action: 'disable',
        reason: 'Contractor offboarding',
        user_ids: ['u-alice'],
      })
    )
  })
})
