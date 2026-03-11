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
import type { HostBasedIndicator, CompromisedHost, CustomFieldOption } from '@/types'
import {
    Plus,
    HardDrive,
    Search,
    FileCode,
    Settings,
    Clock,
    Cpu,
    FileText,
    Terminal,
    Boxes,
    Trash2,
    MoreHorizontal,
    Key,
    Database,
    Wifi,
    Shield,
    User,
    Folder,
    Bug,
} from 'lucide-react'
import { useConfirm } from '@/components/ui/confirm-dialog'

interface HostBasedIOCsTabProps {
    incidentId: string
}

const DEFAULT_ARTIFACT_TYPES = [
    { value: 'registry', label: 'Registry Key', icon: FileCode },
    { value: 'service', label: 'Service', icon: Cpu },
    { value: 'process', label: 'Process', icon: Terminal },
    { value: 'file', label: 'File', icon: FileText },
    { value: 'scheduled_task', label: 'Scheduled Task', icon: Clock },
    { value: 'wmi_event', label: 'WMI Event', icon: Boxes },
    { value: 'asep', label: 'ASEP', icon: Settings },
    { value: 'user_account', label: 'User Account', icon: User },
    { value: 'log_entry', label: 'Log Entry', icon: Database },
    { value: 'network_connection', label: 'Network Connection', icon: Wifi },
    { value: 'dns_record', label: 'DNS Record', icon: Wifi },
    { value: 'certificate', label: 'Certificate', icon: Key },
    { value: 'browser_artifact', label: 'Browser Artifact', icon: Folder },
    { value: 'memory_artifact', label: 'Memory Artifact', icon: Bug },
    { value: 'email_artifact', label: 'Email Artifact', icon: FileText },
    { value: 'persistence_mechanism', label: 'Persistence Mechanism', icon: Shield },
    { value: 'other', label: 'Other', icon: HardDrive },
]

