/**
 * Storage tab — S3/MinIO configuration + storage analytics (usage, breakdown by type).
 */

"use client"

import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Database, Loader2, Plus, Trash2, Zap, HardDrive, BarChart3 } from 'lucide-react'
import { api } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import { useConfirm } from '@/components/ui/confirm-dialog'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter, DialogBody,
} from '@/components/ui/dialog'

interface Integration {
  id: string; type: string; name: string; is_enabled: boolean
  config: Record<string, any>; has_credentials?: boolean
}

interface StorageStats {
  total_artifacts: number
  total_size_bytes: number
  by_storage_type: Record<string, { count: number; size_bytes: number }>
  by_mime_type: Record<string, { count: number; size_bytes: number }>
}

const FIELD_LABELS: Record<string, string> = {
  bucket_name: 'Bucket Name', region: 'Region', endpoint_url: 'Endpoint URL',
  access_key: 'Access Key', secret_key: 'Secret Key',
}
const SECRET_FIELDS = new Set(['access_key', 'secret_key'])

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

export function StorageTab() {
  const { toast } = useToast()
  const confirm = useConfirm()
  const [loading, setLoading] = useState(true)
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [stats, setStats] = useState<StorageStats | null>(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ id: string; success: boolean; message: string } | null>(null)

  // Modal
  const [showModal, setShowModal] = useState(false)
  const [editingIntegration, setEditingIntegration] = useState<Integration | null>(null)
  const [form, setForm] = useState({ name: '', config: {} as any, credentials: {} as any, is_enabled: true })

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    try {
      const [intRes, statsRes] = await Promise.all([
        api.get<{ items: Integration[] }>('/integrations'),
        api.get<StorageStats>('/storage/stats').catch(() => null),
      ])
      setIntegrations((intRes.items || []).filter(i => i.type === 's3'))
      setStats(statsRes)
    } catch { toast({ title: 'Error', variant: 'destructive' }) }
    finally { setLoading(false) }
  }

  const openModal = (int?: Integration) => {
    if (int) {
      setEditingIntegration(int)
      setForm({ name: int.name, config: { ...int.config }, credentials: {}, is_enabled: int.is_enabled })
    } else {
      setEditingIntegration(null)
      setForm({ name: 'S3 Storage', config: {}, credentials: {}, is_enabled: true })
    }
    setShowModal(true)
  }

  const handleSave = async () => {
    if (!form.name) return
    setSaving(true)
    try {
      const payload: any = { type: 's3', name: form.name, config: form.config, is_enabled: form.is_enabled }
      if (Object.keys(form.credentials).length > 0) payload.credentials = form.credentials
      if (editingIntegration) await api.put(`/integrations/${editingIntegration.id}`, payload)
      else await api.post('/integrations', payload)
      toast({ title: 'Success' }); setShowModal(false); loadData()
    } catch { toast({ title: 'Error', variant: 'destructive' }) }
    finally { setSaving(false) }
  }

  const handleDelete = async (id: string) => {
    const ok = await confirm({ title: 'Delete Storage Config', description: 'Remove this S3 configuration?', confirmLabel: 'Delete', variant: 'destructive' })
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

  if (loading) {
    return <div className="flex items-center justify-center p-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h3 className="text-lg font-medium">Storage</h3>
          <p className="text-sm text-muted-foreground">S3-compatible storage for evidence artifacts</p>
        </div>
        <Button onClick={() => openModal()}><Plus className="mr-2 h-4 w-4" /> Add S3 Configuration</Button>
      </div>

      {/* Storage Analytics */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 border border-green-500/20 flex items-center justify-center">
                <HardDrive className="h-5 w-5 text-green-400" />
              </div>
              <div>
                <p className="text-2xl font-semibold">{formatBytes(stats.total_size_bytes)}</p>
                <p className="text-xs text-muted-foreground">Total Storage Used</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
                <Database className="h-5 w-5 text-blue-400" />
              </div>
              <div>
                <p className="text-2xl font-semibold">{stats.total_artifacts}</p>
                <p className="text-xs text-muted-foreground">Total Artifacts</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
                <BarChart3 className="h-5 w-5 text-purple-400" />
              </div>
              <div>
                <p className="text-2xl font-semibold">{Object.keys(stats.by_storage_type).length}</p>
                <p className="text-xs text-muted-foreground">Storage Backends</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Breakdown by storage type */}
      {stats && Object.keys(stats.by_storage_type).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Storage Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(stats.by_storage_type).map(([type, data]) => (
                <div key={type} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">{type}</Badge>
                    <span className="text-sm">{data.count} artifacts</span>
                  </div>
                  <span className="text-sm font-medium">{formatBytes(data.size_bytes)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* S3 Configurations */}
      {integrations.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
            <Database className="h-8 w-8 mb-3 opacity-50" />
            <p className="font-medium">No S3 storage configured</p>
            <p className="text-sm mt-1">Artifacts are stored locally. Add S3 for cloud storage.</p>
            <Button variant="link" onClick={() => openModal()}>Configure S3</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {integrations.map(int => (
            <Card key={int.id}>
              <CardContent className="flex items-center justify-between p-5">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-lg bg-green-500/10 border border-green-500/20 flex items-center justify-center">
                    <Database className="h-5 w-5 text-green-400" />
                  </div>
                  <div>
                    <h4 className="font-medium flex items-center gap-2">
                      {int.name}
                      {int.is_enabled ? <Badge variant="outline" className="text-green-400 border-green-500/30 text-xs">Active</Badge> : <Badge variant="outline" className="text-muted-foreground text-xs">Disabled</Badge>}
                    </h4>
                    <p className="text-sm text-muted-foreground">
                      {int.config?.bucket_name && `Bucket: ${int.config.bucket_name}`}
                      {int.config?.region && ` · Region: ${int.config.region}`}
                      {int.config?.endpoint_url && ` · ${int.config.endpoint_url}`}
                    </p>
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
          ))}
        </div>
      )}

      {/* Modal */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingIntegration ? 'Edit' : 'Add'} S3 Storage</DialogTitle>
            <DialogDescription>Configure S3-compatible object storage (AWS S3, MinIO, etc.)</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-2">
              <Label>Display Name</Label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Production S3" />
            </div>
            {['bucket_name', 'region', 'endpoint_url'].map(field => (
              <div key={field} className="space-y-1">
                <Label className="text-sm">{FIELD_LABELS[field] || field}</Label>
                <Input value={form.config[field] || ''} onChange={e => setForm({ ...form, config: { ...form.config, [field]: e.target.value } })} placeholder={FIELD_LABELS[field]} />
              </div>
            ))}
            {['access_key', 'secret_key'].map(field => (
              <div key={field} className="space-y-1">
                <Label className="text-sm">{FIELD_LABELS[field] || field}</Label>
                <Input type="password" value={form.credentials[field] || ''} onChange={e => setForm({ ...form, credentials: { ...form.credentials, [field]: e.target.value } })} placeholder={editingIntegration?.has_credentials ? '(unchanged)' : (FIELD_LABELS[field])} />
              </div>
            ))}
            <div className="flex items-center space-x-2 pt-2">
              <Switch id="enable-s3" checked={form.is_enabled} onCheckedChange={c => setForm({ ...form, is_enabled: c })} />
              <Label htmlFor="enable-s3">Enable this storage backend</Label>
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
