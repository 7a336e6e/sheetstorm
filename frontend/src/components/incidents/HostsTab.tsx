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
import { formatDateTime } from '@/lib/utils'
import api from '@/lib/api'
import type { CompromisedHost, CustomFieldOption } from '@/types'
import {
    Plus,
    Search,
    Server,
    Monitor,
    Database,
    Shield,
    Wifi,
    Smartphone,
    HardDrive,
    Cloud,
    Trash2,
    MoreHorizontal,
} from 'lucide-react'
import { useConfirm } from '@/components/ui/confirm-dialog'

interface HostsTabProps {
    incidentId: string
    /** Called when hosts list changes, so parent can sync state */
    onHostsChange?: (hosts: CompromisedHost[]) => void
}

const DEFAULT_SYSTEM_TYPES = [
    { value: 'workstation', label: 'Workstation', icon: Monitor },
    { value: 'server', label: 'Server', icon: Server },
    { value: 'domain_controller', label: 'Domain Controller', icon: Shield },
    { value: 'database_server', label: 'Database Server', icon: Database },
    { value: 'web_server', label: 'Web Server', icon: Cloud },
    { value: 'file_server', label: 'File Server', icon: HardDrive },
    { value: 'mail_server', label: 'Mail Server', icon: Server },
    { value: 'dns_server', label: 'DNS Server', icon: Wifi },
    { value: 'firewall', label: 'Firewall', icon: Shield },
    { value: 'router', label: 'Router / Switch', icon: Wifi },
    { value: 'laptop', label: 'Laptop', icon: Monitor },
    { value: 'mobile_device', label: 'Mobile Device', icon: Smartphone },
    { value: 'virtual_machine', label: 'Virtual Machine', icon: Cloud },
    { value: 'container', label: 'Container', icon: HardDrive },
    { value: 'iot_device', label: 'IoT Device', icon: Wifi },
    { value: 'cloud_instance', label: 'Cloud Instance', icon: Cloud },
    { value: 'other', label: 'Other', icon: HardDrive },
]

const CONTAINMENT_STATUSES = [
    { value: 'active', label: 'Active', color: 'bg-red-500/20 text-red-400 border-red-400/30' },
    { value: 'monitoring', label: 'Monitoring', color: 'bg-amber-500/20 text-amber-400 border-amber-400/30' },
    { value: 'isolated', label: 'Isolated', color: 'bg-blue-500/20 text-blue-400 border-blue-400/30' },
    { value: 'reimaged', label: 'Reimaged', color: 'bg-green-500/20 text-green-400 border-green-400/30' },
    { value: 'decommissioned', label: 'Decommissioned', color: 'bg-gray-500/20 text-gray-400 border-gray-400/30' },
]

