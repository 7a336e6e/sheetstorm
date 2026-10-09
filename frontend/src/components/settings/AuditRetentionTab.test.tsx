import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { AuditSettings } from '@/types'

const mockToast = jest.fn()
// Registered before lib/errors is first loaded (dynamic imports below).
jest.mock('@/components/ui/use-toast', () => ({ toast: (...args: unknown[]) => mockToast(...args) }))

let api: typeof import('@/lib/api').default
let ApiError: typeof import('@/lib/api').ApiError
let useAuthStore: typeof import('@/lib/store').useAuthStore
let ConfirmDialogProvider: typeof import('@/components/ui/confirm-dialog').ConfirmDialogProvider
let AuditRetentionTab: typeof import('./AuditRetentionTab').AuditRetentionTab

beforeAll(async () => {
  ;({ default: api, ApiError } = await import('@/lib/api'))
  ;({ useAuthStore } = await import('@/lib/store'))
  ;({ ConfirmDialogProvider } = await import('@/components/ui/confirm-dialog'))
  ;({ AuditRetentionTab } = await import('./AuditRetentionTab'))
})

const SETTINGS: AuditSettings = {
  audit_retention_days: 730,
  legal_hold: false,
  legal_hold_reason: null,
  legal_hold_set_by: null,
  legal_hold_set_at: null,
  min_retention_days: 365,
  max_retention_days: 36500,
}

type PutBody = Record<string, unknown>
let putSpy: jest.SpiedFunction<typeof import('@/lib/api').default.put>
let putImpl: (body: PutBody) => Promise<unknown>

beforeEach(() => {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'admin@x', name: 'Admin', roles: [], permissions: ['organizations:manage'] },
      isAuthenticated: true,
    })
  })
  jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    if (endpoint === '/admin/audit-settings') return SETTINGS
    throw new Error(`unexpected GET ${endpoint}`)
  }) as unknown as typeof api.get)
  putImpl = async (body) => ({ ...SETTINGS, ...body })
  putSpy = jest.spyOn(api, 'put').mockImplementation((async (_endpoint: string, body: PutBody) =>
    putImpl(body)) as unknown as typeof api.put)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  mockToast.mockClear()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

async function renderTab() {
  await act(async () => {
    render(
      <ConfirmDialogProvider>
        <AuditRetentionTab />
      </ConfirmDialogProvider>
    )
  })
  await screen.findByText('Audit log retention')
}

const conflict = () =>
  new ApiError(409, 'Shortening retention deletes older audit rows at the next purge; resend with confirm: true', {
    code: 'confirmation_required',
    details: {
      error: 'confirmation_required',
      would_purge: 1234,
      cutoff: '2025-10-09T12:00:00+00:00',
    },
  })

