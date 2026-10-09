import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const mockToast = jest.fn()
// Registered before lib/errors is first loaded (dynamic imports below).
jest.mock('@/components/ui/use-toast', () => ({ toast: (...args: unknown[]) => mockToast(...args) }))

let api: typeof import('@/lib/api').default
let ApiError: typeof import('@/lib/api').ApiError
let useAuthStore: typeof import('@/lib/store').useAuthStore
let AuditExportMenu: typeof import('./AuditExportMenu').AuditExportMenu

beforeAll(async () => {
  ;({ default: api, ApiError } = await import('@/lib/api'))
  ;({ useAuthStore } = await import('@/lib/store'))
  ;({ AuditExportMenu } = await import('./AuditExportMenu'))
})

function signIn(permissions: string[]) {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'u@x', name: 'U', roles: [], permissions },
      isAuthenticated: true,
    })
  })
}

const openMenu = () => fireEvent.keyDown(screen.getByRole('button', { name: /export/i }), { key: 'Enter' })

let download: jest.SpiedFunction<typeof import('@/lib/api').default.downloadTo>

beforeEach(() => {
  download = jest.spyOn(api, 'downloadTo').mockResolvedValue('audit-acme-20261009T120000Z.csv')
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })
})

describe('AuditExportMenu', () => {
  it('is not rendered without audit_logs:export (audit_logs:read is not enough)', () => {
    signIn(['audit_logs:read'])
    render(<AuditExportMenu filters={{}} />)
    expect(screen.queryByRole('button', { name: /export/i })).toBeNull()
  })

  it('exports the current filters as CSV through downloadTo', async () => {
    signIn(['audit_logs:read', 'audit_logs:export'])
    render(<AuditExportMenu filters={{ event_type: 'admin_action', ip: '10.0.0.0/8' }} />)
    openMenu()
    expect(screen.getByText('Rows matching the current filters')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(screen.getByRole('menuitem', { name: 'CSV' }))
    })
    expect(download).toHaveBeenCalledTimes(1)
    const [endpoint, opts] = download.mock.calls[0]
    const url = new URL(endpoint, 'http://x')
    expect(url.pathname).toBe('/audit-logs/export')
    expect(Object.fromEntries(url.searchParams)).toEqual({ event_type: 'admin_action', ip: '10.0.0.0/8', format: 'csv' })
    expect(opts).toEqual({ fallbackName: 'audit-log.csv' })
  })

  it('exports JSON Lines', async () => {
    signIn(['audit_logs:export'])
    render(<AuditExportMenu filters={{}} />)
    openMenu()
    expect(screen.getByText('All rows')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(screen.getByRole('menuitem', { name: 'JSON Lines' }))
    })
    expect(download.mock.calls[0][0]).toBe('/audit-logs/export?format=jsonl')
  })

  it('shows the server message when the export is too large', async () => {
    signIn(['audit_logs:export'])
    download.mockRejectedValueOnce(
      new ApiError(422, 'More than 100000 rows match; narrow the filters (e.g. the date range)', {
        code: 'export_too_large',
        details: { error: 'export_too_large', max_rows: 100000 },
      })
    )
    render(<AuditExportMenu filters={{}} />)
    openMenu()
    await act(async () => {
      fireEvent.click(screen.getByRole('menuitem', { name: 'CSV' }))
    })
    expect(download).toHaveBeenCalledTimes(1)
    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          variant: 'destructive',
          title: "Couldn't export the audit log",
          description: expect.stringContaining('narrow the filters'),
        })
      )
    )
  })
})
