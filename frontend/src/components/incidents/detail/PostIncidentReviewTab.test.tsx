import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import type { ImprovementAction, IncidentReview, ReviewResponse } from '@/types'
import { dispatchChange } from '@/lib/realtime/live'
import { envelope, mockApi, renderTab, resetTabTest, setPermissions } from '../test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('../test-utils').navigationMock)

let PostIncidentReviewTab: typeof import('./PostIncidentReviewTab').PostIncidentReviewTab
beforeAll(async () => {
  ;({ PostIncidentReviewTab } = await import('./PostIncidentReviewTab'))
})

const VIEWER = ['incidents:read', 'improvements:read']
const ANALYST = [...VIEWER, 'incidents:update', 'improvements:update']
const RESPONDER = [...ANALYST, 'improvements:create']
const ADMIN = [...RESPONDER, 'improvements:delete']

const review = (over: Partial<IncidentReview> = {}): IncidentReview => ({
  id: 'r1',
  incident_id: 'i1',
  what_went_well: 'Fast triage',
  what_went_wrong: 'Slow containment',
  root_cause: 'No MFA on VPN',
  contributing_factors: [{ category: 'technology', description: 'VPN had no MFA' }],
  detection_source: 'threat_hunt',
  review_date: '2026-03-20',
  participants: ['u2'],
  participant_users: [{ id: 'u2', name: 'Dana' }],
  status: 'draft',
  finalized_at: null,
  finalized_by: null,
  created_at: '2026-03-19T00:00:00Z',
  updated_at: null,
  version: 3,
  ...over,
})

const response = (r: IncidentReview | null, over: Partial<ReviewResponse> = {}): ReviewResponse => ({
  review: r,
  legacy_lessons_learned: null,
  can_manage: false,
  ...over,
})

const action = (over: Partial<ImprovementAction> = {}): ImprovementAction => ({
  id: 'a1',
  incident_id: 'i1',
  incident_ref: '#7 Ransomware',
  incident: { id: 'i1', title: 'Ransomware', incident_number: 7 },
  review_id: 'r1',
  title: 'Enable MFA on VPN',
  description: null,
  owner_id: 'u1',
  owner: { id: 'u1', name: 'Pat' },
  team_id: null,
  due_date: '2099-01-01T00:00:00Z',
  status: 'open',
  priority: 'high',
  category: 'technology',
  control_framework: 'd3fend',
  control_ref: 'D3-MFA',
  completed_at: null,
  created_by: 'u3',
  created_at: '2026-03-19T00:00:00Z',
  updated_at: null,
  version: 4,
  ...over,
})

