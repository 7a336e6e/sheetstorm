// Shared fixtures for the API-key component tests (not imported by app code).
import type { ApiKey, ApiKeyScopesResponse, ApiKeyWithSecret, ServiceAccount } from '@/types'

export const SECRET = 'ssk_abcdefghij23_SECRETSECRETSECRETSECRETSECRETSECRETSEC'

const scope = (value: string, label: string, sensitive = false) => ({
  value,
  label,
  description: `${label} description`,
  sensitive,
})

export const SCOPES: ApiKeyScopesResponse = {
  owner_id: 'u-me',
  max_lifetime_days: 365,
  api_keys_enabled: true,
  groups: [
    {
      group: 'incidents',
      label: 'Incidents',
      scopes: [
        scope('incidents:read', 'View incidents'),
        scope('incidents:update', 'Edit incidents'),
        scope('incidents:export', 'Export incident data', true),
      ],
    },
    {
      group: 'timeline',
      label: 'Timeline',
      scopes: [
        scope('timeline:read', 'View timeline events'),
        scope('timeline:create', 'Create timeline events'),
        scope('timeline:update', 'Edit timeline events'),
        scope('timeline:delete', 'Delete timeline events', true),
      ],
    },
    {
      group: 'users',
      label: 'Users',
      scopes: [scope('users:read', 'View users')],
    },
  ],
}

export function apiKey(over: Partial<ApiKey> = {}): ApiKey {
  return {
    id: 'k-1',
    organization_id: 'org-1',
    owner_user_id: 'u-me',
    name: 'Local MCP',
    description: null,
    prefix: 'ssk_abcdefghij23',
    scopes: ['incidents:read', 'timeline:read'],
    status: 'active',
    expires_at: '2099-01-01T00:00:00+00:00',
    last_used_at: null,
    last_used_ip: null,
    use_count: 0,
    rotated_from_id: null,
    revoked_at: null,
    revoked_by: null,
    revoked_reason: null,
    created_by: 'u-me',
    created_at: '2026-10-01T00:00:00+00:00',
    updated_at: null,
    owner: { id: 'u-me', name: 'Me', email: 'me@x', is_service_account: false },
    ...over,
  }
}

export const withSecret = (over: Partial<ApiKey> = {}): ApiKeyWithSecret => ({ ...apiKey(over), secret: SECRET })

export function serviceAccount(over: Partial<ServiceAccount> = {}): ServiceAccount {
  return {
    id: 'sa-1',
    name: 'ingest-bot',
    email: 'svc-ingest-bot@service.invalid',
    is_active: true,
    is_service_account: true,
    roles: [{ id: 'r-analyst', name: 'Analyst' }],
    active_key_count: 2,
    created_at: '2026-09-01T00:00:00+00:00',
    deactivated_at: null,
    ...over,
  }
}

export function page<T>(items: T[]) {
  return { items, total: items.length, page: 1, per_page: 25, pages: 1, sort: '-created_at' }
}
