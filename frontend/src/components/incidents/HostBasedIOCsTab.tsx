"use client"

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
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
import { DataTable, FilterSelect, type DataTableColumn } from '@/components/ui/data-table'
import { useAllPages, usePaginatedQuery } from '@/hooks/use-paginated-query'
import api from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { notifyError } from '@/lib/errors'
import type { HostBasedIndicator, CompromisedHost, CustomFieldOption, VersionedRow } from '@/types'
import {
    HardDrive,
    FileCode,
    Settings,
    Clock,
    Cpu,
    FileText,
    Terminal,
    Boxes,
    Trash2,
    Pencil,
    Key,
    Database,
    Wifi,
    Shield,
    User,
    Folder,
    Bug,
} from 'lucide-react'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { DateTimeInput } from '@/components/ui/datetime-input'
import { FocusNotice, type IncidentTabBaseProps } from './table-helpers'
import {
    ProvenanceBadge,
    ProvenanceSection,
    emptyProvenance,
    provenanceFromRecord,
    provenancePayload,
    useProvenanceRowActions,
} from './provenance'

type HostIocRow = VersionedRow<HostBasedIndicator>

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

export function HostBasedIOCsTab({ incidentId, focusRowId }: IncidentTabBaseProps) {
    const confirm = useConfirm()
    const endpoint = `/incidents/${incidentId}/host-iocs`
    const query = usePaginatedQuery<HostIocRow>({
        endpoint,
        urlKey: 'host-iocs',
        focus: focusRowId,
        live: 'host_ioc',
    })
    const [showModal, setShowModal] = useState(false)
    const [editingItem, setEditingItem] = useState<HostIocRow | null>(null)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [customTypes, setCustomTypes] = useState<CustomFieldOption[]>([])
    // Provenance (W3-PROV); `provInitial` limits an edit to the changed fields.
    const [prov, setProv] = useState(emptyProvenance)
    const [provInitial, setProvInitial] = useState(emptyProvenance)
    // Every host of the incident for the picker (not just the first page).
    const hosts = useAllPages<CompromisedHost>(`/incidents/${incidentId}/hosts`, { live: 'host', enabled: showModal })

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

    // Org-defined artifact types are optional: the defaults work without them.
    useEffect(() => {
        let cancelled = false
        api.get<{ items: CustomFieldOption[] }>(`/custom-fields?field_name=artifact_type`)
            .then((res) => { if (!cancelled) setCustomTypes(res.items || []) })
            .catch(() => { /* optional data */ })
        return () => { cancelled = true }
    }, [])

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
        setProv(emptyProvenance())
        setProvInitial(emptyProvenance())
        setEditingItem(null)
    }

    const handleOpenModal = (item?: HostIocRow) => {
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
            const fromRecord = provenanceFromRecord(item)
            setProv(fromRecord)
            setProvInitial(fromRecord)
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
                ...provenancePayload(prov, editingItem ? provInitial : undefined),
            }

            if (editingItem) {
                await api.put(`${endpoint}/${editingItem.id}`, payload, { ifMatch: editingItem.version })
            } else {
                await api.post(endpoint, payload)
            }

            setShowModal(false)
            resetForm()
            invalidate(endpoint)
        } catch (error) {
            notifyError(error, editingItem ? 'save the host IOC' : 'add the host IOC')
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleDelete = async (item: HostIocRow) => {
        if (!(await confirmDelete(confirm, 'host IOC', item.artifact_value))) return
        try {
            await api.delete(`${endpoint}/${item.id}`, undefined, { ifMatch: item.version })
            invalidate(endpoint)
        } catch (error) {
            notifyError(error, 'delete the host IOC')
        }
    }

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

    const provenanceActions = useProvenanceRowActions(incidentId, 'host_ioc', () => invalidate(endpoint))

    const columns: DataTableColumn<HostIocRow>[] = [
        {
            id: 'type', header: 'Type', sortKey: 'artifact_type', cell: (item) => (
                <div className="flex items-center gap-2">
                    <div className="p-1 rounded bg-white/5">{getArtifactTypeIcon(item.artifact_type)}</div>
                    <span className="text-xs">{getArtifactTypeLabel(item.artifact_type)}</span>
                </div>
            ),
        },
        {
            id: 'value', header: 'Value', className: 'font-mono text-sm max-w-[300px] truncate',
            cell: (item) => <span title={item.artifact_value}>{item.artifact_value}</span>,
        },
        { id: 'host', header: 'Host', sortKey: 'host', hideBelow: 'sm', cell: (item) => item.host_ref?.hostname || item.host || '-' },
        { id: 'provenance', header: 'Source', hideBelow: 'sm', className: 'w-[56px]', cell: (item) => <ProvenanceBadge record={item} /> },
        {
            id: 'status', header: 'Status', cell: (item) => (
                <Badge variant={item.remediated ? 'default' : 'destructive'} className={item.remediated ? 'bg-green-500/20 text-green-400' : ''}>
                    {item.remediated ? 'Remediated' : 'Active'}
                </Badge>
            ),
        },
        { id: 'notes', header: 'Notes', hideBelow: 'lg', className: 'max-w-[200px] truncate text-muted-foreground text-xs', cell: (item) => item.notes },
    ]

    return (
        <div className="space-y-4">
            <FocusNotice focusRowId={focusRowId} focusFound={query.focusFound} noun="host IOC" />
            <DataTable
                query={query}
                columns={columns}
                getRowId={(item) => item.id}
                ariaLabel="Host-based IOCs"
                searchPlaceholder="Search IOCs..."
                toolbar={
                    <FilterSelect
                        label="Types"
                        allLabel="All types"
                        value={query.state.filters.artifact_type}
                        onChange={(v) => query.setFilter('artifact_type', v)}
                        options={allArtifactTypes.map((t) => ({ value: t.value, label: t.label }))}
                        className="w-48"
                    />
                }
                primaryAction={{ label: 'Add IOC', onSelect: () => handleOpenModal(), permission: 'host_iocs:create' }}
                rowActions={(item) => [
                    { label: 'Edit', icon: Pencil, onSelect: () => handleOpenModal(item), permission: 'host_iocs:update' },
                    ...provenanceActions(item),
                    { label: 'Delete', icon: Trash2, destructive: true, onSelect: () => void handleDelete(item), permission: 'host_iocs:delete' },
                ]}
                focusedRowId={focusRowId}
                empty={{
                    title: 'No host-based IOCs',
                    description: 'Document file artifacts, registry keys, processes, and other host-based indicators of compromise.',
                }}
            />

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
                                        {hosts.items.map(h => <SelectItem key={h.id} value={h.id}>{h.hostname}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label>Date/Time Observed</Label>
                                <DateTimeInput value={form.datetime} onChange={iso => setForm({ ...form, datetime: iso ?? '' })} variant="glass" />
                            </div>
                        </div>
                        <ProvenanceSection
                            incidentId={incidentId}
                            value={prov}
                            onChange={setProv}
                            timestamp={form.datetime}
                            onUseComputed={(utc) => {
                                setForm((f) => ({ ...f, datetime: utc }))
                                setProv((p) => ({ ...p, keep_manual: false }))
                            }}
                            hostId={form.host_id || null}
                            timestampLabel="date/time observed"
                        />
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
