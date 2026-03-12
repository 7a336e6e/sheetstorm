"use client"

import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { Badge } from '@/components/ui/badge'
import { Server, Clock, Star } from 'lucide-react'
import { formatDateTime } from '@/lib/utils'

// Tactic → color mapping (hex for inline SVG / node styles)
const tacticHex: Record<string, string> = {
    'reconnaissance': '#60a5fa',
    'resource development': '#93c5fd',
    'initial access': '#fbbf24',
    'initial-access': '#fbbf24',
    'execution': '#fb923c',
    'persistence': '#fb7185',
    'privilege escalation': '#f87171',
    'privilege-escalation': '#f87171',
    'defense evasion': '#f472b6',
    'defense-evasion': '#f472b6',
    'credential access': '#facc15',
    'credential-access': '#facc15',
    'discovery': '#22d3ee',
    'lateral movement': '#34d399',
    'lateral-movement': '#34d399',
    'collection': '#a78bfa',
    'command and control': '#a855f7',
    'command-and-control': '#a855f7',
    'exfiltration': '#fca5a5',
    'impact': '#ef4444',
}

const tacticTailwind: Record<string, string> = {
    'reconnaissance': 'text-blue-400 border-blue-400/30 bg-blue-400/10',
    'resource development': 'text-blue-300 border-blue-300/30 bg-blue-300/10',
    'initial access': 'text-amber-400 border-amber-400/30 bg-amber-400/10',
    'initial-access': 'text-amber-400 border-amber-400/30 bg-amber-400/10',
    'execution': 'text-orange-400 border-orange-400/30 bg-orange-400/10',
    'persistence': 'text-rose-400 border-rose-400/30 bg-rose-400/10',
    'privilege escalation': 'text-red-400 border-red-400/30 bg-red-400/10',
    'privilege-escalation': 'text-red-400 border-red-400/30 bg-red-400/10',
    'defense evasion': 'text-pink-400 border-pink-400/30 bg-pink-400/10',
    'defense-evasion': 'text-pink-400 border-pink-400/30 bg-pink-400/10',
    'credential access': 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10',
    'credential-access': 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10',
    'discovery': 'text-cyan-400 border-cyan-400/30 bg-cyan-400/10',
    'lateral movement': 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10',
    'lateral-movement': 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10',
    'collection': 'text-violet-400 border-violet-400/30 bg-violet-400/10',
    'command and control': 'text-purple-400 border-purple-400/30 bg-purple-400/10',
    'command-and-control': 'text-purple-400 border-purple-400/30 bg-purple-400/10',
    'exfiltration': 'text-red-300 border-red-300/30 bg-red-300/10',
    'impact': 'text-red-500 border-red-500/30 bg-red-500/10',
}

export interface TimelineNodeData {
    activity: string
    timestamp: string
    hostname?: string
    hostIp?: string
    mitreTactic?: string
    mitreTechnique?: string
    killChainPhase?: string
    source?: string
    isKeyEvent: boolean
    isIoc: boolean
    index: number
    total: number
    orientation: 'horizontal' | 'vertical'
    stemGap?: number
    [key: string]: unknown
}

export type TimelineNode = Node<TimelineNodeData, 'timelineEvent'>

function getTacticAccent(tactic: string | undefined): string {
    if (!tactic) return '#64748b'
    return tacticHex[tactic.toLowerCase()] ?? '#64748b'
}

function getTacticClasses(tactic: string | undefined): string {
    if (!tactic) return 'text-muted-foreground border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5'
    return tacticTailwind[tactic.toLowerCase()] ?? 'text-muted-foreground border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5'
}

