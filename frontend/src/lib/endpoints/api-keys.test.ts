/** @jest-environment node */
import { describe, expect, it } from '@jest/globals'
import { ApiError } from '@/lib/api'
import type { ApiKeyScopeGroup } from '@/types'
import {
  MCP_CONFIG_HINT,
  daysUntil,
  defaultExpiry,
  describeApiKeyError,
  envSnippet,
  expiresSoon,
  expiryOptions,
  fieldErrors,
  isApiKeyCode,
  visibleGroups,
} from './api-keys'

const NOW = Date.parse('2026-10-09T00:00:00Z')
const inDays = (n: number) => new Date(NOW + n * 86_400_000).toISOString()

describe('expiry helpers', () => {
  it('offers the standard choices under the org cap, plus the cap itself', () => {
    expect(expiryOptions(365)).toEqual([7, 30, 90, 180, 365])
    expect(expiryOptions(60)).toEqual([7, 30, 60])
    expect(expiryOptions(3)).toEqual([3])
    expect(expiryOptions(0)).toEqual([1])
  })

  it('defaults to 90 days or the cap when lower', () => {
    expect(defaultExpiry(365)).toBe(90)
    expect(defaultExpiry(30)).toBe(30)
  })

  it('counts whole days and flags only active keys within 14 days', () => {
    expect(daysUntil(inDays(5), NOW)).toBe(5)
    expect(daysUntil('nope', NOW)).toBeNull()
    expect(expiresSoon({ status: 'active', expires_at: inDays(14) }, NOW)).toBe(true)
    expect(expiresSoon({ status: 'active', expires_at: inDays(15) }, NOW)).toBe(false)
    expect(expiresSoon({ status: 'revoked', expires_at: inDays(2) }, NOW)).toBe(false)
    expect(expiresSoon({ status: 'expired', expires_at: inDays(-2) }, NOW)).toBe(false)
  })
})

describe('scope helpers', () => {
  it('drops non-grantable scopes and empty groups', () => {
    const groups: ApiKeyScopeGroup[] = [
      { group: 'a', label: 'A', scopes: [{ value: 'a:read', label: 'r', sensitive: false }] },
      { group: 'b', label: 'B', scopes: [{ value: 'b:x', label: 'x', sensitive: true, grantable: false }] },
    ]
    expect(visibleGroups(groups).map((g) => g.group)).toEqual(['a'])
    expect(visibleGroups(undefined)).toEqual([])
  })
})

describe('MCP hint', () => {
  it('references the variable instead of embedding a key', () => {
    expect(MCP_CONFIG_HINT).toContain('"SHEETSTORM_API_KEY": "${env:SHEETSTORM_API_KEY}"')
    expect(MCP_CONFIG_HINT).not.toMatch(/ssk_/)
    expect(envSnippet('ssk_x_y')).toBe('SHEETSTORM_API_KEY=ssk_x_y')
  })
})

describe('errors', () => {
  it('gives API-key codes specific copy (403 api_keys_disabled is not "permission denied")', () => {
    const disabled = new ApiError(403, 'API keys are disabled for this organization', { code: 'api_keys_disabled' })
    expect(isApiKeyCode(disabled)).toBe(true)
    expect(describeApiKeyError(disabled).title).toBe('API keys are disabled')
    const interactive = new ApiError(403, 'x', { code: 'interactive_session_required' })
    expect(describeApiKeyError(interactive).title).toBe('Sign-in required')
  })

  it('lists the offending scopes of invalid_scopes', () => {
    const err = new ApiError(400, 'x', {
      code: 'invalid_scopes',
      details: { forbidden: ['users:manage'], unknown: ['nope:read'], not_held: [] },
    })
    expect(describeApiKeyError(err).description).toBe(
      'Not grantable to keys: users:manage. Unknown: nope:read.'
    )
  })

  it('falls back to describeError for everything else', () => {
    const guard = new ApiError(403, 'x', { code: 'privilege_escalation', details: { missing: ['a:b'] } })
    expect(isApiKeyCode(guard)).toBe(false)
    expect(describeApiKeyError(guard).title).toBe('Exceeds your permissions')
    expect(describeApiKeyError(new ApiError(404, 'x')).title).toBe('Not found')
  })

  it('reads field errors of a validation_error body', () => {
    const err = new ApiError(400, 'x', {
      code: 'validation_error',
      details: { fields: { name: 'Already used by an active key', n: 3 } },
    })
    expect(fieldErrors(err)).toEqual({ name: 'Already used by an active key' })
    expect(fieldErrors(new Error('x'))).toEqual({})
  })
})
