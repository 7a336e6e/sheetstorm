import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import '@testing-library/jest-dom/jest-globals'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import api, { ApiError } from '@/lib/api'
import { clearCache } from '@/lib/query-cache'
import { useAuthStore } from '@/lib/store'
import type { Role } from '@/types'
import { InviteUserModal } from './InviteUserModal'
import { UserStatusBadges } from './UserStatusBadges'

const managerPerms = ['users:read', 'users:manage', 'roles:manage', 'incidents:read']
const roles: Role[] = [
  {
    id: 'r-admin',
    name: 'Administrator',
    description: '',
    is_system: true,
    permissions: [...managerPerms, 'organizations:manage'],
  },
  { id: 'r-viewer', name: 'Viewer', description: '', is_system: true, permissions: ['incidents:read'] },
]

type PostFn = (endpoint: string, data?: unknown) => Promise<unknown>
let postSpy: jest.Mock<PostFn>

function setPermissions(permissions: string[]) {
  act(() => {
    useAuthStore.setState({ user: { id: 'me', email: 'me@x', name: 'Me', roles: [], permissions } })
  })
}

function Harness() {
  const [open, setOpen] = useState(true)
  return (
    <>
      <button onClick={() => setOpen(true)}>reopen</button>
      <InviteUserModal open={open} onOpenChange={setOpen} onSuccess={() => {}} />
    </>
  )
}

beforeEach(() => {
  clearCache()
  jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    if (endpoint === '/roles') return { items: roles }
    if (endpoint === '/teams')
      return { items: [{ id: 't1', name: 'Blue Team', is_default: false, member_count: 0, created_at: '' }] }
    if (endpoint === '/permissions') return { groups: [], items: [] }
    throw new ApiError(404, 'not found')
  }) as unknown as typeof api.get)
  postSpy = jest.fn<PostFn>(async () => ({
    id: 'inv1',
    invite: { email: 'new@x.test' },
    token: 'secret-token',
    accept_path: '/auth/invite#token=secret-token',
    superseded_invite_id: null,
  }))
  jest.spyOn(api, 'post').mockImplementation(postSpy as unknown as typeof api.post)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null })
  })
})

describe('InviteUserModal', () => {
  it('shows the link once (origin + accept_path) and forgets it after close', async () => {
    setPermissions(managerPerms)
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('Email Address'), { target: { value: 'new@x.test' } })
    fireEvent.click(await screen.findByLabelText('Viewer'))
    fireEvent.click(screen.getByLabelText('Blue Team'))
    fireEvent.click(screen.getByRole('button', { name: 'Create invite' }))

    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/users/invites', {
        email: 'new@x.test',
        expires_in_days: 7,
        role_ids: ['r-viewer'],
        team_ids: ['t1'],
      })
    )
    const link = `${window.location.origin}/auth/invite#token=secret-token`
    expect(await screen.findByDisplayValue(link)).toBeInTheDocument()
    expect(screen.getByText('Shown once. Anyone with this link can join as new@x.test.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    fireEvent.click(screen.getByText('reopen'))
    expect(await screen.findByRole('button', { name: 'Create invite' })).toBeInTheDocument()
    expect(screen.queryByDisplayValue(link)).toBeNull()
  })

  it('prefers the server accept_url when FRONTEND_URL is configured', async () => {
    postSpy.mockImplementation(async () => ({
      id: 'inv1',
      invite: { email: 'new@x.test' },
      token: 't',
      accept_path: '/auth/invite#token=t',
      accept_url: 'https://ir.example.org/auth/invite#token=t',
      superseded_invite_id: 'old',
    }))
    setPermissions(managerPerms)
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('Email Address'), { target: { value: 'new@x.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create invite' }))
    expect(await screen.findByDisplayValue('https://ir.example.org/auth/invite#token=t')).toBeInTheDocument()
    expect(screen.getByText(/previous pending invite for this email was revoked/)).toBeInTheDocument()
  })

  it('hides roles without roles:manage and never sends role_ids', async () => {
    setPermissions(['users:read', 'users:manage'])
    render(<Harness />)
    expect(screen.getByText(/The invitee gets the Viewer role/)).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Roles' })).toBeNull()
    fireEvent.change(screen.getByLabelText('Email Address'), { target: { value: 'new@x.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create invite' }))
    await waitFor(() => expect(postSpy).toHaveBeenCalled())
    expect(postSpy.mock.calls[0][1]).not.toHaveProperty('role_ids')
  })

  it('disables roles above your permissions', async () => {
    setPermissions(managerPerms)
    render(<Harness />)
    const admin = await screen.findByRole('checkbox', { name: /Administrator \(exceeds your permissions\)/ })
    expect(admin).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Viewer' })).toBeEnabled()
  })

  it('shows lifecycle refusals inline', async () => {
    postSpy.mockImplementation(async () => {
      throw new ApiError(409, 'A user with this email is already a member', { code: 'already_member' })
    })
    setPermissions(managerPerms)
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('Email Address'), { target: { value: 'dup@x.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create invite' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Already a member')
  })
})

describe('UserStatusBadges', () => {
  it('renders one badge per state', () => {
    render(
      <UserStatusBadges
        user={{
          id: 'u',
          email: 'u@x',
          name: 'U',
          roles: [],
          created_at: '',
          is_active: false,
          is_locked: true,
          must_change_password: true,
          mfa_enabled: true,
        }}
      />
    )
    for (const label of ['Disabled', 'Locked', 'Must change password', 'MFA']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.queryByText('Active')).toBeNull()
  })
})
