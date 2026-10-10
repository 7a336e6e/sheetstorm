import { clearCache } from './query-cache'

const API_URL = process.env.NEXT_PUBLIC_API_URL || '/api/v1'

/** Read a non-httpOnly cookie (used for the CSRF double-submit token). */
function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const escaped = name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1')
  const m = document.cookie.match(new RegExp('(?:^|; )' + escaped + '=([^;]*)'))
  return m ? decodeURIComponent(m[1]) : null
}

/**
 * Thrown for every non-OK response (and network failures, status 0).
 *
 * - `code` is the server's machine-readable `error` field.
 * - `details` is the full parsed response body (e.g. a 409 `conflict` body
 *   with `current` / `current_version`).
 * - `error` is a getter for `code` so older `err.error` reads keep working.
 */
export class ApiError extends Error {
  readonly status: number
  readonly code?: string
  readonly details?: Record<string, unknown>
  readonly mfa_required?: boolean

  constructor(
    status: number,
    message: string,
    opts: { code?: string; details?: Record<string, unknown> } = {}
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = opts.code
    this.details = opts.details
    if (opts.details?.mfa_required === true) this.mfa_required = true
  }

  get error(): string | undefined {
    return this.code
  }
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError
}

/** True for a fetch aborted through an AbortSignal. Never retried or toasted. */
export function isAbortError(err: unknown): boolean {
  return (
    typeof err === 'object' &&
    err !== null &&
    (err as { name?: string }).name === 'AbortError'
  )
}

async function errorFromResponse(response: Response, fallback: string): Promise<ApiError> {
  let body: Record<string, unknown> | undefined
  try {
    const parsed: unknown = await response.json()
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      body = parsed as Record<string, unknown>
    }
  } catch {
    // Non-JSON error body (proxy page, empty body).
  }
  const code = typeof body?.error === 'string' ? body.error : undefined
  const message =
    (typeof body?.message === 'string' && body.message) || code || fallback
  return new ApiError(response.status, message, { code, details: body })
}

type QueryValue = string | number | boolean | undefined | null

/**
 * Build a query string from params, skipping undefined / null / ''.
 * Returns '' when nothing is left, otherwise a string starting with '?'.
 */
export function buildQuery(params: Record<string, QueryValue>): string {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    q.append(key, String(value))
  })
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** Append params to an endpoint that may already carry a query string. */
export function withQuery(endpoint: string, params: Record<string, QueryValue>): string {
  const qs = buildQuery(params)
  if (!qs) return endpoint
  return endpoint.includes('?') ? `${endpoint}&${qs.slice(1)}` : `${endpoint}${qs}`
}

/**
 * 403 codes from the account-state gate (backend `middleware/account_state`).
 * A registered restriction handler is told about them (it routes the user to
 * the page that lifts the restriction); the request still rejects.
 */
export const RESTRICTION_CODES = ['password_change_required', 'mfa_enrollment_required'] as const

/**
 * Routes that render without a session. A 401 on these must never trigger a
 * hard redirect to /login (that is what caused the logged-out reload loop).
 */
const PUBLIC_PATH_PREFIXES = ['/auth/', '/login/']
const PUBLIC_PATHS = ['/', '/login', '/register']

export function isPublicPath(pathname: string): boolean {
  return (
    PUBLIC_PATHS.includes(pathname) ||
    PUBLIC_PATH_PREFIXES.some((p) => pathname.startsWith(p))
  )
}

/**
 * Auth endpoints for which a 401 means "bad credentials / no session" rather
 * than "access token expired" — never attempt a silent refresh for these.
 */
const NO_REFRESH_ENDPOINTS = [
  '/auth/login',
  '/auth/register',
  '/auth/refresh',
  '/auth/logout',
  '/auth/supabase',
  '/auth/mfa/complete',
  '/auth/github',
  '/auth/sso',
  '/auth/registration-status',
]

/**
 * Requests that start or end a session. The query cache is cleared before
 * them so one user's cached lists are never shown to the next user.
 */
const SESSION_CHANGING_ENDPOINTS = [
  '/auth/login',
  '/auth/logout',
  '/auth/register',
  '/auth/supabase',
  '/auth/mfa/complete',
]

function endpointPath(endpoint: string): string {
  return endpoint.split('?')[0]
}

