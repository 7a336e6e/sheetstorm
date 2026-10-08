/**
 * @jest-environment node
 */
import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals'
import {
  ApiError,
  api,
  buildQuery,
  filenameFromDisposition,
  setRestrictionHandler,
  withQuery,
} from './api'
import { getCached, setCached } from './query-cache'

type FetchMock = jest.Mock<(input: string, init?: RequestInit) => Promise<Response>>

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

let fetchMock: FetchMock

beforeEach(() => {
  fetchMock = jest.fn() as FetchMock
  globalThis.fetch = fetchMock as unknown as typeof fetch
})

afterEach(() => {
  setRestrictionHandler(null)
})

describe('buildQuery / withQuery', () => {
  it('skips empty values and prefixes ?', () => {
    expect(buildQuery({ page: 2, q: 'a b', sort: undefined, x: null, y: '', on: false })).toBe(
      '?page=2&q=a+b&on=false'
    )
    expect(buildQuery({ a: undefined })).toBe('')
  })

  it('appends to an endpoint that already has a query', () => {
    expect(withQuery('/x?a=1', { b: 2 })).toBe('/x?a=1&b=2')
    expect(withQuery('/x', { b: 2 })).toBe('/x?b=2')
    expect(withQuery('/x', {})).toBe('/x')
  })
})

