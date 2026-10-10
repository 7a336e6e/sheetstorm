import type { ComponentType } from 'react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import api from '@/lib/api'
import { useAuthStore } from '@/lib/store'

let params = new URLSearchParams()
const push = jest.fn()
jest.mock('next/navigation', () => ({
  useSearchParams: () => params,
  useRouter: () => ({ push, replace: jest.fn() }),
  usePathname: () => '/login',
}))
jest.mock('@/components/ui/use-toast', () => ({ useToast: () => ({ toast: jest.fn() }), toast: jest.fn() }))
jest.mock('@/hooks/use-password-policy', () => ({
  usePasswordPolicy: () => ({ min_length: 12, require_upper: false, require_lower: false, require_digit: false, require_symbol: false }),
}))

let LoginPage: ComponentType
beforeAll(async () => {
  LoginPage = (await import('./page')).default
})

let ssoOptions: unknown
beforeEach(() => {
  params = new URLSearchParams()
  push.mockReset()
  ssoOptions = { providers: [{ slug: 'corp', name: 'Contoso Entra ID', preset: 'entra', start_url: '/api/v1/auth/sso/corp/start' }], github: false }
  global.fetch = jest.fn(async () => ({ json: async () => ({ registration_enabled: false }) })) as unknown as typeof fetch
  jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    if (endpoint === '/auth/sso/providers') return ssoOptions
    throw new Error(`unexpected GET ${endpoint}`)
  }) as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

async function renderPage() {
  await act(async () => {
    render(<LoginPage />)
  })
}

describe('login page: single sign-on', () => {
  it('shows a button per provider that navigates to its start URL with the next page', async () => {
    params = new URLSearchParams('next=/dashboard/incidents')
    await renderPage()
    const link = await screen.findByRole('link', { name: 'Contoso Entra ID' })
    expect(link.getAttribute('href')).toBe('/api/v1/auth/sso/corp/start?next=%2Fdashboard%2Fincidents')
    // No GitHub app and no Supabase: no GitHub button, no disabled placeholders.
    expect(screen.queryByRole('button', { name: /GitHub/ })).toBeNull()
    expect(screen.queryByText('Okta')).toBeNull()
  })

  it('hides the section when nothing is configured and shows GitHub when it is', async () => {
    ssoOptions = { providers: [], github: false }
    await renderPage()
    expect(screen.queryByText('Single sign-on')).toBeNull()
    cleanup()
    ssoOptions = { providers: [], github: true }
    await renderPage()
    expect(await screen.findByRole('button', { name: /GitHub/ })).toBeTruthy()
  })

  it('explains a refused sign-in from its error code only', async () => {
    params = new URLSearchParams('sso_error=group_not_allowed')
    await renderPage()
    expect(screen.getByTestId('sso-error').textContent).toBe('You are not in a group that may sign in to SheetStorm.')
    cleanup()
    params = new URLSearchParams('sso_error=<script>')
    await renderPage()
    expect(screen.getByTestId('sso-error').textContent).toBe('Something went wrong during sign-in. Please try again.')
  })

  it('finishes an SSO sign-in with the TOTP code (the pre-auth token stays in its cookie)', async () => {
    params = new URLSearchParams('sso=mfa&next=/dashboard/incidents')
    const post = jest.spyOn(api, 'post').mockResolvedValue({
      user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions: [] },
    } as never)
    await renderPage()
    expect(screen.queryByLabelText('Work Email')).toBeNull()
    fireEvent.change(screen.getByLabelText(/Authenticator Code/), { target: { value: '123456' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Verify and continue' }))
    })
    expect(post).toHaveBeenCalledWith('/auth/mfa/complete', { mfa_code: '123456' })
    await waitFor(() => expect(push).toHaveBeenCalledWith('/dashboard/incidents'))
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
  })

  it('never continues to an absolute URL after MFA', async () => {
    params = new URLSearchParams('sso=mfa&next=//evil.example')
    jest.spyOn(api, 'post').mockResolvedValue({ user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions: [] } } as never)
    await renderPage()
    fireEvent.change(screen.getByLabelText(/Authenticator Code/), { target: { value: '123456' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Verify and continue' }))
    })
    await waitFor(() => expect(push).toHaveBeenCalledWith('/dashboard'))
  })
})
