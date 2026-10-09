import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { envelope, getCalls, mockApi, renderTab, resetTabTest, setRole } from './test-utils'

// next/jest does not hoist jest.mock above imports: mock first, then load
// the component dynamically.
// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('./test-utils').navigationMock)

let EventsTable: typeof import('./EventsTable').EventsTable
beforeAll(async () => {
  ;({ EventsTable } = await import('./EventsTable'))
})

const event = {
  id: 'e1',
  incident_id: 'i1',
  timestamp: '2026-01-01T10:00:00Z',
  activity: 'Mimikatz executed on WS-01',
  hostname: 'WS-01',
  is_key_event: false,
  is_ioc: false,
  created_at: '2026-01-01T10:00:00Z',
  version: 7,
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('EventsTable', () => {
  it('Viewer sees rows but no create button, row menu or pin toggle', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/timeline': envelope([event]) })
    renderTab(<EventsTable incidentId="i1" />)

    expect(await screen.findByText('Mimikatz executed on WS-01')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /add event/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /actions for/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /pin event/i })).toBeNull()
  })

  it('requests the paginated timeline with focus', async () => {
    setRole('viewer')
    const api = mockApi({ '/incidents/i1/timeline': envelope([event], { focus_found: true }) })
    renderTab(<EventsTable incidentId="i1" focusRowId="e1" />)

    await screen.findByText('Mimikatz executed on WS-01')
    const first = getCalls(api.get).find((e) => e.startsWith('/incidents/i1/timeline'))!
    const q = new URLSearchParams(first.split('?')[1])
    expect(q.get('page')).toBe('1')
    expect(q.get('per_page')).toBe('50')
    expect(q.get('focus')).toBe('e1')
  })

  it('Responder pins with If-Match', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/timeline': envelope([event]) })
    renderTab(<EventsTable incidentId="i1" />)

    fireEvent.click(await screen.findByRole('button', { name: 'Pin event' }))
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/incidents/i1/timeline/e1', { is_key_event: true }, { ifMatch: 7 })
    )
  })

  it('Responder deletes with a confirm and If-Match', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/timeline': envelope([event]) })
    renderTab(<EventsTable incidentId="i1" />)

    expect(await screen.findByRole('button', { name: /add event/i })).toBeTruthy()
    const row = screen.getByText('Mimikatz executed on WS-01').closest('tr')!
    fireEvent.keyDown(row, { key: '.' })
    const menu = await screen.findByRole('menu')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Delete' }))

    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/incidents/i1/timeline/e1', undefined, { ifMatch: 7 })
    )
  })
})
