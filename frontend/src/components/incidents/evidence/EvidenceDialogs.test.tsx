import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { ApiError } from '@/lib/api'
import { mockApi, renderTab, resetTabTest, setPermissions } from '../test-utils'
import { AddHashDialog } from './AddHashDialog'
import { DisposeVoidDialog } from './DisposeVoidDialog'
import { RegisterEvidenceDialog } from './RegisterEvidenceDialog'
import { ADMIN, makeItem } from './test-fixtures'

const BASE = '/incidents/i1/evidence'

beforeEach(() => {
  resetTabTest()
  setPermissions(ADMIN)
})
afterEach(() => resetTabTest())

describe('DisposeVoidDialog (useConfirm + requireText)', () => {
  const item = makeItem()

  it('void: needs a reason, then the EV number typed to confirm', async () => {
    const api = mockApi()
    const onDone = jest.fn()
    renderTab(<DisposeVoidDialog open onOpenChange={jest.fn()} incidentId="i1" item={item} mode="void" onDone={onDone} />)

    fireEvent.click(screen.getByRole('button', { name: 'Void…' }))
    expect(await screen.findByText('Say why this entry is being voided')).toBeTruthy()
    expect(api.post).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/^reason/i), { target: { value: 'Registered twice' } })
    fireEvent.click(screen.getByRole('button', { name: 'Void…' }))

    // The confirmation stays disabled until the EV number is typed exactly.
    const confirm = (await screen.findAllByRole('dialog')).at(-1)!
    const go = within(confirm).getByRole('button', { name: 'Void' })
    expect((go as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(within(confirm).getByRole('textbox'), { target: { value: 'ev-0001' } })
    expect((go as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(within(confirm).getByRole('textbox'), { target: { value: 'EV-0001' } })
    expect((go as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(go)

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(`${BASE}/ev1/void`, { reason: 'Registered twice' }))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })

  it('dispose: sends method, reason and witness only after the confirmation', async () => {
    const api = mockApi()
    renderTab(<DisposeVoidDialog open onOpenChange={jest.fn()} incidentId="i1" item={item} mode="dispose" />)

    fireEvent.change(screen.getByLabelText(/^method/i), { target: { value: 'destroyed' } })
    fireEvent.change(screen.getByLabelText(/^reason/i), { target: { value: 'Retention period over' } })
    fireEvent.change(screen.getByLabelText(/witness/i), { target: { value: 'K. Lee' } })
    fireEvent.click(screen.getByRole('button', { name: 'Dispose…' }))

    const confirm = (await screen.findAllByRole('dialog')).at(-1)!
    expect(api.post).not.toHaveBeenCalled()
    fireEvent.change(within(confirm).getByRole('textbox'), { target: { value: 'EV-0001' } })
    fireEvent.click(within(confirm).getByRole('button', { name: 'Dispose' }))

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(`${BASE}/ev1/dispose`, {
        method: 'destroyed',
        reason: 'Retention period over',
        witness_name: 'K. Lee',
      })
    )
  })

  it('cancelling the confirmation sends nothing', async () => {
    const api = mockApi()
    renderTab(<DisposeVoidDialog open onOpenChange={jest.fn()} incidentId="i1" item={item} mode="void" />)
    fireEvent.change(screen.getByLabelText(/^reason/i), { target: { value: 'oops' } })
    fireEvent.click(screen.getByRole('button', { name: 'Void…' }))
    const confirm = (await screen.findAllByRole('dialog')).at(-1)!
    fireEvent.click(within(confirm).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.getAllByRole('dialog')).toHaveLength(1))
    expect(api.post).not.toHaveBeenCalled()
  })

  it('shows the 409 legal_hold refusal inline', async () => {
    const api = mockApi()
    api.post.mockRejectedValueOnce(new ApiError(409, 'EV-0001 is under legal hold', { code: 'legal_hold' }) as never)
    renderTab(<DisposeVoidDialog open onOpenChange={jest.fn()} incidentId="i1" item={item} mode="dispose" />)

    fireEvent.change(screen.getByLabelText(/^reason/i), { target: { value: 'done' } })
    fireEvent.click(screen.getByRole('button', { name: 'Dispose…' }))
    const confirm = (await screen.findAllByRole('dialog')).at(-1)!
    fireEvent.change(within(confirm).getByRole('textbox'), { target: { value: 'EV-0001' } })
    fireEvent.click(within(confirm).getByRole('button', { name: 'Dispose' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/under legal hold.*Release the hold first/)
  })

  it('warns up front when the item is already under hold', () => {
    mockApi()
    renderTab(
      <DisposeVoidDialog open onOpenChange={jest.fn()} incidentId="i1" item={makeItem({ under_legal_hold: true })} mode="dispose" />
    )
    expect(screen.getByText(/under legal hold, so the server will refuse this/i)).toBeTruthy()
  })
})

describe('RegisterEvidenceDialog', () => {
  const sha = 'b'.repeat(64)

  it('requires a title and validates hashes per algorithm length before sending', async () => {
    const api = mockApi()
    renderTab(<RegisterEvidenceDialog open onOpenChange={jest.fn()} incidentId="i1" />)

    fireEvent.click(screen.getByRole('button', { name: 'Register' }))
    expect(await screen.findByText('A title is required')).toBeTruthy()
    expect(api.post).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/^title/i), { target: { value: 'Seized USB' } })
    fireEvent.change(screen.getByLabelText('Hash 1 value'), { target: { value: 'abc123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))
    expect(await screen.findByText(/SHA-256 must be 64 characters \(got 6\)/)).toBeTruthy()
    expect(api.post).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Hash 1 value'), { target: { value: sha.toUpperCase() } })
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))
    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith(BASE, {
      title: 'Seized USB',
      evidence_type: 'digital_file',
      acquisition_hashes: [{ algorithm: 'sha256', value: sha, source: 'tool_reported' }],
    })
  })

  it('selects the algorithm a pasted hash’s length points at', async () => {
    mockApi()
    renderTab(<RegisterEvidenceDialog open onOpenChange={jest.fn()} incidentId="i1" />)
    fireEvent.change(screen.getByLabelText('Hash 1 value'), { target: { value: 'c'.repeat(32) } })
    expect((screen.getByLabelText('Hash 1 algorithm') as HTMLSelectElement).value).toBe('md5')
  })

  it('refuses an acquisition time in the future', async () => {
    const api = mockApi()
    renderTab(<RegisterEvidenceDialog open onOpenChange={jest.fn()} incidentId="i1" />)
    fireEvent.change(screen.getByLabelText(/^title/i), { target: { value: 'Phone' } })
    fireEvent.change(screen.getByLabelText(/acquired at/i), { target: { value: '2099-01-01T10:00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))
    expect(await screen.findByText('Acquisition time cannot be in the future')).toBeTruthy()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('edit sends only the changed fields with If-Match', async () => {
    const api = mockApi()
    const item = makeItem({ version: 7 })
    renderTab(<RegisterEvidenceDialog open onOpenChange={jest.fn()} incidentId="i1" item={item} />)

    expect(screen.queryByRole('heading', { name: 'Hashes' })).toBeNull() // hashes are changed through their own action
    expect((screen.getByLabelText(/storage location/i) as HTMLInputElement).disabled).toBe(true)

    fireEvent.change(screen.getByLabelText(/^title/i), { target: { value: 'CFO laptop image (verified)' } })
    fireEvent.change(screen.getByLabelText(/serial number/i), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(api.patch).toHaveBeenCalled())
    expect(api.patch).toHaveBeenCalledWith(
      `${BASE}/ev1`,
      { title: 'CFO laptop image (verified)', serial_number: null },
      { ifMatch: 7 }
    )
  })

  it('edit with no change closes without a request', async () => {
    const api = mockApi()
    const onOpenChange = jest.fn()
    renderTab(<RegisterEvidenceDialog open onOpenChange={onOpenChange} incidentId="i1" item={makeItem()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(api.patch).not.toHaveBeenCalled()
  })
})

describe('AddHashDialog (write-once hashes)', () => {
  it('a second value for an algorithm must supersede the first, with a reason', async () => {
    const api = mockApi()
    renderTab(<AddHashDialog open onOpenChange={jest.fn()} incidentId="i1" item={makeItem()} />)

    fireEvent.change(screen.getByLabelText('Hash 1 value'), { target: { value: 'd'.repeat(64) } })
    expect(screen.getByText(/already recorded\. This entry will supersede it/i)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Supersede hash' }))
    expect(await screen.findByText('Say why the recorded value is being replaced')).toBeTruthy()
    expect(api.post).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/reason for the correction/i), { target: { value: 'Typo in the lab sheet' } })
    fireEvent.click(screen.getByRole('button', { name: 'Supersede hash' }))
    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith(`${BASE}/ev1/hashes`, {
      algorithm: 'sha256',
      value: 'd'.repeat(64),
      source: 'computed_in_lab',
      supersedes: 'a'.repeat(64),
      reason: 'Typo in the lab sheet',
    })
  })

  it('a new algorithm is a plain add (no supersede, no reason)', async () => {
    const api = mockApi()
    renderTab(<AddHashDialog open onOpenChange={jest.fn()} incidentId="i1" item={makeItem()} />)
    fireEvent.change(screen.getByLabelText('Hash 1 algorithm'), { target: { value: 'sha1' } })
    fireEvent.change(screen.getByLabelText('Hash 1 value'), { target: { value: 'e'.repeat(40) } })
    fireEvent.click(screen.getByRole('button', { name: 'Record hash' }))
    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith(`${BASE}/ev1/hashes`, {
      algorithm: 'sha1',
      value: 'e'.repeat(40),
      source: 'computed_in_lab',
      supersedes: undefined,
      reason: undefined,
    })
  })
})
