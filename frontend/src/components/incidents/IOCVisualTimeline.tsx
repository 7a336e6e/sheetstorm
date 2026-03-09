"use client"

import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { formatDateTime } from '@/lib/utils'
import api from '@/lib/api'
import type { TimelineEvent } from '@/types'
import { Clock, Server, Shield, ChevronDown, ChevronUp } from 'lucide-react'

interface IOCVisualTimelineProps {
    incidentId: string
}

const tacticColor: Record<string, string> = {
    'reconnaissance': 'text-blue-400',
    'resource development': 'text-blue-300',
    'initial access': 'text-amber-400',
    'execution': 'text-orange-400',
    'persistence': 'text-rose-400',
    'privilege escalation': 'text-red-400',
    'defense evasion': 'text-pink-400',
    'credential access': 'text-yellow-400',
    'discovery': 'text-cyan-400',
    'lateral movement': 'text-emerald-400',
    'collection': 'text-violet-400',
    'command and control': 'text-purple-400',
    'exfiltration': 'text-red-300',
    'impact': 'text-red-500',
}

function getTacticColor(tactic: string | undefined | null): string {
    if (!tactic) return 'text-muted-foreground'
    return tacticColor[tactic.toLowerCase()] ?? 'text-muted-foreground'
}

export function IOCVisualTimeline({ incidentId }: IOCVisualTimelineProps) {
    const [events, setEvents] = useState<TimelineEvent[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [expanded, setExpanded] = useState<string | null>(null)

    useEffect(() => {
        if (incidentId) {
            loadData()
        }
    }, [incidentId])

    const loadData = async () => {
        setIsLoading(true)
        try {
            const res = await api.get<{ items: TimelineEvent[] }>(`/incidents/${incidentId}/timeline`)
            const iocEvents = (res.items || []).filter(e => e.is_ioc).sort((a, b) =>
                new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
            )
            setEvents(iocEvents)
        } catch (error) {
            console.error('Failed to load events:', error)
        } finally {
            setIsLoading(false)
        }
    }

    if (isLoading) {
        return <div className="py-6 text-center text-sm text-muted-foreground animate-pulse">Loading timeline...</div>
    }

    if (events.length === 0) {
        return (
            <div className="py-10 text-center border border-dashed border-white/10 rounded-lg">
                <Clock className="w-8 h-8 mx-auto text-muted-foreground/30 mb-3" />
                <p className="text-sm font-medium text-foreground">No IOC Events</p>
                <p className="text-xs text-muted-foreground mt-1">
                    Mark events as IOCs in the Events tab to populate this timeline.
                </p>
            </div>
        )
    }

    return (
        <div className="relative pl-5">
            {/* Thin vertical line */}
            <div className="absolute left-[7px] top-1 bottom-1 w-px bg-white/10" />

            <ol className="space-y-0.5">
                {events.map((event) => {
                    const isOpen = expanded === event.id
                    return (
                        <li key={event.id} className="relative group">
                            {/* Dot */}
                            <div className="absolute -left-[13px] top-[11px] w-2 h-2 rounded-full bg-cyan-500/80 ring-2 ring-background z-10 group-hover:bg-cyan-400 transition-colors" />

                            <button
                                onClick={() => setExpanded(isOpen ? null : event.id)}
                                className="w-full text-left px-3 py-2 rounded-md hover:bg-white/[0.03] transition-colors"
                            >
                                {/* Main row */}
                                <div className="flex items-center gap-3 min-w-0">
                                    <span className="shrink-0 text-[11px] font-mono tabular-nums text-muted-foreground w-[130px]">
                                        {formatDateTime(event.timestamp)}
                                    </span>

                                    <span className="truncate text-sm text-foreground/90 flex-1 min-w-0">
                                        {event.activity}
                                    </span>

                                    {event.host && (
                                        <span className="hidden sm:flex items-center gap-1 shrink-0 text-xs text-muted-foreground">
                                            <Server className="h-3 w-3" />
                                            {event.host.hostname}
                                        </span>
                                    )}

                                    {event.mitre_tactic && (
                                        <Badge variant="outline" className={`shrink-0 text-[10px] px-1.5 py-0 border-white/10 ${getTacticColor(event.mitre_tactic)}`}>
                                            {event.mitre_tactic}
                                        </Badge>
                                    )}

                                    {event.mitre_technique && (
                                        <span className="shrink-0 text-[10px] font-mono text-muted-foreground/70">
                                            {event.mitre_technique}
                                        </span>
                                    )}

                                    {isOpen
                                        ? <ChevronUp className="h-3 w-3 shrink-0 text-muted-foreground/50" />
                                        : <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground/30" />
                                    }
                                </div>
                            </button>

                            {/* Expanded detail panel */}
                            {isOpen && (
                                <div className="ml-[142px] mr-3 mb-2 px-3 py-2 rounded border border-white/5 bg-white/[0.02] text-xs space-y-1">
                                    {event.description && (
                                        <p className="text-muted-foreground leading-relaxed">{event.description}</p>
                                    )}
                                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground/80">
                                        {event.host && (
                                            <span><strong className="text-foreground/70">Host:</strong> {event.host.hostname} {event.host.ip_address && `(${event.host.ip_address})`}</span>
                                        )}
                                        {event.mitre_tactic && (
                                            <span><strong className="text-foreground/70">Tactic:</strong> {event.mitre_tactic}</span>
                                        )}
                                        {event.mitre_technique && (
                                            <span><strong className="text-foreground/70">Technique:</strong> {event.mitre_technique}</span>
                                        )}
                                        {event.source && (
                                            <span><strong className="text-foreground/70">Source:</strong> {event.source}</span>
                                        )}
                                    </div>
                                </div>
                            )}
                        </li>
                    )
                })}
            </ol>

            {/* Summary footer */}
            <div className="mt-4 pt-3 border-t border-white/5 flex items-center gap-4 text-[11px] text-muted-foreground/60">
                <span className="flex items-center gap-1"><Shield className="h-3 w-3" /> {events.length} IOC{events.length !== 1 ? 's' : ''}</span>
                {events.length > 0 && (
                    <>
                        <span>First: {formatDateTime(events[0].timestamp)}</span>
                        <span>Last: {formatDateTime(events[events.length - 1].timestamp)}</span>
                    </>
                )}
            </div>
        </div>
    )
}