function setup(permissions: string[], res: ReviewResponse, actions: ImprovementAction[] = []) {
  setPermissions(permissions)
  const spies = mockApi({
    '/incidents/i1/review': res,
    '/incidents/i1/improvement-actions': envelope(actions),
  })
  spies.put.mockResolvedValue(review() as never)
  renderTab(<PostIncidentReviewTab incidentId="i1" />)
  return spies
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

const root = () => screen.findByLabelText('Root cause') as Promise<HTMLTextAreaElement>

describe('PostIncidentReviewTab', () => {
  it('is read-only for a viewer: no save, no finalize, no add action', async () => {
    setup(VIEWER, response(review()), [action()])
    expect((await root()).value).toBe('No MFA on VPN')
    expect(screen.getByLabelText('Root cause')).toHaveAttribute('readonly')
    expect(screen.queryByRole('button', { name: /save review/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /finalize/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /add action/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /add factor/i })).toBeNull()
    expect(screen.getByText('VPN had no MFA')).toBeInTheDocument()
    expect(screen.getByText('Dana')).toBeInTheDocument()
    expect(await screen.findByText('Enable MFA on VPN')).toBeInTheDocument()
    expect(screen.getByTestId('review-status').textContent).toBe('Draft')
  })

  it('shows the legacy lessons-learned text read-only', async () => {
    setup(VIEWER, response(null, { legacy_lessons_learned: 'old notes from before' }))
    expect(await screen.findByText('old notes from before')).toBeInTheDocument()
    expect(screen.getByText('Legacy notes')).toBeInTheDocument()
  })

  it('creates the first review without If-Match and only saves when something changed', async () => {
    const spies = setup(ANALYST, response(null))
    const field = await root()
    const save = screen.getByRole('button', { name: /save review/i })
    expect(save).toBeDisabled()
    fireEvent.change(field, { target: { value: 'Stolen VPN credentials' } })
    expect(save).toBeEnabled()
    fireEvent.click(save)
    await waitFor(() => expect(spies.put).toHaveBeenCalledTimes(1))
    const [endpoint, body, opts] = spies.put.mock.calls[0] as [string, Record<string, unknown>, { ifMatch?: number }]
    expect(endpoint).toBe('/incidents/i1/review')
    expect(body).toMatchObject({ root_cause: 'Stolen VPN credentials', detection_source: null, review_date: null })
    expect(body.status).toBeUndefined()
    expect(opts.ifMatch).toBeUndefined()
  })

  it('sends the review version as If-Match on later saves, with contributing factors', async () => {
    const spies = setup(ANALYST, response(review()))
    await root()
    fireEvent.change(screen.getByLabelText('Factor description'), { target: { value: 'No alerting on VPN logins' } })
    fireEvent.click(screen.getByRole('button', { name: /add factor/i }))
    expect(screen.getByText('No alerting on VPN logins')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /save review/i }))
    await waitFor(() => expect(spies.put).toHaveBeenCalled())
    const [, body, opts] = spies.put.mock.calls[0] as [string, { contributing_factors: unknown[] }, { ifMatch?: number }]
    expect(opts.ifMatch).toBe(3)
    expect(body.contributing_factors).toEqual([
      { category: 'technology', description: 'VPN had no MFA' },
      { category: 'process', description: 'No alerting on VPN logins' },
    ])
  })

  it('removes a contributing factor and a participant', async () => {
    const spies = setup(ANALYST, response(review()))
    await root()
    fireEvent.click(screen.getByRole('button', { name: /remove factor: vpn had no mfa/i }))
    fireEvent.click(screen.getByRole('button', { name: /remove participant dana/i }))
    fireEvent.click(screen.getByRole('button', { name: /save review/i }))
    await waitFor(() => expect(spies.put).toHaveBeenCalled())
    const body = spies.put.mock.calls[0][1] as { contributing_factors: unknown[]; participants: string[] }
    expect(body.contributing_factors).toEqual([])
    expect(body.participants).toEqual([])
  })

  it('does not offer Finalize to someone without the manager tier', async () => {
    setup(ANALYST, response(review(), { can_manage: false }))
    await root()
    expect(screen.queryByRole('button', { name: /finalize/i })).toBeNull()
  })

  it('finalizes after confirmation (manager tier), with If-Match', async () => {
    const spies = setup(RESPONDER, response(review(), { can_manage: true }))
    await root()
    fireEvent.click(screen.getByRole('button', { name: /^finalize$/i }))
    const dialog = await screen.findByRole('dialog', { name: /finalize this review/i })
    fireEvent.click(within(dialog).getByRole('button', { name: /^finalize$/i }))
    await waitFor(() => expect(spies.put).toHaveBeenCalled())
    const [endpoint, body, opts] = spies.put.mock.calls[0] as [string, { status?: string }, { ifMatch?: number }]
    expect(endpoint).toBe('/incidents/i1/review')
    expect(body.status).toBe('final')
    expect(opts.ifMatch).toBe(3)
  })

  it('locks a final review for the analyst tier and explains why', async () => {
    setup(ANALYST, response(review({ status: 'final', finalized_at: '2026-03-21T00:00:00Z' }), { can_manage: false }))
    await root()
    expect(screen.getByTestId('review-status').textContent).toBe('Final')
    expect(screen.getByLabelText('Root cause')).toHaveAttribute('readonly')
    expect(screen.queryByRole('button', { name: /save review/i })).toBeNull()
    expect(screen.getByText(/this review is final/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reopen/i })).toBeNull()
  })

  it('lets the manager tier reopen a final review', async () => {
    const spies = setup(RESPONDER, response(review({ status: 'final', finalized_at: '2026-03-21T00:00:00Z' }), { can_manage: true }))
    await root()
    expect(screen.getByLabelText('Root cause')).not.toHaveAttribute('readonly')
    fireEvent.click(screen.getByRole('button', { name: /reopen/i }))
    await waitFor(() => expect(spies.put).toHaveBeenCalled())
    expect((spies.put.mock.calls[0][1] as { status?: string }).status).toBe('draft')
  })

  describe('remote changes', () => {
    const remote = (over: Partial<IncidentReview>) =>
      ({
        incident_id: 'i1', entity: 'review', op: 'updated', id: 'r1', version: 4, scope: 'review', seq: 2,
        at: '2026-03-20T00:00:00Z', data: review({ version: 4, ...over }),
      }) as never

    it('applies a remote edit silently while the form is untouched', async () => {
      setup(ANALYST, response(review()))
      await root()
      act(() => dispatchChange(remote({ root_cause: 'Phished admin' })))
      await waitFor(() => expect((screen.getByLabelText('Root cause') as HTMLTextAreaElement).value).toBe('Phished admin'))
      expect(screen.queryByText(/changed while you were editing/i)).toBeNull()
    })

    it('never overwrites an open form: shows a banner and loads theirs on request', async () => {
      setup(ANALYST, response(review()))
      const field = await root()
      fireEvent.change(field, { target: { value: 'my unsaved edit' } })
      act(() => dispatchChange(remote({ root_cause: 'Phished admin' })))
      expect(await screen.findByText(/changed while you were editing/i)).toBeInTheDocument()
      expect((screen.getByLabelText('Root cause') as HTMLTextAreaElement).value).toBe('my unsaved edit')
      fireEvent.click(screen.getByRole('button', { name: /load their version/i }))
      expect((screen.getByLabelText('Root cause') as HTMLTextAreaElement).value).toBe('Phished admin')
      expect(screen.queryByText(/changed while you were editing/i)).toBeNull()
    })

    it('ignores stale echoes and other incidents', async () => {
      setup(ANALYST, response(review()))
      await root()
      act(() => {
        dispatchChange(remote({ root_cause: 'echo', version: 3 }))
        dispatchChange({ ...(remote({ root_cause: 'other' }) as object), incident_id: 'other' } as never)
      })
      expect((screen.getByLabelText('Root cause') as HTMLTextAreaElement).value).toBe('No MFA on VPN')
    })
  })

  describe('improvement actions', () => {
    it('lists the actions and lets the owner change the status inline', async () => {
      const spies = setup(ANALYST, response(review()), [action({ owner_id: 'u1' })])
      // The signed-in user (setPermissions) is id u1: the owner.
      expect(await screen.findByText('Enable MFA on VPN')).toBeInTheDocument()
      expect(screen.getByText('D3FEND D3-MFA')).toBeInTheDocument()
      expect(screen.getByLabelText('Status of Enable MFA on VPN')).toBeInTheDocument()
      expect(spies.get).toHaveBeenCalledWith(expect.stringContaining('/incidents/i1/improvement-actions'), expect.anything())
    })

    it('shows a plain status badge for an action the analyst neither owns nor created', async () => {
      setup(ANALYST, response(review()), [action({ owner_id: 'someone', created_by: 'else' })])
      expect(await screen.findByText('Enable MFA on VPN')).toBeInTheDocument()
      expect(screen.queryByLabelText('Status of Enable MFA on VPN')).toBeNull()
    })

    it('lets the responder tier change any action and add new ones', async () => {
      setup(RESPONDER, response(review()), [action({ owner_id: 'someone', created_by: 'else' })])
      expect(await screen.findByLabelText('Status of Enable MFA on VPN')).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: /add action/i }))
      expect(await screen.findByRole('dialog', { name: /add improvement action/i })).toBeInTheDocument()
    })

    it('hides Add action without improvements:create and the whole table without improvements:read', async () => {
      setup(ANALYST, response(review()), [action()])
      await screen.findByText('Enable MFA on VPN')
      expect(screen.queryByRole('button', { name: /add action/i })).toBeNull()
    })

    it('does not render the actions card for a user who cannot read improvements', async () => {
      setup(['incidents:read'], response(review()))
      await root()
      expect(screen.queryByText('Improvement actions')).toBeNull()
    })

    it('creates an action through the dialog (title required)', async () => {
      const spies = setup(ADMIN, response(review()))
      spies.post.mockResolvedValue(action() as never)
      await root()
      fireEvent.click(await screen.findByRole('button', { name: /add action/i }))
      const dialog = await screen.findByRole('dialog', { name: /add improvement action/i })
      fireEvent.click(within(dialog).getByRole('button', { name: /^add action$/i }))
      expect((await within(dialog).findByRole('alert')).textContent).toMatch(/title is required/i)
      expect(spies.post).not.toHaveBeenCalled()
      fireEvent.change(within(dialog).getByLabelText('Title'), { target: { value: 'Rotate VPN secrets' } })
      fireEvent.click(within(dialog).getByRole('button', { name: /^add action$/i }))
      await waitFor(() => expect(spies.post).toHaveBeenCalled())
      const [endpoint, body] = spies.post.mock.calls[0] as [string, Record<string, unknown>]
      expect(endpoint).toBe('/incidents/i1/improvement-actions')
      expect(body).toMatchObject({ title: 'Rotate VPN secrets', priority: 'medium', status: 'open', control_framework: null })
    })
  })
})
