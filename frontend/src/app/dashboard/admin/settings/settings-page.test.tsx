import { afterEach, beforeAll, beforeEach, describe, it, jest } from '@jest/globals'
import { act, cleanup, render, screen } from '@testing-library/react'

let mockSearch = ''
jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(mockSearch),
  usePathname: () => '/dashboard/admin/settings',
  useRouter: () => ({ push: () => {}, replace: () => {} }),
}))

type PageMod = typeof import('./page')
let SettingsPage: PageMod['default']
let useAuthStore: typeof import('@/lib/store').useAuthStore
let api: typeof import('@/lib/api').default

beforeAll(async () => {
  ;({ default: SettingsPage } = await import('./page'))
  ;({ useAuthStore } = await import('@/lib/store'))
  ;({ default: api } = await import('@/lib/api'))
})

const patterns = {
  patterns: [
    { technique: 'T1059', tactic: 'execution', name: 'Command and Scripting Interpreter', keywords: ['powershell'], regex: [], weight: 0.8 },
  ],
}

function signIn(permissions: string[]) {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions },
      isAuthenticated: true,
    })
  })
}

beforeEach(() => {
  jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    if (endpoint.startsWith('/mitre/patterns')) return patterns
    return { items: [], types: [] }
  }) as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

const tabNames = () => screen.getAllByRole('tab').map((t) => t.textContent)

describe('Settings page', () => {
  it('lists only the tabs the permissions allow', async () => {
    mockSearch = ''
    signIn(['incidents:read', 'admin:manage'])
    await act(async () => {
      render(<SettingsPage />)
    })
    expect(tabNames()).toEqual(['MITRE Patterns'])
  })

  it('shows MITRE patterns read-only without admin:manage', async () => {
    mockSearch = 'tab=mitre-patterns'
    signIn(['incidents:read', 'integrations:read'])
    await act(async () => {
      render(<SettingsPage />)
    })
    expect(await screen.findByText('T1059')).toBeInTheDocument()
    expect(screen.getByTestId('mitre-read-only')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add pattern/i })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Delete T1059' })).toBeNull()
  })

  it('lets admin:manage holders edit MITRE patterns', async () => {
    mockSearch = 'tab=mitre-patterns'
    signIn(['incidents:read', 'admin:manage'])
    await act(async () => {
      render(<SettingsPage />)
    })
    expect(await screen.findByText('T1059')).toBeInTheDocument()
    expect(screen.queryByTestId('mitre-read-only')).toBeNull()
    expect(screen.getByRole('button', { name: /add pattern/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete T1059' })).toBeInTheDocument()
  })

  it('falls back to the first visible tab when the requested one is hidden', async () => {
    mockSearch = 'tab=general'
    signIn(['incidents:read', 'integrations:read'])
    await act(async () => {
      render(<SettingsPage />)
    })
    expect(tabNames()[0]).toBe('Integrations')
    expect(screen.getByRole('tab', { name: 'Integrations' })).toHaveAttribute('aria-selected', 'true')
  })
})
