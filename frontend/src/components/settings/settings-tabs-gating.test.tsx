import type { ComponentType } from 'react'
import { afterEach, beforeAll, beforeEach, describe, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import api from '@/lib/api'
import { useAuthStore } from '@/lib/store'

// Registered before the tabs are first loaded (dynamic imports below).
jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/dashboard/admin/settings',
  useRouter: () => ({ push: () => {}, replace: () => {} }),
}))

const TAB_MODULES = {
  Integrations: ['./IntegrationsTab', 'IntegrationsTab', 'Slack Ops'],
  'AI Providers': ['./AIProvidersTab', 'AIProvidersTab', 'OpenAI Prod'],
  Storage: ['./StorageTab', 'StorageTab', 'S3 Evidence'],
  'Threat Intel': ['./ThreatIntelTab', 'ThreatIntelTab', 'VirusTotal Main'],
  Notifications: ['./NotificationsTab', 'NotificationsTab', 'Slack Ops'],
} as const
type TabLabel = keyof typeof TAB_MODULES
const tabs = {} as Record<TabLabel, ComponentType>

beforeAll(async () => {
  for (const [label, [path, name]] of Object.entries(TAB_MODULES)) {
    const mod = (await import(`${path}`)) as Record<string, ComponentType>
    tabs[label as TabLabel] = mod[name]
  }
})

const row = (id: string, type: string, name: string) => ({ id, type, name, is_enabled: true, config: {} })
const type = (id: string, name: string, category: string) => ({
  id, name, description: '', category, config_fields: [], credential_fields: [],
})

const RESPONSES: Record<string, unknown> = {
  '/integrations': {
    items: [
      row('i-slack', 'slack', 'Slack Ops'),
      row('i-openai', 'openai', 'OpenAI Prod'),
      row('i-s3', 's3', 'S3 Evidence'),
      row('i-vt', 'virustotal', 'VirusTotal Main'),
    ],
  },
  '/integrations/types': {
    types: [
      type('slack', 'Slack', 'notification'),
      type('webhook', 'Webhook', 'notification'),
      type('openai', 'OpenAI', 'ai'),
      type('s3', 'S3', 'storage'),
      type('virustotal', 'VirusTotal', 'threat_intel'),
      type('misp', 'MISP', 'threat_intel'),
    ],
  },
  '/storage/stats': {
    total_artifacts: 0, total_size_bytes: 0, by_storage_type: {}, by_mime_type: {},
    disk_usage: { total_bytes: 100, used_bytes: 50, free_bytes: 50, usage_percent: 50 },
  },
  '/google-drive/status': { configured: true, connected: true, email: 'ir@example.test', root_folder_id: 'root' },
  '/mitre/patterns': { patterns: [] },
}

const READ_ONLY = ['integrations:read']
const FULL = ['integrations:read', 'integrations:create', 'integrations:update', 'integrations:delete']

function setPermissions(permissions: string[]) {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions },
      isAuthenticated: true,
    })
  })
}

beforeEach(() => {
  jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    const key = endpoint.split('?')[0]
    if (!(key in RESPONSES)) throw new Error(`unexpected GET ${endpoint}`)
    return RESPONSES[key]
  }) as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

/** Renders the tab and returns the card row of its integration `rowName`. */
async function renderTab(label: TabLabel) {
  const Tab = tabs[label]
  const rowName = TAB_MODULES[label][2]
  await act(async () => {
    render(<Tab />)
  })
  const title = await screen.findByText(rowName)
  return within(title.closest('[class*="justify-between"]') as HTMLElement)
}

describe.each(Object.keys(TAB_MODULES) as TabLabel[])('%s tab gating', (label) => {
  const rowName = TAB_MODULES[label][2]

  it('offers add / test / configure / delete to holders of the integration permissions', async () => {
    setPermissions(FULL)
    const card = await renderTab(label)
    expect(screen.getAllByRole('button', { name: /^add /i }).length).toBeGreaterThan(0)
    expect(card.getByRole('button', { name: 'Test' })).toBeInTheDocument()
    expect(card.getByRole('button', { name: 'Configure' })).toBeInTheDocument()
    expect(card.getByRole('button', { name: `Delete ${rowName}` })).toBeInTheDocument()
  })

  it('is read-only with integrations:read alone', async () => {
    setPermissions(READ_ONLY)
    const card = await renderTab(label)
    expect(screen.queryAllByRole('button', { name: /add/i })).toHaveLength(0)
    expect(card.queryByRole('button', { name: 'Test' })).toBeNull()
    expect(card.queryByRole('button', { name: 'Configure' })).toBeNull()
    expect(card.queryByRole('button', { name: `Delete ${rowName}` })).toBeNull()
  })
})

describe('tab-specific gating', () => {
  it('Storage: Google Drive folder / disconnect need integrations:update', async () => {
    setPermissions(READ_ONLY)
    await renderTab('Storage')
    expect(screen.queryByRole('button', { name: /folder/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /disconnect/i })).toBeNull()
    cleanup()
    setPermissions(FULL)
    await renderTab('Storage')
    expect(screen.getByRole('button', { name: /set folder/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /disconnect/i })).toBeInTheDocument()
  })

  it('Storage: renders the disk card without a server path (platform admins only get one)', async () => {
    setPermissions(READ_ONLY)
    await renderTab('Storage')
    expect(screen.getByText('Local artifact storage volume')).toBeInTheDocument()
  })

  it('Threat Intel: the MITRE suggest tester needs incidents:read', async () => {
    setPermissions(READ_ONLY)
    await renderTab('Threat Intel')
    const input = screen.getByPlaceholderText(/test MITRE auto-mapping/i)
    act(() => {
      fireEvent.change(input, { target: { value: 'powershell -enc' } })
    })
    expect(screen.getByRole('button', { name: /test suggestions/i })).toBeDisabled()
    expect(screen.getByText('Requires the incidents:read permission.')).toBeInTheDocument()
    cleanup()
    setPermissions([...READ_ONLY, 'incidents:read'])
    await renderTab('Threat Intel')
    act(() => {
      fireEvent.change(screen.getByPlaceholderText(/test MITRE auto-mapping/i), { target: { value: 'powershell -enc' } })
    })
    expect(screen.getByRole('button', { name: /test suggestions/i })).toBeEnabled()
  })

  it.each([
    ['Threat Intel', /MISP/],
    ['Notifications', /Webhook/],
  ] as Array<[TabLabel, RegExp]>)(
    '%s: available-provider tiles are disabled without integrations:create',
    async (label, tile) => {
      setPermissions(READ_ONLY)
      await renderTab(label)
      expect(screen.getByRole('button', { name: tile })).toBeDisabled()
    }
  )
})
