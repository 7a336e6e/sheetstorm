/**
 * Jest helpers for the incident tab tests (W1-TBL). Test-only: never import
 * from application code.
 *
 * In a test file (next/jest does not hoist jest.mock, so load the tab
 * dynamically after mocking):
 *
 *   import { mockApi, renderTab, setRole, resetTabTest } from './test-utils'
 *   jest.mock('next/navigation', () => require('./test-utils').navigationMock)
 *   let HostsTab: typeof import('./HostsTab').HostsTab
 *   beforeAll(async () => { ({ HostsTab } = await import('./HostsTab')) })
 *
 *   beforeEach(() => resetTabTest())
 *   it('viewer sees no mutations', async () => {
 *     setRole('viewer')
 *     mockApi({ '/incidents/i1/hosts': envelope([host]) })
 *     renderTab(<HostsTab incidentId="i1" />)
 *     ...
 *   })
 */
import { jest } from '@jest/globals'
import { act, cleanup, render } from '@testing-library/react'
import { useSyncExternalStore, type ReactElement } from 'react'
import api from '@/lib/api'
import { clearCache } from '@/lib/query-cache'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'

// ── next/navigation stand-in: a tiny URL store ─────────────────────────
let search = ''
const listeners = new Set<() => void>()

export const mockReplace = jest.fn((url: string) => {
  const i = url.indexOf('?')
  search = i === -1 ? '' : url.slice(i + 1)
  window.history.replaceState(null, '', url)
  listeners.forEach((l) => l())
})

export const navigationMock = {
  useRouter: () => ({ replace: mockReplace, push: mockReplace, back: () => {}, refresh: () => {} }),
  usePathname: () => '/dashboard/incidents/i1',
  useParams: () => ({ id: 'i1' }),
  useSearchParams: () => {
    const s = useSyncExternalStore(
      (cb) => {
        listeners.add(cb)
        return () => listeners.delete(cb)
      },
      () => search
    )
    return new URLSearchParams(s)
  },
}

/** Current URL query (without `?`). */
export function currentSearch(): URLSearchParams {
  return new URLSearchParams(search)
}

export function setSearch(next: string) {
  act(() => {
    search = next.replace(/^\?/, '')
    window.history.replaceState(null, '', `/dashboard/incidents/i1${search ? `?${search}` : ''}`)
    listeners.forEach((l) => l())
  })
}

// ── Roles (system role permission sets, backend `permissions.py`) ──────
const EVIDENCE_GROUPS = ['timeline', 'hosts', 'accounts', 'network_iocs', 'host_iocs', 'malware']
const crud = (actions: string[]) => EVIDENCE_GROUPS.flatMap((g) => actions.map((a) => `${g}:${a}`))

export const ROLE_PERMISSIONS = {
  viewer: [
    'incidents:read',
    'incidents:read_tlp_white',
    ...crud(['read']),
    'tasks:read',
    'attack_graph:read',
    'decisions:read',
    'response_actions:read',
    'improvements:read',
  ],
  responder: [
    'incidents:read',
    'incidents:read_team',
    'incidents:update',
    ...crud(['create', 'read', 'update', 'delete']),
    'tasks:create',
    'tasks:read',
    'tasks:update',
    'tasks:delete',
    'attack_graph:create',
    'attack_graph:read',
    'attack_graph:update',
    'attack_graph:delete',
    'artifacts:read',
    'reports:generate',
    'compromised_accounts:reveal',
    'case_notes:delete',
  ],
} as const

export function setPermissions(permissions: readonly string[]) {
  act(() => {
    useAuthStore.setState({
      user: { id: 'u1', email: 'u@example.test', name: 'U', roles: [], permissions: [...permissions] },
    } as never)
  })
}

export function setRole(role: keyof typeof ROLE_PERMISSIONS) {
  setPermissions(ROLE_PERMISSIONS[role])
}

// ── API ────────────────────────────────────────────────────────────────
export function envelope<T>(items: T[], extra: Record<string, unknown> = {}) {
  return { items, total: items.length, page: 1, per_page: 50, pages: items.length ? 1 : 0, ...extra }
}

type Responder = unknown | ((endpoint: string) => unknown)

/**
 * Stub `api.get` by endpoint path (query string ignored; longest matching
 * path wins). Unmatched GETs resolve to an empty envelope. Returns the spies
 * for get/post/put/patch/delete so tests can assert mutations.
 */
export function mockApi(routes: Record<string, Responder> = {}) {
  const paths = Object.keys(routes).sort((a, b) => b.length - a.length)
  const get = jest.spyOn(api, 'get').mockImplementation((async (endpoint: string) => {
    const path = endpoint.split('?')[0]
    const hit = paths.find((p) => path === p)
    if (hit === undefined) return envelope([])
    const r = routes[hit]
    return typeof r === 'function' ? (r as (e: string) => unknown)(endpoint) : r
  }) as unknown as typeof api.get)
  const ok = (async () => ({})) as never
  return {
    get,
    post: jest.spyOn(api, 'post').mockImplementation(ok),
    put: jest.spyOn(api, 'put').mockImplementation(ok),
    patch: jest.spyOn(api, 'patch').mockImplementation(ok),
    delete: jest.spyOn(api, 'delete').mockImplementation(ok),
  }
}

/** Endpoints `api.get` was called with (full strings, query included). */
export function getCalls(spy: { mock: { calls: unknown[][] } }): string[] {
  return spy.mock.calls.map((c) => String(c[0]))
}

export function renderTab(ui: ReactElement) {
  return render(<ConfirmDialogProvider>{ui}</ConfirmDialogProvider>)
}

/** Call from beforeEach/afterEach: clears DOM, URL, cache, auth and spies. */
export function resetTabTest() {
  cleanup()
  clearCache()
  search = ''
  window.history.replaceState(null, '', '/dashboard/incidents/i1')
  mockReplace.mockClear()
  jest.restoreAllMocks()
  act(() => {
    useAuthStore.setState({ user: null } as never)
  })
}
