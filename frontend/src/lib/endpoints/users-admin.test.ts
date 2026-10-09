import { afterEach, describe, expect, it, jest } from '@jest/globals'
import api from '@/lib/api'
import {
  absoluteLink,
  accountPublic,
  isPasswordValid,
  passwordChecks,
  takeHashToken,
  usersAdmin,
} from './users-admin'

afterEach(() => {
  jest.restoreAllMocks()
  window.history.replaceState(null, '', '/')
})

describe('takeHashToken', () => {
  it('reads #token and strips the fragment from the address bar', () => {
    window.history.replaceState(null, '', '/auth/invite?x=1#token=abc-DEF_123')
    expect(takeHashToken()).toBe('abc-DEF_123')
    expect(window.location.hash).toBe('')
    expect(window.location.pathname + window.location.search).toBe('/auth/invite?x=1')
  })

  it('returns null without a token or for an oversized one', () => {
    window.history.replaceState(null, '', '/auth/invite')
    expect(takeHashToken()).toBeNull()
    window.history.replaceState(null, '', `/auth/invite#token=${'a'.repeat(201)}`)
    expect(takeHashToken()).toBeNull()
  })
})

describe('absoluteLink', () => {
  it('prefers the server accept_url, else the current origin', () => {
    expect(absoluteLink({ accept_path: '/auth/invite#token=t', accept_url: 'https://ir.example/auth/invite#token=t' })).toBe(
      'https://ir.example/auth/invite#token=t'
    )
    expect(absoluteLink({ accept_path: '/auth/invite#token=t' })).toBe(`${window.location.origin}/auth/invite#token=t`)
  })
})

describe('password policy mirror', () => {
  it('matches backend validate_password', () => {
    expect(isPasswordValid('Str0ng!Passw0rd')).toBe(true)
    expect(isPasswordValid('Short1!a')).toBe(false)
    expect(isPasswordValid('NoSpecials1234')).toBe(false)
    // Any non-alphanumeric character is a symbol (security policy, W3-SEC).
    expect(passwordChecks('Abcdefghij1-_').special).toBe(true)
    expect(passwordChecks('Abcdefghij12').special).toBe(false)
    // The org's rules apply when given.
    const rules = { min_length: 16, max_bytes: 72, require_upper: true, require_lower: true, require_digit: true,
      require_symbol: false, history_count: 0, max_age_days: 0 }
    expect(isPasswordValid('Str0ng!Passw0rd', rules)).toBe(false)
    expect(isPasswordValid('NoSpecials123456', rules)).toBe(true)
    expect(isPasswordValid('Aa1!' + 'x'.repeat(69))).toBe(false) // over 72 bytes
  })
})

describe('endpoints', () => {
  it('hits the backend routes', async () => {
    const post = jest.spyOn(api, 'post').mockResolvedValue({} as never)
    const del = jest.spyOn(api, 'delete').mockResolvedValue({} as never)
    const get = jest.spyOn(api, 'get').mockResolvedValue({} as never)

    await usersAdmin.resetPassword('u1', 'link', { revokeSessions: false })
    expect(post).toHaveBeenLastCalledWith('/users/u1/reset-password', { mode: 'link', revoke_sessions: false })
    await usersAdmin.resetPassword('u1', 'temp')
    expect(post).toHaveBeenLastCalledWith('/users/u1/reset-password', { mode: 'temp' })
    await usersAdmin.remove('u1', { anonymize: true })
    expect(del).toHaveBeenLastCalledWith('/users/u1?anonymize=true')
    await usersAdmin.remove('u2')
    expect(del).toHaveBeenLastCalledWith('/users/u2')
    await usersAdmin.activity('u1', { scope: 'target', per_page: 20 })
    expect(get).toHaveBeenLastCalledWith('/users/u1/activity?scope=target&per_page=20', undefined)
    await usersAdmin.invites.revoke('i1')
    expect(del).toHaveBeenLastCalledWith('/users/invites/i1')
    await accountPublic.completePasswordReset({ token: 't', new_password: 'p' })
    expect(post).toHaveBeenLastCalledWith('/auth/password-reset/complete', { token: 't', new_password: 'p' })
    await accountPublic.acceptInvite({ token: 't', name: 'N', password: 'p' })
    expect(post).toHaveBeenLastCalledWith('/auth/invites/accept', { token: 't', name: 'N', password: 'p' })
  })
})
