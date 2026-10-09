import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConflictProvider, ConflictDismissedError, collectionOf, currentVersionOf } from './conflict-provider'
import { conflictFields, formatConflictValue } from '@/components/incidents/ConflictDialog'
import api, { ApiError, isAbortError } from '@/lib/api'
import { notifyError } from '@/lib/errors'
import { clearCache, getCached, setCached } from '@/lib/query-cache'
import { useIncidentStore } from '@/lib/store'

const INC = '11111111-1111-4111-8111-111111111111'
const HOST = '22222222-2222-4222-8222-222222222222'
const HOST_URL = `/incidents/${INC}/hosts/${HOST}`
const LIST_KEY = `/incidents/${INC}/hosts?page=1&per_page=50`

type FetchCall = [string, RequestInit | undefined]
type FakeResponse = { ok: boolean; status: number; json: () => Promise<unknown> }
let fetchMock: jest.Mock<(url: string, init?: RequestInit) => Promise<FakeResponse>>

function respond(status: number, body: unknown): FakeResponse {
  return { ok: status >= 200 && status < 300, status, json: async () => body }
}

const CONFLICT = {
  error: 'conflict',
  message: 'Changed by someone else',
  current: { id: HOST, hostname: 'THEIRS-01', ip_address: '10.0.0.5', version: 4 },
  current_version: 4,
}

function ifMatchOf(call: FetchCall | undefined): string | null {
  return new Headers(call?.[1]?.headers).get('If-Match')
}

beforeEach(() => {
  clearCache()
  fetchMock = jest.fn()
  globalThis.fetch = fetchMock as unknown as typeof fetch
})

afterEach(() => {
  cleanup()
  jest.restoreAllMocks()
  act(() => useIncidentStore.setState({ currentIncident: null }))
})

function mount() {
  return render(
    <ConflictProvider>
      <div>page</div>
    </ConflictProvider>
  )
}

