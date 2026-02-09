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
import {
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
} from '@/components/ui/tabs'
import { SkeletonTableRow } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/utils'
import api from '@/lib/api'
import type { HostBasedIndicator, CompromisedHost, TimelineEvent } from '@/types'
import {
    Plus,
    HardDrive,
    Search,
    CheckCircle2,
    FileCode,
    Settings,
    Clock,
    Cpu,
    FileText,
    Terminal,
    Boxes,
    Trash2,
    Calendar,
    AlertTriangle,
    Tag,
    MoreHorizontal
} from 'lucide-react'
import { useConfirm } from '@/components/ui/confirm-dialog'

interface HostBasedIOCsTabProps {
    incidentId: string
}

export function HostBasedIOCsTab({ incidentId }: HostBasedIOCsTabProps) {
    const confirm = useConfirm()
    const [indicators, setIndicators] = useState<HostBasedIndicator[]>([])
    const [timelineIOCs, setTimelineIOCs] = useState<TimelineEvent[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [typeFilter, setTypeFilter] = useState<string>('all')
    const [showModal, setShowModal] = useState(false)
    const [editingItem, setEditingItem] = useState<HostBasedIndicator | null>(null)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [activeTab, setActiveTab] = useState('all')
    const [hosts, setHosts] = useState<CompromisedHost[]>([])

    const [form, setForm] = useState({
        artifact_type: 'registry',
        artifact_value: '',
        datetime: '',
        host_id: '',
        host: '',
        timeline_event_id: '',
        notes: '',
        is_malicious: true,
        remediated: false,
    })

    useEffect(() => {
        if (incidentId) {
            loadData()
        }
    }, [incidentId])

    const loadData = async () => {
        setIsLoading(true)
        try {
            const [indicatorsRes, hostsRes, timelineRes] = await Promise.all([
                api.get<{ items: HostBasedIndicator[] }>(`/incidents/${incidentId}/host-iocs`),
                api.get<{ items: CompromisedHost[] }>(`/incidents/${incidentId}/hosts`),
                api.get<{ items: TimelineEvent[] }>(`/incidents/${incidentId}/timeline`),
            ])
            setIndicators(indicatorsRes.items || [])
            setHosts(hostsRes.items || [])
            setTimelineIOCs((timelineRes.items || []).filter((e) => e.is_ioc))
        } catch (error) {
            console.error('Failed to load host-based IOCs:', error)
        } finally {
            setIsLoading(false)
        }
    }

    const resetForm = () => {
        setForm({
            artifact_type: 'registry',
            artifact_value: '',
            datetime: '',
            host_id: '',
            host: '',
            timeline_event_id: '',
            notes: '',
            is_malicious: true,
            remediated: false,
        })
        setEditingItem(null)
    }

    const handleOpenModal = (item?: HostBasedIndicator) => {
        if (item) {
            setEditingItem(item)
            setForm({
                artifact_type: item.artifact_type,
                artifact_value: item.artifact_value,
                datetime: item.datetime || '',
                host_id: item.host_id || '',
                host: item.host || '',
                timeline_event_id: item.timeline_event_id || '',
                notes: item.notes || '',
                is_malicious: item.is_malicious,
                remediated: item.remediated,
            })
        } else {
            resetForm()
        }
        setShowModal(true)
    }

    const handleSubmit = async () => {
        if (!form.artifact_value) return
        setIsSubmitting(true)
        try {
            const payload = {
                artifact_type: form.artifact_type,
                artifact_value: form.artifact_value,
                datetime: form.datetime || null,
                host_id: form.host_id || null,
                host: form.host || null,
                timeline_event_id: form.timeline_event_id || null,
                notes: form.notes || null,
                is_malicious: form.is_malicious,
                remediated: form.remediated,
            }

            if (editingItem) {
                await api.put(`/incidents/${incidentId}/host-iocs/${editingItem.id}`, payload)
            } else {
                await api.post(`/incidents/${incidentId}/host-iocs`, payload)
            }

            setShowModal(false)
            resetForm()
            loadData()
        } catch (error) {
            console.error('Failed to save host-based IOC:', error)
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleDelete = async (id: string) => {
        const confirmed = await confirm({
            title: 'Delete IOC',
            description: 'Are you sure you want to delete this host-based indicator?',
            confirmLabel: 'Delete',
            variant: 'destructive',
        })
        if (!confirmed) return
        try {
            await api.delete(`/incidents/${incidentId}/host-iocs/${id}`)
            loadData()
        } catch (error) {
            console.error('Failed to delete:', error)
        }
    }

    const filteredIndicators = indicators.filter((indicator) => {
        const matchesSearch =
            indicator.artifact_value.toLowerCase().includes(search.toLowerCase()) ||
            indicator.notes?.toLowerCase().includes(search.toLowerCase())
        const matchesType = typeFilter === 'all' || indicator.artifact_type === typeFilter
        return matchesSearch && matchesType
    })

    const getArtifactTypeIcon = (type: string) => {
        switch (type) {
            case 'wmi_event': return <Boxes className="h-4 w-4" />
            case 'asep': return <Settings className="h-4 w-4" />
            case 'registry': return <FileCode className="h-4 w-4" />
            case 'scheduled_task': return <Clock className="h-4 w-4" />
            case 'service': return <Cpu className="h-4 w-4" />
            case 'file': return <FileText className="h-4 w-4" />
            case 'process': return <Terminal className="h-4 w-4" />
            default: return <HardDrive className="h-4 w-4" />
        }
    }

    return (
        <div className="space-y-4">
            <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList>
                    <TabsTrigger value="all" className="gap-2">
                        <HardDrive className="h-4 w-4" /> All IOCs
                        <Badge variant="outline" className="ml-1">{indicators.length}</Badge>
                    </TabsTrigger>
                    <TabsTrigger value="timeline" className="gap-2">
                        <Calendar className="h-4 w-4" /> From Timeline
                        <Badge variant="outline" className="ml-1">{timelineIOCs.length}</Badge>
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="all" className="space-y-4">
                    <Card>
                        <CardContent className="p-4">
                            <div className="flex justify-between items-center">
                                <div className="flex gap-4 items-center flex-1">
                                    <div className="relative w-64">
                                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                        <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search IOCs..." className="pl-10" variant="glass" />
                                    </div>
                                    <Select value={typeFilter} onValueChange={setTypeFilter}>
                                        <SelectTrigger className="w-40"><SelectValue placeholder="All Types" /></SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="all">All Types</SelectItem>
                                            <SelectItem value="registry">Registry</SelectItem>
                                            <SelectItem value="service">Service</SelectItem>
                                            <SelectItem value="scheduled_task">Task</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                                <Button onClick={() => handleOpenModal()}><Plus className="mr-2 h-4 w-4" /> Add IOC</Button>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardContent className="p-0">
                            <GlassTable className="border-0">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>Type</TableHead>
                                            <TableHead>Value</TableHead>
                                            <TableHead>Host</TableHead>
                                            <TableHead>Status</TableHead>
                                            <TableHead>Notes</TableHead>
                                            <TableHead className="w-[50px]"></TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {isLoading ? <SkeletonTableRow columns={6} /> : filteredIndicators.length === 0 ? (
                                            <TableRow><TableCell colSpan={6}><TableEmpty title="No Host IOCs" icon={<HardDrive className="w-10 h-10" />} /></TableCell></TableRow>
                                        ) : (
                                            filteredIndicators.map(item => (
                                                <TableRow key={item.id} className="group">
                                                    <TableCell>
                                                        <div className="flex items-center gap-2">
                                                            <div className="p-1 rounded bg-white/5">{getArtifactTypeIcon(item.artifact_type)}</div>
                                                            <span className="capitalize text-xs">{item.artifact_type}</span>
                                                        </div>
                                                    </TableCell>
                                                    <TableCell className="font-mono text-sm max-w-[300px] truncate" title={item.artifact_value}>{item.artifact_value}</TableCell>
                                                    <TableCell>{item.host_id ? hosts.find(h => h.id === item.host_id)?.hostname : '-'}</TableCell>
                                                    <TableCell>
                                                        <Badge variant={item.remediated ? 'default' : 'destructive'} className={item.remediated ? 'bg-green-500/20 text-green-400' : ''}>
                                                            {item.remediated ? 'Remediated' : 'Active'}
                                                        </Badge>
                                                    </TableCell>
                                                    <TableCell className="max-w-[200px] truncate text-muted-foreground text-xs">{item.notes}</TableCell>
                                                    <TableCell>
                                                        <div className="flex items-center gap-1">
                                                            <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100" onClick={() => handleOpenModal(item)}>
                                                                <MoreHorizontal className="w-4 h-4" />
                                                            </Button>
                                                            <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100 text-destructive" onClick={() => handleDelete(item.id)}>
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
                </TabsContent>

                <TabsContent value="timeline" className="space-y-4">
                    <Card>
                        <CardContent className="p-0">
                            <GlassTable className="border-0">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>Time</TableHead>
                                            <TableHead>Activity</TableHead>
                                            <TableHead>Indicator</TableHead>
                                            <TableHead>Host</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {timelineIOCs.map(event => (
                                            <TableRow key={event.id}>
                                                <TableCell>{formatDateTime(event.timestamp)}</TableCell>
                                                <TableCell>{event.activity}</TableCell>
                                                <TableCell><Badge variant="outline">Timeline Event</Badge></TableCell>
                                                <TableCell>{event.hostname || '-'}</TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </GlassTable>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>

            {/* Add Host IOC Modal */}
            <Dialog open={showModal} onOpenChange={setShowModal}>
                <DialogContent className="max-w-lg">
                    <DialogHeader><DialogTitle>{editingItem ? 'Edit' : 'Add'} Host-Based IOC</DialogTitle></DialogHeader>
                    <DialogBody className="space-y-4">
                        <div className="space-y-2">
                            <Label>Artifact Type</Label>
                            <Select value={form.artifact_type} onValueChange={v => setForm({ ...form, artifact_type: v })}>
                                <SelectTrigger variant="glass"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="registry">Registry</SelectItem>
                                    <SelectItem value="service">Service</SelectItem>
                                    <SelectItem value="process">Process</SelectItem>
                                    <SelectItem value="file">File</SelectItem>
                                    <SelectItem value="scheduled_task">Scheduled Task</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Value</Label>
                            <Textarea value={form.artifact_value} onChange={e => setForm({ ...form, artifact_value: e.target.value })} variant="glass" />
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
                        <div className="space-y-2">
                            <Label>Notes</Label>
                            <Textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} variant="glass" />
                        </div>
                        <div className="flex items-center gap-2">
                            <input type="checkbox" checked={form.remediated} onChange={e => setForm({ ...form, remediated: e.target.checked })} />
                            <Label>Remediated?</Label>
                        </div>
                    </DialogBody>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowModal(false)}>Cancel</Button>
                        <Button onClick={handleSubmit}>{editingItem ? 'Save Changes' : 'Add IOC'}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
