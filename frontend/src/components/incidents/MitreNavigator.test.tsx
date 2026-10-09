import { afterEach, beforeEach, describe, expect, it } from '@jest/globals'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { ApiError } from '@/lib/api'
import api from '@/lib/api'
import { mockApi, renderTab, resetTabTest, setRole } from './test-utils'
import { MitreNavigator } from './MitreNavigator'

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

const formData = {
  tactics: [{ id: 'TA0002', name: 'Execution', slug: 'execution' }],
  technique_by_tactic: { execution: [{ id: 'T1059', name: 'Command and Scripting Interpreter' }] },
  technique_to_tactic: { T1059: 'execution' },
}

const events = [
  {
    id: 'e1',
    incident_id: 'i1',
    timestamp: '2026-01-01T00:00:00Z',
    activity: 'powershell -enc …',
    mitre_tactic: 'Execution',
    mitre_technique: 'T1059',
    is_key_event: false,
    is_ioc: false,
    created_at: '2026-01-01T00:00:00Z',
  },
]

const MUTATION = /add|edit|delete|remove|save|map|assign/i

describe('MitreNavigator', () => {
  it.each(['viewer', 'responder'] as const)('%s gets a read-only matrix (no mutation controls)', async (role) => {
    setRole(role)
    const spies = mockApi({ '/knowledge-base/mitre-attack/form-data': formData })
    renderTab(<MitreNavigator events={events} incidentId="i1" />)

    expect((await screen.findAllByText('T1059')).length).toBeGreaterThan(0)
    const labels = screen.queryAllByRole('button').map((b) => b.textContent ?? '')
    expect(labels.filter((l) => MUTATION.test(l))).toEqual([])
    expect(spies.put).not.toHaveBeenCalled()
    expect(spies.delete).not.toHaveBeenCalled()
  })

  it('shows the load error inline with Retry instead of logging it', async () => {
    setRole('viewer')
    const spies = mockApi()
    let fail = true
    spies.get.mockImplementation((async () => {
      if (fail) throw new ApiError(500, 'boom')
      return formData
    }) as unknown as typeof api.get)
    renderTab(<MitreNavigator events={events} incidentId="i1" />)

    expect(await screen.findByText(/Failed to load MITRE ATT&CK data/)).toBeTruthy()
    fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(screen.getAllByText('T1059').length).toBeGreaterThan(0))
  })
})
