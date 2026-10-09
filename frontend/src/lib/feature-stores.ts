/**
 * Notification state shared by the sidebar badge and the notification panel.
 *
 * - `unreadCount` is the single source for the badge. It comes from the
 *   server (`/notifications/unread-count`) and is adjusted locally on socket
 *   events and mark-read actions, so nothing counts twice.
 * - The sidebar is the only `notification` socket subscriber; it calls
 *   `onSocketNotification`, which bumps the count and invalidates cached
 *   notification lists so an open panel refetches.
 * - The panel's list is a `usePaginatedQuery` over `/notifications`.
 */
import { create } from 'zustand'
import api from './api'
import { invalidate, upsertItem } from './query-cache'
import type { Notification } from '@/types'

export const NOTIFICATIONS_ENDPOINT = '/notifications'

interface NotificationState {
  unreadCount: number
  setUnreadCount: (n: number) => void
  /** Re-read the unread count from the server. Errors keep the last value. */
  refreshUnreadCount: () => Promise<void>
  /** Called once per `notification` socket event (sidebar only). */
  onSocketNotification: (notification?: Partial<Notification>) => void
  /** Mark one notification read. Throws on failure. */
  markRead: (notification: Pick<Notification, 'id' | 'is_read'>) => Promise<void>
  /** Mark everything read. Throws on failure. */
  markAllRead: () => Promise<void>
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  unreadCount: 0,

  setUnreadCount: (n: number) => set({ unreadCount: Math.max(0, Math.floor(n) || 0) }),

  refreshUnreadCount: async () => {
    try {
      const data = await api.get<{ unread_count: number }>(`${NOTIFICATIONS_ENDPOINT}/unread-count`)
      get().setUnreadCount(data.unread_count)
    } catch {
      // Keep the last known count; the badge is best-effort.
    }
  },

  onSocketNotification: (notification) => {
    if (!notification || notification.is_read !== true) {
      set((s) => ({ unreadCount: s.unreadCount + 1 }))
    }
    invalidate(NOTIFICATIONS_ENDPOINT)
  },

  markRead: async (notification) => {
    if (notification.is_read) return
    await api.post(`${NOTIFICATIONS_ENDPOINT}/${encodeURIComponent(notification.id)}/read`)
    set((s) => ({ unreadCount: Math.max(0, s.unreadCount - 1) }))
    upsertItem(NOTIFICATIONS_ENDPOINT, { id: notification.id, is_read: true })
  },

  markAllRead: async () => {
    await api.post(`${NOTIFICATIONS_ENDPOINT}/read-all`)
    set({ unreadCount: 0 })
    invalidate(NOTIFICATIONS_ENDPOINT)
  },
}))

// ── Navigation guard ───────────────────────────────────────────────────

const DASHBOARD_PREFIX = '/dashboard'
const GUARD_ORIGIN = 'http://sheetstorm.invalid'

/**
 * Return `url` as a same-origin path under `/dashboard`, or null.
 *
 * Only relative paths that start with a single `/` are considered, so
 * absolute URLs, protocol-relative `//host`, `javascript:`/`data:` schemes,
 * backslash tricks and control characters are all rejected. The path is
 * normalised (`..` resolved) before the prefix check, so
 * `/dashboard/../login` is rejected too.
 */
export function safeDashboardHref(url: unknown): string | null {
  if (typeof url !== 'string') return null
  const raw = url.trim()
  if (!raw.startsWith('/') || raw.startsWith('//')) return null
  if (/[\\\u0000-\u001f\u007f]/.test(raw)) return null
  let parsed: URL
  try {
    parsed = new URL(raw, GUARD_ORIGIN)
  } catch {
    return null
  }
  if (parsed.origin !== GUARD_ORIGIN) return null
  const path = parsed.pathname
  if (path !== DASHBOARD_PREFIX && !path.startsWith(`${DASHBOARD_PREFIX}/`)) return null
  return `${path}${parsed.search}${parsed.hash}`
}

/**
 * Where clicking a notification goes: its `action_url` when that is a safe
 * internal dashboard path, else its incident, else nowhere (null).
 */
export function notificationHref(n: Pick<Notification, 'action_url' | 'incident'>): string | null {
  const direct = safeDashboardHref(n.action_url)
  if (direct) return direct
  const incidentId = n.incident?.id
  if (typeof incidentId === 'string' && /^[A-Za-z0-9-]+$/.test(incidentId)) {
    return `/dashboard/incidents/${incidentId}`
  }
  return null
}
