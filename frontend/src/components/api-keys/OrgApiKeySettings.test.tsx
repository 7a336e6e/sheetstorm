import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import api from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import { OrgApiKeySettings, parseLifetime } from './OrgApiKeySettings'

type Fn = (endpoint: string, data?: unknown) => Promise<unknown>
let putSpy: jest.Mock<Fn>
let settings: Record<string, unknown>

function setPermissions(permissions: string[]) {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'a@x', name: 'A', roles: [], permissions },
      isAuthenticated: true,
    })
  })
}

beforeEach(() => {
  settings = { api_keys_enabled: true, api_key_max_lifetime_days: 365 }
  jest.spyOn(api, 'get').mockImplementation((async () => ({ id: 'o', name: 'O', settings })) as unknown as typeof api.get)
  putSpy = jest.fn<Fn>(async () => ({ settings }))
  jest.spyOn(api, 'put').mockImplementation(putSpy as unknown as typeof api.put)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

async function renderCard() {
  await act(async () => {
    render(
      <ConfirmDialogProvider>
        <OrgApiKeySettings />
      </ConfirmDialogProvider>
    )
  })
  await screen.findByLabelText('Allow API keys')
}

describe('OrgApiKeySettings', () => {
  it('reads the current values; defaults apply when the org stored none', async () => {
    settings = {}
    setPermissions(['organizations:manage'])
    await renderCard()
    expect(screen.getByLabelText('Allow API keys')).toBeChecked()
    expect(screen.getByLabelText('Maximum key lifetime (days)')).toHaveValue('365')
  })

  it('saves the maximum lifetime through PUT /organization', async () => {
    setPermissions(['organizations:manage'])
    await renderCard()
    const input = screen.getByLabelText('Maximum key lifetime (days)')
    const save = screen.getByRole('button', { name: 'Save' })
    expect(save).toBeDisabled()
    fireEvent.change(input, { target: { value: '400' } })
    expect(save).toBeDisabled()
    expect(screen.getByText(/whole number from 1 to 365/)).toBeInTheDocument()
    fireEvent.change(input, { target: { value: '90' } })
    fireEvent.click(save)
    await waitFor(() => expect(putSpy).toHaveBeenCalledWith('/organization', { settings: { api_key_max_lifetime_days: 90 } }))
  })

  it('asks before disabling keys, then writes api_keys_enabled=false', async () => {
    setPermissions(['organizations:manage'])
    await renderCard()
    fireEvent.click(screen.getByLabelText('Allow API keys'))
    const dialog = await screen.findByRole('dialog', { name: 'Disable API keys?' })
    expect(putSpy).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Disable API keys' }))
    await waitFor(() => expect(putSpy).toHaveBeenCalledWith('/organization', { settings: { api_keys_enabled: false } }))
    await waitFor(() => expect(screen.getByLabelText('Allow API keys')).not.toBeChecked())
  })

  it('enabling needs no confirmation', async () => {
    settings = { api_keys_enabled: false }
    setPermissions(['organizations:manage'])
    await renderCard()
    fireEvent.click(screen.getByLabelText('Allow API keys'))
    await waitFor(() => expect(putSpy).toHaveBeenCalledWith('/organization', { settings: { api_keys_enabled: true } }))
  })

  it('is read-only for holders of api_keys:manage without organizations:manage', async () => {
    setPermissions(['api_keys:manage'])
    await renderCard()
    expect(screen.getByLabelText('Allow API keys')).toBeDisabled()
    expect(screen.getByLabelText('Maximum key lifetime (days)')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
    expect(screen.getByText(/requires the organization settings permission/)).toBeInTheDocument()
  })

  it('parses lifetimes strictly', () => {
    expect(parseLifetime('90')).toBe(90)
    expect(parseLifetime(' 365 ')).toBe(365)
    for (const bad of ['0', '366', '-1', '1.5', 'abc', '', '1e2']) expect(parseLifetime(bad)).toBeNull()
  })
})
