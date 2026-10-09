import type { ComponentType } from 'react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { clearCache } from '@/lib/query-cache'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import { SCOPES, SECRET, apiKey, page, serviceAccount, withSecret } from './test-fixtures'

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/dashboard/profile',
  useRouter: () => ({ push: () => {}, replace: () => {} }),
}))

// Loaded after the next/navigation mock above is registered.
let ApiKeysPanel: ComponentType<{
  scope: 'mine' | 'org'
  createOpen?: boolean
  onCreateOpenChange?: (open: boolean) => void
  defaultOwnerId?: string
}>
beforeAll(async () => {
  ;({ ApiKeysPanel } = await import('./ApiKeysPanel'))
})

type Fn = (endpoint: string, data?: unknown) => Promise<unknown>
let keys = [apiKey()]
let getSpy: jest.Mock<Fn>
let postSpy: jest.Mock<Fn>
let deleteSpy: jest.Mock<Fn>

function setPermissions(permissions: string[]) {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u-me', email: 'me@x', name: 'Me', roles: [], permissions },
      isAuthenticated: true,
    })
  })
}

beforeEach(() => {
  clearCache()
  keys = [apiKey()]
  getSpy = jest.fn<Fn>(async (endpoint) => {
    const path = endpoint.split('?')[0]
    if (path === '/api-keys') return page(keys)
    if (path === '/api-keys/scopes') return SCOPES
    if (path === '/permissions') return { groups: [], items: [] }
    if (path === '/service-accounts') return page([serviceAccount()])
    throw new ApiError(404, `unexpected GET ${endpoint}`)
  })
  postSpy = jest.fn<Fn>(async () => withSecret())
  deleteSpy = jest.fn<Fn>(async () => apiKey({ status: 'revoked' }))
  jest.spyOn(api, 'get').mockImplementation(getSpy as unknown as typeof api.get)
  jest.spyOn(api, 'post').mockImplementation(postSpy as unknown as typeof api.post)
  jest.spyOn(api, 'delete').mockImplementation(deleteSpy as unknown as typeof api.delete)
  setPermissions(['api_keys:own'])
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

async function renderPanel(scope: 'mine' | 'org' = 'mine') {
  render(
    <ConfirmDialogProvider>
      <ApiKeysPanel scope={scope} />
    </ConfirmDialogProvider>
  )
  await screen.findByText(keys[0].name)
}

const rowOf = (name: string) => screen.getByText(name).closest('tr') as HTMLElement
const keyListCalls = () => getSpy.mock.calls.filter(([e]) => e.startsWith('/api-keys?'))

async function openRowMenu(name: string) {
  fireEvent.keyDown(rowOf(name), { key: '.' })
  return screen.findByRole('menu')
}

describe('list', () => {
  it('loads only my keys for the profile card (?mine=true)', async () => {
    await renderPanel('mine')
    expect(keyListCalls().some(([e]) => e.includes('mine=true'))).toBe(true)
    expect(screen.getByText('ssk_abcdefghij23')).toBeInTheDocument()
  })

  it('flags a key that expires within 14 days', async () => {
    keys = [apiKey({ expires_at: new Date(Date.now() + 5 * 86_400_000).toISOString() })]
    await renderPanel()
    expect(screen.getByText(/Expires in [45] days/)).toBeInTheDocument()
  })

  it('does not flag a key that expires later', async () => {
    await renderPanel()
    expect(screen.queryByText(/Expires in/)).toBeNull()
  })
})

describe('create', () => {
  async function openCreate() {
    fireEvent.click(await screen.findByRole('button', { name: /Create API key/ }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByLabelText('View timeline events')
    return dialog
  }

  it('creates a key and shows the secret once', async () => {
    await renderPanel()
    const dialog = await openCreate()
    const submit = within(dialog).getByRole('button', { name: 'Create key' })
    expect(submit).toBeDisabled()

    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'CI ingest' } })
    expect(submit).toBeDisabled() // still no scopes
    fireEvent.click(within(dialog).getByLabelText('Select all Timeline'))
    await waitFor(() => expect(submit).toBeEnabled())
    fireEvent.click(submit)

    await waitFor(() => expect(postSpy).toHaveBeenCalledTimes(1))
    expect(postSpy).toHaveBeenCalledWith('/api-keys', {
      name: 'CI ingest',
      description: undefined,
      scopes: ['timeline:create', 'timeline:delete', 'timeline:read', 'timeline:update'],
      expires_in_days: 90,
      owner_id: undefined,
    })

    // Shown once in the secret dialog...
    const secretDialog = await screen.findByRole('dialog', { name: 'API key created' })
    expect(within(secretDialog).getByTestId('api-key-secret')).toHaveTextContent(SECRET)
    fireEvent.click(within(secretDialog).getByLabelText('I have stored this key'))
    fireEvent.click(within(secretDialog).getByRole('button', { name: 'Done' }))

    // ...and gone afterwards; the list was refetched.
    await waitFor(() => expect(screen.queryByTestId('api-key-secret')).toBeNull())
    expect(document.body.textContent).not.toContain(SECRET)
    await waitFor(() => expect(keyListCalls().length).toBeGreaterThan(1))
  })

  it('shows the server reason for non-grantable scopes and keeps the form', async () => {
    postSpy.mockRejectedValueOnce(
      new ApiError(400, 'Some scopes cannot be granted to this key', {
        code: 'invalid_scopes',
        details: { forbidden: ['users:manage'], unknown: [], not_held: ['incidents:export'] },
      })
    )
    await renderPanel()
    const dialog = await openCreate()
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'CI ingest' } })
    fireEvent.click(within(dialog).getByLabelText('View timeline events'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create key' }))

    const alert = await within(dialog).findByRole('alert')
    expect(alert).toHaveTextContent('Invalid scopes')
    expect(alert).toHaveTextContent('Not grantable to keys: users:manage')
    expect(alert).toHaveTextContent('Not held by the owner: incidents:export')
    expect(screen.queryByTestId('api-key-secret')).toBeNull()
    expect(within(dialog).getByLabelText('Name')).toHaveValue('CI ingest')
  })

  it('explains api_keys_disabled instead of a generic permission error', async () => {
    postSpy.mockRejectedValueOnce(
      new ApiError(403, 'API keys are disabled for this organization', { code: 'api_keys_disabled' })
    )
    await renderPanel()
    const dialog = await openCreate()
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'k' } })
    fireEvent.click(within(dialog).getByLabelText('View timeline events'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create key' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('API keys are switched off')
  })

  it('blocks creation when the org has keys disabled', async () => {
    getSpy.mockImplementation(async (endpoint) => {
      const path = endpoint.split('?')[0]
      if (path === '/api-keys') return page(keys)
      if (path === '/api-keys/scopes') return { ...SCOPES, api_keys_enabled: false }
      throw new ApiError(404, 'nope')
    })
    await renderPanel()
    const dialog = await openCreate()
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('API keys are disabled')
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'k' } })
    fireEvent.click(within(dialog).getByLabelText('View timeline events'))
    expect(within(dialog).getByRole('button', { name: 'Create key' })).toBeDisabled()
  })

  it('has no create button without api_keys:own', async () => {
    setPermissions([])
    await renderPanel()
    expect(screen.queryByRole('button', { name: /Create API key/ })).toBeNull()
  })
})