describe('AuditRetentionTab: retention', () => {
  it('shortening shows the would_purge count and resends with confirm after the typed confirmation', async () => {
    let calls = 0
    putImpl = async (body) => {
      calls++
      if (calls === 1) throw conflict()
      return { ...SETTINGS, audit_retention_days: body.audit_retention_days as number }
    }
    await renderTab()
    expect(screen.getByTestId('current-retention')).toHaveTextContent('730 days')

    fireEvent.click(screen.getByRole('radio', { name: /1 year/ }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save retention' }))
    })

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Shorten audit retention?')).toBeInTheDocument()
    expect(within(dialog).getByTestId('would-purge')).toHaveTextContent('1,234 audit rows are older than the new cutoff')
    expect(putSpy).toHaveBeenCalledTimes(1)
    expect(putSpy.mock.calls[0][1]).toEqual({ audit_retention_days: 365 })

    const confirmBtn = within(dialog).getByRole('button', { name: 'Shorten retention' })
    expect(confirmBtn).toBeDisabled()
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: '36' } })
    expect(confirmBtn).toBeDisabled()
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: '365' } })
    expect(confirmBtn).toBeEnabled()
    await act(async () => {
      fireEvent.click(confirmBtn)
    })

    await waitFor(() => expect(putSpy).toHaveBeenCalledTimes(2))
    expect(putSpy.mock.calls[1]).toEqual(['/admin/audit-settings', { audit_retention_days: 365, confirm: true }])
    await waitFor(() => expect(screen.getByTestId('current-retention')).toHaveTextContent('365 days'))
  })

  it('cancelling the confirmation sends nothing more', async () => {
    putImpl = async () => {
      throw conflict()
    }
    await renderTab()
    fireEvent.click(screen.getByRole('radio', { name: /1 year/ }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save retention' }))
    })
    const dialog = await screen.findByRole('dialog')
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(putSpy).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('current-retention')).toHaveTextContent('730 days')
  })

  it('lengthening or keeping forever needs no confirmation', async () => {
    await renderTab()
    fireEvent.click(screen.getByRole('radio', { name: /Keep forever/ }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save retention' }))
    })
    expect(putSpy.mock.calls[0][1]).toEqual({ audit_retention_days: null })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('validates a custom value against the server bounds', async () => {
    await renderTab()
    fireEvent.click(screen.getByRole('radio', { name: /Custom/ }))
    const input = screen.getByLabelText('Retention (days)')
    fireEvent.change(input, { target: { value: '100' } })
    expect(screen.getByText(/between 365 and 36500/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save retention' })).toBeDisabled()
    fireEvent.change(input, { target: { value: '1000' } })
    expect(screen.getByRole('button', { name: 'Save retention' })).toBeEnabled()
  })
})

describe('AuditRetentionTab: legal hold', () => {
  it('requires a reason to place a hold', async () => {
    putImpl = async (body) => ({
      ...SETTINGS,
      legal_hold: true,
      legal_hold_reason: body.legal_hold_reason,
      legal_hold_set_at: '2026-10-09T10:00:00+00:00',
      legal_hold_set_by: 'u1',
    })
    await renderTab()
    await act(async () => {
      fireEvent.click(screen.getByRole('switch'))
    })
    const place = screen.getByRole('button', { name: 'Place legal hold' })
    expect(place).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Reason (required)'), { target: { value: '   ' } })
    expect(place).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Reason (required)'), { target: { value: 'Litigation hold: matter 14' } })
    expect(place).toBeEnabled()
    await act(async () => {
      fireEvent.click(place)
    })
    expect(putSpy.mock.calls[0][1]).toEqual({ legal_hold: true, legal_hold_reason: 'Litigation hold: matter 14' })
    expect(await screen.findByText('Legal hold is on')).toBeInTheDocument()
    expect(screen.getByText('Litigation hold: matter 14')).toBeInTheDocument()
  })

  it('asks before releasing a hold', async () => {
    jest.spyOn(api, 'get').mockImplementation((async () => ({
      ...SETTINGS,
      legal_hold: true,
      legal_hold_reason: 'Matter 9',
      legal_hold_set_at: '2026-10-01T00:00:00+00:00',
    })) as unknown as typeof api.get)
    await renderTab()
    await act(async () => {
      fireEvent.click(screen.getByRole('switch'))
    })
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Release the legal hold?')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Release hold' }))
    })
    await waitFor(() => expect(putSpy).toHaveBeenCalledTimes(1))
    expect(putSpy.mock.calls[0][1]).toEqual({ legal_hold: false })
  })
})

describe('AuditRetentionTab: integrity', () => {
  it('runs the chain check and shows the result', async () => {
    jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
      if (endpoint === '/admin/audit-settings') return SETTINGS
      if (endpoint === '/admin/audit-integrity') {
        return {
          ok: false, organization_id: 'o1', chain_key: 'audit:o1', checked: 120, failure_count: 2,
          failures: [{ seq: 41, id: 'a1b2c3d4-0000', reason: 'hash_mismatch' }, { seq: 57, id: null, reason: 'gap' }],
          unverifiable_rotated_key: 0, legacy_unchained: 3, head_seq: 120, head_hash: 'abcdef0123456789abcdef',
          purged_through_seq: 0, first_seq: 1, last_seq: 120, key_id: 'k1', verified_at: '2026-10-09T12:00:00+00:00',
        }
      }
      throw new Error(`unexpected GET ${endpoint}`)
    }) as unknown as typeof api.get)
    await renderTab()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Verify now' }))
    })
    expect(await screen.findByText('Chain verification failed: 2 problems')).toBeInTheDocument()
    const failures = screen.getByRole('table', { name: 'Chain failures' })
    expect(within(failures).getByText('Row edited (hash mismatch)')).toBeInTheDocument()
    expect(within(failures).getByText('Missing row (sequence gap)')).toBeInTheDocument()
  })
})
