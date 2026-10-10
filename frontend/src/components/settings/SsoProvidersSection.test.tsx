import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import api from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import type { SsoProvider } from '@/types'
import { SsoProvidersSection } from './SsoProvidersSection'
import { AuthenticationTab } from './AuthenticationTab'

const TEMPLATE = 'https://ir.example.com/api/v1/auth/sso/{slug}/callback'

const provider = (over: Partial<SsoProvider> = {}): SsoProvider => ({
  id: 'p1', organization_id: 'o1', slug: 'corp-okta', display_name: 'Corp Okta', preset: 'okta',
  issuer: 'https://corp.okta.com/oauth2/default', client_id: 'cid', token_auth_method: 'client_secret_basic',
  scopes: 'openid email profile groups', email_claims: ['email'], name_claim: 'name', groups_claim: 'groups',
  role_mappings: [{ group: 'IR-Leads', role_id: 'r-manager' }], default_role_id: null, allowed_groups: [],
  allowed_domains: [], is_enabled: true, show_on_login: true, auto_provision: true, link_existing: false,
  require_email_verified: true, role_sync: 'first_login', mfa_mode: 'idp', has_client_secret: true,
  identity_count: 3, redirect_uri: TEMPLATE.replace('{slug}', 'corp-okta'),
  start_url: '/api/v1/auth/sso/corp-okta/start', created_at: null, updated_at: null, last_login_at: null, ...over,
})

const roles = [
  { id: 'r-analyst', name: 'Analyst', description: '', permissions: [], is_system: true },
  { id: 'r-manager', name: 'Manager', description: '', permissions: [], is_system: true },
]

let items: SsoProvider[]

beforeEach(() => {
  items = [provider()]
  jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    if (endpoint === '/admin/sso-providers') return { items, redirect_uri_template: TEMPLATE, allow_http_issuers: false }
    if (endpoint === '/roles') return { items: roles }
    if (endpoint === '/integrations/types') return { types: [] }
    if (endpoint === '/integrations') return { items: [] }
    throw new Error(`unexpected GET ${endpoint}`)
  }) as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

async function renderSection() {
  await act(async () => {
    render(
      <ConfirmDialogProvider>
        <SsoProvidersSection />
      </ConfirmDialogProvider>
    )
  })
}

