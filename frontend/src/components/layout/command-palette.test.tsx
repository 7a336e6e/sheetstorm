import { afterEach, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals'
// Types jest-dom matchers on the @jest/globals `expect`.
import '@testing-library/jest-dom/jest-globals'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import api from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { RECENT_SEARCHES_KEY } from '@/lib/global-search'
import type { SearchResponse } from '@/types'

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn() }),
  usePathname: () => '/dashboard',
  useSearchParams: () => new URLSearchParams(),
}))

// Imported after the mock is registered (SWC does not hoist jest.mock above
// static imports when `jest` comes from @jest/globals).
type Palette = typeof import('./command-palette')
let CommandPalette: Palette['CommandPalette']
let filterNavCommands: Palette['filterNavCommands']
let NAV_COMMANDS: Palette['NAV_COMMANDS']
let PALETTE_DEBOUNCE_MS: Palette['PALETTE_DEBOUNCE_MS']
let useCommandPalette: Palette['useCommandPalette']
let useShortcutsHelp: typeof import('./shortcuts-help')['useShortcutsHelp']

beforeAll(async () => {
  ;({ CommandPalette, filterNavCommands, NAV_COMMANDS, PALETTE_DEBOUNCE_MS, useCommandPalette } = await import(
    './command-palette'
  ))
  ;({ useShortcutsHelp } = await import('./shortcuts-help'))
})

type GetFn = (endpoint: string, opts?: { signal?: AbortSignal }) => Promise<unknown>
let getSpy: jest.Mock<GetFn>

const searchResponse: SearchResponse = {
  results: [
    {
      type: 'host',
      id: 'h1',
      incident_id: 'i1',
      incident_title: 'Ransomware at HQ',
      title: 'WS-0042 (10.0.0.42)',
      snippet: 'beacon to 10.0.0.42',
      timestamp: '2026-10-01T10:00:00Z',
      link: { incident_id: 'i1', tab: 'hosts', row: 'h1' },
    },
    {
      type: 'incident',
      id: 'i1',
      incident_id: 'i1',
      incident_title: 'Ransomware at HQ',
      title: 'Ransomware at HQ',
      snippet: '10.0.0.42 encrypted',
      timestamp: '2026-10-01T09:00:00Z',
      link: { incident_id: 'i1', tab: 'overview', row: null },
    },
  ],
  total: 7,
  page: 1,
  per_page: 20,
  pages: 1,
  facets: { host: 6, incident: 1 },
}

function setPermissions(permissions: string[]) {
  act(() => {
    useAuthStore.setState({ user: { id: 'u', email: 'u@x', name: 'U', roles: [], permissions } })
  })
}

function pressMod(key: string) {
  fireEvent.keyDown(document.body, { key, ctrlKey: true })
}

function input() {
  return screen.getByRole('combobox', { name: 'Search or jump to' })
}

function activeOption(): HTMLElement | null {
  const id = input().getAttribute('aria-activedescendant')
  return id ? document.getElementById(id) : null
}

