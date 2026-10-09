// Example of a zustand store test with the API client mocked out.
// Pattern: mock the module boundary (`./api`, `./supabase`), drive the store
// through its public actions, and reset state between tests.
import api from './api'
import { useAuthStore, type User } from './store'

jest.mock('./api', () => {
  const client = {
    get: jest.fn(),
    post: jest.fn(),
    onUnauthorized: jest.fn(),
  }
  return { __esModule: true, default: client, api: client }
})

// No Supabase in unit tests: the store must fall back to local auth only.
jest.mock('./supabase', () => ({ __esModule: true, getSupabase: () => null, supabase: {} }))

const mockedApi = api as unknown as { get: jest.Mock; post: jest.Mock; onUnauthorized: jest.Mock }

// Captured once at import time, before clearMocks wipes the call history.
const unauthorizedHandler = mockedApi.onUnauthorized.mock.calls[0]?.[0] as (() => void) | undefined

const analyst: User = {
  id: 'u-1',
  email: 'analyst@example.test',
  name: 'Analyst',
  roles: ['Analyst'],
  permissions: ['incidents:read', 'timeline:create'],
}

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: true })
})

describe('useAuthStore', () => {
  it('answers permission and role checks from the current user', () => {
    useAuthStore.setState({ user: analyst, isAuthenticated: true })
    const { hasPermission, hasRole } = useAuthStore.getState()

    expect(hasPermission('incidents:read')).toBe(true)
    expect(hasPermission('users:manage')).toBe(false)
    expect(hasRole('Analyst')).toBe(true)
    expect(hasRole('Administrator')).toBe(false)
  })

  it('denies everything when logged out', () => {
    const { hasPermission, hasRole } = useAuthStore.getState()
    expect(hasPermission('incidents:read')).toBe(false)
    expect(hasRole('Analyst')).toBe(false)
  })

  it('stores the user returned by a successful local login', async () => {
    mockedApi.post.mockResolvedValueOnce({ user: analyst })

    await useAuthStore.getState().login('analyst@example.test', 'pw')

    expect(mockedApi.post).toHaveBeenCalledWith('/auth/login', {
      email: 'analyst@example.test',
      password: 'pw',
      mfa_code: undefined,
    })
    expect(useAuthStore.getState()).toMatchObject({ user: analyst, isAuthenticated: true, isLoading: false })
  })

  it('surfaces a 401 when Supabase is not configured and stays logged out', async () => {
    mockedApi.post.mockRejectedValueOnce(Object.assign(new Error('Invalid credentials'), { status: 401 }))

    await expect(useAuthStore.getState().login('analyst@example.test', 'bad')).rejects.toThrow('Invalid credentials')
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })

  it('drops the cached user when the API client reports the session is gone', () => {
    expect(unauthorizedHandler).toBeInstanceOf(Function)
    useAuthStore.setState({ user: analyst, isAuthenticated: true })

    unauthorizedHandler!()

    expect(useAuthStore.getState()).toMatchObject({ user: null, isAuthenticated: false, isLoading: false })
  })
})
