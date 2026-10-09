import { afterEach, beforeEach, describe, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { clearCache } from '@/lib/query-cache'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import type { PermissionCatalog, Role } from '@/types'
import RolesPage from './page'

const p = (key: string, group: string, label: string, extra: Partial<PermissionCatalog['items'][number]> = {}) => ({
  key,
  group,
  label,
  description: `${label} description`,
  dangerous: false,
  privileged: false,
  api_key_grantable: true,
  platform_only: false,
  ...extra,
})

const catalog: PermissionCatalog = {
  groups: [
    { key: 'incidents', label: 'Incidents' },
    { key: 'users', label: 'Users' },
    { key: 'roles', label: 'Roles' },
  ],
  items: [
    p('incidents:read', 'incidents', 'View incidents'),
    p('incidents:purge', 'incidents', 'Permanently delete incidents', { dangerous: true, privileged: true }),
    p('users:read', 'users', 'View users'),
    p('users:manage', 'users', 'Manage users', { dangerous: true, privileged: true }),
    p('roles:manage', 'roles', 'Manage roles', { dangerous: true, privileged: true }),
  ],
}

const roles: Role[] = [
  { id: 'r-analyst', name: 'Analyst', description: 'Built-in', permissions: ['incidents:read'], is_system: true,
    organization_id: null, user_count: 3, editable: false },
  { id: 'r-hunters', name: 'Hunters', description: 'Custom', permissions: ['incidents:read'], is_system: false,
    organization_id: 'org-1', user_count: 1, editable: true },
]

let postSpy: jest.Mock<(endpoint: string, data?: unknown) => Promise<unknown>>

beforeEach(() => {
  clearCache()
  jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    if (endpoint === '/permissions') return catalog
    if (endpoint === '/roles') return { items: roles }
    throw new ApiError(404, 'not found')
  }) as unknown as typeof api.get)
  postSpy = jest.fn<(endpoint: string, data?: unknown) => Promise<unknown>>(async () => ({}))
  jest.spyOn(api, 'post').mockImplementation(postSpy as unknown as typeof api.post)
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'u@x', name: 'Deputy', roles: ['Deputy'],
        permissions: ['incidents:read', 'users:read', 'roles:manage'] },
      isAuthenticated: true,
    })
  })
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

async function renderPage() {
  render(
    <ConfirmDialogProvider>
      <RolesPage />
    </ConfirmDialogProvider>
  )
  await screen.findByText('Hunters')
}

function rowOf(name: string): HTMLElement {
  return screen.getAllByRole('row').find((r) => within(r).queryByText(name))!
}

async function openCreate() {
  fireEvent.click(screen.getByRole('button', { name: 'Create role' }))
  return screen.findByRole('dialog')
}

describe('Roles page', () => {
  it('renders the server catalog grouped, with flags', async () => {
    await renderPage()
    const dialog = await openCreate()
    await within(dialog).findByRole('region', { name: 'Incidents' })
    expect(within(dialog).getByRole('region', { name: 'Users' })).toBeInTheDocument()
    expect(within(dialog).getByRole('region', { name: 'Roles' })).toBeInTheDocument()
    const roleRow = within(within(dialog).getByRole('region', { name: 'Roles' })).getByText('Manage roles').closest('li')!
    expect(within(roleRow).getByText('Dangerous')).toBeInTheDocument()
  })

  it('disables permissions the caller does not hold', async () => {
    await renderPage()
    const dialog = await openCreate()
    await within(dialog).findByRole('region', { name: 'Users' })
    expect(within(dialog).getByRole('checkbox', { name: 'Manage users' })).toBeDisabled()
    expect(within(dialog).getByRole('checkbox', { name: 'Manage users' })).toHaveAttribute(
      'title',
      "You don't hold this permission"
    )
    expect(within(dialog).getByRole('checkbox', { name: 'View users' })).toBeEnabled()
  })

  it('offers Clone but not Edit/Delete on a system role', async () => {
    await renderPage()
    fireEvent.keyDown(rowOf('Analyst'), { key: '.' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByRole('menuitem', { name: 'Clone' })).toBeInTheDocument()
    expect(within(menu).queryByRole('menuitem', { name: 'Edit role' })).toBeNull()
    expect(within(menu).queryByRole('menuitem', { name: 'Delete role' })).toBeNull()
  })

  it('offers Edit and Delete on an editable custom role', async () => {
    await renderPage()
    fireEvent.keyDown(rowOf('Hunters'), { key: '.' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByRole('menuitem', { name: 'Edit role' })).toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'Delete role' })).toBeInTheDocument()
  })

  it('shows the server privilege_escalation message and the missing permissions', async () => {
    postSpy.mockImplementation(async () => {
      throw new ApiError(403, "You cannot grant permissions you don't hold", {
        code: 'privilege_escalation',
        details: { error: 'privilege_escalation', message: "You cannot grant permissions you don't hold", missing: ['users:manage'] },
      })
    })
    await renderPage()
    const dialog = await openCreate()
    await within(dialog).findByRole('region', { name: 'Users' })
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Readers' } })
    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'View users' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create role' }))

    const alert = await within(dialog).findByRole('alert')
    expect(alert).toHaveTextContent('Exceeds your permissions')
    expect(alert).toHaveTextContent("You cannot grant permissions you don't hold")
    expect(within(alert).getByRole('list', { name: 'Permissions involved' })).toHaveTextContent('Manage users')
    expect(postSpy).toHaveBeenCalledWith('/roles', { name: 'Readers', description: '', permissions: ['users:read'] })
  })

  it('requires typing the role name before granting a dangerous permission', async () => {
    await renderPage()
    const dialog = await openCreate()
    await within(dialog).findByRole('region', { name: 'Roles' })
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Role admins' } })
    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Manage roles' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create role' }))

    const confirmTitle = await screen.findByText('Grant dangerous permissions?')
    const confirmDialog = confirmTitle.closest('[role="dialog"]') as HTMLElement
    const grant = within(confirmDialog).getByRole('button', { name: 'Grant' })
    expect(grant).toBeDisabled()
    fireEvent.change(within(confirmDialog).getByRole('textbox'), { target: { value: 'Role admins' } })
    expect(grant).toBeEnabled()
    fireEvent.click(grant)
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/roles', { name: 'Role admins', description: '', permissions: ['roles:manage'] })
    )
  })
})
