import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { dispatchChange } from '@/lib/realtime/live'
import {
  currentSearch,
  envelope,
  getCalls,
  mockApi,
  renderTab,
  resetTabTest,
  setPermissions,
} from '../test-utils'
import { ADMIN, READ, RESPONDER, makeCustody, makeDetail, makeItem, makeVerification } from './test-fixtures'

// next/jest does not hoist jest.mock above imports: mock first, then load
// the component dynamically.
// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('../test-utils').navigationMock)

let EvidenceTab: typeof import('./EvidenceTab').EvidenceTab
beforeAll(async () => {
  ;({ EvidenceTab } = await import('./EvidenceTab'))
})

const LIST = '/incidents/i1/evidence'
const held = makeItem({ id: 'ev2', sequence_number: 2, evidence_number: 'EV-0002', title: 'Seized phone', custody_state: 'checked_out', under_legal_hold: true, is_locked: true })
const voided = makeItem({ id: 'ev3', sequence_number: 3, evidence_number: 'EV-0003', title: 'Entered twice', voided_at: '2026-01-02T00:00:00Z' })

function routes(items = [makeItem(), held]) {
  return {
    [LIST]: envelope(items),
    [`${LIST}/custody/verify`]: makeVerification(),
    [`${LIST}/ev1`]: makeDetail(),
    [`${LIST}/ev1/custody`]: makeCustody(),
  }
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

async function openRowMenu(title: string) {
  const tr = (await screen.findByText(title)).closest('tr')!
  fireEvent.keyDown(tr, { key: '.' })
  return within(await screen.findByRole('menu'))
}

describe('EvidenceTab permission gating', () => {
  it('read-only users (artifacts:read) see the register but no write, export or row actions', async () => {
    setPermissions(READ)
    mockApi(routes())
    renderTab(<EvidenceTab incidentId="i1" />)

    expect(await screen.findByText('CFO laptop image')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /register evidence/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /upload file/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /export register/i })).toBeNull()

    const menu = await openRowMenu('CFO laptop image')
    expect(menu.getAllByRole('menuitem').map((m) => m.textContent)).toEqual(['Open details'])
  })

  it('responders can register, upload and export, and run custody actions, but not dispose or void', async () => {
    setPermissions(RESPONDER)
    mockApi(routes())
    renderTab(<EvidenceTab incidentId="i1" />)

    expect(await screen.findByRole('button', { name: /register evidence/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /upload file/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /export register/i })).toBeTruthy()

    const menu = await openRowMenu('CFO laptop image')
    const labels = menu.getAllByRole('menuitem').map((m) => m.textContent)
    expect(labels).toEqual(['Open details', 'Check out', 'Check in', 'Transfer'])
    // The state machine: an item in storage can be checked out but not checked in.
    expect(menu.getByRole('menuitem', { name: 'Check out' }).getAttribute('aria-disabled')).not.toBe('true')
    expect(menu.getByRole('menuitem', { name: 'Check in' }).getAttribute('aria-disabled')).toBe('true')
  })

  it('administrators (artifacts:delete) also get Dispose and Void', async () => {
    setPermissions(ADMIN)
    mockApi(routes())
    renderTab(<EvidenceTab incidentId="i1" />)

    const menu = await openRowMenu('CFO laptop image')
    expect(menu.getAllByRole('menuitem').map((m) => m.textContent)).toEqual([
      'Open details',
      'Check out',
      'Check in',
      'Transfer',
      'Dispose',
      'Void',
    ])
  })

  it('disables Dispose and Void while the item is under legal hold', async () => {
    setPermissions(ADMIN)
    mockApi(routes())
    renderTab(<EvidenceTab incidentId="i1" />)

    const menu = await openRowMenu('Seized phone')
    expect(menu.getByRole('menuitem', { name: 'Dispose' }).getAttribute('aria-disabled')).toBe('true')
    expect(menu.getByRole('menuitem', { name: 'Void' }).getAttribute('aria-disabled')).toBe('true')
    expect(menu.getByRole('menuitem', { name: 'Check in' }).getAttribute('aria-disabled')).not.toBe('true')
  })

  it('exports the register only with incidents:export', async () => {
    setPermissions([...READ, 'artifacts:upload'])
    mockApi(routes())
    renderTab(<EvidenceTab incidentId="i1" />)
    await screen.findByText('CFO laptop image')
    expect(screen.getByRole('button', { name: /register evidence/i })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /export register/i })).toBeNull()
  })
})

