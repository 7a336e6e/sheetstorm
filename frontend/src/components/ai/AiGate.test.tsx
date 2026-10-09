import { afterEach, beforeEach, describe, it, jest } from '@jest/globals'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import api from '@/lib/api'
import { clearCache } from '@/lib/query-cache'
import type { AiAvailability } from '@/hooks/use-ai-availability'
import type { AiAvailabilityResponse } from '@/types'
import { AiGate } from './AiGate'

const blocked: AiAvailabilityResponse = {
  ai_configured: true,
  ai_allowed: false,
  ai_providers: [],
  policy_mode: 'block',
  providers: [{ name: 'openai', allowed: false, reason: 'policy_block' }],
  tlp: 'red',
}

let mockResponse: AiAvailabilityResponse = blocked

beforeEach(() => {
  clearCache()
  mockResponse = blocked
  jest.spyOn(api, 'get').mockImplementation((async () => mockResponse) as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
})

describe('AiGate', () => {
  it('disables the button and explains why when the policy blocks AI', async () => {
    const onClick = jest.fn()
    render(
      <AiGate incidentId="inc-1">
        <button onClick={onClick}>AI summary</button>
      </AiGate>
    )
    await waitFor(() => expect(screen.getByRole('button', { name: 'AI summary' })).toBeDisabled())
    const button = screen.getByRole('button', { name: 'AI summary' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
    expect(button).toHaveAccessibleDescription(
      "AI is disabled for TLP:RED incidents by your organization's data egress policy."
    )
  })

  it('leaves the button alone when AI is allowed', async () => {
    mockResponse = { ...blocked, policy_mode: 'allow', ai_allowed: true, ai_providers: ['openai'],
      providers: [{ name: 'openai', allowed: true, reason: 'allowed' }], tlp: 'green' }
    render(
      <AiGate incidentId="inc-2">
        <button>AI summary</button>
      </AiGate>
    )
    await waitFor(() => expect(api.get).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: 'AI summary' })).toBeEnabled()
  })

  it('uses a precomputed availability without fetching', () => {
    const availability = {
      allowed: false,
      reason: 'Blocked for testing.',
    } as AiAvailability
    render(
      <AiGate incidentId="inc-3" availability={availability}>
        <button>Generate with AI</button>
      </AiGate>
    )
    expect(screen.getByRole('button', { name: 'Generate with AI' })).toBeDisabled()
    expect(screen.getByText('Blocked for testing.')).toBeInTheDocument()
    expect(api.get).not.toHaveBeenCalled()
  })
})
