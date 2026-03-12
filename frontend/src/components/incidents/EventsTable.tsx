"use client"

import { useEffect, useState, useCallback } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
    DialogBody,
} from '@/components/ui/dialog'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
    GlassTable,
    TableEmpty,
} from '@/components/ui/table'
import { SkeletonTableRow, Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/utils'
import api from '@/lib/api'
import type { TimelineEvent, CompromisedHost, D3FENDTechnique } from '@/types'
import {
    Plus,
    Clock,
    Search,
    Filter,
    MoreHorizontal,
    Trash2,
    AlertTriangle,
    Server,
    Edit2,
    Star,
    ChevronDown,
    ChevronRight,
    Shield,
    Target,
    Tag,
    Loader2,
} from 'lucide-react'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { useToast } from '@/components/ui/use-toast'

const tacticColors: Record<string, string> = {
    'reconnaissance': 'text-blue-400',
    'resource-development': 'text-blue-300',
    'resource development': 'text-blue-300',
    'initial-access': 'text-amber-400',
    'initial access': 'text-amber-400',
    'execution': 'text-orange-400',
    'persistence': 'text-rose-400',
    'privilege-escalation': 'text-red-400',
    'privilege escalation': 'text-red-400',
    'defense-evasion': 'text-pink-400',
    'defense evasion': 'text-pink-400',
    'credential-access': 'text-yellow-400',
    'credential access': 'text-yellow-400',
    'discovery': 'text-cyan-400',
    'lateral-movement': 'text-emerald-400',
    'lateral movement': 'text-emerald-400',
    'collection': 'text-violet-400',
    'command-and-control': 'text-purple-400',
    'command and control': 'text-purple-400',
    'exfiltration': 'text-red-300',
    'impact': 'text-red-500',
}

const d3fendTacticColors: Record<string, string> = {
    'Harden': 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    'Detect': 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    'Isolate': 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    'Deceive': 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    'Evict': 'bg-red-500/10 text-red-400 border-red-500/20',
    'Restore': 'bg-green-500/10 text-green-400 border-green-500/20',
}

interface EventsTableProps {
    incidentId: string
}

export function EventsTable({ incidentId }: EventsTableProps) {
    const confirm = useConfirm()
    const { toast } = useToast()
    const [events, setEvents] = useState<TimelineEvent[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [showAddModal, setShowAddModal] = useState(false)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [hosts, setHosts] = useState<CompromisedHost[]>([])
    const [editingId, setEditingId] = useState<string | null>(null)
    const [expandedId, setExpandedId] = useState<string | null>(null)
    const [d3fendCache, setD3fendCache] = useState<Record<string, D3FENDTechnique[]>>({})
    const [d3fendLoading, setD3fendLoading] = useState<string | null>(null)

    const [form, setForm] = useState({
        timestamp: '',
        activity: '',
        source: '',
        host_id: '',
        mitre_tactic: '',
        mitre_technique: '',
    })

    const fetchD3fendSuggestions = useCallback(async (techniqueId: string) => {
        if (d3fendCache[techniqueId]) return
        setD3fendLoading(techniqueId)
        try {
            const res = await api.post<{ items: D3FENDTechnique[]; total: number }>('/knowledge-base/d3fend/suggest', {
                attack_techniques: [techniqueId],
            })
            setD3fendCache(prev => ({ ...prev, [techniqueId]: res.items || [] }))
        } catch {
            setD3fendCache(prev => ({ ...prev, [techniqueId]: [] }))
        } finally {
            setD3fendLoading(null)
        }
    }, [d3fendCache])

    const handleToggleExpand = useCallback((event: TimelineEvent) => {
        if (expandedId === event.id) {
            setExpandedId(null)
            return
        }
        setExpandedId(event.id)
        if (event.mitre_technique && !d3fendCache[event.mitre_technique]) {
            fetchD3fendSuggestions(event.mitre_technique)
        }
    }, [expandedId, d3fendCache, fetchD3fendSuggestions])

    useEffect(() => {
        if (incidentId) {
            loadData()
        }
    }, [incidentId])

    const loadData = async () => {
        setIsLoading(true)
        try {
            const [eventsRes, hostsRes] = await Promise.all([
                api.get<{ items: TimelineEvent[] }>(`/incidents/${incidentId}/timeline`),
                api.get<{ items: CompromisedHost[] }>(`/incidents/${incidentId}/hosts`),
            ])
            setEvents(eventsRes.items || [])
            setHosts(hostsRes.items || [])
        } catch (error) {
            console.error('Failed to load events:', error)
        } finally {
            setIsLoading(false)
        }
    }

    const handleAddEvent = async () => {
        if (!form.timestamp || !form.activity) return
        setIsSubmitting(true)
        try {
            if (editingId) {
                await api.put(`/incidents/${incidentId}/timeline/${editingId}`, {
                    timestamp: form.timestamp,
                    activity: form.activity,
                    source: form.source || null,
                    host_id: form.host_id || null,
                    mitre_tactic: form.mitre_tactic || null,
                    mitre_technique: form.mitre_technique || null,
                })
            } else {
                await api.post(`/incidents/${incidentId}/timeline`, {
                    timestamp: form.timestamp,
                    activity: form.activity,
                    source: form.source || null,
                    host_id: form.host_id || null,
                    mitre_tactic: form.mitre_tactic || null,
                    mitre_technique: form.mitre_technique || null,
                })
            }
            setShowAddModal(false)
            setEditingId(null)
            resetForm()
            loadData()
        } catch (error) {
            console.error('Failed to save event:', error)
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleDelete = async (id: string) => {
        const confirmed = await confirm({
            title: 'Delete Event',
            description: 'Are you sure you want to delete this timeline event?',
            confirmLabel: 'Delete',
            variant: 'destructive',
        })
        if (!confirmed) return
        try {
            await api.delete(`/incidents/${incidentId}/timeline/${id}`)
            loadData()
        } catch (error) {
            console.error('Failed to delete:', error)
        }
    }

    const handleEditClick = (event: TimelineEvent) => {
        setEditingId(event.id)
        setForm({
            timestamp: event.timestamp ? new Date(event.timestamp).toISOString().slice(0, 16) : '',
            activity: event.activity,
            source: event.source || '',
            host_id: event.host?.id || '',
            mitre_tactic: event.mitre_tactic || '',
            mitre_technique: event.mitre_technique || '',
        })
        setShowAddModal(true)
    }

    const handleToggleKeyEvent = async (event: TimelineEvent) => {
        try {
            const res = await api.put<TimelineEvent>(`/incidents/${incidentId}/timeline/${event.id}`, {
                is_key_event: !event.is_key_event,
            })
            setEvents(prev => prev.map(e => e.id === event.id ? { ...e, is_key_event: !e.is_key_event } : e))
            toast({
                title: event.is_key_event ? 'Removed from Timeline' : 'Pinned to Timeline',
                description: event.is_key_event
                    ? 'Event will no longer appear on the visual timeline.'
                    : 'Event will now appear on the visual timeline.',
            })
        } catch (error) {
            console.error('Failed to toggle key event:', error)
            toast({ title: 'Error', description: 'Failed to update event', variant: 'destructive' })
        }
    }

    const resetForm = () => {
        setForm({
            timestamp: '',
            activity: '',
            source: '',
            host_id: '',
            mitre_tactic: '',
            mitre_technique: '',
        })
    }

    const filteredEvents = events.filter(e =>
        e.activity.toLowerCase().includes(search.toLowerCase()) ||
        e.mitre_tactic?.toLowerCase().includes(search.toLowerCase())
    )

    return (
        <div className="space-y-4">
            <Card>
                <CardContent className="p-4">
                    <div className="flex justify-between items-center gap-4">
                        <div className="relative flex-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search events..." className="pl-10" variant="glass" />
                        </div>
                        <Button onClick={() => { setEditingId(null); resetForm(); setShowAddModal(true); }}>
                            <Plus className="mr-2 h-4 w-4" /> Add Event
                        </Button>
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardContent className="p-0">
                    <GlassTable className="border-0">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead className="w-[32px]"></TableHead>
                                    <TableHead className="w-[40px]" title="Pin to timeline">
                                        <Star className="h-3.5 w-3.5 text-muted-foreground" />
                                    </TableHead>
                                    <TableHead>Time</TableHead>
                                    <TableHead>Host</TableHead>
                                    <TableHead>Activity</TableHead>
                                    <TableHead>MITRE Tactic / Technique</TableHead>
                                    <TableHead className="w-[100px]"></TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {isLoading ? <SkeletonTableRow columns={7} /> : filteredEvents.length === 0 ? (
                                    <TableRow><TableCell colSpan={7}>
                                        <TableEmpty
                                            title={search ? 'No matching events' : 'No timeline events'}
                                            description={search ? 'Try adjusting your search criteria' : 'Build a chronological timeline of attacker activity, system events, and investigation milestones.'}
                                            icon={<Clock className="w-8 h-8" />}
                                        />
                                    </TableCell></TableRow>
                                ) : (
                                    filteredEvents.map(event => {
                                        const isExpanded = expandedId === event.id
                                        const techniqueId = event.mitre_technique
                                        const d3fendResults = techniqueId ? d3fendCache[techniqueId] : undefined
                                        const isLoadingD3fend = d3fendLoading === techniqueId

                                        return (
                                            <>
                                                <TableRow
                                                    key={event.id}
                                                    className={`group cursor-pointer transition-colors ${isExpanded ? 'bg-white/[0.03]' : 'hover:bg-white/[0.02]'}`}
                                                    onClick={() => handleToggleExpand(event)}
                                                >
                                                    <TableCell className="w-[32px] px-2">
                                                        {isExpanded
                                                            ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
                                                            : <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                                        }
                                                    </TableCell>
                                                    <TableCell className="w-[40px]">
                                                        <button
                                                            onClick={(e) => { e.stopPropagation(); handleToggleKeyEvent(event) }}
                                                            className={`p-0.5 rounded transition-colors ${event.is_key_event
                                                                ? 'text-amber-400 hover:text-amber-300'
                                                                : 'text-muted-foreground/30 hover:text-amber-400/60'
                                                            }`}
                                                            title={event.is_key_event ? 'Remove from timeline' : 'Pin to timeline'}
                                                        >
                                                            <Star className={`h-4 w-4 ${event.is_key_event ? 'fill-current' : ''}`} />
                                                        </button>
                                                    </TableCell>
                                                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                                                        {formatDateTime(event.timestamp)}
                                                    </TableCell>
                                                    <TableCell>
                                                        {event.host || event.hostname ? (
                                                            <div className="flex items-center gap-1">
                                                                <Server className="h-3 w-3 text-muted-foreground" />
                                                                {event.host?.hostname || event.hostname}
                                                            </div>
                                                        ) : '-'}
                                                    </TableCell>
                                                    <TableCell className="max-w-[400px] truncate" title={event.activity}>
                                                        {event.activity}
                                                    </TableCell>
                                                    <TableCell>
                                                        <div className="flex flex-col gap-1 items-start">
                                                            {event.mitre_tactic && <Badge variant="outline" className="text-[10px]">{event.mitre_tactic}</Badge>}
                                                            {event.mitre_technique && <span className="text-xs font-mono text-muted-foreground">{event.mitre_technique}</span>}
                                                        </div>
                                                    </TableCell>
                                                    <TableCell>
                                                        <div className="flex items-center gap-1">
                                                            <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100" onClick={(e) => { e.stopPropagation(); handleEditClick(event) }} title="Edit event">
                                                                <Edit2 className="w-4 h-4" />
                                                            </Button>
                                                            <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100 text-destructive" onClick={(e) => { e.stopPropagation(); handleDelete(event.id) }} title="Delete event">
                                                                <Trash2 className="w-4 h-4" />
                                                            </Button>
                                                        </div>
                                                    </TableCell>
                                                </TableRow>

                                                {isExpanded && (
                                                    <TableRow key={`${event.id}-detail`} className="bg-white/[0.02] hover:bg-white/[0.02]">
                                                        <TableCell colSpan={7} className="p-0">
                                                            <div className="px-6 py-4 space-y-4 border-l-2 border-blue-500/30 ml-4">
                                                                {/* Event Details */}
                                                                <div>
                                                                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Event Details</h4>
                                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                                        <div className="space-y-1">
                                                                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                                                <Clock className="h-3 w-3" />
                                                                                <span className="font-medium">Timestamp</span>
                                                                            </div>
                                                                            <p className="text-sm pl-5">{formatDateTime(event.timestamp)}</p>
                                                                        </div>
                                                                        {(event.host || event.hostname) && (
                                                                            <div className="space-y-1">
                                                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                                                    <Server className="h-3 w-3" />
                                                                                    <span className="font-medium">Host</span>
                                                                                </div>
                                                                                <p className="text-sm pl-5">{event.host?.hostname || event.hostname}</p>
                                                                            </div>
                                                                        )}
                                                                        {event.source && (
                                                                            <div className="space-y-1">
                                                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                                                    <Tag className="h-3 w-3" />
                                                                                    <span className="font-medium">Source</span>
                                                                                </div>
                                                                                <p className="text-sm pl-5">{event.source}</p>
                                                                            </div>
                                                                        )}
                                                                        {event.mitre_tactic && (
                                                                            <div className="space-y-1">
                                                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                                                    <Target className="h-3 w-3" />
                                                                                    <span className="font-medium">MITRE ATT&CK</span>
                                                                                </div>
                                                                                <div className="flex items-center gap-2 pl-5">
                                                                                    <Badge variant="outline" className={`text-[10px] ${tacticColors[event.mitre_tactic.toLowerCase()] || ''}`}>
                                                                                        {event.mitre_tactic}
                                                                                    </Badge>
                                                                                    {event.mitre_technique && (
                                                                                        <span className="text-xs font-mono text-muted-foreground">{event.mitre_technique}</span>
                                                                                    )}
                                                                                </div>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>

                                                                {/* Activity Full Text */}
                                                                <div>
                                                                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Activity</h4>
                                                                    <p className="text-sm whitespace-pre-wrap">{event.activity}</p>
                                                                </div>

                                                                {/* D3FEND Mitigations */}
                                                                {techniqueId && (
                                                                    <div>
                                                                        <div className="flex items-center gap-2 mb-2">
                                                                            <Shield className="h-3.5 w-3.5 text-blue-400" />
                                                                            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                                                                                Recommended Mitigations (D3FEND)
                                                                            </h4>
                                                                        </div>

                                                                        {isLoadingD3fend ? (
                                                                            <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
                                                                                <Loader2 className="h-3 w-3 animate-spin" />
                                                                                Loading D3FEND countermeasures...
                                                                            </div>
                                                                        ) : d3fendResults && d3fendResults.length > 0 ? (
                                                                            <div className="grid gap-2">
                                                                                {d3fendResults.map((d3) => (
                                                                                    <div
                                                                                        key={d3.id}
                                                                                        className={`rounded-md border px-3 py-2 ${d3fendTacticColors[d3.tactic] || 'bg-white/5 text-muted-foreground border-white/10'}`}
                                                                                    >
                                                                                        <div className="flex items-center gap-2 mb-1">
                                                                                            <span className="text-xs font-mono opacity-70">{d3.id}</span>
                                                                                            <span className="text-sm font-medium">{d3.name}</span>
                                                                                            <Badge variant="outline" className="text-[9px] ml-auto">{d3.tactic}</Badge>
                                                                                        </div>
                                                                                        <p className="text-xs opacity-80">{d3.description}</p>
                                                                                        {d3.examples && d3.examples.length > 0 && (
                                                                                            <div className="mt-1.5 flex flex-wrap gap-1">
                                                                                                {d3.examples.map((ex, i) => (
                                                                                                    <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5">
                                                                                                        {ex}
                                                                                                    </span>
                                                                                                ))}
                                                                                            </div>
                                                                                        )}
                                                                                    </div>
                                                                                ))}
                                                                            </div>
                                                                        ) : d3fendResults ? (
                                                                            <p className="text-xs text-muted-foreground py-1">
                                                                                No D3FEND countermeasures mapped for {techniqueId}
                                                                            </p>
                                                                        ) : null}
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </TableCell>
                                                    </TableRow>
                                                )}
                                            </>
                                        )
                                    })
                                )}
                            </TableBody>
                        </Table>
                    </GlassTable>
                </CardContent>
            </Card>

            <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>{editingId ? 'Edit Event' : 'Add Event'}</DialogTitle>
                    </DialogHeader>
                    <DialogBody className="space-y-4">
                        <div className="space-y-2">
                            <Label>Timestamp *</Label>
                            <Input type="datetime-local" value={form.timestamp} onChange={e => setForm({ ...form, timestamp: e.target.value })} variant="glass" />
                        </div>
                        <div className="space-y-2">
                            <Label>Activity *</Label>
                            <Textarea value={form.activity} onChange={e => setForm({ ...form, activity: e.target.value })} variant="glass" />
                        </div>
                        <div className="space-y-2">
                            <Label>Source</Label>
                            <Input value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} placeholder="e.g. Sysmon, EDR, Firewall..." variant="glass" />
                        </div>
                        <div className="space-y-2">
                            <Label>Host</Label>
                            <Select value={form.host_id} onValueChange={v => setForm({ ...form, host_id: v })}>
                                <SelectTrigger variant="glass"><SelectValue placeholder="Select Host" /></SelectTrigger>
                                <SelectContent>
                                    {hosts.map(h => (
                                        <SelectItem key={h.id} value={h.id}>
                                            {h.hostname}{h.ip_address ? ` (${h.ip_address})` : ''}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>MITRE Tactic</Label>
                                <Select value={form.mitre_tactic} onValueChange={v => setForm({ ...form, mitre_tactic: v })}>
                                    <SelectTrigger variant="glass"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="initial-access">Initial Access</SelectItem>
                                        <SelectItem value="execution">Execution</SelectItem>
                                        <SelectItem value="persistence">Persistence</SelectItem>
                                        <SelectItem value="privilege-escalation">Privilege Escalation</SelectItem>
                                        <SelectItem value="defense-evasion">Defense Evasion</SelectItem>
                                        <SelectItem value="credential-access">Credential Access</SelectItem>
                                        <SelectItem value="discovery">Discovery</SelectItem>
                                        <SelectItem value="lateral-movement">Lateral Movement</SelectItem>
                                        <SelectItem value="collection">Collection</SelectItem>
                                        <SelectItem value="command-and-control">C2</SelectItem>
                                        <SelectItem value="exfiltration">Exfiltration</SelectItem>
                                        <SelectItem value="impact">Impact</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label>Technique ID</Label>
                                <Input value={form.mitre_technique} onChange={e => setForm({ ...form, mitre_technique: e.target.value })} placeholder="T1059" variant="glass" />
                            </div>
                        </div>
                    </DialogBody>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowAddModal(false)}>Cancel</Button>
                        <Button onClick={handleAddEvent} loading={isSubmitting}>Save</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

        </div>
    )
}
