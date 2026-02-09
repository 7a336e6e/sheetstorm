/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/lib/store'
import api from '@/lib/api'
import {
  Shield,
  LayoutDashboard,
  AlertTriangle,
  Users,
  UsersRound,
  Settings,
  LogOut,
  Bell,
  FileText,
  Activity,
  ChevronLeft,
  ChevronRight,
  KeyRound,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ThemeToggle } from '@/components/ui/theme-toggle'
import { useState, useEffect, useCallback } from 'react'
import { useSocketEvent } from '@/hooks/use-socket'
import { NotificationPanel } from '@/components/layout/NotificationPanel'

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Incidents', href: '/dashboard/incidents', icon: AlertTriangle },
  { name: 'Reports', href: '/dashboard/reports', icon: FileText },
  { name: 'Activity', href: '/dashboard/activity', icon: Activity },
]

const adminNavigation = [
  { name: 'Users', href: '/dashboard/admin/users', icon: Users },
  { name: 'Teams', href: '/dashboard/admin/teams', icon: UsersRound },
  { name: 'Security', href: '/dashboard/admin/security', icon: KeyRound },
  { name: 'Settings', href: '/dashboard/admin/settings', icon: Settings },
]

export function Sidebar({ onNavigate }: { onNavigate?: () => void } = {}) {
  const pathname = usePathname()
  const { user, logout, hasRole } = useAuthStore()
  const isAdmin = hasRole('Administrator')
  const [collapsed, setCollapsed] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)
  const [notifPanelOpen, setNotifPanelOpen] = useState(false)

  // Fetch unread notification count
  const fetchUnreadCount = useCallback(async () => {
    try {
      const data = await api.get<{ items: { is_read: boolean }[]; total: number }>('/notifications?is_read=false&per_page=1')
      setUnreadCount(data.total)
    } catch {
      // Silently fail — badge just won't show
    }
  }, [])

  useEffect(() => {
    fetchUnreadCount()
    const interval = setInterval(fetchUnreadCount, 60000) // Refresh every 60s
    return () => clearInterval(interval)
  }, [fetchUnreadCount])

  // Real-time notification updates via WebSocket
  useSocketEvent('notification', () => {
    setUnreadCount((prev) => prev + 1)
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

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-2 py-4 overflow-y-auto">
        <div className="space-y-1">
          {navigation.map((item) => {
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
                    ? 'bg-secondary text-foreground'
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

        {isAdmin && (
          <div className="pt-4">
            {!collapsed && (
              <p className="px-3 mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Admin
              </p>
            )}
            {collapsed && <div className="border-t border-border my-2" />}
            <div className="space-y-1">
              {adminNavigation.map((item) => {
                const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    onClick={onNavigate}
                    className={cn(
                      'group flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-secondary text-foreground'
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
          <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-sm font-medium">
            {user?.name?.charAt(0).toUpperCase() || 'U'}
          </div>
          {!collapsed && (
            <>
              <div className="ml-3 flex-1 min-w-0">
                <p className="text-sm font-medium truncate">
                  {user?.name || 'User'}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {user?.roles?.[0] || 'Viewer'}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <ThemeToggle />
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:text-foreground relative"
                  onClick={() => setNotifPanelOpen(true)}
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

      <NotificationPanel
        open={notifPanelOpen}
        onClose={() => setNotifPanelOpen(false)}
        onUnreadCountChange={setUnreadCount}
      />
    </div>
  )
}
