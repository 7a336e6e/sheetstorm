/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import api from '@/lib/api'
import type { LOLBASEntry, WindowsEventID, D3FENDTechnique } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Search,
  BookOpen,
  Terminal,
  MonitorDot,
  Shield,
  Loader2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Filter,
  Sparkles,
} from 'lucide-react'

type KBTab = 'lolbas' | 'eventids' | 'd3fend'

const KB_TABS: { id: KBTab; label: string; icon: React.ElementType }[] = [
  { id: 'lolbas', label: 'LOLBAS', icon: Terminal },
  { id: 'eventids', label: 'Event IDs', icon: MonitorDot },
  { id: 'd3fend', label: 'MITRE D3FEND', icon: Shield },
]

export default function KnowledgeBasePage() {
  const [activeTab, setActiveTab] = useState<KBTab>('lolbas')

  return (
    <div className="p-6 lg:p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Knowledge Base</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Reference data for incident response and threat analysis
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 border-b border-border pb-px">
        {KB_TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-t-md transition-colors',
              activeTab === tab.id
                ? 'bg-card text-foreground border border-border border-b-transparent -mb-px'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'lolbas' && <LOLBASTab />}
      {activeTab === 'eventids' && <EventIDTab />}
      {activeTab === 'd3fend' && <D3FENDTab />}
    </div>
  )
}

/* ────────────────── LOLBAS Tab ────────────────── */

