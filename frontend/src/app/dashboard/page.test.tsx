import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen } from '@testing-library/react'
import type { DashboardStats } from '@/types'
import { getCalls, mockApi, renderTab, resetTabTest, setRole } from '@/components/incidents/test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('@/components/incidents/test-utils').navigationMock)

let DashboardPage: typeof import('./page').default
beforeAll(async () => {
  ;({ default: DashboardPage } = await import('./page'))
})

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

const stats: DashboardStats = {
  incidents: {
    total: 1234, active: 1200, closed: 34, critical: 77, created_7d: 12, created_30d: 43,
    by_severity: { critical: 77, high: 100, medium: 1000, low: 57 },
    by_status: { open: 1200, closed: 34 }, by_phase_open: { '2': 1200 }, by_tlp: { amber: 1234 },
  },
  mitre: {
    events_total: 5000, events_mapped: 4000,
    tactics: [{ tactic: 'execution', count: 4000, techniques: { T1059: 3999, T1047: 1 } }],
  },
  dfir: { open_leads: 9, hosts_by_triage: { under_analysis: 31 } },
}

describe('dashboard page', () => {
  it('renders server aggregates from one request, without per-incident timeline calls', async () => {
    setRole('viewer')
    const api = mockApi({ '/dashboard/stats': stats })
    renderTab(<DashboardPage />)
    expect((await screen.findAllByText('1234')).length).toBeGreaterThan(0)
    expect(screen.getByText('Open leads').closest('div')?.parentElement?.textContent).toContain('9')
    expect(screen.getByText('4000/5000 events mapped (80%)')).toBeTruthy()
    const calls = getCalls(api.get)
    expect(calls.filter((c) => c.startsWith('/dashboard/stats'))).toHaveLength(1)
    expect(calls.some((c) => c.includes('/timeline'))).toBe(false)
  })

  it('expands an aggregate tactic to techniques only', async () => {
    setRole('viewer')
    mockApi({ '/dashboard/stats': stats })
    renderTab(<DashboardPage />)
    fireEvent.click(await screen.findByRole('button', { name: /execution/i }))
    expect(screen.getByText('T1047 x1')).toBeTruthy()
  })
})
