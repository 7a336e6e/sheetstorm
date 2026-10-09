import type { ComponentType } from 'react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { clearCache } from '@/lib/query-cache'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import type { Role, ServiceAccount } from '@/types'
import { changes } from './ServiceAccountDialog'
import { page, serviceAccount } from './test-fixtures'

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/dashboard/admin/settings',
  useRouter: () => ({ push: () => {}, replace: () => {} }),
}))

let ServiceAccountsPanel: ComponentType<{ onCreateKey?: (a: ServiceAccount) => void }>
beforeAll(async () => {
  ;({ ServiceAccountsPanel } = await import('./ServiceAccountsPanel'))
})

const role = (id: string, name: string, permissions: string[]): Role => ({
  id,
  name,
  description: '',
  permissions,
  is_system: true,
  organization_id: null,
})
const ROLES = [
  role('r-analyst', 'Analyst', ['incidents:read', 'timeline:read']),
  role('r-admin', 'Administrator', ['incidents:read', 'users:manage', 'roles:manage']),
]

type Fn = (endpoint: string, data?: unknown) => Promise<unknown>
let accounts: ServiceAccount[]
let postSpy: jest.Mock<Fn>
let patchSpy: jest.Mock<Fn>
const onCreateKey = jest.fn()

beforeEach(() => {
  clearCache()
  accounts = [serviceAccount()]
  jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    const path = endpoint.split('?')[0]
    if (path === '/service-accounts') return page(accounts)
    if (path === '/roles') return { items: ROLES }
    if (path === '/permissions') return { groups: [], items: [] }
    throw new ApiError(404, `unexpected GET ${endpoint}`)
  }) as unknown as typeof api.get)
  postSpy = jest.fn<Fn>(async () => serviceAccount({ id: 'sa-2', name: 'new-bot' }))
  patchSpy = jest.fn<Fn>(async () => serviceAccount())
  jest.spyOn(api, 'post').mockImplementation(postSpy as unknown as typeof api.post)
  jest.spyOn(api, 'patch').mockImplementation(patchSpy as unknown as typeof api.patch)
  act(() => {
    useAuthStore.setState({
      user: {
        id: 'u-admin',
        email: 'a@x',
        name: 'Admin',
        roles: [],
        // Holds everything in "Analyst" but not users:manage / roles:manage.
        permissions: ['api_keys:manage', 'incidents:read', 'timeline:read'],
      },
      isAuthenticated: true,
    })
  })
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  onCreateKey.mockClear()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

async function renderPanel() {
  render(
    <ConfirmDialogProvider>
      <ServiceAccountsPanel onCreateKey={onCreateKey} />
    </ConfirmDialogProvider>
  )
  await screen.findByText(accounts[0].name)
}

async function openMenu(name: string) {
  fireEvent.keyDown(screen.getByText(name).closest('tr') as HTMLElement, { key: '.' })
  return screen.findByRole('menu')
}

describe('service accounts', () => {
  it('lists accounts with roles, key counts and status', async () => {
    await renderPanel()
    const row = screen.getByText('ingest-bot').closest('tr') as HTMLElement
    expect(within(row).getByText('Analyst')).toBeInTheDocument()
    expect(within(row).getByText('2')).toBeInTheDocument()
    expect(within(row).getByText('Active')).toBeInTheDocument()
  })

  it('creates an account with a role under the ceiling; roles above it cannot be picked', async () => {
    await renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Create service account/ }))
    const dialog = await screen.findByRole('dialog')
    const analyst = await within(dialog).findByRole('checkbox', { name: 'Analyst' })
    const admin = within(dialog).getByRole('checkbox', { name: 'Administrator' })
    expect(analyst).toBeEnabled()
    expect(admin).toBeDisabled()
    expect(within(dialog).getByText(/exceeds your permissions/)).toBeInTheDocument()

    const submit = within(dialog).getByRole('button', { name: 'Create service account' })
    expect(submit).toBeDisabled()
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'new-bot' } })
    fireEvent.click(analyst)
    fireEvent.click(submit)

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith('/service-accounts', { name: 'new-bot', role_ids: ['r-analyst'] }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('shows the guard refusal with the missing permissions', async () => {
    postSpy.mockRejectedValueOnce(
      new ApiError(403, "You can't grant permissions you don't hold.", {
        code: 'privilege_escalation',
        details: { missing: ['users:manage'] },
      })
    )
    await renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Create service account/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'bot' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create service account' }))
    const alert = await within(dialog).findByRole('alert')
    expect(alert).toHaveTextContent('Exceeds your permissions')
    expect(alert).toHaveTextContent('users:manage')
  })

  it('edits only what changed (an untouched role set is not re-sent)', async () => {
    await renderPanel()
    const menu = await openMenu('ingest-bot')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Edit' }))
    const dialog = await screen.findByRole('dialog', { name: /Edit ingest-bot/ })
    const name = within(dialog).getByLabelText('Name')
    expect(name).toHaveValue('ingest-bot')
    expect(await within(dialog).findByRole('checkbox', { name: 'Analyst' })).toBeChecked()
    fireEvent.change(name, { target: { value: 'ingest-bot-2' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith('/service-accounts/sa-1', { name: 'ingest-bot-2' }))
  })

  it('disables after a confirmation that states the keys are revoked', async () => {
    await renderPanel()
    const menu = await openMenu('ingest-bot')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Disable' }))
    const dialog = await screen.findByRole('dialog', { name: 'Disable ingest-bot?' })
    expect(dialog).toHaveTextContent('Every API key of this service account is revoked now (2 active)')
    expect(patchSpy).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Disable' }))
    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith('/service-accounts/sa-1', { is_active: false }))
  })

  it('re-enables a disabled account without a confirmation and offers no key creation for it', async () => {
    accounts = [serviceAccount({ is_active: false, deactivated_at: '2026-10-01T00:00:00+00:00' })]
    await renderPanel()
    const menu = await openMenu('ingest-bot')
    expect(within(menu).queryByRole('menuitem', { name: 'Create key' })).toBeNull()
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Enable' }))
    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith('/service-accounts/sa-1', { is_active: true }))
  })

  it('starts a key for the account', async () => {
    await renderPanel()
    const menu = await openMenu('ingest-bot')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Create key' }))
    expect(onCreateKey).toHaveBeenCalledWith(expect.objectContaining({ id: 'sa-1' }))
  })
})

describe('changes()', () => {
  const sa = serviceAccount({ roles: [{ id: 'b', name: 'B' }, { id: 'a', name: 'A' }] })
  it('is empty when nothing changed, regardless of order', () => {
    expect(changes(sa, sa.name, ['a', 'b'])).toEqual({})
  })
  it('includes roles only when the set differs', () => {
    expect(changes(sa, 'x', ['a'])).toEqual({ name: 'x', role_ids: ['a'] })
  })
})
