/**
 * API Keys tab in Settings (needs `api_keys:manage`): the organization policy
 * (enable / max lifetime), every key of the organization, and service
 * accounts. Components live in @/components/api-keys.
 */

"use client"

import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PermissionGate } from '@/components/auth/permission-gate'
import { ApiKeysPanel } from '@/components/api-keys/ApiKeysPanel'
import { OrgApiKeySettings } from '@/components/api-keys/OrgApiKeySettings'
import { ServiceAccountsPanel } from '@/components/api-keys/ServiceAccountsPanel'

export function ApiKeysTab() {
  const [createOpen, setCreateOpen] = useState(false)
  const [ownerId, setOwnerId] = useState<string | undefined>()

  return (
    <PermissionGate
      permission="api_keys:manage"
      fallback={<p className="text-sm text-muted-foreground">You don&apos;t have access to API key management.</p>}
    >
      <div className="space-y-6">
        <OrgApiKeySettings />

        <Card>
          <CardHeader>
            <CardTitle className="text-base">API keys</CardTitle>
            <CardDescription>
              Every key in the organization with its last use. Revoke any key at once; rotate service account keys
              with an optional grace period.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ApiKeysPanel
              scope="org"
              urlKey="keys"
              createOpen={createOpen}
              defaultOwnerId={ownerId}
              onCreateOpenChange={(open) => {
                setCreateOpen(open)
                if (!open) setOwnerId(undefined)
              }}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Service accounts</CardTitle>
            <CardDescription>
              Non-interactive identities that own keys for automation. Their keys are limited to the permissions of
              their roles.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ServiceAccountsPanel
              urlKey="sa"
              onCreateKey={(account) => {
                setOwnerId(account.id)
                setCreateOpen(true)
              }}
            />
          </CardContent>
        </Card>
      </div>
    </PermissionGate>
  )
}
