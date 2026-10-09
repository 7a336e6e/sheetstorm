import type { ComponentType, ReactElement } from 'react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, render, screen } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { clearCache } from '@/lib/query-cache'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import { page, serviceAccount } from '@/components/api-keys/test-fixtures'

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/dashboard/admin/settings',
  useRouter: () => ({ push: () => {}, replace: () => {} }),
}))

// The other tabs are not under test here (they fetch their own data).
const stub = (name: string) => ({ [name]: () => null })
jest.mock('@/components/settings/GeneralTab', () => stub('GeneralTab'))
jest.mock('@/components/settings/IntegrationsTab', () => stub('IntegrationsTab'))
jest.mock('@/components/settings/AIProvidersTab', () => stub('AIProvidersTab'))
jest.mock('@/components/settings/StorageTab', () => stub('StorageTab'))
jest.mock('@/components/settings/ThreatIntelTab', () => stub('ThreatIntelTab'))
jest.mock('@/components/settings/NotificationsTab', () => stub('NotificationsTab'))
jest.mock('@/components/settings/AuthenticationTab', () => stub('AuthenticationTab'))
jest.mock('@/components/settings/MitrePatternManager', () => stub('MitrePatternManager'))
jest.mock('@/components/settings/AuditRetentionTab', () => stub('AuditRetentionTab'))

let SettingsPage: ComponentType
let ApiKeysTab: ComponentType
beforeAll(async () => {
  SettingsPage = (await import('@/app/dashboard/admin/settings/page')).default
  ;({ ApiKeysTab } = await import('./ApiKeysTab'))
})

function setPermissions(permissions: string[]) {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u-admin', email: 'a@x', name: 'Admin', roles: [], permissions },
      isAuthenticated: true,
    })
  })
}

beforeEach(() => {
  clearCache()
  jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    const path = endpoint.split('?')[0]
    if (path === '/organization') {
      return { id: 'org', name: 'Org', slug: 'default', is_default: true, settings: { api_key_max_lifetime_days: 180 } }
    }
    if (path === '/api-keys') return page([])
    if (path === '/service-accounts') return page([serviceAccount()])
    if (path === '/permissions') return { groups: [], items: [] }
    throw new ApiError(404, `unexpected GET ${endpoint}`)
  }) as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

/** Render and let the tab's initial requests settle. */
async function renderSettled(ui: ReactElement) {
  await act(async () => {
    render(ui)
  })
  await act(async () => {})
}

describe('Settings > API Keys tab (C28: api_keys:manage)', () => {
  it('is listed for api_keys:manage', async () => {
    setPermissions(['api_keys:manage'])
    await renderSettled(<SettingsPage />)
    expect(screen.getByRole('tab', { name: /API Keys/ })).toBeInTheDocument()
  })

  it('is not listed with api_keys:own or the organization permission alone', async () => {
    setPermissions(['api_keys:own', 'organizations:manage'])
    await renderSettled(<SettingsPage />)
    expect(screen.queryByRole('tab', { name: /API Keys/ })).toBeNull()
    expect(screen.getByRole('tab', { name: /General/ })).toBeInTheDocument()
  })

  it('renders none of the API key content without the permission', async () => {
    setPermissions(['organizations:manage'])
    await renderSettled(<SettingsPage />)
    expect(screen.queryByRole('tab', { name: /API Keys/ })).toBeNull()
    expect(screen.queryByText('Service accounts')).toBeNull()
  })
})

describe('ApiKeysTab', () => {
  const renderTab = () =>
    renderSettled(
      <ConfirmDialogProvider>
        <ApiKeysTab />
      </ConfirmDialogProvider>
    )

  it('shows the org policy, every key and the service accounts to a manager', async () => {
    setPermissions(['api_keys:manage', 'api_keys:own', 'organizations:manage'])
    await renderTab()
    expect(await screen.findByLabelText('Allow API keys')).toBeInTheDocument()
    expect(screen.getByLabelText('Maximum key lifetime (days)')).toHaveValue('180')
    expect(await screen.findByText('ingest-bot')).toBeInTheDocument()
    expect(screen.getByRole('grid', { name: 'API keys of the organization' })).toBeInTheDocument()
    expect(screen.getByRole('grid', { name: 'Service accounts' })).toBeInTheDocument()
  })

  it('renders nothing but a notice without api_keys:manage', async () => {
    setPermissions(['api_keys:own'])
    await renderTab()
    expect(screen.getByText(/don't have access to API key management/)).toBeInTheDocument()
    expect(screen.queryByRole('grid')).toBeNull()
  })
})
