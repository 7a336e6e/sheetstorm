import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { clearCache, invalidate } from '@/lib/query-cache'
import { describeAiAvailability, useAiAvailability } from './use-ai-availability'
import type { AiAvailabilityResponse } from '@/types'

function response(over: Partial<AiAvailabilityResponse> = {}): AiAvailabilityResponse {
  return {
    ai_configured: true,
    ai_allowed: true,
    ai_providers: ['openai'],
    policy_mode: 'allow',
    providers: [{ name: 'openai', allowed: true, reason: 'allowed' }],
    tlp: 'green',
    ...over,
  }
}

const redLocalOnly = response({
  tlp: 'red',
  policy_mode: 'local_only',
  ai_allowed: true,
  ai_providers: ['ollama'],
  providers: [
    { name: 'openai', allowed: false, reason: 'cloud_provider' },
    { name: 'ollama', allowed: true, reason: 'local' },
  ],
})

describe('describeAiAvailability', () => {
  it('allows while unknown (loading / error)', () => {
    expect(describeAiAvailability(null)).toEqual({ allowed: true, reason: null })
  })

  it('blocks with the policy reason when the TLP level is blocked', () => {
    const v = describeAiAvailability(response({ tlp: 'amber_strict', policy_mode: 'block', ai_allowed: false, ai_providers: [],
      providers: [{ name: 'openai', allowed: false, reason: 'policy_block' }] }))
    expect(v.allowed).toBe(false)
    expect(v.reason).toBe("AI is disabled for TLP:AMBER+STRICT incidents by your organization's data egress policy.")
  })

  it('allows when any provider is allowed, and judges an explicit provider by its own entry', () => {
    expect(describeAiAvailability(redLocalOnly).allowed).toBe(true)
    expect(describeAiAvailability(redLocalOnly, 'ollama').allowed).toBe(true)
    const openai = describeAiAvailability(redLocalOnly, 'openai')
    expect(openai.allowed).toBe(false)
    expect(openai.reason).toContain('TLP:RED incidents may only use local AI providers')
    expect(openai.reason).toContain('it is a cloud provider')
  })

  it('explains local_only with no local provider available', () => {
    const v = describeAiAvailability(response({ tlp: 'red', policy_mode: 'local_only', ai_allowed: false, ai_providers: [],
      providers: [{ name: 'ollama', allowed: false, reason: 'not_allowlisted' }] }))
    expect(v.allowed).toBe(false)
    expect(v.reason).toMatch(/only use local AI providers .* none is available/)
  })

  it('reports an unconfigured AI setup', () => {
    const v = describeAiAvailability(response({ ai_configured: false, ai_allowed: false, ai_providers: [], providers: [] }))
    expect(v).toEqual({ allowed: false, reason: expect.stringContaining('No AI provider is configured') })
  })
})

describe('useAiAvailability', () => {
  let getSpy: jest.Mock<(endpoint: string) => Promise<unknown>>

  beforeEach(() => {
    clearCache()
    getSpy = jest.fn<(endpoint: string) => Promise<unknown>>(async () => redLocalOnly)
    jest.spyOn(api, 'get').mockImplementation(getSpy as unknown as typeof api.get)
  })

  afterEach(() => {
    cleanup()
    jest.restoreAllMocks()
  })

  it('reads the per-incident providers endpoint once for every consumer', async () => {
    const a = renderHook(() => useAiAvailability('inc-1'))
    const b = renderHook(() => useAiAvailability('inc-1', { provider: 'openai' }))
    expect(a.result.current.loading).toBe(true)
    await waitFor(() => expect(a.result.current.loading).toBe(false))
    await waitFor(() => expect(b.result.current.loading).toBe(false))

    expect(getSpy).toHaveBeenCalledTimes(1)
    expect(getSpy.mock.calls[0][0]).toBe('/incidents/inc-1/reports/types')
    expect(a.result.current).toMatchObject({ allowed: true, policyMode: 'local_only', tlp: 'red', allowedProviders: ['ollama'] })
    expect(b.result.current.allowed).toBe(false)
  })

  it('refetches when the incident is invalidated (e.g. TLP changed)', async () => {
    const { result } = renderHook(() => useAiAvailability('inc-2'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    getSpy.mockImplementation(async () =>
      response({ tlp: 'red', policy_mode: 'block', ai_allowed: false, ai_providers: [],
        providers: [{ name: 'openai', allowed: false, reason: 'policy_block' }] }))

    act(() => invalidate('/incidents/inc-2'))

    await waitFor(() => expect(result.current.allowed).toBe(false))
    expect(getSpy).toHaveBeenCalledTimes(2)
  })

  it('never blocks on a failed lookup', async () => {
    getSpy.mockImplementation(async () => {
      throw new ApiError(403, 'Permission denied', { code: 'forbidden' })
    })
    const { result } = renderHook(() => useAiAvailability('inc-3'))
    await waitFor(() => expect(result.current.error).toBeTruthy())
    expect(result.current.allowed).toBe(true)
    expect(result.current.loading).toBe(false)
  })

  it('does nothing without an incident id', () => {
    const { result } = renderHook(() => useAiAvailability(null))
    expect(result.current.loading).toBe(false)
    expect(getSpy).not.toHaveBeenCalled()
  })
})
