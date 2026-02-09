"use client"

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/use-toast'
import { useSocketEvent } from '@/hooks/use-socket'
import api from '@/lib/api'
import { formatRelativeTime } from '@/lib/utils'
import type { Notification } from '@/types'
import {
  Bell, X, CheckCheck, AlertTriangle, FileText, Shield, Users, Activity,
  Loader2, Inbox, ChevronRight,
} from 'lucide-react'

interface NotificationPanelProps {
  open: boolean
  onClose: () => void
  onUnreadCountChange: (count: number) => void
}

const typeIcons: Record<string, React.ReactNode> = {
  incident_created: <AlertTriangle className="h-4 w-4 text-orange-400" />,
  incident_updated: <Activity className="h-4 w-4 text-blue-400" />,
  report_generated: <FileText className="h-4 w-4 text-cyan-400" />,
  artifact_uploaded: <Shield className="h-4 w-4 text-green-400" />,
  user_assigned: <Users className="h-4 w-4 text-purple-400" />,
  status_changed: <Activity className="h-4 w-4 text-yellow-400" />,
}

export function NotificationPanel({ open, onClose, onUnreadCountChange }: NotificationPanelProps) {
  const { toast } = useToast()
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [loading, setLoading] = useState(true)
  const [markingAll, setMarkingAll] = useState(false)

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await api.get<{ items: Notification[]; total: number }>('/notifications?per_page=50')
      setNotifications(res.items || [])
      const unread = (res.items || []).filter(n => !n.is_read).length
      onUnreadCountChange(unread)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [onUnreadCountChange])

  useEffect(() => {
    if (open) {
      setLoading(true)
      fetchNotifications()
    }
  }, [open, fetchNotifications])

  // Real-time updates
  useSocketEvent('notification', (data: Notification) => {
    setNotifications(prev => [data, ...prev])
    onUnreadCountChange(notifications.filter(n => !n.is_read).length + 1)
  })

  const markAsRead = async (id: string) => {
    try {
      await api.put(`/notifications/${id}/read`)
      setNotifications(prev =>
        prev.map(n => n.id === id ? { ...n, is_read: true } : n)
      )
      const newUnread = notifications.filter(n => !n.is_read && n.id !== id).length
      onUnreadCountChange(newUnread)
    } catch {
      // silent
    }
  }

  const markAllRead = async () => {
    setMarkingAll(true)
    try {
      await api.post('/notifications/mark-all-read')
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
      onUnreadCountChange(0)
      toast({ title: 'All caught up', description: 'All notifications marked as read' })
    } catch {
      toast({ title: 'Error', description: 'Failed to mark notifications', variant: 'destructive' })
    } finally {
      setMarkingAll(false)
    }
  }

  const unreadCount = notifications.filter(n => !n.is_read).length

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm" onClick={onClose} />

      {/* Panel */}
      <div className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-md bg-card border-l border-border shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Bell className="h-5 w-5" />
            <h2 className="text-lg font-semibold">Notifications</h2>
            {unreadCount > 0 && (
              <Badge variant="destructive" className="text-xs">
                {unreadCount}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            {unreadCount > 0 && (
              <Button variant="ghost" size="sm" onClick={markAllRead} disabled={markingAll}>
                {markingAll ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <CheckCheck className="h-4 w-4 mr-1" />}
                Mark all read
              </Button>
            )}
            <Button variant="ghost" size="icon-sm" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Notification list */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12 gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading...
            </div>
          ) : notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <Inbox className="h-12 w-12 mb-4 opacity-50" />
              <p className="font-medium">No notifications</p>
              <p className="text-sm mt-1">You&apos;re all caught up!</p>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {notifications.map(notification => {
                const icon = typeIcons[notification.type] || <Bell className="h-4 w-4 text-muted-foreground" />
                const href = notification.incident
                  ? `/dashboard/incidents/${notification.incident.id}`
                  : notification.action_url || '#'

                return (
                  <div
                    key={notification.id}
                    className={`p-4 hover:bg-muted/50 transition-colors cursor-pointer ${
                      !notification.is_read ? 'bg-primary/5' : ''
                    }`}
                    onClick={() => {
                      if (!notification.is_read) markAsRead(notification.id)
                    }}
                  >
                    <div className="flex gap-3">
                      <div className="mt-0.5 shrink-0">
                        {icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2">
                          <p className={`text-sm ${!notification.is_read ? 'font-medium text-foreground' : 'text-muted-foreground'}`}>
                            {notification.title}
                          </p>
                          {!notification.is_read && (
                            <div className="w-2 h-2 rounded-full bg-cyan-500 shrink-0 mt-1.5" />
                          )}
                        </div>
                        {notification.message && (
                          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                            {notification.message}
                          </p>
                        )}
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className="text-[10px] text-muted-foreground">
                            {formatRelativeTime(notification.created_at)}
                          </span>
                          {notification.incident && (
                            <Link
                              href={href}
                              onClick={(e) => e.stopPropagation()}
                              className="text-[10px] text-cyan-400 hover:underline flex items-center gap-0.5"
                            >
                              #{notification.incident.incident_number}
                              <ChevronRight className="h-3 w-3" />
                            </Link>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
