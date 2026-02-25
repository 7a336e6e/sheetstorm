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
    DialogDescription,
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
import { SkeletonTableRow } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/utils'
import api from '@/lib/api'
import type { TimelineEvent, CompromisedHost } from '@/types'
import {
    Plus,
    Clock,
    Search,
    Filter,
    MoreHorizontal,
    Trash2,
    AlertTriangle,
    Server,
    Tag,
    Edit2,
    ShieldAlert,
    Loader2,
} from 'lucide-react'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { useToast } from '@/components/ui/use-toast'

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

    // Mark as IOC dialog state
    const [showIocModal, setShowIocModal] = useState(false)
    const [iocEvent, setIocEvent] = useState<TimelineEvent | null>(null)
    const [iocForm, setIocForm] = useState({ artifact_type: 'other', notes: '', is_malicious: true })
    const [iocSubmitting, setIocSubmitting] = useState(false)

    const [form, setForm] = useState({
        timestamp: '',
        activity: '',
        host_id: '',
        mitre_tactic: '',
        mitre_technique: '',
        is_ioc: false,
    })

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
                    host_id: form.host_id || null,
                    mitre_tactic: form.mitre_tactic || null,
                    mitre_technique: form.mitre_technique || null,
                    is_ioc: form.is_ioc,
                })
            } else {
                await api.post(`/incidents/${incidentId}/timeline`, {
                    timestamp: form.timestamp,
                    activity: form.activity,
                    host_id: form.host_id || null,
                    mitre_tactic: form.mitre_tactic || null,
                    mitre_technique: form.mitre_technique || null,
                    is_ioc: form.is_ioc,
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
            host_id: event.host?.id || '',
            mitre_tactic: event.mitre_tactic || '',
            mitre_technique: event.mitre_technique || '',
            is_ioc: event.is_ioc || false
        })
        setShowAddModal(true)
    }

    const handleToggleIOC = async (event: TimelineEvent, checked: boolean) => {
        // Optimistic update
        const updatedEvents = events.map(e => e.id === event.id ? { ...e, is_ioc: checked } : e)
        setEvents(updatedEvents)

        try {
            await api.put(`/incidents/${incidentId}/timeline/${event.id}`, {
                ...event,
                host_id: event.host?.id, // Ensure host_id is preserved/passed correctly if needed by backend
                is_ioc: checked
            })
        } catch (error) {
            console.error("Failed to update IOC status", error)
            loadData() // Revert on error
        }
    }

    const handleOpenMarkAsIOC = (event: TimelineEvent) => {
        setIocEvent(event)
        setIocForm({ artifact_type: 'other', notes: '', is_malicious: true })
        setShowIocModal(true)
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
            toast({ title: 'IOC Created', description: `Event marked as IOC and host-based indicator created.` })
            setShowIocModal(false)
            setIocEvent(null)
            loadData()
        } catch (error: any) {
            toast({ title: 'Error', description: error?.message || 'Failed to mark as IOC', variant: 'destructive' })
        } finally {
            setIocSubmitting(false)
        }
    }

    const resetForm = () => {
        setForm({
            timestamp: '',
            activity: '',
            host_id: '',
            mitre_tactic: '',
            mitre_technique: '',
            is_ioc: false,
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
                    <div className="flex justify-between items-center">
                        <div className="relative w-72">
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
                                    <TableHead>Time</TableHead>
                                    <TableHead>Host</TableHead>
                                    <TableHead>Activity</TableHead>
                                    <TableHead>MITRE Tactic / Technique</TableHead>
                                    <TableHead>IOC?</TableHead>
                                    <TableHead className="w-[80px]"></TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {isLoading ? <SkeletonTableRow columns={6} /> : filteredEvents.length === 0 ? (
                                    <TableRow><TableCell colSpan={6}><TableEmpty title="No events" icon={<Clock className="w-10 h-10" />} /></TableCell></TableRow>
                                ) : (
                                    filteredEvents.map(event => (
                                        <TableRow key={event.id} className="group">
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
                                                <div className="flex items-center gap-2">
                                                    <input
                                                        type="checkbox"
                                                        checked={event.is_ioc}
                                                        onChange={(e) => handleToggleIOC(event, e.target.checked)}
                                                        className="rounded bg-white/10 border-white/20"
                                                    />
                                                    {event.is_ioc && <Tag className="h-3 w-3 text-red-400" />}
                                                </div>
                                            </TableCell>
                                            <TableCell>
                                                <div className="flex items-center gap-1">
                                                    <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100" onClick={() => handleEditClick(event)} title="Edit event">
                                                        <Edit2 className="w-4 h-4" />
                                                    </Button>
                                                    {!event.is_ioc && (
                                                        <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100 text-amber-500 hover:text-amber-400" onClick={() => handleOpenMarkAsIOC(event)} title="Mark as IOC & create indicator">
                                                            <ShieldAlert className="w-4 h-4" />
                                                        </Button>
                                                    )}
                                                    <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100 text-destructive" onClick={() => handleDelete(event.id)} title="Delete event">
                                                        <Trash2 className="w-4 h-4" />
                                                    </Button>
                                                </div>
                                            </TableCell>
                                        </TableRow>
                                    ))
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
                        <div className="flex items-center gap-2">
                            <input type="checkbox" checked={form.is_ioc} onChange={e => setForm({ ...form, is_ioc: e.target.checked })} className="rounded bg-white/10 border-white/20" />
                            <Label>Mark as IOC</Label>
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
                        <DialogDescription>
                            This will flag the event as an IOC and create a host-based indicator record.
                        </DialogDescription>
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
