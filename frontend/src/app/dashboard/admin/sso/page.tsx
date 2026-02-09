"use client"

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogBody,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/use-toast'
import { useConfirm } from '@/components/ui/confirm-dialog'
import api from '@/lib/api'
import { ArrowLeft, Plus, Pencil, Trash2, Loader2, ExternalLink, KeyRound, Shield } from 'lucide-react'

interface SSOProvider {
  id: string
  name: string
  protocol: 'saml' | 'oidc'
  is_enabled: boolean
  client_id?: string
  issuer_url?: string
  metadata_url?: string
  entity_id?: string
  acs_url?: string
  domains: string[]
  created_at: string
  updated_at?: string
}

const EMPTY_FORM: Omit<SSOProvider, 'id' | 'created_at' | 'updated_at'> = {
  name: '',
  protocol: 'oidc',
  is_enabled: false,
  client_id: '',
  issuer_url: '',
  metadata_url: '',
  entity_id: '',
  acs_url: '',
  domains: [],
}

export default function SSOConfigPage() {
  const { toast } = useToast()
  const confirm = useConfirm()
  const [providers, setProviders] = useState<SSOProvider[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showDialog, setShowDialog] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [domainInput, setDomainInput] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  const fetchProviders = async () => {
    try {
      const data = await api.get<{ items: SSOProvider[] }>('/admin/sso-providers')
      setProviders(data.items || [])
    } catch {
      // API may not exist yet — show empty
      setProviders([])
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchProviders()
  }, [])

  const openCreate = () => {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setDomainInput('')
    setShowDialog(true)
  }

  const openEdit = (provider: SSOProvider) => {
    setEditingId(provider.id)
    setForm({
      name: provider.name,
      protocol: provider.protocol,
      is_enabled: provider.is_enabled,
      client_id: provider.client_id || '',
      issuer_url: provider.issuer_url || '',
      metadata_url: provider.metadata_url || '',
      entity_id: provider.entity_id || '',
      acs_url: provider.acs_url || '',
      domains: [...provider.domains],
    })
    setDomainInput('')
    setShowDialog(true)
  }

  const addDomain = () => {
    const domain = domainInput.trim().toLowerCase()
    if (domain && !form.domains.includes(domain)) {
      setForm({ ...form, domains: [...form.domains, domain] })
      setDomainInput('')
    }
  }

  const removeDomain = (d: string) => {
    setForm({ ...form, domains: form.domains.filter((x) => x !== d) })
  }

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast({ title: 'Validation Error', description: 'Provider name is required', variant: 'destructive' })
      return
    }
    setIsSaving(true)
    try {
      if (editingId) {
        await api.put(`/admin/sso-providers/${editingId}`, form)
        toast({ title: 'Updated', description: 'SSO provider updated successfully' })
      } else {
        await api.post('/admin/sso-providers', form)
        toast({ title: 'Created', description: 'SSO provider created successfully' })
      }
      setShowDialog(false)
      fetchProviders()
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to save',
        variant: 'destructive',
      })
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    const confirmed = await confirm({
      title: 'Delete SSO Provider',
      description: 'Delete this SSO provider? Users will no longer be able to log in with it.',
      confirmLabel: 'Delete',
      variant: 'destructive',
    })
    if (!confirmed) return
    try {
      await api.delete(`/admin/sso-providers/${id}`)
      toast({ title: 'Deleted', description: 'SSO provider removed' })
      fetchProviders()
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to delete provider', variant: 'destructive' })
    }
  }

  const toggleEnabled = async (provider: SSOProvider) => {
    try {
      await api.patch(`/admin/sso-providers/${provider.id}`, {
        is_enabled: !provider.is_enabled,
      })
      setProviders((prev) =>
        prev.map((p) => (p.id === provider.id ? { ...p, is_enabled: !p.is_enabled } : p))
      )
    } catch {
      toast({ title: 'Error', description: 'Failed to update provider', variant: 'destructive' })
    }
  }

  return (
    <div className="p-6 lg:p-8 space-y-6">
      <Link
        href="/dashboard/admin/settings"
        className="inline-flex items-center text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Settings
      </Link>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-3">
            <Shield className="h-6 w-6" />
            Single Sign-On (SSO)
          </h1>
          <p className="text-muted-foreground mt-1">
            Configure SAML or OpenID Connect identity providers for your organization.
          </p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          Add Provider
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Provider</TableHead>
                <TableHead>Protocol</TableHead>
                <TableHead>Domains</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-[100px]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin mx-auto text-muted-foreground" />
                  </TableCell>
                </TableRow>
              ) : providers.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-12 text-muted-foreground">
                    No SSO providers configured. Click &quot;Add Provider&quot; to get started.
                  </TableCell>
                </TableRow>
              ) : (
                providers.map((provider) => (
                  <TableRow key={provider.id}>
                    <TableCell className="font-medium">{provider.name}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="uppercase text-xs">
                        {provider.protocol}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {provider.domains.map((d) => (
                          <Badge key={d} variant="outline" className="text-xs">
                            {d}
                          </Badge>
                        ))}
                        {provider.domains.length === 0 && (
                          <span className="text-muted-foreground text-xs">All domains</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={provider.is_enabled}
                        onCheckedChange={() => toggleEnabled(provider)}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="icon-sm" onClick={() => openEdit(provider)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon-sm" onClick={() => handleDelete(provider.id)}>
                          <Trash2 className="h-4 w-4 text-red-400" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Create/Edit Dialog */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingId ? 'Edit' : 'Add'} SSO Provider</DialogTitle>
            <DialogDescription>
              Configure a SAML or OpenID Connect identity provider.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Provider Name *</Label>
                <Input
                  placeholder="e.g. Azure AD, Okta, Google Workspace"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label>Protocol *</Label>
                <Select
                  value={form.protocol}
                  onValueChange={(v: 'saml' | 'oidc') => setForm({ ...form, protocol: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="oidc">OpenID Connect (OIDC)</SelectItem>
                    <SelectItem value="saml">SAML 2.0</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {form.protocol === 'oidc' ? (
                <>
                  <div className="space-y-2">
                    <Label>Client ID</Label>
                    <Input
                      placeholder="Application client ID"
                      value={form.client_id}
                      onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Issuer URL</Label>
                    <Input
                      placeholder="https://login.microsoftonline.com/{tenant}/v2.0"
                      value={form.issuer_url}
                      onChange={(e) => setForm({ ...form, issuer_url: e.target.value })}
                    />
                  </div>
                </>
              ) : (
                <>
                  <div className="space-y-2">
                    <Label>Entity ID</Label>
                    <Input
                      placeholder="IdP Entity ID / Issuer"
                      value={form.entity_id}
                      onChange={(e) => setForm({ ...form, entity_id: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Metadata URL</Label>
                    <Input
                      placeholder="https://idp.example.com/metadata"
                      value={form.metadata_url}
                      onChange={(e) => setForm({ ...form, metadata_url: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>ACS URL (auto-generated)</Label>
                    <Input
                      placeholder="https://app.sheetstorm.com/api/v1/auth/saml/callback"
                      value={form.acs_url}
                      onChange={(e) => setForm({ ...form, acs_url: e.target.value })}
                      disabled
                    />
                    <p className="text-xs text-muted-foreground">
                      This is your Assertion Consumer Service URL — provide this to your IdP.
                    </p>
                  </div>
                </>
              )}

              <div className="space-y-2">
                <Label>Allowed Email Domains</Label>
                <div className="flex gap-2">
                  <Input
                    placeholder="company.com"
                    value={domainInput}
                    onChange={(e) => setDomainInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addDomain())}
                  />
                  <Button variant="outline" onClick={addDomain} type="button">
                    Add
                  </Button>
                </div>
                {form.domains.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {form.domains.map((d) => (
                      <Badge key={d} variant="outline" className="gap-1">
                        {d}
                        <button onClick={() => removeDomain(d)} className="ml-1 hover:text-red-400">
                          ×
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  Leave empty to allow all email domains. Otherwise only users with matching domains can use this provider.
                </p>
              </div>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {editingId ? 'Save Changes' : 'Create Provider'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
