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
import { Combobox, type ComboboxOption } from '@/components/ui/combobox'
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
import type { NetworkIndicator, CompromisedHost } from '@/types'
import {
    Plus,
    Globe,
    Search,
    ArrowUpRight,
    ArrowDownLeft,
    ArrowLeftRight,
    Trash2,
    Network,
    MoreHorizontal
} from 'lucide-react'
import { useConfirm } from '@/components/ui/confirm-dialog'

interface NetworkIOCsTabProps {
    incidentId: string
}

export function NetworkIOCsTab({ incidentId }: NetworkIOCsTabProps) {
    const confirm = useConfirm()
    const [indicators, setIndicators] = useState<NetworkIndicator[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [showModal, setShowModal] = useState(false)
    const [editingItem, setEditingItem] = useState<NetworkIndicator | null>(null)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [hosts, setHosts] = useState<CompromisedHost[]>([])

    const [form, setForm] = useState({
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
    })

    useEffect(() => {
        if (incidentId) {
            loadData()
        }
    }, [incidentId])

    const loadData = async () => {
        setIsLoading(true)
        try {
            const [indicatorsRes, hostsRes] = await Promise.all([
                api.get<{ items: NetworkIndicator[] }>(`/incidents/${incidentId}/network-iocs`),
                api.get<{ items: CompromisedHost[] }>(`/incidents/${incidentId}/hosts`),
            ])
            setIndicators(indicatorsRes.items || [])
            setHosts(hostsRes.items || [])
        } catch (error) {
            console.error('Failed to load network IOCs:', error)
        } finally {
            setIsLoading(false)
        }
    }

    const resetForm = () => {
        setForm({
            timestamp: '', protocol: '', port: '', dns_ip: '', source_host: '', destination_host: '',
            source_host_id: '', destination_host_id: '',
            direction: 'outbound', host_id: '', timeline_event_id: '', description: '', is_malicious: true, threat_intel_source: '',
            add_to_attack_graph: false,
        })
        setEditingItem(null)
    }

    const handleOpenModal = (item?: NetworkIndicator) => {
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
            const payload: Record<string, any> = {
                timestamp: form.timestamp || null,
                protocol: form.protocol || null,
                port: form.port ? parseInt(form.port) : null,
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
                await api.put(`/incidents/${incidentId}/network-iocs/${editingItem.id}`, payload)
            } else {
                await api.post(`/incidents/${incidentId}/network-iocs`, payload)
            }

            setShowModal(false)
            resetForm()
            loadData()
        } catch (error) {
            console.error('Failed to save network IOC:', error)
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleDelete = async (id: string) => {
        const confirmed = await confirm({
            title: 'Delete IOC',
            description: 'Are you sure you want to delete this network indicator?',
            confirmLabel: 'Delete',
            variant: 'destructive',
        })
        if (!confirmed) return
        try {
            await api.delete(`/incidents/${incidentId}/network-iocs/${id}`)
            loadData()
        } catch (error) {
            console.error('Failed to delete', error)
        }
    }

    const getDirectionIcon = (direction: string) => {
        switch (direction) {
            case 'inbound': return <ArrowDownLeft className="h-4 w-4 text-orange-400" />
            case 'outbound': return <ArrowUpRight className="h-4 w-4 text-red-400" />
            case 'lateral': return <ArrowLeftRight className="h-4 w-4 text-yellow-400" />
            default: return <Globe className="h-4 w-4" />
        }
    }

    const filteredIndicators = indicators.filter(i =>
        i.dns_ip.includes(search) || i.description?.toLowerCase().includes(search.toLowerCase())
    )

    return (
        <div className="space-y-4">
            <Card>
                <CardContent className="p-4">
                    <div className="flex justify-between gap-4">
                        <div className="relative flex-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search IPs, domains..." className="pl-10" variant="glass" />
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
                                    <TableHead>Direction</TableHead>
                                    <TableHead>Value (IP/DNS)</TableHead>
                                    <TableHead>Protocol/Port</TableHead>
                                    <TableHead>Source Host</TableHead>
                                    <TableHead>Dest Host</TableHead>
                                    <TableHead>Description</TableHead>
                                    <TableHead className="w-[50px]"></TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {isLoading ? <SkeletonTableRow columns={7} /> : filteredIndicators.length === 0 ? (
                                    <TableRow><TableCell colSpan={7}>
                                        <TableEmpty
                                            title={search ? 'No matching network IOCs' : 'No network IOCs'}
                                            description={search ? 'Try adjusting your search criteria' : 'Track IP addresses, domains, and URLs associated with malicious network activity.'}
                                            icon={<Network className="w-8 h-8" />}
                                        />
                                    </TableCell></TableRow>
                                ) : (
                                    filteredIndicators.map(item => (
                                        <TableRow key={item.id} className="group">
                                            <TableCell>
                                                <div className="flex items-center gap-2">
                                                    <div className="p-1 rounded bg-black/5 dark:bg-white/5">{getDirectionIcon(item.direction || '')}</div>
                                                    <span className="capitalize text-xs">{item.direction}</span>
                                                </div>
                                            </TableCell>
                                            <TableCell className="font-mono text-sm">{item.dns_ip}</TableCell>
                                            <TableCell>{item.protocol} {item.port ? `:${item.port}` : ''}</TableCell>
                                            <TableCell className="text-sm text-muted-foreground">
                                                {item.source_host_id
                                                    ? hosts.find(h => h.id === item.source_host_id)?.hostname
                                                    : item.source_host || '-'}
                                            </TableCell>
                                            <TableCell className="text-sm text-muted-foreground">
                                                {item.destination_host_id
                                                    ? hosts.find(h => h.id === item.destination_host_id)?.hostname
                                                    : item.destination_host || '-'}
                                            </TableCell>
                                            <TableCell className="text-sm text-muted-foreground">{item.description || '-'}</TableCell>
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

            <Dialog open={showModal} onOpenChange={setShowModal}>
                <DialogContent className="max-w-xl">
                    <DialogHeader><DialogTitle>{editingItem ? 'Edit' : 'Add'} Network Indicator</DialogTitle></DialogHeader>
                    <DialogBody className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Timestamp</Label>
                                <Input type="datetime-local" value={form.timestamp} onChange={e => setForm({ ...form, timestamp: e.target.value })} variant="glass" />
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
                                        <SelectItem value="TCP">TCP</SelectItem>
                                        <SelectItem value="UDP">UDP</SelectItem>
                                        <SelectItem value="HTTP">HTTP</SelectItem>
                                        <SelectItem value="HTTPS">HTTPS</SelectItem>
                                        <SelectItem value="DNS">DNS</SelectItem>
                                        <SelectItem value="ICMP">ICMP</SelectItem>
                                        <SelectItem value="SMB">SMB</SelectItem>
                                        <SelectItem value="RDP">RDP</SelectItem>
                                        <SelectItem value="SSH">SSH</SelectItem>
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
                            <div className="flex items-center gap-2 p-3 rounded-md border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-white/[0.02]">
                                <input
                                    type="checkbox"
                                    checked={form.add_to_attack_graph}
                                    onChange={e => setForm({ ...form, add_to_attack_graph: e.target.checked })}
                                    className="rounded bg-black/5 dark:bg-white/10 border-black/10 dark:border-white/20"
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
