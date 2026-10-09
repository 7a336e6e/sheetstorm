import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import type { Incident, IncidentSummary } from '@/types'
import { currentSearch, envelope, mockApi, renderTab, resetTabTest, setRole } from '../test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('../test-utils').navigationMock)

let OverviewTab: typeof import('./OverviewTab').OverviewTab
beforeAll(async () => {
  ;({ OverviewTab } = await import('./OverviewTab'))
})

const summary: IncidentSummary = {
  first_event_at: '2026-01-01T00:00:00Z',
  last_event_at: '2026-01-04T00:00:00Z',
  earliest_detection_at: null,
  leads: { total: 5, open: 3, by_outcome: { open: 3, resolved: 2 } },
  hosts_by_triage: { under_analysis: 4, clean: 1 },
  acquisition: { disk_imaged: 0, memory_captured: 1, logs_collected: 0, forensically_sound: 0 },
}

const baseIncident = {
  id: 'i1',
  incident_number: 7,
  title: 'Ransomware at HQ',
  severity: 'high',
  status: 'open',
  phase: 2,
  phase_name: 'Identification',
  tlp: 'amber',
  created_at: '2026-01-01T00:00:00Z',
  executive_summary: '<b>not html</b>\nsecond line',
  version: 2,
} as Incident & { version: number }

const events = [
  { id: 'e-old', incident_id: 'i1', timestamp: '2026-01-01T00:00:00Z', activity: 'oldest event', is_key_event: false, is_ioc: false, created_at: '' },
  { id: 'e-new', incident_id: 'i1', timestamp: '2026-01-04T00:00:00Z', activity: 'newest event', is_key_event: false, is_ioc: false, created_at: '' },
]

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

function render(props: Partial<React.ComponentProps<typeof OverviewTab>> = {}, incident = { ...baseIncident, summary }) {
  return renderTab(
    <OverviewTab
      incident={incident}
      incidentId="i1"
      onViewEvents={() => {}}
      onIncidentUpdated={() => {}}
      {...props}
    />
  )
}

describe('OverviewTab', () => {
  it('renders the questions and metrics slots in place', () => {
    setRole('viewer')
    mockApi()
    const { container } = render({
      questionsSlot: <div>questions panel</div>,
      metricsSlot: <div>metrics card</div>,
    })
    const questions = container.querySelector('[data-slot="overview-questions"]')
    const metrics = container.querySelector('[data-slot="overview-metrics"]')
    expect(questions?.textContent).toBe('questions panel')
    expect(metrics?.textContent).toBe('metrics card')
    // The metrics slot sits directly below the milestone strip.
    expect(metrics?.previousElementSibling?.textContent).toContain('IR Milestones')
  })

  it('renders no slot wrappers when the slots are empty', () => {
    setRole('viewer')
    mockApi()
    const { container } = render()
    expect(container.querySelector('[data-slot]')).toBeNull()
  })

  it('shows server counts for open leads and hosts under analysis, and the lead card opens the lead queue', () => {
    setRole('viewer')
    mockApi()
    render()
    expect(screen.getByText('Hosts under analysis').parentElement?.parentElement?.textContent).toContain('4')
    fireEvent.click(screen.getByRole('button', { name: /open leads: 3/i }))
    expect(currentSearch().get('tab')).toBe('tasks')
    expect(currentSearch().get('tasks.view')).toBe('leads')
  })

  it('uses onOpenLeads when given', () => {
    setRole('viewer')
    mockApi()
    const onOpenLeads = jest.fn()
    render({ onOpenLeads })
    fireEvent.click(screen.getByRole('button', { name: /open leads/i }))
    expect(onOpenLeads).toHaveBeenCalled()
  })

  it('hides the DFIR cards when the summary parts are not readable', () => {
    setRole('viewer')
    mockApi()
    render({}, { ...baseIncident, summary: { ...summary, leads: null, hosts_by_triage: null } })
    expect(screen.queryByText('Open leads')).toBeNull()
    expect(screen.queryByText('Hosts under analysis')).toBeNull()
  })

  it('lists the latest timeline events newest first', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/timeline': envelope(events) })
    render()
    await screen.findByText('newest event')
    const texts = screen.getAllByText(/(newest|oldest) event/).map((n) => n.textContent)
    expect(texts).toEqual(['newest event', 'oldest event'])
  })

  it('renders the narrative as plain text and gates editing', async () => {
    setRole('viewer')
    mockApi()
    const { unmount } = render()
    expect(screen.getByText(/<b>not html<\/b>/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /edit executive summary/i })).toBeNull()
    unmount()

    setRole('responder')
    const api = mockApi()
    render()
    fireEvent.click(screen.getByRole('button', { name: /edit lessons learned/i }))
    fireEvent.change(screen.getByLabelText('Lessons learned', { selector: 'textarea' }), {
      target: { value: 'Patch VPN' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/incidents/i1', { lessons_learned: 'Patch VPN' }, { ifMatch: 2 })
    )
  })
})
