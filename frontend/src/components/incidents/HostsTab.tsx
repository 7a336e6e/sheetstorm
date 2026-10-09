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
import { usePermission } from '@/components/auth/permission-gate'
import { Switch } from '@/components/ui/switch'
import api from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { notifyError, notifySuccess } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { acquisitionChip, triageColors, type TriageKey } from '@/lib/design-tokens'
import type {
    AcquisitionFlag,
    AcquisitionStatus,
    BulkHostUpdate,
    BulkHostUpdateResult,
    CompromisedHost,
    CustomFieldOption,
    VersionedRow,
} from '@/types'
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
    Clock,
} from 'lucide-react'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { DateTimeInput } from '@/components/ui/datetime-input'
import { Timestamp } from '@/components/ui/timestamp'
import { FocusNotice, type IncidentTabBaseProps } from './table-helpers'
import { ClockSkewEditor, formatSkew } from './provenance'

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

// Same values as the backend (CompromisedHost.CONTAINMENT_STATUSES); the
// former 'monitoring' option was rejected by the API with a 400.
const CONTAINMENT_STATUSES = [
    { value: 'active', label: 'Active', color: 'bg-red-500/20 text-red-400 border-red-400/30' },
    { value: 'compromised', label: 'Compromised', color: 'bg-red-500/20 text-red-400 border-red-400/30' },
    { value: 'isolated', label: 'Isolated', color: 'bg-blue-500/20 text-blue-400 border-blue-400/30' },
    { value: 'contained', label: 'Contained', color: 'bg-amber-500/20 text-amber-400 border-amber-400/30' },
    { value: 'reimaged', label: 'Reimaged', color: 'bg-green-500/20 text-green-400 border-green-400/30' },
    { value: 'cleaned', label: 'Cleaned', color: 'bg-green-500/20 text-green-400 border-green-400/30' },
    { value: 'decommissioned', label: 'Decommissioned', color: 'bg-gray-500/20 text-gray-400 border-gray-400/30' },
]

const TRIAGE_KEYS = Object.keys(triageColors) as TriageKey[]
const TRIAGE_OPTIONS = TRIAGE_KEYS.map((k) => ({ value: k, label: triageColors[k].label }))

const ACQUISITION_FLAGS: { key: AcquisitionFlag; short: string; label: string }[] = [
    { key: 'disk_imaged', short: 'Disk', label: 'Disk imaged' },
    { key: 'memory_captured', short: 'Mem', label: 'Memory captured' },
    { key: 'logs_collected', short: 'Logs', label: 'Logs collected' },
    { key: 'forensically_sound', short: '✓', label: 'Forensically sound' },
]

/** Server `acquisition` filter: flags must be true; `!flag` = not done. */
const ACQUISITION_FILTER_OPTIONS = [
    { value: 'disk_imaged', label: 'Disk imaged' },
    { value: 'memory_captured', label: 'Memory captured' },
    { value: 'logs_collected', label: 'Logs collected' },
    { value: 'forensically_sound', label: 'Forensically sound' },
    { value: 'memory_captured,!disk_imaged', label: 'Memory but no disk image' },
    { value: '!disk_imaged', label: 'No disk image' },
    { value: '!memory_captured', label: 'No memory capture' },
]

const BULK_MAX = 500

export function TriageBadge({ status }: { status?: string | null }) {
    const c = triageColors[(status || 'under_analysis') as TriageKey] ?? triageColors.under_analysis
    return (
        <Badge variant="outline" className={cn('border text-[10px]', c.bg, c.text, c.border)}>
            {c.label}
        </Badge>
    )
}

export function AcquisitionChips({ status }: { status?: AcquisitionStatus | null }) {
    return (
        <div className="flex items-center gap-1">
            {ACQUISITION_FLAGS.map((f) => {
                const on = !!status?.[f.key]
                return (
                    <span
                        key={f.key}
                        title={`${f.label}: ${on ? 'yes' : 'no'}`}
                        aria-label={`${f.label}: ${on ? 'yes' : 'no'}`}
                        className={cn('rounded border px-1 py-0 text-[10px] leading-4', on ? acquisitionChip.on : acquisitionChip.off)}
                    >
                        {f.short}
                    </span>
                )
            })}
        </div>
    )
}