export function HostBasedIOCsTab({ incidentId }: HostBasedIOCsTabProps) {
    const confirm = useConfirm()
    const [indicators, setIndicators] = useState<HostBasedIndicator[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [typeFilter, setTypeFilter] = useState<string>('all')
    const [showModal, setShowModal] = useState(false)
    const [editingItem, setEditingItem] = useState<HostBasedIndicator | null>(null)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [hosts, setHosts] = useState<CompromisedHost[]>([])
    const [customTypes, setCustomTypes] = useState<CustomFieldOption[]>([])

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
        if (incidentId) loadData()
    }, [incidentId])

    const loadData = async () => {
        setIsLoading(true)
        try {
            const [indicatorsRes, hostsRes, typesRes] = await Promise.all([
                api.get<{ items: HostBasedIndicator[] }>(`/incidents/${incidentId}/host-iocs`),
                api.get<{ items: CompromisedHost[] }>(`/incidents/${incidentId}/hosts`),
                api.get<{ items: CustomFieldOption[] }>(`/custom-fields?field_name=artifact_type`).catch(() => ({ items: [] })),
            ])
            setIndicators(indicatorsRes.items || [])
            setHosts(hostsRes.items || [])
            setCustomTypes(typesRes.items || [])
        } catch (error) {
            console.error('Failed to load host-based IOCs:', error)
        } finally {
            setIsLoading(false)
        }
    }

    // Merge default types with custom org-specific types
    const allArtifactTypes = [
        ...DEFAULT_ARTIFACT_TYPES,
        ...customTypes
            .filter(ct => !DEFAULT_ARTIFACT_TYPES.some(d => d.value === ct.field_value))
            .map(ct => ({ value: ct.field_value, label: ct.display_label || ct.field_value, icon: HardDrive })),
    ]

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
        const found = allArtifactTypes.find(t => t.value === type)
        if (found) {
            const Icon = found.icon
            return <Icon className="h-4 w-4" />
        }
        return <HardDrive className="h-4 w-4" />
    }

    const getArtifactTypeLabel = (type: string) => {
        return allArtifactTypes.find(t => t.value === type)?.label || type
    }

    // Unique types present in data for filter dropdown
    const typesInData = Array.from(new Set(indicators.map(i => i.artifact_type)))

    return (
        <div className="space-y-4">
            <Card>
                <CardContent className="p-4">
                    <div className="flex justify-between items-center">
                        <div className="flex gap-4 items-center flex-1">
                            <div className="relative flex-1">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search IOCs..." className="pl-10" variant="glass" />
                            </div>
                            <Select value={typeFilter} onValueChange={setTypeFilter}>
                                <SelectTrigger className="w-48"><SelectValue placeholder="All Types" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">All Types</SelectItem>
                                    {typesInData.map(type => (
                                        <SelectItem key={type} value={type}>{getArtifactTypeLabel(type)}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <Button onClick={() => handleOpenModal()} className="ml-4"><Plus className="mr-2 h-4 w-4" /> Add IOC</Button>
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
                                    <TableRow><TableCell colSpan={6}>
                                        <TableEmpty
                                            title={search || typeFilter !== 'all' ? 'No matching host IOCs' : 'No host-based IOCs'}
                                            description={search || typeFilter !== 'all' ? 'Try adjusting your search or filter criteria' : 'Document file artifacts, registry keys, processes, and other host-based indicators of compromise.'}
                                            icon={<HardDrive className="w-8 h-8" />}
                                        />
                                    </TableCell></TableRow>
                                ) : (
                                    filteredIndicators.map(item => (
                                        <TableRow key={item.id} className="group">
                                            <TableCell>
                                                <div className="flex items-center gap-2">
                                                    <div className="p-1 rounded bg-white/5">{getArtifactTypeIcon(item.artifact_type)}</div>
                                                    <span className="text-xs">{getArtifactTypeLabel(item.artifact_type)}</span>
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

            {/* Add/Edit Host IOC Modal */}
            <Dialog open={showModal} onOpenChange={setShowModal}>
                <DialogContent className="max-w-lg">
                    <DialogHeader><DialogTitle>{editingItem ? 'Edit' : 'Add'} Host-Based IOC</DialogTitle></DialogHeader>
                    <DialogBody className="space-y-4">
                        <div className="space-y-2">
                            <Label>Artifact Type</Label>
                            <Select value={form.artifact_type} onValueChange={v => setForm({ ...form, artifact_type: v })}>
                                <SelectTrigger variant="glass"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    {allArtifactTypes.map(t => (
                                        <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Value *</Label>
                            <Textarea value={form.artifact_value} onChange={e => setForm({ ...form, artifact_value: e.target.value })} variant="glass" placeholder="Enter the artifact value (file path, registry key, process name, etc.)" />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
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
                                <Label>Date/Time Observed</Label>
                                <Input type="datetime-local" value={form.datetime} onChange={e => setForm({ ...form, datetime: e.target.value })} variant="glass" />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label>Notes</Label>
                            <Textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} variant="glass" placeholder="Additional context about this indicator..." />
                        </div>
                        <div className="flex items-center gap-6">
                            <div className="flex items-center gap-2">
                                <input type="checkbox" checked={form.is_malicious} onChange={e => setForm({ ...form, is_malicious: e.target.checked })} className="rounded bg-white/10 border-white/20" />
                                <Label>Confirmed malicious</Label>
                            </div>
                            <div className="flex items-center gap-2">
                                <input type="checkbox" checked={form.remediated} onChange={e => setForm({ ...form, remediated: e.target.checked })} className="rounded bg-white/10 border-white/20" />
                                <Label>Remediated</Label>
                            </div>
                        </div>
                    </DialogBody>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowModal(false)}>Cancel</Button>
                        <Button onClick={handleSubmit} loading={isSubmitting}>{editingItem ? 'Save Changes' : 'Add IOC'}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
