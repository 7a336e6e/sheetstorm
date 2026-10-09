/**
 * Settings page: one tab per area, each a component under @/components/settings/*.
 * A tab is listed when the user holds ANY of its `anyOf` permissions; the
 * requested `?tab=` falls back to the first visible tab.
 */

"use client"

import { Suspense, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { Settings, Zap, Database, Search, Bell, Shield, Puzzle, FileCode2, ScrollText } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { GeneralTab } from '@/components/settings/GeneralTab'
import { IntegrationsTab } from '@/components/settings/IntegrationsTab'
import { AIProvidersTab } from '@/components/settings/AIProvidersTab'
import { StorageTab } from '@/components/settings/StorageTab'
import { ThreatIntelTab } from '@/components/settings/ThreatIntelTab'
import { NotificationsTab } from '@/components/settings/NotificationsTab'
import { AuthenticationTab } from '@/components/settings/AuthenticationTab'
import { MitrePatternManager } from '@/components/settings/MitrePatternManager'
import { AuditRetentionTab } from '@/components/settings/AuditRetentionTab'
import { useAuthStore } from '@/lib/store'

const TAB_CONFIG = [
    { value: 'general', label: 'General', icon: Settings, anyOf: ['organizations:manage'] },
    { value: 'integrations', label: 'Integrations', icon: Puzzle, anyOf: ['integrations:read'] },
    { value: 'ai', label: 'AI Providers', icon: Zap, anyOf: ['integrations:read'] },
    { value: 'storage', label: 'Storage', icon: Database, anyOf: ['integrations:read'] },
    { value: 'threat-intel', label: 'Threat Intel', icon: Search, anyOf: ['integrations:read'] },
    // Read-only without admin:manage (MitrePatternManager gates editing).
    { value: 'mitre-patterns', label: 'MITRE Patterns', icon: FileCode2, anyOf: ['incidents:read', 'admin:manage'] },
    { value: 'notifications', label: 'Notifications', icon: Bell, anyOf: ['integrations:read'] },
    { value: 'authentication', label: 'Authentication', icon: Shield, anyOf: ['integrations:read'] },
    { value: 'audit-retention', label: 'Audit Retention', icon: ScrollText, anyOf: ['organizations:manage'] },
]

/** Tabs a user holding `permissions` may see, in display order. */
function visibleTabs(permissions: readonly string[] | undefined) {
    const granted = permissions ?? []
    return TAB_CONFIG.filter((t) => t.anyOf.some((p) => granted.includes(p)))
}

function SettingsInner() {
    const searchParams = useSearchParams()
    const permissions = useAuthStore((s) => s.user?.permissions)
    const tabs = visibleTabs(permissions)
    const requested = searchParams.get('tab')
    const initial = tabs.find((t) => t.value === requested)?.value ?? tabs[0]?.value
    const show = (value: string | null | undefined) => tabs.some((t) => t.value === value)
    const [tab, setTab] = useState(initial)
    // Follow in-app links to another ?tab= while mounted.
    const [lastRequested, setLastRequested] = useState(requested)
    if (requested !== lastRequested) {
        setLastRequested(requested)
        if (show(requested)) setTab(requested!)
    }
    // Permissions can change at runtime (permissions_changed): never leave a hidden tab selected.
    const current = show(tab) ? tab : initial

    return (
        <div className="p-6 space-y-6">
            <div>
                <h1 className="text-2xl font-semibold">Settings</h1>
                <p className="text-sm text-muted-foreground mt-1">Configure system settings and integrations</p>
            </div>

            {tabs.length === 0 ? (
                <p className="text-sm text-muted-foreground">You don&apos;t have access to any settings.</p>
            ) : (
            <Tabs value={current} onValueChange={setTab}>
                <TabsList className="flex-wrap h-auto gap-1">
                    {tabs.map(({ value, label, icon: Icon }) => (
                        <TabsTrigger key={value} value={value} className="gap-1.5">
                            <Icon className="h-4 w-4" />
                            <span className="hidden sm:inline">{label}</span>
                        </TabsTrigger>
                    ))}
                </TabsList>

                {show('general') && (
                    <TabsContent value="general" className="mt-6 max-w-4xl">
                        <GeneralTab />
                    </TabsContent>
                )}
                {show('integrations') && (
                    <TabsContent value="integrations" className="mt-6">
                        <IntegrationsTab />
                    </TabsContent>
                )}
                {show('ai') && (
                    <TabsContent value="ai" className="mt-6 max-w-4xl">
                        <AIProvidersTab />
                    </TabsContent>
                )}
                {show('storage') && (
                    <TabsContent value="storage" className="mt-6 max-w-4xl">
                        <StorageTab />
                    </TabsContent>
                )}
                {show('threat-intel') && (
                    <TabsContent value="threat-intel" className="mt-6 max-w-4xl">
                        <ThreatIntelTab />
                    </TabsContent>
                )}
                {show('mitre-patterns') && (
                    <TabsContent value="mitre-patterns" className="mt-6 max-w-4xl">
                        <MitrePatternManager />
                    </TabsContent>
                )}
                {show('notifications') && (
                    <TabsContent value="notifications" className="mt-6 max-w-4xl">
                        <NotificationsTab />
                    </TabsContent>
                )}
                {show('authentication') && (
                    <TabsContent value="authentication" className="mt-6 max-w-4xl">
                        <AuthenticationTab />
                    </TabsContent>
                )}
                {show('audit-retention') && (
                    <TabsContent value="audit-retention" className="mt-6 max-w-4xl">
                        <AuditRetentionTab />
                    </TabsContent>
                )}
            </Tabs>
            )}
        </div>
    )
}

export default function SettingsPage() {
    return (
        <Suspense fallback={null}>
            <SettingsInner />
        </Suspense>
    )
}
