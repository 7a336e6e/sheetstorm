/**
 * MITRE Pattern Management — CRUD for YAML detection patterns.
 * Shows current patterns, allows add/edit/delete, inline editing.
 */

"use client"

import { useState, useEffect, useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Loader2, Plus, Trash2, Search, Save, X, FileCode2 } from 'lucide-react'
import { api } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import { useConfirm } from '@/components/ui/confirm-dialog'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter, DialogBody,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

interface Pattern {
  technique: string
  tactic: string
  name: string
  keywords: string[]
  regex: string[]
  weight: number
}

const TACTICS = [
  'reconnaissance', 'resource-development', 'initial-access', 'execution',
  'persistence', 'privilege-escalation', 'defense-evasion', 'credential-access',
  'discovery', 'lateral-movement', 'collection', 'command-and-control',
  'exfiltration', 'impact',
]

const TACTIC_LABELS: Record<string, string> = {
  'reconnaissance': 'Reconnaissance',
  'resource-development': 'Resource Development',
  'initial-access': 'Initial Access',
  'execution': 'Execution',
  'persistence': 'Persistence',
  'privilege-escalation': 'Privilege Escalation',
  'defense-evasion': 'Defense Evasion',
  'credential-access': 'Credential Access',
  'discovery': 'Discovery',
  'lateral-movement': 'Lateral Movement',
  'collection': 'Collection',
  'command-and-control': 'Command and Control',
  'exfiltration': 'Exfiltration',
  'impact': 'Impact',
}

