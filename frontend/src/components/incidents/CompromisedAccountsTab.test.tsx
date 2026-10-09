import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { envelope, getCalls, mockApi, renderTab, resetTabTest, setRole } from './test-utils'

// next/jest does not hoist jest.mock above imports: mock first, then load
// the component dynamically.
// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('./test-utils').navigationMock)

let CompromisedAccountsTab: typeof import('./CompromisedAccountsTab').CompromisedAccountsTab
beforeAll(async () => {
  ;({ CompromisedAccountsTab } = await import('./CompromisedAccountsTab'))
})

const account = {
  id: 'a1',
  incident_id: 'i1',
  account_name: 'jdoe',
  domain: 'CORP',
  account_type: 'domain',
  datetime_seen: '2026-01-01T00:00:00Z',
  has_password: true,
  password: '********',
  is_privileged: false,
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  version: 5,
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('CompromisedAccountsTab', () => {
  it('Viewer sees rows but no mutation or reveal controls', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/accounts': envelope([account]) })
    renderTab(<CompromisedAccountsTab incidentId="i1" />)

    expect(await screen.findByText('jdoe')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /add account/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /actions for/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /reveal password/i })).toBeNull()
  })

  it('queries the paginated endpoint with focus', async () => {
    setRole('viewer')
    const api = mockApi({ '/incidents/i1/accounts': envelope([account], { focus_found: true }) })
    renderTab(<CompromisedAccountsTab incidentId="i1" focusRowId="a1" />)

    await screen.findByText('jdoe')
    const first = getCalls(api.get).find((e) => e.startsWith('/incidents/i1/accounts'))!
    const q = new URLSearchParams(first.split('?')[1])
    expect(q.get('page')).toBe('1')
    expect(q.get('per_page')).toBe('50')
    expect(q.get('focus')).toBe('a1')
    expect(q.get('reveal')).toBeNull()
  })

  it('reveals a single account through the single-account endpoint', async () => {
    setRole('responder')
    const api = mockApi({
      '/incidents/i1/accounts': envelope([account]),
      '/incidents/i1/accounts/a1': { ...account, password: 'Hunter2!' },
    })
    renderTab(<CompromisedAccountsTab incidentId="i1" />)

    fireEvent.click(await screen.findByRole('button', { name: /reveal password/i }))
    expect(await screen.findByText('Hunter2!')).toBeTruthy()
    expect(getCalls(api.get)).toContain('/incidents/i1/accounts/a1?reveal=true')
    expect(getCalls(api.get).some((e) => e.startsWith('/incidents/i1/accounts?') && e.includes('reveal'))).toBe(false)
  })

  it('Responder deletes with a confirm and If-Match', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/accounts': envelope([account]) })
    renderTab(<CompromisedAccountsTab incidentId="i1" />)

    expect(await screen.findByRole('button', { name: /add account/i })).toBeTruthy()
    const row = (await screen.findByText('jdoe')).closest('tr')!
    fireEvent.keyDown(row, { key: '.' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByRole('menuitem', { name: 'Edit' })).toBeTruthy()
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Delete' }))

    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/incidents/i1/accounts/a1', undefined, { ifMatch: 5 })
    )
  })
})
