import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import '@testing-library/jest-dom/jest-globals'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'

let ResetPage: typeof import('./page').default
beforeAll(async () => {
  ;({ default: ResetPage } = await import('./page'))
})

type PostFn = (endpoint: string, data?: unknown) => Promise<unknown>
let postSpy: jest.Mock<PostFn>

beforeEach(() => {
  postSpy = jest.fn<PostFn>(async () => ({ message: 'ok' }))
  jest.spyOn(api, 'post').mockImplementation(postSpy as unknown as typeof api.post)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  window.history.replaceState(null, '', '/')
})

function fill(pw: string, confirm = pw) {
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: pw } })
  fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: confirm } })
}

describe('Password reset page', () => {
  it('completes the reset with the fragment token and points to sign in', async () => {
    window.history.replaceState(null, '', '/auth/reset-password#token=rst')
    render(<ResetPage />)
    await screen.findByRole('button', { name: 'Set password' })
    expect(window.location.hash).toBe('')
    fill('Str0ng!Passw0rd', 'Different!Pass1')
    expect(screen.getByText('Passwords do not match')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Set password' })).toBeDisabled()
    fill('Str0ng!Passw0rd')
    fireEvent.click(screen.getByRole('button', { name: 'Set password' }))
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/auth/password-reset/complete', {
        token: 'rst',
        new_password: 'Str0ng!Passw0rd',
      })
    )
    expect(await screen.findByText('Password updated')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login')
  })

  it('shows the generic error on reset_invalid and keeps policy errors on the form', async () => {
    window.history.replaceState(null, '', '/auth/reset-password#token=rst')
    postSpy.mockImplementationOnce(async () => {
      throw new ApiError(400, 'Password must contain a number', { code: 'bad_request' })
    })
    render(<ResetPage />)
    await screen.findByRole('button', { name: 'Set password' })
    fill('Str0ng!Passw0rd')
    fireEvent.click(screen.getByRole('button', { name: 'Set password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Password must contain a number')

    postSpy.mockImplementationOnce(async () => {
      throw new ApiError(400, 'This reset link is invalid or has expired', { code: 'reset_invalid' })
    })
    fireEvent.click(screen.getByRole('button', { name: 'Set password' }))
    expect(await screen.findByText('Reset link not valid')).toBeInTheDocument()
  })

  it('is invalid without a token', async () => {
    window.history.replaceState(null, '', '/auth/reset-password')
    render(<ResetPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid or has expired/)
  })
})