export const TimelineEventNode = memo(function TimelineEventNode({ data, selected }: NodeProps<TimelineNode>) {
    const accent = getTacticAccent(data.mitreTactic)
    const isHorizontal = data.orientation === 'horizontal'
    const stemGap = (data.stemGap as number) || 28

    return (
        <div className="relative">
            {/* Handles for edges */}
            {isHorizontal ? (
                <>
                    <Handle type="target" position={Position.Left} className="!w-0 !h-0 !border-0 !bg-transparent !min-w-0 !min-h-0" />
                    <Handle type="source" position={Position.Right} className="!w-0 !h-0 !border-0 !bg-transparent !min-w-0 !min-h-0" />
                </>
            ) : (
                <>
                    <Handle type="target" position={Position.Top} className="!w-0 !h-0 !border-0 !bg-transparent !min-w-0 !min-h-0" />
                    <Handle type="source" position={Position.Bottom} className="!w-0 !h-0 !border-0 !bg-transparent !min-w-0 !min-h-0" />
                </>
            )}

            {/* Connector stem to axis */}
            {isHorizontal ? (
                <div
                    className="absolute left-1/2 -translate-x-1/2 w-px"
                    style={{
                        backgroundColor: accent,
                        opacity: 0.4,
                        ...(data.index % 2 === 0
                            ? { bottom: -stemGap, height: stemGap }
                            : { top: -stemGap, height: stemGap }
                        ),
                    }}
                />
            ) : (
                <div
                    className="absolute top-1/2 -translate-y-1/2 h-px"
                    style={{
                        backgroundColor: accent,
                        opacity: 0.4,
                        ...(data.index % 2 === 0
                            ? { right: -stemGap, width: stemGap }
                            : { left: -stemGap, width: stemGap }
                        ),
                    }}
                />
            )}

            {/* Dot on stem end (sits on axis) */}
            {isHorizontal ? (
                <div
                    className="absolute left-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full ring-2 ring-background z-10"
                    style={{
                        backgroundColor: accent,
                        ...(data.index % 2 === 0
                            ? { bottom: -(stemGap + 5) }
                            : { top: -(stemGap + 5) }
                        ),
                    }}
                />
            ) : (
                <div
                    className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full ring-2 ring-background z-10"
                    style={{
                        backgroundColor: accent,
                        ...(data.index % 2 === 0
                            ? { right: -(stemGap + 5) }
                            : { left: -(stemGap + 5) }
                        ),
                    }}
                />
            )}

            {/* Event card */}
            <div
                className={`
                    w-[240px] h-[160px] overflow-hidden rounded-lg shadow-lg border transition-all duration-200
                    bg-card text-card-foreground
                    ${selected ? 'border-cyan-500/50 shadow-cyan-500/10 ring-1 ring-cyan-500/20' : 'border-black/10 dark:border-white/10'}
                    hover:shadow-xl hover:border-black/20 dark:hover:border-white/20
                `}
            >
                {/* Accent strip */}
                <div className="h-[3px] rounded-t-lg" style={{ background: `linear-gradient(90deg, ${accent}, ${accent}88)` }} />

                <div className="p-3 space-y-2">
                    {/* Timestamp row */}
                    <div className="flex items-center justify-between gap-2">
                        <span className="text-[10px] font-mono tabular-nums text-muted-foreground flex items-center gap-1">
                            <Clock className="h-2.5 w-2.5" />
                            {formatDateTime(data.timestamp)}
                        </span>
                        {data.isKeyEvent && (
                            <Star className="h-3 w-3 text-amber-400 fill-amber-400 shrink-0" />
                        )}
                    </div>

                    {/* Activity */}
                    <p className="text-xs leading-relaxed text-foreground/90 line-clamp-3">
                        {data.activity}
                    </p>

                    {/* Host */}
                    {data.hostname && (
                        <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                            <Server className="h-2.5 w-2.5 shrink-0" />
                            <span className="truncate">{data.hostname}</span>
                            {data.hostIp && (
                                <span className="text-muted-foreground/50">({data.hostIp})</span>
                            )}
                        </div>
                    )}

                    {/* MITRE tags */}
                    {(data.mitreTactic || data.mitreTechnique) && (
                        <div className="flex flex-wrap items-center gap-1 pt-0.5">
                            {data.mitreTactic && (
                                <Badge variant="outline" className={`text-[9px] px-1.5 py-0 ${getTacticClasses(data.mitreTactic)}`}>
                                    {data.mitreTactic}
                                </Badge>
                            )}
                            {data.mitreTechnique && (
                                <span className="text-[9px] font-mono text-muted-foreground/60">
                                    {data.mitreTechnique}
                                </span>
                            )}
                        </div>
                    )}

                    {/* Kill chain / source metadata */}
                    {(data.killChainPhase || data.source) && (
                        <div className="flex flex-wrap gap-1 text-[9px] text-muted-foreground/50 pt-0.5 border-t border-black/5 dark:border-white/5">
                            {data.killChainPhase && <span>Phase: {data.killChainPhase}</span>}
                            {data.source && <span>Source: {data.source}</span>}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
})
