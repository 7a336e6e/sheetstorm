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

describe('SocketProvider session:revoked (W2-LIFE-UI)', () => {
  it('logs out and lands on /login with a notice', async () => {
    const { sessionNavigation } = await import('@/components/users/session-revoked')
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

    await act(async () => {
      mockHandlers.get('session:revoked')!({ reason: 'disabled' })
    })
    expect(logout).toHaveBeenCalledTimes(1)
    expect(assign).toHaveBeenCalledWith('/login?reason=session_revoked')
    assign.mockRestore()
  })
})
