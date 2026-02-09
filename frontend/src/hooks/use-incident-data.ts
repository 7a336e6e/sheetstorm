import { useState, useEffect, useCallback } from 'react'
import api from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import type {
  TimelineEvent,
  CompromisedHost,
  CompromisedAccount,
  NetworkIndicator,
  HostBasedIndicator,
  MalwareTool,
  Artifact,
  Task,
  AttackGraphNode,
  AttackGraphEdge,
} from '@/types'

// --- Generic fetch hook ---
interface UseFetchResult<T> {
  data: T[]
  loading: boolean
  error: string | null
  refetch: () => Promise<void>
}

function useFetchList<T>(endpoint: string, enabled: boolean = true): UseFetchResult<T> {
  const [data, setData] = useState<T[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<{ items: T[] }>(endpoint)
      setData(res.items || [])
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch data'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [endpoint])

  useEffect(() => {
    if (enabled) refetch()
  }, [enabled, refetch])

  return { data, loading, error, refetch }
}

// --- Incident-specific hooks ---

export function useTimeline(incidentId: string) {
  const result = useFetchList<TimelineEvent>(`/incidents/${incidentId}/timeline`, !!incidentId)
  const { toast } = useToast()

  const addEvent = useCallback(async (event: Partial<TimelineEvent>) => {
    try {
      await api.post(`/incidents/${incidentId}/timeline`, event)
      await result.refetch()
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to add event', variant: 'destructive' })
      throw err
    }
  }, [incidentId, result, toast])

  const deleteEvent = useCallback(async (eventId: string) => {
    try {
      await api.delete(`/incidents/${incidentId}/timeline/${eventId}`)
      await result.refetch()
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to delete event', variant: 'destructive' })
      throw err
    }
  }, [incidentId, result, toast])

  return { ...result, addEvent, deleteEvent }
}

export function useHosts(incidentId: string) {
  const result = useFetchList<CompromisedHost>(`/incidents/${incidentId}/hosts`, !!incidentId)
  const { toast } = useToast()

  const addHost = useCallback(async (host: Partial<CompromisedHost>) => {
    try {
      await api.post(`/incidents/${incidentId}/hosts`, host)
      await result.refetch()
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to add host', variant: 'destructive' })
      throw err
    }
  }, [incidentId, result, toast])

  const updateHost = useCallback(async (hostId: string, data: Partial<CompromisedHost>) => {
    try {
      await api.put(`/incidents/${incidentId}/hosts/${hostId}`, data)
      await result.refetch()
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to update host', variant: 'destructive' })
      throw err
    }
  }, [incidentId, result, toast])

  const deleteHost = useCallback(async (hostId: string) => {
    try {
      await api.delete(`/incidents/${incidentId}/hosts/${hostId}`)
      await result.refetch()
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to delete host', variant: 'destructive' })
      throw err
    }
  }, [incidentId, result, toast])

  return { ...result, addHost, updateHost, deleteHost }
}

export function useAccounts(incidentId: string) {
  const result = useFetchList<CompromisedAccount>(`/incidents/${incidentId}/accounts`, !!incidentId)
  const { toast } = useToast()

  const addAccount = useCallback(async (account: Partial<CompromisedAccount>) => {
    try {
      await api.post(`/incidents/${incidentId}/accounts`, account)
      await result.refetch()
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to add account', variant: 'destructive' })
      throw err
    }
  }, [incidentId, result, toast])

  const deleteAccount = useCallback(async (accountId: string) => {
    try {
      await api.delete(`/incidents/${incidentId}/accounts/${accountId}`)
      await result.refetch()
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to delete account', variant: 'destructive' })
      throw err
    }
  }, [incidentId, result, toast])

  return { ...result, addAccount, deleteAccount }
}

export function useIOCs(incidentId: string) {
  const network = useFetchList<NetworkIndicator>(`/incidents/${incidentId}/network-iocs`, !!incidentId)
  const hostBased = useFetchList<HostBasedIndicator>(`/incidents/${incidentId}/host-iocs`, !!incidentId)

  return {
    networkIOCs: network.data,
    hostIOCs: hostBased.data,
    loading: network.loading || hostBased.loading,
    error: network.error || hostBased.error,
    refetchNetwork: network.refetch,
    refetchHost: hostBased.refetch,
  }
}

export function useArtifacts(incidentId: string) {
  const result = useFetchList<Artifact>(`/incidents/${incidentId}/artifacts`, !!incidentId)
  const { toast } = useToast()

  const uploadArtifact = useCallback(async (file: File) => {
    try {
      await api.uploadFile(`/incidents/${incidentId}/artifacts`, file)
      await result.refetch()
      toast({ title: 'Uploaded', description: `${file.name} uploaded successfully` })
    } catch (err) {
      toast({ title: 'Upload Failed', description: err instanceof Error ? err.message : 'Failed to upload', variant: 'destructive' })
      throw err
    }
  }, [incidentId, result, toast])

  const deleteArtifact = useCallback(async (artifactId: string) => {
    try {
      await api.delete(`/incidents/${incidentId}/artifacts/${artifactId}`)
      await result.refetch()
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to delete artifact', variant: 'destructive' })
      throw err
    }
  }, [incidentId, result, toast])

  const verifyArtifact = useCallback(async (artifactId: string) => {
    try {
      const res = await api.post<{ is_valid: boolean }>(`/incidents/${incidentId}/artifacts/${artifactId}/verify`)
      await result.refetch()
      return res.is_valid
    } catch (err) {
      toast({ title: 'Error', description: 'Verification failed', variant: 'destructive' })
      throw err
    }
  }, [incidentId, result, toast])

  return { ...result, uploadArtifact, deleteArtifact, verifyArtifact }
}

export function useTasks(incidentId: string) {
  const result = useFetchList<Task>(`/incidents/${incidentId}/tasks`, !!incidentId)
  const { toast } = useToast()

  const addTask = useCallback(async (task: Partial<Task>) => {
    try {
      await api.post(`/incidents/${incidentId}/tasks`, task)
      await result.refetch()
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to add task', variant: 'destructive' })
      throw err
    }
  }, [incidentId, result, toast])

  const updateTask = useCallback(async (taskId: string, data: Partial<Task>) => {
    try {
      await api.put(`/incidents/${incidentId}/tasks/${taskId}`, data)
      await result.refetch()
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to update task', variant: 'destructive' })
      throw err
    }
  }, [incidentId, result, toast])

  return { ...result, addTask, updateTask }
}

export function useGraph(incidentId: string) {
  const [nodes, setNodes] = useState<AttackGraphNode[]>([])
  const [edges, setEdges] = useState<AttackGraphEdge[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  const refetch = useCallback(async () => {
    if (!incidentId) return
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<{ nodes: AttackGraphNode[]; edges: AttackGraphEdge[] }>(
        `/incidents/${incidentId}/attack-graph`
      )
      setNodes(res.nodes || [])
      setEdges(res.edges || [])
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch graph'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [incidentId])

  useEffect(() => { refetch() }, [refetch])

  const autoGenerate = useCallback(async (clearExisting: boolean = true) => {
    try {
      await api.post(`/incidents/${incidentId}/attack-graph/auto-generate`, { clear_existing: clearExisting })
      await refetch()
      toast({ title: 'Graph Generated', description: 'Attack graph has been auto-generated' })
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to generate graph', variant: 'destructive' })
      throw err
    }
  }, [incidentId, refetch, toast])

  return { nodes, edges, loading, error, refetch, autoGenerate }
}
