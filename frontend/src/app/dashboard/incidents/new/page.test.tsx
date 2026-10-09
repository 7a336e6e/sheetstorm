import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import {
  mockApi,
  mockReplace,
  renderTab,
  resetTabTest,
  setPermissions,
} from '@/components/incidents/test-utils'

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('next/navigation', () => require('@/components/incidents/test-utils').navigationMock)

let NewIncidentPage: typeof import('./page').default
beforeAll(async () => {
  ;({ default: NewIncidentPage } = await import('./page'))
})

beforeEach(() => resetTabTest())
afterEach(() => resetTabTest())

const CREATOR = ['incidents:create', 'incidents:read']

function fillTitle(value: string) {
  fireEvent.change(screen.getByLabelText(/title/i), { target: { value } })
}

describe('new incident form', () => {
  it('requires a title of at least 3 characters', async () => {
    setPermissions(CREATOR)
    const api = mockApi()
    renderTab(<NewIncidentPage />)
    fillTitle('ab')
    fireEvent.click(screen.getByRole('button', { name: /create incident/i }))
    expect(await screen.findByText('Title must be at least 3 characters')).toBeTruthy()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('sends TLP (default amber) and the detected time', async () => {
    setPermissions(CREATOR)
    const api = mockApi()
    api.post.mockImplementation((async () => ({ id: 'new-1', incident_number: 9 })) as never)
    renderTab(<NewIncidentPage />)
    fillTitle('Phishing wave')
    fireEvent.change(screen.getByLabelText(/detected at/i), { target: { value: '2026-01-02T03:04:05' } })
    fireEvent.click(screen.getByRole('button', { name: /create incident/i }))
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/incidents',
        expect.objectContaining({ title: 'Phishing wave', tlp: 'amber', detected_at: '2026-01-02T03:04:05.000Z' })
      )
    )
    const body = api.post.mock.calls[0][1] as Record<string, unknown>
    expect(body).not.toHaveProperty('lead_responder_id')
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/dashboard/incidents/new-1'))
  })

  it('omits detected_at when empty (the server defaults it to now)', async () => {
    setPermissions(CREATOR)
    const api = mockApi()
    api.post.mockImplementation((async () => ({ id: 'new-2', incident_number: 10 })) as never)
    renderTab(<NewIncidentPage />)
    fillTitle('Insider')
    fireEvent.click(screen.getByRole('button', { name: /create incident/i }))
    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post.mock.calls[0][1]).not.toHaveProperty('detected_at')
  })

  it('rejects a detected time in the future', async () => {
    setPermissions(CREATOR)
    const api = mockApi()
    renderTab(<NewIncidentPage />)
    fillTitle('Future incident')
    fireEvent.change(screen.getByLabelText(/detected at/i), { target: { value: '2099-01-01T00:00:00' } })
    fireEvent.click(screen.getByRole('button', { name: /create incident/i }))
    expect(await screen.findByText('Detected time cannot be in the future')).toBeTruthy()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('shows the lead responder picker only with users:read', () => {
    setPermissions(CREATOR)
    mockApi()
    const { unmount } = renderTab(<NewIncidentPage />)
    expect(screen.queryByLabelText('Lead responder')).toBeNull()
    unmount()

    setPermissions([...CREATOR, 'users:read'])
    mockApi()
    renderTab(<NewIncidentPage />)
    expect(screen.getByLabelText('Lead responder')).toBeTruthy()
    expect(screen.getByLabelText('TLP')).toBeTruthy()
  })
})
