import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import api from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import type { SecurityStatus } from '@/types'
import ProfilePage from './page'

const SETUP = { secret: 'JBSWY3DPEHPK3PXP', provisioning_uri: 'otpauth://totp/x?secret=JBSWY3DPEHPK3PXP', backup_codes: ['AAAA1111'] }

function status(over: Partial<SecurityStatus> = {}): SecurityStatus {
  return {
    mfa_required: true,
    mfa_enrollment_required: true,
    mfa_grace_ends_at: '2026-10-01T00:00:00Z',
    password_change_required: false,
    password_expires_at: null,
    ...over,
  }
}

let me: Record<string, unknown>
let postSpy: jest.Mock<(endpoint: string, data?: unknown) => Promise<unknown>>
const refreshUser = jest.fn(async () => {})

beforeEach(() => {
  window.history.replaceState(null, '', '/dashboard/profile')
  me = {
    id: 'u1', email: 'u@x.test', name: 'U', roles: ['Analyst'], permissions: ['incidents:read'],
    is_active: true, created_at: '2026-01-01T00:00:00Z', mfa_enabled: false, security: status(),
  }
  jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    if (endpoint === '/auth/me') return me
    if (endpoint === '/auth/password-policy') {
      return { min_length: 14, max_bytes: 72, require_upper: true, require_lower: true, require_digit: true,
        require_symbol: true, history_count: 0, max_age_days: 0 }
    }
    if (endpoint.startsWith('/users/u1/sessions')) return { items: [], total: 0, page: 1, per_page: 100, pages: 0 }
    return {}
  }) as unknown as typeof api.get)
  postSpy = jest.fn<(endpoint: string, data?: unknown) => Promise<unknown>>(async (endpoint: string) => {
    if (endpoint === '/auth/mfa/setup') return SETUP
    if (endpoint === '/auth/mfa/verify') {
      me = { ...me, mfa_enabled: true, security: status({ mfa_enrollment_required: false, mfa_grace_ends_at: null }) }
      return { message: 'ok' }
    }
    return {}
  })
  jest.spyOn(api, 'post').mockImplementation(postSpy as unknown as typeof api.post)
  refreshUser.mockClear()
  act(() => {
    useAuthStore.setState({
      user: me as never,
      isAuthenticated: true,
      refreshUser,
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

function renderPage() {
  return render(
    <ConfirmDialogProvider>
      <ProfilePage />
    </ConfirmDialogProvider>
  )
}

describe('Profile: MFA enrollment required by the security policy', () => {
  it('explains the restriction and opens the setup automatically', async () => {
    renderPage()
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Set up two-factor authentication to continue')).toBeInTheDocument()
    await waitFor(() => expect(postSpy).toHaveBeenCalledWith('/auth/mfa/setup', {}))
    expect(await screen.findByText('Set Up Authenticator')).toBeInTheDocument()
    // Sessions are not offered while restricted (the API refuses them).
    expect(screen.queryByText('Your sessions')).toBeNull()
  })

  it('verifying the code lifts the restriction', async () => {
    renderPage()
    const input = await screen.findByLabelText('Enter the 6-digit code from your app')
    fireEvent.change(input, { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: /Verify & Enable/ }))
    await waitFor(() => expect(postSpy).toHaveBeenCalledWith('/auth/mfa/verify', { code: '123456' }))
    await waitFor(() => expect(refreshUser).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByText('Set up two-factor authentication to continue')).toBeNull())
  })

  it('?enroll_mfa=1 during the grace period shows the deadline and opens the setup', async () => {
    window.history.replaceState(null, '', '/dashboard/profile?enroll_mfa=1')
    me = { ...me, security: status({ mfa_enrollment_required: false, mfa_grace_ends_at: '2099-01-01T00:00:00Z' }) }
    renderPage()
    const banner = await screen.findByRole('status')
    expect(within(banner).getByText('Two-factor authentication is required')).toBeInTheDocument()
    await waitFor(() => expect(postSpy).toHaveBeenCalledWith('/auth/mfa/setup', {}))
  })

  it('cannot disable MFA the organization requires; shows the sessions card', async () => {
    me = { ...me, mfa_enabled: true, security: status({ mfa_enrollment_required: false, mfa_grace_ends_at: null }) }
    renderPage()
    expect(await screen.findByText(/requires two-factor authentication, so it cannot be turned off/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Disable MFA' })).toBeNull()
    expect(await screen.findByText('Your sessions')).toBeInTheDocument()
    expect(postSpy).not.toHaveBeenCalledWith('/auth/mfa/setup', {})
  })

  it('password hints follow the org policy', async () => {
    me = { ...me, mfa_enabled: true, security: status({ mfa_required: false, mfa_enrollment_required: false, mfa_grace_ends_at: null }) }
    renderPage()
    expect(await screen.findByText(/At least 14 characters/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('New Password'), { target: { value: 'Short1!' } })
    expect(screen.getByText('14+ characters')).toBeInTheDocument()
  })
})
