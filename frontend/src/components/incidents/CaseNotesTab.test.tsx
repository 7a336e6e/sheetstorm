import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import {
  currentSearch,
  envelope,
  getCalls,
  mockApi,
  renderTab,
  resetTabTest,
  setRole,
} from './test-utils'

// next/jest does not hoist jest.mock above imports: mock first, then load
// the component dynamically.
// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('./test-utils').navigationMock)

let CaseNotesTab: typeof import('./CaseNotesTab').CaseNotesTab
beforeAll(async () => {
  ;({ CaseNotesTab } = await import('./CaseNotesTab'))
})

const note = {
  id: 'n1',
  incident_id: 'i1',
  title: 'Initial triage',
  content: 'Beacon to 203.0.113.7',
  category: 'finding',
  is_pinned: false,
  author: { id: 'someone-else', name: 'Ana' },
  created_at: '2026-01-01T00:00:00Z',
  version: 2,
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('CaseNotesTab', () => {
  it('Viewer sees notes but no mutation controls', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/case-notes': envelope([note]) })
    renderTab(<CaseNotesTab incidentId="i1" />)

    expect(await screen.findByText('Initial triage')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /add note/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /edit note/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /pin note/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /delete note/i })).toBeNull()
  })

  it('pages through the endpoint with focus, highlights the note and keeps search in the URL', async () => {
    setRole('viewer')
    const api = mockApi({ '/incidents/i1/case-notes': envelope([note], { total: 120, pages: 3, focus_found: true }) })
    renderTab(<CaseNotesTab incidentId="i1" focusRowId="n1" />)

    await screen.findByText('Initial triage')
    const first = getCalls(api.get).find((e) => e.startsWith('/incidents/i1/case-notes?'))!
    const q = new URLSearchParams(first.split('?')[1])
    expect(q.get('page')).toBe('1')
    expect(q.get('per_page')).toBe('50')
    expect(q.get('focus')).toBe('n1')
    expect(screen.getByText('1–50 of 120')).toBeTruthy()
    expect(screen.getByTestId('case-note').className).toContain('ring-1')

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'beacon' } })
    await waitFor(() => expect(currentSearch().get('notes.q')).toBe('beacon'))
  })

  it('tells the user when the linked note was not found', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/case-notes': envelope([note], { focus_found: false }) })
    renderTab(<CaseNotesTab incidentId="i1" focusRowId="gone" />)
    expect(await screen.findByText(/linked note was not found/i)).toBeTruthy()
  })

  it('Responder pins and deletes with If-Match (delete confirms)', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/case-notes': envelope([note]) })
    renderTab(<CaseNotesTab incidentId="i1" />)

    expect(await screen.findByRole('button', { name: /add note/i })).toBeTruthy()
    fireEvent.click(await screen.findByRole('button', { name: 'Pin note' }))
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/incidents/i1/case-notes/n1', { is_pinned: true }, { ifMatch: 2 })
    )

    fireEvent.click(screen.getByRole('button', { name: 'Delete note' }))
    const dialog = await screen.findByRole('dialog')
    expect(api.delete).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/incidents/i1/case-notes/n1', undefined, { ifMatch: 2 })
    )
  })
})
