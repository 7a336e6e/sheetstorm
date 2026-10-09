import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import api from './api'
import { invalidate } from './query-cache'
import { supabase, getSupabase } from './supabase'
import { isTimeMode, type TimeMode } from './time'

export interface User {
  id: string
  email: string
  name: string
  avatar_url?: string
  roles: string[]
  permissions?: string[]
  organization_id?: string
  mfa_enabled?: boolean
  preferences?: { display_timezone?: TimeMode }
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
  /** True when the user holds at least one of `permissions` (false for an empty list). */
  hasAnyPermission: (permissions: readonly string[]) => boolean
  /** @deprecated Display only (e.g. a role badge). Never authorize by role name. */
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
        // Local backend auth first: local/admin accounts never send their
        // password to a third party. Supabase is only tried as a fallback,
        // and only when this deployment is configured for it.
        const sb = getSupabase()
        let localError: unknown
        try {
          const response = await api.post<{
            user: User
            mfa_required?: boolean
          }>('/auth/login', { email, password, mfa_code: mfaCode })

          if (response.mfa_required) {
            throw Object.assign(new Error('MFA code required'), { mfa_required: true, error: 'mfa_required' })
          }
          set({
            user: response.user,
            isAuthenticated: true,
            isLoading: false,
          })
          return
        } catch (error) {
          const status = (error as { status?: number })?.status
          // Only a plain authentication failure (401) can mean "this is a
          // Supabase account"; MFA steps, rate limits and network errors
          // surface as-is.
          if (!sb || status !== 401 || mfaCode) throw error
          localError = error
        }

        try {
          const { data: sbData, error: sbError } = await sb!.auth.signInWithPassword({ email, password })
          if (!sbError && sbData.session) {
            // Exchange Supabase token for backend session cookies
            const response = await api.post<{
              user: User
            }>('/auth/supabase', { access_token: sbData.session.access_token })
            set({
              user: response.user,
              isAuthenticated: true,
              isLoading: false,
            })
            return
          }
        } catch {
          // Supabase unreachable or rejected — report the local auth error.
        }
        throw localError
      },

      register: async (email: string, password: string, name: string) => {
        // Try Supabase first, then fallback to local backend auth
        let registered = false

        try {
          const { data: sbData, error: sbError } = await supabase.auth.signUp({
            email,
            password,
            options: { data: { name } },
          })

          if (!sbError && sbData.session) {
            const response = await api.post<{
              user: User
            }>('/auth/supabase', { access_token: sbData.session.access_token })
            set({
              user: response.user,
              isAuthenticated: true,
              isLoading: false,
            })
            registered = true
          }
        } catch {
          // Supabase failed — will try local auth below
        }

        if (!registered) {
          // Fallback: local backend registration
          const response = await api.post<{
            user: User
          }>('/auth/register', { email, password, name })
          set({
            user: response.user,
            isAuthenticated: true,
            isLoading: false,
          })
        }
      },

      logout: async () => {
        try {
          await api.post('/auth/logout')
        } catch {
          // Ignore errors on logout
        }
        try {
          await getSupabase()?.auth.signOut()
        } catch {
          // Supabase not configured/unreachable — local session is already cleared
        }
        set({ user: null, isAuthenticated: false })
      },

      checkAuth: async () => {
        // Verify with the server using the httpOnly cookie. If the access
        // cookie expired, the API client silently refreshes once; /auth/me
        // never hard-redirects — AuthProvider routes on the resulting state.
        try {
          const user = await api.get<User>('/auth/me')
          set({ user, isAuthenticated: true, isLoading: false })
        } catch {
          set({ user: null, isAuthenticated: false, isLoading: false })
        }
      },

      hasPermission: (permission: string) => {
        const { user } = get()
        return user?.permissions?.includes(permission) ?? false
      },

      hasAnyPermission: (permissions: readonly string[]) => {
        const granted = get().user?.permissions ?? []
        return permissions.some((p) => granted.includes(p))
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

// When the API client concludes the session is gone (refresh failed), drop
// the cached user so persisted state can't claim we're still logged in.
api.onUnauthorized(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false })
})