describe('rotate', () => {
  it('rotates with the default (no grace) and shows the new secret once', async () => {
    postSpy.mockResolvedValueOnce(withSecret({ id: 'k-2', prefix: 'ssk_newnewnew234' }))
    await renderPanel()
    const menu = await openRowMenu('Local MCP')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Rotate' }))
    const dialog = await screen.findByRole('dialog', { name: /Rotate Local MCP/ })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Rotate key' }))

    await waitFor(() => expect(postSpy).toHaveBeenCalledTimes(1))
    expect(postSpy).toHaveBeenCalledWith('/api-keys/k-1/rotate', { grace_minutes: 0, expires_in_days: undefined })
    const secretDialog = await screen.findByRole('dialog', { name: 'API key rotated' })
    expect(within(secretDialog).getByTestId('api-key-secret')).toHaveTextContent(SECRET)
    expect(within(secretDialog).getByText(/previous key stopped working immediately/)).toBeInTheDocument()
    fireEvent.click(within(secretDialog).getByLabelText('I have stored this key'))
    fireEvent.click(within(secretDialog).getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(screen.queryByTestId('api-key-secret')).toBeNull())
  })

  it('does not offer rotate on a key already rotating out', async () => {
    keys = [apiKey({ status: 'active', revoked_at: '2099-01-01T00:00:00+00:00' })]
    await renderPanel()
    expect(screen.getByText('Rotating out')).toBeInTheDocument()
    const menu = await openRowMenu('Local MCP')
    expect(within(menu).queryByRole('menuitem', { name: 'Rotate' })).toBeNull()
    expect(within(menu).getByRole('menuitem', { name: 'Revoke' })).toBeInTheDocument()
  })

  it('shows a server refusal inline', async () => {
    postSpy.mockRejectedValueOnce(new ApiError(409, 'Only an active key can be rotated', { code: 'key_not_active' }))
    await renderPanel()
    const menu = await openRowMenu('Local MCP')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Rotate' }))
    const dialog = await screen.findByRole('dialog', { name: /Rotate Local MCP/ })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Rotate key' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Key is not active')
  })
})

