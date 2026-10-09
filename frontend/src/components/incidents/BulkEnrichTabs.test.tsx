import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, within } from '@testing-library/react'
import { act } from '@testing-library/react'
import { useIncidentStore } from '@/lib/store'
import { envelope, mockApi, renderTab, resetTabTest, setRole } from './test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('./test-utils').navigationMock)

let NetworkIOCsTab: typeof import('./NetworkIOCsTab').NetworkIOCsTab
let MalwareToolsTab: typeof import('./MalwareToolsTab').MalwareToolsTab
let HostsTab: typeof import('./HostsTab').HostsTab
beforeAll(async () => {
  ;({ NetworkIOCsTab } = await import('./NetworkIOCsTab'))
  ;({ MalwareToolsTab } = await import('./MalwareToolsTab'))
  ;({ HostsTab } = await import('./HostsTab'))
})

beforeEach(() => {
  resetTabTest()
  act(() => {
    useIncidentStore.setState({ currentIncident: { id: 'i1', tlp: 'amber' } } as never)
  })
})
afterEach(() => {
  resetTabTest()
  act(() => {
    useIncidentStore.setState({ currentIncident: null } as never)
  })
})

const ioc = { id: 'n1', incident_id: 'i1', dns_ip: '203.0.113.9', direction: 'outbound', is_malicious: true, version: 1 }
const malware = {
  id: 'm1', incident_id: 'i1', file_name: 'beacon.exe', sha256: 'a'.repeat(64), md5: 'b'.repeat(32),
  is_tool: false, version: 1,
}

function selectFirstRow() {
  const checkboxes = screen.getAllByRole('checkbox')
  fireEvent.click(checkboxes[1]) // [0] is select-all
}

describe('bulk enrich on the Network IOCs and Malware tabs (C35)', () => {
  it('Network IOCs: selecting a row offers Enrich (n) for its value', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/network-iocs': envelope([ioc]) })
    renderTab(<NetworkIOCsTab incidentId="i1" />)
    await screen.findByText('203.0.113.9')
    expect(screen.queryByRole('button', { name: /^Enrich/ })).toBeNull()
    selectFirstRow()
    fireEvent.click(await screen.findByRole('button', { name: 'Enrich (1)' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Enrich 1 network IOC?')).toBeTruthy()
  })

  it('Malware: enriches the SHA-256 of the selected rows', async () => {
    setRole('viewer')
    const m = mockApi({ '/incidents/i1/malware': envelope([malware]) })
    ;(m.post as jest.Mock).mockResolvedValue({ results: [], total: 0, enriched: 0, failed: 0, blocked: 0, providers: [] } as never)
    renderTab(<MalwareToolsTab incidentId="i1" />)
    await screen.findByText('beacon.exe')
    selectFirstRow()
    fireEvent.click(await screen.findByRole('button', { name: 'Enrich (1)' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Enrich' }))
    await screen.findByRole('table', { name: 'Enrichment results' })
    expect(m.post).toHaveBeenCalledWith('/bulk-enrich', {
      incident_id: 'i1',
      ioc_values: [{ value: 'a'.repeat(64), type: 'sha256' }],
    })
  })

  it('the Hosts tab has no enrich action (only Network IOCs and Malware do)', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/hosts': envelope([{ id: 'h1', incident_id: 'i1', hostname: 'WS-01', version: 1 }]) })
    renderTab(<HostsTab incidentId="i1" />)
    await screen.findByText('WS-01')
    expect(screen.queryByRole('button', { name: /^Enrich/ })).toBeNull()
  })
})
