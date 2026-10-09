"use client"

/**
 * "My API keys" card for the profile page: the caller's own keys with create,
 * rotate and revoke. Renders nothing without `api_keys:own`. Self-contained:
 * the profile page only mounts it.
 */
import { ExternalLink } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PermissionGate } from '@/components/auth/permission-gate'
import { MCP_API_KEY_ENV, MCP_DOCS_URL } from '@/lib/endpoints/api-keys'
import { ApiKeysPanel } from './ApiKeysPanel'

export function MyApiKeysCard() {
  return (
    <PermissionGate permission="api_keys:own">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">My API keys</CardTitle>
          <CardDescription>
            Personal keys for scripts and MCP clients. They work with MFA on, carry only the scopes you pick, and
            expire.{' '}
            <a
              href={MCP_DOCS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
            >
              MCP setup with {MCP_API_KEY_ENV}
              <ExternalLink className="h-3 w-3" aria-hidden />
            </a>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ApiKeysPanel scope="mine" />
        </CardContent>
      </Card>
    </PermissionGate>
  )
}
