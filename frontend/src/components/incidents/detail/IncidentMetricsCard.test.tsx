import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import type { IncidentMetrics } from '@/types'
import { dispatchChange } from '@/lib/realtime/live'
import { mockApi, renderTab, resetTabTest, setPermissions } from '../test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('../test-utils').navigationMock)

let IncidentMetricsCard: typeof import('./IncidentMetricsCard').IncidentMetricsCard
let EDIT_LIFECYCLE_EVENT: string
beforeAll(async () => {
  ;({ IncidentMetricsCard } = await import('./IncidentMetricsCard'))
  ;({ EDIT_LIFECYCLE_EVENT } = await import('./IRMilestoneStrip'))
})

const H = 3600

const metrics = (over: Partial<IncidentMetrics> = {}): IncidentMetrics => ({
  incident_id: 'i1',
  timestamps: {
    first_malicious: '2026-01-01T00:00:00Z',
    detected: '2026-01-02T12:00:00Z',
    responded: null,
    contained: '2026-01-02T16:00:00Z',
    eradicated: null,
    recovered: null,
    closed: null,
  },
  durations: {
    dwell_time: 36 * H,
    time_to_respond: null,
    time_to_contain: 4 * H,
    contain_to_eradicate: null,
    eradicate_to_recover: null,
    recover_to_close: null,
    total_open: 3 * 86400 + 5 * H,
  },
  anomalies: [],
  sources: { first_malicious: 'timeline' },
  ...over,
})

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('IncidentMetricsCard', () => {
  it('shows each duration, with a dash when an endpoint is missing', async () => {
    setPermissions(['incidents:read'])
    const spies = mockApi({ '/incidents/i1/metrics': metrics() })
    renderTab(<IncidentMetricsCard incidentId="i1" version={1} />)
    await waitFor(() => expect(screen.getByTestId('metric-dwell_time').textContent).toContain('1d 12h'))
    expect(screen.getByTestId('metric-time_to_contain').textContent).toContain('4h')
    expect(screen.getByTestId('metric-total_open').textContent).toContain('3d 5h')
    expect(screen.getByTestId('metric-time_to_respond').textContent).toContain('—')
    expect(spies.get).toHaveBeenCalledWith('/incidents/i1/metrics', expect.anything())
    expect(screen.getByText(/earliest timeline event marked as malicious/i)).toBeInTheDocument()
    expect(screen.queryByText(/out-of-order lifecycle times/i)).toBeNull()
  })

  it('flags out-of-order intervals instead of showing a negative duration', async () => {
    setPermissions(['incidents:read'])
    mockApi({
      '/incidents/i1/metrics': metrics({
        durations: { ...metrics().durations, time_to_contain: null },
        anomalies: [{ metric: 'time_to_contain', reason: 'negative', seconds: -3600 }],
      }),
    })
    renderTab(<IncidentMetricsCard incidentId="i1" />)
    expect((await screen.findByRole('status')).textContent).toMatch(/Out-of-order lifecycle times: Time to contain/)
    expect(screen.getByTestId('metric-time_to_contain').textContent).toContain('—')
    expect(screen.getByLabelText('out of order')).toBeInTheDocument()
  })

  it.each<[IncidentMetrics['sources']['first_malicious'], RegExp]>([
    ['override', /set on this incident/i],
    ['restricted', /do not have timeline access/i],
    [null, /mark a timeline event as malicious/i],
  ])('explains the dwell start source %s', async (source, copy) => {
    setPermissions(['incidents:read'])
    mockApi({ '/incidents/i1/metrics': metrics({ sources: { first_malicious: source } }) })
    renderTab(<IncidentMetricsCard incidentId="i1" />)
    expect(await screen.findByText(copy)).toBeInTheDocument()
  })

  it('shows a load error inline', async () => {
    setPermissions(['incidents:read'])
    mockApi()
    jest.spyOn(api, 'get').mockRejectedValue(new ApiError(403, 'Permission denied', { code: 'forbidden' }))
    renderTab(<IncidentMetricsCard incidentId="i1" />)
    expect((await screen.findByRole('alert')).textContent).toMatch(/Could not load the metrics/)
  })

  it('offers "Edit lifecycle times" only with incidents:update, and asks the strip to open', async () => {
    setPermissions(['incidents:read'])
    mockApi({ '/incidents/i1/metrics': metrics() })
    const { unmount } = renderTab(<IncidentMetricsCard incidentId="i1" />)
    await screen.findByTestId('metric-dwell_time')
    expect(screen.queryByRole('button', { name: /edit lifecycle times/i })).toBeNull()
    unmount()

    setPermissions(['incidents:read', 'incidents:update'])
    renderTab(<IncidentMetricsCard incidentId="i1" />)
    const heard = jest.fn()
    window.addEventListener(EDIT_LIFECYCLE_EVENT, heard)
    fireEvent.click(await screen.findByRole('button', { name: /edit lifecycle times/i }))
    window.removeEventListener(EDIT_LIFECYCLE_EVENT, heard)
    expect(heard).toHaveBeenCalledTimes(1)
  })

  it('refetches when the incident version changes and on the refresh button', async () => {
    setPermissions(['incidents:read'])
    const spies = mockApi({ '/incidents/i1/metrics': metrics() })
    const { rerender } = renderTab(<IncidentMetricsCard incidentId="i1" version={1} />)
    await screen.findByTestId('metric-dwell_time')
    expect(spies.get).toHaveBeenCalledTimes(1)
    rerender(<IncidentMetricsCard incidentId="i1" version={2} />)
    await waitFor(() => expect(spies.get).toHaveBeenCalledTimes(2))
    fireEvent.click(screen.getByRole('button', { name: /refresh metrics/i }))
    await waitFor(() => expect(spies.get).toHaveBeenCalledTimes(3))
  })

  it('refetches (debounced) when a timeline event of this incident changes', async () => {
    jest.useFakeTimers({ advanceTimers: true })
    try {
      setPermissions(['incidents:read'])
      const spies = mockApi({ '/incidents/i1/metrics': metrics() })
      renderTab(<IncidentMetricsCard incidentId="i1" version={1} />)
      await screen.findByTestId('metric-dwell_time')
      const change = (incident_id: string) => ({
        incident_id, entity: 'timeline_event', op: 'created', id: 'e1', version: 1, scope: 'timeline', seq: 1,
        at: '2026-01-01T00:00:00Z', data: {},
      }) as never
      act(() => {
        dispatchChange(change('other'))
        dispatchChange(change('i1'))
        dispatchChange(change('i1'))
      })
      expect(spies.get).toHaveBeenCalledTimes(1)
      await act(async () => {
        jest.advanceTimersByTime(1100)
      })
      await waitFor(() => expect(spies.get).toHaveBeenCalledTimes(2))
    } finally {
      jest.useRealTimers()
    }
  })
})
