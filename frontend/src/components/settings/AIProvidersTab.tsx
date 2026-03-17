/**
 * AI Providers tab — Configure OpenAI, Google Gemini, and Ollama integrations.
 * Shows only AI-category integrations with provider-specific UI.
 */

"use client"

import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Zap, Loader2, Plus, Trash2, CheckCircle, RefreshCw, AlertTriangle } from 'lucide-react'
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
  config_fields: string[]; credential_fields: string[]; doc_url?: string
}

interface OllamaModel {
  name: string; size: number; modified_at: string
}

const AI_TYPES = new Set(['openai', 'google_ai', 'ollama'])

const FIELD_LABELS: Record<string, string> = {
  api_key: 'API Key', model: 'Model', base_url: 'Base URL',
  timeout: 'Timeout (seconds)', api_url: 'API URL',
}
const SECRET_FIELDS = new Set(['api_key'])

export function AIProvidersTab() {
  const { toast } = useToast()
  const confirm = useConfirm()
  const [loading, setLoading] = useState(true)
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [integrationTypes, setIntegrationTypes] = useState<IntegrationType[]>([])
  const [saving, setSaving] = useState<string | null>(null)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ id: string; success: boolean; message: string } | null>(null)

  // Modal
  const [showModal, setShowModal] = useState(false)
  const [editingIntegration, setEditingIntegration] = useState<Integration | null>(null)
  const [form, setForm] = useState({ type: 'openai', name: '', config: {} as any, credentials: {} as any, is_enabled: true })

  // Ollama model discovery
  const [ollamaModels, setOllamaModels] = useState<OllamaModel[]>([])
  const [ollamaLoading, setOllamaLoading] = useState(false)

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    try {
      const [intRes, typesRes] = await Promise.all([
        api.get<{ items: Integration[] }>('/integrations'),
        api.get<{ types: IntegrationType[] }>('/integrations/types').catch(() => ({ types: [] })),
      ])
      setIntegrations((intRes.items || []).filter(i => AI_TYPES.has(i.type)))
      setIntegrationTypes((typesRes.types || []).filter(t => AI_TYPES.has(t.id)))
    } catch { toast({ title: 'Error', description: 'Failed to load AI providers', variant: 'destructive' }) }
    finally { setLoading(false) }
  }

  const discoverOllamaModels = async () => {
    setOllamaLoading(true)
    try {
      const res = await api.get<{ models: OllamaModel[] }>('/integrations/ollama/models')
      setOllamaModels(res.models || [])
      toast({ title: 'Models Discovered', description: `Found ${res.models?.length || 0} models` })
    } catch {
      toast({ title: 'Error', description: 'Failed to discover Ollama models. Is Ollama running?', variant: 'destructive' })
    } finally { setOllamaLoading(false) }
  }

  const openModal = (integration?: Integration) => {
    if (integration) {
      setEditingIntegration(integration)
      setForm({ type: integration.type, name: integration.name, config: { ...integration.config }, credentials: {}, is_enabled: integration.is_enabled })
    } else {
      setEditingIntegration(null)
      setForm({ type: 'openai', name: '', config: {}, credentials: {}, is_enabled: true })
    }
    setShowModal(true)
  }

  const handleDelete = async (id: string) => {
    const ok = await confirm({ title: 'Delete AI Provider', description: 'Remove this AI provider configuration?', confirmLabel: 'Delete', variant: 'destructive' })
    if (!ok) return
    try { await api.delete(`/integrations/${id}`); toast({ title: 'Deleted' }); setIntegrations(prev => prev.filter(i => i.id !== id)) }
    catch { toast({ title: 'Error', variant: 'destructive' }) }
  }

  const handleTest = async (id: string) => {
    setTesting(id); setTestResult(null)
    try {
      const res = await api.post<{ success: boolean; message: string }>(`/integrations/${id}/test`)
      setTestResult({ id, success: res.success, message: res.message })
      toast({ title: res.success ? 'Connection Successful' : 'Connection Failed', description: res.message, variant: res.success ? 'default' : 'destructive' })
    } catch (e: any) { const m = e?.message || 'Test failed'; setTestResult({ id, success: false, message: m }) }
    finally { setTesting(null) }
  }

  const handleSave = async () => {
    if (!form.name) return
    setSaving('ai')
    try {
      const payload: any = { type: form.type, name: form.name, config: form.config, is_enabled: form.is_enabled }
      if (Object.keys(form.credentials).length > 0) payload.credentials = form.credentials
      if (editingIntegration) await api.put(`/integrations/${editingIntegration.id}`, payload)
      else await api.post('/integrations', payload)
      toast({ title: 'Success', description: `AI provider ${editingIntegration ? 'updated' : 'created'}` })
      setShowModal(false); loadData()
    } catch { toast({ title: 'Error', description: 'Failed to save AI provider', variant: 'destructive' }) }
    finally { setSaving(null) }
  }

  const getTypeInfo = (typeId: string) => integrationTypes.find(t => t.id === typeId)

  const providerIcon = (type: string) => {
    switch (type) {
      case 'openai': return '🤖'
      case 'google_ai': return '✨'
      case 'ollama': return '🦙'
      default: return '⚡'
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center p-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h3 className="text-lg font-medium">AI Providers</h3>
          <p className="text-sm text-muted-foreground">Configure AI providers for report generation and analysis</p>
        </div>
        <Button onClick={() => openModal()}><Plus className="mr-2 h-4 w-4" /> Add AI Provider</Button>
      </div>

      {integrations.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
            <Zap className="h-8 w-8 mb-3 opacity-50" />
            <p className="font-medium">No AI providers configured</p>
            <p className="text-sm mt-1">Add OpenAI, Google Gemini, or Ollama to enable AI-powered reports</p>
            <Button variant="link" onClick={() => openModal()}>Add AI Provider</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {integrations.map(int => {
            const typeInfo = getTypeInfo(int.type)
            return (
              <Card key={int.id}>
                <CardContent className="flex items-center justify-between p-5">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-lg">
                      {providerIcon(int.type)}
                    </div>
                    <div>
                      <h4 className="font-medium flex items-center gap-2">
                        {int.name}
                        {int.is_enabled ? (
                          <Badge variant="outline" className="text-green-400 border-green-500/30 text-xs">Active</Badge>
                        ) : (
                          <Badge variant="outline" className="text-muted-foreground text-xs">Disabled</Badge>
                        )}
                      </h4>
                      <p className="text-sm text-muted-foreground">
                        {typeInfo?.description || int.type}
                        {int.config?.model && <span className="ml-2 text-xs">Model: {int.config.model}</span>}
                        {int.type === 'ollama' && int.config?.base_url && <span className="ml-2 text-xs">({int.config.base_url})</span>}
                      </p>
                      {testResult?.id === int.id && (
                        <p className={`text-xs mt-1 ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>
                          {testResult.success ? '✓' : '✗'} {testResult.message}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {int.type === 'ollama' && (
                      <Button variant="outline" size="sm" onClick={discoverOllamaModels} disabled={ollamaLoading}>
                        {ollamaLoading ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1.5 h-3.5 w-3.5" />}
                        Models
                      </Button>
                    )}
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

      {/* Ollama Models Discovery */}
      {ollamaModels.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Available Ollama Models</CardTitle>
            <CardDescription>Models installed on your Ollama instance</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {ollamaModels.map(m => (
                <div key={m.name} className="flex items-center justify-between p-2 rounded border text-sm">
                  <span className="font-medium">{m.name}</span>
                  <span className="text-xs text-muted-foreground">{(m.size / 1e9).toFixed(1)} GB</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Provider tips */}
      <Card className="border-dashed">
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-4 w-4 text-amber-400 mt-0.5 shrink-0" />
            <div className="text-sm text-muted-foreground space-y-1">
              <p><strong>Priority order:</strong> The platform tries providers in the order they were added. The first active provider is used for report generation.</p>
              <p><strong>Ollama:</strong> For local/self-hosted AI. Default timeout is 120 seconds for large models. Ensure Ollama is running and accessible from the backend.</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Modal */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingIntegration ? 'Edit' : 'Add'} AI Provider</DialogTitle>
            <DialogDescription>Configure an AI provider for report generation</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-2">
              <Label>Provider Type</Label>
              <Select value={form.type} onValueChange={v => setForm({ ...form, type: v, name: form.name || getTypeInfo(v)?.name || '', config: v === 'ollama' ? { base_url: 'http://localhost:11434', model: 'llama3', timeout: '120' } : {}, credentials: {} })} disabled={!!editingIntegration}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {integrationTypes.map(t => (
                    <SelectItem key={t.id} value={t.id}>
                      <span>{providerIcon(t.id)} {t.name}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Display Name</Label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Production OpenAI" />
            </div>

            {/* Dynamic fields */}
            {getTypeInfo(form.type)?.config_fields?.map(field => (
              <div key={field} className="space-y-1">
                <Label className="text-sm">{FIELD_LABELS[field] || field}</Label>
                <Input value={form.config[field] || ''} onChange={e => setForm({ ...form, config: { ...form.config, [field]: e.target.value } })} placeholder={FIELD_LABELS[field] || field} />
              </div>
            ))}
            {getTypeInfo(form.type)?.credential_fields?.map(field => (
              <div key={field} className="space-y-1">
                <Label className="text-sm">{FIELD_LABELS[field] || field}</Label>
                <Input type={SECRET_FIELDS.has(field) ? 'password' : 'text'} value={form.credentials[field] || ''} onChange={e => setForm({ ...form, credentials: { ...form.credentials, [field]: e.target.value } })} placeholder={editingIntegration?.has_credentials ? '(unchanged)' : (FIELD_LABELS[field] || field)} />
              </div>
            ))}

            {/* Ollama-specific: model selector if models discovered */}
            {form.type === 'ollama' && ollamaModels.length > 0 && (
              <div className="space-y-1">
                <Label className="text-sm">Select Discovered Model</Label>
                <Select value={form.config.model || ''} onValueChange={v => setForm({ ...form, config: { ...form.config, model: v } })}>
                  <SelectTrigger><SelectValue placeholder="Select a model" /></SelectTrigger>
                  <SelectContent>
                    {ollamaModels.map(m => (
                      <SelectItem key={m.name} value={m.name}>{m.name} ({(m.size / 1e9).toFixed(1)} GB)</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="flex items-center space-x-2 pt-2">
              <Switch id="enable-ai" checked={form.is_enabled} onCheckedChange={c => setForm({ ...form, is_enabled: c })} />
              <Label htmlFor="enable-ai">Enable this provider</Label>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowModal(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={!!saving || !form.name}>{saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{editingIntegration ? 'Update' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