function canRefreshFor(endpoint: string): boolean {
  const path = endpointPath(endpoint)
  return !NO_REFRESH_ENDPOINTS.some((p) => path === p || path.startsWith(p + '/'))
}

function isAuthEndpoint(endpoint: string): boolean {
  return endpointPath(endpoint).startsWith('/auth/')
}

/**
 * Filename from a Content-Disposition header (RFC 6266 / 5987), reduced to a
 * safe basename. Returns null if there is none.
 */
export function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null
  let name: string | null = null
  const star = header.match(/filename\*\s*=\s*([^;]+)/i)
  if (star) {
    const raw = star[1].trim().replace(/^"(.*)"$/, '$1')
    const value = raw.replace(/^[\w-]+'[^']*'/, '') // strip charset'lang'
    try {
      name = decodeURIComponent(value)
    } catch {
      name = value
    }
  }
  if (!name) {
    const plain = header.match(/filename\s*=\s*("([^"]*)"|[^;]+)/i)
    if (plain) name = (plain[2] ?? plain[1]).trim()
  }
  if (!name) return null
  const safe = name.replace(/[\x00-\x1f\x7f]/g, '').split(/[\\/]/).pop()?.trim() || ''
  return safe && safe !== '.' && safe !== '..' ? safe : null
}

export interface GetOptions {
  signal?: AbortSignal
}

export interface WriteOptions {
  /** Sends `If-Match: "<version>"` for optimistic concurrency (409 `conflict`). */
  ifMatch?: number
  signal?: AbortSignal
}

/**
 * A versioned write (`ifMatch`) answered 409 `conflict`. A registered
 * conflict handler (ConflictProvider) settles it: resolve with `retry(v)` to
 * overwrite with the server's current version, or reject to give up.
 */
export interface ConflictRequest {
  method: 'PUT' | 'PATCH' | 'DELETE'
  endpoint: string
  /** The body that was sent (undefined for most deletes). */
  data: unknown
  ifMatch: number
  error: ApiError
  /** Re-send the same write with `If-Match: <version>` (or none when undefined). */
  retry: (version: number | undefined) => Promise<unknown>
}

export type ConflictHandler = (conflict: ConflictRequest) => Promise<unknown>

export interface DownloadOptions {
  fallbackName: string
  method?: 'GET' | 'POST'
  data?: unknown
}

/**
 * Browser auth is cookie-only: the access/refresh JWTs live in httpOnly
 * cookies and mutating requests carry the CSRF double-submit header. The SPA
 * never sends an Authorization header — JSON token fields in auth responses
 * exist for non-browser clients (MCP) and are deliberately ignored here.
 */
/** Methods retried on 5xx / network errors (never POST/PATCH/PUT/DELETE). */
const RETRYABLE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

