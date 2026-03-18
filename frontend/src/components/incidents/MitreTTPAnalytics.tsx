"use client"

import { useMemo, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Shield, Target, Crosshair, ChevronDown, Clock, Server } from 'lucide-react'
import type { TimelineEvent } from '@/types'

// Tactic ordering per MITRE ATT&CK kill chain
const TACTIC_ORDER = [
  'reconnaissance',
  'resource-development', 'resource development',
  'initial-access', 'initial access',
  'execution',
  'persistence',
  'privilege-escalation', 'privilege escalation',
  'defense-evasion', 'defense evasion',
  'credential-access', 'credential access',
  'discovery',
  'lateral-movement', 'lateral movement',
  'collection',
  'command-and-control', 'command and control',
  'exfiltration',
  'impact',
]

const tacticColors: Record<string, { bg: string; text: string; bar: string }> = {
  'reconnaissance': { bg: 'bg-blue-500/10', text: 'text-blue-400', bar: 'bg-blue-500' },
  'resource-development': { bg: 'bg-blue-400/10', text: 'text-blue-300', bar: 'bg-blue-400' },
  'resource development': { bg: 'bg-blue-400/10', text: 'text-blue-300', bar: 'bg-blue-400' },
  'initial-access': { bg: 'bg-amber-500/10', text: 'text-amber-400', bar: 'bg-amber-500' },
  'initial access': { bg: 'bg-amber-500/10', text: 'text-amber-400', bar: 'bg-amber-500' },
  'execution': { bg: 'bg-orange-500/10', text: 'text-orange-400', bar: 'bg-orange-500' },
  'persistence': { bg: 'bg-rose-500/10', text: 'text-rose-400', bar: 'bg-rose-500' },
  'privilege-escalation': { bg: 'bg-red-500/10', text: 'text-red-400', bar: 'bg-red-500' },
  'privilege escalation': { bg: 'bg-red-500/10', text: 'text-red-400', bar: 'bg-red-500' },
  'defense-evasion': { bg: 'bg-pink-500/10', text: 'text-pink-400', bar: 'bg-pink-500' },
  'defense evasion': { bg: 'bg-pink-500/10', text: 'text-pink-400', bar: 'bg-pink-500' },
  'credential-access': { bg: 'bg-yellow-500/10', text: 'text-yellow-400', bar: 'bg-yellow-500' },
  'credential access': { bg: 'bg-yellow-500/10', text: 'text-yellow-400', bar: 'bg-yellow-500' },
  'discovery': { bg: 'bg-cyan-500/10', text: 'text-cyan-400', bar: 'bg-cyan-500' },
  'lateral-movement': { bg: 'bg-emerald-500/10', text: 'text-emerald-400', bar: 'bg-emerald-500' },
  'lateral movement': { bg: 'bg-emerald-500/10', text: 'text-emerald-400', bar: 'bg-emerald-500' },
  'collection': { bg: 'bg-violet-500/10', text: 'text-violet-400', bar: 'bg-violet-500' },
  'command-and-control': { bg: 'bg-purple-500/10', text: 'text-purple-400', bar: 'bg-purple-500' },
  'command and control': { bg: 'bg-purple-500/10', text: 'text-purple-400', bar: 'bg-purple-500' },
  'exfiltration': { bg: 'bg-red-400/10', text: 'text-red-300', bar: 'bg-red-400' },
  'impact': { bg: 'bg-red-600/10', text: 'text-red-500', bar: 'bg-red-600' },
}

const defaultTacticColor = { bg: 'bg-gray-500/10', text: 'text-gray-400', bar: 'bg-gray-500' }

function getTacticIndex(tactic: string): number {
  const lower = tactic.toLowerCase()
  const idx = TACTIC_ORDER.indexOf(lower)
  return idx >= 0 ? idx : 999
}