function LOLBASTab() {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [data, setData] = useState<LOLBASEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [fetched, setFetched] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const load = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      if (category) params.set('category', category)
      const res = await api.get<{ items: LOLBASEntry[] }>(`/knowledge-base/lolbas?${params}`)
      setData(res.items)
      setFetched(true)
    } finally { setLoading(false) }
  }

  const toggle = (name: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
  }

  const categories = ['Binaries', 'Scripts', 'Libraries']

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && load()}
            placeholder="Search binaries, scripts…"
            className="w-full pl-9 pr-4 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <select
          value={category}
          onChange={e => setCategory(e.target.value)}
          className="px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All categories</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <Button onClick={load} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4 mr-1" />}
          Search
        </Button>
      </div>

      {!fetched && (
        <div className="text-center py-12 text-muted-foreground text-sm">
          <Terminal className="h-8 w-8 mx-auto mb-2 opacity-40" />
          Search the LOLBAS knowledge base for living-off-the-land binaries, scripts, and libraries.
        </div>
      )}

      {fetched && data.length === 0 && (
        <div className="text-center py-12 text-muted-foreground text-sm">No results found.</div>
      )}

      {data.length > 0 && (
        <div className="border border-border rounded-lg divide-y divide-border bg-card">
          {data.map(entry => (
            <div key={entry.name}>
              <button
                onClick={() => toggle(entry.name)}
                className="w-full flex items-center justify-between p-3 text-left hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  {expanded.has(entry.name) ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  <div>
                    <span className="font-mono text-sm font-semibold">{entry.name}</span>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{entry.description}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {entry.mitre_id && <Badge variant="outline">{entry.mitre_id}</Badge>}
                  <Badge variant="default">{entry.category}</Badge>
                </div>
              </button>
              {expanded.has(entry.name) && (
                <div className="px-10 pb-4 space-y-2 text-sm">
                  <p className="text-muted-foreground">{entry.description}</p>
                  {entry.path && <KBField label="Path" value={entry.path} mono />}
                  {entry.commands && entry.commands.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-muted-foreground mb-1">Commands</p>
                      {entry.commands.map((cmd, i) => (
                        <code key={i} className="block text-xs bg-muted px-2 py-1 rounded mb-1 break-all">{cmd}</code>
                      ))}
                    </div>
                  )}
                  {entry.detection && entry.detection.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-muted-foreground mb-0.5">Detection</p>
                      <ul className="list-disc list-inside text-sm text-muted-foreground space-y-0.5">
                        {entry.detection.map((d, i) => <li key={i}>{d}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ────────────────── Event IDs Tab ────────────────── */

function EventIDTab() {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [severity, setSeverity] = useState('')
  const [data, setData] = useState<WindowsEventID[]>([])
  const [loading, setLoading] = useState(false)
  const [fetched, setFetched] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      if (category) params.set('category', category)
      if (severity) params.set('severity', severity)
      const res = await api.get<{ items: WindowsEventID[] }>(`/knowledge-base/event-ids?${params}`)
      setData(res.items)
      setFetched(true)
    } finally { setLoading(false) }
  }

  const categories = useMemo(() => Array.from(new Set(data.map(d => d.category))).sort(), [data])
  const severities = ['Critical', 'High', 'Medium', 'Low', 'Informational']

  const severityColor = (s: string) => {
    const sl = s.toLowerCase()
    if (sl === 'critical') return 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300'
    if (sl === 'high') return 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300'
    if (sl === 'medium') return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300'
    return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && load()}
            placeholder="Search event IDs or descriptions…"
            className="w-full pl-9 pr-4 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <select
          value={category}
          onChange={e => setCategory(e.target.value)}
          className="px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All categories</option>
          {['Authentication', 'Privilege Use', 'Account Management', 'Lateral Movement', 'Persistence', 'Defense Evasion', 'PowerShell', 'Process/Sysmon', 'Credential Access', 'Firewall'].map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={severity}
          onChange={e => setSeverity(e.target.value)}
          className="px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All severities</option>
          {severities.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <Button onClick={load} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Filter className="h-4 w-4 mr-1" />}
          Filter
        </Button>
      </div>

      {!fetched && (
        <div className="text-center py-12 text-muted-foreground text-sm">
          <MonitorDot className="h-8 w-8 mx-auto mb-2 opacity-40" />
          Search security-relevant Windows event IDs for monitoring and detection.
        </div>
      )}

      {fetched && data.length === 0 && (
        <div className="text-center py-12 text-muted-foreground text-sm">No results found.</div>
      )}

      {data.length > 0 && (
        <div className="border border-border rounded-lg bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="text-left py-2 px-3 font-medium text-muted-foreground w-24">Event ID</th>
                <th className="text-left py-2 px-3 font-medium text-muted-foreground">Description</th>
                <th className="text-left py-2 px-3 font-medium text-muted-foreground w-36">Category</th>
                <th className="text-left py-2 px-3 font-medium text-muted-foreground w-36">Provider</th>
                <th className="text-left py-2 px-3 font-medium text-muted-foreground w-28">Severity</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.map(evt => (
                <tr key={evt.event_id} className="hover:bg-muted/30 transition-colors">
                  <td className="py-2 px-3 font-mono font-semibold">{evt.event_id}</td>
                  <td className="py-2 px-3">{evt.description}</td>
                  <td className="py-2 px-3">
                    <Badge variant="outline">{evt.category}</Badge>
                  </td>
                  <td className="py-2 px-3 text-muted-foreground text-xs">{evt.provider}</td>
                  <td className="py-2 px-3">
                    <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full', severityColor(evt.severity))}>
                      {evt.severity}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* ────────────────── D3FEND Tab ────────────────── */

function D3FENDTab() {
  const [search, setSearch] = useState('')
  const [tactic, setTactic] = useState('')
  const [data, setData] = useState<D3FENDTechnique[]>([])
  const [loading, setLoading] = useState(false)
  const [fetched, setFetched] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // Suggest
  const [suggestInput, setSuggestInput] = useState('')
  const [suggestions, setSuggestions] = useState<D3FENDTechnique[]>([])
  const [suggestLoading, setSuggestLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      if (tactic) params.set('tactic', tactic)
      const res = await api.get<{ items: D3FENDTechnique[] }>(`/knowledge-base/d3fend?${params}`)
      setData(res.items)
      setFetched(true)
    } finally { setLoading(false) }
  }

  const suggest = async () => {
    if (!suggestInput.trim()) return
    setSuggestLoading(true)
    try {
      const ids = suggestInput.split(',').map(s => s.trim()).filter(Boolean)
      const res = await api.post<{ suggestions: D3FENDTechnique[]; attack_techniques: string[] }>(
        '/knowledge-base/d3fend/suggest', { attack_techniques: ids }
      )
      setSuggestions(res.suggestions)
    } finally { setSuggestLoading(false) }
  }

  const toggle = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const tactics = ['Harden', 'Detect', 'Isolate', 'Deceive', 'Evict', 'Restore']
  const tacticColor = (t: string) => {
    const colors: Record<string, string> = {
      'Harden': 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300',
      'Detect': 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300',
      'Isolate': 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300',
      'Deceive': 'bg-pink-100 text-pink-800 dark:bg-pink-950 dark:text-pink-300',
      'Evict': 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
      'Restore': 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300',
    }
    return colors[t] || 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
  }

  return (
    <div className="space-y-6">
      {/* Suggest Section */}
      <div className="border border-border rounded-lg bg-card p-4 space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="h-4 w-4 text-yellow-500" />
          Suggest Countermeasures from ATT&CK Techniques
        </div>
        <p className="text-xs text-muted-foreground">
          Enter MITRE ATT&CK technique IDs (comma-separated) to get recommended D3FEND countermeasures.
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={suggestInput}
            onChange={e => setSuggestInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && suggest()}
            placeholder="T1059, T1078, T1486…"
            className="flex-1 px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Button onClick={suggest} disabled={suggestLoading || !suggestInput.trim()}>
            {suggestLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Sparkles className="h-4 w-4 mr-1" />}
            Suggest
          </Button>
        </div>
        {suggestions.length > 0 && (
          <div className="divide-y divide-border border border-border rounded-md mt-2">
            {suggestions.map(s => (
              <div key={s.id} className="p-3 space-y-1">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="font-mono text-xs">{s.id}</Badge>
                  <span className="text-sm font-medium">{s.name}</span>
                  <span className={cn('text-[10px] font-medium px-1.5 py-0.5 rounded-full', tacticColor(s.tactic))}>
                    {s.tactic}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">{s.description}</p>
                <div className="flex gap-1 flex-wrap">
                  {s.mitre_attack_mappings.map(m => (
                    <Badge key={m} variant="default" className="text-[10px]">{m}</Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Browse Section */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && load()}
            placeholder="Search D3FEND techniques…"
            className="w-full pl-9 pr-4 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <select
          value={tactic}
          onChange={e => setTactic(e.target.value)}
          className="px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All tactics</option>
          {tactics.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <Button onClick={load} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4 mr-1" />}
          Browse
        </Button>
      </div>

      {!fetched && (
        <div className="text-center py-12 text-muted-foreground text-sm">
          <Shield className="h-8 w-8 mx-auto mb-2 opacity-40" />
          Browse the MITRE D3FEND knowledge base of defensive countermeasures.
        </div>
      )}

      {fetched && data.length === 0 && (
        <div className="text-center py-12 text-muted-foreground text-sm">No results found.</div>
      )}

      {data.length > 0 && (
        <div className="border border-border rounded-lg divide-y divide-border bg-card">
          {data.map(tech => (
            <div key={tech.id}>
              <button
                onClick={() => toggle(tech.id)}
                className="w-full flex items-center justify-between p-3 text-left hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  {expanded.has(tech.id) ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  <div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="font-mono text-xs">{tech.id}</Badge>
                      <span className="text-sm font-medium">{tech.name}</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{tech.description}</p>
                  </div>
                </div>
                <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap', tacticColor(tech.tactic))}>
                  {tech.tactic}
                </span>
              </button>
              {expanded.has(tech.id) && (
                <div className="px-10 pb-4 space-y-2 text-sm">
                  <p className="text-muted-foreground">{tech.description}</p>
                  {tech.mitre_attack_mappings.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-muted-foreground mb-1">Counters ATT&CK Techniques</p>
                      <div className="flex gap-1 flex-wrap">
                        {tech.mitre_attack_mappings.map(m => (
                          <Badge key={m} variant="default" className="text-xs">{m}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {tech.examples && tech.examples.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-muted-foreground mb-1">Implementation Examples</p>
                      <ul className="list-disc list-inside text-xs text-muted-foreground space-y-0.5">
                        {tech.examples.map((ex, i) => <li key={i}>{ex}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ────────────────── Helpers ────────────────── */

function KBField({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground mb-0.5">{label}</p>
      <p className={cn('text-sm', mono && 'font-mono')}>{value}</p>
    </div>
  )
}