// Time display preference (UTC / Local). Persisted locally for instant
// first paint and server-side in users.preferences.display_timezone so it
// follows the user across browsers. The server value wins when it loads.
interface TimePrefState {
  mode: TimeMode
  setMode: (mode: TimeMode) => void
  /** Apply a server-side preference (from /auth/me) without writing it back. */
  hydrate: (mode: unknown) => void
}

export const useTimePrefStore = create<TimePrefState>()(
  persist(
    (set, get) => ({
      mode: 'local',

      setMode: (mode: TimeMode) => {
        if (!isTimeMode(mode)) return
        const previous = get().mode
        set({ mode })
        const auth = useAuthStore.getState()
        if (!auth.isAuthenticated || !auth.user) return
        // Keep the cached user in sync so the auth subscription below does
        // not snap back to the old server value.
        useAuthStore.setState({
          user: { ...auth.user, preferences: { ...auth.user.preferences, display_timezone: mode } },
        })
        api.patch('/auth/me/preferences', { display_timezone: mode }).catch(() => {
          // Roll back: restoring the cached server value makes the auth
          // subscription below hydrate the previous mode again.
          const current = useAuthStore.getState().user
          if (current) {
            useAuthStore.setState({
              user: { ...current, preferences: { ...current.preferences, display_timezone: previous } },
            })
          }
        })
      },

      hydrate: (mode: unknown) => {
        if (isTimeMode(mode) && mode !== get().mode) set({ mode })
      },
    }),
    { name: 'sheetstorm-time-pref', partialize: (state) => ({ mode: state.mode }) }
  )
)

useAuthStore.subscribe((state, prev) => {
  const next = state.user?.preferences?.display_timezone
  if (next !== undefined && next !== prev.user?.preferences?.display_timezone) {
    useTimePrefStore.getState().hydrate(next)
  }
})

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
  tlp?: 'white' | 'green' | 'amber' | 'amber_strict' | 'red'
  team_id?: string
  owning_team?: { id: string; name: string }
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
    network_indicators?: number
    host_indicators?: number
    malware_tools?: number
  }
}

// The incident *lists* live in usePaginatedQuery / useAllPages (server
// paging, filters, URL state). This store keeps the open incident and the
// mutations; every mutation invalidates the cached lists so readers refetch.
// `/incidents?` (with the `?`) matches list queries only, not the
// per-incident tab endpoints under `/incidents/<id>/…`.
function invalidateIncidentLists() {
  invalidate('/incidents?')
  invalidate('/incidents/archived')
}

interface IncidentState {
  currentIncident: Incident | null
  isLoading: boolean
  fetchIncident: (id: string) => Promise<void>
  createIncident: (data: Partial<Incident>) => Promise<Incident>
  updateIncident: (id: string, data: Partial<Incident>) => Promise<void>
  archiveIncident: (id: string) => Promise<void>
  unarchiveIncident: (id: string) => Promise<void>
  permanentDeleteIncident: (id: string) => Promise<void>
}

export const useIncidentStore = create<IncidentState>((set) => ({
  currentIncident: null,
  isLoading: false,

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
    invalidateIncidentLists()
    return incident
  },

  updateIncident: async (id: string, data: Partial<Incident>) => {
    const updated = await api.put<Incident>(`/incidents/${id}`, data)
    set((state) => ({
      currentIncident: state.currentIncident?.id === id ? updated : state.currentIncident,
    }))
    invalidateIncidentLists()
  },

  archiveIncident: async (id: string) => {
    await api.post(`/incidents/${id}/archive`, {})
    set((state) => ({
      currentIncident: state.currentIncident?.id === id ? null : state.currentIncident,
    }))
    invalidateIncidentLists()
  },

  unarchiveIncident: async (id: string) => {
    await api.post(`/incidents/${id}/unarchive`, {})
    invalidateIncidentLists()
  },

  permanentDeleteIncident: async (id: string) => {
    await api.delete(`/incidents/${id}/permanent`)
    set((state) => ({
      currentIncident: state.currentIncident?.id === id ? null : state.currentIncident,
    }))
    invalidateIncidentLists()
  },
}))
