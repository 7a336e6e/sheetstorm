/**
 * Threat Intel tab — MISP, VirusTotal, AbuseIPDB, HIBP, Shodan + MITRE settings.
 * Shows only threat-intel-category integrations with provider-specific UI.
 */

"use client"

import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Search, Loader2, Plus, Trash2, Zap, Shield, Globe, AlertTriangle, Brain } from 'lucide-react'
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

interface Integration {
  id: string; type: string; name: string; is_enabled: boolean
  config: Record<string, any>; has_credentials?: boolean
}

interface IntegrationType {
  id: string; name: string; description: string; category: string
  config_fields: string[]; credential_fields: string[]
}

const THREAT_INTEL_TYPES = new Set(['misp', 'virustotal', 'abuseipdb', 'hibp', 'shodan', 'mitre_attack'])

const PROVIDER_META: Record<string, { icon: string; color: string; description: string }> = {
  virustotal: { icon: '🛡️', color: 'text-blue-400', description: 'File, URL, and domain reputation scanning' },
  misp: { icon: '🔗', color: 'text-purple-400', description: 'Threat intelligence sharing platform' },
  abuseipdb: { icon: '🌐', color: 'text-red-400', description: 'IP address abuse reporting and checking' },
  hibp: { icon: '🔓', color: 'text-amber-400', description: 'Compromised email/credential checking' },
  shodan: { icon: '🔍', color: 'text-cyan-400', description: 'Internet-connected device search engine' },
  mitre_attack: { icon: '⚔️', color: 'text-orange-400', description: 'MITRE ATT&CK framework integration' },
}

const FIELD_LABELS: Record<string, string> = {
  api_key: 'API Key', api_url: 'API URL', url: 'URL',
  verify_ssl: 'Verify SSL', username: 'Username', password: 'Password',
  token: 'API Token',
}
const SECRET_FIELDS = new Set(['api_key', 'password', 'token'])

