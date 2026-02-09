/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
    Activity, Clock, User, FileEdit, AlertTriangle, Trash2, UserPlus,
    ChevronDown, ChevronRight, Globe, Monitor, Shield, Database,
    LogIn, LogOut, Settings, Eye, Filter, ChevronLeft, ChevronsLeft,
    ChevronsRight, Search, X
} from 'lucide-react'
import { auditLogs } from '@/lib/api'
import { AuditLog } from '@/types'

// ── Display helpers ────────────────────────────────────────────────

const actionDisplay: Record<string, { icon: any; color: string; bg: string }> = {
    create: { icon: FileEdit, color: 'text-green-600', bg: 'bg-green-50' },
    update: { icon: FileEdit, color: 'text-blue-600', bg: 'bg-blue-50' },
    delete: { icon: Trash2, color: 'text-red-600', bg: 'bg-red-50' },
    login: { icon: LogIn, color: 'text-emerald-600', bg: 'bg-emerald-50' },
    logout: { icon: LogOut, color: 'text-gray-500', bg: 'bg-gray-50' },
    generate: { icon: Settings, color: 'text-purple-600', bg: 'bg-purple-50' },
    view: { icon: Eye, color: 'text-sky-600', bg: 'bg-sky-50' },
    export: { icon: Database, color: 'text-amber-600', bg: 'bg-amber-50' },
}

const eventTypeBadge: Record<string, { label: string; className: string }> = {
    authentication: { label: 'Auth', className: 'bg-emerald-100 text-emerald-700' },
    authorization: { label: 'Authz', className: 'bg-orange-100 text-orange-700' },
    data_access: { label: 'Access', className: 'bg-sky-100 text-sky-700' },
    data_modification: { label: 'Modify', className: 'bg-blue-100 text-blue-700' },
    admin_action: { label: 'Admin', className: 'bg-purple-100 text-purple-700' },
    security_event: { label: 'Security', className: 'bg-red-100 text-red-700' },
    system_event: { label: 'System', className: 'bg-gray-100 text-gray-600' },
}

function getActivityDisplay(eventType: string, action: string, resourceType?: string) {
    let description = action.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
    if (resourceType) {
        description = `${description} ${resourceType.replace(/_/g, ' ')}`
    }
    const actionKey = action.split('_')[0] || action
    const display = actionDisplay[actionKey] || { icon: Activity, color: 'text-gray-500', bg: 'bg-gray-50' }
    return { description, ...display }
}

function formatRelativeTime(dateString: string) {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffSecs = Math.floor(diffMs / 1000)
    const diffMins = Math.floor(diffSecs / 60)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)
    if (diffSecs < 60) return 'just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`
    return date.toLocaleDateString()
}

function formatFullTimestamp(dateString: string) {
    const date = new Date(dateString)
    return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
    })
}

function formatDateHeader(dateString: string) {
    const date = new Date(dateString)
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    if (date.toDateString() === today.toDateString()) return 'Today'
    if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'
    return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
}

// ── Constants ──────────────────────────────────────────────────────

const EVENT_TYPE_OPTIONS = [
    { value: '', label: 'All Types' },
    { value: 'authentication', label: 'Authentication' },
    { value: 'authorization', label: 'Authorization' },
    { value: 'data_access', label: 'Data Access' },
    { value: 'data_modification', label: 'Data Modification' },
    { value: 'admin_action', label: 'Admin Action' },
    { value: 'security_event', label: 'Security Event' },
    { value: 'system_event', label: 'System Event' },
]

const ACTION_OPTIONS = [
    { value: '', label: 'All Actions' },
    { value: 'create', label: 'Create' },
    { value: 'update', label: 'Update' },
    { value: 'delete', label: 'Delete' },
    { value: 'login', label: 'Login' },
    { value: 'logout', label: 'Logout' },
    { value: 'generate', label: 'Generate' },
]

const PER_PAGE = 25

// ── Row detail component ───────────────────────────────────────────

