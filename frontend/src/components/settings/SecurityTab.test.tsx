import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import type { SecurityPolicy, SecurityPolicyResponse } from '@/types'
import { SecurityTab, normalizeDomain, policyUpdate } from './SecurityTab'

const POLICY: SecurityPolicy = {
  password: {
    min_length: 12,
    require_upper: true,
    require_lower: true,
    require_digit: true,
    require_symbol: true,
    history_count: 0,
    max_age_days: 0,
  },
  lockout: { threshold: 10, duration_minutes: 15 },
  mfa: { required_for: 'none', grace_days: 7, enforced_since: null },
  session: { access_token_minutes: 60, refresh_token_days: 7 },
  provisioning: { allowed_email_domains: [], registration_enabled: false, default_role: 'Viewer' },
}

function response(over: Partial<SecurityPolicyResponse> = {}): SecurityPolicyResponse {
  return {
    id: null,
    organization_id: 'org-1',
    policy: JSON.parse(JSON.stringify(POLICY)),
    version: 0,
    defaults: JSON.parse(JSON.stringify(POLICY)),
    bounds: {
      'password.min_length': { min: 12, max: 72 },
      'password.history_count': { min: 0, max: 24 },
      'password.max_age_days': { min: 30, max: 730, off: 0 },
    },
    stats: { users_total: 4, users_mfa: 1, privileged_total: 1, privileged_mfa: 1, users_without_mfa_past_grace: 0 },
    is_platform_org: false,
    updated_by: null,
    updated_at: null,
    ...over,
  }
}

let current: SecurityPolicyResponse
let getSpy: jest.Mock<(endpoint: string) => Promise<unknown>>
let putSpy: jest.Mock<(endpoint: string, data?: unknown) => Promise<unknown>>

beforeEach(() => {
  current = response()
  getSpy = jest.fn<(endpoint: string) => Promise<unknown>>(async (endpoint: string) => {
    if (endpoint === '/organization/security-policy') return current
    if (endpoint === '/roles') {
      return {
        items: [
          { id: 'r1', name: 'Viewer', description: '', permissions: ['incidents:read'], is_system: true },
          { id: 'r2', name: 'Administrator', description: '', permissions: ['users:manage'], is_system: true },
        ],
      }
    }
    if (endpoint === '/permissions') {
      return {
        groups: [],
        items: [
          { key: 'users:manage', group: 'users', label: 'Manage users', description: '', dangerous: true,
            privileged: true, api_key_grantable: false, platform_only: false },
        ],
      }
    }
    return { items: [] }
  })
  jest.spyOn(api, 'get').mockImplementation(getSpy as unknown as typeof api.get)
  putSpy = jest.fn<(endpoint: string, data?: unknown) => Promise<unknown>>(async (_e, data) => {
    const body = data as { policy: SecurityPolicy }
    current = response({ version: 1, policy: { ...POLICY, ...body.policy } as SecurityPolicy })
    return current
  })
  jest.spyOn(api, 'put').mockImplementation(putSpy as unknown as typeof api.put)
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'a@x', name: 'A', roles: [], permissions: ['organizations:manage'], mfa_enabled: true },
      isAuthenticated: true,
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

function renderTab() {
  return render(
    <ConfirmDialogProvider>
      <SecurityTab />
    </ConfirmDialogProvider>
  )
}

describe('SecurityTab', () => {
  it('saves the edited policy with the loaded version (no enforced_since)', async () => {
    renderTab()
    const minLength = await screen.findByLabelText('Minimum length')
    fireEvent.change(minLength, { target: { value: '16' } })
    fireEvent.click(screen.getByRole('switch', { name: 'Require a symbol' }))
    fireEvent.change(screen.getByLabelText('Allowed email domains'), { target: { value: '@Corp.Example' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(screen.getByText('corp.example')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(putSpy).toHaveBeenCalled())
    const [endpoint, body] = putSpy.mock.calls[0] as [string, { policy: SecurityPolicy; version: number }]
    expect(endpoint).toBe('/organization/security-policy')
    expect(body.version).toBe(0)
    expect(body.policy.password.min_length).toBe(16)
    expect(body.policy.password.require_symbol).toBe(false)
    expect(body.policy.provisioning.allowed_email_domains).toEqual(['corp.example'])
    expect(body.policy.mfa).toEqual({ required_for: 'none', grace_days: 7 })
  })

  it('shows field errors from a 400 validation_error', async () => {
    putSpy.mockImplementation(async () => {
      throw new ApiError(400, 'Invalid security policy', {
        code: 'validation_error',
        details: { error: 'validation_error', fields: { 'password.min_length': 'Input should be less than or equal to 72' } },
      })
    })
    renderTab()
    fireEvent.change(await screen.findByLabelText('Minimum length'), { target: { value: '99' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Input should be less than or equal to 72')).toBeInTheDocument()
  })

  it('reloads on a version conflict', async () => {
    putSpy.mockImplementation(async () => {
      throw new ApiError(409, 'changed', { code: 'conflict', details: { error: 'conflict' } })
    })
    renderTab()
    fireEvent.change(await screen.findByLabelText('Minimum length'), { target: { value: '20' } })
    current = response({ version: 3, policy: { ...POLICY, password: { ...POLICY.password, min_length: 14 } } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect((screen.getByLabelText('Minimum length') as HTMLInputElement).value).toBe('14'))
    expect(getSpy.mock.calls.filter(([e]) => e === '/organization/security-policy').length).toBe(2)
  })

  it('offers the registration switch only on the platform organization', async () => {
    renderTab()
    await screen.findByLabelText('Minimum length')
    expect(screen.queryByRole('switch', { name: 'Allow self-registration' })).toBeNull()
    cleanup()
    current = response({ is_platform_org: true })
    renderTab()
    expect(await screen.findByRole('switch', { name: 'Allow self-registration' })).toBeInTheDocument()
  })

  it('shows MFA adoption and keeps Save disabled until something changes', async () => {
    renderTab()
    expect(await screen.findByText(/1 of 4 users \(25%\)/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  })
})

describe('SecurityTab helpers', () => {
  it('normalizes domains like the server', () => {
    expect(normalizeDomain(' @Example.COM ')).toBe('example.com')
    expect(normalizeDomain('not a domain')).toBeNull()
    expect(normalizeDomain('localhost')).toBeNull()
  })

  it('never sends the server-managed enforced_since', () => {
    const body = policyUpdate({ ...POLICY, mfa: { required_for: 'all', grace_days: 3, enforced_since: '2026-01-01T00:00:00Z' } })
    expect(body.mfa).toEqual({ required_for: 'all', grace_days: 3 })
  })
})
