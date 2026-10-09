import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import { RateLimitingSection } from './RateLimitingSection'
import { isValidLimit, overridesFrom } from '@/lib/endpoints/rate-limits'
import type { RateLimitGroup, RateLimitSettings } from '@/types'

const group = (key: string, extra: Partial<RateLimitGroup> = {}): RateLimitGroup => ({
  key, description: `${key} desc`, category: key === 'api_default' ? 'global' : 'auth', auth_sensitive: key !== 'api_default',
  routes: [], default: key === 'api_default' ? '600 per minute' : '5 per minute', env: null, override: null,
  limit: key === 'api_default' ? '600 per minute' : '5 per minute', source: 'code', enabled: true,
  effective: '5 per minute', ...extra,
})

const settings = (extra: Partial<RateLimitSettings> = {}): RateLimitSettings => ({
  enabled: true, locked: false, hard_disabled: false, can_edit: true, version: 3, updated_at: null,
  cache_ttl_seconds: 5, groups: [group('api_default'), group('auth_login')], ...extra,
})

const renderSection = () => render(<ConfirmDialogProvider><RateLimitingSection /></ConfirmDialogProvider>)

beforeEach(() => {
  jest.restoreAllMocks()
})
afterEach(() => cleanup())

describe('rate-limit helpers', () => {
  it('pre-checks limit strings', () => {
    for (const ok of ['5 per minute', '10/minute', '5 per minute;100 per day', '2 per 5 minutes']) expect(isValidLimit(ok)).toBe(true)
    for (const bad of ['', 'lots', '5 per fortnight', '1/second;'.repeat(6)]) expect(isValidLimit(bad)).toBe(false)
  })

  it('sends only real overrides', () => {
    const groups = [group('api_default'), group('auth_login', { env: '7 per minute', limit: '7 per minute', source: 'env' })]
    expect(overridesFrom(groups, {
      api_default: { limit: '600 per minute', enabled: true },
      auth_login: { limit: '7 per minute', enabled: false },
    })).toEqual({ auth_login: { enabled: false } })
    expect(overridesFrom(groups, { api_default: { limit: '900 per minute', enabled: true } })).toEqual({
      api_default: { limit: '900 per minute' },
    })
  })
})

describe('RateLimitingSection', () => {
  it('is read-only for non platform admins', async () => {
    jest.spyOn(api, 'get').mockResolvedValue(settings({ can_edit: false }) as never)
    renderSection()
    expect(await screen.findByText(/Only platform administrators/)).toBeTruthy()
    expect((screen.getByLabelText('auth_login limit') as HTMLInputElement).disabled).toBe(true)
    expect(screen.queryByRole('button', { name: /save rate limits/i })).toBeNull()
  })

  it('asks for confirmation when the change weakens protection, then resends', async () => {
    jest.spyOn(api, 'get').mockResolvedValue(settings() as never)
    const put = jest.spyOn(api, 'put')
      .mockRejectedValueOnce(new ApiError(409, 'weakens', {
        code: 'confirmation_required',
        details: { error: 'confirmation_required', warnings: ['auth_login: an authentication limit is disabled'] },
      }) as never)
      .mockResolvedValueOnce(settings({ version: 4 }) as never)
    renderSection()
    fireEvent.click(await screen.findByRole('switch', { name: 'auth_login enabled' }))
    fireEvent.click(screen.getByRole('button', { name: /save rate limits/i }))
    expect(await screen.findByText(/an authentication limit is disabled/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Apply anyway' }))
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2))
    expect(put.mock.calls[0][1]).toMatchObject({ version: 3, groups: { auth_login: { enabled: false } } })
    expect(put.mock.calls[1][1]).toMatchObject({ confirm_weakening: true })
  })

  it('blocks saving an invalid limit', async () => {
    jest.spyOn(api, 'get').mockResolvedValue(settings() as never)
    renderSection()
    fireEvent.change(await screen.findByLabelText('auth_login limit'), { target: { value: 'lots' } })
    expect(screen.getByText(/Invalid limit for auth_login/)).toBeTruthy()
    expect((screen.getByRole('button', { name: /save rate limits/i }) as HTMLButtonElement).disabled).toBe(true)
  })
})
