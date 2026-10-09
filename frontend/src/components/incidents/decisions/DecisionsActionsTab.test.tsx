import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { Decision, ResponseAction } from '@/types'
import { envelope, mockApi, renderTab, resetTabTest, setPermissions } from '../test-utils'
import { TransitionDialog } from './TransitionDialog'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('../test-utils').navigationMock)

let DecisionsActionsTab: typeof import('./DecisionsActionsTab').DecisionsActionsTab
beforeAll(async () => {
  ;({ DecisionsActionsTab } = await import('./DecisionsActionsTab'))
})

const VIEWER = ['incidents:read', 'decisions:read', 'response_actions:read']
const RESPONDER = [
  ...VIEWER, 'decisions:create', 'decisions:update', 'decisions:approve', 'decisions:read_privileged',
  'response_actions:create', 'response_actions:update', 'response_actions:authorize', 'incidents:export',
]

const decision = (over: Partial<Decision> = {}): Decision =>
  ({
    id: 'd1', incident_id: 'i1', number: 1, display_id: 'D-001', record_type: 'decision', title: 'Do not pay',
    decision: 'We will not pay the ransom', rationale: 'Policy', alternatives: [], category: 'ransom_legal',
    status: 'proposed', status_reason: null, is_privileged: false, decided_at: '2026-03-01T10:00:00Z',
    decided_by_user_id: 'u1', decided_by_name: null, approved_by_user_id: null, approved_by_name: null,
    approved_at: null, self_approved: false, superseded_by_id: null, links: [], created_at: '2026-03-01T10:00:00Z',
    created_by: 'u1', updated_at: null, version: 3, revision_count: 1, users: { decided_by_user_id: { id: 'u1', name: 'Pat' } },
    ...over,
  }) as Decision

const action = (over: Partial<ResponseAction> = {}): ResponseAction =>
  ({
    id: 'a1', incident_id: 'i1', number: 1, display_id: 'A-001', record_type: 'response_action',
    action_type: 'isolate_host', title: 'Isolate WS-01', description: null, target_type: 'host', target_id: 'h1',
    target_label: 'WS-01', decision_id: null, decision: null, status: 'authorized', status_reason: null,
    requested_by_user_id: 'u1', requested_at: '2026-03-01T10:00:00Z', authorized_by_user_id: null,
    authorized_by_name: 'CISO', authorized_at: '2026-03-01T10:05:00Z', self_approved: false,
    executed_by_user_id: null, executed_by_name: null, executed_at: null, verified_by_user_id: null,
    verified_by_name: null, verified_at: null, verification_method: null, verification_result: null,
    verification_notes: null, self_verified: false, rollback_plan: null, rolled_back_at: null, rollback_reason: null,
    target_state_before: null, target_state_after: null, links: [], created_at: '2026-03-01T10:00:00Z',
    updated_at: null, version: 2, revision_count: 2, users: {},
    ...over,
  }) as ResponseAction

function setup(permissions: string[], decisions = [decision()], actions = [action()]) {
  setPermissions(permissions)
  const spies = mockApi({
    '/incidents/i1/decisions': envelope(decisions),
    '/incidents/i1/response-actions': envelope(actions),
  })
  renderTab(<DecisionsActionsTab incidentId="i1" />)
  return spies
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('DecisionsActionsTab', () => {
  it('is read-only for a viewer', async () => {
    setup(VIEWER)
    expect(await screen.findByText('Do not pay')).toBeInTheDocument()
    expect(await screen.findByText('Isolate WS-01')).toBeInTheDocument()
    expect(screen.getByText(/CISO \(recorded\)/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /record decision/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /plan action/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /export decision log/i })).toBeNull()
  })

  it('offers create and export to a responder and marks privileged decisions', async () => {
    setup(RESPONDER, [decision({ is_privileged: true, title: 'Counsel advice' })])
    expect(await screen.findByText('Counsel advice')).toBeInTheDocument()
    expect(screen.getByText('Privileged')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /record decision/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /plan action/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /export decision log/i })).toBeInTheDocument()
  })

  it('creates a decision with the form values', async () => {
    const spies = setup(RESPONDER, [])
    fireEvent.click(await screen.findByRole('button', { name: /record decision/i }))
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Rebuild AD' } })
    fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'Rebuild the forest' } })
    spies.post.mockResolvedValue(decision() as never)
    fireEvent.click(screen.getByRole('button', { name: /^record decision$/i, hidden: false }))
    await waitFor(() => expect(spies.post).toHaveBeenCalled())
    const [endpoint, body] = spies.post.mock.calls[0] as [string, Record<string, unknown>]
    expect(endpoint).toBe('/incidents/i1/decisions')
    expect(body).toMatchObject({ title: 'Rebuild AD', decision: 'Rebuild the forest', category: 'other', is_privileged: false })
  })
})

describe('TransitionDialog', () => {
  it('forces an external attestation without decisions:approve and sends expected_version', async () => {
    setPermissions(['decisions:read', 'decisions:update'])
    const spies = mockApi()
    render(<TransitionDialog incidentId="i1" target={{ kind: 'decision', record: decision(), event: 'approve' }} onOpenChange={() => {}} />)
    const box = screen.getByRole('checkbox', { name: /outside sheetstorm/i })
    expect(box).toBeChecked()
    expect(box).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Approved by'), { target: { value: 'General Counsel' } })
    fireEvent.click(screen.getByRole('button', { name: /approve decision/i }))
    await waitFor(() => expect(spies.post).toHaveBeenCalled())
    const [endpoint, body] = spies.post.mock.calls[0] as [string, Record<string, unknown>]
    expect(endpoint).toBe('/incidents/i1/decisions/d1/approve')
    expect(body).toEqual({ approved_by_name: 'General Counsel', expected_version: 3 })
  })

  it('disables the target-state checkbox without hosts:update', () => {
    setPermissions(['response_actions:read', 'response_actions:update'])
    mockApi()
    render(<TransitionDialog incidentId="i1" target={{ kind: 'action', record: action(), event: 'execute' }} onOpenChange={() => {}} />)
    expect(screen.getByRole('checkbox', { name: /update the host/i })).toBeDisabled()
    expect(screen.getByText(/needs hosts:update/i)).toBeInTheDocument()
  })

  it('enables it with hosts:update', () => {
    setPermissions(['response_actions:read', 'response_actions:update', 'hosts:update'])
    mockApi()
    render(<TransitionDialog incidentId="i1" target={{ kind: 'action', record: action(), event: 'execute' }} onOpenChange={() => {}} />)
    expect(screen.getByRole('checkbox', { name: /update the host/i })).toBeEnabled()
  })
})