describe('ConflictProvider', () => {
  it('opens the dialog on a versioned 409 and overwrites with the current version', async () => {
    fetchMock
      .mockResolvedValueOnce(respond(409, CONFLICT))
      .mockResolvedValueOnce(respond(200, { id: HOST, hostname: 'MINE-01', version: 5 }))
    mount()

    let result: unknown
    let pending!: Promise<unknown>
    act(() => {
      pending = api.put(HOST_URL, { hostname: 'MINE-01', ip_address: '10.0.0.5' }, { ifMatch: 3 }).then((r) => (result = r))
    })

    expect(await screen.findByRole('dialog')).toBeTruthy()
    expect(screen.getByText('Changed by someone else')).toBeTruthy()
    // Only the differing field is listed.
    const table = screen.getByRole('table', { name: 'Conflicting fields' })
    expect(table.textContent).toContain('Hostname')
    expect(table.textContent).toContain('MINE-01')
    expect(table.textContent).toContain('THEIRS-01')
    expect(table.textContent).not.toContain('Ip address')

    fireEvent.click(screen.getByRole('button', { name: 'Overwrite with mine' }))
    await act(async () => {
      await pending
    })
    expect(result).toEqual({ id: HOST, hostname: 'MINE-01', version: 5 })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const calls = fetchMock.mock.calls as FetchCall[]
    expect(ifMatchOf(calls[0])).toBe('"3"')
    expect(ifMatchOf(calls[1])).toBe('"4"')
    expect(calls[1][1]?.method).toBe('PUT')
    expect(calls[1][1]?.body).toBe(JSON.stringify({ hostname: 'MINE-01', ip_address: '10.0.0.5' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('"Reload theirs" shows the server copy and rejects quietly', async () => {
    fetchMock.mockResolvedValueOnce(respond(409, CONFLICT))
    setCached(LIST_KEY, {
      items: [{ id: HOST, hostname: 'OLD-01', version: 3 }],
      total: 1, page: 1, per_page: 50, pages: 1,
    })
    mount()

    let error: unknown
    let pending!: Promise<unknown>
    act(() => {
      pending = api.put(HOST_URL, { hostname: 'MINE-01' }, { ifMatch: 3 }).catch((e) => (error = e))
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Reload theirs' }))
    await act(async () => {
      await pending
    })

    expect(error).toBeInstanceOf(ConflictDismissedError)
    expect(isAbortError(error)).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const list = getCached<{ items: Array<{ hostname: string; version: number }> }>(LIST_KEY)
    expect(list?.data.items[0]).toMatchObject({ hostname: 'THEIRS-01', version: 4 })

    // Abort-type: a caller's notifyError skips it (no second, destructive toast).
    expect(() => notifyError(error, 'update the host')).not.toThrow()
  })

  it('updates the open incident when its own write conflicts', async () => {
    fetchMock.mockResolvedValueOnce(
      respond(409, { error: 'conflict', current: { id: INC, title: 'Theirs', version: 8 }, current_version: 8 })
    )
    act(() => useIncidentStore.setState({ currentIncident: { id: INC, title: 'Mine', version: 7 } as never }))
    mount()
    let pending!: Promise<unknown>
    act(() => {
      pending = api.put(`/incidents/${INC}`, { title: 'Mine' }, { ifMatch: 7 }).catch(() => undefined)
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Reload theirs' }))
    await act(async () => {
      await pending
    })
    expect(useIncidentStore.getState().currentIncident).toMatchObject({ title: 'Theirs', version: 8 })
  })

  it('offers "Delete anyway" for a conflicting delete', async () => {
    fetchMock.mockResolvedValueOnce(respond(409, CONFLICT)).mockResolvedValueOnce(respond(204, {}))
    mount()
    let pending!: Promise<unknown>
    act(() => {
      pending = api.delete(HOST_URL, undefined, { ifMatch: 3 })
    })
    expect(await screen.findByText(/Keep the latest version, or delete it anyway/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Delete anyway' }))
    await act(async () => {
      await pending
    })
    const calls = fetchMock.mock.calls as FetchCall[]
    expect(calls[1][1]?.method).toBe('DELETE')
    expect(ifMatchOf(calls[1])).toBe('"4"')
  })

  it('queues concurrent conflicts and shows them one at a time', async () => {
    fetchMock.mockResolvedValue(respond(409, CONFLICT))
    mount()
    const errors: unknown[] = []
    let a!: Promise<unknown>
    let b!: Promise<unknown>
    act(() => {
      a = api.put(HOST_URL, { hostname: 'A' }, { ifMatch: 1 }).catch((e) => errors.push(e))
      b = api.put(HOST_URL, { hostname: 'B' }, { ifMatch: 1 }).catch((e) => errors.push(e))
    })
    await screen.findByRole('dialog')
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Reload theirs' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Reload theirs' }))
    await act(async () => {
      await Promise.all([a, b])
    })
    expect(errors).toHaveLength(2)
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('leaves unversioned writes and unmounted apps alone', async () => {
    fetchMock.mockResolvedValue(respond(409, CONFLICT))
    const { unmount } = mount()
    // No ifMatch: plain rejection, no dialog.
    await expect(api.put(HOST_URL, { hostname: 'x' })).rejects.toBeInstanceOf(ApiError)
    expect(screen.queryByRole('dialog')).toBeNull()
    unmount()
    // No provider: the 409 rejects as before.
    await expect(api.put(HOST_URL, { hostname: 'x' }, { ifMatch: 1 })).rejects.toMatchObject({ status: 409, code: 'conflict' })
  })
})

describe('conflict helpers', () => {
  it('lists only the differing fields of my body', () => {
    expect(
      conflictFields(
        { hostname: 'a', notes: '', version: 3, tags: ['x'] },
        { hostname: 'b', notes: null, version: 4, tags: ['x'] }
      )
    ).toEqual([{ field: 'hostname', mine: 'a', theirs: 'b' }])
    expect(conflictFields(undefined, {})).toEqual([])
  })

  it('formats values safely', () => {
    expect(formatConflictValue(null)).toBe('—')
    expect(formatConflictValue({ a: 1 })).toBe('{"a":1}')
    expect(formatConflictValue('x'.repeat(300))).toHaveLength(201)
  })

  it('finds the collection and version', () => {
    expect(collectionOf(HOST_URL)).toEqual({ collection: `/incidents/${INC}/hosts`, id: HOST })
    expect(collectionOf(`/incidents/${INC}/status`)).toEqual({ collection: '/incidents', id: INC })
    expect(collectionOf('/settings')).toBeNull()
    expect(currentVersionOf(new ApiError(409, 'c', { code: 'conflict', details: { current: { version: 6 } } }))).toBe(6)
  })
})
