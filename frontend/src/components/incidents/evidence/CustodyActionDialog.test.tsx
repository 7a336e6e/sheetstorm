import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { ApiError } from '@/lib/api'
import { envelope, mockApi, renderTab, resetTabTest, setPermissions } from '../test-utils'
import { CustodyActionDialog } from './CustodyActionDialog'
import { RESPONDER, makeEntry, makeItem } from './test-fixtures'

const TRANSFER = '/incidents/i1/evidence/ev1/custody/transfer'
const CHECK_OUT = '/incidents/i1/evidence/ev1/custody/check-out'
const CHECK_IN = '/incidents/i1/evidence/ev1/custody/check-in'

const party = {
  id: 'p1',
  name: 'Jane Roe',
  organization_name: 'Roe & Partners LLP',
  role: 'counsel',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
}
const colleague = { id: 'u2', name: 'Bob', email: 'bob@x.test', roles: [], is_active: true, created_at: '2026-01-01T00:00:00Z' }

beforeEach(() => {
  resetTabTest()
  setPermissions(RESPONDER)
})
afterEach(() => resetTabTest())

function renderDialog(mode: 'transfer' | 'check_out' | 'check_in', extra: Partial<React.ComponentProps<typeof CustodyActionDialog>> = {}) {
  const onOpenChange = jest.fn()
  const onDone = jest.fn()
  const item = makeItem(mode === 'check_in' ? { custody_state: 'checked_out' } : {})
  renderTab(
    <CustodyActionDialog open onOpenChange={onOpenChange} incidentId="i1" item={item} mode={mode} onDone={onDone} {...extra} />
  )
  return { onOpenChange, onDone }
}

async function pickFirstOption(name: string) {
  const input = screen.getByRole('combobox', { name })
  fireEvent.focus(input)
  await screen.findAllByRole('option')
  fireEvent.keyDown(input, { key: 'Enter' })
}

describe('CustodyActionDialog: transfer', () => {
  it('requires a recipient, a reason and a method before anything is sent', async () => {
    const api = mockApi({ '/custody-parties': envelope([party]) })
    renderDialog('transfer')

    fireEvent.change(screen.getByLabelText(/transfer method/i), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Transfer' }))

    expect(await screen.findByText(/choose the receiving party/i)).toBeTruthy()
    expect(screen.getByText(/give the reason for the transfer/i)).toBeTruthy()
    expect(screen.getByText(/choose how it is being delivered/i)).toBeTruthy()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('sends exactly one recipient (a saved party) with method, reason and tracking', async () => {
    const api = mockApi({ '/custody-parties': envelope([party]) })
    const { onDone } = renderDialog('transfer')

    await pickFirstOption('Recipient party')
    fireEvent.change(screen.getByLabelText(/transfer method/i), { target: { value: 'courier' } })
    fireEvent.change(screen.getByLabelText(/^reason/i), { target: { value: 'Released to counsel' } })
    fireEvent.change(screen.getByLabelText(/tracking number/i), { target: { value: 'TRK-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Transfer' }))

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    expect(api.post).toHaveBeenCalledWith(TRANSFER, {
      to_party_id: 'p1',
      transfer_method: 'courier',
      reason: 'Released to counsel',
      tracking_number: 'TRK-1',
    })
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })

  it('creates a new party in place (new_party only, no ids)', async () => {
    const api = mockApi()
    renderDialog('transfer')

    fireEvent.click(screen.getByRole('radio', { name: 'New party' }))
    fireEvent.change(screen.getByLabelText(/party name/i), { target: { value: 'Acme Forensics' } })
    fireEvent.change(screen.getByLabelText(/^role/i), { target: { value: 'third_party_lab' } })
    fireEvent.change(screen.getByLabelText(/^reason/i), { target: { value: 'Deep analysis' } })
    fireEvent.click(screen.getByRole('button', { name: 'Transfer' }))

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    const [, body] = api.post.mock.calls[0] as [string, Record<string, unknown>]
    expect(body.new_party).toEqual({ name: 'Acme Forensics', role: 'third_party_lab' })
    expect(body).not.toHaveProperty('to_party_id')
    expect(body).not.toHaveProperty('to_user_id')
    expect(body.transfer_method).toBe('hand_delivery')
  })

  it('shows recipient_no_access inline and stays open', async () => {
    const api = mockApi({ '/users': envelope([colleague]) })
    api.post.mockRejectedValueOnce(
      new ApiError(400, 'The recipient cannot access this incident', { code: 'recipient_no_access' }) as never
    )
    const { onOpenChange } = renderDialog('transfer')

    fireEvent.click(screen.getByRole('radio', { name: 'Colleague' }))
    await pickFirstOption('Recipient colleague')
    fireEvent.change(screen.getByLabelText(/^reason/i), { target: { value: 'Hand-off' } })
    fireEvent.click(screen.getByRole('button', { name: 'Transfer' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/cannot access this incident/i)
    expect(alert.textContent).toMatch(/add them to the incident/i)
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })

  it('explains an invalid custody transition inline', async () => {
    const api = mockApi({ '/custody-parties': envelope([party]) })
    api.post.mockRejectedValueOnce(
      new ApiError(409, 'Cannot transfer an item that is disposed', { code: 'invalid_custody_transition' }) as never
    )
    renderDialog('transfer')
    await pickFirstOption('Recipient party')
    fireEvent.change(screen.getByLabelText(/^reason/i), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Transfer' }))
    expect((await screen.findByRole('alert')).textContent).toMatch(/Cannot transfer an item that is disposed/)
  })

  it('offers "Acknowledge now" once the transfer is recorded', async () => {
    const api = mockApi({ '/custody-parties': envelope([party]) })
    const entry = makeEntry({ id: 'c9', action: 'transfer' })
    api.post.mockResolvedValueOnce({ ledger_entries: [entry] } as never)
    const onAcknowledge = jest.fn()
    renderDialog('transfer', { onAcknowledge })

    await pickFirstOption('Recipient party')
    fireEvent.change(screen.getByLabelText(/^reason/i), { target: { value: 'To counsel' } })
    fireEvent.click(screen.getByRole('button', { name: 'Transfer' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/EV-0001 transferred/)).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Acknowledge now' }))
    expect(onAcknowledge).toHaveBeenCalledWith(entry)
  })
})

describe('CustodyActionDialog: check out / check in', () => {
  it('check out sends a colleague, the purpose and an optional method', async () => {
    const api = mockApi({ '/users': envelope([colleague]) })
    renderDialog('check_out')

    await pickFirstOption('Recipient colleague')
    fireEvent.change(screen.getByLabelText(/^purpose/i), { target: { value: 'Imaging in the lab' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check out' }))

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith(CHECK_OUT, {
      to_user_id: 'u2',
      purpose: 'Imaging in the lab',
      transfer_method: undefined,
      expected_return_at: null,
    })
  })

  it('check in needs a location and an explicit seal state', async () => {
    const api = mockApi()
    renderDialog('check_in')

    fireEvent.click(screen.getByRole('button', { name: 'Check in' }))
    expect(await screen.findByText(/where is the item stored now/i)).toBeTruthy()
    expect(screen.getByText(/state whether the seal was intact/i)).toBeTruthy()
    expect(api.post).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/storage location/i), { target: { value: 'Locker 9' } })
    fireEvent.change(screen.getByLabelText(/seal intact/i), { target: { value: 'no' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check in' }))

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith(CHECK_IN, {
      storage_location: 'Locker 9',
      seal_intact: false,
      condition_notes: undefined,
      seal_number: undefined,
      received_from_party_id: undefined,
    })
  })
})
