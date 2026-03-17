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
    ChevronsRight, Search, X, Smartphone, Laptop, Bot, Terminal,
    MapPin, Gauge, Link2, FileText, Hash, ArrowRight, Server, Radio
} from 'lucide-react'
import { auditLogs } from '@/lib/api'
import { AuditLog } from '@/types'
import { useSocketEvent } from '@/hooks/use-socket'

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
    connect: { icon: Link2, color: 'text-teal-600', bg: 'bg-teal-50' },
    disconnect: { icon: X, color: 'text-orange-600', bg: 'bg-orange-50' },
    password_reveal: { icon: Eye, color: 'text-red-600', bg: 'bg-red-50' },
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

const methodColor: Record<string, string> = {
    GET: 'text-green-700 bg-green-50',
    POST: 'text-blue-700 bg-blue-50',
    PUT: 'text-amber-700 bg-amber-50',
    PATCH: 'text-orange-700 bg-orange-50',
    DELETE: 'text-red-700 bg-red-50',
}

const statusColor = (code?: number) => {
    if (!code) return 'text-gray-500'
    if (code < 300) return 'text-green-600'
    if (code < 400) return 'text-amber-600'
    return 'text-red-600'
}

const deviceIcon: Record<string, any> = {
    Mobile: Smartphone,
    Tablet: Smartphone,
    Desktop: Laptop,
    Bot: Bot,
    CLI: Terminal,
    API: Server,
}