describe('EvidenceTab data', () => {
  it('requests the paginated endpoint with the evidence contract', async () => {
    setPermissions(READ)
    const api = mockApi(routes())
    renderTab(<EvidenceTab incidentId="i1" focusRowId="ev1" />)
    // A deep link (?row=) also opens that item's drawer.
    expect((await screen.findAllByText('CFO laptop image')).length).toBeGreaterThan(0)
    expect(await screen.findByRole('dialog')).toBeTruthy()

    const first = getCalls(api.get).find((e) => e.startsWith(`${LIST}?`))!
    const q = new URLSearchParams(first.split('?')[1])
    expect(q.get('page')).toBe('1')
    expect(q.get('sort')).toBe('sequence_number')
    expect(q.get('focus')).toBe('ev1')
  })

  it('merges live evidence_item changes into the register', async () => {
    setPermissions(READ)
    mockApi(routes())
    renderTab(<EvidenceTab incidentId="i1" />)
    await screen.findByText('CFO laptop image')

    act(() => {
      dispatchChange({
        incident_id: 'i1',
        entity: 'evidence_item',
        op: 'updated',
        id: 'ev1',
        version: 4,
        data: { ...makeItem(), title: 'CFO laptop image (re-imaged)', version: 4 },
      })
    })
    expect(await screen.findByText('CFO laptop image (re-imaged)')).toBeTruthy()
  })

  it('keeps filters and search in the URL under the tab key', async () => {
    setPermissions(READ)
    mockApi(routes())
    renderTab(<EvidenceTab incidentId="i1" />)
    await screen.findByText('CFO laptop image')

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'EV-0002' } })
    await waitFor(() => expect(currentSearch().get('evidence.q')).toBe('EV-0002'))

    fireEvent.click(screen.getByRole('switch', { name: /include voided/i }))
    await waitFor(() => expect(currentSearch().get('evidence.f.include_voided')).toBe('true'))
  })

  it('renders hold, voided and derived markers, and a legacy chain badge', async () => {
    setPermissions(READ)
    mockApi({
      ...routes([makeItem({ parent: { id: 'p', evidence_number: 'EV-0009', title: 'Source', evidence_type: 'storage_media', voided: false } }), held, voided]),
      [`${LIST}/custody/verify`]: makeVerification({ status: 'intact_with_unsigned_legacy' }),
    })
    renderTab(<EvidenceTab incidentId="i1" />)

    await screen.findByText('CFO laptop image')
    expect(screen.getByText(/from EV-0009/)).toBeTruthy()
    expect(screen.getByText('Under legal hold')).toBeTruthy()
    expect(within(screen.getByText('Entered twice').closest('tr')!).getByText('Voided')).toBeTruthy()
    await waitFor(() =>
      expect(screen.getAllByRole('button').some((b) => b.getAttribute('data-status') === 'intact_with_unsigned_legacy')).toBe(true)
    )
  })

  it('warns when the incident ledger fails verification and marks the affected item', async () => {
    setPermissions(READ)
    mockApi({
      ...routes(),
      [`${LIST}/custody/verify`]: makeVerification({
        status: 'broken',
        breaks: [{ seq: 2, id: 'c2', reason: 'prev_hash_mismatch', chain: 'item', evidence_item_id: 'ev1' }],
        items: { ev1: { evidence_number: 'EV-0001', length: 2, head_seq: 2, head_hash: 'f'.repeat(64), breaks: [{ seq: 2, id: 'c2', reason: 'prev_hash_mismatch' }] } },
      }),
    })
    renderTab(<EvidenceTab incidentId="i1" />)

    expect((await screen.findByRole('alert')).textContent).toMatch(/failed verification \(1 problem\)/)
    expect(screen.getByText('Custody chain broken')).toBeTruthy()
  })

  it('opens the item drawer from a row, with the custody timeline', async () => {
    setPermissions(READ)
    const api = mockApi(routes())
    renderTab(<EvidenceTab incidentId="i1" />)

    fireEvent.click((await screen.findByText('CFO laptop image')).closest('tr')!)
    const drawer = await screen.findByRole('dialog')
    expect(await within(drawer).findByRole('list', { name: 'Chain of custody' })).toBeTruthy()
    expect(within(within(drawer).getByRole('list', { name: 'Chain of custody' })).getByText('Registered')).toBeTruthy()
    expect(getCalls(api.get)).toContain(`${LIST}/ev1`)
    // Read-only: no actions menu, no hold controls.
    expect(within(drawer).queryByRole('button', { name: /actions for/i })).toBeNull()
    expect(within(drawer).queryByRole('button', { name: /place legal hold/i })).toBeNull()
    expect(within(drawer).queryByRole('button', { name: /record hash/i })).toBeNull()
  })

  it('shows write actions in the drawer to responders and hold controls only to managers', async () => {
    setPermissions(RESPONDER)
    mockApi(routes())
    const { unmount } = renderTab(<EvidenceTab incidentId="i1" />)
    fireEvent.click((await screen.findByText('CFO laptop image')).closest('tr')!)
    const drawer = await screen.findByRole('dialog')
    expect(await within(drawer).findByRole('button', { name: /actions for ev-0001/i })).toBeTruthy()
    expect(within(drawer).getAllByRole('button', { name: /record hash/i }).length).toBeGreaterThan(0)
    expect(within(drawer).queryByRole('button', { name: /place legal hold/i })).toBeNull()
    unmount()
    resetTabTest()

    setPermissions(ADMIN)
    mockApi(routes())
    renderTab(<EvidenceTab incidentId="i1" />)
    fireEvent.click((await screen.findByText('CFO laptop image')).closest('tr')!)
    const adminDrawer = await screen.findByRole('dialog')
    expect(await within(adminDrawer).findByRole('button', { name: /place legal hold on ev-0001/i })).toBeTruthy()
  })
})
