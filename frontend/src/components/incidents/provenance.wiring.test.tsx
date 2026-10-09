import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { act } from 'react'
import { provenanceApi } from '@/lib/endpoints/provenance'
import { useTimePrefStore } from '@/lib/store'
import { envelope, mockApi, renderTab, resetTabTest, setPermissions, setRole } from './test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('./test-utils').navigationMock)

let EventsTable: typeof import('./EventsTable').EventsTable
let NetworkIOCsTab: typeof import('./NetworkIOCsTab').NetworkIOCsTab
let HostsTab: typeof import('./HostsTab').HostsTab
beforeAll(async () => {
  ;({ EventsTable } = await import('./EventsTable'))
  ;({ NetworkIOCsTab } = await import('./NetworkIOCsTab'))
  ;({ HostsTab } = await import('./HostsTab'))
})

beforeEach(() => {
  resetTabTest()
  act(() => useTimePrefStore.setState({ mode: 'utc' } as never))
})
afterEach(() => resetTabTest())

const base = { incident_id: 'i1', is_key_event: false, is_ioc: false, created_at: '2026-10-01T00:00:00Z', version: 3 }
const event = (over: Record<string, unknown>) => ({
  ...base, id: 'e1', activity: 'Logon from 10.0.0.9', timestamp: '2026-10-01T12:00:00Z', provenance_level: 'none', ...over,
})

