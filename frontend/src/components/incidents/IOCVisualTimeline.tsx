"use client"

import { useEffect, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { SkeletonTableRow } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/utils'
import api from '@/lib/api'
import type { TimelineEvent } from '@/types'
import { Clock, AlertTriangle, CheckCircle2, Server, Tag } from 'lucide-react'

interface IOCVisualTimelineProps {
    incidentId: string
}

export function IOCVisualTimeline({ incidentId }: IOCVisualTimelineProps) {
    const [events, setEvents] = useState<TimelineEvent[]>([])
    const [isLoading, setIsLoading] = useState(true)

    useEffect(() => {
        if (incidentId) {
            loadData()
        }
    }, [incidentId])

    const loadData = async () => {
        setIsLoading(true)
        try {
            const res = await api.get<{ items: TimelineEvent[] }>(`/incidents/${incidentId}/timeline`)
            // Filter for IOCs only
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
        return <div className="p-8 text-center text-muted-foreground">Loading timeline...</div>
    }

    if (events.length === 0) {
        return (
            <div className="p-12 text-center border-2 border-dashed border-white/10 rounded-xl">
                <Clock className="w-12 h-12 mx-auto text-muted-foreground/30 mb-4" />
                <h3 className="text-lg font-medium text-foreground">No IOC Events</h3>
                <p className="text-muted-foreground mt-2">
                    Mark events as Indicators of Compromise in the Events tab to see them here.
                </p>
            </div>
        )
    }

    return (
        <div className="relative space-y-8 pl-8 before:absolute before:left-[15px] before:top-4 before:bottom-4 before:w-0.5 before:bg-gradient-to-b before:from-cyan-500 before:to-transparent">
            {events.map((event, index) => (
                <div key={event.id} className="relative group">
                    {/* Dot */}
                    <div className="absolute -left-[23px] top-1.5 w-4 h-4 rounded-full bg-cyan-950 border border-cyan-500 shadow-[0_0_10px_rgba(6,182,212,0.5)] z-10" />

                    <Card className="ml-4 transition-all hover:bg-white/5 border-l-4 border-l-red-500">
                        <CardContent className="p-4">
                            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                                <div className="space-y-1">
                                    <Badge variant="outline" className="mb-2 font-mono text-xs">
                                        {formatDateTime(event.timestamp)}
                                    </Badge>
                                    <h4 className="font-semibold text-lg text-foreground">{event.activity}</h4>
                                    {event.host && (
                                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                            <Server className="h-3 w-3" />
                                            {event.host.hostname}
                                        </div>
                                    )}
                                </div>

                                <div className="flex flex-row lg:flex-col items-end gap-2">
                                    {event.mitre_tactic && (
                                        <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/30">
                                            {event.mitre_tactic}
                                        </Badge>
                                    )}
                                    {event.mitre_technique && (
                                        <span className="text-xs font-mono text-muted-foreground">
                                            {event.mitre_technique}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            ))}
        </div>
    )
}
