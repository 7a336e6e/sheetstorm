import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import type { Incident } from '@/types'
import { mockApi, renderTab, resetTabTest, setRole } from '../test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('../test-utils').navigationMock)

const mockAi = { allowed: true, reason: null as string | null }
jest.mock('@/hooks/use-ai-availability', () => ({
  useAiAvailability: () => ({ ...mockAi, loading: false }),
}))

type Mod = typeof import('./IncidentModals')
let EditIncidentModal: Mod['EditIncidentModal']
let UpdateStatusModal: Mod['UpdateStatusModal']
let ReportModal: Mod['ReportModal']
let ImportWizardModal: typeof import('../import-wizard/ImportWizardModal').ImportWizardModal
beforeAll(async () => {
  ;({ EditIncidentModal, UpdateStatusModal, ReportModal } = await import('./IncidentModals'))
  ;({ ImportWizardModal } = await import('../import-wizard/ImportWizardModal'))
})

const incident = {
  id: 'i1',
  incident_number: 7,
  title: 'Ransomware at HQ',
  severity: 'high',
  status: 'open',
  phase: 2,
  phase_name: 'Identification',
  tlp: 'amber',
  created_at: '2026-01-01T00:00:00Z',
  version: 4,
} as Incident & { version: number }

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('incident modals', () => {
  it('Edit sends If-Match with the incident version', async () => {
    setRole('responder')
    const api = mockApi()
    const onUpdated = jest.fn()
    renderTab(
      <EditIncidentModal open onOpenChange={() => {}} incident={incident} incidentId="i1" onUpdated={onUpdated} />
    )
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }))
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/incidents/i1', expect.objectContaining({ title: 'Ransomware at HQ' }), {
        ifMatch: 4,
      })
    )
    expect(onUpdated).toHaveBeenCalled()
  })

  it('Update status sends If-Match with the incident version', async () => {
    setRole('responder')
    const api = mockApi()
    renderTab(
      <UpdateStatusModal
        open
        onOpenChange={() => {}}
        currentStatus="open"
        incidentVersion={4}
        incidentId="i1"
        onUpdated={() => {}}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /contained/i }))
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith('/incidents/i1/status', expect.objectContaining({ status: 'contained' }), {
        ifMatch: 4,
      })
    )
  })

  it('a failed save shows a toast instead of failing silently', async () => {
    setRole('responder')
    const api = mockApi()
    const { ApiError } = await import('@/lib/api')
    api.put.mockImplementation((async () => {
      throw new ApiError(409, 'stale', { code: 'conflict' })
    }) as never)
    const { Toaster } = await import('@/components/ui/toaster')
    renderTab(
      <>
        <EditIncidentModal open onOpenChange={() => {}} incident={incident} incidentId="i1" onUpdated={() => {}} />
        <Toaster />
      </>
    )
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }))
    expect(await screen.findByText("Couldn't update the incident")).toBeTruthy()
  })

  it('Import wizard renders nothing without incidents:update', () => {
    setRole('viewer')
    mockApi()
    renderTab(<ImportWizardModal isOpen onOpenChange={() => {}} incidentId="i1" />)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('Import wizard opens for a Responder', async () => {
    setRole('responder')
    mockApi()
    renderTab(<ImportWizardModal isOpen onOpenChange={() => {}} incidentId="i1" />)
    expect(await screen.findByRole('dialog')).toBeTruthy()
  })

  it('Report stays available when AI is ruled out, and says why', async () => {
    setRole('responder')
    mockApi()
    mockAi.allowed = false
    mockAi.reason = 'AI is disabled for TLP:RED incidents by your organization\'s data egress policy.'
    try {
      renderTab(<ReportModal open onOpenChange={() => {}} incidentId="i1" incidentNumber={7} />)
      expect(screen.getByRole('status').textContent).toContain('TLP:RED')
      expect((screen.getByRole('button', { name: /generate pdf/i }) as HTMLButtonElement).disabled).toBe(false)
    } finally {
      mockAi.allowed = true
      mockAi.reason = null
    }
  })
})
