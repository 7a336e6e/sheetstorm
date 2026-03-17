"use client"

import { useEffect, useState, useCallback, useMemo, memo, useRef } from 'react'
import {
    ReactFlow,
    Background,
    BackgroundVariant,
    useNodesState,
    useEdgesState,
    type Node,
    type Edge,
    type NodeTypes,
    Panel,
    useReactFlow,
    ReactFlowProvider,
    getNodesBounds,
    getViewportForBounds,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { Card, CardContent } from '@/components/ui/card'
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
import api from '@/lib/api'
import { formatDateTime } from '@/lib/utils'
import type { TimelineEvent, CompromisedHost } from '@/types'
import { useTheme } from '@/components/providers/theme-provider'
import { useToast } from '@/components/ui/use-toast'
import {
    ArrowLeftRight,
    ArrowUpDown,
    Clock,
    Download,
    Eye,
    Maximize2,
    Plus,
    Server,
    Star,
    ZoomIn,
    ZoomOut,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { TimelineEventNode, type TimelineNodeData } from './TimelineEventNode'

// ─── Types ───────────────────────────────────────────────────────────────────

type Orientation = 'horizontal' | 'vertical'

interface IOCVisualTimelineProps {
    incidentId: string
}

// ─── Constants ──────────────────────────────────────────────────────────────

const NODE_WIDTH = 240
const NODE_MIN_HEIGHT = 160  // enforced via min-h on the card
const CARD_SPACING = 320    // distance between cards along the main axis
const STEM_GAP = 28         // gap between card edge and axis line
const AXIS_WIDTH = 2

// Axis line node — rendered inside the viewport so it appears in PNG exports
const AxisLineNode = memo(function AxisLineNode({ data }: any) {
    return (
        <div style={{ width: data.lineWidth, height: data.lineHeight }} className="pointer-events-none">
            <div
                className="w-full h-full"
                style={{
                    background: data.orientation === 'horizontal'
                        ? 'linear-gradient(to right, rgba(6,182,212,0.6), rgba(6,182,212,0.4), rgba(6,182,212,0.6))'
                        : 'linear-gradient(to bottom, rgba(6,182,212,0.6), rgba(6,182,212,0.4), rgba(6,182,212,0.6))',
                }}
            />
        </div>
    )
})

const nodeTypes: NodeTypes = {
    timelineEvent: TimelineEventNode,
    axisLine: AxisLineNode as any,
}

// ─── Layout Logic ────────────────────────────────────────────────────────────

function buildTimelineGraph(
    events: TimelineEvent[],
    orientation: Orientation,
): { nodes: Node[]; edges: Edge[] } {
    const nodes: Node[] = []
    const edges: Edge[] = []

    if (events.length === 0) return { nodes, edges }

    events.forEach((event, i) => {
        // Alternate cards above/below (horizontal) or left/right (vertical) the axis
        let x: number
        let y: number

        if (orientation === 'horizontal') {
            x = i * CARD_SPACING
            // Position card edge exactly STEM_GAP from the axis (y=0)
            y = i % 2 === 0
                ? -(NODE_MIN_HEIGHT + STEM_GAP)  // above: card bottom at -STEM_GAP
                : STEM_GAP                        // below: card top at +STEM_GAP
        } else {
            // Position card edge exactly STEM_GAP from the axis (x=0)
            x = i % 2 === 0
                ? -(NODE_WIDTH + STEM_GAP)         // left: card right edge at -STEM_GAP
                : STEM_GAP                         // right: card left edge at +STEM_GAP
            y = i * CARD_SPACING
        }

        nodes.push({
            id: event.id,
            type: 'timelineEvent',
            position: { x, y },
            data: {
                activity: event.activity,
                timestamp: event.timestamp,
                hostname: event.host?.hostname || event.hostname,
                hostIp: event.host?.ip_address,
                mitreTactic: event.mitre_tactic,
                mitreTechnique: event.mitre_technique,
                killChainPhase: event.kill_chain_phase,
                source: event.source,
                isKeyEvent: event.is_key_event,
                isIoc: event.is_ioc,
                index: i,
                total: events.length,
                orientation,
                stemGap: STEM_GAP,
            },
        })

        // Connect sequential events
        if (i > 0) {
            edges.push({
                id: `e-${events[i - 1].id}-${event.id}`,
                source: events[i - 1].id,
                target: event.id,
                type: 'default',
                style: { stroke: 'transparent', strokeWidth: 0 },
                animated: false,
            })
        }
    })

    // Add axis line node (lives inside viewport → included in PNG export)
    const len = events.length
    if (orientation === 'horizontal') {
        const firstCenter = NODE_WIDTH / 2
        const lastCenter = (len - 1) * CARD_SPACING + NODE_WIDTH / 2
        nodes.push({
            id: 'axis-line',
            type: 'axisLine',
            position: { x: firstCenter - 40, y: -AXIS_WIDTH / 2 },
            data: { orientation, lineWidth: lastCenter - firstCenter + 80, lineHeight: AXIS_WIDTH },
            selectable: false,
            draggable: false,
            zIndex: -1,
        } as any)
    } else {
        const firstCenter = NODE_MIN_HEIGHT / 2
        const lastCenter = (len - 1) * CARD_SPACING + NODE_MIN_HEIGHT / 2
        nodes.push({
            id: 'axis-line',
            type: 'axisLine',
            position: { x: -AXIS_WIDTH / 2, y: firstCenter - 40 },
            data: { orientation, lineWidth: AXIS_WIDTH, lineHeight: lastCenter - firstCenter + 80 },
            selectable: false,
            draggable: false,
            zIndex: -1,
        } as any)
    }

    return { nodes, edges }
}

// ─── Inner component (needs ReactFlowProvider) ──────────────────────────────

function TimelineInner({ incidentId }: IOCVisualTimelineProps) {
    const { resolvedTheme } = useTheme()
    const { toast } = useToast()
    const { fitView, zoomIn, zoomOut, getNodes } = useReactFlow()

    const [allEvents, setAllEvents] = useState<TimelineEvent[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [filterMode, setFilterMode] = useState<'pinned' | 'all'>('pinned')
    const [orientation, setOrientation] = useState<Orientation>('horizontal')
    const [hosts, setHosts] = useState<CompromisedHost[]>([])

    // Add event dialog
    const [showAddModal, setShowAddModal] = useState(false)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [form, setForm] = useState({
        timestamp: '',
        activity: '',
        source: '',
        host_id: '',
        mitre_tactic: '',
        mitre_technique: '',
    })

    const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])

    // ─── Data loading ────────────────────────────────────────────────────

    useEffect(() => {
        if (incidentId) loadData()
    }, [incidentId])

    const loadData = async () => {
        setIsLoading(true)
        try {
            const [eventsRes, hostsRes] = await Promise.all([
                api.get<{ items: TimelineEvent[] }>(`/incidents/${incidentId}/timeline`),
                api.get<{ items: CompromisedHost[] }>(`/incidents/${incidentId}/hosts`),
            ])
            const sorted = (eventsRes.items || []).sort(
                (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
            )
            setAllEvents(sorted)
            setHosts(hostsRes.items || [])
        } catch (error) {
            console.error('Failed to load timeline:', error)
        } finally {
            setIsLoading(false)
        }
    }

    const events = useMemo(
        () => filterMode === 'pinned' ? allEvents.filter(e => e.is_key_event) : allEvents,
        [allEvents, filterMode]
    )
    const pinnedCount = useMemo(() => allEvents.filter(e => e.is_key_event).length, [allEvents])

    // ─── Build graph when events or orientation change ───────────────────

    useEffect(() => {
        const { nodes: n, edges: e } = buildTimelineGraph(events, orientation)
        setNodes(n)
        setEdges(e)
        // fit view after DOM paints the new nodes
        setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 100)
    }, [events, orientation, setNodes, setEdges, fitView])

    // ─── Add event handler ──────────────────────────────────────────────

    const handleAddEvent = async () => {
        if (!form.timestamp || !form.activity) return
        setIsSubmitting(true)
        try {
            await api.post(`/incidents/${incidentId}/timeline`, {
                timestamp: form.timestamp,
                activity: form.activity,
                source: form.source || null,
                host_id: form.host_id || null,
                mitre_tactic: form.mitre_tactic || null,
                mitre_technique: form.mitre_technique || null,
            })
            setShowAddModal(false)
            setForm({ timestamp: '', activity: '', source: '', host_id: '', mitre_tactic: '', mitre_technique: '' })
            loadData()
        } catch (error) {
            console.error('Failed to add event:', error)
        } finally {
            setIsSubmitting(false)
        }
    }

    // ─── Export PNG ──────────────────────────────────────────────────────

    const handleExportPng = useCallback(() => {
        const currentNodes = getNodes()
        if (currentNodes.length === 0) {
            toast({ title: 'Export Failed', description: 'No events to export', variant: 'destructive' })
            return
        }

        const viewportEl = document.querySelector('.react-flow__viewport') as HTMLElement
        if (!viewportEl) return

        import('html-to-image' as string).then((mod: { toPng: (el: HTMLElement, opts: Record<string, unknown>) => Promise<string> }) => {
            const nodesBounds = getNodesBounds(currentNodes)
            const padding = 60
            const imageWidth = nodesBounds.width + padding * 2
            const imageHeight = nodesBounds.height + padding * 2

            const vp = getViewportForBounds(
                nodesBounds,
                imageWidth,
                imageHeight,
                1, 1,
                padding,
            )

            mod.toPng(viewportEl, {
                backgroundColor: resolvedTheme === 'dark' ? '#0f172a' : '#ffffff',
                width: imageWidth,
                height: imageHeight,
                pixelRatio: 2,
                style: {
                    width: `${imageWidth}px`,
                    height: `${imageHeight}px`,
                    transform: `translate(${vp.x}px, ${vp.y}px) scale(${vp.zoom})`,
                    transformOrigin: 'top left',
                },
            }).then((dataUrl: string) => {
                const link = document.createElement('a')
                link.download = `timeline-${incidentId}.png`
                link.href = dataUrl
                link.click()
                toast({ title: 'Exported', description: 'Timeline exported as PNG' })
            }).catch(() => {
                toast({ title: 'Export Failed', description: 'Could not export timeline as PNG', variant: 'destructive' })
            })
        }).catch(() => {
            toast({ title: 'Export Unavailable', description: 'PNG export requires html-to-image package', variant: 'destructive' })
        })
    }, [incidentId, toast, getNodes, resolvedTheme])

    // ─── Toggle orientation ──────────────────────────────────────────────

    const toggleOrientation = useCallback(() => {
        setOrientation(prev => prev === 'horizontal' ? 'vertical' : 'horizontal')
    }, [])

    // ─── Loading state ───────────────────────────────────────────────────

    if (isLoading) {
        return (
            <div className="py-16 text-center text-sm text-muted-foreground animate-pulse">
                <Clock className="h-6 w-6 mx-auto mb-2 opacity-30" />
                Loading timeline...
            </div>
        )
    }

    // ─── Empty state ─────────────────────────────────────────────────────

    if (events.length === 0) {
        return (
            <div className="space-y-4">
                <ControlBar
                    filterMode={filterMode}
                    setFilterMode={setFilterMode}
                    pinnedCount={pinnedCount}
                    allCount={allEvents.length}
                    onAdd={() => setShowAddModal(true)}
                    orientation={orientation}
                    onToggleOrientation={toggleOrientation}
                    onExport={handleExportPng}
                    onFit={() => fitView({ padding: 0.15, duration: 300 })}
                    onZoomIn={() => zoomIn({ duration: 200 })}
                    onZoomOut={() => zoomOut({ duration: 200 })}
                    isEmpty
                />
                <div className="py-16 text-center border border-dashed border-black/10 dark:border-white/10 rounded-lg">
                    <Clock className="w-8 h-8 mx-auto text-muted-foreground/30 mb-3" />
                    <p className="text-sm font-medium text-foreground">
                        {filterMode === 'pinned' ? 'No Pinned Events' : 'No Timeline Events'}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                        {filterMode === 'pinned'
                            ? 'Pin events from the Events tab using the ★ icon to build your timeline.'
                            : 'Add events from the Events tab or click "Add Event" above.'}
                    </p>
                </div>
                <AddEventDialog
                    open={showAddModal}
                    onOpenChange={setShowAddModal}
                    form={form}
                    setForm={setForm}
                    hosts={hosts}
                    onSubmit={handleAddEvent}
                    isSubmitting={isSubmitting}
                />
            </div>
        )
    }

    // ─── Render ──────────────────────────────────────────────────────────

    return (
        <div className="space-y-4">
            <ControlBar
                filterMode={filterMode}
                setFilterMode={setFilterMode}
                pinnedCount={pinnedCount}
                allCount={allEvents.length}
                onAdd={() => setShowAddModal(true)}
                orientation={orientation}
                onToggleOrientation={toggleOrientation}
                onExport={handleExportPng}
                onFit={() => fitView({ padding: 0.15, duration: 300 })}
                onZoomIn={() => zoomIn({ duration: 200 })}
                onZoomOut={() => zoomOut({ duration: 200 })}
            />

            <div
                className="rounded-lg border border-black/10 dark:border-white/10 overflow-hidden"
                style={{ height: 'calc(100vh - 340px)', minHeight: 500 }}
            >
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    nodeTypes={nodeTypes}
                    fitView
                    minZoom={0.1}
                    maxZoom={2}
                    nodesDraggable={false}
                    nodesConnectable={false}
                    elementsSelectable={true}
                    panOnScroll
                    zoomOnScroll
                    proOptions={{ hideAttribution: true }}
                    className={resolvedTheme === 'dark' ? 'bg-slate-950' : 'bg-slate-50'}
                >
                    <Background
                        variant={BackgroundVariant.Dots}
                        gap={24}
                        size={1}
                        color={resolvedTheme === 'dark' ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.04)'}
                    />

                    {/* Info legend panel */}
                    <Panel position="bottom-left">
                        <div className="bg-card/90 backdrop-blur border border-black/10 dark:border-white/10 rounded-lg px-3 py-2 text-[10px] text-muted-foreground flex items-center gap-4">
                            <span className="flex items-center gap-1.5">
                                <Star className="h-3 w-3 text-amber-400 fill-amber-400" /> {pinnedCount} pinned
                            </span>
                            <span className="flex items-center gap-1.5">
                                <Clock className="h-3 w-3" /> {allEvents.length} total
                            </span>
                            {events.length > 0 && (
                                <>
                                    <span>First: {formatDateTime(events[0].timestamp)}</span>
                                    <span>Last: {formatDateTime(events[events.length - 1].timestamp)}</span>
                                </>
                            )}
                        </div>
                    </Panel>
                </ReactFlow>
            </div>

            <AddEventDialog
                open={showAddModal}
                onOpenChange={setShowAddModal}
                form={form}
                setForm={setForm}
                hosts={hosts}
                onSubmit={handleAddEvent}
                isSubmitting={isSubmitting}
            />
        </div>
    )
}

// ─── Control Bar ─────────────────────────────────────────────────────────────

function ControlBar({
    filterMode,
    setFilterMode,
    pinnedCount,
    allCount,
    onAdd,
    orientation,
    onToggleOrientation,
    onExport,
    onFit,
    onZoomIn,
    onZoomOut,
    isEmpty,
}: {
    filterMode: 'pinned' | 'all'
    setFilterMode: (m: 'pinned' | 'all') => void
    pinnedCount: number
    allCount: number
    onAdd: () => void
    orientation: Orientation
    onToggleOrientation: () => void
    onExport: () => void
    onFit: () => void
    onZoomIn: () => void
    onZoomOut: () => void
    isEmpty?: boolean
}) {
    return (
        <Card>
            <CardContent className="p-3">
                <div className="flex justify-between items-center gap-3">
                    {/* Left: filter tabs */}
                    <div className="flex items-center gap-2">
                        <Button
                            variant={filterMode === 'pinned' ? 'default' : 'outline'}
                            size="sm"
                            onClick={() => setFilterMode('pinned')}
                        >
                            <Star className="mr-1.5 h-3.5 w-3.5" /> Pinned ({pinnedCount})
                        </Button>
                        <Button
                            variant={filterMode === 'all' ? 'default' : 'outline'}
                            size="sm"
                            onClick={() => setFilterMode('all')}
                        >
                            <Eye className="mr-1.5 h-3.5 w-3.5" /> All ({allCount})
                        </Button>
                    </div>

                    {/* Right: toolbar */}
                    <div className="flex items-center gap-1">
                        {!isEmpty && (
                            <>
                                <Button
                                    variant="outline"
                                    size="icon"
                                    className="h-8 w-8"
                                    onClick={onToggleOrientation}
                                    title={`Switch to ${orientation === 'horizontal' ? 'vertical' : 'horizontal'} layout`}
                                >
                                    {orientation === 'horizontal'
                                        ? <ArrowUpDown className="h-3.5 w-3.5" />
                                        : <ArrowLeftRight className="h-3.5 w-3.5" />
                                    }
                                </Button>
                                <Button variant="outline" size="icon" className="h-8 w-8" onClick={onZoomIn} title="Zoom in">
                                    <ZoomIn className="h-3.5 w-3.5" />
                                </Button>
                                <Button variant="outline" size="icon" className="h-8 w-8" onClick={onZoomOut} title="Zoom out">
                                    <ZoomOut className="h-3.5 w-3.5" />
                                </Button>
                                <Button variant="outline" size="icon" className="h-8 w-8" onClick={onFit} title="Fit view">
                                    <Maximize2 className="h-3.5 w-3.5" />
                                </Button>
                                <div className="w-px h-5 bg-black/10 dark:bg-white/10 mx-1" />
                                <Button variant="outline" size="sm" onClick={onExport} title="Export timeline as PNG">
                                    <Download className="mr-1.5 h-3.5 w-3.5" /> Export PNG
                                </Button>
                            </>
                        )}
                        <Button onClick={onAdd} size="sm">
                            <Plus className="mr-1.5 h-3.5 w-3.5" /> Add Event
                        </Button>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}

// ─── Pinned Events Table (text format) ───────────────────────────────────────

const tacticColor: Record<string, string> = {
    'reconnaissance': 'text-blue-400',
    'resource development': 'text-blue-300',
    'initial access': 'text-amber-400',
    'initial-access': 'text-amber-400',
    'execution': 'text-orange-400',
    'persistence': 'text-rose-400',
    'privilege escalation': 'text-red-400',
    'privilege-escalation': 'text-red-400',
    'defense evasion': 'text-pink-400',
    'defense-evasion': 'text-pink-400',
    'credential access': 'text-yellow-400',
    'credential-access': 'text-yellow-400',
    'discovery': 'text-cyan-400',
    'lateral movement': 'text-emerald-400',
    'lateral-movement': 'text-emerald-400',
    'collection': 'text-violet-400',
    'command and control': 'text-purple-400',
    'command-and-control': 'text-purple-400',
    'exfiltration': 'text-red-300',
    'impact': 'text-red-500',
}

export function PinnedEventsTable({ events }: { events: TimelineEvent[] }) {
    const sorted = useMemo(
        () => [...events].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()),
        [events],
    )

    return (
        <Card>
            <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-3">
                    <Star className="h-4 w-4 text-amber-400 fill-amber-400" />
                    <h3 className="text-sm font-semibold text-foreground">Pinned Timeline Events</h3>
                    <Badge variant="outline" className="text-[10px] ml-1">{sorted.length}</Badge>
                </div>

                <div className="relative pl-5">
                    {/* Vertical timeline line */}
                    <div className="absolute left-[7px] top-1 bottom-1 w-px bg-cyan-500/30" />

                    <ol className="space-y-0.5">
                        {sorted.map((event) => (
                            <li key={event.id} className="relative group">
                                {/* Dot */}
                                <div className="absolute -left-[13px] top-[11px] w-2 h-2 rounded-full bg-cyan-500/80 ring-2 ring-background z-10 group-hover:bg-cyan-400 transition-colors" />

                                <div className="w-full text-left px-3 py-2 rounded-md hover:bg-white/[0.03] transition-colors">
                                    <div className="flex items-center gap-3 min-w-0">
                                        <span className="shrink-0 text-[11px] font-mono tabular-nums text-muted-foreground w-[130px]">
                                            {formatDateTime(event.timestamp)}
                                        </span>

                                        <span className="truncate text-sm text-foreground/90 flex-1 min-w-0">
                                            {event.activity}
                                        </span>

                                        {(event.host || event.hostname) && (
                                            <span className="hidden sm:flex items-center gap-1 shrink-0 text-xs text-muted-foreground">
                                                <Server className="h-3 w-3" />
                                                {event.host?.hostname || event.hostname}
                                                {event.host?.ip_address && (
                                                    <span className="text-muted-foreground/50">({event.host.ip_address})</span>
                                                )}
                                            </span>
                                        )}

                                        {event.source && (
                                            <span className="hidden lg:block shrink-0 text-[10px] text-muted-foreground/70">
                                                {event.source}
                                            </span>
                                        )}

                                        {event.mitre_tactic && (
                                            <Badge variant="outline" className={`shrink-0 text-[10px] px-1.5 py-0 border-white/10 ${tacticColor[event.mitre_tactic.toLowerCase()] || 'text-muted-foreground'}`}>
                                                {event.mitre_tactic}
                                            </Badge>
                                        )}

                                        {event.mitre_technique && (
                                            <span className="shrink-0 text-[10px] font-mono text-muted-foreground/70">
                                                {event.mitre_technique}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </li>
                        ))}
                    </ol>

                    {/* Summary footer */}
                    <div className="mt-3 pt-2 border-t border-white/5 flex items-center gap-4 text-[11px] text-muted-foreground/60">
                        <span className="flex items-center gap-1"><Star className="h-3 w-3 text-amber-400 fill-amber-400" /> {sorted.length} pinned event{sorted.length !== 1 ? 's' : ''}</span>
                        {sorted.length > 0 && (
                            <>
                                <span>First: {formatDateTime(sorted[0].timestamp)}</span>
                                <span>Last: {formatDateTime(sorted[sorted.length - 1].timestamp)}</span>
                            </>
                        )}
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}

// ─── Add Event Dialog ────────────────────────────────────────────────────────

function AddEventDialog({
    open,
    onOpenChange,
    form,
    setForm,
    hosts,
    onSubmit,
    isSubmitting,
}: {
    open: boolean
    onOpenChange: (o: boolean) => void
    form: { timestamp: string; activity: string; source: string; host_id: string; mitre_tactic: string; mitre_technique: string }
    setForm: (f: typeof form) => void
    hosts: CompromisedHost[]
    onSubmit: () => void
    isSubmitting: boolean
}) {
    const [tactics, setTactics] = useState<{ id: string; name: string; slug: string }[]>([])
    const [techByTactic, setTechByTactic] = useState<Record<string, { id: string; name: string }[]>>({})
    const [techToTactic, setTechToTactic] = useState<Record<string, string>>({})
    const [allTechniques, setAllTechniques] = useState<{ id: string; name: string }[]>([])
    const [techSearch, setTechSearch] = useState('')

    // Auto-suggest state
    const [suggestions, setSuggestions] = useState<{ technique: string; tactic: string; name: string; score: number }[]>([])
    const suggestTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    // Debounced auto-suggest when activity text changes
    const fetchSuggestions = useCallback((activity: string) => {
        if (suggestTimerRef.current) clearTimeout(suggestTimerRef.current)
        if (!activity || activity.length < 10) { setSuggestions([]); return }
        suggestTimerRef.current = setTimeout(() => {
            api.post<{ suggestions: typeof suggestions }>('/mitre/suggest', { activity, limit: 3 })
                .then(data => setSuggestions(data.suggestions || []))
                .catch(() => {})
        }, 400)
    }, [])

    useEffect(() => { return () => { if (suggestTimerRef.current) clearTimeout(suggestTimerRef.current) } }, [])

    // Fetch form data once on open
    useEffect(() => {
        if (!open || tactics.length > 0) return
        api.get<{
            tactics: { id: string; name: string; slug: string }[]
            technique_by_tactic: Record<string, { id: string; name: string }[]>
            technique_to_tactic: Record<string, string>
        }>('/knowledge-base/mitre-attack/form-data').then(data => {
            setTactics(data.tactics)
            setTechByTactic(data.technique_by_tactic)
            setTechToTactic(data.technique_to_tactic)
            // Flatten all techniques for search
            const all: { id: string; name: string }[] = []
            const seen = new Set<string>()
            for (const techs of Object.values(data.technique_by_tactic)) {
                for (const t of techs) {
                    if (!seen.has(t.id)) { seen.add(t.id); all.push(t) }
                }
            }
            all.sort((a, b) => a.id.localeCompare(b.id))
            setAllTechniques(all)
        }).catch(() => {})
    }, [open, tactics.length])

    // Techniques available for the selected tactic (or all if none selected)
    const availableTechniques = useMemo(() => {
        if (form.mitre_tactic && techByTactic[form.mitre_tactic]) {
            return techByTactic[form.mitre_tactic]
        }
        return allTechniques
    }, [form.mitre_tactic, techByTactic, allTechniques])

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
        const techs = techByTactic[slug] || []
        const currentTechInNewTactic = techs.some(t => t.id === form.mitre_technique)
        setForm({
            ...form,
            mitre_tactic: slug,
            mitre_technique: currentTechInNewTactic ? form.mitre_technique : '',
        })
        setTechSearch('')
    }

    // Handle technique selection — auto-select tactic
    const handleTechniqueSelect = (techId: string) => {
        const tacticSlug = techToTactic[techId]
        setForm({
            ...form,
            mitre_technique: techId,
            mitre_tactic: tacticSlug || form.mitre_tactic,
        })
        setTechSearch('')
    }

    // Handle manual technique ID input — auto-resolve tactic
    const handleTechniqueInput = (value: string) => {
        const upper = value.toUpperCase().trim()
        setTechSearch(value)
        const resolvedTactic = techToTactic[upper]
        setForm({
            ...form,
            mitre_technique: upper,
            mitre_tactic: resolvedTactic || form.mitre_tactic,
        })
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>Add Timeline Event</DialogTitle>
                </DialogHeader>
                <DialogBody className="space-y-4">
                    <div className="space-y-2">
                        <Label>Timestamp *</Label>
                        <Input
                            type="datetime-local"
                            value={form.timestamp}
                            onChange={e => setForm({ ...form, timestamp: e.target.value })}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Activity *</Label>
                        <Textarea
                            value={form.activity}
                            onChange={e => { setForm({ ...form, activity: e.target.value }); fetchSuggestions(e.target.value) }}
                        />
                        {suggestions.length > 0 && !form.mitre_technique && (
                            <div className="flex flex-wrap gap-1.5">
                                <span className="text-[10px] text-muted-foreground self-center">Suggested:</span>
                                {suggestions.map(s => (
                                    <button
                                        key={s.technique}
                                        type="button"
                                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-blue-500/10 border border-blue-500/20 text-blue-400 hover:bg-blue-500/20 cursor-pointer transition-colors"
                                        onClick={() => {
                                            handleTechniqueSelect(s.technique)
                                            setSuggestions([])
                                        }}
                                    >
                                        <span className="font-mono">{s.technique}</span>
                                        <span className="text-muted-foreground">{s.name}</span>
                                        <span className="text-blue-300/60">{Math.round(s.score * 100)}%</span>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    <div className="space-y-2">
                        <Label>Source</Label>
                        <Input
                            value={form.source}
                            onChange={e => setForm({ ...form, source: e.target.value })}
                            placeholder="e.g. Sysmon, EDR, Firewall..."
                        />
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
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label>MITRE Tactic</Label>
                            <Select value={form.mitre_tactic} onValueChange={handleTacticChange}>
                                <SelectTrigger><SelectValue placeholder="Select Tactic" /></SelectTrigger>
                                <SelectContent side="top">
                                    {tactics.map(t => (
                                        <SelectItem key={t.slug} value={t.slug}>{t.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Technique ID</Label>
                            <div className="relative">
                                <Input
                                    value={techSearch || form.mitre_technique}
                                    onChange={e => { handleTechniqueInput(e.target.value) }}
                                    placeholder="Search T1059 or name..."
                                    onFocus={() => setTechSearch(form.mitre_technique)}
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
                    </div>
                </DialogBody>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
                    <Button onClick={onSubmit} loading={isSubmitting}>Save</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

// ─── Wrapper with ReactFlowProvider ──────────────────────────────────────────

export function IOCVisualTimeline({ incidentId }: IOCVisualTimelineProps) {
    return (
        <ReactFlowProvider>
            <TimelineInner incidentId={incidentId} />
        </ReactFlowProvider>
    )
}
