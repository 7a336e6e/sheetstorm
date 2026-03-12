"use client"

import { useEffect, useState, useMemo } from 'react'
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
import { formatDateTime } from '@/lib/utils'
import api from '@/lib/api'
import type { TimelineEvent, CompromisedHost } from '@/types'
import {
    Clock, Server, ChevronDown, ChevronUp, Plus,
    Tag, Eye, Star,
} from 'lucide-react'

interface IOCVisualTimelineProps {
    incidentId: string
}

const tacticColor: Record<string, string> = {
    'reconnaissance': 'text-blue-400',
    'resource development': 'text-blue-300',
    'initial access': 'text-amber-400',
    'initial-access': 'text-amber-400',
    'execution': 'text-orange-400',
    'persistence': 'text-rose-400',
    'privilege escalation': 'text-red-400',
    'privilege-escalation': 'text-red-400',
    'defense evasion': 'text-pink-400',
    'defense-evasion': 'text-pink-400',
    'credential access': 'text-yellow-400',
    'credential-access': 'text-yellow-400',
    'discovery': 'text-cyan-400',
    'lateral movement': 'text-emerald-400',
    'lateral-movement': 'text-emerald-400',
    'collection': 'text-violet-400',
    'command and control': 'text-purple-400',
    'command-and-control': 'text-purple-400',
    'exfiltration': 'text-red-300',
    'impact': 'text-red-500',
}

function getTacticColor(tactic: string | undefined | null): string {
    if (!tactic) return 'text-muted-foreground'
    return tacticColor[tactic.toLowerCase()] ?? 'text-muted-foreground'
}

