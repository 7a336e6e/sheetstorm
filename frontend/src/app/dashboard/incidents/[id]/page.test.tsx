import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import type { ComponentType } from 'react'
import {
  currentSearch,
  mockApi,
  renderTab,
  resetTabTest,
  setRole,
  setSearch,
} from '@/components/incidents/test-utils'
import { useIncidentStore } from '@/lib/store'
import type { IncidentTabProps } from './tabs'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('@/components/incidents/test-utils').navigationMock)

// A light registry: the real panels are covered by their own tests.
jest.mock('./tabs', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const actual = jest.requireActual('./tabs') as typeof import('./tabs')
  const panel = (id: string): ComponentType<IncidentTabProps> =>
    function Panel({ focusRowId }: IncidentTabProps) {
      return <div data-testid={`panel-${id}`}>{`${id}:${focusRowId ?? '-'}`}</div>
    }
  return {
    ...actual,
    TAB_REGISTRY: [
      { id: 'overview', label: 'Overview', icon: () => null, permission: 'incidents:read', component: panel('overview'), keepMounted: true },
      { id: 'hosts', label: 'Hosts', icon: () => null, permission: 'hosts:read', component: panel('hosts'), keepMounted: true },
      { id: 'graph', label: 'Attack Graph', icon: () => null, permission: 'attack_graph:read', component: panel('graph'), keepMounted: false },
      { id: 'evidence', label: 'Artifacts', icon: () => null, permission: 'artifacts:read', component: panel('evidence'), keepMounted: true },
    ],
  }
})

let Page: typeof import('./page').default
beforeAll(async () => {
  ;({ default: Page } = await import('./page'))
})

const incident = {
  id: 'i1',
  incident_number: 7,
  title: 'Ransomware at HQ',
  severity: 'high',
  status: 'open',
  phase: 2,
  phase_name: 'Identification',
  tlp: 'amber',
  created_at: '2026-01-01T00:00:00Z',
  version: 4,
}

beforeEach(() => {
  resetTabTest()
  useIncidentStore.setState({ currentIncident: null })
})
afterEach(() => resetTabTest())

function setup(role: 'viewer' | 'responder', search = '') {
  setRole(role)
  setSearch(search)
  const api = mockApi({ '/incidents/i1': incident })
  renderTab(<Page />)
  return api
}

describe('incident detail page', () => {
  it('Viewer sees no header mutation actions', async () => {
    setup('viewer')
    expect(await screen.findByText('Ransomware at HQ')).toBeTruthy()
    ;['Edit', 'Import', 'Update Status', 'Generate Report'].forEach((name) =>
      expect(screen.queryByRole('button', { name: new RegExp(name, 'i') })).toBeNull()
    )
    // Tabs the Viewer cannot read are not offered.
    expect(screen.queryByRole('tab', { name: /artifacts/i })).toBeNull()
    expect(screen.getByRole('tab', { name: /hosts/i })).toBeTruthy()
  })

  it('Responder sees the header actions', async () => {
    setup('responder')
    await screen.findByText('Ransomware at HQ')
    ;['Edit', 'Import', 'Update Status', 'Generate Report'].forEach((name) =>
      expect(screen.getByRole('button', { name: new RegExp(name, 'i') })).toBeTruthy()
    )
  })

  it('opens the tab from ?tab= and passes ?row= to it as focus', async () => {
    setup('viewer', 'tab=hosts&row=h1')
    expect((await screen.findByTestId('panel-hosts')).textContent).toBe('hosts:h1')
  })

  it('aliases ?tab=artifacts to the evidence tab', async () => {
    setup('responder', 'tab=artifacts')
    expect(await screen.findByTestId('panel-evidence')).toBeTruthy()
  })

  it('falls back to overview for a tab the user cannot see', async () => {
    setup('viewer', 'tab=artifacts')
    expect(await screen.findByTestId('panel-overview')).toBeTruthy()
    expect(screen.queryByTestId('panel-evidence')).toBeNull()
  })

  it('switching tabs writes ?tab=, drops ?row= and keeps visited list tabs mounted', async () => {
    setup('viewer', 'tab=hosts&row=h1&hosts.page=3')
    await screen.findByTestId('panel-hosts')

    const overview = screen.getByRole('tab', { name: /overview/i })
    fireEvent.mouseDown(overview)
    fireEvent.click(overview)
    await waitFor(() => expect(currentSearch().get('tab')).toBeNull())
    expect(currentSearch().get('row')).toBeNull()
    expect(currentSearch().get('hosts.page')).toBe('3')

    // Hosts stays mounted (hidden) with its state; focus is cleared.
    const hosts = screen.getByTestId('panel-hosts')
    expect(hosts.textContent).toBe('hosts:-')
    expect(hosts.closest('[role="tabpanel"]')?.hasAttribute('hidden')).toBe(true)
  })

  it('unmounts the graph panel when it is not active', async () => {
    setup('viewer', 'tab=graph')
    await screen.findByTestId('panel-graph')
    setSearch('tab=hosts')
    await screen.findByTestId('panel-hosts')
    expect(screen.queryByTestId('panel-graph')).toBeNull()
  })

  it('shows not found when the incident cannot be loaded', async () => {
    setRole('viewer')
    const { ApiError } = await import('@/lib/api')
    mockApi({
      '/incidents/i1': () => {
        throw new ApiError(404, 'Incident not found', { code: 'not_found' })
      },
    })
    renderTab(<Page />)
    expect(await screen.findByText('Incident not found')).toBeTruthy()
  })
})