function ActivityRow({ activity, isExpanded, onToggle }: {
    activity: AuditLog
    isExpanded: boolean
    onToggle: () => void
}) {
    const display = getActivityDisplay(activity.event_type, activity.action, activity.resource_type)
    const Icon = display.icon
    const badge = eventTypeBadge[activity.event_type]

    return (
        <div className="border-b border-border/50 last:border-b-0">
            <button
                onClick={onToggle}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/50 transition-colors text-left"
            >
                {/* Expand chevron */}
                <div className="text-muted-foreground shrink-0">
                    {isExpanded
                        ? <ChevronDown className="h-4 w-4" />
                        : <ChevronRight className="h-4 w-4" />}
                </div>

                {/* Action icon */}
                <div className={`shrink-0 rounded-md p-1.5 ${display.bg}`}>
                    <Icon className={`h-4 w-4 ${display.color}`} />
                </div>

                {/* Main content */}
                <div className="flex-1 min-w-0 grid grid-cols-[1fr_auto] gap-x-4 items-center">
                    <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{display.description}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-xs text-muted-foreground truncate">
                                {activity.user?.name || activity.user_email || 'System'}
                            </span>
                            {badge && (
                                <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium ${badge.className}`}>
                                    {badge.label}
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Timestamp */}
                    <div className="text-right shrink-0">
                        <p className="text-xs text-muted-foreground whitespace-nowrap">
                            {formatRelativeTime(activity.created_at)}
                        </p>
                        <p className="text-[11px] text-muted-foreground/70 whitespace-nowrap">
                            {formatFullTimestamp(activity.created_at)}
                        </p>
                    </div>
                </div>
            </button>

            {/* Expanded detail panel */}
            {isExpanded && (
                <div className="px-4 pb-4 pt-1 ml-[52px] mr-4">
                    <div className="rounded-md border border-border bg-muted/30 p-4">
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3 text-sm">
                            {/* User info */}
                            <DetailField
                                icon={<User className="h-3.5 w-3.5" />}
                                label="User"
                                value={activity.user?.name || activity.user_email || 'System'}
                            />
                            {activity.user?.email && (
                                <DetailField
                                    icon={<Globe className="h-3.5 w-3.5" />}
                                    label="Email"
                                    value={activity.user.email}
                                />
                            )}
                            {activity.ip_address && (
                                <DetailField
                                    icon={<Monitor className="h-3.5 w-3.5" />}
                                    label="IP Address"
                                    value={activity.ip_address}
                                />
                            )}

                            {/* Event info */}
                            <DetailField
                                icon={<Shield className="h-3.5 w-3.5" />}
                                label="Event Type"
                                value={activity.event_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                            />
                            <DetailField
                                icon={<Activity className="h-3.5 w-3.5" />}
                                label="Action"
                                value={activity.action.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                            />
                            {activity.resource_type && (
                                <DetailField
                                    icon={<Database className="h-3.5 w-3.5" />}
                                    label="Resource Type"
                                    value={activity.resource_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                                />
                            )}

                            {/* Resource ID */}
                            {activity.resource_id && (
                                <DetailField
                                    icon={<Database className="h-3.5 w-3.5" />}
                                    label="Resource ID"
                                    value={activity.resource_id}
                                    mono
                                />
                            )}

                            {/* Timestamp */}
                            <DetailField
                                icon={<Clock className="h-3.5 w-3.5" />}
                                label="Timestamp"
                                value={formatFullTimestamp(activity.created_at)}
                            />
                        </div>

                        {/* Details / metadata */}
                        {activity.details && Object.keys(activity.details).length > 0 && (
                            <div className="mt-4 pt-3 border-t border-border/50">
                                <p className="text-xs font-medium text-muted-foreground mb-2">Additional Details</p>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
                                    {Object.entries(activity.details).map(([key, value]) => (
                                        <div key={key} className="flex items-baseline gap-2 text-xs">
                                            <span className="text-muted-foreground shrink-0">
                                                {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}:
                                            </span>
                                            <span className="font-mono text-foreground truncate">
                                                {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}

function DetailField({ icon, label, value, mono }: {
    icon: React.ReactNode
    label: string
    value: string
    mono?: boolean
}) {
    return (
        <div className="flex items-start gap-2">
            <span className="text-muted-foreground mt-0.5 shrink-0">{icon}</span>
            <div className="min-w-0">
                <p className="text-[11px] text-muted-foreground">{label}</p>
                <p className={`text-sm truncate ${mono ? 'font-mono text-xs' : ''}`}>{value}</p>
            </div>
        </div>
    )
}

// ── Main page ──────────────────────────────────────────────────────

export default function ActivityPage() {
    const [activities, setActivities] = useState<AuditLog[]>([])
    const [stats, setStats] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [expandedId, setExpandedId] = useState<string | null>(null)

    // Pagination
    const [page, setPage] = useState(1)
    const [totalPages, setTotalPages] = useState(1)
    const [total, setTotal] = useState(0)

    // Filters
    const [filterEventType, setFilterEventType] = useState('')
    const [filterAction, setFilterAction] = useState('')
    const [showFilters, setShowFilters] = useState(false)

    const fetchData = useCallback(async () => {
        try {
            setLoading(true)
            setError(null)

            const params: Record<string, any> = { per_page: PER_PAGE, page }
            if (filterEventType) params.event_type = filterEventType
            if (filterAction) params.action = filterAction

            const [logsResponse, statsResponse] = await Promise.all([
                auditLogs.list(params),
                auditLogs.getStats(),
            ])

            setActivities(logsResponse.items)
            setTotalPages(logsResponse.pages)
            setTotal(logsResponse.total)
            setStats(statsResponse)
        } catch (err: any) {
            setError(err.message || 'Failed to load activity data')
        } finally {
            setLoading(false)
        }
    }, [page, filterEventType, filterAction])

    useEffect(() => { fetchData() }, [fetchData])

    // Reset page when filters change
    useEffect(() => { setPage(1) }, [filterEventType, filterAction])

    // ── Stats calculations ──
    const todayActions = stats ? (() => {
        const today = new Date().toISOString().split('T')[0]
        return stats.by_day[today] || 0
    })() : 0

    const weekActions = stats ? (() => {
        const now = new Date()
        let t = 0
        for (let i = 0; i < 7; i++) {
            const d = new Date(now); d.setDate(d.getDate() - i)
            t += stats.by_day[d.toISOString().split('T')[0]] || 0
        }
        return t
    })() : 0

    const incidentsUpdated = stats?.by_event_type?.['data_modification'] || 0
    const activeUsers = activities ? new Set(activities.map(a => a.user?.id).filter(Boolean)).size : 0
    const hasFilters = filterEventType || filterAction

    // Group activities by date
    const groupedActivities: { date: string; items: AuditLog[] }[] = []
    let currentDate = ''
    for (const a of activities) {
        const dateKey = new Date(a.created_at).toDateString()
        if (dateKey !== currentDate) {
            currentDate = dateKey
            groupedActivities.push({ date: a.created_at, items: [a] })
        } else {
            groupedActivities[groupedActivities.length - 1].items.push(a)
        }
    }

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-semibold">Activity</h1>
                <p className="text-sm text-muted-foreground mt-1">Track all system activity and audit logs</p>
            </div>

            {/* Stats */}
            <div className="grid gap-4 md:grid-cols-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Today&apos;s Actions</CardDescription>
                        <CardTitle className="text-2xl">{loading ? '...' : todayActions}</CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>This Week</CardDescription>
                        <CardTitle className="text-2xl">{loading ? '...' : weekActions}</CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Active Users</CardDescription>
                        <CardTitle className="text-2xl">{loading ? '...' : activeUsers}</CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Incidents Updated</CardDescription>
                        <CardTitle className="text-2xl">{loading ? '...' : incidentsUpdated}</CardTitle>
                    </CardHeader>
                </Card>
            </div>

            {/* Activity Log */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Clock className="h-5 w-5" />
                                Activity Log
                            </CardTitle>
                            <CardDescription className="mt-1">
                                {total > 0
                                    ? `${total} total events · Page ${page} of ${totalPages}`
                                    : 'Recent actions across all incidents'}
                            </CardDescription>
                        </div>
                        <button
                            onClick={() => setShowFilters(v => !v)}
                            className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                                hasFilters
                                    ? 'border-blue-200 bg-blue-50 text-blue-700'
                                    : 'border-border bg-background text-muted-foreground hover:bg-muted/50'
                            }`}
                        >
                            <Filter className="h-3.5 w-3.5" />
                            Filters
                            {hasFilters && (
                                <span className="rounded-full bg-blue-600 text-white h-4 w-4 text-[10px] flex items-center justify-center">
                                    {[filterEventType, filterAction].filter(Boolean).length}
                                </span>
                            )}
                        </button>
                    </div>

                    {/* Filter bar */}
                    {showFilters && (
                        <div className="flex flex-wrap items-center gap-3 pt-3 mt-3 border-t border-border/50">
                            <select
                                value={filterEventType}
                                onChange={(e) => setFilterEventType(e.target.value)}
                                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                            >
                                {EVENT_TYPE_OPTIONS.map(o => (
                                    <option key={o.value} value={o.value}>{o.label}</option>
                                ))}
                            </select>
                            <select
                                value={filterAction}
                                onChange={(e) => setFilterAction(e.target.value)}
                                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                            >
                                {ACTION_OPTIONS.map(o => (
                                    <option key={o.value} value={o.value}>{o.label}</option>
                                ))}
                            </select>
                            {hasFilters && (
                                <button
                                    onClick={() => { setFilterEventType(''); setFilterAction('') }}
                                    className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                                >
                                    <X className="h-3.5 w-3.5" />
                                    Clear
                                </button>
                            )}
                        </div>
                    )}
                </CardHeader>

                <CardContent className="px-0">
                    {error ? (
                        <div className="text-center py-12 px-4">
                            <div className="mx-auto w-12 h-12 rounded-md bg-red-50 flex items-center justify-center mb-4">
                                <AlertTriangle className="h-6 w-6 text-red-500" />
                            </div>
                            <p className="font-medium mb-1 text-red-600">Error loading activity</p>
                            <p className="text-sm text-muted-foreground">{error}</p>
                        </div>
                    ) : loading ? (
                        <div className="text-center py-12">
                            <div className="mx-auto w-12 h-12 rounded-md bg-muted flex items-center justify-center mb-4">
                                <Activity className="h-6 w-6 text-muted-foreground animate-pulse" />
                            </div>
                            <p className="font-medium mb-1">Loading activity...</p>
                        </div>
                    ) : activities.length > 0 ? (
                        <div>
                            {groupedActivities.map((group) => (
                                <div key={group.date}>
                                    {/* Date header */}
                                    <div className="sticky top-0 z-10 bg-muted/60 backdrop-blur-sm px-4 py-1.5 border-y border-border/40">
                                        <p className="text-xs font-medium text-muted-foreground">
                                            {formatDateHeader(group.date)}
                                        </p>
                                    </div>
                                    {group.items.map((activity) => (
                                        <ActivityRow
                                            key={activity.id}
                                            activity={activity}
                                            isExpanded={expandedId === activity.id}
                                            onToggle={() =>
                                                setExpandedId(prev => prev === activity.id ? null : activity.id)
                                            }
                                        />
                                    ))}
                                </div>
                            ))}

                            {/* Pagination */}
                            {totalPages > 1 && (
                                <div className="flex items-center justify-between px-4 py-3 border-t border-border/50">
                                    <p className="text-xs text-muted-foreground">
                                        Showing {(page - 1) * PER_PAGE + 1}–{Math.min(page * PER_PAGE, total)} of {total}
                                    </p>
                                    <div className="flex items-center gap-1">
                                        <button
                                            onClick={() => setPage(1)}
                                            disabled={page === 1}
                                            className="p-1.5 rounded-md hover:bg-muted disabled:opacity-30 disabled:pointer-events-none"
                                        >
                                            <ChevronsLeft className="h-4 w-4" />
                                        </button>
                                        <button
                                            onClick={() => setPage(p => Math.max(1, p - 1))}
                                            disabled={page === 1}
                                            className="p-1.5 rounded-md hover:bg-muted disabled:opacity-30 disabled:pointer-events-none"
                                        >
                                            <ChevronLeft className="h-4 w-4" />
                                        </button>
                                        <span className="text-xs px-2 text-muted-foreground">
                                            {page} / {totalPages}
                                        </span>
                                        <button
                                            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                                            disabled={page === totalPages}
                                            className="p-1.5 rounded-md hover:bg-muted disabled:opacity-30 disabled:pointer-events-none"
                                        >
                                            <ChevronRight className="h-4 w-4" />
                                        </button>
                                        <button
                                            onClick={() => setPage(totalPages)}
                                            disabled={page === totalPages}
                                            className="p-1.5 rounded-md hover:bg-muted disabled:opacity-30 disabled:pointer-events-none"
                                        >
                                            <ChevronsRight className="h-4 w-4" />
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="text-center py-12">
                            <div className="mx-auto w-12 h-12 rounded-md bg-muted flex items-center justify-center mb-4">
                                <Activity className="h-6 w-6 text-muted-foreground" />
                            </div>
                            <p className="font-medium mb-1">No activity found</p>
                            <p className="text-sm text-muted-foreground">
                                {hasFilters ? 'Try adjusting your filters' : 'Actions on incidents will appear here'}
                            </p>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
