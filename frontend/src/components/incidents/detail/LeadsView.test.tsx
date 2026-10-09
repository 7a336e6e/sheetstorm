import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import {
  currentSearch,
  envelope,
  getCalls,
  mockApi,
  renderTab,
  resetTabTest,
  setRole,
  setSearch,
} from '../test-utils'

// next/jest does not hoist jest.mock above imports: mock first, then load
// the components dynamically.
// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('../test-utils').navigationMock)

let mod: typeof import('./LeadsView')
let TasksTab: typeof import('./TasksTab').TasksTab
beforeAll(async () => {
  mod = await import('./LeadsView')
  ;({ TasksTab } = await import('./TasksTab'))
})

const lead = {
  id: 't1',
  incident_id: 'i1',
  title: 'RDP from jump host',
  status: 'in_progress',
  priority: 'high',
  task_type: 'investigative_lead',
  lead_outcome: null,
  investigation_direction: 'Prove or disprove lateral movement from JUMP-01',
  evidence_refs: [{ evidence_type: 'host', evidence_id: 'h1' }],
  evidence: [
    { evidence_type: 'host', evidence_id: 'h1', label: 'WS-01', missing: false },
    { evidence_type: 'malware', evidence_id: 'm1', label: null, missing: true },
  ],
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-02T00:00:00Z',
  version: 7,
}

const counts = { open: 2, false_positive: 1, confirmed_malicious: 0, inconclusive: 0, resolved: 3 }

function tasksRoute(endpoint: string) {
  const q = new URLSearchParams(endpoint.split('?')[1] ?? '')
  if (q.get('lead_counts') === 'true') return envelope([], { lead_counts: counts })
  return envelope([lead])
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('taskEvidence / evidenceLabel', () => {
  it('prefers server labels, falls back to legacy linked_entities labels', () => {
    expect(mod.taskEvidence(lead as never).map(mod.evidenceLabel)).toEqual(['WS-01', 'Malware (deleted)'])
    const live = {
      evidence_refs: [{ evidence_type: 'host_indicator', evidence_id: 'abcdef123456' }],
      extra_data: { linked_entities: [{ type: 'host_indicator', id: 'abcdef123456', label: 'file: x.exe' }] },
    }
    expect(mod.taskEvidence(live as never)).toEqual([
      { evidence_type: 'host_ioc', evidence_id: 'abcdef123456', label: 'file: x.exe', missing: false },
    ])
    const legacyOnly = { extra_data: { linked_entities: [{ type: 'account', id: 'a1', label: 'CORP\\bob' }] } }
    expect(mod.taskEvidence(legacyOnly as never)[0].evidence_type).toBe('account')
    expect(
      mod.evidenceLabel({ evidence_type: 'host', evidence_id: '1234567890', label: null, missing: false })
    ).toBe('Host 12345678')
    expect(
      mod.evidenceLabel({ evidence_type: 'artifact', evidence_id: 'x', label: null, missing: false, restricted: true })
    ).toBe('Artifact (restricted)')
  })
})

describe('LeadsView', () => {
  it('lists open leads by default with outcome counts', async () => {
    setRole('viewer')
    const api = mockApi({ '/incidents/i1/tasks': tasksRoute })
    renderTab(<mod.LeadsView incidentId="i1" />)

    expect(await screen.findByText('RDP from jump host')).toBeTruthy()
    const list = getCalls(api.get).find((e) => e.includes('task_type=investigative_lead') && !e.includes('lead_counts'))!
    const q = new URLSearchParams(list.split('?')[1])
    expect(q.get('lead_outcome')).toBe('open')
    expect(q.get('include_comments')).toBe('false')
    expect(q.get('sort')).toBe('-updated_at')

    const group = await screen.findByRole('group', { name: 'Leads by outcome' })
    expect(within(group).getByRole('button', { name: /Resolved\s*3/ })).toBeTruthy()
    // Viewer: a read-only outcome badge, no inline select.
    expect(screen.queryByRole('combobox', { name: /Outcome of/ })).toBeNull()
    expect(screen.getAllByText('Open').length).toBeGreaterThan(0)
  })

  it('evidence chips open the owning tab on the linked row', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/tasks': tasksRoute })
    renderTab(<mod.LeadsView incidentId="i1" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open WS-01' }))
    await waitFor(() => expect(currentSearch().get('tab')).toBe('hosts'))
    expect(currentSearch().get('row')).toBe('h1')
    // Deleted evidence is not clickable.
    expect(screen.queryByRole('button', { name: /Malware \(deleted\)/ })).toBeNull()
    expect(screen.getByText('Malware (deleted)')).toBeTruthy()
  })

  it('Responder sets the outcome inline with If-Match', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/tasks': tasksRoute })
    renderTab(<mod.LeadsView incidentId="i1" />)
    const select = await screen.findByRole('combobox', { name: 'Outcome of RDP from jump host' })
    fireEvent.click(select)
    fireEvent.click(await screen.findByRole('option', { name: 'Confirmed malicious' }))
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/incidents/i1/tasks/t1', { lead_outcome: 'confirmed_malicious' }, { ifMatch: 7 })
    )
  })
})

describe('TasksTab leads integration', () => {
  it('switches to the lead queue through the URL', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/tasks': tasksRoute })
    renderTab(<TasksTab incidentId="i1" />)
    await screen.findByText('RDP from jump host')
    fireEvent.click(screen.getByRole('button', { name: 'Leads' }))
    await waitFor(() => expect(currentSearch().get('tasks.view')).toBe('leads'))
    expect(await screen.findByRole('group', { name: 'Leads by outcome' })).toBeTruthy()
    expect(screen.getByRole('searchbox')).toHaveProperty('placeholder', 'Search leads...')
  })

  it('shows type, outcome and resolved evidence on task rows', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/tasks': tasksRoute })
    renderTab(<TasksTab incidentId="i1" />)
    await screen.findByText('RDP from jump host')
    expect(screen.getByText('Investigative Lead')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Open WS-01' })).toBeTruthy()
  })

  it('saving a task sends evidence_refs and never extra_data.linked_entities', async () => {
    setRole('responder')
    setSearch('')
    const api = mockApi({ '/incidents/i1/tasks': tasksRoute })
    renderTab(<TasksTab incidentId="i1" />)
    await screen.findByText('RDP from jump host')
    const row = screen.getByText('RDP from jump host').closest('tr')!
    fireEvent.keyDown(row, { key: '.' })
    fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Edit' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('Investigation Direction')).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Update Task' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const [url, body, opts] = api.put.mock.calls[0] as [string, Record<string, unknown>, unknown]
    expect(url).toBe('/incidents/i1/tasks/t1')
    expect(opts).toEqual({ ifMatch: 7 })
    expect(body.evidence_refs).toEqual([
      { evidence_type: 'host', evidence_id: 'h1' },
      { evidence_type: 'malware', evidence_id: 'm1' },
    ])
    expect(body).not.toHaveProperty('extra_data')
    expect(body.investigation_direction).toBe('Prove or disprove lateral movement from JUMP-01')
  })
})