class ApiClient {
  private baseUrl: string
  private refreshPromise: Promise<boolean> | null = null
  private unauthorizedHandler: (() => void) | null = null
  private restrictionHandler: ((code: string) => void) | null = null
  private conflictHandler: ConflictHandler | null = null

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl
    // One-time cleanup of tokens persisted by older builds. A stale token
    // here was previously sent as a Bearer header and overrode the cookie.
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.removeItem('access_token')
        window.localStorage.removeItem('refresh_token')
      } catch {
        // Storage unavailable (private mode / blocked) — nothing to clean.
      }
    }
  }

  /** Called when a session is definitively gone (refresh failed). */
  onUnauthorized(handler: (() => void) | null) {
    this.unauthorizedHandler = handler
  }

  /** Called with the code when a request hits an account restriction (403). */
  setRestrictionHandler(handler: ((code: string) => void) | null) {
    this.restrictionHandler = handler
  }

  /** Settles 409 `conflict` answers to `put/patch/delete(..., {ifMatch})` (ConflictProvider). */
  setConflictHandler(handler: ConflictHandler | null) {
    this.conflictHandler = handler
  }

  /** Exchange the refresh cookie for a new access cookie. Deduplicated. */
  refreshSession(): Promise<boolean> {
    if (!this.refreshPromise) {
      this.refreshPromise = (async () => {
        const csrf = readCookie('csrf_refresh_token')
        // No refresh CSRF cookie means there is no refreshable session.
        if (!csrf) return false
        try {
          const res = await fetch(`${this.baseUrl}/auth/refresh`, {
            method: 'POST',
            headers: { 'X-CSRF-TOKEN': csrf },
            credentials: 'include',
          })
          return res.ok
        } catch {
          return false
        }
      })().finally(() => {
        this.refreshPromise = null
      })
    }
    return this.refreshPromise
  }

  private handleSessionLost(endpoint: string) {
    clearCache()
    this.unauthorizedHandler?.()
    // Auth endpoints (/auth/me etc.) never redirect: AuthProvider routes.
    if (isAuthEndpoint(endpoint)) return
    if (typeof window !== 'undefined' && !isPublicPath(window.location.pathname)) {
      // Full navigation on purpose: drops all in-memory state of the dead session.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = '/login'
    }
  }

  /**
   * Low-level fetch: cookies, CSRF header, and one silent refresh + retry on
   * 401. Returns the Response (ok or not) for the caller to interpret.
   * Network failures reject with ApiError(0, 'network_error'); aborts
   * reject with the original AbortError.
   */
  private async send(endpoint: string, init: RequestInit = {}): Promise<Response> {
    const url = `${this.baseUrl}${endpoint}`
    const doFetch = async () => {
      const headers = new Headers(init.headers)
      const method = (init.method || 'GET').toUpperCase()
      if (method !== 'GET' && method !== 'HEAD') {
        // Re-read on every attempt: a refresh rotates csrf_access_token.
        const csrf = readCookie('csrf_access_token')
        if (csrf) headers.set('X-CSRF-TOKEN', csrf)
      }
      try {
        return await fetch(url, { ...init, headers, credentials: 'include' })
      } catch (err) {
        if (isAbortError(err)) throw err
        throw new ApiError(0, 'Network error', { code: 'network_error' })
      }
    }

    if (SESSION_CHANGING_ENDPOINTS.includes(endpointPath(endpoint))) clearCache()

    let response = await doFetch()
    if (response.status === 401 && canRefreshFor(endpoint)) {
      if (await this.refreshSession()) {
        // Session is valid again. A 401 on the retry is a domain error
        // (e.g. "current password is incorrect"), not a lost session.
        response = await doFetch()
      } else {
        this.handleSessionLost(endpoint)
      }
    }
    return response
  }

  /** Parse a failed response into an ApiError and run the restriction hook. */
  private async fail(response: Response, fallback: string): Promise<ApiError> {
    const err = await errorFromResponse(response, fallback)
    if (
      err.status === 403 &&
      err.code &&
      (RESTRICTION_CODES as readonly string[]).includes(err.code)
    ) {
      this.restrictionHandler?.(err.code)
    }
    return err
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    maxRetries: number = 2
  ): Promise<T> {
    // Only safe, idempotent reads are retried (5xx / network error). A write
    // that failed with a 5xx or lost connection may already have been applied.
    const method = (options.method || 'GET').toUpperCase()
    const retries = RETRYABLE_METHODS.has(method) ? maxRetries : 0
    const headers = new Headers(options.headers)
    headers.set('Content-Type', 'application/json')

    let lastError: ApiError | null = null

    for (let attempt = 0; attempt <= retries; attempt++) {
      let response: Response
      try {
        response = await this.send(endpoint, { ...options, headers })
      } catch (err) {
        if (isAbortError(err)) throw err
        lastError = isApiError(err) ? err : new ApiError(0, 'Network error', { code: 'network_error' })
        if (attempt < retries) {
          await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)))
          continue
        }
        throw lastError
      }

      if (!response.ok) {
        const err = await this.fail(response, 'Request failed')
        // Don't retry client errors (4xx), only server errors (5xx)
        if (response.status < 500 || attempt >= retries) throw err
        lastError = err
        await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)))
        continue
      }

      if (response.status === 204) {
        return {} as T
      }

      return response.json()
    }

    throw lastError || new ApiError(0, 'Request failed')
  }

  private writeInit(method: string, data: unknown, opts?: WriteOptions): RequestInit {
    const headers = new Headers()
    if (opts?.ifMatch !== undefined && opts.ifMatch !== null) {
      headers.set('If-Match', `"${opts.ifMatch}"`)
    }
    return {
      method,
      headers,
      body: data !== undefined && data !== null ? JSON.stringify(data) : undefined,
      signal: opts?.signal,
    }
  }

  async get<T>(endpoint: string, opts?: GetOptions): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET', signal: opts?.signal })
  }

  async post<T>(endpoint: string, data?: unknown, opts?: { signal?: AbortSignal }): Promise<T> {
    return this.request<T>(endpoint, this.writeInit('POST', data, opts))
  }

  /** PUT/PATCH/DELETE; a versioned write's 409 `conflict` goes to the conflict handler. */
  private async write<T>(
    method: 'PUT' | 'PATCH' | 'DELETE',
    endpoint: string,
    data: unknown,
    opts?: WriteOptions
  ): Promise<T> {
    try {
      return await this.request<T>(endpoint, this.writeInit(method, data, opts))
    } catch (err) {
      const ifMatch = opts?.ifMatch
      const handler = this.conflictHandler
      if (
        handler &&
        typeof ifMatch === 'number' &&
        isApiError(err) &&
        err.status === 409 &&
        err.code === 'conflict'
      ) {
        return (await handler({
          method,
          endpoint,
          data,
          ifMatch,
          error: err,
          retry: (version) => this.write<T>(method, endpoint, data, { ...opts, ifMatch: version }),
        })) as T
      }
      throw err
    }
  }

  async put<T>(endpoint: string, data?: unknown, opts?: WriteOptions): Promise<T> {
    return this.write<T>('PUT', endpoint, data, opts)
  }

  async patch<T>(endpoint: string, data?: unknown, opts?: WriteOptions): Promise<T> {
    return this.write<T>('PATCH', endpoint, data, opts)
  }

  async delete<T>(endpoint: string, data?: unknown, opts?: WriteOptions): Promise<T> {
    return this.write<T>('DELETE', endpoint, data, opts)
  }

  async uploadFile<T>(endpoint: string, fileOrFormData: File | FormData, data?: Record<string, string>): Promise<T> {
    let formData: FormData

    if (fileOrFormData instanceof FormData) {
      formData = fileOrFormData
    } else {
      formData = new FormData()
      formData.append('file', fileOrFormData)
      if (data) {
        Object.entries(data).forEach(([key, value]) => {
          formData.append(key, value)
        })
      }
    }

    const response = await this.send(endpoint, { method: 'POST', body: formData })

    if (!response.ok) {
      throw await this.fail(response, 'Upload failed')
    }

    return response.json()
  }

  async downloadFile(endpoint: string): Promise<Blob> {
    const response = await this.send(endpoint, { method: 'GET' })

    if (!response.ok) {
      throw await this.fail(response, 'Download failed')
    }

    return response.blob()
  }

  /** POST a JSON body and return the binary response (e.g. generated PDFs). */
  async postForBlob(endpoint: string, data?: unknown): Promise<Blob> {
    const response = await this.send(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: data ? JSON.stringify(data) : undefined,
    })

    if (!response.ok) {
      throw await this.fail(response, 'Request failed')
    }

    return response.blob()
  }

  /**
   * Fetch a file and hand it to the browser as a download. The name comes
   * from Content-Disposition, else `fallbackName`. Resolves to the name used.
   */
  async downloadTo(endpoint: string, opts: DownloadOptions): Promise<string> {
    const method = opts.method ?? 'GET'
    const init: RequestInit = { method }
    if (method === 'POST') {
      init.headers = { 'Content-Type': 'application/json' }
      if (opts.data !== undefined) init.body = JSON.stringify(opts.data)
    }
    const response = await this.send(endpoint, init)
    if (!response.ok) {
      throw await this.fail(response, 'Download failed')
    }
    const name =
      filenameFromDisposition(response.headers.get('Content-Disposition')) || opts.fallbackName
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    try {
      const a = document.createElement('a')
      a.href = url
      a.download = name
      a.rel = 'noopener'
      document.body.appendChild(a)
      a.click()
      a.remove()
    } finally {
      // Revoke on the next tick so the click has started the download.
      setTimeout(() => URL.revokeObjectURL(url), 0)
    }
    return name
  }
}

export const api = new ApiClient(API_URL)
export const setRestrictionHandler = (handler: ((code: string) => void) | null) =>
  api.setRestrictionHandler(handler)
export const downloadTo = (endpoint: string, opts: DownloadOptions) => api.downloadTo(endpoint, opts)
export default api
