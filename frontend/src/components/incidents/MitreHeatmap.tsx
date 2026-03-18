"use client"

import { useEffect, useMemo, useState, useCallback } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Target, Clock, Server, Loader2, Flame, ChevronRight, ChevronDown } from 'lucide-react'
import api from '@/lib/api'
import type { TimelineEvent } from '@/types'

// ─── Tactic Order ───────────────────────────────────────────────────────

const TACTICS_ORDER = [
  { slug: 'reconnaissance', name: 'Recon' },
  { slug: 'resource-development', name: 'Res Dev' },
  { slug: 'initial-access', name: 'Init Access' },
  { slug: 'execution', name: 'Execution' },
  { slug: 'persistence', name: 'Persistence' },
  { slug: 'privilege-escalation', name: 'Priv Esc' },
  { slug: 'defense-evasion', name: 'Def Evasion' },
  { slug: 'credential-access', name: 'Cred Access' },
  { slug: 'discovery', name: 'Discovery' },
  { slug: 'lateral-movement', name: 'Lat Move' },
  { slug: 'collection', name: 'Collection' },
  { slug: 'command-and-control', name: 'C2' },
  { slug: 'exfiltration', name: 'Exfil' },
  { slug: 'impact', name: 'Impact' },
]

// ─── Types ──────────────────────────────────────────────────────────────

interface HeatCell {
  id: string
  name: string
  count: number
  events: TimelineEvent[]
}

interface FormDataResponse {
  tactics: { id: string; name: string; slug: string }[]
  technique_by_tactic: Record<string, { id: string; name: string }[]>
  technique_to_tactic: Record<string, string>
}

interface MitreHeatmapProps {
  events: TimelineEvent[]
  incidentId: string
}

// ─── Heat Color Helpers ─────────────────────────────────────────────────

function getHeatColor(count: number, maxCount: number): string {
  if (count === 0) return 'transparent'
  const intensity = Math.min(count / maxCount, 1)
  // Gradient: low = amber, mid = orange, high = red
  if (intensity <= 0.33) {
    const a = intensity / 0.33
    // amber 400 → orange 500
    return `rgba(251, 191, 36, ${0.3 + a * 0.3})`
  } else if (intensity <= 0.66) {
    const a = (intensity - 0.33) / 0.33
    return `rgba(249, 115, 22, ${0.4 + a * 0.3})`
  } else {
    const a = (intensity - 0.66) / 0.34
    return `rgba(239, 68, 68, ${0.5 + a * 0.4})`
  }
}

function getHeatTextClass(count: number, maxCount: number): string {
  if (count === 0) return 'text-muted-foreground/20'
  const intensity = count / maxCount
  if (intensity > 0.5) return 'text-white font-semibold'
  return 'text-foreground font-medium'
}

// ─── Helpers ────────────────────────────────────────────────────────────

function normalizeTactic(t: string): string {
  return t.toLowerCase().replace(/\s+/g, '-')
}

interface TechniqueGroup {
  parent: { id: string; name: string } | null
  parentId: string
  children: { id: string; name: string }[]
}

function groupTechniques(techniques: { id: string; name: string }[]): TechniqueGroup[] {
  const map = new Map<string, TechniqueGroup>()
  for (const tech of techniques) {
    if (tech.id.includes('.')) {
      const pid = tech.id.split('.')[0]
      if (!map.has(pid)) map.set(pid, { parent: null, parentId: pid, children: [] })
      map.get(pid)!.children.push(tech)
    } else {
      if (!map.has(tech.id)) map.set(tech.id, { parent: tech, parentId: tech.id, children: [] })
      else map.get(tech.id)!.parent = tech
    }
  }
  const result: TechniqueGroup[] = []
  const seen = new Set<string>()
  for (const tech of techniques) {
    const pid = tech.id.includes('.') ? tech.id.split('.')[0] : tech.id
    if (!seen.has(pid)) {
      seen.add(pid)
      result.push(map.get(pid)!)
    }
  }
  return result
}

// ─── Component ──────────────────────────────────────────────────────────