function normalizeTacticLabel(tactic: string): string {
  return tactic.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

interface MitreTTPAnalyticsProps {
  events: TimelineEvent[]
  compact?: boolean
  title?: string
  description?: string
}

export function MitreTTPAnalytics({ events, compact = false, title = 'MITRE ATT&CK Coverage', description }: MitreTTPAnalyticsProps) {
  const [expandedTactic, setExpandedTactic] = useState<string | null>(null)

  const analytics = useMemo(() => {
    const tacticsMap: Record<string, { count: number; techniques: Record<string, number>; events: TimelineEvent[] }> = {}
    let totalMapped = 0

    for (const event of events) {
      // Collect mappings: prefer mitre_mappings array, fall back to legacy fields
      const mappings = event.mitre_mappings?.length
        ? event.mitre_mappings
        : event.mitre_tactic
          ? [{ tactic: event.mitre_tactic, technique: event.mitre_technique || '', name: '' }]
          : []

      if (mappings.length > 0) {
        totalMapped++
        for (const m of mappings) {
          if (!m.tactic) continue
          const tacticKey = m.tactic.toLowerCase()
          if (!tacticsMap[tacticKey]) {
            tacticsMap[tacticKey] = { count: 0, techniques: {}, events: [] }
          }
          tacticsMap[tacticKey].count++
          tacticsMap[tacticKey].events.push(event)

          if (m.technique) {
            const tech = m.technique.toUpperCase()
            tacticsMap[tacticKey].techniques[tech] = (tacticsMap[tacticKey].techniques[tech] || 0) + 1
          }
        }
      }
    }

    // Sort by kill chain order
    const sortedTactics: [string, { count: number; techniques: Record<string, number>; events: TimelineEvent[] }][] = Object.entries(tacticsMap)
      .sort(([a], [b]) => getTacticIndex(a) - getTacticIndex(b))

    const maxCount = Math.max(...Object.values(tacticsMap).map(t => t.count), 1)

    // Unique techniques
    const allTechniques = new Set<string>()
    for (const t of Object.values(tacticsMap)) {
      for (const tech of Object.keys(t.techniques)) {
        allTechniques.add(tech)
      }
    }

    return {
      sortedTactics,
      maxCount,
      totalMapped,
      totalEvents: events.length,
      uniqueTactics: Object.keys(tacticsMap).length,
      uniqueTechniques: allTechniques.size,
      allTechniqueIds: Array.from(allTechniques),
    }
  }, [events])

  if (analytics.totalMapped === 0) {
    return null
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className={compact ? 'text-sm font-medium' : 'text-lg'}>
              <div className="flex items-center gap-2">
                <Target className="h-4 w-4 text-red-400" />
                {title}
              </div>
            </CardTitle>
            {description && <CardDescription className="text-xs">{description}</CardDescription>}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Crosshair className="h-3 w-3" />
              {analytics.uniqueTactics} tactics
            </span>
            <span className="flex items-center gap-1">
              <Shield className="h-3 w-3" />
              {analytics.uniqueTechniques} techniques
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Coverage bar - how many events are mapped */}
        <div className="space-y-1">
          <div className="flex justify-between text-[11px] text-muted-foreground">
            <span>TTP Coverage</span>
            <span>{analytics.totalMapped}/{analytics.totalEvents} events mapped ({analytics.totalEvents > 0 ? Math.round((analytics.totalMapped / analytics.totalEvents) * 100) : 0}%)</span>
          </div>
          <div className="w-full bg-black/5 dark:bg-white/10 rounded-full h-1.5 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-red-500 to-orange-500 transition-all duration-500"
              style={{ width: `${analytics.totalEvents > 0 ? (analytics.totalMapped / analytics.totalEvents) * 100 : 0}%` }}
            />
          </div>
        </div>

        {/* Tactic breakdown */}
        <div className="space-y-2">
          {analytics.sortedTactics.map(([tactic, data]) => {
            const colors = tacticColors[tactic] || defaultTacticColor
            const techniques: [string, number][] = Object.entries(data.techniques).sort((a, b) => b[1] - a[1])
            const isExpanded = expandedTactic === tactic
            const sortedEvents = isExpanded
              ? [...data.events].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
              : []

            return (
              <div key={tactic} className="space-y-1">
                <button
                  onClick={() => setExpandedTactic(isExpanded ? null : tactic)}
                  className={`w-full text-left rounded-lg px-2 py-1.5 transition-colors cursor-pointer ${
                    isExpanded
                      ? 'bg-black/[0.04] dark:bg-white/[0.04]'
                      : 'hover:bg-black/[0.02] dark:hover:bg-white/[0.02]'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <ChevronDown className={`h-3 w-3 shrink-0 text-muted-foreground transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
                      <span className={`text-xs font-medium ${colors.text}`}>
                        {normalizeTacticLabel(tactic)}
                      </span>
                      {!compact && techniques.length > 0 && (
                        <div className="flex items-center gap-1 flex-wrap">
                          {techniques.slice(0, compact ? 2 : 5).map(([tech, techCount]) => (
                            <Badge
                              key={tech}
                              variant="outline"
                              className={`text-[9px] px-1 py-0 font-mono border-black/10 dark:border-white/10 ${colors.text}`}
                            >
                              {tech}{techCount > 1 ? ` x${techCount}` : ''}
                            </Badge>
                          ))}
                          {techniques.length > (compact ? 2 : 5) && (
                            <span className="text-[9px] text-muted-foreground">+{techniques.length - (compact ? 2 : 5)}</span>
                          )}
                        </div>
                      )}
                    </div>
                    <span className="text-xs font-bold text-foreground shrink-0">{data.count}</span>
                  </div>
                  <div className="w-full bg-black/5 dark:bg-white/10 rounded-full h-1.5 overflow-hidden mt-1">
                    <div
                      className={`h-full rounded-full ${colors.bar} transition-all duration-500`}
                      style={{ width: `${(data.count / analytics.maxCount) * 100}%` }}
                    />
                  </div>
                </button>

                {/* Expanded events list */}
                {isExpanded && (
                  <div className="ml-5 pl-3 border-l-2 border-black/5 dark:border-white/5 space-y-1 animate-in slide-in-from-top-1 fade-in duration-200">
                    {sortedEvents.length === 0 ? (
                      <p className="text-[11px] text-muted-foreground py-2">No events for this tactic</p>
                    ) : (
                      sortedEvents.slice(0, 20).map((event) => (
                        <div
                          key={event.id}
                          className="flex items-start gap-3 py-2 px-2 rounded-md hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition-colors"
                        >
                          <div className="shrink-0 pt-0.5">
                            <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-mono">
                              <Clock className="h-3 w-3" />
                              {new Date(event.timestamp).toLocaleString(undefined, {
                                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                              })}
                            </div>
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-[11px] text-foreground leading-snug truncate">{event.activity}</p>
                            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                              {event.hostname && (
                                <span className="inline-flex items-center gap-1 text-[9px] text-muted-foreground">
                                  <Server className="h-2.5 w-2.5" />
                                  {event.hostname}
                                  {event.host?.ip_address && (
                                    <span className="text-muted-foreground/50">({event.host.ip_address})</span>
                                  )}
                                </span>
                              )}
                              {(event.mitre_mappings?.length ? event.mitre_mappings : (event.mitre_technique ? [{ technique: event.mitre_technique }] : [])).map((m, mi) => (
                                m.technique && <Badge key={mi} variant="outline" className="text-[9px] px-1 py-0 font-mono border-black/10 dark:border-white/10">
                                  {m.technique.toUpperCase()}
                                </Badge>
                              ))}
                              {event.is_ioc && (
                                <Badge className="bg-red-500/20 text-red-400 border-red-500/30 border text-[9px] px-1 py-0">
                                  IOC
                                </Badge>
                              )}
                              {event.is_key_event && (
                                <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30 border text-[9px] px-1 py-0">
                                  KEY
                                </Badge>
                              )}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                    {sortedEvents.length > 20 && (
                      <p className="text-[10px] text-muted-foreground/60 px-2 py-1">
                        +{sortedEvents.length - 20} more events
                      </p>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Technique list for compact mode */}
        {compact && analytics.allTechniqueIds.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-1 border-t border-black/5 dark:border-white/5">
            {analytics.allTechniqueIds.slice(0, 8).map(tech => (
              <Badge key={tech} variant="outline" className="text-[9px] px-1.5 py-0 font-mono">
                {tech}
              </Badge>
            ))}
            {analytics.allTechniqueIds.length > 8 && (
              <span className="text-[9px] text-muted-foreground self-center">+{analytics.allTechniqueIds.length - 8} more</span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
