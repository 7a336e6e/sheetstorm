/**
 * Integrations tab — full CRUD for integration configs, test connection,
 * Google Drive OAuth, category filtering. Extracted from the old settings page.
 */

"use client"

import { useState, useEffect, useCallback } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import {
  Bell, Shield, Database, Slack, Mail, Key, Loader2, CheckCircle, Plus,
  Trash2, Zap, Server, Search, Bug, FileText, Link2, Unlink, FolderOpen, ChevronRight,
} from 'lucide-react'
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
  id: string
  type: string
  name: string
  is_enabled: boolean
  config: Record<string, any>
  has_credentials?: boolean
}

interface IntegrationType {
  id: string
  name: string
  description: string
  category: string
  config_fields: string[]
  credential_fields: string[]
  doc_url?: string
}

const CATEGORY_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  ai: { label: 'AI & Analysis', icon: <Zap className="h-4 w-4" />, color: 'text-purple-400' },
  notification: { label: 'Notifications', icon: <Bell className="h-4 w-4" />, color: 'text-blue-400' },
  storage: { label: 'Storage', icon: <Database className="h-4 w-4" />, color: 'text-green-400' },
  auth: { label: 'Authentication', icon: <Shield className="h-4 w-4" />, color: 'text-cyan-400' },
  threat_intel: { label: 'Threat Intel', icon: <Search className="h-4 w-4" />, color: 'text-red-400' },
  ir_tools: { label: 'IR Tools', icon: <Bug className="h-4 w-4" />, color: 'text-orange-400' },
  ticketing: { label: 'Ticketing', icon: <FileText className="h-4 w-4" />, color: 'text-yellow-400' },
  siem: { label: 'SIEM / Log Management', icon: <Server className="h-4 w-4" />, color: 'text-teal-400' },
}

const FIELD_LABELS: Record<string, string> = {
  api_key: 'API Key',
  api_url: 'API URL',
  webhook_url: 'Webhook URL',
  bucket_name: 'Bucket Name',
  region: 'Region',
  endpoint_url: 'Endpoint URL',
  access_key: 'Access Key',
  secret_key: 'Secret Key',
  client_id: 'Client ID',
  client_secret: 'Client Secret',
  model: 'Model',
  smtp_host: 'SMTP Host',
  smtp_port: 'SMTP Port',
  smtp_user: 'Username',
  smtp_password: 'Password',
  from_address: 'From Address',
  url: 'URL',
  project_key: 'Project Key',
  username: 'Username',
  password: 'Password',
  token: 'API Token',
  index: 'Index',
  verify_ssl: 'Verify SSL',
  redirect_uri: 'Redirect URI',
  base_url: 'Base URL',
  timeout: 'Timeout (seconds)',
}

const SECRET_FIELDS = new Set([
  'api_key', 'secret_key', 'client_secret', 'smtp_password', 'password', 'token', 'webhook_url', 'access_key',
])

/** Categories to hide from the generic Integrations tab (they have their own tabs) */
const HIDDEN_CATEGORIES = new Set(['ai', 'storage'])

