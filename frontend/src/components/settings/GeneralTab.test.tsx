import { afterEach, beforeEach, describe, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import type { Organization } from '@/types'
import {
  AI_TLP_POLICY_DEFAULTS,
  GeneralTab,
  buildOrganizationUpdate,
  formFromOrganization,
  loosenedLevels,
} from './GeneralTab'

function org(over: Partial<Organization> = {}): Organization {
  return {
    id: 'org-1',
    name: 'Acme',
    slug: 'default',
    is_default: true,
    settings: {
      timezone: 'Europe/Paris',
      auto_enrich_iocs: false,
      enrichment_allow_amber_strict: false,
      ai_tlp_policy: { ...AI_TLP_POLICY_DEFAULTS },
    },
    ...over,
  }
}

let current: Organization
let putSpy: jest.Mock<(endpoint: string, data?: unknown) => Promise<unknown>>

beforeEach(() => {
  current = org()
  jest.spyOn(api, 'get').mockImplementation((async () => current) as unknown as typeof api.get)
  putSpy = jest.fn<(endpoint: string, data?: unknown) => Promise<unknown>>(async () => current)
  jest.spyOn(api, 'put').mockImplementation(putSpy as unknown as typeof api.put)
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'a@x', name: 'A', roles: [], permissions: ['organizations:manage'] },
      isAuthenticated: true,
    })
  })
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

function renderTab() {
  return render(
    <ConfirmDialogProvider>
      <GeneralTab />
    </ConfirmDialogProvider>
  )
}

describe('GeneralTab', () => {
  it('saves name + validated settings keys only (PUT payload shape)', async () => {
    renderTab()
    const name = await screen.findByLabelText('Organization name')
    fireEvent.change(name, { target: { value: '  Acme IR  ' } })
    fireEvent.click(screen.getByRole('switch', { name: 'Auto-enrich new indicators' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(putSpy).toHaveBeenCalled())
    expect(putSpy.mock.calls[0][0]).toBe('/organization')
    expect(putSpy.mock.calls[0][1]).toEqual({
      name: 'Acme IR',
      settings: {
        timezone: 'Europe/Paris',
        auto_enrich_iocs: true,
        enrichment_allow_amber_strict: false,
        ai_tlp_policy: { white: 'allow', green: 'allow', amber: 'allow', amber_strict: 'local_only', red: 'local_only' },
      },
    })
  })

  it('has no registration switch (it moved to the Security tab) and never sends it', async () => {
    renderTab()
    await screen.findByLabelText('Organization name')
    expect(screen.queryByRole('switch', { name: 'Allow self-registration' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(putSpy).toHaveBeenCalled())
    const body = putSpy.mock.calls[0][1] as { settings: Record<string, unknown> }
    expect(body.settings).not.toHaveProperty('registration_enabled')
  })

  it('shows the Data egress card with the red enrichment row locked', async () => {
    renderTab()
    const table = await screen.findByRole('table', { name: 'Data egress by TLP level' })
    expect(within(table).getAllByRole('row')).toHaveLength(6) // header + 5 TLP levels
    expect(within(table).getByTestId('enrichment-red-locked')).toHaveTextContent('Always blocked')
    expect(within(table).getByRole('combobox', { name: 'AI processing for TLP:RED' })).toHaveTextContent(
      'Local providers only'
    )
    expect(
      within(table).getByRole('switch', { name: 'Allow enrichment of TLP:AMBER+STRICT indicators' })
    ).not.toBeChecked()
  })

  it('asks before allowing AMBER+STRICT enrichment and does not save on cancel', async () => {
    renderTab()
    await screen.findByLabelText('Organization name')
    fireEvent.click(screen.getByRole('switch', { name: 'Allow enrichment of TLP:AMBER+STRICT indicators' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Loosen data egress policy?')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(putSpy).not.toHaveBeenCalled()
  })

  it('shows field errors from a 400 validation_error', async () => {
    putSpy.mockImplementation(async () => {
      throw new ApiError(400, 'Invalid organization settings', {
        code: 'validation_error',
        details: { error: 'validation_error', fields: { 'settings.timezone': 'Unknown IANA timezone' } },
      })
    })
    renderTab()
    await screen.findByLabelText('Organization name')
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Unknown IANA timezone')).toBeInTheDocument()
  })
})

describe('GeneralTab helpers', () => {
  it('detects loosened AI levels only', () => {
    const before = { ...AI_TLP_POLICY_DEFAULTS }
    expect(loosenedLevels(before, { ...before, red: 'allow', green: 'block' })).toEqual(['red'])
    expect(loosenedLevels(before, { ...before, amber: 'local_only' })).toEqual([])
  })

  it('fills missing AI levels with the defaults', () => {
    const o = org({ settings: { ai_tlp_policy: { red: 'block' } } })
    expect(formFromOrganization(o).ai_tlp_policy).toEqual({ ...AI_TLP_POLICY_DEFAULTS, red: 'block' })
    expect(buildOrganizationUpdate(o, formFromOrganization(o)).settings?.ai_tlp_policy?.red).toBe('block')
  })
})