beforeEach(() => {
  sessionStorage.clear()
  mockPush.mockClear()
  act(() => {
    useCommandPalette.setState({ open: false })
    useShortcutsHelp.setState({ open: false })
  })
  setPermissions(['incidents:read'])
  getSpy = jest.fn<GetFn>(async () => searchResponse)
  jest.spyOn(api, 'get').mockImplementation(getSpy as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  jest.useRealTimers()
  act(() => {
    useAuthStore.setState({ user: null })
  })
})

describe('filterNavCommands', () => {
  it('drops commands the user lacks every permission for and matches keywords', () => {
    const can = (perm: string | string[]) => (Array.isArray(perm) ? perm : [perm]).includes('reports:read')
    const ids = filterNavCommands(NAV_COMMANDS, '', can).map((c) => c.id)
    expect(ids).toContain('nav-reports')
    expect(ids).not.toContain('nav-new-incident')
    expect(ids).not.toContain('nav-users')
    expect(filterNavCommands(NAV_COMMANDS, 'audit', () => true).map((c) => c.id)).toEqual(['nav-activity'])
  })
})

describe('CommandPalette keyboard behaviour', () => {
  it('opens on mod+K and closes on a second mod+K and on Escape', () => {
    render(<CommandPalette />)
    expect(screen.queryByRole('combobox')).toBeNull()

    pressMod('k')
    expect(input()).toBeInTheDocument()
    expect(input()).toHaveFocus()

    pressMod('k')
    expect(screen.queryByRole('combobox')).toBeNull()

    pressMod('k')
    fireEvent.keyDown(input(), { key: 'Escape' })
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('moves the active option with arrows (wrapping) and runs it on Enter', () => {
    render(<CommandPalette />)
    pressMod('k')

    const options = screen.getAllByRole('option')
    expect(options[0]).toHaveTextContent('Dashboard')
    expect(activeOption()).toBe(options[0])
    expect(options[0]).toHaveAttribute('aria-selected', 'true')

    fireEvent.keyDown(input(), { key: 'ArrowDown' })
    expect(activeOption()).toBe(options[1])
    expect(options[1]).toHaveTextContent('Incidents')

    fireEvent.keyDown(input(), { key: 'ArrowUp' })
    fireEvent.keyDown(input(), { key: 'ArrowUp' })
    expect(activeOption()).toBe(options[options.length - 1])

    fireEvent.keyDown(input(), { key: 'Home' })
    fireEvent.keyDown(input(), { key: 'ArrowDown' })
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(mockPush).toHaveBeenCalledWith('/dashboard/incidents')
    expect(useCommandPalette.getState().open).toBe(false)
  })

  it('hides commands without permission and filters as you type', () => {
    render(<CommandPalette />)
    pressMod('k')
    expect(screen.queryByRole('option', { name: /new incident/i })).toBeNull()
    cleanup()

    setPermissions(['incidents:read', 'incidents:create'])
    render(<CommandPalette />)
    act(() => useCommandPalette.setState({ open: true }))
    fireEvent.change(input(), { target: { value: 'new' } })
    const options = screen.getAllByRole('option')
    expect(options[0]).toHaveTextContent('New incident')
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(mockPush).toHaveBeenCalledWith('/dashboard/incidents/new')
  })

  it('opens the shortcuts help from its command', () => {
    render(<CommandPalette />)
    pressMod('k')
    fireEvent.change(input(), { target: { value: 'shortcuts' } })
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(useShortcutsHelp.getState().open).toBe(true)
    expect(useCommandPalette.getState().open).toBe(false)
  })

  it('searches records from 3 characters (debounced) and deep-links the active hit', async () => {
    jest.useFakeTimers()
    render(<CommandPalette />)
    pressMod('k')

    fireEvent.change(input(), { target: { value: '10' } })
    await act(async () => {
      await jest.advanceTimersByTimeAsync(PALETTE_DEBOUNCE_MS)
    })
    expect(getSpy).not.toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent(/at least 3 characters/i)

    fireEvent.change(input(), { target: { value: '10.0' } })
    fireEvent.change(input(), { target: { value: '10.0.0.42' } })
    await act(async () => {
      await jest.advanceTimersByTimeAsync(PALETTE_DEBOUNCE_MS)
    })
    expect(getSpy).toHaveBeenCalledTimes(1)
    const [endpoint, opts] = getSpy.mock.calls[0]
    const params = new URLSearchParams(endpoint.split('?')[1])
    expect(endpoint.startsWith('/search?')).toBe(true)
    expect(params.get('q')).toBe('10.0.0.42')
    expect(params.get('per_page')).toBe('20')
    expect(params.get('sort')).toBe('relevance')
    expect(opts?.signal).toBeDefined()

    const hosts = screen.getByRole('group', { name: 'Hosts (6)' })
    expect(within(hosts).getByRole('option')).toHaveTextContent('WS-0042 (10.0.0.42)')
    // The matched text is highlighted as a <mark>, never injected as HTML.
    expect(within(hosts).getAllByText('10.0.0.42')[0].tagName).toBe('MARK')
    expect(screen.getByRole('option', { name: /see all 7 results/i })).toBeInTheDocument()

    // No nav command matches the IP, so the first option is the first hit.
    expect(activeOption()).toHaveTextContent('Ransomware at HQ')
    fireEvent.keyDown(input(), { key: 'ArrowDown' })
    expect(activeOption()).toHaveTextContent('WS-0042')
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(mockPush).toHaveBeenCalledWith('/dashboard/incidents/i1?tab=hosts&row=h1')
    expect(JSON.parse(sessionStorage.getItem(RECENT_SEARCHES_KEY) ?? '[]')).toEqual(['10.0.0.42'])
  })

  it('aborts a stale search when the query changes', async () => {
    jest.useFakeTimers()
    const signals: AbortSignal[] = []
    getSpy.mockImplementation((_endpoint, opts) => {
      if (opts?.signal) signals.push(opts.signal)
      return new Promise(() => undefined)
    })
    render(<CommandPalette />)
    pressMod('k')
    fireEvent.change(input(), { target: { value: 'abc' } })
    await act(async () => {
      await jest.advanceTimersByTimeAsync(PALETTE_DEBOUNCE_MS)
    })
    fireEvent.change(input(), { target: { value: 'abcd' } })
    await act(async () => {
      await jest.advanceTimersByTimeAsync(PALETTE_DEBOUNCE_MS)
    })
    expect(signals).toHaveLength(2)
    expect(signals[0].aborted).toBe(true)
    expect(signals[1].aborted).toBe(false)
  })

  it('offers recent searches when empty and Enter refills the query', () => {
    sessionStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(['mimikatz']))
    render(<CommandPalette />)
    pressMod('k')
    expect(screen.getByRole('group', { name: 'Recent searches' })).toBeInTheDocument()
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(input()).toHaveValue('mimikatz')
  })
})
