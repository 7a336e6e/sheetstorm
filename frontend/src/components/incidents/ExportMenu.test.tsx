import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import api from '@/lib/api'
import { mockApi, renderTab, resetTabTest, setPermissions, setSearch } from './test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('./test-utils').navigationMock)

let ExportMenu: typeof import('./ExportMenu').ExportMenu
beforeAll(async () => {
  ;({ ExportMenu } = await import('./ExportMenu'))
})

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

const READ = ['incidents:read', 'hosts:read', 'timeline:read', 'network_iocs:read', 'tasks:read']

function openMenu() {
  fireEvent.keyDown(screen.getByRole('button', { name: 'Export' }), { key: 'Enter' })
  return screen.getByRole('menu')
}

function downloaded() {
  return jest.spyOn(api, 'downloadTo').mockResolvedValue('file.csv')
}

function parsed(call: unknown[]) {
  const [endpoint, opts] = call as [string, { fallbackName: string }]
  const [path, qs = ''] = endpoint.split('?')
  return { path, params: Object.fromEntries(new URLSearchParams(qs)), fallbackName: opts.fallbackName }
}

describe('ExportMenu', () => {
  it('is hidden without incidents:export (C24), whatever else the user can read', () => {
    setPermissions(READ)
    renderTab(<ExportMenu incidentId="i1" activeTab="hosts" tlp="amber" />)
    expect(screen.queryByRole('button', { name: 'Export' })).toBeNull()
  })

  it("exports the active tab's rows with the URL's search, sort and filters", async () => {
    setPermissions([...READ, 'incidents:export'])
    setSearch('tab=hosts&hosts.q=ws&hosts.sort=-first_seen&hosts.f.triage_status=compromised&hosts.page=3')
    const spy = downloaded()
    renderTab(<ExportMenu incidentId="i1" incidentNumber={7} tlp="amber" activeTab="hosts" />)

    const menu = openMenu()
    expect(within(menu).getByText('Exports are marked TLP:AMBER')).toBeTruthy()
    expect(within(menu).getByText(/current tab, 3 filters applied/)).toBeTruthy()
    fireEvent.click(within(menu).getByRole('menuitem', { name: /CSV: Hosts/ }))

    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    const call = parsed(spy.mock.calls[0])
    expect(call.path).toBe('/incidents/i1/export/hosts')
    expect(call.params).toEqual({ triage_status: 'compromised', q: 'ws', sort: '-first_seen' })
    expect(call.fallbackName).toBe('incident-7-hosts.csv')
  })

  it('offers a defanged CSV on IOC tabs only', () => {
    setPermissions([...READ, 'incidents:export'])
    const { unmount } = renderTab(<ExportMenu incidentId="i1" activeTab="network" />)
    expect(within(openMenu()).getByRole('menuitem', { name: /\(defanged\)/ })).toBeTruthy()
    unmount()
    renderTab(<ExportMenu incidentId="i1" activeTab="hosts" />)
    expect(within(openMenu()).queryByRole('menuitem', { name: /\(defanged\)/ })).toBeNull()
  })

  it('sends defang=true for the defanged variant', async () => {
    setPermissions([...READ, 'incidents:export'])
    setSearch('tab=network&network.f.direction=outbound')
    const spy = downloaded()
    renderTab(<ExportMenu incidentId="i1" activeTab="network" />)
    fireEvent.click(within(openMenu()).getByRole('menuitem', { name: /Network IOCs \(defanged\)/ }))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    expect(parsed(spy.mock.calls[0]).params).toEqual({ direction: 'outbound', defang: 'true' })
  })

  it('tabs without an export (Overview, Playbook, ...) offer STIX and the all-rows CSVs only', async () => {
    setPermissions([...READ, 'incidents:export'])
    const spy = downloaded()
    renderTab(<ExportMenu incidentId="i1" incidentNumber={7} activeTab="overview" />)
    const menu = openMenu()
    expect(within(menu).queryByText(/current tab/)).toBeNull()
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'STIX 2.1 bundle' }))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('/incidents/i1/export/stix', { fallbackName: 'incident-7-stix.json' }))
  })

  it("lists a CSV only for entities the user can read (the API requires both)", () => {
    setPermissions(['incidents:read', 'incidents:export', 'hosts:read'])
    renderTab(<ExportMenu incidentId="i1" activeTab="tasks" />)
    const menu = openMenu()
    expect(within(menu).getByRole('menuitem', { name: 'Hosts' })).toBeTruthy()
    expect(within(menu).queryByRole('menuitem', { name: 'Tasks' })).toBeNull()
    expect(within(menu).queryByRole('menuitem', { name: /CSV: Tasks/ })).toBeNull()
    expect(within(menu).getByRole('menuitem', { name: 'STIX 2.1 bundle' })).toBeTruthy()
  })

  it('all-rows CSV ignores the active tab filters', async () => {
    setPermissions([...READ, 'incidents:export'])
    setSearch('tab=hosts&hosts.q=ws')
    const spy = downloaded()
    renderTab(<ExportMenu incidentId="i1" activeTab="hosts" />)
    fireEvent.click(within(openMenu()).getByRole('menuitem', { name: 'Events' }))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    expect(parsed(spy.mock.calls[0])).toMatchObject({ path: '/incidents/i1/export/timeline', params: {} })
  })

  it('a refused export (403) is reported, not swallowed', async () => {
    setPermissions([...READ, 'incidents:export'])
    jest.spyOn(api, 'downloadTo').mockRejectedValue(new Error('Permission denied. Required: incidents:export'))
    renderTab(<ExportMenu incidentId="i1" activeTab="hosts" />)
    fireEvent.click(within(openMenu()).getByRole('menuitem', { name: /CSV: Hosts/ }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export' })).toBeTruthy())
    expect((screen.getByRole('button', { name: 'Export' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('opens the IOC correlation dialog for this incident', async () => {
    setPermissions([...READ, 'incidents:export'])
    const m = mockApi()
    ;(m.post as jest.Mock).mockResolvedValue({ correlations: [], total: 0 } as never)
    renderTab(<ExportMenu incidentId="i1" activeTab="hosts" />)
    fireEvent.click(within(openMenu()).getByRole('menuitem', { name: /Correlate IOCs/ }))
    expect(await screen.findByText('IOC correlation')).toBeTruthy()
    await waitFor(() => expect(m.post).toHaveBeenCalledWith('/correlate-iocs', { incident_id: 'i1' }))
  })
})
