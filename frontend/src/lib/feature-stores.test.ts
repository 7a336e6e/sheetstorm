import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import api from './api'
import * as cache from './query-cache'
import { notificationHref, safeDashboardHref, useNotificationStore } from './feature-stores'

describe('safeDashboardHref (notification open-redirect guard)', () => {
  it.each([
    ['/dashboard', '/dashboard'],
    ['/dashboard/incidents/abc', '/dashboard/incidents/abc'],
    ['/dashboard/incidents/abc?tab=tasks&row=r1', '/dashboard/incidents/abc?tab=tasks&row=r1'],
    ['  /dashboard/incidents/abc#x  ', '/dashboard/incidents/abc#x'],
  ])('allows internal dashboard path %p', (input, expected) => {
    expect(safeDashboardHref(input)).toBe(expected)
  })

  it.each([
    ['javascript:alert(1)'],
    ['JavaScript:alert(1)//dashboard/'],
    ['data:text/html,<script>alert(1)</script>'],
    ['https://evil.example/dashboard/incidents'],
    ['//evil.example/dashboard'],
    ['/\\evil.example/dashboard'],
    ['\\\\evil.example\\dashboard'],
    ['/dashboard\\..\\..\\evil'],
    ['/dashboard/../login'],
    ['/dashboardx/incidents'],
    ['/incidents/abc'],
    ['/login?next=/dashboard'],
    ['dashboard/incidents'],
    ['/dashboard/\nincidents'],
    ['/dashboard/\tx'],
    [''],
    [null],
    [undefined],
    [42],
  ])('rejects %p', (input) => {
    expect(safeDashboardHref(input)).toBeNull()
  })
})

describe('notificationHref', () => {
  it('prefers a safe action_url', () => {
    expect(
      notificationHref({ action_url: '/dashboard/incidents/i1?tab=tasks&row=t1', incident: { id: 'i2', title: 'x', incident_number: 2 } })
    ).toBe('/dashboard/incidents/i1?tab=tasks&row=t1')
  })

  it('falls back to the incident when action_url is unsafe or missing', () => {
    const incident = { id: '5b0e7c1e-0000-4000-8000-000000000001', title: 'x', incident_number: 7 }
    expect(notificationHref({ action_url: 'javascript:alert(1)', incident })).toBe(`/dashboard/incidents/${incident.id}`)
    expect(notificationHref({ action_url: 'https://evil.example', incident })).toBe(`/dashboard/incidents/${incident.id}`)
    expect(notificationHref({ incident })).toBe(`/dashboard/incidents/${incident.id}`)
  })

  it('returns null when nothing safe is left', () => {
    expect(notificationHref({ action_url: '//evil.example' })).toBeNull()
    expect(notificationHref({ incident: { id: '../../login', title: 'x', incident_number: 1 } })).toBeNull()
    expect(notificationHref({})).toBeNull()
  })
})

describe('useNotificationStore', () => {
  let post: jest.SpiedFunction<typeof api.post>

  beforeEach(() => {
    useNotificationStore.setState({ unreadCount: 0 })
    post = jest.spyOn(api, 'post').mockResolvedValue({} as never)
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('counts each socket notification once and invalidates the list', () => {
    const events: cache.CacheEvent[] = []
    const unsubscribe = cache.subscribe('/notifications', (e) => events.push(e))
    const { onSocketNotification } = useNotificationStore.getState()
    onSocketNotification({ id: 'n1', is_read: false })
    onSocketNotification({ id: 'n2' })
    unsubscribe()
    expect(useNotificationStore.getState().unreadCount).toBe(2)
    expect(events).toEqual([
      { type: 'invalidate', prefix: '/notifications' },
      { type: 'invalidate', prefix: '/notifications' },
    ])
  })

  it('loads the unread count from the server and keeps it on failure', async () => {
    const get = jest.spyOn(api, 'get').mockResolvedValueOnce({ unread_count: 4 } as never)
    await useNotificationStore.getState().refreshUnreadCount()
    expect(get).toHaveBeenCalledWith('/notifications/unread-count')
    expect(useNotificationStore.getState().unreadCount).toBe(4)

    get.mockRejectedValueOnce(new Error('offline'))
    await useNotificationStore.getState().refreshUnreadCount()
    expect(useNotificationStore.getState().unreadCount).toBe(4)
  })

  it('markRead decrements only for unread items and never below zero', async () => {
    useNotificationStore.setState({ unreadCount: 1 })
    const { markRead } = useNotificationStore.getState()
    await markRead({ id: 'n1', is_read: true })
    expect(post).not.toHaveBeenCalled()
    await markRead({ id: 'n1', is_read: false })
    expect(post).toHaveBeenCalledWith('/notifications/n1/read')
    expect(useNotificationStore.getState().unreadCount).toBe(0)
    await markRead({ id: 'n2', is_read: false })
    expect(useNotificationStore.getState().unreadCount).toBe(0)
  })

  it('markRead propagates errors and leaves the count alone', async () => {
    useNotificationStore.setState({ unreadCount: 3 })
    post.mockRejectedValueOnce(new Error('boom'))
    await expect(useNotificationStore.getState().markRead({ id: 'n1', is_read: false })).rejects.toThrow('boom')
    expect(useNotificationStore.getState().unreadCount).toBe(3)
  })

  it('markAllRead zeroes the badge', async () => {
    useNotificationStore.setState({ unreadCount: 9 })
    await useNotificationStore.getState().markAllRead()
    expect(post).toHaveBeenCalledWith('/notifications/read-all')
    expect(useNotificationStore.getState().unreadCount).toBe(0)
  })
})
