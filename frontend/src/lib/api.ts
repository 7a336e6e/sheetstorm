import type { AuditLog } from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || '/api/v1'

/** Read a non-httpOnly cookie (used for the CSRF double-submit token). */
function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const escaped = name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1')
  const m = document.cookie.match(new RegExp('(?:^|; )' + escaped + '=([^;]*)'))
  return m ? decodeURIComponent(m[1]) : null
}


interface ApiError {
  error: string
  message: string
  details?: Record<string, unknown>
  mfa_required?: boolean
}

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
  '/auth/registration-status',
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
 * Browser auth is cookie-only: the access/refresh JWTs live in httpOnly
 * cookies and mutating requests carry the CSRF double-submit header. The SPA
 * never sends an Authorization header — JSON token fields in auth responses
 * exist for non-browser clients (MCP) and are deliberately ignored here.
 */
class ApiClient {
  private baseUrl: string
  private refreshPromise: Promise<boolean> | null = null
  private unauthorizedHandler: (() => void) | null = null

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
   */
  private async send(endpoint: string, init: RequestInit = {}): Promise<Response> {
    const url = `${this.baseUrl}${endpoint}`
    const doFetch = () => {
      const headers = new Headers(init.headers)
      const method = (init.method || 'GET').toUpperCase()
      if (method !== 'GET' && method !== 'HEAD') {
        // Re-read on every attempt: a refresh rotates csrf_access_token.
        const csrf = readCookie('csrf_access_token')
        if (csrf) headers.set('X-CSRF-TOKEN', csrf)
      }
      return fetch(url, { ...init, headers, credentials: 'include' })
    }

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

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    retries: number = 2
  ): Promise<T> {
    const headers = new Headers(options.headers)
    headers.set('Content-Type', 'application/json')

    let lastError: Error | null = null

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const response = await this.send(endpoint, { ...options, headers })

        if (!response.ok) {
          const error: ApiError = await response.json().catch(() => ({
            error: 'unknown_error',
            message: 'An unexpected error occurred',
          }))

          // Don't retry client errors (4xx), only server errors (5xx)
          if (response.status >= 400 && response.status < 500) {
            const err = new Error(error.message || 'Request failed') as Error & {
              mfa_required?: boolean
              error?: string
              status?: number
            }
            // Preserve the full error body for MFA and other structured errors
            if (error.mfa_required) err.mfa_required = true
            if (error.error) err.error = error.error
            err.status = response.status
            throw err
          }

          lastError = new Error(error.message || 'Request failed')
          if (attempt < retries) {
            await new Promise(r => setTimeout(r, 1000 * (attempt + 1)))
            continue
          }
          throw lastError
        }

        if (response.status === 204) {
          return {} as T
        }

        return response.json()
      } catch (err) {
        lastError = err instanceof Error ? err : new Error('Network error')
        // Retry on network errors (TypeError from fetch)
        if (err instanceof TypeError && attempt < retries) {
          await new Promise(r => setTimeout(r, 1000 * (attempt + 1)))
          continue
        }
        throw lastError
      }
    }

    throw lastError || new Error('Request failed')
  }

  async get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' })
  }

  async post<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  async put<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  async patch<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  async delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' })
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
      const error = await response.json().catch(() => ({ message: 'Upload failed' }))
      throw new Error(error.message)
    }

    return response.json()
  }

  async downloadFile(endpoint: string): Promise<Blob> {
    const response = await this.send(endpoint, { method: 'GET' })

    if (!response.ok) {
      throw new Error('Download failed')
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
      const err = await response.json().catch(() => ({ message: 'Request failed' }))
      throw new Error(err.message || 'Request failed')
    }

    return response.blob()
  }
}

// Audit Logs API
interface AuditLogStats {
  by_event_type: Record<string, number>
  by_day: Record<string, number>
  total: number
}

interface AuditLogsResponse {
  items: AuditLog[]
  total: number
  page: number
  per_page: number
  pages: number
}

export const auditLogs = {
  list: (params?: {
    page?: number
    per_page?: number
    user_id?: string
    event_type?: string
    action?: string
    resource_type?: string
    incident_id?: string
    start_date?: string
    end_date?: string
  }) => {
    const query = new URLSearchParams()
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          query.append(key, String(value))
        }
      })
    }
    const queryString = query.toString()
    return api.get<AuditLogsResponse>(
      `/audit-logs${queryString ? `?${queryString}` : ''}`
    )
  },

  getStats: () => {
    return api.get<AuditLogStats>('/audit-logs/stats')
  },
}

export const api = new ApiClient(API_URL)
export default api
