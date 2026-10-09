"use client"

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
import { useAllPages, usePaginatedQuery } from '@/hooks/use-paginated-query'
import api from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { notifyError } from '@/lib/errors'
import type { NetworkIndicator, CompromisedHost, VersionedRow } from '@/types'
import {
    Globe,
    ArrowUpRight,
    ArrowDownLeft,
    ArrowLeftRight,
    Pencil,
    Trash2,
} from 'lucide-react'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { DateTimeInput } from '@/components/ui/datetime-input'
import { FocusNotice, type IncidentTabBaseProps } from './table-helpers'

type IndicatorRow = VersionedRow<NetworkIndicator>

const PROTOCOLS = ['TCP', 'UDP', 'HTTP', 'HTTPS', 'DNS', 'ICMP', 'SMB', 'RDP', 'SSH']

const DIRECTIONS = [
    { value: 'outbound', label: 'Outbound' },
    { value: 'inbound', label: 'Inbound' },
    { value: 'lateral', label: 'Lateral' },
]

const EMPTY_FORM = {
    timestamp: '',
    protocol: '',
    port: '',
    dns_ip: '',
    source_host: '',
    destination_host: '',
    source_host_id: '',
    destination_host_id: '',
    direction: 'outbound',
    host_id: '',
    timeline_event_id: '',
    description: '',
    is_malicious: true,
    threat_intel_source: '',
    add_to_attack_graph: false,
}

const getDirectionIcon = (direction: string) => {
    switch (direction) {
        case 'inbound': return <ArrowDownLeft className="h-4 w-4 text-orange-400" />
        case 'outbound': return <ArrowUpRight className="h-4 w-4 text-red-400" />
        case 'lateral': return <ArrowLeftRight className="h-4 w-4 text-yellow-400" />
        default: return <Globe className="h-4 w-4" />
    }
}

