import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'
import { useTimePrefStore } from '@/lib/store'
import { currentSearch, envelope, getCalls, mockApi, renderTab, resetTabTest, setRole, setSearch } from './test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('./test-utils').navigationMock)

let mod: typeof import('./EventsTable')
beforeAll(async () => {
  mod = await import('./EventsTable')
})

const event = (over: Record<string, unknown>) => ({
  incident_id: 'i1',
  is_key_event: false,
  is_ioc: false,
  created_at: '2026-10-01T00:00:00Z',
  version: 1,
  ...over,
})

const events = [
  event({ id: 'e1', activity: 'psexec to DC', timestamp: '2026-10-01T10:00:00Z',
    detection_time: '2026-10-03T14:00:00Z', confidence_level: 'high' }),
  event({ id: 'e2', activity: 'clock skewed', timestamp: '2026-10-04T10:00:00Z',
    detection_time: '2026-10-04T09:55:00Z', confidence_level: null }),
]

beforeEach(() => {
  resetTabTest()
  act(() => useTimePrefStore.setState({ mode: 'utc' } as never))
})
afterEach(() => resetTabTest())

describe('EventsTable dual time', () => {
  it('shows event time, detection, dwell and confidence', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/timeline': envelope(events) })
    renderTab(<mod.EventsTable incidentId="i1" />)

    expect(await screen.findByText('psexec to DC')).toBeTruthy()
    expect(screen.getByText('2d 4h')).toBeTruthy()
    expect(screen.getByText('High')).toBeTruthy()
    // Negative dwell is flagged.
    expect(screen.getByLabelText('Detected before occurrence — check timestamps')).toBeTruthy()
    expect(screen.getByText('-5m')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Detected/ })).toBeTruthy() // sortable header
  })

  it('sends confidence / detection filters and detection sort to the server', async () => {
    setRole('viewer')
    setSearch('events.f.confidence=high,certain&events.f.has_detection=true&events.sort=-detection_time')
    const api = mockApi({ '/incidents/i1/timeline': envelope(events) })
    renderTab(<mod.EventsTable incidentId="i1" />)
    await screen.findByText('psexec to DC')
    const call = getCalls(api.get).find((e) => e.startsWith('/incidents/i1/timeline?'))!
    const q = new URLSearchParams(call.split('?')[1])
    expect(q.get('confidence')).toBe('high,certain')
    expect(q.get('has_detection')).toBe('true')
    expect(q.get('sort')).toBe('-detection_time')
  })

  it('header sort cycles detection time in the URL', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/timeline': envelope(events) })
    renderTab(<mod.EventsTable incidentId="i1" />)
    await screen.findByText('psexec to DC')
    fireEvent.click(screen.getByRole('button', { name: /^Detected/ }))
    await waitFor(() => expect(currentSearch().get('events.sort')).toBe('detection_time'))
  })
})

describe('ConfidenceBadge / DwellCell', () => {
  it('renders a dash when unset', () => {
    render(<>
      <mod.ConfidenceBadge level={null} />
      <mod.DwellCell event={{ timestamp: '2026-10-01T00:00:00Z', detection_time: null }} />
    </>)
    expect(screen.getAllByText('—')).toHaveLength(2)
  })
})