describe('SsoProvidersSection', () => {
  it('lists providers with their redirect URI and status', async () => {
    await renderSection()
    const card = await screen.findByTestId('sso-provider-corp-okta')
    expect(within(card).getByText('Corp Okta')).toBeTruthy()
    expect(within(card).getByText('Okta')).toBeTruthy()
    expect(within(card).getByText('MFA by IdP')).toBeTruthy()
    expect(within(card).getByText(/3 linked accounts/)).toBeTruthy()
    expect(card.textContent).toContain('https://ir.example.com/api/v1/auth/sso/corp-okta/callback')
  })

  it('builds the issuer from the preset fields and creates the provider', async () => {
    const post = jest.spyOn(api, 'post').mockResolvedValue(provider({ id: 'p2' }) as never)
    await renderSection()
    fireEvent.click(screen.getByRole('button', { name: 'Add identity provider' }))
    const dialog = await screen.findByRole('dialog')

    // Default preset: Microsoft Entra ID (no email_verified, app roles).
    fireEvent.change(within(dialog).getByLabelText(/Directory \(tenant\) ID/), { target: { value: 'tenant-123' } })
    expect(dialog.textContent).toContain('https://login.microsoftonline.com/tenant-123/v2.0')
    expect(within(dialog).getByTestId('sso-redirect-uri').textContent).toBe(
      'https://ir.example.com/api/v1/auth/sso/microsoft-entra-id/callback')

    fireEvent.change(within(dialog).getByLabelText(/^Client ID/), { target: { value: 'app-id' } })
    fireEvent.change(within(dialog).getByLabelText(/^Client secret/), { target: { value: 's3cret' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Map a group to a role' }))
    fireEvent.change(within(dialog).getByLabelText('Group 1'), { target: { value: 'SheetStorm.Responder' } })
    fireEvent.change(within(dialog).getByLabelText('Role for group 1'), { target: { value: 'r-analyst' } })
    fireEvent.change(within(dialog).getByLabelText(/^Allowed email domains/), { target: { value: 'contoso.com, @Contoso.org' } })

    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Add provider' }))
    })
    await waitFor(() => expect(post).toHaveBeenCalled())
    const [endpoint, body] = post.mock.calls[0] as [string, Record<string, unknown>]
    expect(endpoint).toBe('/admin/sso-providers')
    expect(body).toMatchObject({
      slug: 'microsoft-entra-id', display_name: 'Microsoft Entra ID', preset: 'entra',
      issuer: 'https://login.microsoftonline.com/tenant-123/v2.0', client_id: 'app-id', client_secret: 's3cret',
      require_email_verified: false, groups_claim: 'roles', email_claims: ['email', 'preferred_username'],
      role_mappings: [{ group: 'SheetStorm.Responder', role_id: 'r-analyst' }],
      allowed_domains: ['contoso.com', '@Contoso.org'],
    })
  })

  it('switching presets replaces the claim defaults and keeps a custom label', async () => {
    jest.spyOn(api, 'post').mockResolvedValue(provider() as never)
    await renderSection()
    fireEvent.click(screen.getByRole('button', { name: 'Add identity provider' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/^Button label/), { target: { value: 'Lab SSO' } })
    fireEvent.change(within(dialog).getByLabelText(/^Identity provider/), { target: { value: 'keycloak' } })
    expect((within(dialog).getByLabelText(/^Button label/) as HTMLInputElement).value).toBe('Lab SSO')
    expect((within(dialog).getByLabelText(/^Groups claim/) as HTMLInputElement).value).toBe('groups')
    fireEvent.change(within(dialog).getByLabelText(/^Keycloak host/), { target: { value: 'https://sso.lab.example/' } })
    fireEvent.change(within(dialog).getByLabelText(/^Realm/), { target: { value: 'ir' } })
    expect(dialog.textContent).toContain('https://sso.lab.example/realms/ir')
  })

  it('keeps the stored secret unless a new one is typed, and refuses incomplete forms', async () => {
    const put = jest.spyOn(api, 'put').mockResolvedValue(provider() as never)
    await renderSection()
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    const dialog = await screen.findByRole('dialog')
    expect((within(dialog).getByLabelText(/^Client secret/) as HTMLInputElement).placeholder).toBe('(unchanged)')
    fireEvent.change(within(dialog).getByLabelText(/^Client ID/), { target: { value: '' } })
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))
    })
    expect(within(dialog).getByRole('alert').textContent).toContain('the client ID')
    expect(put).not.toHaveBeenCalled()

    fireEvent.change(within(dialog).getByLabelText(/^Client ID/), { target: { value: 'cid-2' } })
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))
    })
    await waitFor(() => expect(put).toHaveBeenCalled())
    const [endpoint, body] = put.mock.calls[0] as [string, Record<string, unknown>]
    expect(endpoint).toBe('/admin/sso-providers/p1')
    expect(body.client_id).toBe('cid-2')
    expect('client_secret' in body).toBe(false)
    expect(body.issuer).toBe('https://corp.okta.com/oauth2/default')
  })

  it('shows the configuration check results', async () => {
    jest.spyOn(api, 'post').mockResolvedValue({
      ok: false, redirect_uri: '', checks: [
        { name: 'discovery', ok: true, warning: false, detail: 'issuer https://corp.okta.com/oauth2/default' },
        { name: 'PKCE', ok: true, warning: true, detail: 'S256 not advertised' },
        { name: 'signing keys', ok: false, warning: false, detail: 'jwks: no keys' },
      ],
    } as never)
    await renderSection()
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: 'Test' }))
    })
    const report = await screen.findByRole('list', { name: 'Configuration check' })
    expect(within(report).getByLabelText('failed')).toBeTruthy()
    expect(within(report).getByLabelText('warning')).toBeTruthy()
    expect(report.textContent).toContain('jwks: no keys')
  })
})

describe('AuthenticationTab gating', () => {
  const setPermissions = (permissions: string[]) =>
    act(() => {
      useAuthStore.setState({ user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions }, isAuthenticated: true })
    })

  it('shows single sign-on to users:manage and OAuth apps to integrations:read', async () => {
    setPermissions(['users:manage'])
    await act(async () => {
      render(<ConfirmDialogProvider><AuthenticationTab /></ConfirmDialogProvider>)
    })
    expect(await screen.findByText('Single sign-on (OpenID Connect)')).toBeTruthy()
    expect(screen.queryByText('OAuth apps')).toBeNull()
    cleanup()

    setPermissions(['integrations:read'])
    await act(async () => {
      render(<ConfirmDialogProvider><AuthenticationTab /></ConfirmDialogProvider>)
    })
    expect(await screen.findByText('OAuth apps')).toBeTruthy()
    expect(screen.queryByText('Single sign-on (OpenID Connect)')).toBeNull()
  })
})
