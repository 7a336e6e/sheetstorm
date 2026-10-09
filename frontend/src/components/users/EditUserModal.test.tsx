import { afterEach, beforeEach, describe, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { clearCache } from '@/lib/query-cache'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import type { Role, User } from '@/types'
import { EditUserModal } from './EditUserModal'
import { AddUserModal } from './AddUserModal'

const deputyPerms = ['users:read', 'users:update', 'users:manage', 'roles:manage', 'incidents:read']

const roles: Role[] = [
  { id: 'r-admin', name: 'Administrator', description: '', is_system: true,
    permissions: ['users:read', 'users:update', 'users:manage', 'roles:manage', 'incidents:read', 'organizations:manage'] },
  { id: 'r-viewer', name: 'Viewer', description: '', is_system: true, permissions: ['incidents:read'] },
]

const target: User = {
  id: 'u-target', email: 't@x', name: 'Target', roles: ['Viewer'], is_active: true, created_at: '2026-01-01T00:00:00Z',
}

let targetPermissions: string[] = ['incidents:read']
let putSpy: jest.Mock<(endpoint: string, data?: unknown) => Promise<unknown>>

beforeEach(() => {
  clearCache()
  targetPermissions = ['incidents:read']
  jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    if (endpoint === '/roles') return { items: roles }
    if (endpoint === '/teams') return { items: [] }
    if (endpoint === '/permissions') return { groups: [], items: [] }
    if (endpoint.endsWith('/roles')) return { roles: [{ id: 'r-viewer', name: 'Viewer' }] }
    if (endpoint.startsWith('/users/')) return { ...target, permissions: targetPermissions }
    throw new ApiError(404, 'not found')
  }) as unknown as typeof api.get)
  putSpy = jest.fn<(endpoint: string, data?: unknown) => Promise<unknown>>(async () => ({}))
  jest.spyOn(api, 'put').mockImplementation(putSpy as unknown as typeof api.put)
  act(() => {
    useAuthStore.setState({
      user: { id: 'u-deputy', email: 'd@x', name: 'Deputy', roles: ['Deputy'], permissions: deputyPerms },
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

function renderEdit(user: User) {
  render(
    <ConfirmDialogProvider>
      <EditUserModal user={user} open onOpenChange={() => {}} onSuccess={() => {}} />
    </ConfirmDialogProvider>
  )
}

describe('EditUserModal', () => {
  it('disables roles that exceed your permissions', async () => {
    renderEdit(target)
    const trigger = await screen.findByRole('combobox', { name: 'Add role' })
    fireEvent.keyDown(trigger, { key: 'ArrowDown' })
    const admin = await screen.findByRole('option', { name: /Administrator \(exceeds your permissions\)/ })
    expect(admin).toHaveAttribute('aria-disabled', 'true')
  })

  it('hides the Active switch and password reset on your own account', async () => {
    renderEdit({ ...target, id: 'u-deputy', name: 'Deputy' })
    await screen.findByText(/Your own account/)
    expect(screen.queryByRole('switch')).toBeNull()
    expect(screen.queryByLabelText(/Reset Password/)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }))
    await waitFor(() => expect(putSpy).toHaveBeenCalled())
    const body = putSpy.mock.calls[0][1] as Record<string, unknown>
    expect(body).not.toHaveProperty('is_active')
    expect(body).not.toHaveProperty('password')
  })

  it('locks the form for a user holding permissions you lack', async () => {
    targetPermissions = [...deputyPerms, 'organizations:manage']
    renderEdit(target)
    expect(await screen.findByText("This user holds permissions you don't have")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save Changes' })).toBeDisabled()
  })

  it('shows the server message for last_admin', async () => {
    putSpy.mockImplementation(async () => {
      throw new ApiError(409, 'This change would leave the organization without an administrator', {
        code: 'last_admin',
        details: { error: 'last_admin', message: 'This change would leave the organization without an administrator' },
      })
    })
    renderEdit(target)
    await screen.findByRole('switch')
    fireEvent.click(screen.getByRole('switch'))
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Last administrator')
    expect(alert).toHaveTextContent('This change would leave the organization without an administrator')
    expect(putSpy.mock.calls[0][1]).toMatchObject({ is_active: false })
  })
})

describe('AddUserModal', () => {
  it('does not send roles without roles:manage (server assigns Viewer)', async () => {
    const postSpy = jest.spyOn(api, 'post').mockResolvedValue({ id: 'new' } as never)
    act(() => {
      useAuthStore.setState({
        user: { id: 'u-hr', email: 'hr@x', name: 'HR', roles: [], permissions: ['users:create', 'users:read'] },
      })
    })
    render(<AddUserModal open onOpenChange={() => {}} onSuccess={() => {}} />)
    expect(await screen.findByText(/New users get the Viewer role/)).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Add role' })).toBeNull()

    fireEvent.change(screen.getByLabelText('Full Name'), { target: { value: 'New User' } })
    fireEvent.change(screen.getByLabelText('Email Address'), { target: { value: 'new@x.test' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Str0ng!Passw0rd' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create User' }))

    await waitFor(() => expect(postSpy).toHaveBeenCalled())
    expect(postSpy.mock.calls[0][1]).not.toHaveProperty('roles')
  })

  it('disables roles above your ceiling', async () => {
    render(<AddUserModal open onOpenChange={() => {}} onSuccess={() => {}} />)
    const trigger = await screen.findByRole('combobox', { name: 'Add role' })
    fireEvent.keyDown(trigger, { key: 'ArrowDown' })
    expect(await screen.findByRole('option', { name: /Administrator \(exceeds your permissions\)/ })).toHaveAttribute(
      'aria-disabled',
      'true'
    )
    expect(screen.getByRole('option', { name: 'Viewer' })).not.toHaveAttribute('aria-disabled', 'true')
  })
})