export function IntegrationsTab() {
  const { toast } = useToast()
  const confirm = useConfirm()
  const router = useRouter()
  const searchParams = useSearchParams()

  const [loading, setLoading] = useState(true)
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [integrationTypes, setIntegrationTypes] = useState<IntegrationType[]>([])
  const [saving, setSaving] = useState<string | null>(null)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ id: string; success: boolean; message: string } | null>(null)

  // Modal
  const [showModal, setShowModal] = useState(false)
  const [editingIntegration, setEditingIntegration] = useState<Integration | null>(null)
  const [form, setForm] = useState({ type: 'slack', name: '', config: {} as any, credentials: {} as any, is_enabled: true })

  const [categoryFilter, setCategoryFilter] = useState<string>('all')

  // Google Drive OAuth
  const [driveStatus, setDriveStatus] = useState<{
    configured: boolean; connected: boolean; email?: string;
    display_name?: string; root_folder_id?: string; root_folder_name?: string;
  } | null>(null)
  const [driveLoading, setDriveLoading] = useState(false)
  const [showFolderPicker, setShowFolderPicker] = useState(false)
  const [driveFolders, setDriveFolders] = useState<{ id: string; name: string }[]>([])
  const [folderStack, setFolderStack] = useState<{ id: string; name: string }[]>([{ id: 'root', name: 'My Drive' }])
  const [foldersLoading, setFoldersLoading] = useState(false)

  const loadDriveStatus = useCallback(async () => {
    try {
      const res = await api.get<any>('/google-drive/status')
      setDriveStatus(res)
    } catch { setDriveStatus(null) }
  }, [])

  useEffect(() => {
    const driveConnected = searchParams.get('drive_connected')
    const driveToken = searchParams.get('drive_token')
    const driveRefresh = searchParams.get('drive_refresh')
    const driveError = searchParams.get('drive_error')
    if (driveError) {
      toast({ title: 'Google Drive Error', description: driveError, variant: 'destructive' })
      router.replace('/dashboard/admin/settings?tab=integrations')
      return
    }
    if (driveConnected === 'true' && driveToken && driveRefresh) {
      setDriveLoading(true)
      api.post('/google-drive/connect', { access_token: driveToken, refresh_token: driveRefresh })
        .then(() => { toast({ title: 'Google Drive Connected' }); loadDriveStatus(); loadData(); setShowFolderPicker(true) })
        .catch(() => toast({ title: 'Connection Failed', variant: 'destructive' }))
        .finally(() => { setDriveLoading(false); router.replace('/dashboard/admin/settings?tab=integrations') })
    }
  }, [searchParams])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { loadData(); loadDriveStatus() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const loadData = async () => {
    try {
      const [intRes, typesRes] = await Promise.all([
        api.get<{ items: Integration[] }>('/integrations'),
        api.get<{ types: IntegrationType[] }>('/integrations/types').catch(() => ({ types: [] })),
      ])
      setIntegrations(intRes.items || [])
      setIntegrationTypes(typesRes.types || [])
    } catch { toast({ title: 'Error', description: 'Failed to load integrations', variant: 'destructive' }) }
    finally { setLoading(false) }
  }

  // Google Drive helpers
  const handleDriveConnect = async () => {
    setDriveLoading(true)
    try {
      const res = await api.post<{ auth_url: string }>('/google-drive/auth')
      window.location.href = res.auth_url
    } catch { toast({ title: 'Error', description: 'Could not start Google Drive OAuth', variant: 'destructive' }); setDriveLoading(false) }
  }
  const handleDriveDisconnect = async () => {
    const ok = await confirm({ title: 'Disconnect Google Drive', description: 'Existing files in Drive will not be deleted.', confirmLabel: 'Disconnect', variant: 'destructive' })
    if (!ok) return
    try { await api.post('/google-drive/disconnect'); toast({ title: 'Disconnected' }); setDriveStatus(prev => prev ? { ...prev, connected: false, email: undefined, root_folder_id: undefined, root_folder_name: undefined } : null); loadData() }
    catch { toast({ title: 'Error', variant: 'destructive' }) }
  }
  const loadDriveFolders = async (parentId: string) => {
    setFoldersLoading(true)
    try { const res = await api.get<{ folders: { id: string; name: string }[] }>(`/google-drive/folders?parent_id=${parentId}`); setDriveFolders(res.folders || []) }
    catch { toast({ title: 'Error', description: 'Could not load folders', variant: 'destructive' }) }
    finally { setFoldersLoading(false) }
  }
  const openFolderPicker = () => { setFolderStack([{ id: 'root', name: 'My Drive' }]); setDriveFolders([]); setShowFolderPicker(true); loadDriveFolders('root') }
  const navigateToFolder = (f: { id: string; name: string }) => { setFolderStack(prev => [...prev, f]); loadDriveFolders(f.id) }
  const navigateBack = (i: number) => { const s = folderStack.slice(0, i + 1); setFolderStack(s); loadDriveFolders(s[s.length - 1].id) }
  const selectRootFolder = async () => {
    const c = folderStack[folderStack.length - 1]
    try { await api.post('/google-drive/set-root', { folder_id: c.id, folder_name: c.name }); toast({ title: 'Root Folder Set' }); setShowFolderPicker(false); loadDriveStatus() }
    catch { toast({ title: 'Error', variant: 'destructive' }) }
  }
  const isGoogleDrive = (typeId: string) => typeId === 'google_drive'

  // CRUD helpers
  const openModal = (integration?: Integration) => {
    if (integration) {
      setEditingIntegration(integration)
      setForm({ type: integration.type, name: integration.name, config: { ...integration.config }, credentials: {}, is_enabled: integration.is_enabled })
    } else {
      setEditingIntegration(null)
      const first = visibleTypes[0]?.id || 'slack'
      setForm({ type: first, name: '', config: {}, credentials: {}, is_enabled: true })
    }
    setShowModal(true)
  }
  const handleDelete = async (id: string) => {
    const ok = await confirm({ title: 'Delete Integration', description: 'Are you sure?', confirmLabel: 'Delete', variant: 'destructive' })
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
    } catch (e: any) { const m = e?.message || 'Test failed'; setTestResult({ id, success: false, message: m }); toast({ title: 'Test Failed', description: m, variant: 'destructive' }) }
    finally { setTesting(null) }
  }
  const handleSave = async () => {
    if (!form.name) return
    setSaving('integration')
    try {
      const payload: any = { type: form.type, name: form.name, config: form.config, is_enabled: form.is_enabled }
      if (Object.keys(form.credentials).length > 0) payload.credentials = form.credentials
      if (editingIntegration) await api.put(`/integrations/${editingIntegration.id}`, payload)
      else await api.post('/integrations', payload)
      toast({ title: 'Success', description: `Integration ${editingIntegration ? 'updated' : 'created'}` })
      setShowModal(false); loadData()
    } catch { toast({ title: 'Error', description: 'Failed to save integration', variant: 'destructive' }) }
    finally { setSaving(null) }
  }

  const getTypeInfo = (typeId: string) => integrationTypes.find(t => t.id === typeId)
  const getTypeIcon = (typeId: string) => {
    const cat = CATEGORY_META[getTypeInfo(typeId)?.category || '']
    if (typeId.includes('slack')) return <Slack className="h-5 w-5" />
    if (typeId.includes('email') || typeId.includes('smtp')) return <Mail className="h-5 w-5" />
    if (cat) return cat.icon
    return <Key className="h-5 w-5" />
  }
  const selectedTypeInfo = getTypeInfo(form.type)

  // Filter out categories that have their own tabs
  const visibleTypes = integrationTypes.filter(t => !HIDDEN_CATEGORIES.has(t.category))
  const visibleIntegrations = integrations.filter(i => !HIDDEN_CATEGORIES.has(getTypeInfo(i.type)?.category || ''))
  const categories = visibleTypes.reduce((acc, t) => { const c = t.category || 'other'; if (!acc[c]) acc[c] = []; acc[c].push(t); return acc }, {} as Record<string, IntegrationType[]>)
  const filteredIntegrations = categoryFilter === 'all' ? visibleIntegrations : visibleIntegrations.filter(i => getTypeInfo(i.type)?.category === categoryFilter)

  if (loading) {
    return <div className="flex items-center justify-center p-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h3 className="text-lg font-medium">Integrations</h3>
          <p className="text-sm text-muted-foreground">
            {visibleIntegrations.length} configured · {visibleIntegrations.filter(i => i.is_enabled).length} active
          </p>
        </div>
        <Button onClick={() => openModal()}><Plus className="mr-2 h-4 w-4" /> Add Integration</Button>
      </div>

      {/* Category Filters */}
      <div className="flex flex-wrap gap-2">
        <Button variant={categoryFilter === 'all' ? 'default' : 'outline'} size="sm" onClick={() => setCategoryFilter('all')}>
          All ({visibleIntegrations.length})
        </Button>
        {Object.entries(CATEGORY_META).filter(([k]) => !HIDDEN_CATEGORIES.has(k)).map(([key, meta]) => {
          const count = visibleIntegrations.filter(i => getTypeInfo(i.type)?.category === key).length
          if (count === 0 && !categories[key]) return null
          return (
            <Button key={key} variant={categoryFilter === key ? 'default' : 'outline'} size="sm" onClick={() => setCategoryFilter(key)} className="gap-1.5">
              {meta.icon}{meta.label}{count > 0 && <span className="ml-1 text-xs opacity-60">({count})</span>}
            </Button>
          )
        })}
      </div>

      {/* Integration Cards */}
      <div className="grid gap-4">
        {filteredIntegrations.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center justify-center p-6 text-center text-muted-foreground">
              <div className="w-12 h-12 bg-muted/50 rounded-full flex items-center justify-center mb-4"><Shield className="h-6 w-6" /></div>
              <p>{categoryFilter !== 'all' ? 'No integrations in this category' : 'No integrations configured'}</p>
              <Button variant="link" onClick={() => openModal()}>Add your first integration</Button>
            </CardContent>
          </Card>
        ) : (
          filteredIntegrations.map(integration => {
            const typeInfo = getTypeInfo(integration.type)
            const catMeta = CATEGORY_META[typeInfo?.category || '']
            const isDrive = isGoogleDrive(integration.type)
            return (
              <Card key={integration.id}>
                <CardContent className="flex items-center justify-between p-5">
                  <div className="flex items-center gap-4">
                    <div className={`w-10 h-10 rounded-lg bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 flex items-center justify-center ${catMeta?.color || 'text-muted-foreground'}`}>
                      {getTypeIcon(integration.type)}
                    </div>
                    <div>
                      <h4 className="font-medium flex items-center gap-2">
                        {integration.name}
                        {integration.is_enabled ? (
                          <Badge variant="outline" className="text-green-400 border-green-500/30 text-xs">Active</Badge>
                        ) : (
                          <Badge variant="outline" className="text-muted-foreground text-xs">Disabled</Badge>
                        )}
                        {isDrive && driveStatus?.connected && (
                          <Badge variant="outline" className="text-cyan-400 border-cyan-500/30 text-xs">Connected</Badge>
                        )}
                      </h4>
                      <p className="text-sm text-muted-foreground">
                        {typeInfo?.description || integration.type}
                        {catMeta && <span className="ml-2 text-xs opacity-50">· {catMeta.label}</span>}
                        {typeInfo?.doc_url && (
                          <a href={typeInfo.doc_url} target="_blank" rel="noopener noreferrer" className="ml-2 text-xs text-blue-400 hover:underline">Docs</a>
                        )}
                      </p>
                      {isDrive && driveStatus?.connected && driveStatus.email && (
                        <p className="text-xs mt-1 text-cyan-400/80">
                          {driveStatus.email}
                          {driveStatus.root_folder_name && <span className="ml-2 text-muted-foreground">· Root: {driveStatus.root_folder_name}</span>}
                        </p>
                      )}
                      {isDrive && driveStatus && !driveStatus.connected && driveStatus.configured && (
                        <p className="text-xs mt-1 text-amber-400">Not connected — click Connect to link your Google account</p>
                      )}
                      {testResult?.id === integration.id && (
                        <p className={`text-xs mt-1 ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>{testResult.success ? '✓' : '✗'} {testResult.message}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {isDrive && driveStatus?.configured && !driveStatus.connected && (
                      <Button variant="outline" size="sm" onClick={handleDriveConnect} disabled={driveLoading} className="text-cyan-400 border-cyan-500/30 hover:bg-cyan-500/10">
                        {driveLoading ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Link2 className="mr-1.5 h-3.5 w-3.5" />}Connect
                      </Button>
                    )}
                    {isDrive && driveStatus?.connected && (
                      <>
                        <Button variant="outline" size="sm" onClick={openFolderPicker}><FolderOpen className="mr-1.5 h-3.5 w-3.5" />{driveStatus.root_folder_id && driveStatus.root_folder_id !== 'root' ? 'Change Folder' : 'Set Folder'}</Button>
                        <Button variant="outline" size="sm" onClick={handleDriveDisconnect} className="text-destructive border-destructive/30 hover:bg-destructive/10"><Unlink className="mr-1.5 h-3.5 w-3.5" />Disconnect</Button>
                      </>
                    )}
                    <Button variant="outline" size="sm" onClick={() => handleTest(integration.id)} disabled={testing === integration.id || !integration.is_enabled}>
                      {testing === integration.id ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Zap className="mr-1.5 h-3.5 w-3.5" />}Test
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => openModal(integration)}>Configure</Button>
                    <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive/90" onClick={() => handleDelete(integration.id)}><Trash2 className="h-4 w-4" /></Button>
                  </div>
                </CardContent>
              </Card>
            )
          })
        )}
      </div>

      {/* Available integration types */}
      {categoryFilter === 'all' && (
        <div className="mt-8 space-y-4">
          <h4 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Available Integration Types</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {Object.entries(categories).map(([cat, types]) => {
              const meta = CATEGORY_META[cat]
              if (!meta) return null
              return (
                <Card key={cat} className="border-dashed">
                  <CardContent className="p-4">
                    <div className={`flex items-center gap-2 mb-2 ${meta.color}`}>
                      {meta.icon}<span className="font-medium text-sm">{meta.label}</span>
                    </div>
                    <div className="space-y-1">
                      {types.map(t => {
                        const isConfigured = integrations.some(i => i.type === t.id)
                        return (
                          <div key={t.id} className="flex items-center justify-between text-sm">
                            <span className={isConfigured ? 'text-foreground' : 'text-muted-foreground'}>{t.name}</span>
                            {isConfigured ? <CheckCircle className="h-3.5 w-3.5 text-green-400" /> : (
                              <button onClick={() => { setEditingIntegration(null); setForm({ type: t.id, name: t.name, config: {}, credentials: {}, is_enabled: true }); setShowModal(true) }} className="text-xs text-muted-foreground hover:text-foreground transition-colors">+ Add</button>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </div>
      )}

      {/* Integration Modal */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingIntegration ? 'Edit' : 'Add'} Integration</DialogTitle>
            <DialogDescription>{selectedTypeInfo?.description || 'Connect external services to the platform.'}</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-2">
              <Label>Integration Type</Label>
              <Select value={form.type} onValueChange={v => { const info = getTypeInfo(v); setForm({ ...form, type: v, name: form.name || info?.name || '', config: {}, credentials: {} }) }} disabled={!!editingIntegration}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(categories).map(([cat, types]) => {
                    const meta = CATEGORY_META[cat]
                    return types.map((t, idx) => (
                      <SelectItem key={t.id} value={t.id}><span>{idx === 0 && meta ? `[${meta.label}] ` : ''}{t.name}</span></SelectItem>
                    ))
                  })}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Display Name</Label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder={selectedTypeInfo?.name || 'Integration name'} />
            </div>
            {selectedTypeInfo?.config_fields?.length ? (
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Configuration</p>
                {selectedTypeInfo.config_fields.map(field => (
                  <div key={field} className="space-y-1">
                    <Label className="text-sm">{FIELD_LABELS[field] || field}</Label>
                    <Input value={form.config[field] || ''} onChange={e => setForm({ ...form, config: { ...form.config, [field]: e.target.value } })} placeholder={FIELD_LABELS[field] || field} />
                  </div>
                ))}
              </div>
            ) : null}
            {selectedTypeInfo?.credential_fields?.length ? (
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Credentials</p>
                {editingIntegration?.has_credentials && <p className="text-xs text-amber-400">Existing credentials are encrypted. Leave blank to keep current values.</p>}
                {selectedTypeInfo.credential_fields.map(field => (
                  <div key={field} className="space-y-1">
                    <Label className="text-sm">{FIELD_LABELS[field] || field}</Label>
                    <Input type={SECRET_FIELDS.has(field) ? 'password' : 'text'} value={form.credentials[field] || ''} onChange={e => setForm({ ...form, credentials: { ...form.credentials, [field]: e.target.value } })} placeholder={editingIntegration?.has_credentials ? '(unchanged)' : (FIELD_LABELS[field] || field)} />
                  </div>
                ))}
              </div>
            ) : null}
            <div className="flex items-center space-x-2 pt-2">
              <Switch id="enable-integration" checked={form.is_enabled} onCheckedChange={c => setForm({ ...form, is_enabled: c })} />
              <Label htmlFor="enable-integration">Enable this integration</Label>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowModal(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={!!saving || !form.name}>{saving === 'integration' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{editingIntegration ? 'Update' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Google Drive Folder Picker */}
      <Dialog open={showFolderPicker} onOpenChange={setShowFolderPicker}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Select Root Folder</DialogTitle>
            <DialogDescription>Choose the Google Drive folder where SheetStorm will create CASE-xxxx directories.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <div className="flex items-center gap-1 text-sm flex-wrap">
              {folderStack.map((f, i) => (
                <span key={f.id} className="flex items-center gap-1">
                  {i > 0 && <ChevronRight className="h-3 w-3 text-muted-foreground" />}
                  <button onClick={() => navigateBack(i)} className={`hover:underline ${i === folderStack.length - 1 ? 'font-medium text-foreground' : 'text-muted-foreground'}`}>{f.name}</button>
                </span>
              ))}
            </div>
            <div className="border rounded-md divide-y max-h-64 overflow-y-auto">
              {foldersLoading ? (
                <div className="flex items-center justify-center p-6"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
              ) : driveFolders.length === 0 ? (
                <div className="p-4 text-sm text-muted-foreground text-center">No subfolders. Select this folder as the root.</div>
              ) : (
                driveFolders.map(folder => (
                  <button key={folder.id} onClick={() => navigateToFolder(folder)} className="w-full flex items-center gap-3 px-3 py-2.5 text-sm hover:bg-muted/50 transition-colors text-left">
                    <FolderOpen className="h-4 w-4 text-yellow-500 shrink-0" /><span className="truncate">{folder.name}</span><ChevronRight className="h-3.5 w-3.5 text-muted-foreground ml-auto shrink-0" />
                  </button>
                ))
              )}
            </div>
            <p className="text-xs text-muted-foreground">Current: <span className="font-medium text-foreground">{folderStack[folderStack.length - 1]?.name}</span></p>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowFolderPicker(false)}>Cancel</Button>
            <Button onClick={selectRootFolder}><FolderOpen className="mr-2 h-4 w-4" />Use This Folder</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
