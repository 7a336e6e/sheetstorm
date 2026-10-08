import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import api, { ApiError } from '@/lib/api'
import { PICKER_DEBOUNCE_MS, UserPicker } from './entity-picker'
import type { User } from '@/types'

type GetFn = (endpoint: string, opts?: { signal?: AbortSignal }) => Promise<unknown>
let getSpy: jest.Mock<GetFn>

const users: User[] = [
  { id: 'u1', name: 'Alice', email: 'alice@x', roles: [], is_active: true, created_at: '2026-01-01T00:00:00Z' },
  { id: 'u2', name: 'Bob', email: 'bob@x', roles: [], is_active: true, created_at: '2026-01-01T00:00:00Z' },
]

beforeEach(() => {
  getSpy = jest.fn<GetFn>(async (endpoint) => {
    if (endpoint.startsWith('/users/')) return users.find((u) => endpoint.endsWith(u.id))
    const q = new URLSearchParams(endpoint.split('?')[1]).get('q')?.toLowerCase()
    const items = q ? users.filter((u) => u.name.toLowerCase().includes(q)) : users
    return { items, total: items.length, page: 1, per_page: 20, pages: 1 }
  })
  jest.spyOn(api, 'get').mockImplementation(getSpy as unknown as typeof api.get)
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  jest.useRealTimers()
})

describe('UserPicker', () => {
  it('searches the server with the contract params and selects by keyboard', async () => {
    jest.useFakeTimers()
    const onChange = jest.fn()
    render(<UserPicker value={null} onChange={onChange} ariaLabel="Assignee" />)
    const input = screen.getByRole('combobox', { name: 'Assignee' })
    fireEvent.focus(input)
    await act(async () => {
      await jest.advanceTimersByTimeAsync(0)
    })
    const first = new URLSearchParams(getSpy.mock.calls[0][0].split('?')[1])
    expect(getSpy.mock.calls[0][0].startsWith('/users?')).toBe(true)
    expect(first.get('is_active')).toBe('true')
    expect(first.get('sort')).toBe('name')
    expect(first.get('per_page')).toBe('20')
    expect(screen.getAllByRole('option')).toHaveLength(2)

    fireEvent.change(input, { target: { value: 'bo' } })
    await act(async () => {
      await jest.advanceTimersByTimeAsync(PICKER_DEBOUNCE_MS)
    })
    expect(new URLSearchParams(getSpy.mock.calls.at(-1)![0].split('?')[1]).get('q')).toBe('bo')
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual(['Bobbob@x'])

    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith('u2', users[1])
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('aborts stale searches', async () => {
    jest.useFakeTimers()
    const signals: AbortSignal[] = []
    getSpy.mockImplementation((_endpoint, opts) => {
      signals.push(opts!.signal!)
      return new Promise(() => undefined)
    })
    render(<UserPicker value={null} onChange={jest.fn()} ariaLabel="Assignee" />)
    const input = screen.getByRole('combobox', { name: 'Assignee' })
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: 'a' } })
    await act(async () => {
      await jest.advanceTimersByTimeAsync(PICKER_DEBOUNCE_MS)
    })
    expect(signals.length).toBeGreaterThanOrEqual(2)
    expect(signals[0].aborted).toBe(true)
  })

  it('resolves the label of the current value', async () => {
    render(<UserPicker value="u1" onChange={jest.fn()} ariaLabel="Assignee" />)
    await waitFor(() =>
      expect((screen.getByRole('combobox', { name: 'Assignee' }) as HTMLInputElement).value).toBe('Alice')
    )
    expect(getSpy).toHaveBeenCalledWith('/users/u1', expect.anything())
  })

  it('shows server errors inline and can be cleared', async () => {
    getSpy.mockRejectedValue(new ApiError(403, 'no'))
    const onChange = jest.fn()
    render(<UserPicker value="u1" valueLabel="Alice" onChange={onChange} ariaLabel="Assignee" />)
    fireEvent.focus(screen.getByRole('combobox', { name: 'Assignee' }))
    await waitFor(() => expect(screen.getByText("You don't have permission to do that.")).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: 'Clear Assignee' }))
    expect(onChange).toHaveBeenCalledWith(null, null)
  })
})
