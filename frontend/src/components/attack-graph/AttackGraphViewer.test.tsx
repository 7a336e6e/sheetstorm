import { afterEach, beforeEach, describe, expect, it } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { getCalls, mockApi, renderTab, resetTabTest, setRole } from '@/components/incidents/test-utils'
import { AttackGraphViewer, graphAbilities, isManualNode } from './AttackGraphViewer'

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

const autoNode = {
  id: 'n1',
  incident_id: 'i1',
  node_type: 'workstation',
  label: 'WS-01',
  compromised_host_id: 'h1',
  position_x: 0,
  position_y: 0,
  is_initial_access: false,
  is_objective: false,
  extra_data: { containment_status: 'active', ip_address: '10.0.0.5' },
  created_at: '2026-01-01T00:00:00Z',
  version: 2,
}
const manualNode = {
  ...autoNode,
  id: 'n2',
  node_type: 'attacker',
  label: 'APT',
  compromised_host_id: undefined,
  extra_data: { description: 'drawn by hand' },
}

describe('graph helpers', () => {
  it('treats nodes without entity links or data as manual', () => {
    expect(isManualNode({ compromisedHostId: 'h1', extra_data: {} })).toBe(false)
    expect(isManualNode({ extra_data: { sha256: 'abc' } })).toBe(false)
    expect(isManualNode({ extra_data: { description: 'x' } })).toBe(true)
    expect(isManualNode({})).toBe(true)
  })

  it('regenerate needs create and delete', () => {
    expect(graphAbilities({ create: true, update: false, delete: false }).canRegenerate).toBe(false)
    expect(graphAbilities({ create: true, update: false, delete: true }).canRegenerate).toBe(true)
  })
})

describe('AttackGraphViewer gating', () => {
  it('Viewer: empty graph is not auto-generated and offers no Generate button', async () => {
    setRole('viewer')
    const api = mockApi({ '/incidents/i1/attack-graph': { nodes: [], edges: [] } })
    renderTab(<AttackGraphViewer incidentId="i1" />)

    expect(await screen.findByText('No graph data found')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /generate graph/i })).toBeNull()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('Responder: an empty graph is generated automatically without a confirm', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/attack-graph': { nodes: [], edges: [] } })
    renderTab(<AttackGraphViewer incidentId="i1" />)

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/incidents/i1/attack-graph/auto-generate', { clear_existing: true })
    )
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('Viewer: no add / draw / regenerate controls on a populated graph', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/attack-graph': { nodes: [autoNode], edges: [] } })
    renderTab(<AttackGraphViewer incidentId="i1" />)

    expect(await screen.findByTitle('Zoom In')).toBeTruthy()
    expect(screen.queryByTitle('Add Node')).toBeNull()
    expect(screen.queryByTitle('Draw Connection')).toBeNull()
    expect(screen.queryByTitle('Regenerate Graph')).toBeNull()
  })

  it('Responder: regenerate with manual nodes requires typing REGENERATE', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/attack-graph': { nodes: [autoNode, manualNode], edges: [] } })
    renderTab(<AttackGraphViewer incidentId="i1" />)

    fireEvent.click(await screen.findByTitle('Regenerate Graph'))
    const dialog = await screen.findByRole('dialog')
    const confirmBtn = within(dialog).getByRole('button', { name: 'Regenerate' })
    expect((confirmBtn as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'REGENERATE' } })
    expect((confirmBtn as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(confirmBtn)
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/incidents/i1/attack-graph/auto-generate', { clear_existing: true })
    )
  })

  it('Responder: cancelling the regenerate confirm sends nothing', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/attack-graph': { nodes: [autoNode], edges: [] } })
    renderTab(<AttackGraphViewer incidentId="i1" />)

    fireEvent.click(await screen.findByTitle('Regenerate Graph'))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByRole('textbox')).toBeNull() // no manual nodes: plain confirm
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(api.post).not.toHaveBeenCalled()
  })
})

describe('AttackGraphViewer draw-edge dialog', () => {
  it('offers timeline events from every page, not just the first', async () => {
    setRole('responder')
    const event = (id: string, activity: string) => ({ id, incident_id: 'i1', timestamp: '2026-01-01T00:00:00Z', activity })
    const api = mockApi({
      '/incidents/i1/attack-graph': { nodes: [autoNode, manualNode], edges: [] },
      '/incidents/i1/timeline': (endpoint: string) => {
        const page = Number(new URL(endpoint, 'http://x').searchParams.get('page') || 1)
        const items = page === 1 ? [event('e1', 'first page logon')] : [event('e2', 'second page beacon')]
        return { items, total: 2, page, per_page: 1, pages: 2 }
      },
    })
    const { container } = renderTab(<AttackGraphViewer incidentId="i1" />)
    await screen.findByTitle('Zoom In')
    expect(getCalls(api.get).some((c) => c.startsWith('/incidents/i1/timeline'))).toBe(false)

    fireEvent.click(screen.getByTitle('Draw Connection'))
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="n2"]')).not.toBeNull())
    fireEvent.click(container.querySelector('.react-flow__node[data-id="n1"]') as Element)
    fireEvent.click(container.querySelector('.react-flow__node[data-id="n2"]') as Element)

    await screen.findByRole('dialog')
    await waitFor(() => {
      const pages = getCalls(api.get)
        .filter((c) => c.startsWith('/incidents/i1/timeline'))
        .map((c) => new URL(c, 'http://x').searchParams.get('page'))
      expect(pages).toEqual(expect.arrayContaining(['1', '2']))
    })
    await waitFor(() => expect(screen.queryByText('Loading events...')).toBeNull())
  })
})
