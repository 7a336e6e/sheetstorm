import { afterEach, beforeEach, describe, expect, it } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { getCalls, mockApi, renderTab, resetTabTest, setPermissions, setRole } from '@/components/incidents/test-utils'
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

  it('nodes the generator created (origin auto) are never manual', () => {
    expect(isManualNode({ extra_data: { origin: 'auto', auto_key: 'nioc:c2.example' } })).toBe(false)
    expect(isManualNode({ extra_data: { origin: 'auto' } })).toBe(false)
  })

  it('adding missing items needs create; rebuilding from scratch needs create and delete', () => {
    const none = graphAbilities({ create: false, update: false, delete: false })
    expect(none.canRegenerate).toBe(false)
    expect(none.canRebuild).toBe(false)
    const create = graphAbilities({ create: true, update: false, delete: false })
    expect(create.canRegenerate).toBe(true)
    expect(create.canRebuild).toBe(false)
    expect(graphAbilities({ create: true, update: false, delete: true }).canRebuild).toBe(true)
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
      expect(api.post).toHaveBeenCalledWith('/incidents/i1/attack-graph/auto-generate', { mode: 'merge' })
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

  it('Responder: Regenerate offers "Add missing items" first and merges without a destructive confirm', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/attack-graph': { nodes: [autoNode, manualNode], edges: [] } })
    renderTab(<AttackGraphViewer incidentId="i1" />)

    fireEvent.click(await screen.findByTitle('Regenerate Graph'))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/keeps your edits and layout/i)).toBeTruthy()
    expect(within(dialog).getByText(/deletes all manual nodes, edges and positions/i)).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('button', { name: /add missing items/i }))
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/incidents/i1/attack-graph/auto-generate', { mode: 'merge' })
    )
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('Responder: rebuilding with manual nodes requires typing REBUILD and sends confirm', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/attack-graph': { nodes: [autoNode, manualNode], edges: [] } })
    renderTab(<AttackGraphViewer incidentId="i1" />)

    fireEvent.click(await screen.findByTitle('Regenerate Graph'))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /rebuild from scratch/i }))
    const confirmDialog = await screen.findByRole('dialog')
    const confirmBtn = within(confirmDialog).getByRole('button', { name: 'Rebuild' })
    expect((confirmBtn as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(within(confirmDialog).getByRole('textbox'), { target: { value: 'REBUILD' } })
    expect((confirmBtn as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(confirmBtn)
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/incidents/i1/attack-graph/auto-generate', { mode: 'replace', confirm: true })
    )
  })

  it('without attack_graph:delete only "Add missing items" is offered', async () => {
    setPermissions(['incidents:read', 'attack_graph:read', 'attack_graph:create'])
    mockApi({ '/incidents/i1/attack-graph': { nodes: [autoNode], edges: [] } })
    renderTab(<AttackGraphViewer incidentId="i1" />)

    fireEvent.click(await screen.findByTitle('Regenerate Graph'))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('button', { name: /add missing items/i })).toBeTruthy()
    expect(within(dialog).queryByRole('button', { name: /rebuild from scratch/i })).toBeNull()
  })

  it('Responder: cancelling the regenerate dialog or the rebuild confirm sends nothing', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/attack-graph': { nodes: [autoNode], edges: [] } })
    renderTab(<AttackGraphViewer incidentId="i1" />)

    fireEvent.click(await screen.findByTitle('Regenerate Graph'))
    let dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    fireEvent.click(screen.getByTitle('Regenerate Graph'))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /rebuild from scratch/i }))
    dialog = await screen.findByRole('dialog')
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
