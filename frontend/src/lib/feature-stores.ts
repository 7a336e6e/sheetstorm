import { create } from 'zustand'
import api from './api'
import type {
  TimelineEvent,
  CompromisedHost,
  CompromisedAccount,
  Artifact,
  Task,
  Notification,
  AttackGraphNode,
  AttackGraphEdge,
} from '@/types'

// --- Generic entity state pattern ---
interface EntityState<T> {
  items: T[]
  loading: boolean
  error: string | null
}

// --- Notification Store ---
interface NotificationState extends EntityState<Notification> {
  unreadCount: number
  fetchNotifications: () => Promise<void>
  markAsRead: (id: string) => Promise<void>
  markAllRead: () => Promise<void>
  addNotification: (notification: Notification) => void
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  items: [],
  loading: false,
  error: null,
  unreadCount: 0,

  fetchNotifications: async () => {
    set({ loading: true, error: null })
    try {
      const res = await api.get<{ items: Notification[]; total: number }>('/notifications?per_page=50')
      const items = res.items || []
      set({
        items,
        unreadCount: items.filter(n => !n.is_read).length,
        loading: false,
      })
    } catch (err) {
      set({ loading: false, error: err instanceof Error ? err.message : 'Failed to fetch notifications' })
    }
  },

  markAsRead: async (id: string) => {
    try {
      await api.put(`/notifications/${id}/read`)
      set(state => ({
        items: state.items.map(n => n.id === id ? { ...n, is_read: true } : n),
        unreadCount: Math.max(0, state.unreadCount - 1),
      }))
    } catch { /* silent */ }
  },

  markAllRead: async () => {
    try {
      await api.post('/notifications/mark-all-read')
      set(state => ({
        items: state.items.map(n => ({ ...n, is_read: true })),
        unreadCount: 0,
      }))
    } catch { /* silent */ }
  },

  addNotification: (notification: Notification) => {
    set(state => ({
      items: [notification, ...state.items],
      unreadCount: state.unreadCount + 1,
    }))
  },
}))

// --- Timeline Store ---
interface TimelineState extends EntityState<TimelineEvent> {
  fetchTimeline: (incidentId: string) => Promise<void>
  addEvent: (incidentId: string, event: Partial<TimelineEvent>) => Promise<void>
  deleteEvent: (incidentId: string, eventId: string) => Promise<void>
}

export const useTimelineStore = create<TimelineState>((set) => ({
  items: [],
  loading: false,
  error: null,

  fetchTimeline: async (incidentId: string) => {
    set({ loading: true, error: null })
    try {
      const res = await api.get<{ items: TimelineEvent[] }>(`/incidents/${incidentId}/timeline`)
      set({ items: res.items || [], loading: false })
    } catch (err) {
      set({ loading: false, error: err instanceof Error ? err.message : 'Failed to fetch timeline' })
    }
  },

  addEvent: async (incidentId: string, event: Partial<TimelineEvent>) => {
    const newEvent = await api.post<TimelineEvent>(`/incidents/${incidentId}/timeline`, event)
    set(state => ({ items: [...state.items, newEvent] }))
  },

  deleteEvent: async (incidentId: string, eventId: string) => {
    await api.delete(`/incidents/${incidentId}/timeline/${eventId}`)
    set(state => ({ items: state.items.filter(e => e.id !== eventId) }))
  },
}))

// --- Hosts Store ---
interface HostState extends EntityState<CompromisedHost> {
  fetchHosts: (incidentId: string) => Promise<void>
  addHost: (incidentId: string, host: Partial<CompromisedHost>) => Promise<void>
  updateHost: (incidentId: string, hostId: string, data: Partial<CompromisedHost>) => Promise<void>
  deleteHost: (incidentId: string, hostId: string) => Promise<void>
}

export const useHostStore = create<HostState>((set) => ({
  items: [],
  loading: false,
  error: null,

  fetchHosts: async (incidentId: string) => {
    set({ loading: true, error: null })
    try {
      const res = await api.get<{ items: CompromisedHost[] }>(`/incidents/${incidentId}/hosts`)
      set({ items: res.items || [], loading: false })
    } catch (err) {
      set({ loading: false, error: err instanceof Error ? err.message : 'Failed to fetch hosts' })
    }
  },

  addHost: async (incidentId: string, host: Partial<CompromisedHost>) => {
    const newHost = await api.post<CompromisedHost>(`/incidents/${incidentId}/hosts`, host)
    set(state => ({ items: [...state.items, newHost] }))
  },

  updateHost: async (incidentId: string, hostId: string, data: Partial<CompromisedHost>) => {
    const updated = await api.put<CompromisedHost>(`/incidents/${incidentId}/hosts/${hostId}`, data)
    set(state => ({ items: state.items.map(h => h.id === hostId ? updated : h) }))
  },

  deleteHost: async (incidentId: string, hostId: string) => {
    await api.delete(`/incidents/${incidentId}/hosts/${hostId}`)
    set(state => ({ items: state.items.filter(h => h.id !== hostId) }))
  },
}))

