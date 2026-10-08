/**
 * Storage tab — evidence storage backends (S3/MinIO + Google Drive) and
 * storage analytics (usage, breakdown by type).
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
  Database, Loader2, Plus, Trash2, Zap, HardDrive, BarChart3, Server,
  Cloud, Link2, Unlink, FolderOpen, Folder, ChevronRight,
} from 'lucide-react'
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

interface DriveStatus {
  configured?: boolean; connected?: boolean; email?: string
  root_folder_id?: string; root_folder_name?: string; message?: string
}

interface StorageStats {
  total_artifacts: number
  total_size_bytes: number
  by_storage_type: Record<string, { count: number; size_bytes: number }>
  by_mime_type: Record<string, { count: number; size_bytes: number }>
  disk_usage?: {
    total_bytes: number
    used_bytes: number
    free_bytes: number
    usage_percent: number
    path: string
  }
}

const FIELD_LABELS: Record<string, string> = {
  bucket_name: 'Bucket Name', region: 'Region', endpoint_url: 'Endpoint URL',
  access_key: 'Access Key', secret_key: 'Secret Key',
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const DRIVE_ERROR_MESSAGES: Record<string, string> = {
  access_denied: 'Google Drive access was denied.',
  no_code: 'Google did not return an authorization code.',
  invalid_state: 'The Google Drive authorization request expired or was invalid. Please try again.',
  token_exchange_failed: 'Could not complete the Google Drive authorization.',
}

export function StorageTab() {
  const { toast } = useToast()
  const confirm = useConfirm()
  const searchParams = useSearchParams()
  const router = useRouter()
  const [loading, setLoading] = useState(true)
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [stats, setStats] = useState<StorageStats | null>(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ id: string; success: boolean; message: string } | null>(null)

  // S3 modal
  const [showModal, setShowModal] = useState(false)
  const [editingIntegration, setEditingIntegration] = useState<Integration | null>(null)
  const [form, setForm] = useState({ name: '', config: {} as any, credentials: {} as any, is_enabled: true })

  // Google Drive
  const [driveStatus, setDriveStatus] = useState<DriveStatus | null>(null)
  const [driveLoading, setDriveLoading] = useState(false)
  const [showFolderPicker, setShowFolderPicker] = useState(false)
  const [driveFolders, setDriveFolders] = useState<{ id: string; name: string }[]>([])
  const [folderStack, setFolderStack] = useState<{ id: string; name: string }[]>([{ id: 'root', name: 'My Drive' }])

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

  const loadDriveStatus = useCallback(async () => {
    try { const res = await api.get<DriveStatus>('/google-drive/status'); setDriveStatus(res) }
    catch { setDriveStatus(null) }
  }, [])

  useEffect(() => { loadData(); loadDriveStatus() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // Handle the OAuth return from Google. The backend completes the token
  // exchange server-side and redirects here with only a status flag
  // (`drive=connected`) or an error code (`drive_error=<code>`). Tokens are
  // never passed through the URL.
  useEffect(() => {
    const driveResult = searchParams.get('drive')
    const driveError = searchParams.get('drive_error')
    if (!driveResult && !driveError) return
    if (driveError) {
      toast({
        title: 'Google Drive Error',
        description: DRIVE_ERROR_MESSAGES[driveError] || 'Google Drive connection failed.',
        variant: 'destructive',
      })
    } else if (driveResult === 'connected') {
      toast({ title: 'Google Drive Connected' })
      loadDriveStatus()
      openFolderPicker()
    }
    router.replace('/dashboard/admin/settings?tab=storage')
  }, [searchParams])  // eslint-disable-line react-hooks/exhaustive-deps

  // ---- S3 ----
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

  // ---- Google Drive ----
  const handleDriveConnect = async () => {
    setDriveLoading(true)
    try { const res = await api.post<{ auth_url: string }>('/google-drive/auth'); window.location.href = res.auth_url }
    catch { toast({ title: 'Error', description: 'Could not start Google Drive OAuth. Ensure the OAuth app credentials are configured.', variant: 'destructive' }); setDriveLoading(false) }
  }

  const handleDriveDisconnect = async () => {
    const ok = await confirm({ title: 'Disconnect Google Drive', description: 'Existing files in Drive will not be deleted.', confirmLabel: 'Disconnect', variant: 'destructive' })
    if (!ok) return
    try { await api.post('/google-drive/disconnect'); toast({ title: 'Disconnected' }); loadDriveStatus() }
    catch { toast({ title: 'Error', variant: 'destructive' }) }
  }

  const loadDriveFolders = async (parentId: string) => {
    try { const res = await api.get<{ folders: { id: string; name: string }[] }>(`/google-drive/folders?parent_id=${parentId}`); setDriveFolders(res.folders || []) }
    catch { toast({ title: 'Error', description: 'Could not load folders', variant: 'destructive' }) }
  }
  const openFolderPicker = () => { setFolderStack([{ id: 'root', name: 'My Drive' }]); setDriveFolders([]); setShowFolderPicker(true); loadDriveFolders('root') }
  const navigateToFolder = (f: { id: string; name: string }) => { setFolderStack(prev => [...prev, f]); loadDriveFolders(f.id) }
  const navigateBack = (i: number) => { const s = folderStack.slice(0, i + 1); setFolderStack(s); loadDriveFolders(s[s.length - 1].id) }
  const selectCurrentFolder = async () => {
    const c = folderStack[folderStack.length - 1]
    try { await api.post('/google-drive/set-root', { folder_id: c.id, folder_name: c.name }); toast({ title: 'Root Folder Set', description: c.name }); setShowFolderPicker(false); loadDriveStatus() }
    catch { toast({ title: 'Error', variant: 'destructive' }) }
  }

  if (loading) {
    return <div className="flex items-center justify-center p-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h3 className="text-lg font-medium">Storage</h3>
          <p className="text-sm text-muted-foreground">Evidence storage backends — S3-compatible object storage and Google Drive</p>
        </div>
        <Button onClick={() => openModal()}><Plus className="mr-2 h-4 w-4" /> Add S3 Configuration</Button>
      </div>

      {/* Storage Analytics */}
      {stats && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Card>
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-green-500/10 border border-green-500/20 flex items-center justify-center">
                  <HardDrive className="h-5 w-5 text-green-400" />
                </div>
                <div>
                  <p className="text-2xl font-semibold">{formatBytes(stats.total_size_bytes ?? 0)}</p>
                  <p className="text-xs text-muted-foreground">Artifact Storage Used</p>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
                  <Database className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <p className="text-2xl font-semibold">{stats.total_artifacts ?? 0}</p>
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
                  <p className="text-2xl font-semibold">{Object.keys(stats.by_storage_type ?? {}).length}</p>
                  <p className="text-xs text-muted-foreground">Storage Backends</p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Disk Usage */}
          {stats.disk_usage && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2"><Server className="h-4 w-4" /> Disk Usage</CardTitle>
                <CardDescription>Local artifact storage volume ({stats.disk_usage.path})</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">
                      {formatBytes(stats.disk_usage.used_bytes)} used of {formatBytes(stats.disk_usage.total_bytes)}
                    </span>
                    <span className="font-medium">{stats.disk_usage.usage_percent}%</span>
                  </div>
                  <div className="h-2.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        stats.disk_usage.usage_percent > 90 ? 'bg-red-500' :
                        stats.disk_usage.usage_percent > 75 ? 'bg-yellow-500' : 'bg-green-500'
                      }`}
                      style={{ width: `${Math.min(stats.disk_usage.usage_percent, 100)}%` }}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">{formatBytes(stats.disk_usage.free_bytes)} free</p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Breakdown by storage type */}
      {stats && Object.keys(stats.by_storage_type ?? {}).length > 0 && (
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

      {/* Google Drive */}
      <Card>
        <CardContent className="flex items-center justify-between p-5">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
              <Cloud className="h-5 w-5 text-cyan-400" />
            </div>
            <div>
              <h4 className="font-medium flex items-center gap-2">
                Google Drive
                {driveStatus?.connected
                  ? <Badge variant="outline" className="text-green-400 border-green-500/30 text-xs">Connected</Badge>
                  : <Badge variant="outline" className="text-muted-foreground text-xs">Not connected</Badge>}
              </h4>
              <p className="text-sm text-muted-foreground">
                {driveStatus?.connected
                  ? <>Case artifacts are stored in Google Drive{driveStatus.root_folder_name ? <> · Root: {driveStatus.root_folder_name}</> : null}</>
                  : driveStatus && driveStatus.configured === false
                    ? (driveStatus.message || 'Google Drive OAuth app is not configured.')
                    : 'Store case artifacts in Google Drive (CASE-xxxx folders).'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {driveStatus?.connected ? (
              <>
                <Button variant="outline" size="sm" onClick={openFolderPicker}>
                  <FolderOpen className="mr-1.5 h-3.5 w-3.5" />
                  {driveStatus.root_folder_id && driveStatus.root_folder_id !== 'root' ? 'Change Folder' : 'Set Folder'}
                </Button>
                <Button variant="outline" size="sm" onClick={handleDriveDisconnect} className="text-destructive border-destructive/30 hover:bg-destructive/10">
                  <Unlink className="mr-1.5 h-3.5 w-3.5" />Disconnect
                </Button>
              </>
            ) : (
              <Button
                variant="outline" size="sm" onClick={handleDriveConnect}
                disabled={driveLoading || (driveStatus?.configured === false)}
                className="text-cyan-400 border-cyan-500/30 hover:bg-cyan-500/10"
              >
                {driveLoading ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Link2 className="mr-1.5 h-3.5 w-3.5" />}Connect
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

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

      {/* S3 Modal */}
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

      {/* Google Drive Folder Picker */}
      <Dialog open={showFolderPicker} onOpenChange={setShowFolderPicker}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Choose Google Drive Folder</DialogTitle>
            <DialogDescription>Choose the folder where SheetStorm will create CASE-xxxx directories.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <div className="flex items-center gap-1 text-sm flex-wrap">
              {folderStack.map((f, i) => (
                <span key={f.id} className="flex items-center gap-1">
                  {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
                  <button className="hover:underline text-cyan-400" onClick={() => navigateBack(i)}>{f.name}</button>
                </span>
              ))}
            </div>
            <div className="border rounded-md max-h-64 overflow-y-auto divide-y divide-border">
              {driveFolders.length === 0 ? (
                <p className="text-sm text-muted-foreground p-4 text-center">No subfolders here.</p>
              ) : (
                driveFolders.map(folder => (
                  <button
                    key={folder.id}
                    onClick={() => navigateToFolder(folder)}
                    className="w-full flex items-center gap-2 p-2.5 text-sm hover:bg-muted text-left"
                  >
                    <Folder className="h-4 w-4 text-cyan-400" /> {folder.name}
                  </button>
                ))
              )}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowFolderPicker(false)}>Cancel</Button>
            <Button onClick={selectCurrentFolder}>Use "{folderStack[folderStack.length - 1]?.name}"</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
