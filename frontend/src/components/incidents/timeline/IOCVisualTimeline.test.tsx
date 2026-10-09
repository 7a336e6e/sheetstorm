import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { screen } from '@testing-library/react'
import { envelope, getCalls, mockApi, renderTab, resetTabTest, setRole } from '../test-utils'

// next/jest does not hoist jest.mock above imports: mock first, then load
// the component dynamically.
// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('../test-utils').navigationMock)

type Mod = typeof import('./IOCVisualTimeline')
let IOCVisualTimeline: Mod['IOCVisualTimeline']
let PinnedTimelineTab: Mod['PinnedTimelineTab']
beforeAll(async () => {
  ;({ IOCVisualTimeline, PinnedTimelineTab } = await import('./IOCVisualTimeline'))
})

const pinned = {
  id: 'e1',
  incident_id: 'i1',
  timestamp: '2026-01-01T10:00:00Z',
  activity: 'Initial phishing email opened',
  is_key_event: true,
  is_ioc: false,
  created_at: '2026-01-01T10:00:00Z',
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('IOCVisualTimeline', () => {
  it('Viewer gets no Add Event control', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/timeline': envelope([]) })
    renderTab(<IOCVisualTimeline incidentId="i1" />)

    expect(await screen.findByText('No Pinned Events')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /add event/i })).toBeNull()
  })

  it('Responder gets the Add Event control', async () => {
    setRole('responder')
    mockApi({ '/incidents/i1/timeline': envelope([]) })
    renderTab(<IOCVisualTimeline incidentId="i1" />)

    expect(await screen.findByRole('button', { name: /add event/i })).toBeTruthy()
  })
})

describe('PinnedTimelineTab', () => {
  it('loads key events server-side filtered', async () => {
    setRole('viewer')
    const api = mockApi({ '/incidents/i1/timeline': envelope([pinned]) })
    renderTab(<PinnedTimelineTab incidentId="i1" />)

    expect(await screen.findByText('Initial phishing email opened')).toBeTruthy()
    const calls = getCalls(api.get).filter((e) => e.startsWith('/incidents/i1/timeline'))
    expect(calls.length).toBeGreaterThan(0)
    calls.forEach((e) => expect(new URLSearchParams(e.split('?')[1]).get('key_only')).toBe('true'))
  })
})