function MitreAutoSuggestTester() {
  const [text, setText] = useState('')
  const [results, setResults] = useState<{ technique: string; tactic: string; name: string; score: number }[]>([])
  const [loading, setLoading] = useState(false)
  const [patternCount, setPatternCount] = useState<number | null>(null)

  useEffect(() => {
    api.get<{ patterns: any[] }>('/mitre/patterns').then(d => setPatternCount(d.patterns?.length ?? 0)).catch(() => {})
  }, [])

  const testSuggest = useCallback(async () => {
    if (!text.trim()) return
    setLoading(true)
    try {
      const res = await api.post<{ suggestions: typeof results }>('/mitre/suggest', { activity: text, limit: 5 })
      setResults(res.suggestions || [])
    } catch { setResults([]) }
    finally { setLoading(false) }
  }, [text])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium flex items-center gap-2"><Brain className="h-4 w-4 text-orange-400" /> MITRE ATT&CK Auto-Suggest</CardTitle>
        <CardDescription>Test the pattern-based auto-suggestion engine. {patternCount !== null && <span>{patternCount} detection patterns loaded.</span>}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Textarea value={text} onChange={e => setText(e.target.value)} placeholder="Paste a timeline activity description to test MITRE auto-mapping..." rows={2} />
        <div className="flex items-center gap-3">
          <Button size="sm" onClick={testSuggest} disabled={loading || !text.trim()}>
            {loading ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Zap className="mr-1.5 h-3.5 w-3.5" />}
            Test Suggestions
          </Button>
          {results.length > 0 && <span className="text-xs text-muted-foreground">{results.length} match{results.length !== 1 ? 'es' : ''}</span>}
        </div>
        {results.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {results.map(r => (
              <div key={r.technique} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs bg-orange-500/10 border border-orange-500/20 text-orange-300">
                <span className="font-mono font-medium">{r.technique}</span>
                <span className="text-orange-200/70">{r.name}</span>
                <Badge variant="outline" className="ml-1 text-[10px] px-1 py-0 border-orange-500/30">{Math.round(r.score * 100)}%</Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function ThreatIntelTab() {
  const { toast } = useToast()
  const confirm = useConfirm()
  const [loading, setLoading] = useState(true)
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [integrationTypes, setIntegrationTypes] = useState<IntegrationType[]>([])
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ id: string; success: boolean; message: string } | null>(null)

  // Modal
  const [showModal, setShowModal] = useState(false)
  const [editingIntegration, setEditingIntegration] = useState<Integration | null>(null)
  const [form, setForm] = useState({ type: 'virustotal', name: '', config: {} as any, credentials: {} as any, is_enabled: true })

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    try {
      const [intRes, typesRes] = await Promise.all([
        api.get<{ items: Integration[] }>('/integrations'),
        api.get<{ types: IntegrationType[] }>('/integrations/types').catch(() => ({ types: [] })),
      ])
      setIntegrations((intRes.items || []).filter(i => THREAT_INTEL_TYPES.has(i.type)))
      setIntegrationTypes((typesRes.types || []).filter(t => THREAT_INTEL_TYPES.has(t.id)))
    } catch { toast({ title: 'Error', variant: 'destructive' }) }
    finally { setLoading(false) }
  }

  const getTypeInfo = (id: string) => integrationTypes.find(t => t.id === id)

  const openModal = (int?: Integration) => {
    if (int) {
      setEditingIntegration(int)
      setForm({ type: int.type, name: int.name, config: { ...int.config }, credentials: {}, is_enabled: int.is_enabled })
    } else {
      setEditingIntegration(null)
      const first = integrationTypes[0]?.id || 'virustotal'
      setForm({ type: first, name: '', config: {}, credentials: {}, is_enabled: true })
    }
    setShowModal(true)
  }

  const handleSave = async () => {
    if (!form.name) return
    setSaving(true)
    try {
      const payload: any = { type: form.type, name: form.name, config: form.config, is_enabled: form.is_enabled }
      if (Object.keys(form.credentials).length > 0) payload.credentials = form.credentials
      if (editingIntegration) await api.put(`/integrations/${editingIntegration.id}`, payload)
      else await api.post('/integrations', payload)
      toast({ title: 'Success' }); setShowModal(false); loadData()
    } catch { toast({ title: 'Error', variant: 'destructive' }) }
    finally { setSaving(false) }
  }

  const handleDelete = async (id: string) => {
    const ok = await confirm({ title: 'Delete Integration', description: 'Remove this threat intel integration?', confirmLabel: 'Delete', variant: 'destructive' })
    if (!ok) return
    try { await api.delete(`/integrations/${id}`); toast({ title: 'Deleted' }); setIntegrations(prev => prev.filter(i => i.id !== id)) }
    catch { toast({ title: 'Error', variant: 'destructive' }) }
  }

  const handleTest = async (id: string) => {
    setTesting(id); setTestResult(null)
    try {
      const res = await api.post<{ success: boolean; message: string }>(`/integrations/${id}/test`)
      setTestResult({ id, success: res.success, message: res.message })
    } catch (e: any) { setTestResult({ id, success: false, message: e?.message || 'Test failed' }) }
    finally { setTesting(null) }
  }

  const selectedTypeInfo = getTypeInfo(form.type)

  if (loading) {
    return <div className="flex items-center justify-center p-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
  }

  // Configured vs available
  const configuredTypes = new Set(integrations.map(i => i.type))
  const availableTypes = integrationTypes.filter(t => !configuredTypes.has(t.id))

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h3 className="text-lg font-medium">Threat Intelligence</h3>
          <p className="text-sm text-muted-foreground">
            {integrations.length} configured · {integrations.filter(i => i.is_enabled).length} active
          </p>
        </div>
        <Button onClick={() => openModal()}><Plus className="mr-2 h-4 w-4" /> Add Provider</Button>
      </div>

      {/* Configured Integrations */}
      {integrations.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
            <Search className="h-8 w-8 mb-3 opacity-50" />
            <p className="font-medium">No threat intel providers configured</p>
            <p className="text-sm mt-1">Add VirusTotal, MISP, or Shodan to enrich IOCs automatically.</p>
            <Button variant="link" onClick={() => openModal()}>Add a provider</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {integrations.map(int => {
            const meta = PROVIDER_META[int.type]
            return (
              <Card key={int.id}>
                <CardContent className="flex items-center justify-between p-5">
                  <div className="flex items-center gap-4">
                    <div className={`w-10 h-10 rounded-lg bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 flex items-center justify-center text-lg`}>
                      {meta?.icon || '🔍'}
                    </div>
                    <div>
                      <h4 className="font-medium flex items-center gap-2">
                        {int.name}
                        {int.is_enabled ? <Badge variant="outline" className="text-green-400 border-green-500/30 text-xs">Active</Badge> : <Badge variant="outline" className="text-muted-foreground text-xs">Disabled</Badge>}
                      </h4>
                      <p className="text-sm text-muted-foreground">{meta?.description || int.type}</p>
                      {testResult?.id === int.id && (
                        <p className={`text-xs mt-1 ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>{testResult.success ? '✓' : '✗'} {testResult.message}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={() => handleTest(int.id)} disabled={testing === int.id || !int.is_enabled}>
                      {testing === int.id ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Zap className="mr-1.5 h-3.5 w-3.5" />}Test
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => openModal(int)}>Configure</Button>
                    <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive/90" onClick={() => handleDelete(int.id)}><Trash2 className="h-4 w-4" /></Button>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* Available types */}
      {availableTypes.length > 0 && (
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Available Providers</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {availableTypes.map(t => {
                const meta = PROVIDER_META[t.id]
                return (
                  <button
                    key={t.id}
                    onClick={() => {
                      setEditingIntegration(null)
                      setForm({ type: t.id, name: t.name, config: {}, credentials: {}, is_enabled: true })
                      setShowModal(true)
                    }}
                    className="flex items-center gap-3 p-3 rounded-lg border border-dashed hover:bg-muted/50 transition-colors text-left"
                  >
                    <span className="text-lg">{meta?.icon || '🔍'}</span>
                    <div>
                      <p className="text-sm font-medium">{t.name}</p>
                      <p className="text-xs text-muted-foreground">{meta?.description || t.description}</p>
                    </div>
                  </button>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Modal */}
      <MitreAutoSuggestTester />
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingIntegration ? 'Edit' : 'Add'} Threat Intel Provider</DialogTitle>
            <DialogDescription>{selectedTypeInfo?.description || 'Configure a threat intelligence provider.'}</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-2">
              <Label>Provider</Label>
              <Select value={form.type} onValueChange={v => { const info = getTypeInfo(v); setForm({ ...form, type: v, name: form.name || info?.name || '', config: {}, credentials: {} }) }} disabled={!!editingIntegration}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {integrationTypes.map(t => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Display Name</Label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder={selectedTypeInfo?.name || 'Provider name'} />
            </div>
            {selectedTypeInfo?.config_fields && selectedTypeInfo.config_fields.length > 0 && (
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Configuration</p>
                {selectedTypeInfo.config_fields.map(field => (
                  <div key={field} className="space-y-1">
                    <Label className="text-sm">{FIELD_LABELS[field] || field}</Label>
                    <Input value={form.config[field] || ''} onChange={e => setForm({ ...form, config: { ...form.config, [field]: e.target.value } })} placeholder={FIELD_LABELS[field] || field} />
                  </div>
                ))}
              </div>
            )}
            {selectedTypeInfo?.credential_fields && selectedTypeInfo.credential_fields.length > 0 && (
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Credentials</p>
                {editingIntegration?.has_credentials && <p className="text-xs text-amber-400">Leave blank to keep current values.</p>}
                {selectedTypeInfo.credential_fields.map(field => (
                  <div key={field} className="space-y-1">
                    <Label className="text-sm">{FIELD_LABELS[field] || field}</Label>
                    <Input type={SECRET_FIELDS.has(field) ? 'password' : 'text'} value={form.credentials[field] || ''} onChange={e => setForm({ ...form, credentials: { ...form.credentials, [field]: e.target.value } })} placeholder={editingIntegration?.has_credentials ? '(unchanged)' : (FIELD_LABELS[field] || field)} />
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-center space-x-2 pt-2">
              <Switch id="enable-ti" checked={form.is_enabled} onCheckedChange={c => setForm({ ...form, is_enabled: c })} />
              <Label htmlFor="enable-ti">Enable this provider</Label>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowModal(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving || !form.name}>{saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{editingIntegration ? 'Update' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
