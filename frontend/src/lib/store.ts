import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import api from './api'
import { supabase } from './supabase'

export interface User {
  id: string
  email: string
  name: string
  avatar_url?: string
  roles: string[]
  permissions?: string[]
  organization_id?: string
  mfa_enabled?: boolean
}

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, password: string, mfaCode?: string) => Promise<void>
  register: (email: string, password: string, name: string) => Promise<void>
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
  hasPermission: (permission: string) => boolean
  hasRole: (role: string) => boolean
  refreshUser: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isLoading: true,

      login: async (email: string, password: string, mfaCode?: string) => {
        // Try Supabase first, then fallback to local backend auth
        let authenticated = false

        try {
          const { data: sbData, error: sbError } = await supabase.auth.signInWithPassword({
            email,
            password,
          })

          if (!sbError && sbData.session) {
            // Exchange Supabase token for backend JWT
            const response = await api.post<{
              access_token: string
              refresh_token: string
              user: User
            }>('/auth/supabase', { access_token: sbData.session.access_token })

            api.setToken(response.access_token)
            localStorage.setItem('refresh_token', response.refresh_token)

            set({
              user: response.user,
              isAuthenticated: true,
              isLoading: false,
            })
            authenticated = true
          }
        } catch {
          // Supabase failed — will try local auth below
        }

        if (!authenticated) {
          // Fallback: local backend auth (for local/admin users)
          const response = await api.post<{
            access_token: string
            refresh_token: string
            user: User
            mfa_required?: boolean
          }>('/auth/login', { email, password, mfa_code: mfaCode })

          if (response.mfa_required) {
            throw Object.assign(new Error('MFA code required'), { mfa_required: true, error: 'mfa_required' })
          }

          api.setToken(response.access_token)
          localStorage.setItem('refresh_token', response.refresh_token)

          set({
            user: response.user,
            isAuthenticated: true,
            isLoading: false,
          })
        }
      },

      register: async (email: string, password: string, name: string) => {
        // Sign up via Supabase
        const { data: sbData, error: sbError } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { name } },
        })

        if (sbError) {
          throw new Error(sbError.message)
        }

        // If Supabase returns a session immediately (email confirm disabled)
        if (sbData.session) {
          const response = await api.post<{
            access_token: string
            refresh_token: string
            user: User
          }>('/auth/supabase', { access_token: sbData.session.access_token })

          api.setToken(response.access_token)
          localStorage.setItem('refresh_token', response.refresh_token)

          set({
            user: response.user,
            isAuthenticated: true,
            isLoading: false,
          })
        } else {
          // Email confirmation is required — user will need to verify email first
          throw new Error('Check your email to confirm your account before signing in.')
        }
      },

      logout: async () => {
        try {
          await api.post('/auth/logout')
        } catch {
          // Ignore errors on logout
        }
        await supabase.auth.signOut()
        api.setToken(null)
        localStorage.removeItem('refresh_token')
        set({ user: null, isAuthenticated: false })
      },

      checkAuth: async () => {
        const token = api.getToken()
        if (!token) {
          set({ isLoading: false, isAuthenticated: false })
          return
        }

        try {
          const user = await api.get<User>('/auth/me')
          set({ user, isAuthenticated: true, isLoading: false })
        } catch {
          api.setToken(null)
          set({ user: null, isAuthenticated: false, isLoading: false })
        }
      },

      hasPermission: (permission: string) => {
        const { user } = get()
        return user?.permissions?.includes(permission) ?? false
      },

      hasRole: (role: string) => {
        const { user } = get()
        return user?.roles?.includes(role) ?? false
      },

      refreshUser: async () => {
        try {
          const user = await api.get<User>('/auth/me')
          set({ user })
        } catch {
          // Silently fail
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)

// Incident store
export interface Incident {
  id: string
  incident_number: number
  title: string
  description?: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  status: 'open' | 'contained' | 'eradicated' | 'recovered' | 'closed'
  classification?: string
  phase: number
  phase_name: string
  lead_responder?: User
  creator?: { id: string; name: string }
  teams?: { id: string; name: string | null }[]
  detected_at?: string
  created_at: string
  updated_at?: string
  counts?: {
    timeline_events: number
    compromised_hosts: number
    compromised_accounts: number
    artifacts: number
    tasks: number
  }
}

interface IncidentState {
  incidents: Incident[]
  currentIncident: Incident | null
  isLoading: boolean
  fetchIncidents: (params?: Record<string, string>) => Promise<void>
  fetchIncident: (id: string) => Promise<void>
  createIncident: (data: Partial<Incident>) => Promise<Incident>
  updateIncident: (id: string, data: Partial<Incident>) => Promise<void>
  deleteIncident: (id: string) => Promise<void>
}

export const useIncidentStore = create<IncidentState>((set, get) => ({
  incidents: [],
  currentIncident: null,
  isLoading: false,

  fetchIncidents: async (params?: Record<string, string>) => {
    set({ isLoading: true })
    try {
      const query = params ? '?' + new URLSearchParams(params).toString() : ''
      const response = await api.get<{ items: Incident[] }>(`/incidents${query}`)
      set({ incidents: response.items, isLoading: false })
    } catch (error) {
      set({ isLoading: false })
      throw error
    }
  },

  fetchIncident: async (id: string) => {
    set({ isLoading: true })
    try {
      const incident = await api.get<Incident>(`/incidents/${id}`)
      set({ currentIncident: incident, isLoading: false })
    } catch (error) {
      set({ isLoading: false })
      throw error
    }
  },

  createIncident: async (data: Partial<Incident>) => {
    const incident = await api.post<Incident>('/incidents', data)
    set((state) => ({ incidents: [incident, ...state.incidents] }))
    return incident
  },

  updateIncident: async (id: string, data: Partial<Incident>) => {
    const updated = await api.put<Incident>(`/incidents/${id}`, data)
    set((state) => ({
      incidents: state.incidents.map((i) => (i.id === id ? updated : i)),
      currentIncident: state.currentIncident?.id === id ? updated : state.currentIncident,
    }))
  },

  deleteIncident: async (id: string) => {
    await api.delete(`/incidents/${id}`)
    set((state) => ({
      incidents: state.incidents.filter((i) => i.id !== id),
      currentIncident: state.currentIncident?.id === id ? null : state.currentIncident,
    }))
  },
}))
