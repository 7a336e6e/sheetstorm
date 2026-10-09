import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { mockApi, renderTab, resetTabTest, setRole } from './test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('./test-utils').navigationMock)

let AssignmentsPanel: typeof import('./AssignmentsPanel').AssignmentsPanel
let LeadResponderSelector: typeof import('./detail/LeadResponderSelector').LeadResponderSelector
beforeAll(async () => {
  ;({ AssignmentsPanel } = await import('./AssignmentsPanel'))
  ;({ LeadResponderSelector } = await import('./detail/LeadResponderSelector'))
})

const assignment = {
  id: 'a1',
  incident_id: 'i1',
  user: { id: 'u2', name: 'Dana Analyst', email: 'dana@example.test' },
  role: 'Analyst',
  assigned_by: null,
  assigned_at: null,
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('AssignmentsPanel', () => {
  it('Viewer sees personnel but cannot assign or remove', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/assignments': { items: [assignment] } })
    renderTab(<AssignmentsPanel incidentId="i1" />)

    expect(await screen.findByText('Dana Analyst')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /assign/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /remove/i })).toBeNull()
  })

  it('Responder removal asks for confirmation first', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/assignments': { items: [assignment] } })
    renderTab(<AssignmentsPanel incidentId="i1" />)

    fireEvent.click(await screen.findByRole('button', { name: /remove dana analyst/i }))
    const dialog = await screen.findByRole('dialog')
    expect(api.delete).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/incidents/i1/assignments/a1'))
  })

  it('loads the full list (no per_page=200 page-1 cap on users)', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/assignments': { items: [] } })
    renderTab(<AssignmentsPanel incidentId="i1" />)
    await screen.findByText('No personnel assigned')
    const calls = api.get.mock.calls.map((c) => String(c[0]))
    expect(calls.some((c) => c.startsWith('/users'))).toBe(false)
  })
})

describe('LeadResponderSelector', () => {
  it('is read-only for a Viewer', async () => {
    setRole('viewer')
    mockApi()
    renderTab(<LeadResponderSelector incidentId="i1" currentLead={{ id: 'u1', name: 'Lee Lead' }} onUpdated={() => {}} />)
    expect(screen.getByText('Lee Lead')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('opens a user picker for a Responder', async () => {
    setRole('responder')
    mockApi()
    renderTab(<LeadResponderSelector incidentId="i1" currentLead={{ id: 'u1', name: 'Lee Lead' }} onUpdated={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /lead responder/i }))
    expect(await screen.findByRole('combobox', { name: 'Lead responder' })).toBeTruthy()
  })
})
