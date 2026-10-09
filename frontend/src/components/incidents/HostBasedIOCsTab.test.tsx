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

let HostBasedIOCsTab: typeof import('./HostBasedIOCsTab').HostBasedIOCsTab
beforeAll(async () => {
  ;({ HostBasedIOCsTab } = await import('./HostBasedIOCsTab'))
})

const row = {
  id: 'x1',
  incident_id: 'i1',
  artifact_type: 'registry',
  artifact_value: 'HKLM\\Run\\evil',
  host: 'WS-01',
  is_malicious: true,
  remediated: false,
  created_at: '2026-01-01T00:00:00Z',
  version: 3,
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('HostBasedIOCsTab', () => {
  it('Viewer sees rows but no mutation controls', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/host-iocs': envelope([row]) })
    renderTab(<HostBasedIOCsTab incidentId="i1" />)

    expect(await screen.findByText('HKLM\\Run\\evil')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /add ioc/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /actions for/i })).toBeNull()
  })

  it('pages through the paginated endpoint with focus and live entity', async () => {
    setRole('viewer')
    const api = mockApi({ '/incidents/i1/host-iocs': envelope([row], { total: 120, pages: 3, focus_found: true }) })
    renderTab(<HostBasedIOCsTab incidentId="i1" focusRowId="x1" />)

    await screen.findByText('HKLM\\Run\\evil')
    const first = getCalls(api.get).find((e) => e.startsWith('/incidents/i1/host-iocs'))!
    const q = new URLSearchParams(first.split('?')[1])
    expect(q.get('page')).toBe('1')
    expect(q.get('per_page')).toBe('50')
    expect(q.get('focus')).toBe('x1')
    expect(screen.getByText('1–50 of 120')).toBeTruthy()
  })

  it('keeps the search in the URL under the tab key', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/host-iocs': envelope([row]) })
    renderTab(<HostBasedIOCsTab incidentId="i1" />)
    await screen.findByText('HKLM\\Run\\evil')

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'WS' } })
    await waitFor(() => expect(currentSearch().get('host-iocs.q')).toBe('WS'))
  })

  it('Responder deletes with a confirm and If-Match', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/host-iocs': envelope([row]) })
    renderTab(<HostBasedIOCsTab incidentId="i1" />)

    expect(await screen.findByRole('button', { name: /add ioc/i })).toBeTruthy()
    const tr = screen.getByText('HKLM\\Run\\evil').closest('tr')!
    fireEvent.keyDown(tr, { key: '.' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByRole('menuitem', { name: 'Edit' })).toBeTruthy()
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Delete' }))

    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/incidents/i1/host-iocs/x1', undefined, { ifMatch: 3 })
    )
  })
})
