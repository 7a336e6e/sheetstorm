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
} from './test-utils'

// next/jest does not hoist jest.mock above imports: mock first, then load
// the component dynamically.
// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('./test-utils').navigationMock)

let HostsTab: typeof import('./HostsTab').HostsTab
beforeAll(async () => {
  ;({ HostsTab } = await import('./HostsTab'))
})

const host = {
  id: 'h1',
  incident_id: 'i1',
  hostname: 'WS-01',
  ip_address: '10.0.0.5',
  containment_status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  version: 3,
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('HostsTab', () => {
  it('Viewer sees rows but no mutation controls', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/hosts': envelope([host]) })
    renderTab(<HostsTab incidentId="i1" />)

    expect(await screen.findByText('WS-01')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /add host/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /actions for/i })).toBeNull()
  })

  it('pages through the paginated endpoint with focus and live entity', async () => {
    setRole('viewer')
    const api = mockApi({ '/incidents/i1/hosts': envelope([host], { total: 120, pages: 3, focus_found: true }) })
    renderTab(<HostsTab incidentId="i1" focusRowId="h1" />)

    await screen.findByText('WS-01')
    const first = getCalls(api.get).find((e) => e.startsWith('/incidents/i1/hosts'))!
    const q = new URLSearchParams(first.split('?')[1])
    expect(q.get('page')).toBe('1')
    expect(q.get('per_page')).toBe('50')
    expect(q.get('focus')).toBe('h1')
    expect(screen.getByText('1–50 of 120')).toBeTruthy()
  })

  it('keeps the search in the URL under the tab key', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/hosts': envelope([host]) })
    renderTab(<HostsTab incidentId="i1" />)
    await screen.findByText('WS-01')

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'WS' } })
    await waitFor(() => expect(currentSearch().get('hosts.q')).toBe('WS'))
  })

  it('Responder deletes with a confirm and If-Match', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/hosts': envelope([host]) })
    renderTab(<HostsTab incidentId="i1" />)

    expect(await screen.findByRole('button', { name: /add host/i })).toBeTruthy()
    const row = screen.getByText('WS-01').closest('tr')!
    fireEvent.keyDown(row, { key: '.' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByRole('menuitem', { name: 'Edit' })).toBeTruthy()
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Delete' }))

    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/incidents/i1/hosts/h1', undefined, { ifMatch: 3 })
    )
  })
})
