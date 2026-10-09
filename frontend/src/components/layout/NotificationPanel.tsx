"use client"

/**
 * Slide-over notification list. Pages through `/notifications` 20 at a time
 * ("Load more"); the unread badge lives in `useNotificationStore` and the
 * sidebar is the only socket subscriber (it invalidates this list).
 * Each row is a link to its `action_url` (internal `/dashboard/...` paths
 * only) or its incident, and marks the notification read.
 */
import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import Link from 'next/link'
import {
  AlertTriangle,
  AtSign,
  Bell,
  CheckCheck,
  ClipboardList,
  Clock,
  Inbox,
  ListChecks,
  Loader2,
  MessageSquare,
  Paperclip,
  RefreshCw,
  UserPlus,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import { describeError, notifyError } from '@/lib/errors'
import { notificationHref, NOTIFICATIONS_ENDPOINT, useNotificationStore } from '@/lib/feature-stores'
import { cn, formatRelativeTime } from '@/lib/utils'
import type { Notification } from '@/types'

interface NotificationPanelProps {
  open: boolean
  onClose: () => void
}

/** Keyed on the backend `Notification.NOTIFICATION_TYPES`; Bell is the fallback. */
const TYPE_ICONS: Record<string, React.ReactNode> = {
  incident_assigned: <UserPlus className="h-4 w-4 text-purple-400" />,
  incident_updated: <RefreshCw className="h-4 w-4 text-blue-400" />,
  task_assigned: <ClipboardList className="h-4 w-4 text-cyan-400" />,
  task_due: <Clock className="h-4 w-4 text-amber-400" />,
  improvement_due: <ListChecks className="h-4 w-4 text-amber-400" />,
  comment_added: <MessageSquare className="h-4 w-4 text-sky-400" />,
  artifact_uploaded: <Paperclip className="h-4 w-4 text-emerald-400" />,
  mention: <AtSign className="h-4 w-4 text-pink-400" />,
  system: <AlertTriangle className="h-4 w-4 text-orange-400" />,
}

const PAGE_SIZE = 20

export function NotificationPanel({ open, onClose }: NotificationPanelProps) {
  const unreadCount = useNotificationStore((s) => s.unreadCount)
  const markRead = useNotificationStore((s) => s.markRead)
  const markAllRead = useNotificationStore((s) => s.markAllRead)
  const refreshUnreadCount = useNotificationStore((s) => s.refreshUnreadCount)

  const query = usePaginatedQuery<Notification>({
    endpoint: NOTIFICATIONS_ENDPOINT,
    mode: 'append',
    defaults: { perPage: PAGE_SIZE },
    enabled: open,
  })

  // Opening the panel re-syncs the badge with the server.
  useEffect(() => {
    if (open) void refreshUnreadCount()
  }, [open, refreshUnreadCount])

  // Escape closes.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open || typeof document === 'undefined') return null

  const handleMarkAll = async () => {
    try {
      await markAllRead()
    } catch (err) {
      notifyError(err, 'mark notifications as read')
    }
  }

  const handleRowActivate = (n: Notification) => {
    if (!n.is_read) {
      markRead(n).catch((err) => notifyError(err, 'mark the notification as read'))
    }
  }

  const { items } = query
  const hasMore = query.state.page < query.pages

  return createPortal(
    <>
      <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" onClick={onClose} aria-hidden />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="notification-panel-title"
        className="fixed bottom-0 right-0 top-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-card shadow-2xl animate-in slide-in-from-right duration-200"
      >
        <div className="flex items-center justify-between border-b border-border p-4">
          <div className="flex items-center gap-2">
            <Bell className="h-5 w-5" />
            <h2 id="notification-panel-title" className="text-lg font-semibold">
              Notifications
            </h2>
            {unreadCount > 0 && (
              <Badge variant="destructive" className="text-xs">
                {unreadCount}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            {unreadCount > 0 && (
              <Button variant="ghost" size="sm" onClick={() => void handleMarkAll()}>
                <CheckCheck className="mr-1 h-4 w-4" />
                Mark all read
              </Button>
            )}
            <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close notifications">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {query.isLoading ? (
            <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : query.error && items.length === 0 ? (
            <div role="alert" className="flex flex-col items-center gap-2 px-6 py-12 text-center">
              <AlertTriangle className="h-6 w-6 text-destructive" />
              <p className="text-sm font-medium">{describeError(query.error).title}</p>
              <p className="text-xs text-muted-foreground">{describeError(query.error).description}</p>
              <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                Retry
              </Button>
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <Inbox className="mb-4 h-12 w-12 opacity-50" />
              <p className="font-medium">No notifications</p>
              <p className="mt-1 text-sm">You&apos;re all caught up.</p>
            </div>
          ) : (
            <ul className="divide-y divide-border" aria-label="Notifications">
              {items.map((n) => (
                <li key={n.id}>
                  <NotificationRow notification={n} onActivate={handleRowActivate} onNavigate={onClose} />
                </li>
              ))}
            </ul>
          )}

          {hasMore && items.length > 0 && (
            <div className="p-3">
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                disabled={query.isFetching}
                onClick={() => query.setPage(query.state.page + 1)}
              >
                {query.isFetching && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Load more
              </Button>
            </div>
          )}
        </div>
      </div>
    </>,
    document.body
  )
}

function NotificationRow({
  notification: n,
  onActivate,
  onNavigate,
}: {
  notification: Notification
  onActivate: (n: Notification) => void
  onNavigate: () => void
}) {
  const href = notificationHref(n)
  const body = (
    <div className="flex gap-3">
      <div className="mt-0.5 shrink-0">{TYPE_ICONS[n.type] ?? <Bell className="h-4 w-4 text-muted-foreground" />}</div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className={cn('text-sm', n.is_read ? 'text-muted-foreground' : 'font-medium text-foreground')}>{n.title}</p>
          {!n.is_read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-cyan-500" aria-label="Unread" />}
        </div>
        {n.message && <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{n.message}</p>}
        <div className="mt-1.5 flex items-center gap-2 text-[10px] text-muted-foreground">
          <span>{formatRelativeTime(n.created_at)}</span>
          {n.incident && <span className="text-cyan-400">#{n.incident.incident_number}</span>}
        </div>
      </div>
    </div>
  )
  const className = cn(
    'block w-full p-4 text-left transition-colors hover:bg-muted/50 focus-visible:bg-muted/60 focus-visible:outline-none',
    !n.is_read && 'bg-primary/5'
  )

  if (href) {
    return (
      <Link
        href={href}
        className={className}
        onClick={() => {
          onActivate(n)
          onNavigate()
        }}
      >
        {body}
      </Link>
    )
  }
  return (
    <button type="button" className={className} onClick={() => onActivate(n)}>
      {body}
    </button>
  )
}
