"use client"

import { useEffect, useMemo, useState, useRef, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { Target, Clock, Server, ChevronRight, ChevronDown, Link2, Eye, EyeOff, Loader2, Layers, ExternalLink, Shield } from 'lucide-react'
import api from '@/lib/api'
import type { TimelineEvent, MitreMapping, D3FENDTechnique, MITREAttackTechnique } from '@/types'

// ─── MITRE ATT&CK Tactics in Kill Chain Order ────────────────────────────

const TACTICS_ORDER = [
  { slug: 'reconnaissance', id: 'TA0043', name: 'Reconnaissance' },
  { slug: 'resource-development', id: 'TA0042', name: 'Resource Development' },
  { slug: 'initial-access', id: 'TA0001', name: 'Initial Access' },
  { slug: 'execution', id: 'TA0002', name: 'Execution' },
  { slug: 'persistence', id: 'TA0003', name: 'Persistence' },
  { slug: 'privilege-escalation', id: 'TA0004', name: 'Privilege Escalation' },
  { slug: 'defense-evasion', id: 'TA0005', name: 'Defense Evasion' },
  { slug: 'credential-access', id: 'TA0006', name: 'Credential Access' },
  { slug: 'discovery', id: 'TA0007', name: 'Discovery' },
  { slug: 'lateral-movement', id: 'TA0008', name: 'Lateral Movement' },
  { slug: 'collection', id: 'TA0009', name: 'Collection' },
  { slug: 'command-and-control', id: 'TA0011', name: 'Command and Control' },
  { slug: 'exfiltration', id: 'TA0010', name: 'Exfiltration' },
  { slug: 'impact', id: 'TA0040', name: 'Impact' },
]

const TACTIC_COLORS: Record<string, string> = {
  'reconnaissance': '#3b82f6',
  'resource-development': '#60a5fa',
  'initial-access': '#f59e0b',
  'execution': '#f97316',
  'persistence': '#f43f5e',
  'privilege-escalation': '#ef4444',
  'defense-evasion': '#ec4899',
  'credential-access': '#eab308',
  'discovery': '#06b6d4',
  'lateral-movement': '#10b981',
  'collection': '#8b5cf6',
  'command-and-control': '#a855f7',
  'exfiltration': '#f87171',
  'impact': '#dc2626',
}

// ─── Types ──────────────────────────────────────────────────────────────

interface TechniqueCell {
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

interface MitreNavigatorProps {
  events: TimelineEvent[]
  incidentId: string
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

export function MitreNavigator({ events, incidentId }: MitreNavigatorProps) {
  const [formData, setFormData] = useState<FormDataResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [selectedTechnique, setSelectedTechnique] = useState<TechniqueCell | null>(null)
  const [selectedTactic, setSelectedTactic] = useState<string | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [showChain, setShowChain] = useState(true)
  const [showAll, setShowAll] = useState(false)
  const [hoveredTech, setHoveredTech] = useState<string | null>(null)
  const matrixRef = useRef<HTMLDivElement>(null)
  const [toggledTechs, setToggledTechs] = useState<Set<string>>(new Set())
  const [ttpInfo, setTtpInfo] = useState<MITREAttackTechnique | null>(null)
  const [d3fendItems, setD3fendItems] = useState<D3FENDTechnique[]>([])
  const [drawerLoading, setDrawerLoading] = useState(false)

  // Fetch full MITRE matrix structure
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

  // Aggregate events by tactic → technique
  const { techniqueMap, attackChain, activeTactics } = useMemo(() => {
    const tMap: Record<string, TechniqueCell> = {}
    const activeTacticSet = new Set<string>()

    // Build per-event mappings
    const eventMappings: { event: TimelineEvent; tactic: string; technique: string }[] = []

    for (const event of events) {
      const mappings = event.mitre_mappings?.length
        ? event.mitre_mappings
        : event.mitre_tactic
          ? [{ tactic: event.mitre_tactic, technique: event.mitre_technique || '', name: '' }]
          : []

      if (mappings.length === 0) continue

      for (const m of mappings) {
        if (!m.tactic) continue
        const tacticSlug = normalizeTactic(m.tactic)
        const techId = (m.technique || '').toUpperCase()
        const key = `${tacticSlug}::${techId}`

        activeTacticSet.add(tacticSlug)

        if (!tMap[key]) {
          tMap[key] = { id: techId, name: m.name || techId, count: 0, events: [] }
        }
        tMap[key].count++
        tMap[key].events.push(event)

        eventMappings.push({ event, tactic: tacticSlug, technique: techId })
      }
    }

    // Build attack chain: for each active tactic, pick the top technique (highest event count)
    // to serve as the representative node. Chain flows between these representative techniques.
    const chainNodes: { tactic: string; technique: string; key: string }[] = []
    if (activeTacticSet.size > 1) {
      for (const t of TACTICS_ORDER) {
        if (!activeTacticSet.has(t.slug)) continue
        // Find the technique with the highest count in this tactic
        let best: { key: string; count: number; techId: string } | null = null
        for (const [key, cell] of Object.entries(tMap)) {
          if (!key.startsWith(t.slug + '::')) continue
          if (!cell.id) continue // skip entries without a technique ID
          if (!best || cell.count > best.count) {
            best = { key, count: cell.count, techId: cell.id }
          }
        }
        if (best) {
          chainNodes.push({ tactic: t.slug, technique: best.techId, key: best.key })
        }
      }
    }

    return { techniqueMap: tMap, attackChain: chainNodes, activeTactics: activeTacticSet }
  }, [events])

  const handleCellClick = useCallback(async (tech: TechniqueCell, tacticSlug: string) => {
    setSelectedTechnique(tech)
    setSelectedTactic(tacticSlug)
    setSheetOpen(true)
    setTtpInfo(null)
    setD3fendItems([])
    setDrawerLoading(true)
    try {
      const [ttpRes, d3fendRes] = await Promise.all([
        api.get<{ items: MITREAttackTechnique[] }>(`/knowledge-base/mitre-attack?search=${encodeURIComponent(tech.id)}`),
        api.post<{ items: D3FENDTechnique[] }>('/knowledge-base/d3fend/suggest', {
          attack_techniques: [tech.id.split('.')[0]],
        }).catch(() => ({ items: [] as D3FENDTechnique[] })),
      ])
      const match = ttpRes.items?.find((t: MITREAttackTechnique) => t.id === tech.id) || ttpRes.items?.[0] || null
      setTtpInfo(match)
      setD3fendItems(d3fendRes.items || [])
    } catch (err) {
      console.error('Failed to load TTP details:', err)
    } finally {
      setDrawerLoading(false)
    }
  }, [])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        Loading MITRE ATT&CK Matrix...
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

  // Build matrix columns
  const columns = TACTICS_ORDER.map(tactic => {
    const techniques = formData.technique_by_tactic[tactic.slug] || []
    return {
      ...tactic,
      techniques,
      active: activeTactics.has(tactic.slug),
      color: TACTIC_COLORS[tactic.slug] || '#6b7280',
    }
  })

  const totalMapped = Object.keys(techniqueMap).length
  const totalEvents = events.filter(e =>
    (e.mitre_mappings && e.mitre_mappings.length > 0) || e.mitre_tactic
  ).length

  return (
    <div className="space-y-4">
      {/* Stats Bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <Target className="h-4 w-4 text-red-400" />
            <strong className="text-foreground">{activeTactics.size}</strong> tactics active
          </span>
          <span>
            <strong className="text-foreground">{totalMapped}</strong> unique techniques
          </span>
          <span>
            <strong className="text-foreground">{totalEvents}</strong> mapped events
          </span>
          <span>
            <strong className="text-foreground">{attackChain.length}</strong> phases in chain
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => setShowAll(v => !v)}
          >
            <Layers className="h-3.5 w-3.5" />
            {showAll ? 'Mapped Only' : 'Show All'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => setShowChain(v => !v)}
          >
            {showChain ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            {showChain ? 'Hide' : 'Show'} Attack Chain
          </Button>
        </div>
      </div>

      {/* Attack Chain Flow */}
      {showChain && attackChain.length >= 2 && (
        <div className="border rounded-lg bg-muted/20 p-3">
          <div className="text-[11px] font-medium text-muted-foreground mb-2 flex items-center gap-1.5">
            <Link2 className="h-3.5 w-3.5" />
            Attack Chain — {attackChain.length} phases
          </div>
          <ScrollArea className="w-full">
            <div className="flex items-center gap-1 pb-1">
              {attackChain.map((node, i) => {
                const cell = techniqueMap[node.key]
                const tacticInfo = TACTICS_ORDER.find(t => t.slug === node.tactic)
                const color = TACTIC_COLORS[node.tactic] || '#6b7280'
                return (
                  <div key={node.key} className="flex items-center gap-1">
                    {i > 0 && (
                      <svg width="20" height="12" className="shrink-0 text-muted-foreground/40">
                        <path d="M 0 6 L 14 6" stroke="currentColor" strokeWidth="1.5" fill="none" />
                        <polygon points="13,2 19,6 13,10" fill="currentColor" />
                      </svg>
                    )}
                    <div
                      className="flex-shrink-0 rounded-md border bg-background px-2.5 py-1.5 cursor-pointer hover:bg-accent/50 transition-colors"
                      style={{ borderLeftWidth: 3, borderLeftColor: color }}
                      onClick={() => { if (cell) handleCellClick(cell, node.tactic) }}
                    >
                      <div className="flex items-center gap-1.5">
                        <span
                          className="inline-flex items-center justify-center h-4 w-4 rounded-full text-[8px] font-bold text-white shrink-0"
                          style={{ backgroundColor: color }}
                        >
                          {i + 1}
                        </span>
                        <span className="text-[10px] text-muted-foreground whitespace-nowrap">{tacticInfo?.name}</span>
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="text-[11px] font-semibold whitespace-nowrap" style={{ color }}>{node.technique}</span>
                        {cell && (
                          <Badge className="h-3.5 px-1 text-[8px] font-bold" style={{ backgroundColor: color, color: '#fff' }}>
                            {cell.count}
                          </Badge>
                        )}
                      </div>
                      {cell && (
                        <div className="text-[9px] text-muted-foreground truncate max-w-[100px] mt-0.5">{cell.name}</div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </div>
      )}

      {/* Matrix */}
      <div className="relative border rounded-lg bg-background" ref={matrixRef}>
        <ScrollArea className="w-full">
          <div className="inline-flex min-w-full">
            {columns.map(col => (
              <div key={col.slug} className="flex-shrink-0 w-[140px] border-r last:border-r-0">
                {/* Tactic Header */}
                <div
                  className="sticky top-0 z-10 px-2 py-2.5 text-center border-b font-medium text-[11px] leading-tight"
                  style={{
                    backgroundColor: col.active ? `${col.color}15` : undefined,
                    borderBottom: col.active ? `2px solid ${col.color}` : undefined,
                  }}
                >
                  {(() => {
                    const chainIdx = attackChain.findIndex(n => n.tactic === col.slug)
                    return (
                      <div className={`flex items-center justify-center gap-1 ${col.active ? 'text-foreground' : 'text-muted-foreground/60'}`}>
                        {showChain && chainIdx >= 0 && (
                          <span
                            className="inline-flex items-center justify-center h-4 w-4 rounded-full text-[8px] font-bold text-white shrink-0"
                            style={{ backgroundColor: col.color }}
                          >
                            {chainIdx + 1}
                          </span>
                        )}
                        <span className="truncate">{col.name}</span>
                      </div>
                    )
                  })()}
                  {col.active && (
                    <div className="text-[9px] mt-0.5" style={{ color: col.color }}>
                      {col.id}
                    </div>
                  )}
                </div>

                {/* Technique Cells — grouped by parent */}
                <div className="divide-y divide-border/50">
                  {groupTechniques(col.techniques).map(group => {
                    const hasChildren = group.children.length > 0
                    const parentKey = `${col.slug}::${group.parentId}`
                    const parentCell = techniqueMap[parentKey]
                    const childCounts = group.children.reduce((sum, c) => sum + (techniqueMap[`${col.slug}::${c.id}`]?.count || 0), 0)
                    const totalCount = (parentCell?.count || 0) + childCounts
                    const isGroupActive = totalCount > 0
                    const parentTech = group.parent

                    // When not showing all, hide techniques/groups with no mapped events
                    if (!showAll && !isGroupActive) return null

                    // Standalone technique (no sub-techniques)
                    if (!hasChildren) {
                      const cell = parentCell
                      const isActive = !!cell
                      const tech = parentTech!
                      const isHovered = hoveredTech === tech.id
                      return (
                        <TooltipProvider key={tech.id} delayDuration={200}>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <div
                                className={`px-1.5 py-1 text-[10px] leading-tight cursor-pointer transition-all duration-150 ${
                                  isActive
                                    ? 'font-medium hover:brightness-110'
                                    : 'text-muted-foreground/40 hover:text-muted-foreground/70 hover:bg-muted/30'
                                } ${isHovered ? 'ring-1 ring-primary/50' : ''}`}
                                style={isActive ? { backgroundColor: `${col.color}25`, color: col.color, borderLeft: `3px solid ${col.color}` } : undefined}
                                onClick={() => { if (isActive && cell) handleCellClick(cell, col.slug) }}
                                onMouseEnter={() => setHoveredTech(tech.id)}
                                onMouseLeave={() => setHoveredTech(null)}
                              >
                                <div className="flex items-center justify-between gap-0.5">
                                  <span className="truncate">{tech.id}</span>
                                  {isActive && (
                                    <Badge className="h-3.5 min-w-[16px] px-1 text-[8px] font-bold" style={{ backgroundColor: col.color, color: '#fff' }}>
                                      {cell.count}
                                    </Badge>
                                  )}
                                </div>
                                <div className="truncate text-[9px] opacity-80">{tech.name}</div>
                              </div>
                            </TooltipTrigger>
                            <TooltipContent side="right" className="max-w-[250px]">
                              <div className="space-y-1">
                                <div className="font-medium">{tech.id}: {tech.name}</div>
                                <div className="text-xs text-muted-foreground">Tactic: {col.name}</div>
                                {isActive ? (
                                  <div className="text-xs"><span className="font-medium text-primary">{cell.count} event{cell.count !== 1 ? 's' : ''}</span> mapped</div>
                                ) : (
                                  <div className="text-xs text-muted-foreground">No events mapped</div>
                                )}
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )
                    }

                    // Group with sub-techniques — always collapsed by default, user toggles to expand
                    const groupToggleKey = `${col.slug}::${group.parentId}`
                    const isExpanded = toggledTechs.has(groupToggleKey)
                    const isParentHovered = hoveredTech === group.parentId

                    // Filter sub-techniques: only show mapped ones (unless showAll)
                    const visibleChildren = showAll
                      ? group.children
                      : group.children.filter(c => techniqueMap[`${col.slug}::${c.id}`]?.count > 0)

                    // Merged cell with all group events for parent click
                    const allGroupEvents = [...(parentCell?.events || []), ...group.children.flatMap(c => techniqueMap[`${col.slug}::${c.id}`]?.events || [])]
                    const mergedCell: TechniqueCell = {
                      id: group.parentId,
                      name: parentTech?.name || group.parentId,
                      count: totalCount,
                      events: Array.from(new Map(allGroupEvents.map(e => [e.id, e] as const)).values()),
                    }

                    return (
                      <div key={group.parentId}>
                        {/* Parent row */}
                        <TooltipProvider delayDuration={200}>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <div
                                className={`px-1.5 py-1 text-[10px] leading-tight cursor-pointer transition-all duration-150 ${
                                  isGroupActive
                                    ? 'font-medium hover:brightness-110'
                                    : 'text-muted-foreground/40 hover:text-muted-foreground/70 hover:bg-muted/30'
                                } ${isParentHovered ? 'ring-1 ring-primary/50' : ''}`}
                                style={isGroupActive ? { backgroundColor: `${col.color}25`, color: col.color, borderLeft: `3px solid ${col.color}` } : undefined}
                                onClick={() => { if (isGroupActive) handleCellClick(mergedCell, col.slug) }}
                                onMouseEnter={() => setHoveredTech(group.parentId)}
                                onMouseLeave={() => setHoveredTech(null)}
                              >
                                <div className="flex items-center justify-between gap-0.5">
                                  <span className="flex items-center gap-0.5 truncate">
                                    {visibleChildren.length > 0 && (
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
                                        ? <ChevronDown className="h-3 w-3" />
                                        : <ChevronRight className="h-3 w-3" />}
                                    </span>
                                    )}
                                    {group.parentId}
                                  </span>
                                  {isGroupActive && (
                                    <Badge className="h-3.5 min-w-[16px] px-1 text-[8px] font-bold" style={{ backgroundColor: col.color, color: '#fff' }}>
                                      {totalCount}
                                    </Badge>
                                  )}
                                </div>
                                <div className="truncate text-[9px] opacity-80 pl-3.5">
                                  {parentTech?.name || `${group.children.length} sub-technique${group.children.length !== 1 ? 's' : ''}`}
                                </div>
                              </div>
                            </TooltipTrigger>
                            <TooltipContent side="right" className="max-w-[250px]">
                              <div className="space-y-1">
                                <div className="font-medium">{group.parentId}: {parentTech?.name || 'Technique Group'}</div>
                                <div className="text-xs text-muted-foreground">
                                  Tactic: {col.name} &middot; {group.children.length} sub-technique{group.children.length !== 1 ? 's' : ''}
                                </div>
                                {isGroupActive && (
                                  <div className="text-xs"><span className="font-medium text-primary">{totalCount} event{totalCount !== 1 ? 's' : ''}</span> across group</div>
                                )}
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>

                        {/* Sub-techniques — only mapped ones shown by default */}
                        {isExpanded && visibleChildren.map(child => {
                          const childKey = `${col.slug}::${child.id}`
                          const childCell = techniqueMap[childKey]
                          const isChildActive = !!childCell
                          const isChildHovered = hoveredTech === child.id

                          return (
                            <TooltipProvider key={child.id} delayDuration={200}>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <div
                                    className={`pl-4 pr-1.5 py-0.5 text-[9px] leading-tight cursor-pointer transition-all duration-150 border-t border-border/30 ${
                                      isChildActive
                                        ? 'font-medium hover:brightness-110'
                                        : 'text-muted-foreground/30 hover:text-muted-foreground/60 hover:bg-muted/20'
                                    } ${isChildHovered ? 'ring-1 ring-primary/50' : ''}`}
                                    style={isChildActive ? { backgroundColor: `${col.color}15`, color: col.color, borderLeft: `3px solid ${col.color}50` } : undefined}
                                    onClick={() => { if (isChildActive && childCell) handleCellClick(childCell, col.slug) }}
                                    onMouseEnter={() => setHoveredTech(child.id)}
                                    onMouseLeave={() => setHoveredTech(null)}
                                  >
                                    <div className="flex items-center justify-between gap-0.5">
                                      <span className="truncate">.{child.id.split('.')[1]}</span>
                                      {isChildActive && (
                                        <Badge className="h-3 min-w-[14px] px-0.5 text-[7px] font-bold" style={{ backgroundColor: col.color, color: '#fff' }}>
                                          {childCell.count}
                                        </Badge>
                                      )}
                                    </div>
                                    <div className="truncate text-[8px] opacity-70">{child.name}</div>
                                  </div>
                                </TooltipTrigger>
                                <TooltipContent side="right" className="max-w-[250px]">
                                  <div className="space-y-1">
                                    <div className="font-medium">{child.id}: {child.name}</div>
                                    <div className="text-xs text-muted-foreground">Tactic: {col.name}</div>
                                    {isChildActive ? (
                                      <div className="text-xs"><span className="font-medium text-primary">{childCell.count} event{childCell.count !== 1 ? 's' : ''}</span> mapped</div>
                                    ) : (
                                      <div className="text-xs text-muted-foreground">No events mapped</div>
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
                  {col.techniques.length === 0 && (
                    <div className="px-2 py-4 text-center text-[10px] text-muted-foreground/30">
                      No techniques
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
          <ScrollBar orientation="horizontal" />
        </ScrollArea>

      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
        <span className="font-medium">Kill Chain:</span>
        {TACTICS_ORDER.map((t, i) => (
          <span key={t.slug} className="flex items-center gap-0.5">
            <span
              className="w-2 h-2 rounded-sm"
              style={{ backgroundColor: activeTactics.has(t.slug) ? TACTIC_COLORS[t.slug] : '#374151' }}
            />
            <span className={activeTactics.has(t.slug) ? 'text-foreground font-medium' : ''}>
              {t.name}
            </span>
            {i < TACTICS_ORDER.length - 1 && <ChevronRight className="h-2.5 w-2.5 opacity-30" />}
          </span>
        ))}
      </div>

      {/* Event Detail Sheet */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent className="sm:max-w-lg overflow-y-auto">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <Target className="h-4 w-4" />
              {selectedTechnique?.id}
              {selectedTechnique?.name && selectedTechnique.name !== selectedTechnique.id && (
                <span className="font-normal text-muted-foreground">— {selectedTechnique.name}</span>
              )}
            </SheetTitle>
            <SheetDescription>
              {selectedTactic && (
                <Badge variant="outline" className="mr-2">
                  {TACTICS_ORDER.find(t => t.slug === selectedTactic)?.name || selectedTactic}
                </Badge>
              )}
              {selectedTechnique?.count} event{(selectedTechnique?.count || 0) !== 1 ? 's' : ''} matched
            </SheetDescription>
          </SheetHeader>

          <div className="mt-6 space-y-5">
            {/* TTP Description */}
            {drawerLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading technique details...
              </div>
            ) : ttpInfo ? (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold flex items-center gap-1.5">
                  <Target className="h-3.5 w-3.5" />
                  Technique Description
                </h4>
                <p className="text-sm text-muted-foreground leading-relaxed">{ttpInfo.description}</p>
                {ttpInfo.detection && (
                  <div className="mt-2">
                    <div className="text-xs font-medium text-muted-foreground mb-1">Detection Guidance</div>
                    <p className="text-xs text-muted-foreground/80 leading-relaxed">{ttpInfo.detection}</p>
                  </div>
                )}
                <a
                  href={`https://attack.mitre.org/techniques/${selectedTechnique?.id.replace('.', '/')}/`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-primary hover:underline mt-1"
                >
                  View on MITRE ATT&CK <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            ) : null}

            {/* D3FEND Countermeasures */}
            {!drawerLoading && d3fendItems.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold flex items-center gap-1.5">
                  <Shield className="h-3.5 w-3.5 text-green-500" />
                  D3FEND Countermeasures
                  <Badge variant="outline" className="text-[9px] ml-1">{d3fendItems.length}</Badge>
                </h4>
                <div className="max-h-[280px] overflow-y-auto rounded-md border p-2 space-y-1.5">
                  {d3fendItems.map(d => (
                    <div key={d.id} className="rounded-md border bg-muted/20 px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs font-medium">{d.id}: {d.name}</span>
                            {d.source === 'platform-suggested' && (
                              <Badge variant="glass" className="text-[8px] px-1 py-0 leading-tight">Suggested</Badge>
                            )}
                          </div>
                          <Badge variant="outline" className="text-[9px] mt-0.5 capitalize">{d.tactic}</Badge>
                        </div>
                        <a
                          href={`https://d3fend.mitre.org/technique/d3f:${d.name.replace(/\s+/g, '')}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="shrink-0 text-primary hover:text-primary/80"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      </div>
                      {d.description && (
                        <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">{d.description}</p>
                      )}
                    </div>
                  ))}
                </div>
                <a
                  href="https://d3fend.mitre.org/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                >
                  Browse MITRE D3FEND <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            )}

            {/* Matched Events */}
            <div className="space-y-2">
              <h4 className="text-sm font-semibold flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" />
                Matched Events
                <Badge variant="outline" className="text-[9px] ml-1">{selectedTechnique?.count}</Badge>
              </h4>
              <div className="space-y-2">
                {selectedTechnique?.events
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

                        {/* Show all MITRE mappings for this event */}
                        {event.mitre_mappings && event.mitre_mappings.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {event.mitre_mappings.map((m, i) => (
                              <Badge
                                key={i}
                                variant="default"
                                className="text-[9px] px-1.5 py-0"
                              >
                                {m.technique || m.tactic}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  ))}
              </div>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
