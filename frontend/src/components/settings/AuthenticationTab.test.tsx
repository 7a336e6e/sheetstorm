import { afterEach, beforeEach, describe, it, jest } from '@jest/globals'
import { act, cleanup, render, screen } from '@testing-library/react'
import api from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { AuthenticationTab } from './AuthenticationTab'

const types = [
  { id: 'oauth_google', name: 'Google OAuth', description: '', category: 'auth', config_fields: [], credential_fields: [], login_supported: false },
  { id: 'oauth_github', name: 'GitHub OAuth', description: '', category: 'auth', config_fields: [], credential_fields: [], login_supported: true },
  { id: 'oauth_azure', name: 'Azure AD / Entra ID', description: '', category: 'auth', config_fields: [], credential_fields: [], login_supported: false },
]

beforeEach(() => {
  jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    if (endpoint === '/integrations/types') return { types }
    return { items: [{ id: 'i-google', type: 'oauth_google', name: 'Old Google SSO', is_enabled: true, config: {} }] }
  }) as unknown as typeof api.get)
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'u@x', name: 'U', roles: [],
        permissions: ['integrations:read', 'integrations:create', 'integrations:update', 'integrations:delete'] },
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

describe('AuthenticationTab', () => {
  it('only offers providers with a login flow and marks legacy rows as unused', async () => {
    await act(async () => {
      render(<AuthenticationTab />)
    })
    expect(await screen.findByText('Login not implemented — not used')).toBeInTheDocument()
    // Legacy Google row: delete only.
    expect(screen.queryByRole('button', { name: 'Configure' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Delete Old Google SSO' })).toBeInTheDocument()
    // Only GitHub can be added.
    expect(screen.getByText('GitHub OAuth')).toBeInTheDocument()
    expect(screen.queryByText('Azure AD / Entra ID')).toBeNull()
  })

  it('hides mutations without the integration permissions', async () => {
    act(() => {
      useAuthStore.setState({
        user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions: ['integrations:read'] },
      })
    })
    await act(async () => {
      render(<AuthenticationTab />)
    })
    await screen.findByText('Old Google SSO')
    expect(screen.queryByRole('button', { name: /add oauth provider/i })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Delete Old Google SSO' })).toBeNull()
    expect(screen.queryByText('GitHub OAuth')).toBeNull()
  })
})
