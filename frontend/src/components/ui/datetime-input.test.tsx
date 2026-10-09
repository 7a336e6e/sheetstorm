import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { DateTimeInput } from './datetime-input'
import { Timestamp } from './timestamp'
import { TimeModeToggle } from './time-mode-toggle'
import { useAuthStore, useTimePrefStore } from '@/lib/store'
import api from '@/lib/api'
import { formatOffset, formatTs, toInputValue } from '@/lib/time'

// The real API client is used with `patch` stubbed, so nothing hits the network.
type PatchFn = typeof api.patch
let patchSpy: jest.Spied<PatchFn>

function input(): HTMLInputElement {
  return document.querySelector('input[type="datetime-local"]') as HTMLInputElement
}

// jsdom normalizes datetime-local values to `…:ss.000`; browsers drop it.
const shown = () => input().value.replace(/\.000$/, '')

/** A form-like parent holding ISO in state, like the incident tabs do. */
function Harness({ initial, mode, spy }: { initial: string; mode?: 'utc' | 'local'; spy?: (v: string | null) => void }) {
  const [value, setValue] = useState(initial)
  return (
    <>
      <DateTimeInput
        value={value}
        mode={mode}
        onChange={(iso) => {
          spy?.(iso)
          setValue(iso ?? '')
        }}
      />
      <output data-testid="state">{value}</output>
    </>
  )
}

beforeEach(() => {
  patchSpy = jest.spyOn(api, 'patch').mockImplementation((async () => ({ preferences: {} })) as PatchFn)
  act(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false })
    useTimePrefStore.setState({ mode: 'utc' })
  })
})

afterEach(() => {
  patchSpy.mockRestore()
})

describe('DateTimeInput', () => {
  it('pre-fills an API timestamp with an offset instead of rendering blank', () => {
    render(<Harness initial="2026-03-01T08:15:07.123456+00:00" mode="utc" />)
    expect(shown()).toBe('2026-03-01T08:15:07')
  })

  it('pre-fills in local mode with local digits', () => {
    const iso = '2026-03-01T08:15:07+00:00'
    render(<Harness initial={iso} mode="local" />)
    expect(shown()).toBe(toInputValue(iso, 'local'))
  })

  it('emits a UTC ISO string in utc mode', () => {
    const spy = jest.fn()
    render(<Harness initial="" mode="utc" spy={spy} />)
    fireEvent.change(input(), { target: { value: '2026-10-08T14:03:22' } })
    expect(spy).toHaveBeenLastCalledWith('2026-10-08T14:03:22.000Z')
    expect(screen.getByTestId('state').textContent).toBe('2026-10-08T14:03:22.000Z')
  })

  it('emits the local wall-clock time converted to UTC in local mode', () => {
    const spy = jest.fn()
    render(<Harness initial="" mode="local" spy={spy} />)
    fireEvent.change(input(), { target: { value: '2026-10-08T14:03:22' } })
    expect(spy).toHaveBeenLastCalledWith(new Date(2026, 9, 8, 14, 3, 22).toISOString())
  })

  it('emits null when cleared, and keeps the untouched value on save (no silent clearing)', () => {
    const spy = jest.fn()
    render(<Harness initial="2026-03-01T08:15:07+00:00" mode="utc" spy={spy} />)
    // Untouched: state still holds the original ISO (what gets sent on save).
    expect(screen.getByTestId('state').textContent).toBe('2026-03-01T08:15:07+00:00')
    fireEvent.change(input(), { target: { value: '' } })
    expect(spy).toHaveBeenLastCalledWith(null)
  })

  it('re-renders the same instant when the mode changes', () => {
    const iso = '2026-10-08T14:03:22.000Z'
    const { rerender } = render(<DateTimeInput value={iso} mode="utc" onChange={() => {}} />)
    expect(shown()).toBe('2026-10-08T14:03:22')
    rerender(<DateTimeInput value={iso} mode="local" onChange={() => {}} />)
    expect(shown()).toBe(toInputValue(iso, 'local'))
  })

  it('follows the UTC/Local preference when no mode prop is given', () => {
    const iso = '2026-10-08T14:03:22.000Z'
    render(<DateTimeInput value={iso} onChange={() => {}} />)
    expect(shown()).toBe('2026-10-08T14:03:22')
    act(() => useTimePrefStore.setState({ mode: 'local' }))
    expect(shown()).toBe(toInputValue(iso, 'local'))
  })

  it('shows which zone the digits are in', () => {
    const iso = '2026-10-08T14:03:22.000Z'
    const { rerender } = render(<DateTimeInput value={iso} mode="utc" onChange={() => {}} />)
    expect(screen.getByText('UTC')).toBeTruthy()
    rerender(<DateTimeInput value={iso} mode="local" onChange={() => {}} />)
    expect(screen.getByText(`Local (${formatOffset(new Date(iso))})`)).toBeTruthy()
    expect(input().getAttribute('aria-describedby')).toBeTruthy()
  })

  it('updates when a different record is loaded into the form', () => {
    const { rerender } = render(<DateTimeInput value="2026-01-01T00:00:01Z" mode="utc" onChange={() => {}} />)
    rerender(<DateTimeInput value="2026-02-02T02:02:02+00:00" mode="utc" onChange={() => {}} />)
    expect(shown()).toBe('2026-02-02T02:02:02')
  })
})