export function NetworkIOCsTab({ incidentId, focusRowId }: IncidentTabBaseProps) {
    const confirm = useConfirm()
    const endpoint = `/incidents/${incidentId}/network-iocs`
    const query = usePaginatedQuery<IndicatorRow>({
        endpoint,
        urlKey: 'network',
        focus: focusRowId,
        live: 'network_ioc',
    })
    const [showModal, setShowModal] = useState(false)
    const [editingItem, setEditingItem] = useState<IndicatorRow | null>(null)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [form, setForm] = useState(EMPTY_FORM)

    // Source/destination host pickers: every host, loaded only while the modal is open.
    const hosts = useAllPages<CompromisedHost>(`/incidents/${incidentId}/hosts`, {
        live: 'host',
        enabled: showModal,
    }).items

    const resetForm = () => {
        setForm(EMPTY_FORM)
        setEditingItem(null)
    }

    const handleOpenModal = (item?: IndicatorRow) => {
        if (item) {
            setEditingItem(item)
            setForm({
                timestamp: item.timestamp || '',
                protocol: item.protocol || '',
                port: item.port ? String(item.port) : '',
                dns_ip: item.dns_ip,
                source_host: item.source_host || '',
                destination_host: item.destination_host || '',
                source_host_id: item.source_host_id || '',
                destination_host_id: item.destination_host_id || '',
                direction: item.direction || 'outbound',
                host_id: item.host_id || '',
                timeline_event_id: item.timeline_event_id || '',
                description: item.description || '',
                is_malicious: item.is_malicious,
                threat_intel_source: item.threat_intel_source || '',
                add_to_attack_graph: false,
            })
        } else {
            resetForm()
        }
        setShowModal(true)
    }

    const handleSubmit = async () => {
        if (!form.dns_ip) return
        setIsSubmitting(true)
        try {
            const payload: Record<string, unknown> = {
                timestamp: form.timestamp || null,
                protocol: form.protocol || null,
                port: form.port ? parseInt(form.port, 10) : null,
                dns_ip: form.dns_ip,
                source_host: form.source_host || null,
                destination_host: form.destination_host || null,
                source_host_id: form.source_host_id || null,
                destination_host_id: form.destination_host_id || null,
                direction: form.direction,
                host_id: form.host_id || null,
                timeline_event_id: form.timeline_event_id || null,
                description: form.description || null,
                is_malicious: form.is_malicious,
                threat_intel_source: form.threat_intel_source || null,
            }

            if (!editingItem && form.add_to_attack_graph) {
                payload.add_to_attack_graph = true
            }

            if (editingItem) {
                await api.put(`${endpoint}/${editingItem.id}`, payload, { ifMatch: editingItem.version })
            } else {
                await api.post(endpoint, payload)
            }

            setShowModal(false)
            resetForm()
            invalidate(endpoint)
            if (!editingItem && payload.add_to_attack_graph) invalidate(`/incidents/${incidentId}/attack-graph`)
        } catch (error) {
            notifyError(error, editingItem ? 'save the network IOC' : 'add the network IOC')
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleDelete = async (item: IndicatorRow) => {
        if (!(await confirmDelete(confirm, 'network IOC', item.dns_ip))) return
        try {
            await api.delete(`${endpoint}/${item.id}`, undefined, { ifMatch: item.version })
            invalidate(endpoint)
        } catch (error) {
            notifyError(error, 'delete the network IOC')
        }
    }

    const hostLabel = (ref: CompromisedHost | undefined, text: string | undefined) => ref?.hostname || text || '-'

    const columns: DataTableColumn<IndicatorRow>[] = [
        {
            id: 'direction', header: 'Direction', sortKey: 'direction', cell: (item) => (
                <div className="flex items-center gap-2">
                    <div className="p-1 rounded bg-white/5">{getDirectionIcon(item.direction || '')}</div>
                    <span className="capitalize text-xs">{item.direction}</span>
                </div>
            ),
        },
        { id: 'dns_ip', header: 'Value (IP/DNS)', sortKey: 'dns_ip', className: 'font-mono text-sm', cell: (item) => item.dns_ip },
        {
            id: 'protocol', header: 'Protocol/Port', sortKey: 'protocol', hideBelow: 'sm',
            cell: (item) => `${item.protocol ?? ''}${item.port ? ` :${item.port}` : ''}` || '-',
        },
        {
            id: 'source', header: 'Source Host', hideBelow: 'md', className: 'text-sm text-muted-foreground',
            cell: (item) => hostLabel(item.source_host_ref, item.source_host),
        },
        {
            id: 'destination', header: 'Dest Host', hideBelow: 'md', className: 'text-sm text-muted-foreground',
            cell: (item) => hostLabel(item.destination_host_ref, item.destination_host),
        },
        {
            id: 'description', header: 'Description', hideBelow: 'lg', className: 'text-sm text-muted-foreground',
            cell: (item) => item.description || '-',
        },
    ]

    return (
        <div className="space-y-4">
            <FocusNotice focusRowId={focusRowId} focusFound={query.focusFound} noun="network IOC" />
            <DataTable
                query={query}
                columns={columns}
                getRowId={(i) => i.id}
                ariaLabel="Network IOCs"
                searchPlaceholder="Search IPs, domains..."
                toolbar={
                    <>
                        <FilterSelect
                            label="Direction"
                            allLabel="All directions"
                            value={query.state.filters.direction}
                            onChange={(v) => query.setFilter('direction', v)}
                            options={DIRECTIONS}
                        />
                        <FilterSelect
                            label="Protocol"
                            allLabel="All protocols"
                            value={query.state.filters.protocol}
                            onChange={(v) => query.setFilter('protocol', v)}
                            options={PROTOCOLS.map((p) => ({ value: p, label: p }))}
                        />
                    </>
                }
                primaryAction={{ label: 'Add IOC', onSelect: () => handleOpenModal(), permission: 'network_iocs:create' }}
                rowActions={(i) => [
                    { label: 'Edit', icon: Pencil, onSelect: () => handleOpenModal(i), permission: 'network_iocs:update' },
                    { label: 'Delete', icon: Trash2, destructive: true, onSelect: () => void handleDelete(i), permission: 'network_iocs:delete' },
                ]}
                focusedRowId={focusRowId}
                empty={{
                    title: 'No network IOCs',
                    description: 'Track IP addresses, domains, and URLs associated with malicious network activity.',
                }}
            />

            <Dialog open={showModal} onOpenChange={setShowModal}>
                <DialogContent className="max-w-xl">
                    <DialogHeader><DialogTitle>{editingItem ? 'Edit' : 'Add'} Network Indicator</DialogTitle></DialogHeader>
                    <DialogBody className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Timestamp</Label>
                                <DateTimeInput value={form.timestamp} onChange={iso => setForm({ ...form, timestamp: iso ?? '' })} variant="glass" />
                            </div>
                            <div className="space-y-2">
                                <Label>Direction</Label>
                                <Select value={form.direction} onValueChange={v => setForm({ ...form, direction: v })}>
                                    <SelectTrigger variant="glass"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="outbound">Outbound (C2/Exfil)</SelectItem>
                                        <SelectItem value="inbound">Inbound (Exploit)</SelectItem>
                                        <SelectItem value="lateral">Lateral Movement</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label>IP Address / Domain *</Label>
                            <Input value={form.dns_ip} onChange={e => setForm({ ...form, dns_ip: e.target.value })} placeholder="1.2.3.4 or example.com" variant="glass" />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Protocol</Label>
                                <Select value={form.protocol} onValueChange={v => setForm({ ...form, protocol: v })}>
                                    <SelectTrigger variant="glass"><SelectValue placeholder="Select Protocol" /></SelectTrigger>
                                    <SelectContent>
                                        {PROTOCOLS.map((p) => (
                                            <SelectItem key={p} value={p}>{p}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label>Port</Label>
                                <Input type="number" value={form.port} onChange={e => setForm({ ...form, port: e.target.value })} placeholder="443" variant="glass" />
                            </div>
                        </div>

                        {/* Source / Destination Host Selection */}
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Source Host</Label>
                                <Combobox
                                    options={hosts.map(h => ({
                                        value: h.id,
                                        label: h.hostname + (h.ip_address ? ` (${h.ip_address})` : ''),
                                        description: h.ip_address || undefined,
                                    }))}
                                    value={form.source_host_id}
                                    onChange={v => {
                                        const host = hosts.find(h => h.id === v)
                                        setForm({
                                            ...form,
                                            source_host_id: host ? v : '',
                                            source_host: host ? '' : v,
                                        })
                                    }}
                                    placeholder="Type IP/hostname or select..."
                                    allowCustom
                                    variant="glass"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Destination Host</Label>
                                <Combobox
                                    options={hosts.map(h => ({
                                        value: h.id,
                                        label: h.hostname + (h.ip_address ? ` (${h.ip_address})` : ''),
                                        description: h.ip_address || undefined,
                                    }))}
                                    value={form.destination_host_id}
                                    onChange={v => {
                                        const host = hosts.find(h => h.id === v)
                                        setForm({
                                            ...form,
                                            destination_host_id: host ? v : '',
                                            destination_host: host ? '' : v,
                                        })
                                    }}
                                    placeholder="Type IP/hostname or select..."
                                    allowCustom
                                    variant="glass"
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label>Description</Label>
                            <Textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} variant="glass" />
                        </div>

                        {/* Attack Graph Integration */}
                        {!editingItem && (
                            <div className="flex items-center gap-2 p-3 rounded-md border border-white/10 bg-white/[0.02]">
                                <input
                                    type="checkbox"
                                    checked={form.add_to_attack_graph}
                                    onChange={e => setForm({ ...form, add_to_attack_graph: e.target.checked })}
                                    className="rounded bg-white/10 border-white/20"
                                />
                                <div>
                                    <Label className="cursor-pointer">Add to Attack Graph</Label>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        Automatically create an attack graph node for this network indicator
                                    </p>
                                </div>
                            </div>
                        )}
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
