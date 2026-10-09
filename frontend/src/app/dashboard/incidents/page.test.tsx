import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
// Types jest-dom matchers on the @jest/globals `expect`.
import '@testing-library/jest-dom/jest-globals'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useSyncExternalStore } from 'react'
import api from '@/lib/api'
import { clearCache } from '@/lib/query-cache'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import type { Incident } from '@/types'

// ── next/navigation stand-in backed by a tiny URL store ───────────────
let mockSearch = ''
const mockListeners = new Set<() => void>()
const mockPush = jest.fn()
const mockReplace = jest.fn((url: string) => {
  const i = url.indexOf('?')
  mockSearch = i === -1 ? '' : url.slice(i + 1)
  window.history.replaceState(null, '', url)
  mockListeners.forEach((l) => l())
})
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  usePathname: () => '/dashboard/incidents',
  useSearchParams: () => {
    const search = useSyncExternalStore(
      (cb) => {
        mockListeners.add(cb)
        return () => mockListeners.delete(cb)
      },
      () => mockSearch
    )
    return new URLSearchParams(search)
  },
}))

let IncidentsPage: typeof import('./page').default
beforeAll(async () => {
  ;({ default: IncidentsPage } = await import('./page'))
})

const incidents: Incident[] = [
  {
    id: 'i1',
    incident_number: 101,
    title: 'Ransomware at HQ',
    severity: 'critical',
    status: 'open',
    phase: 2,
    phase_name: 'Identification',
    tlp: 'amber',
    created_at: '2026-10-01T10:00:00Z',
  },
  {
    id: 'i2',
    incident_number: 102,
    title: 'Phishing wave',
    severity: 'medium',
    status: 'contained',
    phase: 3,
    phase_name: 'Containment',
    tlp: 'green',
    created_at: '2026-10-02T10:00:00Z',
  },
]

type GetFn = (endpoint: string, opts?: { signal?: AbortSignal }) => Promise<unknown>
let getSpy: jest.Mock<GetFn>

function setPermissions(permissions: string[]) {
  act(() => {
    useAuthStore.setState({ user: { id: 'u', email: 'u@x', name: 'U', roles: ['Viewer'], permissions } })
  })
}

function renderPage() {
  return render(
    <ConfirmDialogProvider>
      <IncidentsPage />
    </ConfirmDialogProvider>
  )
}

function lastParams(): URLSearchParams {
  const calls = getSpy.mock.calls.filter(([e]) => e.startsWith('/incidents?'))
  return new URLSearchParams(calls[calls.length - 1][0].split('?')[1])
}

beforeEach(() => {
  clearCache()
  mockSearch = ''
  window.history.replaceState(null, '', '/dashboard/incidents')
  mockPush.mockClear()
  mockReplace.mockClear()
  getSpy = jest.fn<GetFn>(async () => ({ items: incidents, total: 120, page: 1, per_page: 50, pages: 3 }))
  jest.spyOn(api, 'get').mockImplementation(getSpy as unknown as typeof api.get)
})

afterEach(async () => {
  // Let in-flight list requests settle inside act before unmounting.
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0))
  })
  cleanup()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null })
  })
})

describe('Incidents list', () => {
  it('pages on the server and shows an honest total', async () => {
    setPermissions(['incidents:read'])
    renderPage()
    expect(await screen.findByText('Ransomware at HQ')).toBeInTheDocument()
    const p = lastParams()
    expect(p.get('page')).toBe('1')
    expect(p.get('per_page')).toBe('50')
    expect(p.get('sort')).toBe('-created_at')
    expect(screen.getByText('1–50 of 120')).toBeInTheDocument()
  })

  it('reads filters, search and sort from the URL', async () => {
    mockSearch = 'inc.f.status=open&inc.f.severity=critical&inc.q=ransom&inc.sort=-severity&inc.page=2'
    setPermissions(['incidents:read'])
    renderPage()
    await screen.findByText('Ransomware at HQ')
    const p = lastParams()
    expect(p.get('status')).toBe('open')
    expect(p.get('severity')).toBe('critical')
    expect(p.get('q')).toBe('ransom')
    expect(p.get('sort')).toBe('-severity')
    expect(p.get('page')).toBe('2')
  })

  it('writes sort changes to the URL', async () => {
    setPermissions(['incidents:read'])
    renderPage()
    await screen.findByText('Ransomware at HQ')
    fireEvent.click(within(screen.getByRole('columnheader', { name: /severity/i })).getByRole('button'))
    expect(mockReplace).toHaveBeenCalled()
    expect(new URLSearchParams(mockSearch).get('inc.sort')).toBe('severity')
    await waitFor(() => expect(lastParams().get('sort')).toBe('severity'))
    expect(await screen.findByText('Ransomware at HQ')).toBeInTheDocument()
  })

  it('shows no create or archive controls to a read-only user', async () => {
    setPermissions(['incidents:read'])
    renderPage()
    await screen.findByText('Ransomware at HQ')
    expect(screen.queryByRole('button', { name: /new incident/i })).toBeNull()
    expect(screen.queryAllByRole('button', { name: /actions for/i })).toHaveLength(0)
  })

  it('does not treat role names as permissions', async () => {
    act(() => {
      useAuthStore.setState({
        user: { id: 'u', email: 'u@x', name: 'U', roles: ['Administrator', 'Manager'], permissions: ['incidents:read'] },
      })
    })
    renderPage()
    await screen.findByText('Ransomware at HQ')
    expect(screen.queryAllByRole('button', { name: /actions for/i })).toHaveLength(0)
  })

  it('gates create on incidents:create', async () => {
    setPermissions(['incidents:read', 'incidents:create'])
    renderPage()
    await screen.findByText('Ransomware at HQ')
    fireEvent.click(screen.getByRole('button', { name: /new incident/i }))
    expect(mockPush).toHaveBeenCalledWith('/dashboard/incidents/new')
  })

  it('gates archive on incidents:archive, confirms, and refetches the list', async () => {
    setPermissions(['incidents:read', 'incidents:archive'])
    const post = jest.spyOn(api, 'post').mockResolvedValue({} as never)
    renderPage()
    await screen.findByText('Ransomware at HQ')

    const kebabs = screen.getAllByRole('button', { name: /actions for/i })
    expect(kebabs).toHaveLength(2)
    const row = screen.getAllByRole('row').filter((r) => r.getAttribute('tabindex') !== null)[0]
    fireEvent.keyDown(row, { key: '.' })
    fireEvent.click(within(screen.getByRole('menu')).getByRole('menuitem', { name: 'Archive' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('#101')
    const callsBefore = getSpy.mock.calls.length
    fireEvent.click(within(dialog).getByRole('button', { name: 'Archive' }))

    await waitFor(() => expect(post).toHaveBeenCalledWith('/incidents/i1/archive', {}))
    await waitFor(() => expect(getSpy.mock.calls.length).toBeGreaterThan(callsBefore))
  })

  it('opens an incident on row click', async () => {
    setPermissions(['incidents:read'])
    renderPage()
    fireEvent.click(await screen.findByText('#102'))
    expect(mockPush).toHaveBeenCalledWith('/dashboard/incidents/i2')
  })
})