export function MitrePatternManager() {
  const { toast } = useToast()
  const confirm = useConfirm()
  const [loading, setLoading] = useState(true)
  const [patterns, setPatterns] = useState<Pattern[]>([])
  const [search, setSearch] = useState('')
  const [filterTactic, setFilterTactic] = useState('')

  // Modal
  const [showModal, setShowModal] = useState(false)
  const [editingIdx, setEditingIdx] = useState<number | null>(null)
  const [form, setForm] = useState({
    technique: '', tactic: 'execution', name: '',
    keywords: '', regex: '', weight: '0.8',
  })

  useEffect(() => { loadPatterns() }, [])

  const loadPatterns = async () => {
    try {
      const res = await api.get<{ patterns: Pattern[] }>('/mitre/patterns')
      setPatterns(res.patterns || [])
    } catch { toast({ title: 'Failed to load patterns', variant: 'destructive' }) }
    finally { setLoading(false) }
  }

  const filtered = useMemo(() => {
    let list = patterns
    if (filterTactic) list = list.filter(p => p.tactic === filterTactic)
    if (search) {
      const q = search.toLowerCase()
      list = list.filter(p =>
        p.technique.toLowerCase().includes(q) ||
        p.name.toLowerCase().includes(q) ||
        p.keywords.some(kw => kw.includes(q))
      )
    }
    return list
  }, [patterns, search, filterTactic])

  // Group by tactic for display
  const grouped = useMemo(() => {
    const map: Record<string, Pattern[]> = {}
    for (const p of filtered) {
      ;(map[p.tactic] ??= []).push(p)
    }
    return map
  }, [filtered])

  const openAddModal = () => {
    setEditingIdx(null)
    setForm({ technique: '', tactic: 'execution', name: '', keywords: '', regex: '', weight: '0.8' })
    setShowModal(true)
  }

  const openEditModal = (pattern: Pattern) => {
    const idx = patterns.indexOf(pattern)
    setEditingIdx(idx)
    setForm({
      technique: pattern.technique,
      tactic: pattern.tactic,
      name: pattern.name,
      keywords: pattern.keywords.join(', '),
      regex: pattern.regex.join('\n'),
      weight: String(pattern.weight),
    })
    setShowModal(true)
  }

  const handleSave = async () => {
    if (!form.technique || !form.name) return
    const entry: Pattern = {
      technique: form.technique.toUpperCase().trim(),
      tactic: form.tactic,
      name: form.name.trim(),
      keywords: form.keywords.split(',').map(k => k.trim().toLowerCase()).filter(Boolean),
      regex: form.regex.split('\n').map(r => r.trim()).filter(Boolean),
      weight: Math.min(1, Math.max(0, parseFloat(form.weight) || 0.8)),
    }

    let newPatterns: Pattern[]
    if (editingIdx !== null) {
      newPatterns = [...patterns]
      newPatterns[editingIdx] = entry
    } else {
      newPatterns = [...patterns, entry]
    }

    try {
      await api.put('/mitre/patterns', { patterns: newPatterns })
      setPatterns(newPatterns)
      setShowModal(false)
      toast({ title: editingIdx !== null ? 'Pattern updated' : 'Pattern added' })
    } catch { toast({ title: 'Error saving', variant: 'destructive' }) }
  }

  const handleDelete = async (pattern: Pattern) => {
    const ok = await confirm({
      title: 'Delete Pattern',
      description: `Remove detection pattern for ${pattern.technique} (${pattern.name})?`,
      confirmLabel: 'Delete',
      variant: 'destructive',
    })
    if (!ok) return

    try {
      await api.delete(`/mitre/patterns/${pattern.technique}`)
      setPatterns(prev => prev.filter(p => p.technique !== pattern.technique))
      toast({ title: 'Pattern removed' })
    } catch { toast({ title: 'Error', variant: 'destructive' }) }
  }

  if (loading) {
    return <div className="flex items-center justify-center p-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h3 className="text-lg font-medium flex items-center gap-2">
            <FileCode2 className="h-5 w-5 text-orange-400" />
            MITRE Detection Patterns
          </h3>
          <p className="text-sm text-muted-foreground">
            {patterns.length} patterns across {new Set(patterns.map(p => p.tactic)).size} tactics
          </p>
        </div>
        <Button onClick={openAddModal}><Plus className="mr-2 h-4 w-4" /> Add Pattern</Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input className="pl-9" placeholder="Search technique ID, name, or keyword..." value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <Select value={filterTactic} onValueChange={setFilterTactic}>
          <SelectTrigger className="w-[200px]"><SelectValue placeholder="All Tactics" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="">All Tactics</SelectItem>
            {TACTICS.map(t => <SelectItem key={t} value={t}>{TACTIC_LABELS[t]}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* Patterns by tactic */}
      {Object.keys(grouped).length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
            <FileCode2 className="h-8 w-8 mb-3 opacity-50" />
            <p className="font-medium">No patterns found</p>
            <p className="text-sm mt-1">Add detection patterns to enable MITRE auto-suggest.</p>
          </CardContent>
        </Card>
      ) : (
        Object.entries(grouped).map(([tactic, pats]) => (
          <Card key={tactic}>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">{TACTIC_LABELS[tactic] || tactic}</CardTitle>
              <CardDescription>{pats.length} pattern{pats.length !== 1 ? 's' : ''}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {pats.map(p => (
                  <div key={p.technique} className="flex items-start justify-between gap-3 p-3 rounded-lg border border-white/5 hover:bg-muted/30 transition-colors">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-sm font-medium text-orange-400">{p.technique}</span>
                        <span className="text-sm">{p.name}</span>
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0">{Math.round(p.weight * 100)}%</Badge>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {p.keywords.slice(0, 8).map(kw => (
                          <span key={kw} className="px-1.5 py-0.5 rounded text-[10px] bg-white/5 text-muted-foreground">{kw}</span>
                        ))}
                        {p.keywords.length > 8 && <span className="text-[10px] text-muted-foreground">+{p.keywords.length - 8} more</span>}
                      </div>
                      {p.regex.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {p.regex.map(rx => (
                            <span key={rx} className="px-1.5 py-0.5 rounded text-[10px] bg-blue-500/10 text-blue-400 font-mono">{rx}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <Button variant="ghost" size="sm" onClick={() => openEditModal(p)}>Edit</Button>
                      <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive/90" onClick={() => handleDelete(p)}><Trash2 className="h-3.5 w-3.5" /></Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ))
      )}

      {/* Add/Edit Modal */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingIdx !== null ? 'Edit' : 'Add'} Detection Pattern</DialogTitle>
            <DialogDescription>Define keywords and regex patterns for MITRE technique auto-detection.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Technique ID *</Label>
                <Input value={form.technique} onChange={e => setForm({ ...form, technique: e.target.value })} placeholder="T1059" />
              </div>
              <div className="space-y-2">
                <Label>Tactic *</Label>
                <Select value={form.tactic} onValueChange={v => setForm({ ...form, tactic: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {TACTICS.map(t => <SelectItem key={t} value={t}>{TACTIC_LABELS[t]}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Technique Name *</Label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Command and Scripting Interpreter" />
            </div>
            <div className="space-y-2">
              <Label>Keywords (comma-separated)</Label>
              <Textarea value={form.keywords} onChange={e => setForm({ ...form, keywords: e.target.value })} placeholder="powershell, cmd.exe, bash, python script" rows={3} />
              <p className="text-xs text-muted-foreground">Case-insensitive substrings matched against activity descriptions.</p>
            </div>
            <div className="space-y-2">
              <Label>Regex Patterns (one per line, optional)</Label>
              <Textarea value={form.regex} onChange={e => setForm({ ...form, regex: e.target.value })} placeholder="powershell\s*-enc&#10;IEX\s*\(" rows={2} className="font-mono text-xs" />
              <p className="text-xs text-muted-foreground">Python-compatible regex. Each match adds a 15% bonus to confidence.</p>
            </div>
            <div className="space-y-2">
              <Label>Base Weight (0.0 – 1.0)</Label>
              <Input type="number" step="0.05" min="0" max="1" value={form.weight} onChange={e => setForm({ ...form, weight: e.target.value })} />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowModal(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={!form.technique || !form.name}>
              <Save className="mr-2 h-4 w-4" />{editingIdx !== null ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