export function MitreHeatmap({ events, incidentId }: MitreHeatmapProps) {
  const [formData, setFormData] = useState<FormDataResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [selectedCell, setSelectedCell] = useState<HeatCell | null>(null)
  const [selectedTacticSlug, setSelectedTacticSlug] = useState<string | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [toggledTechs, setToggledTechs] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await api.get<FormDataResponse>('/knowledge-base/mitre-attack/form-data')
        if (!cancelled) setFormData(res)
      } catch (err) {
        console.error('Failed to load MITRE form data:', err)
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  // Aggregate events per tactic::technique
  const { heatMap, maxCount, tacticCounts } = useMemo(() => {
    const hMap: Record<string, HeatCell> = {}
    const tCounts: Record<string, number> = {}

    for (const event of events) {
      const mappings = event.mitre_mappings?.length
        ? event.mitre_mappings
        : event.mitre_tactic
          ? [{ tactic: event.mitre_tactic, technique: event.mitre_technique || '', name: '' }]
          : []

      for (const m of mappings) {
        if (!m.tactic) continue
        const tacticSlug = normalizeTactic(m.tactic)
        const techId = (m.technique || '').toUpperCase()
        const key = `${tacticSlug}::${techId}`

        if (!hMap[key]) {
          hMap[key] = { id: techId, name: m.name || techId, count: 0, events: [] }
        }
        hMap[key].count++
        hMap[key].events.push(event)

        tCounts[tacticSlug] = (tCounts[tacticSlug] || 0) + 1
      }
    }

    const max = Math.max(...Object.values(hMap).map(h => h.count), 1)
    return { heatMap: hMap, maxCount: max, tacticCounts: tCounts }
  }, [events])

  const handleCellClick = useCallback((cell: HeatCell, tacticSlug: string) => {
    setSelectedCell(cell)
    setSelectedTacticSlug(tacticSlug)
    setSheetOpen(true)
  }, [])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        Loading MITRE ATT&CK Heatmap...
      </div>
    )
  }

  if (!formData) {
    return (
      <div className="py-16 text-center text-sm text-muted-foreground">
        Failed to load MITRE ATT&CK data.
      </div>
    )
  }

  // Determine top techniques across all tactics (for summary)
  const topTechniques = Object.values(heatMap)
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)

  const totalActiveTechniques = Object.values(heatMap).filter(h => h.count > 0).length
  const totalMappedEvents = events.filter(e =>
    (e.mitre_mappings && e.mitre_mappings.length > 0) || e.mitre_tactic
  ).length

  return (
    <div className="space-y-4">
      {/* Summary Row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <Flame className="h-4 w-4 text-orange-400" />
            <strong className="text-foreground">{totalActiveTechniques}</strong> active techniques
          </span>
          <span>
            <strong className="text-foreground">{totalMappedEvents}</strong> events mapped
          </span>
          <span>hottest: <strong className="text-foreground">{maxCount}</strong> hits</span>
        </div>

        {/* Heat Scale Legend */}
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <span>Low</span>
          <div className="flex gap-px">
            {[0.15, 0.3, 0.5, 0.7, 0.9].map((v, i) => (
              <div
                key={i}
                className="w-4 h-3 rounded-sm"
                style={{ backgroundColor: getHeatColor(v * maxCount, maxCount) }}
              />
            ))}
          </div>
          <span>High</span>
        </div>
      </div>

      {/* Top Techniques */}
      {topTechniques.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground font-medium mr-1">Top TTPs:</span>
          {topTechniques.map(t => (
            <Badge key={t.id} variant="default" className="text-[10px] gap-1">
              {t.id}
              <span className="text-[9px] px-1 py-0 rounded bg-primary/20 text-primary font-bold">
                {t.count}
              </span>
            </Badge>
          ))}
        </div>
      )}

      {/* Heatmap Grid */}
      <div className="border rounded-lg bg-background overflow-hidden">
        <ScrollArea className="w-full">
          <div className="inline-flex min-w-full">
            {TACTICS_ORDER.map(tactic => {
              const techniques = formData.technique_by_tactic[tactic.slug] || []
              const tacticCount = tacticCounts[tactic.slug] || 0
              const hasActivity = tacticCount > 0

              // Group techniques and sort by activity
              const groups = groupTechniques(techniques)
              const getGroupCount = (g: TechniqueGroup) => {
                const pc = heatMap[`${tactic.slug}::${g.parentId}`]?.count || 0
                const cc = g.children.reduce((s, c) => s + (heatMap[`${tactic.slug}::${c.id}`]?.count || 0), 0)
                return pc + cc
              }
              const activeGroups = groups.filter(g => getGroupCount(g) > 0).sort((a, b) => getGroupCount(b) - getGroupCount(a))
              const inactiveGroups = groups.filter(g => getGroupCount(g) === 0)
              const capInactive = Math.max(2, 8 - activeGroups.length)
              const displayGroups = [...activeGroups, ...inactiveGroups.slice(0, capInactive)]
              const hiddenCount = Math.max(0, inactiveGroups.length - capInactive)

              return (
                <div key={tactic.slug} className="flex-shrink-0 w-[120px] border-r last:border-r-0">
                  {/* Tactic Header */}
                  <div
                    className={`sticky top-0 z-10 px-1.5 py-2 text-center border-b ${
                      hasActivity ? 'bg-muted/50' : 'bg-background'
                    }`}
                  >
                    <div className={`text-[10px] font-medium leading-tight ${
                      hasActivity ? 'text-foreground' : 'text-muted-foreground/50'
                    }`}>
                      {tactic.name}
                    </div>
                    {hasActivity && (
                      <div className="text-[9px] text-muted-foreground mt-0.5">
                        {tacticCount} hit{tacticCount !== 1 ? 's' : ''}
                      </div>
                    )}
                  </div>

                  {/* Cells — grouped by parent technique */}
                  <div className="p-1 space-y-0.5">
                    {displayGroups.map(group => {
                      const hasChildren = group.children.length > 0
                      const totalCount = getGroupCount(group)
                      const parentTech = group.parent

                      // Standalone technique (no sub-techniques)
                      if (!hasChildren) {
                        const key = `${tactic.slug}::${group.parentId}`
                        const cell = heatMap[key]
                        const count = cell?.count || 0
                        const tech = parentTech!
                        return (
                          <TooltipProvider key={tech.id} delayDuration={150}>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <div
                                  className={`rounded px-1 py-0.5 text-[9px] leading-tight cursor-pointer transition-all ${
                                    count > 0 ? 'hover:ring-1 hover:ring-primary/50' : 'opacity-40 hover:opacity-60'
                                  }`}
                                  style={count > 0 ? { backgroundColor: getHeatColor(count, maxCount) } : undefined}
                                  onClick={() => { if (cell) handleCellClick(cell, tactic.slug) }}
                                >
                                  <div className="flex items-center justify-between gap-0.5">
                                    <span className={`truncate ${getHeatTextClass(count, maxCount)}`}>{tech.id}</span>
                                    {count > 0 && (
                                      <span className={`shrink-0 text-[8px] font-bold ${getHeatTextClass(count, maxCount)}`}>{count}</span>
                                    )}
                                  </div>
                                </div>
                              </TooltipTrigger>
                              <TooltipContent side="right" className="max-w-[220px]">
                                <div className="space-y-0.5">
                                  <div className="font-medium text-xs">{tech.id}: {tech.name}</div>
                                  {count > 0 ? (
                                    <div className="text-xs text-primary font-medium">{count} event{count !== 1 ? 's' : ''}</div>
                                  ) : (
                                    <div className="text-xs text-muted-foreground">No events</div>
                                  )}
                                </div>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )
                      }

                      // Group with sub-techniques
                      const hasActiveChildren = group.children.some(c => heatMap[`${tactic.slug}::${c.id}`]?.count > 0)
                      const parentCount = heatMap[`${tactic.slug}::${group.parentId}`]?.count || 0
                      const groupToggleKey = `${tactic.slug}::${group.parentId}`
                      const defaultExpanded = hasActiveChildren || parentCount > 0
                      const isExpanded = defaultExpanded ? !toggledTechs.has(groupToggleKey) : toggledTechs.has(groupToggleKey)

                      // Merged cell for parent click
                      const parentCell = heatMap[`${tactic.slug}::${group.parentId}`]
                      const allEvents = [
                        ...(parentCell?.events || []),
                        ...group.children.flatMap(c => heatMap[`${tactic.slug}::${c.id}`]?.events || []),
                      ]
                      const mergedCell: HeatCell = {
                        id: group.parentId,
                        name: parentTech?.name || group.parentId,
                        count: totalCount,
                        events: Array.from(new Map(allEvents.map(e => [e.id, e] as const)).values()),
                      }

                      return (
                        <div key={group.parentId}>
                          {/* Parent row */}
                          <TooltipProvider delayDuration={150}>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <div
                                  className={`rounded px-1 py-0.5 text-[9px] leading-tight cursor-pointer transition-all ${
                                    totalCount > 0 ? 'hover:ring-1 hover:ring-primary/50' : 'opacity-40 hover:opacity-60'
                                  }`}
                                  style={totalCount > 0 ? { backgroundColor: getHeatColor(totalCount, maxCount) } : undefined}
                                  onClick={() => { if (totalCount > 0) handleCellClick(mergedCell, tactic.slug) }}
                                >
                                  <div className="flex items-center justify-between gap-0.5">
                                    <span className={`flex items-center gap-0.5 truncate ${getHeatTextClass(totalCount, maxCount)}`}>
                                      <span
                                        className="shrink-0 rounded hover:bg-black/10"
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          setToggledTechs(prev => {
                                            const next = new Set(prev)
                                            if (next.has(groupToggleKey)) next.delete(groupToggleKey)
                                            else next.add(groupToggleKey)
                                            return next
                                          })
                                        }}
                                      >
                                        {isExpanded
                                          ? <ChevronDown className="h-2.5 w-2.5" />
                                          : <ChevronRight className="h-2.5 w-2.5" />}
                                      </span>
                                      {group.parentId}
                                    </span>
                                    {totalCount > 0 && (
                                      <span className={`shrink-0 text-[8px] font-bold ${getHeatTextClass(totalCount, maxCount)}`}>{totalCount}</span>
                                    )}
                                  </div>
                                </div>
                              </TooltipTrigger>
                              <TooltipContent side="right" className="max-w-[220px]">
                                <div className="space-y-0.5">
                                  <div className="font-medium text-xs">{group.parentId}: {parentTech?.name || 'Group'}</div>
                                  <div className="text-[10px] text-muted-foreground">{group.children.length} sub-technique{group.children.length !== 1 ? 's' : ''}</div>
                                  {totalCount > 0 && (
                                    <div className="text-xs text-primary font-medium">{totalCount} event{totalCount !== 1 ? 's' : ''} across group</div>
                                  )}
                                </div>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>

                          {/* Sub-techniques */}
                          {isExpanded && group.children.map(child => {
                            const childKey = `${tactic.slug}::${child.id}`
                            const childCell = heatMap[childKey]
                            const childCount = childCell?.count || 0
                            return (
                              <TooltipProvider key={child.id} delayDuration={150}>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <div
                                      className={`rounded pl-3 pr-1 py-0.5 text-[8px] leading-tight cursor-pointer transition-all mt-px ${
                                        childCount > 0 ? 'hover:ring-1 hover:ring-primary/50' : 'opacity-30 hover:opacity-50'
                                      }`}
                                      style={childCount > 0 ? { backgroundColor: getHeatColor(childCount, maxCount) } : undefined}
                                      onClick={() => { if (childCell) handleCellClick(childCell, tactic.slug) }}
                                    >
                                      <div className="flex items-center justify-between gap-0.5">
                                        <span className={`truncate ${getHeatTextClass(childCount, maxCount)}`}>.{child.id.split('.')[1]}</span>
                                        {childCount > 0 && (
                                          <span className={`shrink-0 text-[7px] font-bold ${getHeatTextClass(childCount, maxCount)}`}>{childCount}</span>
                                        )}
                                      </div>
                                    </div>
                                  </TooltipTrigger>
                                  <TooltipContent side="right" className="max-w-[220px]">
                                    <div className="space-y-0.5">
                                      <div className="font-medium text-xs">{child.id}: {child.name}</div>
                                      {childCount > 0 ? (
                                        <div className="text-xs text-primary font-medium">{childCount} event{childCount !== 1 ? 's' : ''}</div>
                                      ) : (
                                        <div className="text-xs text-muted-foreground">No events</div>
                                      )}
                                    </div>
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            )
                          })}
                        </div>
                      )
                    })}

                    {hiddenCount > 0 && (
                      <div className="text-[8px] text-center text-muted-foreground/40 pt-1">
                        +{hiddenCount} more
                      </div>
                    )}

                    {displayGroups.length === 0 && (
                      <div className="text-[9px] text-center text-muted-foreground/30 py-3">
                        —
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
          <ScrollBar orientation="horizontal" />
        </ScrollArea>
      </div>

      {/* Event Detail Sheet */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent className="sm:max-w-lg overflow-y-auto">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <Flame className="h-4 w-4 text-orange-400" />
              {selectedCell?.id}
              {selectedCell?.name && selectedCell.name !== selectedCell.id && (
                <span className="font-normal text-muted-foreground">— {selectedCell.name}</span>
              )}
            </SheetTitle>
            <SheetDescription>
              {selectedTacticSlug && (
                <Badge variant="outline" className="mr-2">
                  {TACTICS_ORDER.find(t => t.slug === selectedTacticSlug)?.name || selectedTacticSlug}
                </Badge>
              )}
              {selectedCell?.count} event{(selectedCell?.count || 0) !== 1 ? 's' : ''}
            </SheetDescription>
          </SheetHeader>

          <div className="mt-6 space-y-3">
            {selectedCell?.events
              .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
              .map(event => (
                <Card key={event.id} className="bg-muted/30">
                  <CardContent className="p-3 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="font-medium text-sm truncate">{event.activity}</div>
                      </div>
                      <Badge variant="outline" className="shrink-0 text-[10px] capitalize">
                        {event.source || 'event'}
                      </Badge>
                    </div>

                    <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {new Date(event.timestamp).toLocaleString()}
                      </span>
                      {event.hostname && (
                        <span className="flex items-center gap-1">
                          <Server className="h-3 w-3" />
                          {event.hostname}
                        </span>
                      )}
                    </div>

                    {event.mitre_mappings && event.mitre_mappings.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {event.mitre_mappings.map((m, i) => (
                          <Badge key={i} variant="default" className="text-[9px] px-1.5 py-0">
                            {m.technique || m.tactic}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
