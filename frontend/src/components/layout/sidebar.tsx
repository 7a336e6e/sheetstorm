/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/lib/store'
import {
  Shield,
  LayoutDashboard,
  AlertTriangle,
  LogOut,
  Bell,
  FileText,
  ChevronLeft,
  ChevronRight,
  Search,
  BookOpen,
  BarChart3,
  ListChecks,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Suspense, useState, useEffect, useMemo } from 'react'
import { useSocketEvent } from '@/hooks/use-socket'
import { NotificationPanel } from '@/components/layout/NotificationPanel'
import { useCommandPalette } from '@/components/layout/command-palette'
import { adminNavigation, visibleAdminItems } from '@/components/layout/nav-config'
import { useNotificationStore } from '@/lib/feature-stores'
import type { Notification } from '@/types'

// `permission`: the item is shown only to holders of it (cosmetic; pages and API enforce).
const navigation: { name: string; href: string; icon: typeof Shield; permission?: string }[] = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Incidents', href: '/dashboard/incidents', icon: AlertTriangle },
  { name: 'Threat Intel', href: '/dashboard/threat-intel', icon: Search },
  { name: 'Knowledge Base', href: '/dashboard/knowledge-base', icon: BookOpen },
  { name: 'Reports', href: '/dashboard/reports', icon: FileText, permission: 'reports:read' },
  { name: 'Metrics', href: '/dashboard/metrics', icon: BarChart3, permission: 'metrics:read' },
  { name: 'Improvements', href: '/dashboard/improvements', icon: ListChecks, permission: 'improvements:read' },
]

// Admin items live in nav-config.ts, shared with the command palette.
export { adminNavigation, visibleAdminItems }

export function Sidebar({ onNavigate }: { onNavigate?: () => void } = {}) {
  const pathname = usePathname()
  const { user, logout, hasPermission } = useAuthStore()
  const permissions = user?.permissions
  const visibleAdminNavigation = useMemo(() => visibleAdminItems(permissions), [permissions])
  const [collapsed, setCollapsed] = useState(false)
  const [notifPanelOpen, setNotifPanelOpen] = useState(false)
  const openPalette = useCommandPalette((s) => s.setOpen)
  const unreadCount = useNotificationStore((s) => s.unreadCount)
  const refreshUnreadCount = useNotificationStore((s) => s.refreshUnreadCount)
  const onSocketNotification = useNotificationStore((s) => s.onSocketNotification)

  // Filter navigation items based on permissions
  const filteredNavigation = navigation.filter((item) => !item.permission || hasPermission(item.permission))

  // Unread badge: server count (re-synced every 60s) + socket increments.
  // This is the only `notification` socket subscriber (see feature-stores).
  useEffect(() => {
    void refreshUnreadCount()
    const interval = setInterval(() => void refreshUnreadCount(), 60000)
    return () => clearInterval(interval)
  }, [refreshUnreadCount])

  useSocketEvent('notification', (data: Partial<Notification> | undefined) => {
    onSocketNotification(data)
  })

  return (
    <div
      className={cn(
        "flex h-screen flex-col border-r border-border bg-card transition-all duration-200",
        collapsed ? "w-16" : "w-64"
      )}
    >
      {/* Logo */}
      <div className="flex h-14 items-center justify-between px-4 border-b border-border">
        <Link href="/dashboard" className="flex items-center gap-2">
          <Shield className="h-6 w-6 text-foreground" />
          {!collapsed && (
            <span className="text-lg font-semibold">SheetStorm</span>
          )}
        </Link>
        <Button
          variant="ghost"
          size="icon-sm"
          className="text-muted-foreground hover:text-foreground"
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* Search / command palette */}
      <div className="px-2 pt-3">
        <button
          type="button"
          onClick={() => {
            onNavigate?.()
            openPalette(true)
          }}
          aria-label="Search (Ctrl+K)"
          title="Search (Ctrl+K / ⌘K)"
          className={cn(
            'flex w-full items-center rounded-md border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
            collapsed && 'justify-center px-0'
          )}
        >
          <Search className={cn('h-4 w-4 shrink-0', !collapsed && 'mr-2')} />
          {!collapsed && (
            <>
              <span className="flex-1 text-left">Search</span>
              <kbd className="rounded border border-white/10 px-1 text-[10px]">⌘K</kbd>
            </>
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-2 py-4 overflow-y-auto">
        <div className="space-y-1">
          {filteredNavigation.map((item) => {
            const isActive = item.href === '/dashboard'
              ? pathname === '/dashboard'
              : pathname === item.href || pathname.startsWith(item.href + '/')
            return (
              <Link
                key={item.name}
                href={item.href}
                onClick={onNavigate}
                className={cn(
                  'group flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-accent text-accent-foreground font-semibold'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                )}
              >
                <item.icon className={cn(
                  "h-5 w-5 shrink-0",
                  !collapsed && "mr-3"
                )} />
                {!collapsed && item.name}
              </Link>
            )
          })}
        </div>

        {visibleAdminNavigation.length > 0 && (
          <div className="pt-4">
            {!collapsed && (
              <p className="px-3 mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Admin
              </p>
            )}
            {collapsed && <div className="border-t border-border my-2" />}
            <div className="space-y-1">
              {visibleAdminNavigation.map((item) => {
                const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    onClick={onNavigate}
                    className={cn(
                      'group flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-accent text-accent-foreground font-semibold'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                    )}
                  >
                    <item.icon className={cn(
                      "h-5 w-5 shrink-0",
                      !collapsed && "mr-3"
                    )} />
                    {!collapsed && item.name}
                  </Link>
                )
              })}
            </div>
          </div>
        )}
      </nav>

      {/* User section */}
      <div className="border-t border-border p-3">
        <div className={cn(
          "flex items-center mb-3",
          collapsed && "justify-center"
        )}>
          <Link
            href="/dashboard/profile"
            onClick={onNavigate}
            className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-sm font-medium hover:ring-2 hover:ring-primary/50 transition-all"
            title="View profile"
          >
            {user?.name?.charAt(0).toUpperCase() || 'U'}
          </Link>
          {!collapsed && (
            <>
              <Link href="/dashboard/profile" onClick={onNavigate} className="ml-3 flex-1 min-w-0 hover:opacity-80 transition-opacity">
                <p className="text-sm font-medium truncate">
                  {user?.name || 'User'}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {user?.roles?.[0] || 'Viewer'}
                </p>
              </Link>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:text-foreground relative"
                  onClick={() => setNotifPanelOpen(true)}
                  aria-label={unreadCount > 0 ? `Notifications (${unreadCount} unread)` : 'Notifications'}
                >
                  <Bell className="h-4 w-4" />
                  {unreadCount > 0 && (
                    <Badge
                      variant="destructive"
                      className="absolute -top-1 -right-1 h-4 w-4 p-0 flex items-center justify-center text-[10px]"
                    >
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </Badge>
                  )}
                </Button>
              </div>
            </>
          )}
        </div>
        <Button
          variant="ghost"
          className={cn(
            "text-muted-foreground hover:text-foreground w-full",
            collapsed ? "justify-center px-0" : "justify-start"
          )}
          onClick={() => logout()}
        >
          <LogOut className={cn("h-4 w-4", !collapsed && "mr-2")} />
          {!collapsed && "Sign out"}
        </Button>
      </div>

      <Suspense fallback={null}>
        <NotificationPanel open={notifPanelOpen} onClose={() => setNotifPanelOpen(false)} />
      </Suspense>
    </div>
  )
}
