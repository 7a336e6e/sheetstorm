import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { envelope, getCalls, mockApi, renderTab, resetTabTest, setRole, setSearch } from './test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('./test-utils').navigationMock)

let HostsTab: typeof import('./HostsTab').HostsTab
beforeAll(async () => {
  ;({ HostsTab } = await import('./HostsTab'))
})

const host = (over: Record<string, unknown>) => ({
  incident_id: 'i1',
  containment_status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  version: 2,
  ...over,
})

const hosts = [
  host({ id: 'h1', hostname: 'WS-01', triage_status: 'suspicious', acquisition_status: { memory_captured: true } }),
  host({ id: 'h2', hostname: 'DC-01', triage_status: 'compromised',
    acquisition_status: { disk_imaged: true, memory_captured: true, forensically_sound: true } }),
]

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('HostsTab triage and acquisition', () => {
  it('shows triage verdicts and acquisition chips; Viewer cannot select rows', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/hosts': envelope(hosts) })
    renderTab(<HostsTab incidentId="i1" />)

    expect(await screen.findByText('WS-01')).toBeTruthy()
    expect(screen.getByText('Suspicious')).toBeTruthy()
    expect(screen.getAllByLabelText('Memory captured: yes')).toHaveLength(2)
    expect(screen.getAllByLabelText('Disk imaged: no')).toHaveLength(1)
    expect(screen.queryByRole('checkbox', { name: 'Select row' })).toBeNull()
  })

  it('sends triage / acquisition filters to the server', async () => {
    setRole('viewer')
    setSearch('hosts.f.triage_status=under_analysis&hosts.f.acquisition=memory_captured,!disk_imaged')
    const api = mockApi({ '/incidents/i1/hosts': envelope(hosts) })
    renderTab(<HostsTab incidentId="i1" />)
    await screen.findByText('WS-01')
    const call = getCalls(api.get).find((e) => e.startsWith('/incidents/i1/hosts?'))!
    const q = new URLSearchParams(call.split('?')[1])
    expect(q.get('triage_status')).toBe('under_analysis')
    expect(q.get('acquisition')).toBe('memory_captured,!disk_imaged')
  })

  it('Responder bulk-sets triage on the selected hosts', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/hosts': envelope(hosts) })
    api.patch.mockImplementation((async () => ({ updated: 2, items: [] })) as never)
    renderTab(<HostsTab incidentId="i1" />)
    await screen.findByText('WS-01')

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all rows on this page' }))
    const trigger = await screen.findByRole('combobox', { name: 'Set triage for selected hosts' })
    fireEvent.click(trigger)
    fireEvent.click(await screen.findByRole('option', { name: 'Clean' }))
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith('/incidents/i1/hosts/bulk', { host_ids: ['h1', 'h2'], triage_status: 'clean' })
    )
  })

  it('the edit modal saves acquisition_status with If-Match', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/hosts': envelope(hosts) })
    renderTab(<HostsTab incidentId="i1" />)
    const row = (await screen.findByText('WS-01')).closest('tr')!
    fireEvent.keyDown(row, { key: '.' })
    fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Edit' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('switch', { name: 'Disk imaged' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save Changes' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const [url, body, opts] = api.put.mock.calls[0] as [string, Record<string, unknown>, unknown]
    expect(url).toBe('/incidents/i1/hosts/h1')
    expect(opts).toEqual({ ifMatch: 2 })
    expect(body.acquisition_status).toEqual({
      disk_imaged: true, memory_captured: true, logs_collected: false, forensically_sound: false, acquired_at: null,
    })
  })
})
