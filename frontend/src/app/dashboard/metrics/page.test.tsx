import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import type { MetricName, MetricStats, OrgMetrics } from '@/types'
import { getCalls, mockApi, renderTab, resetTabTest, setPermissions } from '@/components/incidents/test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('@/components/incidents/test-utils').navigationMock)

let MetricsPage: typeof import('./page').default
beforeAll(async () => {
  ;({ default: MetricsPage } = await import('./page'))
})

const NAMES: MetricName[] = [
  'dwell_time', 'time_to_respond', 'time_to_contain', 'contain_to_eradicate',
  'eradicate_to_recover', 'recover_to_close', 'total_open',
]
const H = 3600

const stats = (over: Partial<Record<MetricName, Partial<MetricStats[MetricName]>>> = {}): MetricStats =>
  Object.fromEntries(
    NAMES.map((n) => [n, { median: null, p90: null, n: 0, anomalies: 0, ...(over[n] ?? {}) }])
  ) as MetricStats

const payload = (over: Partial<OrgMetrics> = {}): OrgMetrics => ({
  range: { from: '2026-07-12T00:00:00+00:00', to: '2026-10-10T00:00:00+00:00', date_field: 'detected_at' },
  group_by: 'none',
  metrics: NAMES,
  min_group_size: 3,
  overall: {
    n: 12,
    metrics: stats({
      time_to_contain: { median: 3 * H, p90: 7 * H, n: 9, anomalies: 1 },
      dwell_time: { median: 40 * H, p90: 90 * H, n: 2 },
    }),
  },
  groups: [],
  ...over,
})

beforeEach(() => {
  resetTabTest()
  setPermissions(['metrics:read'])
})
afterEach(() => resetTabTest())

describe('MetricsPage', () => {
  it('requests the default 90-day window and shows median, p90 and n per metric', async () => {
    const spies = mockApi({ '/metrics/incidents': payload() })
    renderTab(<MetricsPage />)
    await waitFor(() => expect(screen.getByTestId('median-time_to_contain').textContent).toBe('3h'))
    expect(screen.getByTestId('p90-time_to_contain').textContent).toBe('7h')
    expect(screen.getByTestId('overall-count').textContent).toContain('12 incidents in range')
    const url = getCalls(spies.get).find((c) => c.startsWith('/metrics/incidents')) as string
    const params = new URLSearchParams(url.split('?')[1])
    expect(params.get('group_by')).toBe('none')
    expect(params.get('date_field')).toBe('detected_at')
    const days = (Date.parse(params.get('to') as string) - Date.parse(params.get('from') as string)) / 86_400_000
    expect(days).toBe(89)
  })

  it('shows only the count for a metric with too few values, and flags anomalies', async () => {
    mockApi({ '/metrics/incidents': payload() })
    renderTab(<MetricsPage />)
    await screen.findByTestId('median-dwell_time')
    const dwell = screen.getByTestId('metric-row-dwell_time')
    expect(within(dwell).getAllByText('—').length).toBe(2) // median and p90 hidden at n=2
    expect(screen.getByTestId('median-dwell_time').textContent).toBe('—')
    const contain = screen.getByTestId('metric-row-time_to_contain')
    expect(within(contain).getByLabelText('1 out of order')).toBeInTheDocument()
    expect(screen.getByText(/medians need at least 3 values/i)).toBeInTheDocument()
  })

  it('renders one card per group and refetches when the grouping changes', async () => {
    const grouped = payload({
      group_by: 'severity',
      groups: [
        { key: 'critical', n: 7, metrics: stats({ time_to_contain: { median: 2 * H, p90: 5 * H, n: 7 } }) },
        { key: 'low', n: 1, metrics: stats({ time_to_contain: { median: null, p90: null, n: 1 } }) },
      ],
    })
    const spies = mockApi({
      '/metrics/incidents': (endpoint: string) => (endpoint.includes('group_by=severity') ? grouped : payload()),
    })
    renderTab(<MetricsPage />)
    await screen.findByTestId('median-time_to_contain')
    expect(screen.queryAllByTestId('metrics-group')).toHaveLength(0)

    fireEvent.click(screen.getByRole('combobox', { name: 'Group by' }))
    fireEvent.click(await screen.findByRole('option', { name: 'Severity' }))
    await waitFor(() => expect(screen.getAllByTestId('metrics-group')).toHaveLength(2))
    const [critical, low] = screen.getAllByTestId('metrics-group')
    expect(within(critical).getByText('Critical')).toBeInTheDocument()
    expect(within(critical).getByTestId('median-time_to_contain').textContent).toBe('2h')
    expect(within(low).getByTestId('median-time_to_contain').textContent).toBe('—')
    expect(getCalls(spies.get).some((c) => c.includes('group_by=severity'))).toBe(true)
  })

  it('validates a custom range before requesting it', async () => {
    const spies = mockApi({ '/metrics/incidents': payload() })
    renderTab(<MetricsPage />)
    await screen.findByTestId('median-time_to_contain')
    fireEvent.click(screen.getByRole('combobox', { name: 'Period' }))
    fireEvent.click(await screen.findByRole('option', { name: 'Custom range' }))
    const before = getCalls(spies.get).length
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2023-01-01' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-01-01' } })
    expect((await screen.findByRole('alert')).textContent).toMatch(/may not exceed 731 days/)
    expect(getCalls(spies.get).length).toBe(before)
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2025-12-01' } })
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    await waitFor(() => expect(getCalls(spies.get).some((c) => c.includes('from=2025-12-01') && c.includes('to=2026-01-01'))).toBe(true))
  })

  it('shows an empty-period message', async () => {
    mockApi({ '/metrics/incidents': payload({ overall: { n: 0, metrics: stats() } }) })
    renderTab(<MetricsPage />)
    expect((await screen.findByTestId('overall-count')).textContent).toMatch(/Nothing to show/)
  })

  it('shows a load error inline', async () => {
    mockApi()
    jest.spyOn(api, 'get').mockRejectedValue(new ApiError(429, 'Too many requests', { code: 'rate_limited' }))
    renderTab(<MetricsPage />)
    expect((await screen.findByRole('alert')).textContent).toMatch(/Could not load the metrics/)
  })
})
