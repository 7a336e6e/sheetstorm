import { afterEach, beforeEach, describe, expect, it } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { mockApi, renderTab, resetTabTest, setPermissions } from '../test-utils'
import { HOLD_PERMISSION, LegalHoldControl, holdKind } from './LegalHoldControl'
import { ADMIN, READ } from './test-fixtures'

const HOLD = '/incidents/i1/evidence/ev1/legal-hold'
const NOW = Date.parse('2026-06-01T12:00:00Z')
const future = '2099-01-01T00:00:00Z'

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('holdKind', () => {
  it('classifies indefinite, timed, expired and inherited holds', () => {
    expect(holdKind({ is_locked: true }, NOW)).toBe('indefinite')
    expect(holdKind({ legal_hold_until: '2026-07-01T00:00:00Z', under_legal_hold: true }, NOW)).toBe('until')
    expect(holdKind({ legal_hold_until: '2026-05-01T00:00:00Z' }, NOW)).toBe('none')
    expect(holdKind({ under_legal_hold: true }, NOW)).toBe('inherited')
    expect(holdKind({}, NOW)).toBe('none')
  })

  it('needs artifacts:delete to manage (read-only elsewhere)', () => {
    expect(HOLD_PERMISSION).toBe('artifacts:delete')
  })
})

describe('LegalHoldControl: read-only users', () => {
  it('shows the state without any controls', () => {
    setPermissions(READ)
    renderTab(<LegalHoldControl kind="evidence" incidentId="i1" id="ev1" item={{ is_locked: true, under_legal_hold: true }} label="EV-0001" />)
    expect(screen.getByText('Legal hold')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('shows an inherited hold as coming from the parent', () => {
    setPermissions(READ)
    renderTab(<LegalHoldControl kind="evidence" incidentId="i1" id="ev1" item={{ under_legal_hold: true }} />)
    expect(screen.getByText('Held via parent item')).toBeTruthy()
  })

  it('shows "No hold" when free', () => {
    setPermissions(READ)
    renderTab(<LegalHoldControl kind="evidence" incidentId="i1" id="ev1" item={{}} />)
    expect(screen.getByText('No hold')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })
})

describe('LegalHoldControl: managers', () => {
  it('places an indefinite hold on an evidence item', async () => {
    setPermissions(ADMIN)
    const api = mockApi()
    renderTab(<LegalHoldControl kind="evidence" incidentId="i1" id="ev1" item={{}} label="EV-0001" />)

    fireEvent.click(screen.getByRole('button', { name: 'Place legal hold on EV-0001' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/reason/i), { target: { value: 'Litigation 24-113' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Place hold' }))

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(HOLD, { hold: true, until: undefined, reason: 'Litigation 24-113' }))
  })

  it('a timed hold needs a future end', async () => {
    setPermissions(ADMIN)
    const api = mockApi()
    renderTab(<LegalHoldControl kind="evidence" incidentId="i1" id="ev1" item={{}} label="EV-0001" />)

    fireEvent.click(screen.getByRole('button', { name: 'Place legal hold on EV-0001' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('radio', { name: 'Until a date' }))

    fireEvent.click(within(dialog).getByRole('button', { name: 'Place hold' }))
    expect(await within(dialog).findByText('Choose when the hold ends')).toBeTruthy()

    const end = within(dialog).getByLabelText(/hold ends/i)
    fireEvent.change(end, { target: { value: '2000-01-01T10:00' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Place hold' }))
    expect(await within(dialog).findByText('The end must be in the future')).toBeTruthy()
    expect(api.post).not.toHaveBeenCalled()

    fireEvent.change(end, { target: { value: '2099-01-01T10:00' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Place hold' }))
    await waitFor(() => expect(api.post).toHaveBeenCalled())
    const [path, body] = api.post.mock.calls[0] as [string, { hold: boolean; until: string }]
    expect(path).toBe(HOLD)
    expect(body.hold).toBe(true)
    expect(body.until).toMatch(/^2099-01-01T/)
  })

  it('releases after a confirmation', async () => {
    setPermissions(ADMIN)
    const api = mockApi()
    renderTab(<LegalHoldControl kind="evidence" incidentId="i1" id="ev1" item={{ is_locked: true, under_legal_hold: true }} label="EV-0001" />)

    expect(screen.queryByRole('button', { name: /place legal hold/i })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Release legal hold on EV-0001' }))
    const confirm = await screen.findByRole('dialog')
    expect(api.post).not.toHaveBeenCalled()
    fireEvent.click(within(confirm).getByRole('button', { name: 'Release hold' }))

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(HOLD, { hold: false }))
  })

  it('does not release when the confirmation is cancelled', async () => {
    setPermissions(ADMIN)
    const api = mockApi()
    renderTab(<LegalHoldControl kind="evidence" incidentId="i1" id="ev1" item={{ legal_hold_until: future }} label="EV-0001" />)

    fireEvent.click(screen.getByRole('button', { name: 'Release legal hold on EV-0001' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(api.post).not.toHaveBeenCalled()
  })

  it('holds a stored file through the artifact route', async () => {
    setPermissions(ADMIN)
    const api = mockApi()
    renderTab(<LegalHoldControl kind="artifact" incidentId="i1" id="a1" item={{}} label="disk.E01" compact />)

    fireEvent.click(screen.getByRole('button', { name: 'Place legal hold on disk.E01' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Place hold' }))
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/incidents/i1/artifacts/a1/legal-hold', { hold: true, until: undefined, reason: undefined })
    )
  })
})