describe('ApiError', () => {
  it('carries status, code, full body and the legacy error getter', async () => {
    fetchMock.mockResolvedValue(
      json(409, { error: 'conflict', message: 'Changed', current: { id: 1 }, current_version: 3 })
    )
    const err = (await api.put('/things/1', { a: 1 }).catch((e) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(409)
    expect(err.code).toBe('conflict')
    expect(err.error).toBe('conflict')
    expect(err.message).toBe('Changed')
    expect(err.details?.current_version).toBe(3)
  })

  it('falls back to the error field as message and flags mfa_required', async () => {
    fetchMock.mockResolvedValue(json(403, { error: 'mfa_required', mfa_required: true }))
    const err = (await api.post('/auth/login', {}).catch((e) => e)) as ApiError
    expect(err.message).toBe('mfa_required')
    expect(err.mfa_required).toBe(true)
  })

  it('maps network failures to status 0 network_error after retries', async () => {
    jest.useFakeTimers()
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const p = api.get('/x').catch((e) => e)
    await jest.runAllTimersAsync()
    const err = (await p) as ApiError
    jest.useRealTimers()
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(0)
    expect(err.code).toBe('network_error')
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('rethrows aborts untouched and does not retry', async () => {
    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' })
    fetchMock.mockRejectedValue(abort)
    const err = await api.get('/x', { signal: new AbortController().signal }).catch((e) => e)
    expect(err).toBe(abort)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('wraps upload failures in ApiError', async () => {
    fetchMock.mockResolvedValue(json(413, { error: 'too_large', message: 'File too large' }))
    const err = (await api.uploadFile('/up', new FormData()).catch((e) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(413)
    expect(err.message).toBe('File too large')
  })
})

describe('request options', () => {
  it('passes the abort signal to fetch', async () => {
    fetchMock.mockResolvedValue(json(200, { ok: 1 }))
    const ctrl = new AbortController()
    await api.get('/x', { signal: ctrl.signal })
    expect(fetchMock.mock.calls[0][1]?.signal).toBe(ctrl.signal)
  })

  it('sends If-Match for ifMatch on put/patch/delete', async () => {
    fetchMock.mockImplementation(async () => json(200, {}))
    await api.put('/a', { x: 1 }, { ifMatch: 7 })
    await api.patch('/a', { x: 1 }, { ifMatch: 8 })
    await api.delete('/a', undefined, { ifMatch: 9 })
    await api.put('/a', { x: 1 })
    const header = (i: number) => new Headers(fetchMock.mock.calls[i][1]?.headers).get('If-Match')
    expect(header(0)).toBe('"7"')
    expect(header(1)).toBe('"8"')
    expect(header(2)).toBe('"9"')
    expect(header(3)).toBeNull()
    expect(fetchMock.mock.calls[2][1]?.method).toBe('DELETE')
  })
})

describe('restriction handler', () => {
  it('is told about account restriction codes and the request still rejects', async () => {
    const handler = jest.fn()
    setRestrictionHandler(handler)
    fetchMock.mockResolvedValue(json(403, { error: 'password_change_required' }))
    const err = (await api.get('/incidents').catch((e) => e)) as ApiError
    expect(handler).toHaveBeenCalledWith('password_change_required')
    expect(err.status).toBe(403)
  })

  it('ignores other 403s', async () => {
    const handler = jest.fn()
    setRestrictionHandler(handler)
    fetchMock.mockResolvedValue(json(403, { error: 'insufficient_privilege' }))
    await api.get('/incidents').catch(() => undefined)
    expect(handler).not.toHaveBeenCalled()
  })
})

describe('session changes', () => {
  it('clears the query cache on login/logout', async () => {
    setCached('/incidents?page=1', { items: [] })
    fetchMock.mockImplementation(async () => json(200, {}))
    await api.post('/auth/logout')
    expect(getCached('/incidents?page=1')).toBeUndefined()
  })
})

describe('filenameFromDisposition', () => {
  it('reads plain, quoted and RFC 5987 names', () => {
    expect(filenameFromDisposition('attachment; filename=report.pdf')).toBe('report.pdf')
    expect(filenameFromDisposition('attachment; filename="hosts export.csv"')).toBe('hosts export.csv')
    expect(filenameFromDisposition("attachment; filename*=UTF-8''r%C3%A9sum%C3%A9.txt")).toBe('résumé.txt')
  })

  it('strips paths and rejects empty names', () => {
    expect(filenameFromDisposition('attachment; filename="../../etc/passwd"')).toBe('passwd')
    expect(filenameFromDisposition('attachment; filename=".."')).toBeNull()
    expect(filenameFromDisposition(null)).toBeNull()
    expect(filenameFromDisposition('inline')).toBeNull()
  })
})

describe('downloadTo', () => {
  it('saves the blob under the server filename, else the fallback', async () => {
    const clicks: string[] = []
    const anchor = {
      href: '',
      download: '',
      rel: '',
      click: () => clicks.push(anchor.download),
      remove: () => undefined,
    }
    const g = globalThis as unknown as { document?: unknown }
    const prevDoc = g.document
    g.document = {
      cookie: '',
      createElement: () => anchor,
      body: { appendChild: () => undefined },
    }
    const createUrl = jest.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x')
    const revokeUrl = jest.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    try {
      fetchMock.mockResolvedValueOnce(
        new Response('a,b', { status: 200, headers: { 'Content-Disposition': 'attachment; filename="hosts.csv"' } })
      )
      expect(await api.downloadTo('/export', { fallbackName: 'export.csv' })).toBe('hosts.csv')

      fetchMock.mockResolvedValueOnce(new Response('%PDF', { status: 200 }))
      expect(
        await api.downloadTo('/report', { fallbackName: 'report.pdf', method: 'POST', data: { a: 1 } })
      ).toBe('report.pdf')
      expect(fetchMock.mock.calls[1][1]?.method).toBe('POST')
      expect(fetchMock.mock.calls[1][1]?.body).toBe('{"a":1}')
      expect(clicks).toEqual(['hosts.csv', 'report.pdf'])

      fetchMock.mockResolvedValueOnce(json(403, { error: 'forbidden', message: 'No' }))
      const err = (await api.downloadTo('/export', { fallbackName: 'x' }).catch((e) => e)) as ApiError
      expect(err.status).toBe(403)
    } finally {
      g.document = prevDoc
      createUrl.mockRestore()
      revokeUrl.mockRestore()
    }
  })
})
