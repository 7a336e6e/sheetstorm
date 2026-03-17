/**
 * Notifications tab — Slack webhooks, Email SMTP, and custom webhook configs.
 */

"use client"

import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Bell, Loader2, Plus, Trash2, Zap, Slack, Mail, Globe } from 'lucide-react'
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

const NOTIFICATION_TYPES = new Set(['slack', 'email_smtp', 'webhook'])

const PROVIDER_META: Record<string, { icon: React.ReactNode; color: string; description: string }> = {
  slack: { icon: <Slack className="h-5 w-5" />, color: 'text-purple-400', description: 'Send alerts to Slack channels via webhooks' },
  email_smtp: { icon: <Mail className="h-5 w-5" />, color: 'text-blue-400', description: 'Send email notifications via SMTP' },
  webhook: { icon: <Globe className="h-5 w-5" />, color: 'text-green-400', description: 'Send HTTP POST notifications to custom endpoints' },
}

const FIELD_LABELS: Record<string, string> = {
  webhook_url: 'Webhook URL', smtp_host: 'SMTP Host', smtp_port: 'SMTP Port',
  smtp_user: 'Username', smtp_password: 'Password', from_address: 'From Address',
  url: 'Webhook URL', api_key: 'API Key',
}
const SECRET_FIELDS = new Set(['webhook_url', 'smtp_password', 'api_key'])

export function NotificationsTab() {
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
  const [form, setForm] = useState({ type: 'slack', name: '', config: {} as any, credentials: {} as any, is_enabled: true })

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    try {
      const [intRes, typesRes] = await Promise.all([
        api.get<{ items: Integration[] }>('/integrations'),
        api.get<{ types: IntegrationType[] }>('/integrations/types').catch(() => ({ types: [] })),
      ])
      setIntegrations((intRes.items || []).filter(i => NOTIFICATION_TYPES.has(i.type)))
      setIntegrationTypes((typesRes.types || []).filter(t => NOTIFICATION_TYPES.has(t.id)))
    } catch { toast({ title: 'Error', variant: 'destructive' }) }
    finally { setLoading(false) }
  }

  const getTypeInfo = (id: string) => integrationTypes.find(t => t.id === id)
  const getIcon = (type: string) => PROVIDER_META[type]?.icon || <Bell className="h-5 w-5" />

  const openModal = (int?: Integration) => {
    if (int) {
      setEditingIntegration(int)
      setForm({ type: int.type, name: int.name, config: { ...int.config }, credentials: {}, is_enabled: int.is_enabled })
    } else {
      setEditingIntegration(null)
      const first = integrationTypes[0]?.id || 'slack'
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
    const ok = await confirm({ title: 'Delete Notification', description: 'Remove this notification channel?', confirmLabel: 'Delete', variant: 'destructive' })
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

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h3 className="text-lg font-medium">Notifications</h3>
          <p className="text-sm text-muted-foreground">
            {integrations.length} configured · {integrations.filter(i => i.is_enabled).length} active
          </p>
        </div>
        <Button onClick={() => openModal()}><Plus className="mr-2 h-4 w-4" /> Add Channel</Button>
      </div>

      {/* Tip */}
      <Card className="border-blue-500/20 bg-blue-500/5">
        <CardContent className="p-4 flex items-start gap-3">
          <Bell className="h-5 w-5 text-blue-400 mt-0.5 shrink-0" />
          <div className="text-sm">
            <p className="font-medium text-blue-400">Notification Channels</p>
            <p className="text-muted-foreground mt-0.5">
              Configure where alerts go when incidents are created, escalated, or updated. Slack webhooks send real-time channel messages, SMTP sends email alerts, and custom webhooks send JSON payloads to any HTTP endpoint.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Configured */}
      {integrations.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
            <Bell className="h-8 w-8 mb-3 opacity-50" />
            <p className="font-medium">No notification channels configured</p>
            <p className="text-sm mt-1">Add Slack, Email, or Webhook to receive real-time alerts.</p>
            <Button variant="link" onClick={() => openModal()}>Add a channel</Button>
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
                    <div className={`w-10 h-10 rounded-lg bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 flex items-center justify-center ${meta?.color || 'text-muted-foreground'}`}>
                      {getIcon(int.type)}
                    </div>
                    <div>
                      <h4 className="font-medium flex items-center gap-2">
                        {int.name}
                        {int.is_enabled ? <Badge variant="outline" className="text-green-400 border-green-500/30 text-xs">Active</Badge> : <Badge variant="outline" className="text-muted-foreground text-xs">Disabled</Badge>}
                      </h4>
                      <p className="text-sm text-muted-foreground">{meta?.description || int.type}</p>
                      {int.type === 'email_smtp' && int.config?.from_address && (
                        <p className="text-xs mt-0.5 text-muted-foreground">From: {int.config.from_address}</p>
                      )}
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

      {/* Available */}
      {(() => {
        const configured = new Set(integrations.map(i => i.type))
        const available = integrationTypes.filter(t => !configured.has(t.id))
        if (available.length === 0) return null
        return (
          <Card className="border-dashed">
            <CardHeader><CardTitle className="text-sm font-medium text-muted-foreground">Available Channels</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {available.map(t => {
                  const meta = PROVIDER_META[t.id]
                  return (
                    <button key={t.id} onClick={() => { setEditingIntegration(null); setForm({ type: t.id, name: t.name, config: {}, credentials: {}, is_enabled: true }); setShowModal(true) }}
                      className="flex items-center gap-3 p-3 rounded-lg border border-dashed hover:bg-muted/50 transition-colors text-left">
                      <div className={`${meta?.color || 'text-muted-foreground'}`}>{meta?.icon || <Bell className="h-5 w-5" />}</div>
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
        )
      })()}

      {/* Modal */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingIntegration ? 'Edit' : 'Add'} Notification Channel</DialogTitle>
            <DialogDescription>{selectedTypeInfo?.description || 'Configure a notification channel.'}</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-2">
              <Label>Channel Type</Label>
              <Select value={form.type} onValueChange={v => { const info = getTypeInfo(v); setForm({ ...form, type: v, name: form.name || info?.name || '', config: {}, credentials: {} }) }} disabled={!!editingIntegration}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {integrationTypes.map(t => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Display Name</Label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder={selectedTypeInfo?.name || 'Channel name'} />
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
              <Switch id="enable-notif" checked={form.is_enabled} onCheckedChange={c => setForm({ ...form, is_enabled: c })} />
              <Label htmlFor="enable-notif">Enable this channel</Label>
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
