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
import { Settings, Bell, Shield, Database, Slack, Mail, Save, Key, Loader2, CheckCircle, Plus, Trash2 } from 'lucide-react'
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
    has_credentials?: boolean // Backend shouldn't send real creds, just flag
}

interface Organization {
    id: string
    name: string
    settings: {
        timezone?: string
    }
}

const INTEGRATION_TYPES = [
    { id: 'slack', name: 'Slack', description: 'Send notifications to Slack channels' },
    { id: 'openai', name: 'OpenAI', description: 'AI-powered summaries and analysis' },
    { id: 's3', name: 'S3 Storage', description: 'Archive artifacts to S3' },
    { id: 'oauth_google', name: 'Google OAuth', description: 'Sign in with Google' },
    { id: 'oauth_github', name: 'GitHub OAuth', description: 'Sign in with GitHub' },
]

export default function SettingsPage() {
    const { toast } = useToast()
    const confirm = useConfirm()
    const [loading, setLoading] = useState(true)
    const [integrations, setIntegrations] = useState<Integration[]>([])
    const [organization, setOrganization] = useState<Organization | null>(null)
    const [saving, setSaving] = useState<string | null>(null)

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

    useEffect(() => {
        loadData()
    }, [])

    const loadData = async () => {
        try {
            const [integrationsRes, orgRes] = await Promise.all([
                api.get<{ items: Integration[] }>('/integrations'),
                api.get<Organization>('/organization').catch(() => null) // Handle 404/permissions gracefully
            ])

            setIntegrations(integrationsRes.items || [])

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
                settings: { timezone: orgForm.timezone } // Minimal settings update
            })
            toast({ title: "Organization saved", description: "Settings updated successfully" })
            loadData() // Reload to confirm
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
                credentials: {}, // Don't fill credentials for security, user must re-enter if changing
                is_enabled: integration.is_enabled
            })
        } else {
            setEditingIntegration(null)
            setIntegrationForm({ type: 'slack', name: '', config: {}, credentials: {}, is_enabled: true })
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
            // Only include credentials if keys are present
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
                    {/* Organization Settings */}
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
                                        {/* Add more as needed */}
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

                <TabsContent value="integrations" className="space-y-6 max-w-4xl mt-6">
                    <div className="flex justify-between items-center">
                        <h3 className="text-lg font-medium">Active Integrations</h3>
                        <Button onClick={() => openIntegrationModal()}><Plus className="mr-2 h-4 w-4" /> Add Integration</Button>
                    </div>

                    <div className="grid gap-4">
                        {integrations.length === 0 ? (
                            <Card className="border-dashed">
                                <CardContent className="flex flex-col items-center justify-center p-6 text-center text-muted-foreground">
                                    <div className="w-12 h-12 bg-muted/50 rounded-full flex items-center justify-center mb-4">
                                        <Shield className="h-6 w-6" />
                                    </div>
                                    <p>No integrations configured</p>
                                    <Button variant="link" onClick={() => openIntegrationModal()}>Add your first integration</Button>
                                </CardContent>
                            </Card>
                        ) : (
                            integrations.map(integration => (
                                <Card key={integration.id}>
                                    <CardContent className="flex items-center justify-between p-6">
                                        <div className="flex items-center gap-4">
                                            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
                                                {integration.type.includes('slack') ? <Slack className="h-5 w-5" /> :
                                                    integration.type.includes('google') ? <span className="font-bold">G</span> :
                                                        <Key className="h-5 w-5" />}
                                            </div>
                                            <div>
                                                <h4 className="font-medium flex items-center gap-2">
                                                    {integration.name}
                                                    {!integration.is_enabled && <span className="text-xs bg-muted px-2 py-0.5 rounded text-muted-foreground">Disabled</span>}
                                                </h4>
                                                <p className="text-sm text-muted-foreground">{INTEGRATION_TYPES.find(t => t.id === integration.type)?.description || integration.type}</p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <Button variant="outline" size="sm" onClick={() => openIntegrationModal(integration)}>Configure</Button>
                                            <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive/90" onClick={() => handleDeleteIntegration(integration.id)}>
                                                <Trash2 className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    </CardContent>
                                </Card>
                            ))
                        )}
                    </div>
                </TabsContent>
            </Tabs>

            {/* Integration Modal */}
            <Dialog open={showIntegrationModal} onOpenChange={setShowIntegrationModal}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle>{editingIntegration ? 'Edit' : 'Add'} Integration</DialogTitle>
                        <DialogDescription>Connect external services to the platform.</DialogDescription>
                    </DialogHeader>
                    <DialogBody className="space-y-4">
                        <div className="space-y-2">
                            <Label>Integration Type</Label>
                            <Select
                                value={integrationForm.type}
                                onValueChange={v => setIntegrationForm({ ...integrationForm, type: v })}
                                disabled={!!editingIntegration} // Prevent changing type after creation
                            >
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    {INTEGRATION_TYPES.map(t => (
                                        <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Name</Label>
                            <Input
                                value={integrationForm.name}
                                onChange={e => setIntegrationForm({ ...integrationForm, name: e.target.value })}
                                placeholder="e.g. Corporate Slack"
                            />
                        </div>

                        {/* Dynamic Config Fields based on Type */}
                        {integrationForm.type === 'slack' && (
                            <div className="space-y-2">
                                <Label>Webhook URL</Label>
                                <Input
                                    type="password"
                                    placeholder="https://hooks.slack.com/services/..."
                                    value={integrationForm.credentials.webhook_url || ''}
                                    onChange={e => setIntegrationForm({
                                        ...integrationForm,
                                        credentials: { ...integrationForm.credentials, webhook_url: e.target.value }
                                    })}
                                />
                                <p className="text-xs text-muted-foreground">The incoming webhook URL for your channel.</p>
                            </div>
                        )}

                        {(integrationForm.type === 'openai' || integrationForm.type === 'google_ai') && (
                            <div className="space-y-2">
                                <Label>API Key</Label>
                                <Input
                                    type="password"
                                    placeholder="sk-..."
                                    value={integrationForm.credentials.api_key || ''}
                                    onChange={e => setIntegrationForm({
                                        ...integrationForm,
                                        credentials: { ...integrationForm.credentials, api_key: e.target.value }
                                    })}
                                />
                            </div>
                        )}

                        {integrationForm.type.includes('oauth') && (
                            <>
                                <div className="space-y-2">
                                    <Label>Client ID</Label>
                                    <Input
                                        value={integrationForm.config.client_id || ''}
                                        onChange={e => setIntegrationForm({
                                            ...integrationForm,
                                            config: { ...integrationForm.config, client_id: e.target.value }
                                        })}
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Client Secret</Label>
                                    <Input
                                        type="password"
                                        placeholder={editingIntegration?.has_credentials ? "(Unchanged)" : ""}
                                        value={integrationForm.credentials.client_secret || ''}
                                        onChange={e => setIntegrationForm({
                                            ...integrationForm,
                                            credentials: { ...integrationForm.credentials, client_secret: e.target.value }
                                        })}
                                    />
                                </div>
                            </>
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
                        <Button onClick={handleSaveIntegration} disabled={!!saving}>
                            {saving === 'integration' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Save
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
