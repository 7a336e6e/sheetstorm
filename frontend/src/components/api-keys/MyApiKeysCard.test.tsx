import type { ComponentType } from 'react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, render, screen } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { clearCache } from '@/lib/query-cache'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import { MCP_DOCS_URL } from '@/lib/endpoints/api-keys'
import { apiKey, page } from './test-fixtures'

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/dashboard/profile',
  useRouter: () => ({ push: () => {}, replace: () => {} }),
}))

let MyApiKeysCard: ComponentType
let ProfilePage: ComponentType
beforeAll(async () => {
  ;({ MyApiKeysCard } = await import('./MyApiKeysCard'))
  ProfilePage = (await import('@/app/dashboard/profile/page')).default
})

function setPermissions(permissions: string[]) {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u-me', email: 'me@x', name: 'Me', roles: ['Analyst'], permissions },
      isAuthenticated: true,
    })
  })
}

let getSpy: jest.Mock<(endpoint: string) => Promise<unknown>>
beforeEach(() => {
  clearCache()
  getSpy = jest.fn(async (endpoint: string) => {
    const path = endpoint.split('?')[0]
    if (path === '/api-keys') return page([apiKey()])
    if (path === '/auth/me') {
      return { id: 'u-me', email: 'me@x', name: 'Me', roles: ['Analyst'], permissions: [], mfa_enabled: false }
    }
    throw new ApiError(404, `unexpected GET ${endpoint}`)
  })
  jest.spyOn(api, 'get').mockImplementation(getSpy as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

const settle = () => act(async () => {})

describe('My API keys card', () => {
  it('lists my keys and links the MCP setup docs for api_keys:own', async () => {
    setPermissions(['api_keys:own'])
    await act(async () => {
      render(
        <ConfirmDialogProvider>
          <MyApiKeysCard />
        </ConfirmDialogProvider>
      )
    })
    expect(await screen.findByText('My API keys')).toBeInTheDocument()
    expect(await screen.findByText('Local MCP')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /MCP setup with SHEETSTORM_API_KEY/ })
    expect(link).toHaveAttribute('href', MCP_DOCS_URL)
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
    expect(getSpy.mock.calls.some(([e]) => e.includes('mine=true'))).toBe(true)
  })

  it('renders nothing and requests nothing without api_keys:own (api_keys:manage is not enough)', async () => {
    setPermissions(['api_keys:manage'])
    await act(async () => {
      render(<MyApiKeysCard />)
    })
    await settle()
    expect(screen.queryByText('My API keys')).toBeNull()
    expect(getSpy).not.toHaveBeenCalled()
  })
})

describe('profile page', () => {
  it('shows the card to api_keys:own holders', async () => {
    setPermissions(['api_keys:own'])
    await act(async () => {
      render(
        <ConfirmDialogProvider>
          <ProfilePage />
        </ConfirmDialogProvider>
      )
    })
    expect(await screen.findByText('My API keys')).toBeInTheDocument()
    expect(await screen.findByText('Local MCP')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Profile' })).toBeInTheDocument()
  })

  it('omits the card for users without api_keys:own', async () => {
    setPermissions([])
    await act(async () => {
      render(
        <ConfirmDialogProvider>
          <ProfilePage />
        </ConfirmDialogProvider>
      )
    })
    expect(await screen.findByRole('heading', { name: 'Profile' })).toBeInTheDocument()
    expect(screen.queryByText('My API keys')).toBeNull()
    expect(getSpy.mock.calls.some(([e]) => e.startsWith('/api-keys'))).toBe(false)
  })
})
