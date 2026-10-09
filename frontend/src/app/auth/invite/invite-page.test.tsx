import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import '@testing-library/jest-dom/jest-globals'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { useAuthStore } from '@/lib/store'

const mockReplace = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
}))

let InvitePage: typeof import('./page').default
beforeAll(async () => {
  ;({ default: InvitePage } = await import('./page'))
})

type PostFn = (endpoint: string, data?: unknown) => Promise<unknown>
let postSpy: jest.Mock<PostFn>
const checkAuth = jest.fn(async () => {})

beforeEach(() => {
  mockReplace.mockClear()
  checkAuth.mockClear()
  postSpy = jest.fn<PostFn>(async (endpoint) => {
    if (endpoint === '/auth/invites/lookup')
      return { email: 'new@x.test', name: 'Nia', organization_name: 'Acme IR', expires_at: '2026-10-12T00:00:00Z' }
    return { user: { id: 'n1' } }
  })
  jest.spyOn(api, 'post').mockImplementation(postSpy as unknown as typeof api.post)
  act(() => {
    useAuthStore.setState({ checkAuth })
  })
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  window.history.replaceState(null, '', '/')
})

describe('Invite accept page', () => {
  it('reads the token from the fragment, strips it, and accepts', async () => {
    window.history.replaceState(null, '', '/auth/invite#token=tok-123')
    render(<InvitePage />)
    expect(await screen.findByText('Acme IR')).toBeInTheDocument()
    expect(window.location.hash).toBe('')
    expect(postSpy).toHaveBeenCalledWith('/auth/invites/lookup', { token: 'tok-123' })
    expect(screen.getByLabelText('Full name')).toHaveValue('Nia')

    const submit = screen.getByRole('button', { name: /create account/i })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'weak' } })
    expect(screen.getByLabelText('Password requirements')).toHaveTextContent('12+ characters (missing)')
    expect(submit).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Str0ng!Passw0rd' } })
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'Str0ng!Passw0rd' } })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/auth/invites/accept', {
        token: 'tok-123',
        name: 'Nia',
        password: 'Str0ng!Passw0rd',
      })
    )
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/dashboard'))
    expect(checkAuth).toHaveBeenCalled()
  })

  it('shows one generic error for a missing or invalid token', async () => {
    window.history.replaceState(null, '', '/auth/invite')
    render(<InvitePage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid or has expired/)
    expect(postSpy).not.toHaveBeenCalled()
    cleanup()

    postSpy.mockImplementation(async () => {
      throw new ApiError(400, 'This invitation is invalid or has expired', { code: 'invite_invalid' })
    })
    window.history.replaceState(null, '', '/auth/invite#token=used')
    render(<InvitePage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid or has expired/)
  })

  it('falls back to the generic error when accept says invite_invalid', async () => {
    window.history.replaceState(null, '', '/auth/invite#token=tok')
    postSpy.mockImplementation(async (endpoint) => {
      if (endpoint === '/auth/invites/lookup')
        return { email: 'new@x.test', name: null, organization_name: 'Acme IR', expires_at: '2026-10-12T00:00:00Z' }
      throw new ApiError(400, 'This invitation is invalid or has expired', { code: 'invite_invalid' })
    })
    render(<InvitePage />)
    await screen.findByText('Acme IR')
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'N' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Str0ng!Passw0rd' } })
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'Str0ng!Passw0rd' } })
    fireEvent.click(screen.getByRole('button', { name: /create account/i }))
    expect(await screen.findByText('Invitation not valid')).toBeInTheDocument()
    expect(mockReplace).not.toHaveBeenCalled()
  })
})
