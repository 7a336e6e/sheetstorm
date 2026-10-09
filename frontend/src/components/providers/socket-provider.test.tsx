import { afterEach, beforeAll, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, render } from '@testing-library/react'

type Handler = (...args: unknown[]) => void

// Minimal socket.io client stand-in.
const mockHandlers = new Map<string, Handler>()
const mockSocket = {
  on: jest.fn((event: string, fn: Handler) => {
    mockHandlers.set(event, fn)
  }),
  connect: jest.fn(),
  disconnect: jest.fn(),
}
jest.mock('socket.io-client', () => ({ io: () => mockSocket }))
const mockToast = jest.fn()
jest.mock('@/components/ui/use-toast', () => ({ toast: (...args: unknown[]) => mockToast(...args) }))

let SocketProvider: typeof import('./socket-provider').SocketProvider
let useAuthStore: typeof import('@/lib/store').useAuthStore

beforeAll(async () => {
  ;({ SocketProvider } = await import('./socket-provider'))
  ;({ useAuthStore } = await import('@/lib/store'))
})

afterEach(() => {
  cleanup()
  mockHandlers.clear()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

describe('SocketProvider', () => {
  it('refreshes /auth/me on permissions_changed and reconnects after the server drops the socket', async () => {
    const refreshUser = jest.fn(async () => {})
    act(() => {
      useAuthStore.setState({
        user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions: [] },
        isAuthenticated: true,
        refreshUser,
      })
    })
    render(
      <SocketProvider>
        <div />
      </SocketProvider>
    )
    expect(mockHandlers.has('permissions_changed')).toBe(true)

    act(() => mockHandlers.get('permissions_changed')!({}))
    expect(refreshUser).toHaveBeenCalledTimes(1)

    act(() => mockHandlers.get('disconnect')!('io server disconnect'))
    expect(mockSocket.connect).toHaveBeenCalledTimes(1)

    // A later server-side disconnect without a permission change stays final.
    act(() => mockHandlers.get('disconnect')!('io server disconnect'))
    expect(mockSocket.connect).toHaveBeenCalledTimes(1)
  })

})

// One handler for session:revoked (W2-RT-FE + W2-LIFE-UI): per-reason copy,
// logout, no reconnect, redirect to /login?reason=session_revoked.
describe('SocketProvider session:revoked', () => {
  it('shows the per-reason copy, logs out, does not reconnect and lands on /login with a notice', async () => {
    const { sessionNavigation, readSessionRevokedReason } = await import('@/components/users/session-revoked')
    const assign = jest.spyOn(sessionNavigation, 'assign').mockImplementation(() => {})
    const logout = jest.fn(async () => {})
    act(() => {
      useAuthStore.setState({
        user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions: [] },
        isAuthenticated: true,
        logout,
      })
    })
    render(
      <SocketProvider>
        <div />
      </SocketProvider>
    )
    expect(mockHandlers.has('session:revoked')).toBe(true)
    // permissions_changed handling is untouched.
    expect(mockHandlers.has('permissions_changed')).toBe(true)

    // A pending permissions_changed reconnect is cancelled by the revocation.
    act(() => mockHandlers.get('permissions_changed')!({}))
    await act(async () => {
      mockHandlers.get('session:revoked')!({ reason: 'force_logout' })
    })
    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({ description: 'An administrator signed you out.' })
    )
    expect(logout).toHaveBeenCalledTimes(1)
    expect(assign).toHaveBeenCalledWith('/login?reason=session_revoked')
    expect(readSessionRevokedReason()).toBe('force_logout')

    const connectsBefore = mockSocket.connect.mock.calls.length
    act(() => mockHandlers.get('disconnect')!('io server disconnect'))
    expect(mockSocket.connect.mock.calls.length).toBe(connectsBefore)
    assign.mockRestore()
  })

  it('falls back to generic copy for an unknown reason', async () => {
    const { sessionNavigation, readSessionRevokedReason } = await import('@/components/users/session-revoked')
    const assign = jest.spyOn(sessionNavigation, 'assign').mockImplementation(() => {})
    const logout = jest.fn(async () => {})
    act(() => {
      useAuthStore.setState({
        user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions: [] },
        isAuthenticated: true,
        logout,
      })
    })
    render(
      <SocketProvider>
        <div />
      </SocketProvider>
    )
    await act(async () => {
      mockHandlers.get('session:revoked')!({ reason: 'something-else' })
    })
    expect(mockToast).toHaveBeenLastCalledWith(
      expect.objectContaining({ description: 'Your session was ended. Sign in again.' })
    )
    expect(logout).toHaveBeenCalledTimes(1)
    expect(assign).toHaveBeenCalledWith('/login?reason=session_revoked')
    expect(readSessionRevokedReason()).toBeNull()
    assign.mockRestore()
  })
})
