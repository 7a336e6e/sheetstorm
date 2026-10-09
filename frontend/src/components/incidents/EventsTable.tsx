"use client"

import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
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
import { DataTable, FilterSelect, type DataTableColumn } from '@/components/ui/data-table'
import { DateTimeInput } from '@/components/ui/datetime-input'
import { Timestamp } from '@/components/ui/timestamp'
import { usePermission } from '@/components/auth/permission-gate'
import { useAllPages, usePaginatedQuery } from '@/hooks/use-paginated-query'
import api from '@/lib/api'
import { invalidate } from '@/lib/query-cache'
import { notifyError, notifySuccess } from '@/lib/errors'
import { PHASE_INFO, confidenceColors, type ConfidenceKey } from '@/lib/design-tokens'
import { dwellMs, formatDuration } from '@/lib/time'
import type { TimelineEvent, CompromisedHost, D3FENDTechnique, MitreMapping, VersionedRow } from '@/types'
import {
    AlertTriangle,
    Plus,
    Clock,
    Trash2,
    Server,
    Edit2,
    Star,
    Shield,
    Target,
    Tag,
    Loader2,
} from 'lucide-react'
import { confirmDelete, useConfirm } from '@/components/ui/confirm-dialog'
import { FocusNotice, type IncidentTabBaseProps } from './table-helpers'
import {
    ProvenanceBadge,
    ProvenanceSection,
    emptyProvenance,
    provenanceFromRecord,
    provenancePayload,
    useProvenanceRowActions,
} from './provenance'
import { ProvenanceDetails } from './provenance/ProvenanceDetails'
import { ResponseTimelineToggle } from './decisions/ResponseTimelineToggle'

type EventRow = VersionedRow<TimelineEvent>

const tacticColors: Record<string, string> = {
    'reconnaissance': 'text-blue-400',
    'resource-development': 'text-blue-300',
    'resource development': 'text-blue-300',
    'initial-access': 'text-amber-400',
    'initial access': 'text-amber-400',
    'execution': 'text-orange-400',
    'persistence': 'text-rose-400',
    'privilege-escalation': 'text-red-400',
    'privilege escalation': 'text-red-400',
    'defense-evasion': 'text-pink-400',
    'defense evasion': 'text-pink-400',
    'credential-access': 'text-yellow-400',
    'credential access': 'text-yellow-400',
    'discovery': 'text-cyan-400',
    'lateral-movement': 'text-emerald-400',
    'lateral movement': 'text-emerald-400',
    'collection': 'text-violet-400',
    'command-and-control': 'text-purple-400',
    'command and control': 'text-purple-400',
    'exfiltration': 'text-red-300',
    'impact': 'text-red-500',
}

const d3fendTacticColors: Record<string, string> = {
    'Harden': 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    'Detect': 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    'Isolate': 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    'Deceive': 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    'Evict': 'bg-red-500/10 text-red-400 border-red-500/20',
    'Restore': 'bg-green-500/10 text-green-400 border-green-500/20',
}


const PHASE_OPTIONS = Object.values(PHASE_INFO).map((p) => ({ value: String(p.number), label: `${p.number}. ${p.name}` }))

const SHOW_OPTIONS = [
    { value: 'key', label: 'Pinned only' },
    { value: 'ioc', label: 'IOCs only' },
]

const CONFIDENCE_KEYS = Object.keys(confidenceColors) as ConfidenceKey[]

/** Server filter `confidence` takes a comma list; one combined option covers the common "high or better". */
const CONFIDENCE_OPTIONS = [
    ...CONFIDENCE_KEYS.map((k) => ({ value: k, label: confidenceColors[k].label })),
    { value: 'high,certain', label: 'High or certain' },
]

const DETECTION_OPTIONS = [
    { value: 'true', label: 'Detected' },
    { value: 'false', label: 'Not yet detected' },
]

export function ConfidenceBadge({ level }: { level?: string | null }) {
    const c = level ? confidenceColors[level as ConfidenceKey] : undefined
    if (!c) return <span className="text-xs text-muted-foreground/60">—</span>
    return (
        <Badge variant="outline" className={`border px-1.5 py-0 text-[10px] ${c.bg} ${c.text} ${c.border}`}>
            {c.label}
        </Badge>
    )
}