describe('EventsTable provenance', () => {
  it('shows the level badge per row', async () => {
    setRole('viewer')
    mockApi({
      '/incidents/i1/timeline': envelope([
        event({ id: 'e1', provenance_level: 'none' }),
        event({ id: 'e2', activity: 'second', provenance_level: 'verified' }),
      ]),
    })
    renderTab(<EventsTable incidentId="i1" />)
    expect(await screen.findByText('Logon from 10.0.0.9')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'No provenance' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Verified provenance' })).toBeTruthy()
  })

  it('creates an event from a raw timestamp without sending a timestamp', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/timeline': envelope([]) })
    jest.spyOn(provenanceApi, 'normalizePreview').mockResolvedValue({
      utc: '2026-10-01T12:00:00+00:00', skew_applied: 0, timezone_used: 'UTC', offset_seconds: 0,
    })
    renderTab(<EventsTable incidentId="i1" />)
    fireEvent.click(await screen.findByRole('button', { name: /add event/i }))
    const dialog = await screen.findByRole('dialog')

    fireEvent.change(within(dialog).getAllByRole('textbox')[0], { target: { value: 'Service installed' } })
    fireEvent.click(within(dialog).getByRole('button', { name: /provenance/i }))
    fireEvent.change(within(dialog).getByLabelText('Raw timestamp'), { target: { value: '2026-10-01 12:00:00' } })
    fireEvent.change(within(dialog).getByLabelText('Source time zone'), { target: { value: 'UTC' } })
    fireEvent.change(within(dialog).getByLabelText('Record reference'), { target: { value: 'System.evtx#7045' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    const [url, payload] = api.post.mock.calls[0] as [string, Record<string, unknown>]
    expect(url).toBe('/incidents/i1/timeline')
    expect(payload).toMatchObject({
      activity: 'Service installed',
      raw_timestamp: '2026-10-01 12:00:00',
      source_timezone: 'UTC',
      source_record_ref: 'System.evtx#7045',
    })
    expect(payload.timestamp).toBeUndefined()
  })

  it('does not submit without a timestamp or a raw timestamp', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/timeline': envelope([]) })
    renderTab(<EventsTable incidentId="i1" />)
    fireEvent.click(await screen.findByRole('button', { name: /add event/i }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getAllByRole('textbox')[0], { target: { value: 'No time' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))
    await act(async () => {})
    expect(api.post).not.toHaveBeenCalled()
  })

  it('editing an unrelated field sends no provenance keys', async () => {
    setRole('responder')
    const api = mockApi({
      '/incidents/i1/timeline': envelope([event({
        provenance_level: 'partial', raw_timestamp: '2026-10-01 14:00:00', source_timezone: 'Europe/Berlin',
        timestamp_derivation: 'computed', clock_skew_applied_seconds: 300,
      })]),
    })
    renderTab(<EventsTable incidentId="i1" />)
    const row = (await screen.findByText('Logon from 10.0.0.9')).closest('tr')!
    fireEvent.keyDown(row, { key: '.' })
    fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Edit' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getAllByRole('textbox')[0], { target: { value: 'Logon from 10.0.0.10' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const [url, payload, opts] = api.put.mock.calls[0] as [string, Record<string, unknown>, { ifMatch: number }]
    expect(url).toBe('/incidents/i1/timeline/e1')
    expect(opts).toEqual({ ifMatch: 3 })
    expect(payload.activity).toBe('Logon from 10.0.0.10')
    for (const key of ['raw_timestamp', 'source_timezone', 'source_record_ref', 'timestamp_derivation', 'fold']) {
      expect(key in payload).toBe(false)
    }
  })

  it('offers Verify provenance to a second analyst only, and calls the verify endpoint', async () => {
    setRole('responder') // user id u1
    const verify = jest.spyOn(provenanceApi, 'verify').mockResolvedValue({})
    mockApi({
      '/incidents/i1/timeline': envelope([
        event({ id: 'mine', activity: 'mine', provenance_level: 'partial', creator: { id: 'u1', name: 'U' } }),
        event({ id: 'theirs', activity: 'theirs', provenance_level: 'partial', creator: { id: 'u2', name: 'V' } }),
        event({ id: 'plain', activity: 'plain', provenance_level: 'none', creator: { id: 'u2', name: 'V' } }),
      ]),
    })
    renderTab(<EventsTable incidentId="i1" />)
    await screen.findByText('theirs')

    const open = async (name: string) => {
      fireEvent.keyDown(screen.getByText(name).closest('tr')!, { key: '.' })
      return within(await screen.findByRole('menu')).queryAllByRole('menuitem').map((i) => i.textContent)
    }
    expect(await open('mine')).not.toContain('Verify provenance')
    fireEvent.keyDown(document.body, { key: 'Escape' })
    expect(await open('plain')).not.toContain('Verify provenance')
    fireEvent.keyDown(document.body, { key: 'Escape' })
    expect(await open('theirs')).toContain('Verify provenance')
    fireEvent.click(screen.getByRole('menuitem', { name: 'Verify provenance' }))
    await waitFor(() => expect(verify).toHaveBeenCalledWith('i1', 'timeline_event', 'theirs', 3))
  })

  it('a Viewer has no verify action', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/timeline': envelope([event({ provenance_level: 'partial', creator: { id: 'u2', name: 'V' } })]) })
    renderTab(<EventsTable incidentId="i1" />)
    await screen.findByText('Logon from 10.0.0.9')
    expect(screen.queryByRole('button', { name: /actions for/i })).toBeNull()
  })
})

describe('NetworkIOCsTab provenance', () => {
  it('shows the badge column and sends only the changed provenance fields', async () => {
    setRole('responder')
    const api = mockApi({
      '/incidents/i1/network-iocs': envelope([{
        ...base, id: 'n1', dns_ip: '203.0.113.9', direction: 'outbound', is_malicious: true,
        provenance_level: 'full', source_record_ref: 'fw.log:4411', raw_timestamp: '2026-10-01T12:00:00+02:00',
        source_timezone: 'UTC',
      }]),
    })
    renderTab(<NetworkIOCsTab incidentId="i1" />)
    expect(await screen.findByRole('button', { name: 'Full provenance' })).toBeTruthy()
    const row = screen.getByText('203.0.113.9').closest('tr')!
    fireEvent.keyDown(row, { key: '.' })
    fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Edit' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('button', { name: /provenance/i }).getAttribute('aria-expanded')).toBe('true')
    fireEvent.change(within(dialog).getByLabelText('Record reference'), { target: { value: 'fw.log:4412' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save Changes' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const payload = api.put.mock.calls[0][1] as Record<string, unknown>
    expect(payload.source_record_ref).toBe('fw.log:4412')
    expect('raw_timestamp' in payload).toBe(false)
    expect('source_timezone' in payload).toBe(false)
  })
})

describe('HostsTab clock skew', () => {
  const host = {
    ...base, id: 'h1', hostname: 'WS-01', containment_status: 'active', triage_status: 'under_analysis',
    clock_skew_seconds: 300, clock_skew_basis: 'NTP offset', timezone: 'Europe/Berlin',
  }

  it('shows the skew column and opens the editor from the row menu', async () => {
    setRole('responder')
    mockApi({ '/incidents/i1/hosts': envelope([host]) })
    renderTab(<HostsTab incidentId="i1" />)
    expect(await screen.findByText(/\+5m 0s · Europe\/Berlin/)).toBeTruthy()
    fireEvent.keyDown(screen.getByText('WS-01').closest('tr')!, { key: '.' })
    fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Clock skew…' }))
    expect(await screen.findByText('Clock skew: WS-01')).toBeTruthy()
    expect((screen.getByLabelText('Minutes') as HTMLInputElement).value).toBe('5')
  })

  it('hides the editor entry without hosts:update', async () => {
    setPermissions(['incidents:read', 'hosts:read'])
    mockApi({ '/incidents/i1/hosts': envelope([host]) })
    renderTab(<HostsTab incidentId="i1" />)
    await screen.findByText('WS-01')
    expect(screen.queryByRole('button', { name: /actions for/i })).toBeNull()
  })
})
