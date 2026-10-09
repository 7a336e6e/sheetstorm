import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
// Types jest-dom matchers on the @jest/globals `expect`.
import '@testing-library/jest-dom/jest-globals'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import api from '@/lib/api'
import { clearCache } from '@/lib/query-cache'
import { useNotificationStore } from '@/lib/feature-stores'
import type { Notification } from '@/types'

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  usePathname: () => '/dashboard',
  useSearchParams: () => new URLSearchParams(),
}))

let NotificationPanel: typeof import('./NotificationPanel')['NotificationPanel']
beforeAll(async () => {
  ;({ NotificationPanel } = await import('./NotificationPanel'))
})

const base = { is_read: false, created_at: '2026-10-01T10:00:00Z' }
const notifications: Notification[] = [
  { ...base, id: 'n1', type: 'task_assigned', title: 'Task assigned', action_url: '/dashboard/incidents/i1?tab=tasks&row=t1' },
  { ...base, id: 'n2', type: 'system', title: 'Evil link', action_url: 'javascript:alert(1)' },
  {
    ...base,
    id: 'n3',
    type: 'incident_updated',
    title: 'Offsite link',
    action_url: 'https://evil.example/x',
    incident: { id: 'i9', title: 'Nine', incident_number: 9 },
  },
  { ...base, id: 'n4', type: 'mystery_type', title: 'Read already', is_read: true },
]

type GetFn = (endpoint: string, opts?: { signal?: AbortSignal }) => Promise<unknown>
let getSpy: jest.Mock<GetFn>

beforeEach(() => {
  clearCache()
  useNotificationStore.setState({ unreadCount: 3 })
  getSpy = jest.fn<GetFn>(async (endpoint) => {
    if (endpoint.startsWith('/notifications/unread-count')) return { unread_count: 3 }
    const page = Number(new URLSearchParams(endpoint.split('?')[1]).get('page') ?? 1)
    return page === 1
      ? { items: notifications, total: 21, page: 1, per_page: 20, pages: 2, unread_count: 3 }
      : { items: [{ ...base, id: 'n21', type: 'mention', title: 'Older one' }], total: 21, page: 2, per_page: 20, pages: 2 }
  })
  jest.spyOn(api, 'get').mockImplementation(getSpy as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
})

describe('NotificationPanel', () => {
  it('links rows only to guarded internal paths', async () => {
    render(<NotificationPanel open onClose={jest.fn()} />)
    await screen.findByText('Task assigned')

    expect(screen.getByText('Task assigned').closest('a')).toHaveAttribute('href', '/dashboard/incidents/i1?tab=tasks&row=t1')
    // javascript: URL with no incident → not a link at all.
    expect(screen.getByText('Evil link').closest('a')).toBeNull()
    expect(screen.getByText('Evil link').closest('button')).not.toBeNull()
    // Off-site URL → falls back to the incident.
    expect(screen.getByText('Offsite link').closest('a')).toHaveAttribute('href', '/dashboard/incidents/i9')
    expect(document.querySelector('a[href^="javascript"], a[href^="http"]')).toBeNull()
  })

  it('requests the contract page size and loads more on demand', async () => {
    render(<NotificationPanel open onClose={jest.fn()} />)
    await screen.findByText('Task assigned')
    const listCall = getSpy.mock.calls.find(([e]) => e.startsWith('/notifications?'))!
    const p = new URLSearchParams(listCall[0].split('?')[1])
    expect(p.get('per_page')).toBe('20')
    expect(p.get('page')).toBe('1')

    fireEvent.click(screen.getByRole('button', { name: /load more/i }))
    expect(await screen.findByText('Older one')).toBeInTheDocument()
    expect(screen.getByText('Task assigned')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /load more/i })).toBeNull()
  })

  it('marks a row read and closes when its link is followed', async () => {
    const post = jest.spyOn(api, 'post').mockResolvedValue({} as never)
    const onClose = jest.fn()
    render(<NotificationPanel open onClose={onClose} />)
    // jsdom cannot navigate: stop the anchor's default action after React ran.
    const block = (e: Event) => e.preventDefault()
    document.addEventListener('click', block)
    fireEvent.click(await screen.findByText('Task assigned'))
    document.removeEventListener('click', block)
    expect(onClose).toHaveBeenCalled()
    await waitFor(() => expect(post).toHaveBeenCalledWith('/notifications/n1/read'))
    await waitFor(() => expect(useNotificationStore.getState().unreadCount).toBe(2))
  })

  it('shows the badge from the store and marks all read', async () => {
    const post = jest.spyOn(api, 'post').mockResolvedValue({} as never)
    render(<NotificationPanel open onClose={jest.fn()} />)
    await screen.findByText('Task assigned')
    fireEvent.click(screen.getByRole('button', { name: /mark all read/i }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/notifications/read-all'))
    await waitFor(() => expect(useNotificationStore.getState().unreadCount).toBe(0))
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
  })

  it('renders nothing and fetches nothing while closed', () => {
    render(<NotificationPanel open={false} onClose={jest.fn()} />)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(getSpy.mock.calls.filter(([e]) => e.startsWith('/notifications?'))).toHaveLength(0)
  })
})