function getActivityDisplay(eventType: string, action: string, resourceType?: string) {
    let description = action.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
    if (resourceType) {
        description = `${description} ${resourceType.replace(/_/g, ' ')}`
    }
    const actionKey = action.split('_')[0] || action
    const display = actionDisplay[action] || actionDisplay[actionKey] || { icon: Activity, color: 'text-gray-500', bg: 'bg-gray-50' }
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

function formatGeoLocation(a: AuditLog) {
    const parts = [a.geo_city, a.geo_region, a.geo_country].filter(Boolean)
    return parts.length > 0 ? parts.join(', ') : null
}

// Country code → flag emoji
function countryFlag(code?: string) {
    if (!code || code.length !== 2) return null
    const offset = 127397
    const upper = code.toUpperCase()
    return String.fromCodePoint(upper.charCodeAt(0) + offset, upper.charCodeAt(1) + offset)
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
    const geo = formatGeoLocation(activity)
    const DeviceIcon = deviceIcon[activity.device_type || ''] || Laptop

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

                {/* Main content — responsive grid */}
                <div className="flex-1 min-w-0 grid grid-cols-[1fr] lg:grid-cols-[1.5fr_minmax(80px,0.5fr)_minmax(140px,1fr)_minmax(100px,0.7fr)_auto] gap-x-4 items-center">
                    {/* Description + user */}
                    <div className="min-w-0">
                        <div className="flex items-center gap-2">
                            <p className="text-sm font-medium truncate">{display.description}</p>
                            {badge && (
                                <span className={`hidden sm:inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium shrink-0 ${badge.className}`}>
                                    {badge.label}
                                </span>
                            )}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-xs text-muted-foreground truncate">
                                {activity.user?.name || activity.user_email || 'System'}
                            </span>
                            {activity.user?.role && (
                                <span className="text-[10px] text-muted-foreground/60 truncate">
                                    ({activity.user.role})
                                </span>
                            )}
                        </div>
                    </div>

                    {/* HTTP Method + Status */}
                    <div className="hidden lg:flex items-center gap-2">
                        {activity.request_method && (
                            <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold ${methodColor[activity.request_method] || 'text-gray-600 bg-gray-50'}`}>
                                {activity.request_method}
                            </span>
                        )}
                        {activity.status_code && (
                            <span className={`text-xs font-mono ${statusColor(activity.status_code)}`}>
                                {activity.status_code}
                            </span>
                        )}
                    </div>

                    {/* IP + Location */}
                    <div className="hidden lg:block min-w-0">
                        {activity.ip_address && (
                            <p className="text-xs font-mono text-muted-foreground truncate">
                                {activity.ip_address}
                            </p>
                        )}
                        {geo && (
                            <p className="text-[10px] text-muted-foreground/70 truncate">
                                {countryFlag(activity.geo_country)} {geo}
                            </p>
                        )}
                    </div>

                    {/* Browser + Device */}
                    <div className="hidden lg:flex items-center gap-1.5 min-w-0">
                        <DeviceIcon className="h-3.5 w-3.5 text-muted-foreground/50 shrink-0" />
                        <span className="text-xs text-muted-foreground truncate">
                            {activity.browser || activity.device_type || '—'}
                        </span>
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
                    <div className="rounded-md border border-border bg-muted/30 p-4 space-y-4">
                        {/* Section: User & Identity */}
                        <DetailSection title="User & Identity">
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
                            {activity.user?.role && (
                                <DetailField
                                    icon={<Shield className="h-3.5 w-3.5" />}
                                    label="Role"
                                    value={activity.user.role}
                                />
                            )}
                        </DetailSection>

                        {/* Section: Request */}
                        <DetailSection title="Request">
                            {activity.request_method && (
                                <DetailField
                                    icon={<ArrowRight className="h-3.5 w-3.5" />}
                                    label="Method"
                                    value={activity.request_method}
                                    mono
                                />
                            )}
                            {activity.request_path && (
                                <DetailField
                                    icon={<Link2 className="h-3.5 w-3.5" />}
                                    label="Path"
                                    value={activity.request_path}
                                    mono
                                />
                            )}
                            {activity.status_code && (
                                <DetailField
                                    icon={<Hash className="h-3.5 w-3.5" />}
                                    label="Status Code"
                                    value={`${activity.status_code}`}
                                    mono
                                    className={statusColor(activity.status_code)}
                                />
                            )}
                            {activity.content_type && (
                                <DetailField
                                    icon={<FileText className="h-3.5 w-3.5" />}
                                    label="Content Type"
                                    value={activity.content_type}
                                    mono
                                />
                            )}
                            {activity.duration_ms != null && (
                                <DetailField
                                    icon={<Gauge className="h-3.5 w-3.5" />}
                                    label="Duration"
                                    value={`${Number(activity.duration_ms).toFixed(1)} ms`}
                                    mono
                                />
                            )}
                            {activity.referrer && (
                                <DetailField
                                    icon={<Link2 className="h-3.5 w-3.5" />}
                                    label="Referrer"
                                    value={activity.referrer}
                                    mono
                                />
                            )}
                            {activity.origin && (
                                <DetailField
                                    icon={<Globe className="h-3.5 w-3.5" />}
                                    label="Origin"
                                    value={activity.origin}
                                    mono
                                />
                            )}
                        </DetailSection>

                        {/* Section: Network & Location */}
                        <DetailSection title="Network & Location">
                            {activity.ip_address && (
                                <DetailField
                                    icon={<Monitor className="h-3.5 w-3.5" />}
                                    label="IP Address"
                                    value={activity.ip_address}
                                    mono
                                />
                            )}
                            {geo && (
                                <DetailField
                                    icon={<MapPin className="h-3.5 w-3.5" />}
                                    label="Location"
                                    value={`${countryFlag(activity.geo_country) || ''} ${geo}`}
                                />
                            )}
                            {activity.cf_ray && (
                                <DetailField
                                    icon={<Server className="h-3.5 w-3.5" />}
                                    label="CF-Ray"
                                    value={activity.cf_ray}
                                    mono
                                />
                            )}
                        </DetailSection>

                        {/* Section: Device & Browser */}
                        <DetailSection title="Device & Browser">
                            {activity.browser && (
                                <DetailField
                                    icon={<Globe className="h-3.5 w-3.5" />}
                                    label="Browser"
                                    value={activity.browser}
                                />
                            )}
                            {activity.os && (
                                <DetailField
                                    icon={<Laptop className="h-3.5 w-3.5" />}
                                    label="Operating System"
                                    value={activity.os}
                                />
                            )}
                            {activity.device_type && (
                                <DetailField
                                    icon={(() => { const DI = deviceIcon[activity.device_type] || Laptop; return <DI className="h-3.5 w-3.5" /> })()}
                                    label="Device Type"
                                    value={activity.device_type}
                                />
                            )}
                            {activity.user_agent && (
                                <div className="col-span-full">
                                    <DetailField
                                        icon={<FileText className="h-3.5 w-3.5" />}
                                        label="User Agent"
                                        value={activity.user_agent}
                                        mono
                                        wrap
                                    />
                                </div>
                            )}
                        </DetailSection>

                        {/* Section: Event info */}
                        <DetailSection title="Event">
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
                            {activity.resource_id && (
                                <DetailField
                                    icon={<Hash className="h-3.5 w-3.5" />}
                                    label="Resource ID"
                                    value={activity.resource_id}
                                    mono
                                />
                            )}
                            {activity.incident && (
                                <DetailField
                                    icon={<AlertTriangle className="h-3.5 w-3.5" />}
                                    label="Incident"
                                    value={activity.incident.title}
                                />
                            )}
                            <DetailField
                                icon={<Clock className="h-3.5 w-3.5" />}
                                label="Timestamp"
                                value={formatFullTimestamp(activity.created_at)}
                            />
                        </DetailSection>

                        {/* Query Parameters */}
                        {activity.request_query_params && Object.keys(activity.request_query_params).length > 0 && (
                            <DetailSection title="Query Parameters">
                                <div className="col-span-full">
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
                                        {Object.entries(activity.request_query_params).map(([key, value]) => (
                                            <div key={key} className="flex items-baseline gap-2 text-xs">
                                                <span className="text-muted-foreground shrink-0 font-mono">{key}:</span>
                                                <span className="font-mono text-foreground truncate">{String(value)}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </DetailSection>
                        )}

                        {/* Request Body Summary */}
                        {activity.request_body_summary && Object.keys(activity.request_body_summary).length > 0 && (
                            <DetailSection title="Request Body (Summary)">
                                <div className="col-span-full">
                                    <pre className="text-xs font-mono bg-background/50 rounded p-2 overflow-x-auto max-h-40 text-foreground/80">
                                        {JSON.stringify(activity.request_body_summary, null, 2)}
                                    </pre>
                                </div>
                            </DetailSection>
                        )}

                        {/* Details / metadata */}
                        {activity.details && Object.keys(activity.details).length > 0 && (
                            <DetailSection title="Additional Details">
                                <div className="col-span-full">
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
                            </DetailSection>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div className="border-b border-border/30 pb-3 last:border-b-0 last:pb-0">
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">{title}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3 text-sm">
                {children}
            </div>
        </div>
    )
}

function DetailField({ icon, label, value, mono, wrap, className }: {
    icon: React.ReactNode
    label: string
    value: string
    mono?: boolean
    wrap?: boolean
    className?: string
}) {
    return (
        <div className="flex items-start gap-2">
            <span className="text-muted-foreground mt-0.5 shrink-0">{icon}</span>
            <div className="min-w-0">
                <p className="text-[11px] text-muted-foreground">{label}</p>
                <p className={`text-sm ${mono ? 'font-mono text-xs' : ''} ${wrap ? 'break-all' : 'truncate'} ${className || ''}`}>{value}</p>
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
    const [liveCount, setLiveCount] = useState(0)

    // Pagination
    const [page, setPage] = useState(1)
    const [totalPages, setTotalPages] = useState(1)
    const [total, setTotal] = useState(0)

    // Filters
    const [filterEventType, setFilterEventType] = useState('')
    const [filterAction, setFilterAction] = useState('')
    const [showFilters, setShowFilters] = useState(false)

    // Real-time activity via WebSocket
    useSocketEvent<Partial<AuditLog>>('activity:new', useCallback((data) => {
        if (page === 1 && !filterEventType && !filterAction) {
            setActivities(prev => {
                const exists = prev.some(a => a.id === data.id)
                if (exists) return prev
                return [data as AuditLog, ...prev].slice(0, PER_PAGE)
            })
            setTotal(prev => prev + 1)
            setLiveCount(prev => prev + 1)
        }
    }, [page, filterEventType, filterAction]))

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
            setLiveCount(0)
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
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-semibold">Activity</h1>
                    <p className="text-sm text-muted-foreground mt-1">Track all system activity and audit logs</p>
                </div>
                {liveCount > 0 && (
                    <div className="flex items-center gap-1.5 text-xs text-emerald-600 bg-emerald-50 dark:bg-emerald-950/40 dark:text-emerald-400 px-2.5 py-1 rounded-full">
                        <Radio className="h-3 w-3 animate-pulse" />
                        {liveCount} new
                    </div>
                )}
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
