import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { screen, waitFor } from '@testing-library/react'
import type { Incident } from '@/types'
import { mockApi, renderTab, resetTabTest, setPermissions } from '@/components/incidents/test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('@/components/incidents/test-utils').navigationMock)

let OverviewPanel: typeof import('./panels').OverviewPanel
beforeAll(async () => {
  ;({ OverviewPanel } = await import('./panels'))
})

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

const incident = {
  id: 'i1', incident_number: 7, title: 'Ransomware', severity: 'high', status: 'open', phase: 2,
  phase_name: 'Identification', tlp: 'amber', created_at: '2026-01-01T00:00:00Z', version: 6,
} as Incident & { version: number }

describe('OverviewPanel', () => {
  it('fills the Overview metrics slot with the incident metrics card, keyed on the incident version', async () => {
    setPermissions(['incidents:read', 'timeline:read', 'tasks:read'])
    const spies = mockApi({
      '/incidents/i1/metrics': {
        incident_id: 'i1', timestamps: {}, anomalies: [], sources: { first_malicious: null },
        durations: { dwell_time: 7200, time_to_respond: null, time_to_contain: null, contain_to_eradicate: null,
          eradicate_to_recover: null, recover_to_close: null, total_open: 86400 },
      },
    })
    renderTab(
      <OverviewPanel incident={incident} incidentId="i1" onNavigate={() => {}} onIncidentChanged={() => {}} />
    )
    const slot = await waitFor(() => {
      const el = document.querySelector('[data-slot="overview-metrics"]')
      if (!el) throw new Error('metrics slot missing')
      return el as HTMLElement
    })
    expect(slot.textContent).toContain('Response metrics')
    await waitFor(() => expect(screen.getByTestId('metric-dwell_time').textContent).toContain('2h'))
    expect(spies.get).toHaveBeenCalledWith('/incidents/i1/metrics', expect.anything())
    // The milestone strip (with its editor) renders right above the slot.
    expect(screen.getByLabelText('IR milestones')).toBeInTheDocument()
  })
})
