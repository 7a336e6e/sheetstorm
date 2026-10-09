import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import '@testing-library/jest-dom/jest-globals'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { useAuthStore, type User } from '@/lib/store'

const mockReplace = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
}))

let ChangePasswordPage: typeof import('./page').default
beforeAll(async () => {
  ;({ default: ChangePasswordPage } = await import('./page'))
})

type PostFn = (endpoint: string, data?: unknown) => Promise<unknown>
let postSpy: jest.Mock<PostFn>
const refreshUser = jest.fn(async () => {})

function signIn(extra: Record<string, unknown> = {}) {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions: [], ...extra } as User,
      isAuthenticated: true,
      isLoading: false,
      refreshUser,
    })
  })
}

function fill(current: string, next: string) {
  fireEvent.change(screen.getByLabelText(/temporary password|current password/i), { target: { value: current } })
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: next } })
  fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: next } })
}

beforeEach(() => {
  mockReplace.mockClear()
  refreshUser.mockClear()
  postSpy = jest.fn<PostFn>(async () => ({ message: 'Password changed successfully' }))
  jest.spyOn(api, 'post').mockImplementation(postSpy as unknown as typeof api.post)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: true })
  })
})

describe('Change password page', () => {
  it('forced change: posts, refreshes the user and continues to the dashboard', async () => {
    signIn({ must_change_password: true })
    render(<ChangePasswordPage />)
    expect(screen.getByText('Set a new password')).toBeInTheDocument()
    fill('Temp-Pass-123!', 'Str0ng!Passw0rd')
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }))
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/auth/change-password', {
        current_password: 'Temp-Pass-123!',
        new_password: 'Str0ng!Passw0rd',
      })
    )
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/dashboard'))
    expect(refreshUser).toHaveBeenCalled()
  })

  it('refuses reusing the current password and shows a wrong current password', async () => {
    signIn()
    render(<ChangePasswordPage />)
    fill('Str0ng!Passw0rd', 'Str0ng!Passw0rd')
    expect(screen.getByRole('button', { name: 'Change password' })).toBeDisabled()

    postSpy.mockImplementation(async () => {
      throw new ApiError(401, 'Current password is incorrect', { code: 'unauthorized' })
    })
    fill('wrong-one', 'Str0ng!Passw0rd')
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Current password is incorrect')
    expect(mockReplace).not.toHaveBeenCalled()
  })

  it('sends signed-out visitors to /login', () => {
    act(() => {
      useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false })
    })
    render(<ChangePasswordPage />)
    expect(mockReplace).toHaveBeenCalledWith('/login')
  })
})