/** Detection minus occurrence; negative values are flagged (bad timestamps). */
export function DwellCell({ event }: { event: Pick<TimelineEvent, 'timestamp' | 'detection_time'> }) {
    const ms = dwellMs(event.timestamp, event.detection_time)
    if (ms === null) return <span className="text-xs text-muted-foreground/60">—</span>
    if (ms < 0) {
        return (
            <span
                className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400"
                title="Detected before occurrence — check timestamps"
            >
                <AlertTriangle className="h-3 w-3" aria-label="Detected before occurrence — check timestamps" />
                {formatDuration(ms)}
            </span>
        )
    }
    return <span className="text-xs tabular-nums text-muted-foreground">{formatDuration(ms)}</span>
}

/** MITRE mappings of an event, falling back to the legacy single tactic/technique. */
function eventMappings(event: TimelineEvent): MitreMapping[] {
    if (event.mitre_mappings?.length) return event.mitre_mappings
    if (event.mitre_tactic) return [{ tactic: event.mitre_tactic, technique: event.mitre_technique || '', name: '' }]
    return []
}

/** Expanded row: details, full activity text and D3FEND countermeasures. */
function EventDetail({
    event,
    d3fendCache,
    d3fendLoading,
    onNeedD3fend,
}: {
    event: EventRow
    d3fendCache: Record<string, D3FENDTechnique[]>
    d3fendLoading: Record<string, boolean>
    onNeedD3fend: (techniqueId: string) => void
}) {
    const mappings = eventMappings(event)
    const allTechniqueIds = mappings.map(m => m.technique).filter(Boolean)
    const allD3fend = allTechniqueIds.flatMap(tid => d3fendCache[tid] || [])
    const isLoadingD3fend = allTechniqueIds.some(tid => d3fendLoading[tid])
    const missing = allTechniqueIds.filter(tid => !d3fendCache[tid]).join(',')

    useEffect(() => {
        if (missing) missing.split(',').forEach(onNeedD3fend)
    }, [missing, onNeedD3fend])

    return (
        <div className="px-2 py-1 space-y-4 border-l-2 border-blue-500/30">
                                                                <div>
                                                                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Event Details</h4>
                                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                                        <div className="space-y-1">
                                                                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                                                <Clock className="h-3 w-3" />
                                                                                <span className="font-medium">Event time</span>
                                                                            </div>
                                                                            <p className="text-sm pl-5"><Timestamp value={event.timestamp} mode="utc" /></p>
                                                                            <p className="text-xs pl-5 text-muted-foreground"><Timestamp value={event.timestamp} mode="local" /></p>
                                                                        </div>
                                                                        <div className="space-y-1">
                                                                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                                                <Clock className="h-3 w-3" />
                                                                                <span className="font-medium">Detected</span>
                                                                                <DwellCell event={event} />
                                                                            </div>
                                                                            <p className="text-sm pl-5"><Timestamp value={event.detection_time} mode="utc" fallback="Not recorded" /></p>
                                                                            {event.detection_time && (
                                                                                <p className="text-xs pl-5 text-muted-foreground"><Timestamp value={event.detection_time} mode="local" /></p>
                                                                            )}
                                                                        </div>
                                                                        {(event.host || event.hostname) && (
                                                                            <div className="space-y-1">
                                                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                                                    <Server className="h-3 w-3" />
                                                                                    <span className="font-medium">Host</span>
                                                                                </div>
                                                                                <p className="text-sm pl-5">{event.host?.hostname || event.hostname}</p>
                                                                            </div>
                                                                        )}
                                                                        {event.source && (
                                                                            <div className="space-y-1">
                                                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                                                    <Tag className="h-3 w-3" />
                                                                                    <span className="font-medium">Source</span>
                                                                                </div>
                                                                                <p className="text-sm pl-5">{event.source}</p>
                                                                            </div>
                                                                        )}
                                                                        {event.provenance_level && event.provenance_level !== 'none' && (
                                                                            <div className="space-y-1 md:col-span-2">
                                                                                <ProvenanceDetails record={event} />
                                                                            </div>
                                                                        )}
                                                                        {mappings.length > 0 && (
                                                                            <div className="space-y-1">
                                                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                                                    <Target className="h-3 w-3" />
                                                                                    <span className="font-medium">MITRE ATT&CK</span>
                                                                                </div>
                                                                                <div className="flex flex-col gap-1 pl-5">
                                                                                    {mappings.map((m, i) => (
                                                                                        <div key={i} className="flex items-center gap-2">
                                                                                            <Badge variant="outline" className={`text-[10px] ${tacticColors[m.tactic?.toLowerCase()] || ''}`}>
                                                                                                {m.tactic}
                                                                                            </Badge>
                                                                                            {m.technique && (
                                                                                                <span className="text-xs font-mono text-muted-foreground">{m.technique}</span>
                                                                                            )}
                                                                                            {m.name && (
                                                                                                <span className="text-xs text-muted-foreground">— {m.name}</span>
                                                                                            )}
                                                                                        </div>
                                                                                    ))}
                                                                                </div>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>

                                                                {/* Activity Full Text */}
                                                                <div>
                                                                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Activity</h4>
                                                                    <p className="text-sm whitespace-pre-wrap">{event.activity}</p>
                                                                </div>

                                                                {/* D3FEND Mitigations */}
                                                                {allTechniqueIds.length > 0 && (
                                                                    <div>
                                                                        <div className="flex items-center gap-2 mb-2">
                                                                            <Shield className="h-3.5 w-3.5 text-blue-400" />
                                                                            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                                                                                Recommended Mitigations (D3FEND)
                                                                            </h4>
                                                                        </div>

                                                                        {isLoadingD3fend ? (
                                                                            <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
                                                                                <Loader2 className="h-3 w-3 animate-spin" />
                                                                                Loading D3FEND countermeasures...
                                                                            </div>
                                                                        ) : allD3fend.length > 0 ? (
                                                                            <div className="max-h-64 overflow-y-auto rounded-md border border-white/10 p-2 grid gap-2">
                                                                                {allD3fend.map((d3) => (
                                                                                    <div
                                                                                        key={d3.id}
                                                                                        className={`rounded-md border px-3 py-2 ${d3fendTacticColors[d3.tactic] || 'bg-white/5 text-muted-foreground border-white/10'}`}
                                                                                    >
                                                                                        <div className="flex items-center gap-2 mb-1">
                                                                                            <span className="text-xs font-mono opacity-70">{d3.id}</span>
                                                                                            <span className="text-sm font-medium">{d3.name}</span>
                                                                                            {d3.source === 'platform-suggested' && (
                                                                                                <Badge variant="glass" className="text-[8px] px-1 py-0">Suggested</Badge>
                                                                                            )}
                                                                                            <Badge variant="outline" className="text-[9px] ml-auto">{d3.tactic}</Badge>
                                                                                        </div>
                                                                                        <p className="text-xs opacity-80">{d3.description}</p>
                                                                                        {d3.examples && d3.examples.length > 0 && (
                                                                                            <div className="mt-1.5 flex flex-wrap gap-1">
                                                                                                {d3.examples.map((ex, i) => (
                                                                                                    <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5">
                                                                                                        {ex}
                                                                                                    </span>
                                                                                                ))}
                                                                                            </div>
                                                                                        )}
                                                                                    </div>
                                                                                ))}
                                                                            </div>
                                                                        ) : (
                                                                            <p className="text-xs text-muted-foreground py-1">
                                                                                No D3FEND countermeasures mapped for {allTechniqueIds.join(', ')}
                                                                            </p>
                                                                        )}
                                                                    </div>
                                                                )}
        </div>
    )
}

export function EventsTable({ incidentId, focusRowId }: IncidentTabBaseProps) {
    const confirm = useConfirm()
    const canUpdate = usePermission('timeline:update')
    const endpoint = `/incidents/${incidentId}/timeline`
    const query = usePaginatedQuery<EventRow>({
        endpoint,
        urlKey: 'events',
        focus: focusRowId,
        live: 'timeline_event',
    })
    const [showAddModal, setShowAddModal] = useState(false)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [editing, setEditing] = useState<EventRow | null>(null)
    const [d3fendCache, setD3fendCache] = useState<Record<string, D3FENDTechnique[]>>({})
    const [d3fendLoading, setD3fendLoading] = useState<Record<string, boolean>>({})
    const hostsQuery = useAllPages<CompromisedHost>(`/incidents/${incidentId}/hosts`, { live: 'host', enabled: showAddModal })
    const hosts = hostsQuery.items

    const [form, setForm] = useState({
        timestamp: '',
        detection_time: '',
        confidence_level: '',
        activity: '',
        source: '',
        host_id: '',
        mitre_mappings: [] as MitreMapping[],
    })

    const [mappingDraft, setMappingDraft] = useState({ tactic: '', technique: '' })
    // Provenance (W3-PROV): `provInitial` is what the record had, so an edit
    // only sends the provenance fields that changed.
    const [prov, setProv] = useState(emptyProvenance)
    const [provInitial, setProvInitial] = useState(emptyProvenance)

    // MITRE ATT&CK form data for bidirectional tactic/technique linking
    const [mitreFormData, setMitreFormData] = useState<{
        tactics: { id: string; name: string; slug: string }[]
        techByTactic: Record<string, { id: string; name: string }[]>
        techToTactic: Record<string, string>
        allTechniques: { id: string; name: string }[]
    }>({ tactics: [], techByTactic: {}, techToTactic: {}, allTechniques: [] })
    const [techSearch, setTechSearch] = useState('')

    // Fetch MITRE ATT&CK form data once on dialog open
    useEffect(() => {
        if (!showAddModal || mitreFormData.tactics.length > 0) return
        api.get<{
            tactics: { id: string; name: string; slug: string }[]
            technique_by_tactic: Record<string, { id: string; name: string }[]>
            technique_to_tactic: Record<string, string>
        }>('/knowledge-base/mitre-attack/form-data').then(data => {
            const all: { id: string; name: string }[] = []
            const seen = new Set<string>()
            for (const techs of Object.values(data.technique_by_tactic)) {
                for (const t of techs) {
                    if (!seen.has(t.id)) { seen.add(t.id); all.push(t) }
                }
            }
            all.sort((a, b) => a.id.localeCompare(b.id))
            setMitreFormData({
                tactics: data.tactics,
                techByTactic: data.technique_by_tactic,
                techToTactic: data.technique_to_tactic,
                allTechniques: all,
            })
        }).catch(() => {})
    }, [showAddModal, mitreFormData.tactics.length])

    // Techniques available for the selected tactic (or all if none selected)
    const availableTechniques = useMemo(() => {
        if (mappingDraft.tactic && mitreFormData.techByTactic[mappingDraft.tactic]) {
            return mitreFormData.techByTactic[mappingDraft.tactic]
        }
        return mitreFormData.allTechniques
    }, [mappingDraft.tactic, mitreFormData])

    // Filtered techniques based on search input
    const filteredTechniques = useMemo(() => {
        if (!techSearch) return availableTechniques.slice(0, 50)
        const q = techSearch.toLowerCase()
        return availableTechniques.filter(
            t => t.id.toLowerCase().includes(q) || t.name.toLowerCase().includes(q)
        ).slice(0, 50)
    }, [availableTechniques, techSearch])

    // Handle tactic change — clear technique if it doesn't belong to the new tactic
    const handleTacticChange = (slug: string) => {
        const techs = mitreFormData.techByTactic[slug] || []
        const currentTechInNewTactic = techs.some(t => t.id === mappingDraft.technique)
        setMappingDraft({
            tactic: slug,
            technique: currentTechInNewTactic ? mappingDraft.technique : '',
        })
        setTechSearch('')
    }

    // Handle technique selection — auto-select tactic
    const handleTechniqueSelect = (techId: string) => {
        const tacticSlug = mitreFormData.techToTactic[techId]
        setMappingDraft({
            technique: techId,
            tactic: tacticSlug || mappingDraft.tactic,
        })
        setTechSearch('')
    }

    // Handle manual technique ID input — auto-resolve tactic
    const handleTechniqueInput = (value: string) => {
        const upper = value.toUpperCase().trim()
        setTechSearch(value)
        const resolvedTactic = mitreFormData.techToTactic[upper]
        setMappingDraft({
            technique: upper,
            tactic: resolvedTactic || mappingDraft.tactic,
        })
    }

    // Add current mapping draft to the form's mitre_mappings list
    const handleAddMapping = () => {
        if (!mappingDraft.tactic && !mappingDraft.technique) return
        const techName = mitreFormData.allTechniques.find(t => t.id === mappingDraft.technique)?.name || ''
        const newMapping: MitreMapping = {
            tactic: mappingDraft.tactic,
            technique: mappingDraft.technique,
            name: techName,
        }
        setForm(prev => ({
            ...prev,
            mitre_mappings: [...prev.mitre_mappings, newMapping],
        }))
        setMappingDraft({ tactic: '', technique: '' })
        setTechSearch('')
    }

    // Remove a mapping by index
    const handleRemoveMapping = (idx: number) => {
        setForm(prev => ({
            ...prev,
            mitre_mappings: prev.mitre_mappings.filter((_, i) => i !== idx),
        }))
    }

    const d3fendRequested = useRef<Set<string>>(new Set())
    const fetchD3fendSuggestions = useCallback(async (techniqueId: string) => {
        if (d3fendRequested.current.has(techniqueId)) return
        d3fendRequested.current.add(techniqueId)
        setD3fendLoading(prev => ({ ...prev, [techniqueId]: true }))
        try {
            const res = await api.post<{ items: D3FENDTechnique[]; total: number }>('/knowledge-base/d3fend/suggest', {
                attack_techniques: [techniqueId],
            })
            setD3fendCache(prev => ({ ...prev, [techniqueId]: res.items || [] }))
        } catch {
            // Suggestions are optional context: show "none mapped".
            setD3fendCache(prev => ({ ...prev, [techniqueId]: [] }))
        } finally {
            setD3fendLoading(prev => ({ ...prev, [techniqueId]: false }))
        }
    }, [])

    // Timeline writes can create IOCs / hosts server-side: refresh the whole incident.
    const invalidateIncident = () => invalidate(`/incidents/${incidentId}`)

    const handleAddEvent = async () => {
        // A raw timestamp (+ zone) lets the server derive the time.
        if ((!form.timestamp && !prov.raw_timestamp.trim()) || !form.activity) return
        setIsSubmitting(true)
        try {
            const payload = {
                timestamp: form.timestamp || undefined,
                detection_time: form.detection_time || null,
                confidence_level: form.confidence_level || null,
                activity: form.activity,
                source: form.source || null,
                host_id: form.host_id || null,
                mitre_mappings: form.mitre_mappings.length > 0 ? form.mitre_mappings : undefined,
                ...provenancePayload(prov, editing ? provInitial : undefined),
            }
            if (editing) {
                await api.put(`${endpoint}/${editing.id}`, payload, { ifMatch: editing.version })
            } else {
                await api.post(endpoint, payload)
            }
            setShowAddModal(false)
            setEditing(null)
            resetForm()
            invalidateIncident()
        } catch (error) {
            notifyError(error, editing ? 'save the event' : 'add the event')
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleDelete = async (event: EventRow) => {
        if (!(await confirmDelete(confirm, 'timeline event'))) return
        try {
            await api.delete(`${endpoint}/${event.id}`, undefined, { ifMatch: event.version })
            invalidateIncident()
        } catch (error) {
            notifyError(error, 'delete the event')
        }
    }

    const handleAddClick = () => {
        setEditing(null)
        resetForm()
        setShowAddModal(true)
    }

    const handleEditClick = (event: EventRow) => {
        setEditing(event)
        setForm({
            timestamp: event.timestamp || '',
            detection_time: event.detection_time || '',
            confidence_level: event.confidence_level || '',
            activity: event.activity,
            source: event.source || '',
            host_id: event.host?.id || event.host_id || '',
            mitre_mappings: eventMappings(event),
        })
        const fromRecord = provenanceFromRecord(event)
        setProv(fromRecord)
        setProvInitial(fromRecord)
        setMappingDraft({ tactic: '', technique: '' })
        setShowAddModal(true)
    }

    const handleToggleKeyEvent = async (event: EventRow) => {
        try {
            await api.put(`${endpoint}/${event.id}`, { is_key_event: !event.is_key_event }, { ifMatch: event.version })
            invalidateIncident()
            notifySuccess(
                event.is_key_event ? 'Removed from Timeline' : 'Pinned to Timeline',
                event.is_key_event
                    ? 'Event will no longer appear on the visual timeline.'
                    : 'Event will now appear on the visual timeline.'
            )
        } catch (error) {
            notifyError(error, 'update the event')
        }
    }

    const resetForm = () => {
        setForm({
            timestamp: '',
            detection_time: '',
            confidence_level: '',
            activity: '',
            source: '',
            host_id: '',
            mitre_mappings: [],
        })
        setProv(emptyProvenance())
        setProvInitial(emptyProvenance())
        setMappingDraft({ tactic: '', technique: '' })
        setTechSearch('')
    }

    const provenanceActions = useProvenanceRowActions(incidentId, 'timeline_event', invalidateIncident)

    const { filters } = query.state
    const showValue = filters.key_only === 'true' ? 'key' : filters.ioc_only === 'true' ? 'ioc' : undefined
    const setShow = (v?: string) => {
        query.setFilter('key_only', v === 'key' ? 'true' : undefined)
        query.setFilter('ioc_only', v === 'ioc' ? 'true' : undefined)
    }

    const columns: DataTableColumn<EventRow>[] = [
        {
            id: 'pin',
            header: <Star className="h-3.5 w-3.5" aria-label="Pinned" />,
            className: 'w-[40px] px-2',
            cell: (event) => canUpdate ? (
                <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); void handleToggleKeyEvent(event) }}
                    className={`p-0.5 rounded transition-colors ${event.is_key_event
                        ? 'text-amber-400 hover:text-amber-300'
                        : 'text-muted-foreground/40 hover:text-amber-400/60'
                    }`}
                    title={event.is_key_event ? 'Remove from timeline' : 'Pin to timeline'}
                    aria-label={event.is_key_event ? 'Unpin event' : 'Pin event'}
                    aria-pressed={event.is_key_event}
                >
                    <Star className={`h-4 w-4 ${event.is_key_event ? 'fill-current' : ''}`} />
                </button>
            ) : event.is_key_event ? (
                <Star className="h-4 w-4 fill-current text-amber-400" aria-label="Pinned" />
            ) : null,
        },
        {
            id: 'timestamp', header: 'Event time', sortKey: 'timestamp', className: 'whitespace-nowrap text-xs text-muted-foreground',
            cell: (event) => <Timestamp value={event.timestamp} />,
        },
        {
            id: 'provenance', header: 'Source', hideBelow: 'md', className: 'w-[56px]',
            cell: (event) => <ProvenanceBadge record={event} />,
        },
        {
            id: 'detection_time', header: 'Detected', sortKey: 'detection_time', hideBelow: 'md',
            className: 'whitespace-nowrap text-xs text-muted-foreground',
            cell: (event) => <Timestamp value={event.detection_time} fallback="—" />,
        },
        {
            id: 'dwell', header: 'Dwell', sortKey: 'dwell', hideBelow: 'lg', className: 'whitespace-nowrap',
            cell: (event) => <DwellCell event={event} />,
        },
        {
            id: 'confidence', header: 'Confidence', sortKey: 'confidence', hideBelow: 'sm',
            cell: (event) => <ConfidenceBadge level={event.confidence_level} />,
        },
        {
            id: 'host', header: 'Host', sortKey: 'hostname', hideBelow: 'md',
            cell: (event) => event.host || event.hostname ? (
                <div className="flex items-center gap-1">
                    <Server className="h-3 w-3 text-muted-foreground" />
                    {event.host?.hostname || event.hostname}
                </div>
            ) : '-',
        },
        {
            id: 'activity', header: 'Activity', className: 'max-w-[400px]',
            cell: (event) => (
                <div className="flex items-center gap-2 min-w-0">
                    <span className="truncate" title={event.activity}>{event.activity}</span>
                    {event.is_ioc && <Badge variant="critical" className="text-[10px] px-1.5 py-0 shrink-0">IOC</Badge>}
                </div>
            ),
        },
        {
            id: 'mitre', header: 'MITRE Tactic / Technique', hideBelow: 'lg',
            cell: (event) => {
                const mappings = eventMappings(event)
                return (
                    <div className="flex flex-col gap-1 items-start">
                        {mappings.length > 0 ? mappings.map((m, i) => (
                            <div key={i} className="flex items-center gap-1.5">
                                <Badge variant="outline" className={`text-[10px] ${tacticColors[m.tactic?.toLowerCase()] || ''}`}>{m.tactic}</Badge>
                                {m.technique && <span className="text-xs font-mono text-muted-foreground">{m.technique}</span>}
                            </div>
                        )) : <span className="text-xs text-muted-foreground">—</span>}
                    </div>
                )
            },
        },
    ]

    return (
        <div className="space-y-4">
            <FocusNotice focusRowId={focusRowId} focusFound={query.focusFound} noun="event" />
            <ResponseTimelineToggle incidentId={incidentId} />
            <DataTable
                query={query}
                columns={columns}
                getRowId={(e) => e.id}
                ariaLabel="Timeline events"
                searchPlaceholder="Search activity, hosts..."
                toolbar={
                    <>
                        <FilterSelect
                            label="Phase"
                            allLabel="All phases"
                            value={filters.phase}
                            onChange={(v) => query.setFilter('phase', v)}
                            options={PHASE_OPTIONS}
                        />
                        <FilterSelect
                            label="Show"
                            allLabel="All events"
                            value={showValue}
                            onChange={setShow}
                            options={SHOW_OPTIONS}
                        />
                        <FilterSelect
                            label="Confidence"
                            allLabel="Any confidence"
                            value={filters.confidence}
                            onChange={(v) => query.setFilter('confidence', v)}
                            options={CONFIDENCE_OPTIONS}
                        />
                        <FilterSelect
                            label="Detection"
                            allLabel="Detected or not"
                            value={filters.has_detection}
                            onChange={(v) => query.setFilter('has_detection', v)}
                            options={DETECTION_OPTIONS}
                        />
                    </>
                }
                primaryAction={{ label: 'Add Event', onSelect: handleAddClick, permission: 'timeline:create' }}
                rowActions={(event) => [
                    { label: 'Edit', icon: Edit2, onSelect: () => handleEditClick(event), permission: 'timeline:update' },
                    { label: event.is_key_event ? 'Unpin from timeline' : 'Pin to timeline', icon: Star, onSelect: () => void handleToggleKeyEvent(event), permission: 'timeline:update' },
                    ...provenanceActions(event),
                    { label: 'Delete', icon: Trash2, destructive: true, onSelect: () => void handleDelete(event), permission: 'timeline:delete' },
                ]}
                renderExpanded={(event) => (
                    <EventDetail
                        event={event}
                        d3fendCache={d3fendCache}
                        d3fendLoading={d3fendLoading}
                        onNeedD3fend={fetchD3fendSuggestions}
                    />
                )}
                focusedRowId={focusRowId}
                empty={{
                    title: 'No timeline events',
                    description: 'Build a chronological timeline of attacker activity, system events, and investigation milestones.',
                }}
            />

            <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>{editing ? 'Edit Event' : 'Add Event'}</DialogTitle>
                    </DialogHeader>
                    <DialogBody className="space-y-4">
                        <div className="space-y-2">
                            <Label>{prov.raw_timestamp.trim() ? 'Timestamp' : 'Timestamp *'}</Label>
                            <DateTimeInput value={form.timestamp} onChange={iso => setForm({ ...form, timestamp: iso ?? '' })} />
                        </div>
                        <div className="space-y-2">
                            <Label>Activity *</Label>
                            <Textarea value={form.activity} onChange={e => setForm({ ...form, activity: e.target.value })} />
                        </div>
                        <div className="space-y-2">
                            <Label>Source</Label>
                            <Input value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} placeholder="e.g. Sysmon, EDR, Firewall..." />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Detection Time</Label>
                                <DateTimeInput value={form.detection_time} onChange={iso => setForm({ ...form, detection_time: iso ?? '' })} />
                            </div>
                            <div className="space-y-2">
                                <Label>Confidence</Label>
                                <Select
                                    value={form.confidence_level || 'none'}
                                    onValueChange={v => setForm({ ...form, confidence_level: v === 'none' ? '' : v })}
                                >
                                    <SelectTrigger aria-label="Confidence"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="none">—</SelectItem>
                                        {CONFIDENCE_KEYS.map(k => (
                                            <SelectItem key={k} value={k}>{confidenceColors[k].label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label>Host</Label>
                            <Select value={form.host_id} onValueChange={v => setForm({ ...form, host_id: v })}>
                                <SelectTrigger><SelectValue placeholder="Select Host" /></SelectTrigger>
                                <SelectContent>
                                    {hosts.map(h => (
                                        <SelectItem key={h.id} value={h.id}>
                                            {h.hostname}{h.ip_address ? ` (${h.ip_address})` : ''}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <ProvenanceSection
                            incidentId={incidentId}
                            value={prov}
                            onChange={setProv}
                            timestamp={form.timestamp}
                            onUseComputed={(utc) => {
                                setForm((f) => ({ ...f, timestamp: utc }))
                                setProv((p) => ({ ...p, keep_manual: false }))
                            }}
                            hostId={form.host_id || null}
                            timestampLabel="timestamp"
                        />
                        {/* MITRE ATT&CK Mappings */}
                        <div className="space-y-3">
                            <Label>MITRE ATT&CK Mappings</Label>
                            <p className="text-xs text-muted-foreground">
                                Add one or more MITRE ATT&CK tactics &amp; techniques. Leave empty for auto-suggest.
                            </p>

                            {/* Existing mappings list */}
                            {form.mitre_mappings.length > 0 && (
                                <div className="space-y-1.5">
                                    {form.mitre_mappings.map((m, i) => (
                                        <div key={i} className="flex items-center gap-2 rounded-md border border-white/10 bg-white/[0.03] px-3 py-1.5">
                                            <Badge variant="outline" className={`text-[10px] ${tacticColors[m.tactic?.toLowerCase()] || ''}`}>
                                                {m.tactic}
                                            </Badge>
                                            <span className="text-xs font-mono text-muted-foreground">{m.technique}</span>
                                            {m.name && <span className="text-xs text-muted-foreground truncate">— {m.name}</span>}
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="sm"
                                                className="ml-auto h-6 w-6 p-0 text-destructive hover:text-destructive"
                                                onClick={() => handleRemoveMapping(i)}
                                            >
                                                <Trash2 className="h-3 w-3" />
                                            </Button>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Add mapping row */}
                            <div className="grid grid-cols-[1fr_1fr_auto] gap-2 items-end">
                                <div className="space-y-1">
                                    <Label className="text-xs">Tactic</Label>
                                    <Select value={mappingDraft.tactic} onValueChange={handleTacticChange}>
                                        <SelectTrigger><SelectValue placeholder="Select Tactic" /></SelectTrigger>
                                        <SelectContent side="top">
                                            {mitreFormData.tactics.map(t => (
                                                <SelectItem key={t.slug} value={t.slug}>{t.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-1">
                                    <Label className="text-xs">Technique</Label>
                                    <div className="relative">
                                        <Input
                                            value={techSearch || mappingDraft.technique}
                                            onChange={e => handleTechniqueInput(e.target.value)}
                                            placeholder="Search T1059 or name..."
                                            onFocus={() => setTechSearch(mappingDraft.technique)}
                                            onBlur={() => setTimeout(() => setTechSearch(''), 200)}
                                        />
                                        {techSearch && filteredTechniques.length > 0 && (
                                            <div className="absolute z-50 bottom-full mb-1 left-0 right-0 max-h-48 overflow-y-auto rounded-md border border-white/10 bg-background/95 backdrop-blur-sm shadow-lg">
                                                {filteredTechniques.map(t => (
                                                    <button
                                                        key={t.id}
                                                        type="button"
                                                        className="w-full text-left px-3 py-1.5 text-xs hover:bg-white/10 cursor-pointer flex items-center gap-2"
                                                        onMouseDown={e => { e.preventDefault(); handleTechniqueSelect(t.id) }}
                                                    >
                                                        <span className="font-mono text-muted-foreground">{t.id}</span>
                                                        <span className="truncate">{t.name}</span>
                                                    </button>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </div>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="h-9"
                                    onClick={handleAddMapping}
                                    disabled={!mappingDraft.tactic && !mappingDraft.technique}
                                >
                                    <Plus className="h-3.5 w-3.5" />
                                </Button>
                            </div>
                        </div>
                    </DialogBody>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowAddModal(false)}>Cancel</Button>
                        <Button onClick={handleAddEvent} loading={isSubmitting}>Save</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

        </div>
    )
}