describe('revoke', () => {
  it('confirms, sends the reason and refreshes the list', async () => {
    await renderPanel()
    const menu = await openRowMenu('Local MCP')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Revoke' }))

    const dialog = await screen.findByRole('dialog', { name: 'Revoke Local MCP?' })
    expect(deleteSpy).not.toHaveBeenCalled()
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: 'leaked in a screenshot' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke key' }))

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledTimes(1))
    expect(deleteSpy).toHaveBeenCalledWith('/api-keys/k-1', { reason: 'leaked in a screenshot' })
    await waitFor(() => expect(keyListCalls().length).toBeGreaterThan(1))
  })

  it('does nothing when the confirmation is cancelled', async () => {
    await renderPanel()
    const menu = await openRowMenu('Local MCP')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Revoke' }))
    const dialog = await screen.findByRole('dialog', { name: 'Revoke Local MCP?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(deleteSpy).not.toHaveBeenCalled()
  })

  it('omits an empty reason', async () => {
    await renderPanel()
    const menu = await openRowMenu('Local MCP')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Revoke' }))
    const dialog = await screen.findByRole('dialog', { name: 'Revoke Local MCP?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke key' }))
    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith('/api-keys/k-1', {}))
  })

  it('offers no actions on a revoked key', async () => {
    keys = [apiKey({ status: 'revoked', revoked_at: '2026-10-02T00:00:00+00:00', revoked_reason: 'manual' })]
    await renderPanel()
    expect(screen.queryByRole('button', { name: /Actions for/ })).toBeNull()
  })
})

describe('org scope', () => {
  it("rotates only service-account keys, but can revoke any key", async () => {
    setPermissions(['api_keys:manage'])
    keys = [
      apiKey({
        id: 'k-sa',
        name: 'Bot key',
        owner_user_id: 'sa-1',
        owner: { id: 'sa-1', name: 'ingest-bot', email: 's@x', is_service_account: true },
      }),
      apiKey({
        id: 'k-bob',
        name: 'Bob key',
        owner_user_id: 'u-bob',
        owner: { id: 'u-bob', name: 'Bob', email: 'b@x', is_service_account: false },
      }),
    ]
    await renderPanel('org')
    const menu = await openRowMenu('Bot key')
    expect(within(menu).getByRole('menuitem', { name: 'Rotate' })).toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'Revoke' })).toBeInTheDocument()
    fireEvent.keyDown(menu, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull())
    const bobMenu = await openRowMenu('Bob key')
    expect(within(bobMenu).queryByRole('menuitem', { name: 'Rotate' })).toBeNull()
    expect(within(bobMenu).getByRole('menuitem', { name: 'Revoke' })).toBeInTheDocument()
  })
})

describe('create for a service account (api_keys:manage)', () => {
  it('requests the account\'s scopes and creates the key with owner_id', async () => {
    setPermissions(['api_keys:manage', 'api_keys:own'])
    render(
      <ConfirmDialogProvider>
        <ApiKeysPanel scope="org" createOpen defaultOwnerId="sa-1" onCreateOpenChange={() => {}} />
      </ConfirmDialogProvider>
    )
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByLabelText('View timeline events')
    expect(getSpy.mock.calls.some(([e]) => e === '/api-keys/scopes?owner_id=sa-1')).toBe(true)
    expect(within(dialog).getByRole('combobox', { name: 'Owner' })).toHaveTextContent('ingest-bot (service account)')

    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'bot key' } })
    fireEvent.click(within(dialog).getByLabelText('View timeline events'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create key' }))
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/api-keys', {
        name: 'bot key',
        description: undefined,
        scopes: ['timeline:read'],
        expires_in_days: 90,
        owner_id: 'sa-1',
      })
    )
    expect(await screen.findByRole('dialog', { name: 'API key created' })).toBeInTheDocument()
  })

  it('a manager without api_keys:own can only pick a service account (no "Me")', async () => {
    setPermissions(['api_keys:manage'])
    render(
      <ConfirmDialogProvider>
        <ApiKeysPanel scope="org" createOpen onCreateOpenChange={() => {}} />
      </ConfirmDialogProvider>
    )
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('Choose an owner to see the scopes it can grant.')).toBeInTheDocument()
    expect(getSpy.mock.calls.some(([e]) => e.startsWith('/api-keys/scopes'))).toBe(false)
  })
})