export function IOCVisualTimeline({ incidentId }: IOCVisualTimelineProps) {
    const [allEvents, setAllEvents] = useState<TimelineEvent[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [expanded, setExpanded] = useState<string | null>(null)
    const [filterMode, setFilterMode] = useState<'pinned' | 'all'>('pinned')
    const [hosts, setHosts] = useState<CompromisedHost[]>([])

    // Add event dialog
    const [showAddModal, setShowAddModal] = useState(false)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [form, setForm] = useState({
        timestamp: '',
        activity: '',
        host_id: '',
        mitre_tactic: '',
        mitre_technique: '',
    })

    // MITRE ATT&CK form data
    const [tactics, setTactics] = useState<{ id: string; name: string; slug: string }[]>([])
    const [techByTactic, setTechByTactic] = useState<Record<string, { id: string; name: string }[]>>({})
    const [techToTactic, setTechToTactic] = useState<Record<string, string>>({})
    const [allTechniques, setAllTechniques] = useState<{ id: string; name: string }[]>([])
    const [techSearch, setTechSearch] = useState('')

    // Fetch MITRE ATT&CK form data once on dialog open
    useEffect(() => {
        if (!showAddModal || tactics.length > 0) return
        api.get<{
            tactics: { id: string; name: string; slug: string }[]
            technique_by_tactic: Record<string, { id: string; name: string }[]>
            technique_to_tactic: Record<string, string>
        }>('/knowledge-base/mitre-attack/form-data').then(data => {
            setTactics(data.tactics)
            setTechByTactic(data.technique_by_tactic)
            setTechToTactic(data.technique_to_tactic)
            const all: { id: string; name: string }[] = []
            const seen = new Set<string>()
            for (const techs of Object.values(data.technique_by_tactic)) {
                for (const t of techs) {
                    if (!seen.has(t.id)) { seen.add(t.id); all.push(t) }
                }
            }
            all.sort((a, b) => a.id.localeCompare(b.id))
            setAllTechniques(all)
        }).catch(() => {})
    }, [showAddModal, tactics.length])

    // Techniques available for the selected tactic (or all if none selected)
    const availableTechniques = useMemo(() => {
        if (form.mitre_tactic && techByTactic[form.mitre_tactic]) {
            return techByTactic[form.mitre_tactic]
        }
        return allTechniques
    }, [form.mitre_tactic, techByTactic, allTechniques])

    // Filtered techniques based on search input
    const filteredTechniques = useMemo(() => {
        if (!techSearch) return availableTechniques.slice(0, 50)
        const q = techSearch.toLowerCase()
        return availableTechniques.filter(
            t => t.id.toLowerCase().includes(q) || t.name.toLowerCase().includes(q)
        ).slice(0, 50)
    }, [availableTechniques, techSearch])

    // Handle tactic change — clear technique if it doesn't belong
    const handleTacticChange = (slug: string) => {
        const techs = techByTactic[slug] || []
        const currentTechInNewTactic = techs.some(t => t.id === form.mitre_technique)
        setForm({
            ...form,
            mitre_tactic: slug,
            mitre_technique: currentTechInNewTactic ? form.mitre_technique : '',
        })
        setTechSearch('')
    }

    // Handle technique selection — auto-select tactic
    const handleTechniqueSelect = (techId: string) => {
        const tacticSlug = techToTactic[techId]
        setForm({
            ...form,
            mitre_technique: techId,
            mitre_tactic: tacticSlug || form.mitre_tactic,
        })
        setTechSearch('')
    }

    // Handle manual technique ID input — auto-resolve tactic
    const handleTechniqueInput = (value: string) => {
        const upper = value.toUpperCase().trim()
        setTechSearch(value)
        setForm(prev => ({
            ...prev,
            mitre_technique: upper,
            mitre_tactic: techToTactic[upper] || prev.mitre_tactic,
        }))
    }



    useEffect(() => {
        if (incidentId) loadData()
    }, [incidentId])

    const loadData = async () => {
        setIsLoading(true)
        try {
            const [eventsRes, hostsRes] = await Promise.all([
                api.get<{ items: TimelineEvent[] }>(`/incidents/${incidentId}/timeline`),
                api.get<{ items: CompromisedHost[] }>(`/incidents/${incidentId}/hosts`),
            ])
            const sorted = (eventsRes.items || []).sort((a, b) =>
                new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
            )
            setAllEvents(sorted)
            setHosts(hostsRes.items || [])
        } catch (error) {
            console.error('Failed to load events:', error)
        } finally {
            setIsLoading(false)
        }
    }

    const events = filterMode === 'pinned'
        ? allEvents.filter(e => e.is_key_event)
        : allEvents
    const pinnedCount = allEvents.filter(e => e.is_key_event).length

    const handleAddEvent = async () => {
        if (!form.timestamp || !form.activity) return
        setIsSubmitting(true)
        try {
            await api.post(`/incidents/${incidentId}/timeline`, {
                timestamp: form.timestamp,
                activity: form.activity,
                host_id: form.host_id || null,
                mitre_tactic: form.mitre_tactic || null,
                mitre_technique: form.mitre_technique || null,
            })
            setShowAddModal(false)
            setForm({ timestamp: '', activity: '', host_id: '', mitre_tactic: '', mitre_technique: '' })
            loadData()
        } catch (error) {
            console.error('Failed to add event:', error)
        } finally {
            setIsSubmitting(false)
        }
    }

    if (isLoading) {
        return <div className="py-6 text-center text-sm text-muted-foreground animate-pulse">Loading timeline...</div>
    }

    return (
        <div className="space-y-4">
            {/* Controls bar */}
            <Card>
                <CardContent className="p-4">
                    <div className="flex justify-between items-center gap-4">
                        <div className="flex items-center gap-2">
                            <Button
                                variant={filterMode === 'pinned' ? 'default' : 'outline'}
                                size="sm"
                                onClick={() => setFilterMode('pinned')}
                            >
                                <Star className="mr-1.5 h-3.5 w-3.5" /> Pinned ({pinnedCount})
                            </Button>
                            <Button
                                variant={filterMode === 'all' ? 'default' : 'outline'}
                                size="sm"
                                onClick={() => setFilterMode('all')}
                            >
                                <Eye className="mr-1.5 h-3.5 w-3.5" /> All ({allEvents.length})
                            </Button>
                        </div>
                        <Button onClick={() => setShowAddModal(true)} size="sm">
                            <Plus className="mr-2 h-4 w-4" /> Add Event
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Visual Timeline */}
            {events.length === 0 ? (
                <div className="py-10 text-center border border-dashed border-black/10 dark:border-white/10 rounded-lg">
                    <Clock className="w-8 h-8 mx-auto text-muted-foreground/30 mb-3" />
                    <p className="text-sm font-medium text-foreground">
                        {filterMode === 'pinned' ? 'No Pinned Events' : 'No Timeline Events'}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                        {filterMode === 'pinned'
                            ? 'Pin events from the Events tab using the ★ icon to build your timeline.'
                            : 'Add events from the Events tab or click "Add Event" above.'
                        }
                    </p>
                </div>
            ) : (
                <div className="relative pl-5">
                    {/* Thin vertical line */}
                    <div className="absolute left-[7px] top-1 bottom-1 w-px bg-black/10 dark:bg-white/10" />

                    <ol className="space-y-0.5">
                        {events.map((event) => {
                            const isOpen = expanded === event.id
                            const isIoc = event.is_ioc
                            return (
                                <li key={event.id} className="relative group">
                                    {/* Dot — amber for pinned, cyan for normal */}
                                    <div className={`absolute -left-[13px] top-[11px] w-2 h-2 rounded-full ring-2 ring-background z-10 transition-colors ${
                                        event.is_key_event
                                            ? 'bg-amber-400/80 group-hover:bg-amber-300'
                                            : 'bg-cyan-500/80 group-hover:bg-cyan-400'
                                    }`} />

                                    <button
                                        onClick={() => setExpanded(isOpen ? null : event.id)}
                                        className="w-full text-left px-3 py-2 rounded-md hover:bg-black/[0.03] dark:hover:bg-white/[0.03] transition-colors"
                                    >
                                        <div className="flex items-center gap-3 min-w-0">
                                            <span className="shrink-0 text-[11px] font-mono tabular-nums text-muted-foreground w-[130px]">
                                                {formatDateTime(event.timestamp)}
                                            </span>

                                            {isIoc && (
                                                <Badge variant="outline" className="shrink-0 text-[10px] px-1.5 py-0 border-red-400/30 bg-red-400/10 text-red-400">
                                                    <Tag className="h-2.5 w-2.5 mr-0.5" /> IOC
                                                </Badge>
                                            )}

                                            <span className="truncate text-sm text-foreground/90 flex-1 min-w-0">
                                                {event.activity}
                                            </span>

                                            {event.host && (
                                                <span className="hidden sm:flex items-center gap-1 shrink-0 text-xs text-muted-foreground">
                                                    <Server className="h-3 w-3" />
                                                    {event.host.hostname}
                                                </span>
                                            )}

                                            {event.mitre_tactic && (
                                                <Badge variant="outline" className={`shrink-0 text-[10px] px-1.5 py-0 border-black/10 dark:border-white/10 ${getTacticColor(event.mitre_tactic)}`}>
                                                    {event.mitre_tactic}
                                                </Badge>
                                            )}

                                            {event.mitre_technique && (
                                                <span className="shrink-0 text-[10px] font-mono text-muted-foreground/70">
                                                    {event.mitre_technique}
                                                </span>
                                            )}

                                            {isOpen
                                                ? <ChevronUp className="h-3 w-3 shrink-0 text-muted-foreground/50" />
                                                : <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground/30" />
                                            }
                                        </div>
                                    </button>

                                    {/* Expanded detail panel */}
                                    {isOpen && (
                                        <div className="ml-[142px] mr-3 mb-2 px-3 py-2 rounded border border-black/5 dark:border-white/5 bg-black/[0.02] dark:bg-white/[0.02] text-xs space-y-2">
                                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground/80">
                                                {event.host && (
                                                    <span><strong className="text-foreground/70">Host:</strong> {event.host.hostname} {event.host.ip_address && `(${event.host.ip_address})`}</span>
                                                )}
                                                {event.mitre_tactic && (
                                                    <span><strong className="text-foreground/70">Tactic:</strong> {event.mitre_tactic}</span>
                                                )}
                                                {event.mitre_technique && (
                                                    <span><strong className="text-foreground/70">Technique:</strong> {event.mitre_technique}</span>
                                                )}
                                                {event.source && (
                                                    <span><strong className="text-foreground/70">Source:</strong> {event.source}</span>
                                                )}
                                                {event.kill_chain_phase && (
                                                    <span><strong className="text-foreground/70">Kill Chain:</strong> {event.kill_chain_phase}</span>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </li>
                            )
                        })}
                    </ol>

                    {/* Summary footer */}
                    <div className="mt-4 pt-3 border-t border-black/5 dark:border-white/5 flex items-center gap-4 text-[11px] text-muted-foreground/60">
                        <span className="flex items-center gap-1">
                            <Star className="h-3 w-3" /> {pinnedCount} pinned
                        </span>
                        <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" /> {allEvents.length} total
                        </span>
                        {events.length > 0 && (
                            <>
                                <span>First: {formatDateTime(events[0].timestamp)}</span>
                                <span>Last: {formatDateTime(events[events.length - 1].timestamp)}</span>
                            </>
                        )}
                    </div>
                </div>
            )}

            {/* Add Event Dialog */}
            <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Add Timeline Event</DialogTitle>
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
                            <Label>Host</Label>
                            <Select value={form.host_id} onValueChange={v => setForm({ ...form, host_id: v })}>
                                <SelectTrigger><SelectValue placeholder="Select Host" /></SelectTrigger>
                                <SelectContent>
                                    {hosts.map(h => <SelectItem key={h.id} value={h.id}>{h.hostname}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>MITRE Tactic</Label>
                                <Select value={form.mitre_tactic} onValueChange={handleTacticChange}>
                                    <SelectTrigger><SelectValue placeholder="Select Tactic" /></SelectTrigger>
                                    <SelectContent side="top">
                                        {tactics.map(t => (
                                            <SelectItem key={t.slug} value={t.slug}>{t.name}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label>Technique ID</Label>
                                <div className="relative">
                                    <Input
                                        value={techSearch || form.mitre_technique}
                                        onChange={e => handleTechniqueInput(e.target.value)}
                                        placeholder="Search T1059 or name..."
                                        onFocus={() => setTechSearch(form.mitre_technique)}
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