type AcquisitionForm = Required<Pick<AcquisitionStatus, AcquisitionFlag>> & { acquired_at: string }

const EMPTY_ACQUISITION: AcquisitionForm = {
    disk_imaged: false, memory_captured: false, logs_collected: false, forensically_sound: false, acquired_at: '',
}

function toAcquisitionForm(a?: AcquisitionStatus | null): AcquisitionForm {
    return {
        disk_imaged: !!a?.disk_imaged,
        memory_captured: !!a?.memory_captured,
        logs_collected: !!a?.logs_collected,
        forensically_sound: !!a?.forensically_sound,
        acquired_at: a?.acquired_at || '',
    }
}

function fromAcquisitionForm(a: AcquisitionForm): AcquisitionStatus & { acquired_at: string | null } {
    return { ...a, acquired_at: a.acquired_at || null } as AcquisitionStatus & { acquired_at: string | null }
}

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
    const canUpdate = usePermission('hosts:update')
    const [acquisition, setAcquisition] = useState<AcquisitionForm>(EMPTY_ACQUISITION)
    const [bulkBusy, setBulkBusy] = useState(false)
    // Clock-skew editor (W3-PROV): mounted per host so its fields start from the row.
    const [skewHost, setSkewHost] = useState<HostRow | null>(null)

    const bulkUpdate = async (ids: string[], update: Omit<BulkHostUpdate, 'host_ids'>, clear: () => void) => {
        if (ids.length === 0) return
        if (ids.length > BULK_MAX) {
            notifyError(new Error(`Select at most ${BULK_MAX} hosts`), 'update the hosts')
            return
        }
        setBulkBusy(true)
        try {
            const res = await api.patch<BulkHostUpdateResult>(`${endpoint}/bulk`, { host_ids: ids, ...update })
            clear()
            invalidate(endpoint)
            notifySuccess('Hosts updated', `${res.updated} host${res.updated === 1 ? '' : 's'} updated.`)
        } catch (error) {
            notifyError(error, 'update the hosts')
        } finally {
            setBulkBusy(false)
        }
    }

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
        setAcquisition(EMPTY_ACQUISITION)
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
            setAcquisition(toAcquisitionForm(host.acquisition_status))
        } else {
            resetForm()
        }
        setShowModal(true)
    }

    const handleSubmit = async () => {
        if (!form.hostname) return
        setIsSubmitting(true)
        try {
            const payload = { ...form, first_seen: form.first_seen || null, acquisition_status: fromAcquisitionForm(acquisition) }
            if (editingHost) {
                await api.put(`${endpoint}/${editingHost.id}`, payload, { ifMatch: editingHost.version })
            } else {
                await api.post(endpoint, payload)
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
        { id: 'triage', header: 'Triage', sortKey: 'triage_status', cell: (h) => <TriageBadge status={h.triage_status} /> },
        { id: 'acquisition', header: 'Acquisition', hideBelow: 'md', cell: (h) => <AcquisitionChips status={h.acquisition_status} /> },
        { id: 'containment', header: 'Containment', sortKey: 'containment_status', cell: (h) => getContainmentBadge(h.containment_status || 'active') },
        {
            id: 'first_seen', header: 'First Seen', sortKey: 'first_seen', hideBelow: 'sm', className: 'text-sm text-muted-foreground',
            cell: (h) => <Timestamp value={h.first_seen} fallback="-" />,
        },
        {
            id: 'clock_skew', header: 'Clock skew', hideBelow: 'lg', className: 'whitespace-nowrap text-xs text-muted-foreground',
            cell: (h) => h.clock_skew_seconds === null || h.clock_skew_seconds === undefined
                ? '-'
                : (
                    <span title={h.clock_skew_basis || undefined}>
                        {formatSkew(h.clock_skew_seconds)}{h.timezone ? ` · ${h.timezone}` : ''}
                    </span>
                ),
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
                    <>
                        <FilterSelect
                            label="Triage"
                            allLabel="Any triage"
                            value={query.state.filters.triage_status}
                            onChange={(v) => query.setFilter('triage_status', v)}
                            options={TRIAGE_OPTIONS}
                        />
                        <FilterSelect
                            label="Acquisition"
                            allLabel="Any acquisition"
                            className="w-[200px]"
                            value={query.state.filters.acquisition}
                            onChange={(v) => query.setFilter('acquisition', v)}
                            options={ACQUISITION_FILTER_OPTIONS}
                        />
                        <FilterSelect
                            label="Containment"
                            value={query.state.filters.containment_status}
                            onChange={(v) => query.setFilter('containment_status', v)}
                            options={CONTAINMENT_STATUSES.map((c) => ({ value: c.value, label: c.label }))}
                        />
                    </>
                }
                selectable={canUpdate}
                bulkActions={(ids, clear) => (
                    <>
                        <Select disabled={bulkBusy} value="" onValueChange={(v) => void bulkUpdate(ids, { triage_status: v as TriageKey }, clear)}>
                            <SelectTrigger aria-label="Set triage for selected hosts" className="h-8 w-[160px]"><SelectValue placeholder="Set triage…" /></SelectTrigger>
                            <SelectContent>
                                {TRIAGE_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select disabled={bulkBusy} value="" onValueChange={(v) => void bulkUpdate(ids, { containment_status: v }, clear)}>
                            <SelectTrigger aria-label="Set containment for selected hosts" className="h-8 w-[180px]"><SelectValue placeholder="Set containment…" /></SelectTrigger>
                            <SelectContent>
                                {CONTAINMENT_STATUSES.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </>
                )}
                primaryAction={{ label: 'Add Host', onSelect: () => handleOpenModal(), permission: 'hosts:create' }}
                rowActions={(h) => [
                    { label: 'Edit', icon: Pencil, onSelect: () => handleOpenModal(h), permission: 'hosts:update' },
                    { label: 'Clock skew…', icon: Clock, onSelect: () => setSkewHost(h), permission: 'hosts:update' },
                    { label: 'Delete', icon: Trash2, destructive: true, onSelect: () => void handleDelete(h), permission: 'hosts:delete' },
                ]}
                focusedRowId={focusRowId}
                empty={{
                    title: 'No compromised hosts',
                    description: 'Record systems that have been identified as compromised during this incident investigation.',
                }}
            />

            {skewHost && (
                <ClockSkewEditor
                    key={skewHost.id}
                    incidentId={incidentId}
                    host={skewHost}
                    open
                    onOpenChange={(open) => { if (!open) setSkewHost(null) }}
                    onSaved={() => invalidate(`/incidents/${incidentId}`)}
                />
            )}

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
                        <fieldset className="space-y-3 rounded-md border border-white/10 p-3">
                            <legend className="px-1 text-sm font-medium">Acquisition</legend>
                            <div className="grid grid-cols-2 gap-3">
                                {ACQUISITION_FLAGS.map((f) => (
                                    <label key={f.key} className="flex items-center justify-between gap-2 text-sm">
                                        <span>{f.label}</span>
                                        <Switch
                                            aria-label={f.label}
                                            checked={acquisition[f.key]}
                                            onCheckedChange={(checked) => setAcquisition({ ...acquisition, [f.key]: checked })}
                                        />
                                    </label>
                                ))}
                            </div>
                            <div className="space-y-2">
                                <Label>Acquired At</Label>
                                <DateTimeInput value={acquisition.acquired_at} onChange={iso => setAcquisition({ ...acquisition, acquired_at: iso ?? '' })} variant="glass" />
                            </div>
                        </fieldset>
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
