"use client"

import { useEffect, useState, useCallback, useMemo } from 'react'
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
import type { TimelineEvent, CompromisedHost, D3FENDTechnique, MitreMapping } from '@/types'
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
    const [currentPage, setCurrentPage] = useState(1)
    const EVENTS_PER_PAGE = 25

    const [form, setForm] = useState({
        timestamp: '',
        activity: '',
        source: '',
        host_id: '',
        mitre_mappings: [] as MitreMapping[],
    })

    // Currently editing mapping index (-1 = adding new)
    const [editingMappingIdx, setEditingMappingIdx] = useState(-1)
    const [mappingDraft, setMappingDraft] = useState({ tactic: '', technique: '' })

    // MITRE ATT&CK form data for bidirectional tactic/technique linking
    const [mitreFormData, setMitreFormData] = useState<{
        tactics: { id: string; name: string; slug: string }[]
        techByTactic: Record<string, { id: string; name: string }[]>
        techToTactic: Record<string, string>
        allTechniques: { id: string; name: string }[]
    }>({ tactics: [], techByTactic: {}, techToTactic: {}, allTechniques: [] })
    const [techSearch, setTechSearch] = useState('')

    // Fetch MITRE ATT&CK form data once on dialog open
    useEffect(() => {
        if (!showAddModal || mitreFormData.tactics.length > 0) return
        api.get<{
            tactics: { id: string; name: string; slug: string }[]
            technique_by_tactic: Record<string, { id: string; name: string }[]>
            technique_to_tactic: Record<string, string>
        }>('/knowledge-base/mitre-attack/form-data').then(data => {
            const all: { id: string; name: string }[] = []
            const seen = new Set<string>()
            for (const techs of Object.values(data.technique_by_tactic)) {
                for (const t of techs) {
                    if (!seen.has(t.id)) { seen.add(t.id); all.push(t) }
                }
            }
            all.sort((a, b) => a.id.localeCompare(b.id))
            setMitreFormData({
                tactics: data.tactics,
                techByTactic: data.technique_by_tactic,
                techToTactic: data.technique_to_tactic,
                allTechniques: all,
            })
        }).catch(() => {})
    }, [showAddModal, mitreFormData.tactics.length])

    // Techniques available for the selected tactic (or all if none selected)
    const availableTechniques = useMemo(() => {
        if (mappingDraft.tactic && mitreFormData.techByTactic[mappingDraft.tactic]) {
            return mitreFormData.techByTactic[mappingDraft.tactic]
        }
        return mitreFormData.allTechniques
    }, [mappingDraft.tactic, mitreFormData])

    // Filtered techniques based on search input
    const filteredTechniques = useMemo(() => {
        if (!techSearch) return availableTechniques.slice(0, 50)
        const q = techSearch.toLowerCase()
        return availableTechniques.filter(
            t => t.id.toLowerCase().includes(q) || t.name.toLowerCase().includes(q)
        ).slice(0, 50)
    }, [availableTechniques, techSearch])

    // Handle tactic change — clear technique if it doesn't belong to the new tactic
    const handleTacticChange = (slug: string) => {
        const techs = mitreFormData.techByTactic[slug] || []
        const currentTechInNewTactic = techs.some(t => t.id === mappingDraft.technique)
        setMappingDraft({
            tactic: slug,
            technique: currentTechInNewTactic ? mappingDraft.technique : '',
        })
        setTechSearch('')
    }

    // Handle technique selection — auto-select tactic
    const handleTechniqueSelect = (techId: string) => {
        const tacticSlug = mitreFormData.techToTactic[techId]
        setMappingDraft({
            technique: techId,
            tactic: tacticSlug || mappingDraft.tactic,
        })
        setTechSearch('')
    }

    // Handle manual technique ID input — auto-resolve tactic
    const handleTechniqueInput = (value: string) => {
        const upper = value.toUpperCase().trim()
        setTechSearch(value)
        const resolvedTactic = mitreFormData.techToTactic[upper]
        setMappingDraft({
            technique: upper,
            tactic: resolvedTactic || mappingDraft.tactic,
        })
    }

    // Add current mapping draft to the form's mitre_mappings list
    const handleAddMapping = () => {
        if (!mappingDraft.tactic && !mappingDraft.technique) return
        const techName = mitreFormData.allTechniques.find(t => t.id === mappingDraft.technique)?.name || ''
        const newMapping: MitreMapping = {
            tactic: mappingDraft.tactic,
            technique: mappingDraft.technique,
            name: techName,
        }
        setForm(prev => ({
            ...prev,
            mitre_mappings: [...prev.mitre_mappings, newMapping],
        }))
        setMappingDraft({ tactic: '', technique: '' })
        setTechSearch('')
    }

    // Remove a mapping by index
    const handleRemoveMapping = (idx: number) => {
        setForm(prev => ({
            ...prev,
            mitre_mappings: prev.mitre_mappings.filter((_, i) => i !== idx),
        }))
    }

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
        // Fetch D3FEND suggestions for all techniques in mappings
        const mappings = event.mitre_mappings || []
        const techniques = mappings.map(m => m.technique).filter(Boolean)
        // Fall back to legacy field
        if (techniques.length === 0 && event.mitre_technique) techniques.push(event.mitre_technique)
        for (const tech of techniques) {
            if (!d3fendCache[tech]) {
                fetchD3fendSuggestions(tech)
            }
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
            // Paginate through ALL timeline events (backend defaults to 50)
            const allEvents: TimelineEvent[] = []
            let page = 1
            let totalPages = 1
            do {
                const res = await api.get<{ items: TimelineEvent[]; pages: number }>(
                    `/incidents/${incidentId}/timeline?per_page=200&page=${page}`
                )
                allEvents.push(...(res.items || []))
                totalPages = res.pages || 1
                page++
            } while (page <= totalPages)

            const hostsRes = await api.get<{ items: CompromisedHost[] }>(`/incidents/${incidentId}/hosts`)
            setEvents(allEvents)
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
            const payload = {
                timestamp: form.timestamp,
                activity: form.activity,
                source: form.source || null,
                host_id: form.host_id || null,
                mitre_mappings: form.mitre_mappings.length > 0 ? form.mitre_mappings : undefined,
            }
            if (editingId) {
                await api.put(`/incidents/${incidentId}/timeline/${editingId}`, payload)
            } else {
                await api.post(`/incidents/${incidentId}/timeline`, payload)
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
        // Build mitre_mappings from event
        let mappings: MitreMapping[] = event.mitre_mappings || []
        if (mappings.length === 0 && (event.mitre_tactic || event.mitre_technique)) {
            mappings = [{ tactic: event.mitre_tactic || '', technique: event.mitre_technique || '', name: '' }]
        }
        setForm({
            timestamp: event.timestamp ? new Date(event.timestamp).toISOString().slice(0, 16) : '',
            activity: event.activity,
            source: event.source || '',
            host_id: event.host?.id || '',
            mitre_mappings: mappings,
        })
        setMappingDraft({ tactic: '', technique: '' })
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
            mitre_mappings: [],
        })
        setMappingDraft({ tactic: '', technique: '' })
        setTechSearch('')
    }

    const filteredEvents = events.filter(e => {
        const q = search.toLowerCase()
        if (!q) return true
        return (
            e.activity.toLowerCase().includes(q) ||
            e.mitre_tactic?.toLowerCase().includes(q) ||
            e.mitre_mappings?.some(m =>
                m.tactic?.toLowerCase().includes(q) ||
                m.technique?.toLowerCase().includes(q) ||
                m.name?.toLowerCase().includes(q)
            )
        )
    })

    const totalPages = Math.max(1, Math.ceil(filteredEvents.length / EVENTS_PER_PAGE))
    const paginatedEvents = filteredEvents.slice((currentPage - 1) * EVENTS_PER_PAGE, currentPage * EVENTS_PER_PAGE)

    // Reset to page 1 when search changes
    useEffect(() => { setCurrentPage(1) }, [search])

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
                                    paginatedEvents.map(event => {
                                        const isExpanded = expandedId === event.id
                                        const mappings = event.mitre_mappings?.length ? event.mitre_mappings : (event.mitre_tactic ? [{ tactic: event.mitre_tactic, technique: event.mitre_technique || '', name: '' }] : [])
                                        const allTechniqueIds = mappings.map(m => m.technique).filter(Boolean)
                                        const allD3fend = allTechniqueIds.flatMap(tid => d3fendCache[tid] || [])
                                        const isLoadingD3fend = allTechniqueIds.some(tid => d3fendLoading === tid)

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
                                                            {mappings.length > 0 ? mappings.map((m, i) => (
                                                                <div key={i} className="flex items-center gap-1.5">
                                                                    <Badge variant="outline" className={`text-[10px] ${tacticColors[m.tactic?.toLowerCase()] || ''}`}>{m.tactic}</Badge>
                                                                    {m.technique && <span className="text-xs font-mono text-muted-foreground">{m.technique}</span>}
                                                                </div>
                                                            )) : <span className="text-xs text-muted-foreground">—</span>}
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
                                                                        {mappings.length > 0 && (
                                                                            <div className="space-y-1">
                                                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                                                    <Target className="h-3 w-3" />
                                                                                    <span className="font-medium">MITRE ATT&CK</span>
                                                                                </div>
                                                                                <div className="flex flex-col gap-1 pl-5">
                                                                                    {mappings.map((m, i) => (
                                                                                        <div key={i} className="flex items-center gap-2">
                                                                                            <Badge variant="outline" className={`text-[10px] ${tacticColors[m.tactic?.toLowerCase()] || ''}`}>
                                                                                                {m.tactic}
                                                                                            </Badge>
                                                                                            {m.technique && (
                                                                                                <span className="text-xs font-mono text-muted-foreground">{m.technique}</span>
                                                                                            )}
                                                                                            {m.name && (
                                                                                                <span className="text-xs text-muted-foreground">— {m.name}</span>
                                                                                            )}
                                                                                        </div>
                                                                                    ))}
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
                                                                {allTechniqueIds.length > 0 && (
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
                                                                        ) : allD3fend.length > 0 ? (
                                                                            <div className="max-h-64 overflow-y-auto rounded-md border border-white/10 p-2 grid gap-2">
                                                                                {allD3fend.map((d3) => (
                                                                                    <div
                                                                                        key={d3.id}
                                                                                        className={`rounded-md border px-3 py-2 ${d3fendTacticColors[d3.tactic] || 'bg-white/5 text-muted-foreground border-white/10'}`}
                                                                                    >
                                                                                        <div className="flex items-center gap-2 mb-1">
                                                                                            <span className="text-xs font-mono opacity-70">{d3.id}</span>
                                                                                            <span className="text-sm font-medium">{d3.name}</span>
                                                                                            {d3.source === 'platform-suggested' && (
                                                                                                <Badge variant="glass" className="text-[8px] px-1 py-0">Suggested</Badge>
                                                                                            )}
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
                                                                        ) : (
                                                                            <p className="text-xs text-muted-foreground py-1">
                                                                                No D3FEND countermeasures mapped for {allTechniqueIds.join(', ')}
                                                                            </p>
                                                                        )}
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

            {/* Pagination */}
            {filteredEvents.length > EVENTS_PER_PAGE && (
                <div className="flex items-center justify-between px-2">
                    <span className="text-xs text-muted-foreground">
                        Showing {(currentPage - 1) * EVENTS_PER_PAGE + 1}–{Math.min(currentPage * EVENTS_PER_PAGE, filteredEvents.length)} of {filteredEvents.length} events
                    </span>
                    <div className="flex items-center gap-1">
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={currentPage <= 1}
                            onClick={() => setCurrentPage(p => p - 1)}
                        >
                            Previous
                        </Button>
                        {Array.from({ length: totalPages }, (_, i) => i + 1)
                            .filter(p => p === 1 || p === totalPages || Math.abs(p - currentPage) <= 1)
                            .reduce<(number | string)[]>((acc, p, i, arr) => {
                                if (i > 0 && p - (arr[i - 1] as number) > 1) acc.push('...')
                                acc.push(p)
                                return acc
                            }, [])
                            .map((p, i) =>
                                typeof p === 'string' ? (
                                    <span key={`ellipsis-${i}`} className="px-1 text-xs text-muted-foreground">…</span>
                                ) : (
                                    <Button
                                        key={p}
                                        variant={p === currentPage ? 'default' : 'outline'}
                                        size="sm"
                                        className="h-8 w-8 p-0"
                                        onClick={() => setCurrentPage(p)}
                                    >
                                        {p}
                                    </Button>
                                )
                            )}
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={currentPage >= totalPages}
                            onClick={() => setCurrentPage(p => p + 1)}
                        >
                            Next
                        </Button>
                    </div>
                </div>
            )}

            <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>{editingId ? 'Edit Event' : 'Add Event'}</DialogTitle>
                    </DialogHeader>
                    <DialogBody className="space-y-4">
                        <div className="space-y-2">
                            <Label>Timestamp *</Label>
                            <Input type="datetime-local" value={form.timestamp} onChange={e => setForm({ ...form, timestamp: e.target.value })} />
                        </div>
                        <div className="space-y-2">
                            <Label>Activity *</Label>
                            <Textarea value={form.activity} onChange={e => setForm({ ...form, activity: e.target.value })} />
                        </div>
                        <div className="space-y-2">
                            <Label>Source</Label>
                            <Input value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} placeholder="e.g. Sysmon, EDR, Firewall..." />
                        </div>
                        <div className="space-y-2">
                            <Label>Host</Label>
                            <Select value={form.host_id} onValueChange={v => setForm({ ...form, host_id: v })}>
                                <SelectTrigger><SelectValue placeholder="Select Host" /></SelectTrigger>
                                <SelectContent>
                                    {hosts.map(h => (
                                        <SelectItem key={h.id} value={h.id}>
                                            {h.hostname}{h.ip_address ? ` (${h.ip_address})` : ''}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        {/* MITRE ATT&CK Mappings */}
                        <div className="space-y-3">
                            <Label>MITRE ATT&CK Mappings</Label>
                            <p className="text-xs text-muted-foreground">
                                Add one or more MITRE ATT&CK tactics &amp; techniques. Leave empty for auto-suggest.
                            </p>

                            {/* Existing mappings list */}
                            {form.mitre_mappings.length > 0 && (
                                <div className="space-y-1.5">
                                    {form.mitre_mappings.map((m, i) => (
                                        <div key={i} className="flex items-center gap-2 rounded-md border border-white/10 bg-white/[0.03] px-3 py-1.5">
                                            <Badge variant="outline" className={`text-[10px] ${tacticColors[m.tactic?.toLowerCase()] || ''}`}>
                                                {m.tactic}
                                            </Badge>
                                            <span className="text-xs font-mono text-muted-foreground">{m.technique}</span>
                                            {m.name && <span className="text-xs text-muted-foreground truncate">— {m.name}</span>}
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="sm"
                                                className="ml-auto h-6 w-6 p-0 text-destructive hover:text-destructive"
                                                onClick={() => handleRemoveMapping(i)}
                                            >
                                                <Trash2 className="h-3 w-3" />
                                            </Button>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Add mapping row */}
                            <div className="grid grid-cols-[1fr_1fr_auto] gap-2 items-end">
                                <div className="space-y-1">
                                    <Label className="text-xs">Tactic</Label>
                                    <Select value={mappingDraft.tactic} onValueChange={handleTacticChange}>
                                        <SelectTrigger><SelectValue placeholder="Select Tactic" /></SelectTrigger>
                                        <SelectContent side="top">
                                            {mitreFormData.tactics.map(t => (
                                                <SelectItem key={t.slug} value={t.slug}>{t.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-1">
                                    <Label className="text-xs">Technique</Label>
                                    <div className="relative">
                                        <Input
                                            value={techSearch || mappingDraft.technique}
                                            onChange={e => handleTechniqueInput(e.target.value)}
                                            placeholder="Search T1059 or name..."
                                            onFocus={() => setTechSearch(mappingDraft.technique)}
                                            onBlur={() => setTimeout(() => setTechSearch(''), 200)}
                                        />
                                        {techSearch && filteredTechniques.length > 0 && (
                                            <div className="absolute z-50 bottom-full mb-1 left-0 right-0 max-h-48 overflow-y-auto rounded-md border border-white/10 bg-background/95 backdrop-blur-sm shadow-lg">
                                                {filteredTechniques.map(t => (
                                                    <button
                                                        key={t.id}
                                                        type="button"
                                                        className="w-full text-left px-3 py-1.5 text-xs hover:bg-white/10 cursor-pointer flex items-center gap-2"
                                                        onMouseDown={e => { e.preventDefault(); handleTechniqueSelect(t.id) }}
                                                    >
                                                        <span className="font-mono text-muted-foreground">{t.id}</span>
                                                        <span className="truncate">{t.name}</span>
                                                    </button>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </div>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="h-9"
                                    onClick={handleAddMapping}
                                    disabled={!mappingDraft.tactic && !mappingDraft.technique}
                                >
                                    <Plus className="h-3.5 w-3.5" />
                                </Button>
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