describe('Timestamp', () => {
  it('renders the preferred mode with the other mode in the tooltip', () => {
    const iso = '2026-10-08T14:03:22+00:00'
    render(<Timestamp value={iso} />)
    const el = screen.getByText('2026-10-08 14:03:22Z')
    expect(el.tagName).toBe('TIME')
    expect(el.getAttribute('dateTime')).toBe('2026-10-08T14:03:22.000Z')
    expect(el.getAttribute('title')).toBe(formatTs(iso, 'local'))
  })

  it('renders the fallback for empty values', () => {
    render(<Timestamp value={null} fallback="-" />)
    expect(screen.getByText('-')).toBeTruthy()
  })
})

describe('TimeModeToggle + preference store', () => {
  it('switches the mode and marks the active segment', () => {
    render(<TimeModeToggle />)
    const utc = screen.getByRole('button', { name: 'UTC' })
    const local = screen.getByRole('button', { name: 'Local' })
    expect(utc.getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(local)
    expect(useTimePrefStore.getState().mode).toBe('local')
    expect(local.getAttribute('aria-pressed')).toBe('true')
    // Logged out: nothing is sent to the server.
    expect(patchSpy).not.toHaveBeenCalled()
  })

  it('persists the choice server-side when logged in', () => {
    act(() => {
      useAuthStore.setState({
        isAuthenticated: true,
        user: { id: 'u1', email: 'a@b.c', name: 'A', roles: [], preferences: { display_timezone: 'utc' } },
      })
    })
    render(<TimeModeToggle />)
    fireEvent.click(screen.getByRole('button', { name: 'Local' }))
    expect(patchSpy).toHaveBeenCalledWith('/auth/me/preferences', { display_timezone: 'local' })
    expect(useAuthStore.getState().user?.preferences?.display_timezone).toBe('local')
  })

  it('rolls back when the server rejects the change', async () => {
    patchSpy.mockImplementationOnce((async () => { throw new Error('nope') }) as PatchFn)
    act(() => {
      useAuthStore.setState({
        isAuthenticated: true,
        user: { id: 'u1', email: 'a@b.c', name: 'A', roles: [], preferences: { display_timezone: 'utc' } },
      })
    })
    await act(async () => {
      useTimePrefStore.getState().setMode('local')
    })
    expect(useTimePrefStore.getState().mode).toBe('utc')
  })

  it('hydrates from the server preference in /auth/me', () => {
    act(() => {
      useAuthStore.setState({
        isAuthenticated: true,
        user: { id: 'u1', email: 'a@b.c', name: 'A', roles: [], preferences: { display_timezone: 'local' } },
      })
    })
    expect(useTimePrefStore.getState().mode).toBe('local')
  })
})
