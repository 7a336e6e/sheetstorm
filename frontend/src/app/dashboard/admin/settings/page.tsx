/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Settings, Bell, Shield, Database, Slack, Mail, Save, Key, Loader2, CheckCircle, Plus, Trash2, Zap, Globe, Server, Search, Bug, FileText, AlertTriangle, Network } from 'lucide-react'
import { api } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import { useConfirm } from '@/components/ui/confirm-dialog'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
    DialogBody
} from '@/components/ui/dialog'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

interface Integration {
    id: string
    type: string
    name: string
    is_enabled: boolean
    config: Record<string, any>
    has_credentials?: boolean
}

interface Organization {
    id: string
    name: string
    settings: {
        timezone?: string
    }
}

interface IntegrationType {
    id: string
    name: string
    description: string
    category: string
    config_fields: string[]
    credential_fields: string[]
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
}

const SECRET_FIELDS = new Set([
    'api_key', 'secret_key', 'client_secret', 'smtp_password', 'password', 'token', 'webhook_url', 'access_key'
])

export default function SettingsPage() {
    const { toast } = useToast()
    const confirm = useConfirm()
    const [loading, setLoading] = useState(true)
    const [integrations, setIntegrations] = useState<Integration[]>([])
    const [integrationTypes, setIntegrationTypes] = useState<IntegrationType[]>([])
    const [organization, setOrganization] = useState<Organization | null>(null)
    const [saving, setSaving] = useState<string | null>(null)
    const [testing, setTesting] = useState<string | null>(null)
    const [testResult, setTestResult] = useState<{ id: string; success: boolean; message: string } | null>(null)

    // Modal state for Integrations
    const [showIntegrationModal, setShowIntegrationModal] = useState(false)
    const [editingIntegration, setEditingIntegration] = useState<Integration | null>(null)
    const [integrationForm, setIntegrationForm] = useState({
        type: 'slack',
        name: '',
        config: {} as any,
        credentials: {} as any,
        is_enabled: true
    })

    // Org Settings Form
    const [orgForm, setOrgForm] = useState({
        name: '',
        timezone: 'UTC'
    })

    // Category filter
    const [categoryFilter, setCategoryFilter] = useState<string>('all')

    useEffect(() => {
        loadData()
    }, [])

    const loadData = async () => {
        try {
            const [integrationsRes, typesRes, orgRes] = await Promise.all([
                api.get<{ items: Integration[] }>('/integrations'),
                api.get<{ types: IntegrationType[] }>('/integrations/types').catch(() => ({ types: [] })),
                api.get<Organization>('/organization').catch(() => null)
            ])

            setIntegrations(integrationsRes.items || [])
            setIntegrationTypes(typesRes.types || [])

            if (orgRes) {
                setOrganization(orgRes)
                setOrgForm({
                    name: orgRes.name,
                    timezone: orgRes.settings?.timezone || 'UTC'
                })
            }
        } catch (error) {
            console.error('Failed to load settings:', error)
            toast({
                title: "Error",
                description: "Failed to load settings",
                variant: "destructive"
            })
        } finally {
            setLoading(false)
        }
    }

    const handleSaveOrg = async () => {
        setSaving('org')
        try {
            await api.put('/organization', {
                name: orgForm.name,
                settings: { timezone: orgForm.timezone }
            })
            toast({ title: "Organization saved", description: "Settings updated successfully" })
            loadData()
        } catch (error) {
            toast({ title: "Error", description: "Failed to save organization settings", variant: "destructive" })
        } finally {
            setSaving(null)
        }
    }

    const openIntegrationModal = (integration?: Integration) => {
        if (integration) {
            setEditingIntegration(integration)
            setIntegrationForm({
                type: integration.type,
                name: integration.name,
                config: { ...integration.config },
                credentials: {},
                is_enabled: integration.is_enabled
            })
        } else {
            setEditingIntegration(null)
            const firstType = integrationTypes[0]?.id || 'slack'
            setIntegrationForm({ type: firstType, name: '', config: {}, credentials: {}, is_enabled: true })
        }
        setShowIntegrationModal(true)
    }

    const handleDeleteIntegration = async (id: string) => {
        const confirmed = await confirm({
            title: 'Delete Integration',
            description: 'Are you sure you want to delete this integration?',
            confirmLabel: 'Delete',
            variant: 'destructive',
        })
        if (!confirmed) return
        try {
            await api.delete(`/integrations/${id}`)
            toast({ title: "Deleted", description: "Integration removed" })
            setIntegrations(prev => prev.filter(i => i.id !== id))
        } catch (error) {
            toast({ title: "Error", description: "Failed to delete integration", variant: "destructive" })
        }
    }

    const handleTestIntegration = async (id: string) => {
        setTesting(id)
        setTestResult(null)
        try {
            const res = await api.post<{ success: boolean; message: string }>(`/integrations/${id}/test`)
            setTestResult({ id, success: res.success, message: res.message })
            toast({
                title: res.success ? 'Connection Successful' : 'Connection Failed',
                description: res.message,
                variant: res.success ? 'default' : 'destructive',
            })
        } catch (error: any) {
            const msg = error?.message || 'Test failed'
            setTestResult({ id, success: false, message: msg })
            toast({ title: 'Test Failed', description: msg, variant: 'destructive' })
        } finally {
            setTesting(null)
        }
    }

    const handleSaveIntegration = async () => {
        if (!integrationForm.name) return
        setSaving('integration')
        try {
            const payload: any = {
                type: integrationForm.type,
                name: integrationForm.name,
                config: integrationForm.config,
                is_enabled: integrationForm.is_enabled
            }
            if (Object.keys(integrationForm.credentials).length > 0) {
                payload.credentials = integrationForm.credentials
            }

            if (editingIntegration) {
                await api.put(`/integrations/${editingIntegration.id}`, payload)
            } else {
                await api.post('/integrations', payload)
            }

            toast({ title: "Success", description: `Integration ${editingIntegration ? 'updated' : 'created'}` })
            setShowIntegrationModal(false)
            loadData()
        } catch (error) {
            console.error(error)
            toast({ title: "Error", description: "Failed to save integration", variant: "destructive" })
        } finally {
            setSaving(null)
        }
    }

    const getTypeInfo = (typeId: string) => integrationTypes.find(t => t.id === typeId)

    const getTypeIcon = (typeId: string) => {
        const catMeta = CATEGORY_META[getTypeInfo(typeId)?.category || '']
        if (typeId.includes('slack')) return <Slack className="h-5 w-5" />
        if (typeId.includes('email') || typeId.includes('smtp')) return <Mail className="h-5 w-5" />
        if (catMeta) return catMeta.icon
        return <Key className="h-5 w-5" />
    }

    const selectedTypeInfo = getTypeInfo(integrationForm.type)

    // Group types by category
    const categories = integrationTypes.reduce((acc, t) => {
        const cat = t.category || 'other'
        if (!acc[cat]) acc[cat] = []
        acc[cat].push(t)
        return acc
    }, {} as Record<string, IntegrationType[]>)

    const filteredIntegrations = categoryFilter === 'all'
        ? integrations
        : integrations.filter(i => getTypeInfo(i.type)?.category === categoryFilter)

    if (loading) {
        return (
            <div className="flex items-center justify-center p-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        )
    }

    return (
        <div className="p-6 space-y-6">
            <div>
                <h1 className="text-2xl font-semibold">Settings</h1>
                <p className="text-sm text-muted-foreground mt-1">Configure system settings and integrations</p>
            </div>

            <Tabs defaultValue="general">
                <TabsList>
                    <TabsTrigger value="general">General</TabsTrigger>
                    <TabsTrigger value="integrations">Integrations</TabsTrigger>
                </TabsList>

                <TabsContent value="general" className="space-y-6 max-w-4xl mt-6">
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2 text-base">
                                <Settings className="h-5 w-5" />
                                Organization Settings
                            </CardTitle>
                            <CardDescription>Basic system configuration</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="grid gap-2">
                                <Label htmlFor="org-name">Organization Name</Label>
                                <Input
                                    id="org-name"
                                    value={orgForm.name}
                                    onChange={e => setOrgForm({ ...orgForm, name: e.target.value })}
                                />
                            </div>
                            <div className="grid gap-2">
                                <Label htmlFor="timezone">Timezone</Label>
                                <Select
                                    value={orgForm.timezone}
                                    onValueChange={v => setOrgForm({ ...orgForm, timezone: v })}
                                >
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="UTC">UTC</SelectItem>
                                        <SelectItem value="America/New_York">Eastern Time (ET)</SelectItem>
                                        <SelectItem value="America/Los_Angeles">Pacific Time (PT)</SelectItem>
                                        <SelectItem value="Europe/London">London (GMT)</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="pt-2">
                                <Button onClick={handleSaveOrg} disabled={!!saving}>
                                    {saving === 'org' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Save Changes
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="integrations" className="space-y-6 mt-6">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                        <div>
                            <h3 className="text-lg font-medium">Integrations</h3>
                            <p className="text-sm text-muted-foreground">
                                {integrations.length} configured · {integrations.filter(i => i.is_enabled).length} active
                            </p>
                        </div>
                        <Button onClick={() => openIntegrationModal()}>
                            <Plus className="mr-2 h-4 w-4" /> Add Integration
                        </Button>
                    </div>

                    {/* Category Filters */}
                    <div className="flex flex-wrap gap-2">
                        <Button
                            variant={categoryFilter === 'all' ? 'default' : 'outline'}
                            size="sm"
                            onClick={() => setCategoryFilter('all')}
                        >
                            All ({integrations.length})
                        </Button>
                        {Object.entries(CATEGORY_META).map(([key, meta]) => {
                            const count = integrations.filter(i => getTypeInfo(i.type)?.category === key).length
                            if (count === 0 && !categories[key]) return null
                            return (
                                <Button
                                    key={key}
                                    variant={categoryFilter === key ? 'default' : 'outline'}
                                    size="sm"
                                    onClick={() => setCategoryFilter(key)}
                                    className="gap-1.5"
                                >
                                    {meta.icon}
                                    {meta.label}
                                    {count > 0 && <span className="ml-1 text-xs opacity-60">({count})</span>}
                                </Button>
                            )
                        })}
                    </div>

                    {/* Integration Cards */}
                    <div className="grid gap-4">
                        {filteredIntegrations.length === 0 ? (
                            <Card className="border-dashed">
                                <CardContent className="flex flex-col items-center justify-center p-6 text-center text-muted-foreground">
                                    <div className="w-12 h-12 bg-muted/50 rounded-full flex items-center justify-center mb-4">
                                        <Shield className="h-6 w-6" />
                                    </div>
                                    <p>{categoryFilter !== 'all' ? 'No integrations in this category' : 'No integrations configured'}</p>
                                    <Button variant="link" onClick={() => openIntegrationModal()}>Add your first integration</Button>
                                </CardContent>
                            </Card>
                        ) : (
                            filteredIntegrations.map(integration => {
                                const typeInfo = getTypeInfo(integration.type)
                                const catMeta = CATEGORY_META[typeInfo?.category || '']
                                return (
                                    <Card key={integration.id}>
                                        <CardContent className="flex items-center justify-between p-5">
                                            <div className="flex items-center gap-4">
                                                <div className={`w-10 h-10 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center ${catMeta?.color || 'text-muted-foreground'}`}>
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
                                                    </h4>
                                                    <p className="text-sm text-muted-foreground">
                                                        {typeInfo?.description || integration.type}
                                                        {catMeta && (
                                                            <span className="ml-2 text-xs opacity-50">· {catMeta.label}</span>
                                                        )}
                                                    </p>
                                                    {testResult?.id === integration.id && (
                                                        <p className={`text-xs mt-1 ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>
                                                            {testResult.success ? '✓' : '✗'} {testResult.message}
                                                        </p>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={() => handleTestIntegration(integration.id)}
                                                    disabled={testing === integration.id || !integration.is_enabled}
                                                >
                                                    {testing === integration.id ? (
                                                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                                                    ) : (
                                                        <Zap className="mr-1.5 h-3.5 w-3.5" />
                                                    )}
                                                    Test
                                                </Button>
                                                <Button variant="outline" size="sm" onClick={() => openIntegrationModal(integration)}>
                                                    Configure
                                                </Button>
                                                <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive/90" onClick={() => handleDeleteIntegration(integration.id)}>
                                                    <Trash2 className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </CardContent>
                                    </Card>
                                )
                            })
                        )}
                    </div>

                    {/* Available integrations for discovery */}
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
                                                    {meta.icon}
                                                    <span className="font-medium text-sm">{meta.label}</span>
                                                </div>
                                                <div className="space-y-1">
                                                    {types.map(t => {
                                                        const isConfigured = integrations.some(i => i.type === t.id)
                                                        return (
                                                            <div key={t.id} className="flex items-center justify-between text-sm">
                                                                <span className={isConfigured ? 'text-foreground' : 'text-muted-foreground'}>{t.name}</span>
                                                                {isConfigured ? (
                                                                    <CheckCircle className="h-3.5 w-3.5 text-green-400" />
                                                                ) : (
                                                                    <button
                                                                        onClick={() => {
                                                                            setEditingIntegration(null)
                                                                            setIntegrationForm({
                                                                                type: t.id,
                                                                                name: t.name,
                                                                                config: {},
                                                                                credentials: {},
                                                                                is_enabled: true
                                                                            })
                                                                            setShowIntegrationModal(true)
                                                                        }}
                                                                        className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                                                                    >
                                                                        + Add
                                                                    </button>
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
                </TabsContent>
            </Tabs>

            {/* Integration Modal */}
            <Dialog open={showIntegrationModal} onOpenChange={setShowIntegrationModal}>
                <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>{editingIntegration ? 'Edit' : 'Add'} Integration</DialogTitle>
                        <DialogDescription>
                            {selectedTypeInfo?.description || 'Connect external services to the platform.'}
                        </DialogDescription>
                    </DialogHeader>
                    <DialogBody className="space-y-4">
                        <div className="space-y-2">
                            <Label>Integration Type</Label>
                            <Select
                                value={integrationForm.type}
                                onValueChange={v => {
                                    const info = getTypeInfo(v)
                                    setIntegrationForm({
                                        ...integrationForm,
                                        type: v,
                                        name: integrationForm.name || info?.name || '',
                                        config: {},
                                        credentials: {}
                                    })
                                }}
                                disabled={!!editingIntegration}
                            >
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    {Object.entries(categories).map(([cat, types]) => {
                                        const meta = CATEGORY_META[cat]
                                        return types.map((t, idx) => (
                                            <SelectItem key={t.id} value={t.id}>
                                                {idx === 0 && meta ? `[${meta.label}] ` : ''}{t.name}
                                            </SelectItem>
                                        ))
                                    })}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-2">
                            <Label>Display Name</Label>
                            <Input
                                value={integrationForm.name}
                                onChange={e => setIntegrationForm({ ...integrationForm, name: e.target.value })}
                                placeholder={selectedTypeInfo?.name || 'Integration name'}
                            />
                        </div>

                        {/* Dynamic config fields */}
                        {selectedTypeInfo?.config_fields && selectedTypeInfo.config_fields.length > 0 && (
                            <div className="space-y-3">
                                <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Configuration</p>
                                {selectedTypeInfo.config_fields.map(field => (
                                    <div key={field} className="space-y-1">
                                        <Label className="text-sm">{FIELD_LABELS[field] || field}</Label>
                                        <Input
                                            value={integrationForm.config[field] || ''}
                                            onChange={e => setIntegrationForm({
                                                ...integrationForm,
                                                config: { ...integrationForm.config, [field]: e.target.value }
                                            })}
                                            placeholder={FIELD_LABELS[field] || field}
                                        />
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Dynamic credential fields */}
                        {selectedTypeInfo?.credential_fields && selectedTypeInfo.credential_fields.length > 0 && (
                            <div className="space-y-3">
                                <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Credentials</p>
                                {editingIntegration?.has_credentials && (
                                    <p className="text-xs text-amber-400">Existing credentials are encrypted. Leave blank to keep current values.</p>
                                )}
                                {selectedTypeInfo.credential_fields.map(field => (
                                    <div key={field} className="space-y-1">
                                        <Label className="text-sm">{FIELD_LABELS[field] || field}</Label>
                                        <Input
                                            type={SECRET_FIELDS.has(field) ? 'password' : 'text'}
                                            value={integrationForm.credentials[field] || ''}
                                            onChange={e => setIntegrationForm({
                                                ...integrationForm,
                                                credentials: { ...integrationForm.credentials, [field]: e.target.value }
                                            })}
                                            placeholder={editingIntegration?.has_credentials ? '(unchanged)' : (FIELD_LABELS[field] || field)}
                                        />
                                    </div>
                                ))}
                            </div>
                        )}

                        <div className="flex items-center space-x-2 pt-2">
                            <Switch
                                id="enable-integration"
                                checked={integrationForm.is_enabled}
                                onCheckedChange={c => setIntegrationForm({ ...integrationForm, is_enabled: c })}
                            />
                            <Label htmlFor="enable-integration">Enable this integration</Label>
                        </div>
                    </DialogBody>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowIntegrationModal(false)}>Cancel</Button>
                        <Button onClick={handleSaveIntegration} disabled={!!saving || !integrationForm.name}>
                            {saving === 'integration' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            {editingIntegration ? 'Update' : 'Create'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