export function HostsTab({ incidentId, onHostsChange }: HostsTabProps) {
    const confirm = useConfirm()
    const [hosts, setHosts] = useState<CompromisedHost[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [showModal, setShowModal] = useState(false)
    const [editingHost, setEditingHost] = useState<CompromisedHost | null>(null)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [customTypes, setCustomTypes] = useState<CustomFieldOption[]>([])

    const [form, setForm] = useState({
        hostname: '',
        ip_address: '',
        system_type: 'workstation',
        os_version: '',
        containment_status: 'active',
        first_seen: '',
        evidence: '',
    })

    useEffect(() => {
        if (incidentId) loadData()
    }, [incidentId])

    const loadData = async () => {
        setIsLoading(true)
        try {
            const [hostsRes, typesRes] = await Promise.all([
                api.get<{ items: CompromisedHost[] }>(`/incidents/${incidentId}/hosts`),
                api.get<{ items: CustomFieldOption[] }>(`/custom-fields?field_name=system_type`).catch(() => ({ items: [] })),
            ])
            const h = hostsRes.items || []
            setHosts(h)
            setCustomTypes(typesRes.items || [])
            onHostsChange?.(h)
        } catch (error) {
            console.error('Failed to load hosts:', error)
        } finally {
            setIsLoading(false)
        }
    }

    // Merge default system types with custom org types
    const allSystemTypes = [
        ...DEFAULT_SYSTEM_TYPES,
        ...customTypes
            .filter(ct => !DEFAULT_SYSTEM_TYPES.some(d => d.value === ct.field_value))
            .map(ct => ({ value: ct.field_value, label: ct.display_label || ct.field_value, icon: HardDrive })),
    ]

    const resetForm = () => {
        setForm({
            hostname: '', ip_address: '', system_type: 'workstation',
            os_version: '', containment_status: 'active', first_seen: '', evidence: '',
        })
        setEditingHost(null)
    }

    const handleOpenModal = (host?: CompromisedHost) => {
        if (host) {
            setEditingHost(host)
            setForm({
                hostname: host.hostname,
                ip_address: host.ip_address || '',
                system_type: host.system_type || 'workstation',
                os_version: host.os_version || '',
                containment_status: host.containment_status || 'active',
                first_seen: host.first_seen || '',
                evidence: host.evidence || '',
            })
        } else {
            resetForm()
        }
        setShowModal(true)
    }

    const handleSubmit = async () => {
        if (!form.hostname) return
        setIsSubmitting(true)
        try {
            if (editingHost) {
                await api.put(`/incidents/${incidentId}/hosts/${editingHost.id}`, form)
            } else {
                await api.post(`/incidents/${incidentId}/hosts`, form)
            }
            setShowModal(false)
            resetForm()
            loadData()
        } catch (error) {
            console.error('Failed to save host:', error)
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleDelete = async (id: string) => {
        const confirmed = await confirm({
            title: 'Delete Host',
            description: 'Are you sure you want to delete this compromised host? Related IOCs will lose their host association.',
            confirmLabel: 'Delete',
            variant: 'destructive',
        })
        if (!confirmed) return
        try {
            await api.delete(`/incidents/${incidentId}/hosts/${id}`)
            loadData()
        } catch (error) {
            console.error('Failed to delete host:', error)
        }
    }

    const getContainmentBadge = (status: string) => {
        const s = CONTAINMENT_STATUSES.find(c => c.value === status) || CONTAINMENT_STATUSES[0]
        return <Badge variant="outline" className={s.color}>{s.label}</Badge>
    }

    const getSystemTypeLabel = (type: string) => {
        return allSystemTypes.find(t => t.value === type)?.label || type
    }

    const getSystemTypeIcon = (type: string) => {
        const found = allSystemTypes.find(t => t.value === type)
        if (found) {
            const Icon = found.icon
            return <Icon className="h-4 w-4" />
        }
        return <HardDrive className="h-4 w-4" />
    }

    const filtered = hosts.filter(h =>
        !search ||
        h.hostname?.toLowerCase().includes(search.toLowerCase()) ||
        h.ip_address?.toLowerCase().includes(search.toLowerCase()) ||
        h.system_type?.toLowerCase().includes(search.toLowerCase())
    )

    return (
        <div className="space-y-4">
            <Card>
                <CardContent className="p-4">
                    <div className="flex flex-col lg:flex-row gap-4 justify-between">
                        <div className="relative flex-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input placeholder="Search hosts, IPs..." value={search} onChange={e => setSearch(e.target.value)} className="pl-10" variant="glass" />
                        </div>
                        <Button onClick={() => handleOpenModal()}><Plus className="mr-2 h-4 w-4" /> Add Host</Button>
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardContent className="p-0">
                    <GlassTable className="border-0">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Hostname</TableHead>
                                    <TableHead>IP</TableHead>
                                    <TableHead>Type</TableHead>
                                    <TableHead>OS</TableHead>
                                    <TableHead>Containment</TableHead>
                                    <TableHead>First Seen</TableHead>
                                    <TableHead className="w-[80px]"></TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {isLoading ? (
                                    <TableRow><TableCell colSpan={7} className="text-center py-6 text-muted-foreground animate-pulse">Loading hosts...</TableCell></TableRow>
                                ) : filtered.length === 0 ? (
                                    <TableRow><TableCell colSpan={7}>
                                        <TableEmpty
                                            title={search ? 'No matching hosts' : 'No compromised hosts'}
                                            description={search ? 'Try adjusting your search criteria.' : 'Record systems that have been identified as compromised during this incident investigation.'}
                                            icon={<Server className="w-8 h-8" />}
                                        />
                                    </TableCell></TableRow>
                                ) : (
                                    filtered.map(host => (
                                        <TableRow key={host.id} className="group">
                                            <TableCell className="font-medium">{host.hostname}</TableCell>
                                            <TableCell className="font-mono text-sm">{host.ip_address || '-'}</TableCell>
                                            <TableCell>
                                                <div className="flex items-center gap-2">
                                                    <div className="p-1 rounded bg-white/5">{getSystemTypeIcon(host.system_type || '')}</div>
                                                    <span className="text-xs">{getSystemTypeLabel(host.system_type || '')}</span>
                                                </div>
                                            </TableCell>
                                            <TableCell className="text-xs text-muted-foreground">{host.os_version || '-'}</TableCell>
                                            <TableCell>{getContainmentBadge(host.containment_status || 'active')}</TableCell>
                                            <TableCell className="text-sm text-muted-foreground">{host.first_seen ? formatDateTime(host.first_seen) : '-'}</TableCell>
                                            <TableCell>
                                                <div className="flex items-center gap-1">
                                                    <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100" onClick={() => handleOpenModal(host)}>
                                                        <MoreHorizontal className="w-4 h-4" />
                                                    </Button>
                                                    <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100 text-destructive" onClick={() => handleDelete(host.id)}>
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

            {/* Add/Edit Host Modal */}
            <Dialog open={showModal} onOpenChange={setShowModal}>
                <DialogContent className="max-w-lg">
                    <DialogHeader><DialogTitle>{editingHost ? 'Edit' : 'Add'} Compromised Host</DialogTitle></DialogHeader>
                    <DialogBody className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Hostname *</Label>
                                <Input value={form.hostname} onChange={e => setForm({ ...form, hostname: e.target.value })} variant="glass" placeholder="e.g. WS-FINANCE-01" />
                            </div>
                            <div className="space-y-2">
                                <Label>IP Address</Label>
                                <Input value={form.ip_address} onChange={e => setForm({ ...form, ip_address: e.target.value })} variant="glass" placeholder="192.168.1.100" />
                            </div>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>System Type</Label>
                                <Select value={form.system_type} onValueChange={v => setForm({ ...form, system_type: v })}>
                                    <SelectTrigger variant="glass"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {allSystemTypes.map(t => (
                                            <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label>OS Version</Label>
                                <Input value={form.os_version} onChange={e => setForm({ ...form, os_version: e.target.value })} variant="glass" placeholder="Windows 11 23H2" />
                            </div>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Containment Status</Label>
                                <Select value={form.containment_status} onValueChange={v => setForm({ ...form, containment_status: v })}>
                                    <SelectTrigger variant="glass"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {CONTAINMENT_STATUSES.map(s => (
                                            <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label>First Seen</Label>
                                <Input type="datetime-local" value={form.first_seen} onChange={e => setForm({ ...form, first_seen: e.target.value })} variant="glass" />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label>Evidence / Notes</Label>
                            <Textarea value={form.evidence} onChange={e => setForm({ ...form, evidence: e.target.value })} variant="glass" placeholder="Evidence, indicators, or notes about this host..." />
                        </div>
                    </DialogBody>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowModal(false)}>Cancel</Button>
                        <Button onClick={handleSubmit} loading={isSubmitting}>{editingHost ? 'Save Changes' : 'Add Host'}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
