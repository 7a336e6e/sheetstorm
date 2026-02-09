const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000/api/v1'

interface ApiError {
  error: string
  message: string
  details?: Record<string, unknown>
  mfa_required?: boolean
}

class ApiClient {
  private baseUrl: string
  private token: string | null = null

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('access_token')
    }
  }

  setToken(token: string | null) {
    this.token = token
    if (typeof window !== 'undefined') {
      if (token) {
        localStorage.setItem('access_token', token)
      } else {
        localStorage.removeItem('access_token')
      }
    }
  }

  getToken(): string | null {
    return this.token
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    retries: number = 2
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`
    const headers = new Headers(options.headers)
    headers.set('Content-Type', 'application/json')
    if (this.token) {
      headers.set('Authorization', `Bearer ${this.token}`)
    }

    let lastError: Error | null = null

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const response = await fetch(url, {
          ...options,
          headers,
        })

        if (!response.ok) {
          const error: ApiError = await response.json().catch(() => ({
            error: 'unknown_error',
            message: 'An unexpected error occurred',
          }))

          if (response.status === 401) {
            this.setToken(null)
            if (typeof window !== 'undefined') {
              window.location.href = '/login'
            }
          }

          // Don't retry client errors (4xx), only server errors (5xx)
          if (response.status >= 400 && response.status < 500) {
            const err = new Error(error.message || 'Request failed') as any
            // Preserve the full error body for MFA and other structured errors
            if (error.mfa_required) err.mfa_required = true
            if (error.error) err.error = error.error
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

    const url = `${this.baseUrl}${endpoint}`
    const headers = new Headers()
    if (this.token) {
      headers.set('Authorization', `Bearer ${this.token}`)
    }

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Upload failed' }))
      throw new Error(error.message)
    }

    return response.json()
  }

  async downloadFile(endpoint: string): Promise<Blob> {
    const url = `${this.baseUrl}${endpoint}`
    const headers = new Headers()
    if (this.token) {
      headers.set('Authorization', `Bearer ${this.token}`)
    }

    const response = await fetch(url, { headers })

    if (!response.ok) {
      throw new Error('Download failed')
    }

    return response.blob()
  }
}

// Audit Logs API
interface AuditLog {
  id: string
  event_type: string
  action: string
  resource_type?: string
  resource_id?: string
  incident_id?: string
  created_at: string
  user?: {
    id: string
    email: string
    name: string
  }
  details?: Record<string, unknown>
}

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
