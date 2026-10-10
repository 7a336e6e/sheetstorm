import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import api from '@/lib/api'
import { useAuthStore } from '@/lib/store'

const pathname = '/dashboard'
jest.mock('next/navigation', () => ({ usePathname: () => pathname }))

let TourProvider: typeof import('./TourProvider').TourProvider
let useTourStore: typeof import('./TourProvider').useTourStore

beforeEach(async () => {
  jest.useFakeTimers()
  ;({ TourProvider, useTourStore } = await import('./TourProvider'))
  document.body.innerHTML = ''
})
afterEach(() => {
  cleanup()
  act(() => useTourStore.getState().stop())
  jest.useRealTimers()
  jest.restoreAllMocks()
})

const setUser = (extra: Record<string, unknown> = {}) =>
  act(() => {
    useAuthStore.setState({ user: { id: 'u1', email: 'u@x.test', name: 'U', roles: [], permissions: [], ...extra } } as never)
  })

describe('TourProvider', () => {
  it('starts the page tour once, and remembers it when skipped', () => {
    const patch = jest.spyOn(api, 'patch').mockResolvedValue({} as never)
    setUser()
    render(<TourProvider />)
    act(() => jest.advanceTimersByTime(1000))
    expect(screen.getByRole('dialog').textContent).toContain('Welcome to SheetStorm')
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(patch).toHaveBeenCalledWith('/auth/me/preferences', { tours_seen: ['dashboard'] })
    expect(useAuthStore.getState().user?.preferences?.tours_seen).toEqual(['dashboard'])
  })

  it('does not start when an admin switched tours off or the tour was seen', () => {
    setUser({ tours_enabled: false })
    const { unmount } = render(<TourProvider />)
    act(() => jest.advanceTimersByTime(1000))
    expect(screen.queryByRole('dialog')).toBeNull()
    unmount()
    setUser({ preferences: { tours_seen: ['dashboard'] } })
    render(<TourProvider />)
    act(() => jest.advanceTimersByTime(1000))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('never auto-starts in an automated browser (navigator.webdriver)', () => {
    Object.defineProperty(window.navigator, 'webdriver', { value: true, configurable: true })
    try {
      setUser()
      render(<TourProvider />)
      act(() => jest.advanceTimersByTime(1000))
      expect(screen.queryByRole('dialog')).toBeNull()
    } finally {
      delete (window.navigator as { webdriver?: boolean }).webdriver
    }
  })

  it('walks through the steps with Next and Back', () => {
    jest.spyOn(api, 'patch').mockResolvedValue({} as never)
    document.body.innerHTML = '<div data-tour="search"></div>'
    setUser()
    render(<TourProvider />)
    act(() => jest.advanceTimersByTime(1000))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByRole('dialog').textContent).toContain('Search everything')
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByRole('dialog').textContent).toContain('Welcome to SheetStorm')
  })
})