// --- Tasks Store ---
interface TaskState extends EntityState<Task> {
  fetchTasks: (incidentId: string) => Promise<void>
  addTask: (incidentId: string, task: Partial<Task>) => Promise<void>
  updateTask: (incidentId: string, taskId: string, data: Partial<Task>) => Promise<void>
}

export const useTaskStore = create<TaskState>((set) => ({
  items: [],
  loading: false,
  error: null,

  fetchTasks: async (incidentId: string) => {
    set({ loading: true, error: null })
    try {
      const res = await api.get<{ items: Task[] }>(`/incidents/${incidentId}/tasks`)
      set({ items: res.items || [], loading: false })
    } catch (err) {
      set({ loading: false, error: err instanceof Error ? err.message : 'Failed to fetch tasks' })
    }
  },

  addTask: async (incidentId: string, task: Partial<Task>) => {
    const newTask = await api.post<Task>(`/incidents/${incidentId}/tasks`, task)
    set(state => ({ items: [...state.items, newTask] }))
  },

  updateTask: async (incidentId: string, taskId: string, data: Partial<Task>) => {
    const updated = await api.put<Task>(`/incidents/${incidentId}/tasks/${taskId}`, data)
    set(state => ({ items: state.items.map(t => t.id === taskId ? updated : t) }))
  },
}))

// --- Artifacts Store ---
interface ArtifactState extends EntityState<Artifact> {
  fetchArtifacts: (incidentId: string) => Promise<void>
  deleteArtifact: (incidentId: string, artifactId: string) => Promise<void>
}

export const useArtifactStore = create<ArtifactState>((set) => ({
  items: [],
  loading: false,
  error: null,

  fetchArtifacts: async (incidentId: string) => {
    set({ loading: true, error: null })
    try {
      const res = await api.get<{ items: Artifact[] }>(`/incidents/${incidentId}/artifacts`)
      set({ items: res.items || [], loading: false })
    } catch (err) {
      set({ loading: false, error: err instanceof Error ? err.message : 'Failed to fetch artifacts' })
    }
  },

  deleteArtifact: async (incidentId: string, artifactId: string) => {
    await api.delete(`/incidents/${incidentId}/artifacts/${artifactId}`)
    set(state => ({ items: state.items.filter(a => a.id !== artifactId) }))
  },
}))

// --- Graph Store ---
interface GraphState {
  nodes: AttackGraphNode[]
  edges: AttackGraphEdge[]
  loading: boolean
  error: string | null
  fetchGraph: (incidentId: string) => Promise<void>
  autoGenerate: (incidentId: string, clearExisting?: boolean) => Promise<void>
}

export const useGraphStore = create<GraphState>((set) => ({
  nodes: [],
  edges: [],
  loading: false,
  error: null,

  fetchGraph: async (incidentId: string) => {
    set({ loading: true, error: null })
    try {
      const res = await api.get<{ nodes: AttackGraphNode[]; edges: AttackGraphEdge[] }>(
        `/incidents/${incidentId}/attack-graph`
      )
      set({ nodes: res.nodes || [], edges: res.edges || [], loading: false })
    } catch (err) {
      set({ loading: false, error: err instanceof Error ? err.message : 'Failed to fetch graph' })
    }
  },

  autoGenerate: async (incidentId: string, clearExisting = true) => {
    set({ loading: true })
    try {
      const res = await api.post<{ nodes: AttackGraphNode[]; edges: AttackGraphEdge[] }>(
        `/incidents/${incidentId}/attack-graph/auto-generate`,
        { clear_existing: clearExisting }
      )
      set({ nodes: res.nodes || [], edges: res.edges || [], loading: false })
    } catch (err) {
      set({ loading: false, error: err instanceof Error ? err.message : 'Failed to generate graph' })
      throw err
    }
  },
}))
