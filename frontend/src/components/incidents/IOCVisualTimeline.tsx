"use client"

import { useEffect, useState } from 'react'
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
    Clock, Server, Shield, ChevronDown, ChevronUp, Plus,
    Tag, Eye, ShieldAlert, Loader2,
} from 'lucide-react'
import { useToast } from '@/components/ui/use-toast'

interface IOCVisualTimelineProps {
    incidentId: string
}

const ARTIFACT_TYPES = [
    { value: 'file', label: 'File' },
    { value: 'registry', label: 'Registry Key' },
    { value: 'process', label: 'Process' },
    { value: 'service', label: 'Service' },
    { value: 'scheduled_task', label: 'Scheduled Task' },
    { value: 'user_account', label: 'User Account' },
    { value: 'log_entry', label: 'Log Entry' },
    { value: 'other', label: 'Other' },
]

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
    const { toast } = useToast()
    const [allEvents, setAllEvents] = useState<TimelineEvent[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [expanded, setExpanded] = useState<string | null>(null)
    const [filterMode, setFilterMode] = useState<'all' | 'ioc'>('all')
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

    // Mark as IOC dialog
    const [showIocModal, setShowIocModal] = useState(false)
    const [iocEvent, setIocEvent] = useState<TimelineEvent | null>(null)
    const [iocForm, setIocForm] = useState({ artifact_type: 'other', notes: '', is_malicious: true })
    const [iocSubmitting, setIocSubmitting] = useState(false)

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

    const events = filterMode === 'ioc' ? allEvents.filter(e => e.is_ioc) : allEvents
    const iocCount = allEvents.filter(e => e.is_ioc).length

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

    const handleMarkAsIOC = async () => {
        if (!iocEvent) return
        setIocSubmitting(true)
        try {
            await api.post(`/incidents/${incidentId}/timeline/${iocEvent.id}/mark-as-ioc`, {
                artifact_type: iocForm.artifact_type,
                notes: iocForm.notes || undefined,
                is_malicious: iocForm.is_malicious,
            })
            toast({ title: 'IOC Created', description: 'Event marked as IOC and host-based indicator created.' })
            setShowIocModal(false)
            setIocEvent(null)
            loadData()
        } catch (error: any) {
            toast({ title: 'Error', description: error?.message || 'Failed to mark as IOC', variant: 'destructive' })
        } finally {
            setIocSubmitting(false)
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
                                variant={filterMode === 'all' ? 'default' : 'outline'}
                                size="sm"
                                onClick={() => setFilterMode('all')}
                            >
                                <Eye className="mr-1.5 h-3.5 w-3.5" /> All Events ({allEvents.length})
                            </Button>
                            <Button
                                variant={filterMode === 'ioc' ? 'default' : 'outline'}
                                size="sm"
                                onClick={() => setFilterMode('ioc')}
                            >
                                <Shield className="mr-1.5 h-3.5 w-3.5" /> IOCs Only ({iocCount})
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
                <div className="py-10 text-center border border-dashed border-white/10 rounded-lg">
                    <Clock className="w-8 h-8 mx-auto text-muted-foreground/30 mb-3" />
                    <p className="text-sm font-medium text-foreground">
                        {filterMode === 'ioc' ? 'No IOC Events' : 'No Timeline Events'}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                        {filterMode === 'ioc'
                            ? 'Mark events as IOCs to populate this timeline.'
                            : 'Add events from the Events tab or click "Add Event" above.'
                        }
                    </p>
                </div>
            ) : (
                <div className="relative pl-5">
                    {/* Thin vertical line */}
                    <div className="absolute left-[7px] top-1 bottom-1 w-px bg-white/10" />

                    <ol className="space-y-0.5">
                        {events.map((event) => {
                            const isOpen = expanded === event.id
                            const isIoc = event.is_ioc
                            return (
                                <li key={event.id} className="relative group">
                                    {/* Dot — red for IOC, cyan for normal */}
                                    <div className={`absolute -left-[13px] top-[11px] w-2 h-2 rounded-full ring-2 ring-background z-10 transition-colors ${
                                        isIoc
                                            ? 'bg-red-500/80 group-hover:bg-red-400'
                                            : 'bg-cyan-500/80 group-hover:bg-cyan-400'
                                    }`} />

                                    <button
                                        onClick={() => setExpanded(isOpen ? null : event.id)}
                                        className="w-full text-left px-3 py-2 rounded-md hover:bg-white/[0.03] transition-colors"
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
                                                <Badge variant="outline" className={`shrink-0 text-[10px] px-1.5 py-0 border-white/10 ${getTacticColor(event.mitre_tactic)}`}>
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
                                        <div className="ml-[142px] mr-3 mb-2 px-3 py-2 rounded border border-white/5 bg-white/[0.02] text-xs space-y-2">
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
                                            {!isIoc && (
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="text-amber-500 hover:text-amber-400 h-6 text-xs px-2"
                                                    onClick={(e) => {
                                                        e.stopPropagation()
                                                        setIocEvent(event)
                                                        setIocForm({ artifact_type: 'other', notes: '', is_malicious: true })
                                                        setShowIocModal(true)
                                                    }}
                                                >
                                                    <ShieldAlert className="w-3 h-3 mr-1" /> Mark as IOC
                                                </Button>
                                            )}
                                        </div>
                                    )}
                                </li>
                            )
                        })}
                    </ol>

                    {/* Summary footer */}
                    <div className="mt-4 pt-3 border-t border-white/5 flex items-center gap-4 text-[11px] text-muted-foreground/60">
                        <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" /> {allEvents.length} event{allEvents.length !== 1 ? 's' : ''}
                        </span>
                        <span className="flex items-center gap-1">
                            <Shield className="h-3 w-3" /> {iocCount} IOC{iocCount !== 1 ? 's' : ''}
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
                            <Input type="datetime-local" value={form.timestamp} onChange={e => setForm({ ...form, timestamp: e.target.value })} variant="glass" />
                        </div>
                        <div className="space-y-2">
                            <Label>Activity *</Label>
                            <Textarea value={form.activity} onChange={e => setForm({ ...form, activity: e.target.value })} variant="glass" />
                        </div>
                        <div className="space-y-2">
                            <Label>Host</Label>
                            <Select value={form.host_id} onValueChange={v => setForm({ ...form, host_id: v })}>
                                <SelectTrigger variant="glass"><SelectValue placeholder="Select Host" /></SelectTrigger>
                                <SelectContent>
                                    {hosts.map(h => <SelectItem key={h.id} value={h.id}>{h.hostname}</SelectItem>)}
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

            {/* Mark as IOC Dialog */}
            <Dialog open={showIocModal} onOpenChange={setShowIocModal}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Mark Event as IOC</DialogTitle>
                    </DialogHeader>
                    <DialogBody className="space-y-4">
                        {iocEvent && (
                            <div className="p-3 rounded-md bg-muted/50 text-sm">
                                <p className="font-medium truncate">{iocEvent.activity}</p>
                                <p className="text-xs text-muted-foreground mt-1">
                                    {formatDateTime(iocEvent.timestamp)}
                                    {iocEvent.hostname && ` · ${iocEvent.hostname}`}
                                </p>
                            </div>
                        )}
                        <div className="space-y-2">
                            <Label>Artifact Type</Label>
                            <Select value={iocForm.artifact_type} onValueChange={v => setIocForm({ ...iocForm, artifact_type: v })}>
                                <SelectTrigger variant="glass"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    {ARTIFACT_TYPES.map(t => (
                                        <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Notes (optional)</Label>
                            <Textarea
                                value={iocForm.notes}
                                onChange={e => setIocForm({ ...iocForm, notes: e.target.value })}
                                placeholder="Additional context about this indicator..."
                                variant="glass"
                            />
                        </div>
                        <div className="flex items-center gap-2">
                            <input
                                type="checkbox"
                                checked={iocForm.is_malicious}
                                onChange={e => setIocForm({ ...iocForm, is_malicious: e.target.checked })}
                                className="rounded bg-white/10 border-white/20"
                            />
                            <Label>Confirmed malicious</Label>
                        </div>
                    </DialogBody>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowIocModal(false)}>Cancel</Button>
                        <Button onClick={handleMarkAsIOC} disabled={iocSubmitting}>
                            {iocSubmitting && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                            Create IOC
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
