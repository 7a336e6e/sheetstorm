"use client"

import { useEffect, useState } from 'react'
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
import { Combobox } from '@/components/ui/combobox'
import { DataTable, FilterSelect, type DataTableColumn } from '@/components/ui/data-table'
import { usePaginatedQuery } from '@/hooks/use-paginated-query'
import api from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { notifyError } from '@/lib/errors'
import type { CompromisedHost, CustomFieldOption, VersionedRow } from '@/types'
import {
    Server,
    Monitor,
    Database,
    Shield,
    Wifi,
    Smartphone,
    HardDrive,
    Cloud,
    Pencil,
    Trash2,
} from 'lucide-react'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { DateTimeInput } from '@/components/ui/datetime-input'
import { Timestamp } from '@/components/ui/timestamp'
import { FocusNotice, type IncidentTabBaseProps } from './table-helpers'

type HostRow = VersionedRow<CompromisedHost>

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

export function HostsTab({ incidentId, focusRowId }: IncidentTabBaseProps) {
    const confirm = useConfirm()
    const endpoint = `/incidents/${incidentId}/hosts`
    const query = usePaginatedQuery<HostRow>({
        endpoint,
        urlKey: 'hosts',
        focus: focusRowId,
        live: 'host',
    })
    const [showModal, setShowModal] = useState(false)
    const [editingHost, setEditingHost] = useState<HostRow | null>(null)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [customTypes, setCustomTypes] = useState<CustomFieldOption[]>([])

    const [form, setForm] = useState({
        hostname: '',
        ip_address: '',
        system_type: 'workstation',
        os_version: '',
        containment_status: 'active',
        triage_status: 'under_analysis',
        first_seen: '',
        evidence: '',
    })

    // Org-defined system types are optional: the defaults work without them.
    useEffect(() => {
        let cancelled = false
        api.get<{ items: CustomFieldOption[] }>(`/custom-fields?field_name=system_type`)
            .then((res) => { if (!cancelled) setCustomTypes(res.items || []) })
            .catch(() => { /* optional data */ })
        return () => { cancelled = true }
    }, [])

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
            os_version: '', containment_status: 'active', triage_status: 'under_analysis',
            first_seen: '', evidence: '',
        })
        setEditingHost(null)
    }

    const handleOpenModal = (host?: HostRow) => {
        if (host) {
            setEditingHost(host)
            setForm({
                hostname: host.hostname,
                ip_address: host.ip_address || '',
                system_type: host.system_type || 'workstation',
                os_version: host.os_version || '',
                containment_status: host.containment_status || 'active',
                triage_status: host.triage_status || 'under_analysis',
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
                await api.put(`${endpoint}/${editingHost.id}`, form, { ifMatch: editingHost.version })
            } else {
                await api.post(endpoint, form)
            }
            setShowModal(false)
            resetForm()
            invalidate(endpoint)
        } catch (error) {
            notifyError(error, editingHost ? 'save the host' : 'add the host')
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleDelete = async (host: HostRow) => {
        if (!(await confirmDelete(confirm, 'host', host.hostname))) return
        try {
            await api.delete(`${endpoint}/${host.id}`, undefined, { ifMatch: host.version })
            invalidate(endpoint)
        } catch (error) {
            notifyError(error, 'delete the host')
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

    const columns: DataTableColumn<HostRow>[] = [
        { id: 'hostname', header: 'Hostname', sortKey: 'hostname', className: 'font-medium', cell: (h) => h.hostname },
        { id: 'ip', header: 'IP', className: 'font-mono text-sm', cell: (h) => h.ip_address || '-' },
        {
            id: 'type', header: 'Type', hideBelow: 'md', cell: (h) => (
                <div className="flex items-center gap-2">
                    <div className="p-1 rounded bg-white/5">{getSystemTypeIcon(h.system_type || '')}</div>
                    <span className="text-xs">{getSystemTypeLabel(h.system_type || '')}</span>
                </div>
            ),
        },
        { id: 'os', header: 'OS', hideBelow: 'lg', className: 'text-xs text-muted-foreground', cell: (h) => h.os_version || '-' },
        { id: 'containment', header: 'Containment', sortKey: 'containment_status', cell: (h) => getContainmentBadge(h.containment_status || 'active') },
        {
            id: 'first_seen', header: 'First Seen', sortKey: 'first_seen', hideBelow: 'sm', className: 'text-sm text-muted-foreground',
            cell: (h) => <Timestamp value={h.first_seen} fallback="-" />,
        },
    ]

    return (
        <div className="space-y-4">
            <FocusNotice focusRowId={focusRowId} focusFound={query.focusFound} noun="host" />
            <DataTable
                query={query}
                columns={columns}
                getRowId={(h) => h.id}
                ariaLabel="Compromised hosts"
                searchPlaceholder="Search hosts, IPs..."
                toolbar={
                    <FilterSelect
                        label="Containment"
                        value={query.state.filters.containment_status}
                        onChange={(v) => query.setFilter('containment_status', v)}
                        options={CONTAINMENT_STATUSES.map((c) => ({ value: c.value, label: c.label }))}
                    />
                }
                primaryAction={{ label: 'Add Host', onSelect: () => handleOpenModal(), permission: 'hosts:create' }}
                rowActions={(h) => [
                    { label: 'Edit', icon: Pencil, onSelect: () => handleOpenModal(h), permission: 'hosts:update' },
                    { label: 'Delete', icon: Trash2, destructive: true, onSelect: () => void handleDelete(h), permission: 'hosts:delete' },
                ]}
                focusedRowId={focusRowId}
                empty={{
                    title: 'No compromised hosts',
                    description: 'Record systems that have been identified as compromised during this incident investigation.',
                }}
            />

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
                                <Combobox
                                    options={allSystemTypes.map(t => ({
                                        value: t.value,
                                        label: t.label,
                                    }))}
                                    value={form.system_type}
                                    onChange={v => setForm({ ...form, system_type: v })}
                                    placeholder="Type or select system type..."
                                    allowCustom
                                    variant="glass"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>OS Version</Label>
                                <Input value={form.os_version} onChange={e => setForm({ ...form, os_version: e.target.value })} variant="glass" placeholder="Windows 11 23H2" />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label>Triage Status</Label>
                            <Select value={form.triage_status} onValueChange={v => setForm({ ...form, triage_status: v })}>
                                <SelectTrigger variant="glass"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="under_analysis">Under Analysis</SelectItem>
                                    <SelectItem value="suspicious">Suspicious</SelectItem>
                                    <SelectItem value="compromised">Compromised</SelectItem>
                                    <SelectItem value="clean">Clean</SelectItem>
                                </SelectContent>
                            </Select>
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
                                <DateTimeInput value={form.first_seen} onChange={iso => setForm({ ...form, first_seen: iso ?? '' })} variant="glass" />
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
