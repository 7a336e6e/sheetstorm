import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { envelope, getCalls, mockApi, renderTab, resetTabTest, setRole } from './test-utils'

// next/jest does not hoist jest.mock above imports: mock first, then load
// the component dynamically.
// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('./test-utils').navigationMock)

let NetworkIOCsTab: typeof import('./NetworkIOCsTab').NetworkIOCsTab
beforeAll(async () => {
  ;({ NetworkIOCsTab } = await import('./NetworkIOCsTab'))
})

const ioc = {
  id: 'n1',
  incident_id: 'i1',
  dns_ip: '203.0.113.9',
  protocol: 'HTTPS',
  port: 443,
  direction: 'outbound',
  is_malicious: true,
  created_at: '2026-01-01T00:00:00Z',
  version: 2,
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('NetworkIOCsTab', () => {
  it('Viewer sees rows but no mutation controls', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/network-iocs': envelope([ioc]) })
    renderTab(<NetworkIOCsTab incidentId="i1" />)

    expect(await screen.findByText('203.0.113.9')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /add ioc/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /actions for/i })).toBeNull()
  })

  it('queries the paginated endpoint with focus', async () => {
    setRole('viewer')
    const api = mockApi({ '/incidents/i1/network-iocs': envelope([ioc], { total: 120, pages: 3, focus_found: true }) })
    renderTab(<NetworkIOCsTab incidentId="i1" focusRowId="n1" />)

    await screen.findByText('203.0.113.9')
    const first = getCalls(api.get).find((e) => e.startsWith('/incidents/i1/network-iocs'))!
    const q = new URLSearchParams(first.split('?')[1])
    expect(q.get('page')).toBe('1')
    expect(q.get('per_page')).toBe('50')
    expect(q.get('focus')).toBe('n1')
    expect(screen.getByText('1–50 of 120')).toBeTruthy()
    // The host picker is only loaded when the modal opens.
    expect(getCalls(api.get).some((e) => e.startsWith('/incidents/i1/hosts'))).toBe(false)
  })

  it('Responder deletes with a confirm and If-Match', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/network-iocs': envelope([ioc]) })
    renderTab(<NetworkIOCsTab incidentId="i1" />)

    expect(await screen.findByRole('button', { name: /add ioc/i })).toBeTruthy()
    const row = (await screen.findByText('203.0.113.9')).closest('tr')!
    fireEvent.keyDown(row, { key: '.' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByRole('menuitem', { name: 'Edit' })).toBeTruthy()
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Delete' }))

    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/incidents/i1/network-iocs/n1', undefined, { ifMatch: 2 })
    )
  })
})
