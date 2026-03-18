/**
 * Settings page — orchestrator with 7 tabs.
 * Each tab is a focused component under @/components/settings/*.
 */

"use client"

import { useSearchParams } from 'next/navigation'
import { Settings, Zap, Database, Search, Bell, Shield, Puzzle, FileCode2 } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { GeneralTab } from '@/components/settings/GeneralTab'
import { IntegrationsTab } from '@/components/settings/IntegrationsTab'
import { AIProvidersTab } from '@/components/settings/AIProvidersTab'
import { StorageTab } from '@/components/settings/StorageTab'
import { ThreatIntelTab } from '@/components/settings/ThreatIntelTab'
import { NotificationsTab } from '@/components/settings/NotificationsTab'
import { AuthenticationTab } from '@/components/settings/AuthenticationTab'
import { MitrePatternManager } from '@/components/settings/MitrePatternManager'

const TAB_CONFIG = [
    { value: 'general', label: 'General', icon: Settings },
    { value: 'integrations', label: 'Integrations', icon: Puzzle },
    { value: 'ai', label: 'AI Providers', icon: Zap },
    { value: 'storage', label: 'Storage', icon: Database },
    { value: 'threat-intel', label: 'Threat Intel', icon: Search },
    { value: 'mitre-patterns', label: 'MITRE Patterns', icon: FileCode2 },
    { value: 'notifications', label: 'Notifications', icon: Bell },
    { value: 'authentication', label: 'Authentication', icon: Shield },
] as const

export default function SettingsPage() {
    const searchParams = useSearchParams()
    const defaultTab = searchParams.get('tab') || 'general'

    return (
        <div className="p-6 space-y-6">
            <div>
                <h1 className="text-2xl font-semibold">Settings</h1>
                <p className="text-sm text-muted-foreground mt-1">Configure system settings and integrations</p>
            </div>

            <Tabs defaultValue={defaultTab}>
                <TabsList className="flex-wrap h-auto gap-1">
                    {TAB_CONFIG.map(({ value, label, icon: Icon }) => (
                        <TabsTrigger key={value} value={value} className="gap-1.5">
                            <Icon className="h-4 w-4" />
                            <span className="hidden sm:inline">{label}</span>
                        </TabsTrigger>
                    ))}
                </TabsList>

                <TabsContent value="general" className="mt-6 max-w-4xl">
                    <GeneralTab />
                </TabsContent>
                <TabsContent value="integrations" className="mt-6">
                    <IntegrationsTab />
                </TabsContent>
                <TabsContent value="ai" className="mt-6 max-w-4xl">
                    <AIProvidersTab />
                </TabsContent>
                <TabsContent value="storage" className="mt-6 max-w-4xl">
                    <StorageTab />
                </TabsContent>
                <TabsContent value="threat-intel" className="mt-6 max-w-4xl">
                    <ThreatIntelTab />
                </TabsContent>
                <TabsContent value="mitre-patterns" className="mt-6 max-w-4xl">
                    <MitrePatternManager />
                </TabsContent>
                <TabsContent value="notifications" className="mt-6 max-w-4xl">
                    <NotificationsTab />
                </TabsContent>
                <TabsContent value="authentication" className="mt-6 max-w-4xl">
                    <AuthenticationTab />
                </TabsContent>
            </Tabs>
        </div>
    )
}
