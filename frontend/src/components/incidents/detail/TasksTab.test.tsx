import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import {
  currentSearch,
  envelope,
  getCalls,
  mockApi,
  renderTab,
  resetTabTest,
  ROLE_PERMISSIONS,
  setPermissions,
  setRole,
} from '../test-utils'

// next/jest does not hoist jest.mock above imports: mock first, then load
// the component dynamically.
// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('../test-utils').navigationMock)

let TasksTab: typeof import('./TasksTab').TasksTab
beforeAll(async () => {
  ;({ TasksTab } = await import('./TasksTab'))
})

const task = {
  id: 't1',
  incident_id: 'i1',
  title: 'Collect memory image',
  status: 'pending',
  priority: 'high',
  created_at: '2026-01-01T00:00:00Z',
  version: 4,
}

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

describe('TasksTab', () => {
  it('Viewer sees tasks but no mutation controls', async () => {
    setRole('viewer')
    mockApi({ '/incidents/i1/tasks': envelope([task]) })
    renderTab(<TasksTab incidentId="i1" />)

    expect(await screen.findByText('Collect memory image')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /add task/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /actions for/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /change status/i })).toBeNull()

    // Comments are readable, but there is no composer.
    fireEvent.click(screen.getByRole('button', { name: 'Expand row' }))
    expect(await screen.findByText('No comments yet')).toBeTruthy()
    expect(screen.queryByRole('textbox', { name: 'Add a comment' })).toBeNull()
  })

  it('tasks:create alone shows the create button but no edit or delete', async () => {
    setPermissions([...ROLE_PERMISSIONS.viewer, 'tasks:create'])
    mockApi({ '/incidents/i1/tasks': envelope([task]) })
    renderTab(<TasksTab incidentId="i1" />)

    expect(await screen.findByRole('button', { name: /add task/i })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /actions for/i })).toBeNull()
  })

  it('requests the paginated endpoint with focus and keeps filters in the URL', async () => {
    setRole('viewer')
    const api = mockApi({ '/incidents/i1/tasks': envelope([task], { focus_found: true }) })
    renderTab(<TasksTab incidentId="i1" focusRowId="t1" />)

    await screen.findByText('Collect memory image')
    const first = getCalls(api.get).find((e) => e.startsWith('/incidents/i1/tasks?'))!
    const q = new URLSearchParams(first.split('?')[1])
    expect(q.get('page')).toBe('1')
    expect(q.get('per_page')).toBe('50')
    expect(q.get('focus')).toBe('t1')

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'memory' } })
    await waitFor(() => expect(currentSearch().get('tasks.q')).toBe('memory'))
  })

  it('Responder deletes with a confirm and If-Match, and toggles status with If-Match', async () => {
    setRole('responder')
    const api = mockApi({ '/incidents/i1/tasks': envelope([task]) })
    renderTab(<TasksTab incidentId="i1" />)

    await screen.findByText('Collect memory image')
    fireEvent.click(screen.getByRole('button', { name: /change status/i }))
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/incidents/i1/tasks/t1', { status: 'in_progress' }, { ifMatch: 4 })
    )

    const row = screen.getByText('Collect memory image').closest('tr')!
    fireEvent.keyDown(row, { key: '.' })
    const menu = await screen.findByRole('menu')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Delete' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/incidents/i1/tasks/t1', undefined, { ifMatch: 4 })
    )
  })

  it('comment delete asks for confirmation', async () => {
    setRole('responder')
    const api = mockApi({
      '/incidents/i1/tasks': envelope([task]),
      '/incidents/i1/tasks/t1/comments': {
        items: [{ id: 'c1', content: 'Imaged WS-01', author: { id: 'u1', name: 'U' }, created_at: '2026-01-01T00:00:00Z' }],
      },
    })
    renderTab(<TasksTab incidentId="i1" />)
    await screen.findByText('Collect memory image')
    fireEvent.click(screen.getByRole('button', { name: 'Expand row' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete comment' }))
    const dialog = await screen.findByRole('dialog')
    expect(api.delete).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/incidents/i1/tasks/t1/comments/c1', undefined, undefined))
  })
})
