import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import type { ImprovementAction } from '@/types'
import { envelope, getCalls, mockApi, renderTab, resetTabTest, setPermissions, setSearch } from '@/components/incidents/test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('@/components/incidents/test-utils').navigationMock)

let ImprovementsPage: typeof import('./page').default
beforeAll(async () => {
  ;({ default: ImprovementsPage } = await import('./page'))
})

const VIEWER = ['improvements:read']
const OWNER = ['improvements:read', 'improvements:update'] // sees the user as u1 (test-utils)
const ADMIN = [...OWNER, 'improvements:create', 'improvements:delete']

const action = (over: Partial<ImprovementAction> = {}): ImprovementAction => ({
  id: 'a1',
  incident_id: 'i1',
  incident_ref: '#7 Ransomware',
  incident: { id: 'i1', title: 'Ransomware', incident_number: 7 },
  review_id: null,
  title: 'Enable MFA on VPN',
  description: null,
  owner_id: 'u1',
  owner: { id: 'u1', name: 'Pat' },
  team_id: null,
  due_date: '2099-01-01T00:00:00Z',
  status: 'open',
  priority: 'high',
  category: null,
  control_framework: 'nist_csf',
  control_ref: 'RS.MA-01',
  completed_at: null,
  created_by: 'u9',
  created_at: '2026-03-19T00:00:00Z',
  updated_at: null,
  version: 4,
  ...over,
})

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

function setup(permissions: string[], rows: ImprovementAction[]) {
  setPermissions(permissions)
  const spies = mockApi({ '/improvement-actions': envelope(rows) })
  renderTab(<ImprovementsPage />)
  return spies
}

describe('ImprovementsPage', () => {
  it('lists actions with the incident link, control, overdue marker and owner', async () => {
    setup(VIEWER, [
      action(),
      action({ id: 'a2', title: 'Patch the edge', due_date: '2020-01-01T00:00:00Z', owner: null, owner_id: null, control_framework: null, control_ref: null }),
    ])
    expect(await screen.findByText('Enable MFA on VPN')).toBeInTheDocument()
    expect(screen.getByText('NIST CSF RS.MA-01')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: '#7 Ransomware' })[0]).toHaveAttribute('href', '/dashboard/incidents/i1?tab=review')
    expect(screen.getByText('Pat')).toBeInTheDocument()
    const row = screen.getByText('Patch the edge').closest('tr') as HTMLElement
    expect(within(row).getByText('overdue')).toBeInTheDocument()
    expect(within(row).getByText('Unassigned')).toBeInTheDocument()
    expect(screen.getAllByText('overdue')).toHaveLength(1)
  })

  it('shows the saved label, not a link, once the incident was deleted', async () => {
    setup(VIEWER, [action({ incident_id: null, incident: null, incident_ref: '#7 Ransomware' })])
    expect(await screen.findByText(/#7 Ransomware \(deleted\)/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Ransomware/ })).toBeNull()
  })

  it('keeps the label of an action on an incident the viewer cannot open', async () => {
    setup(VIEWER, [action({ incident: null, incident_ref: '#9 Hidden case' })])
    expect(await screen.findByText('#9 Hidden case')).toBeInTheDocument()
    expect(screen.queryByText(/deleted/)).toBeNull()
  })

  it('a viewer sees status badges only', async () => {
    setup(VIEWER, [action()])
    await screen.findByText('Enable MFA on VPN')
    expect(screen.queryByLabelText('Status of Enable MFA on VPN')).toBeNull()
  })

  it('an owner changes the status inline, with If-Match', async () => {
    const spies = setup(OWNER, [action()])
    fireEvent.click(await screen.findByLabelText('Status of Enable MFA on VPN'))
    fireEvent.click(await screen.findByRole('option', { name: 'In progress' }))
    await waitFor(() =>
      expect(spies.put).toHaveBeenCalledWith('/improvement-actions/a1', { status: 'in_progress' }, { ifMatch: 4 })
    )
  })

  it("does not allow changing someone else's action without improvements:create", async () => {
    setup(OWNER, [action({ owner_id: 'u2', owner: { id: 'u2', name: 'Dana' }, created_by: 'u9' })])
    await screen.findByText('Enable MFA on VPN')
    expect(screen.queryByLabelText('Status of Enable MFA on VPN')).toBeNull()
  })

  it('the manager tier can change any action', async () => {
    setup(ADMIN, [action({ owner_id: 'u2', owner: { id: 'u2', name: 'Dana' } })])
    expect(await screen.findByLabelText('Status of Enable MFA on VPN')).toBeInTheDocument()
  })

  it('"Mine" and "Overdue" are server filters', async () => {
    const spies = setup(VIEWER, [action()])
    await screen.findByText('Enable MFA on VPN')
    fireEvent.click(screen.getByRole('button', { name: 'Mine' }))
    await waitFor(() => expect(getCalls(spies.get).some((c) => c.includes('owner_id=me'))).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: 'Overdue' }))
    await waitFor(() => expect(getCalls(spies.get).some((c) => c.includes('overdue=true'))).toBe(true))
    expect(screen.getByRole('button', { name: 'Mine' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows an empty state', async () => {
    setup(VIEWER, [])
    expect(await screen.findByText('No improvement actions')).toBeInTheDocument()
  })

  it('lands on the row from a reminder link (?id=)', async () => {
    setSearch('id=a1')
    const spies = setup(VIEWER, [action()])
    await screen.findByText('Enable MFA on VPN')
    expect(getCalls(spies.get).some((c) => c.includes('focus=a1'))).toBe(true)
  })
})
