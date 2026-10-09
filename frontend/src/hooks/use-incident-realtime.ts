"use client"

/**
 * Live collaboration for one incident page (mounted once, in
 * `app/dashboard/incidents/[id]/page.tsx`, and provided to the tree through
 * `IncidentRealtimeContext`).
 *
 * - Joins the incident rooms on mount and on every socket (re)connect.
 * - `entity:changed` → seq gap check per scope, then merged into every live
 *   list (`lib/realtime/live.ts`) and the open incident header.
 * - Seq gaps (also detected on rejoin) and `incident:resync` refetch the
 *   affected scopes, coalesced: one request per scope per 500 ms, one in
 *   flight, one trailing; only mounted lists refetch.
 * - `incident:access_revoked` → notice + navigate to the incident list.
 * - Presence: `setFocus(...)` (debounced 300 ms) + a 25 s heartbeat;
 *   `presence:state` feeds PresenceAvatars / ItemPresenceBadge.
 * - `graph:node_drag` relay for the attack graph.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useSocket } from '@/hooks/use-socket'
import { useAuthStore, useIncidentStore } from '@/lib/store'
import { forget } from '@/lib/query-cache'
import { toast } from '@/components/ui/use-toast'
import { createCoalescer } from '@/lib/realtime/coalesce'
import { dispatchChange, resyncScopes } from '@/lib/realtime/live'
import { applyToObject } from '@/lib/realtime/merge'
import { gapsAfterJoin, trackSeq, type SeqState } from '@/lib/realtime/seq'
import {
  REALTIME_EVENTS as EV,
  isEntityChange,
  scopeForEntity,
  type AccessRevokedEvent,
  type EntityChange,
  type JoinAck,
  type LiveStatus,
  type NodeDragEvent,
  type PresenceFocus,
  type PresenceMode,
  type PresenceState,
  type PresenceUser,
  type ResyncEvent,
} from '@/lib/realtime/types'
import type { Incident } from '@/types'

export const RESYNC_COALESCE_MS = 500
export const PRESENCE_DEBOUNCE_MS = 300
export const PRESENCE_HEARTBEAT_MS = 25_000

export interface IncidentRealtime {
  incidentId: string | null
  status: LiveStatus
  /** Everyone on the incident (one entry per socket; may include me). */
  presence: PresenceUser[]
  selfUserId?: string
  /** What I'm looking at / editing (`null` = just viewing the incident). */
  setFocus(focus: PresenceFocus | null, mode?: PresenceMode): void
  /** Relay a node drag preview (throttle at the caller). */
  sendNodeDrag(nodeId: string, x: number, y: number): void
  /** Remote drag previews. Returns the unsubscribe function. */
  onNodeDrag(fn: (ev: NodeDragEvent) => void): () => void
}

export const IncidentRealtimeContext = createContext<IncidentRealtime | null>(null)

/** The incident page's realtime handle, or null outside an incident page. */
export function useIncidentRealtimeContext(): IncidentRealtime | null {
  return useContext(IncidentRealtimeContext)
}

const ACCESS_REVOKED_COPY: Record<string, string> = {
  archived: 'This incident was archived.',
  purged: 'This incident was permanently deleted.',
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

function isPresenceUser(v: unknown): v is PresenceUser {
  return isRecord(v) && typeof v.pid === 'string' && typeof v.user_id === 'string'
}

/** Merge an `incident` change into the open incident (version-guarded). */
function applyIncidentChange(change: EntityChange): void {
  const { currentIncident } = useIncidentStore.getState()
  if (!currentIncident || currentIncident.id !== change.id || change.op === 'deleted') return
  const next = applyToObject(currentIncident as Incident & { version?: number }, change)
  if (next && next !== currentIncident) useIncidentStore.setState({ currentIncident: next as Incident })
}

export function useIncidentRealtime(incidentId: string | null | undefined): IncidentRealtime {
  const id = incidentId || null
  const { socket, status: socketStatus } = useSocket()
  const router = useRouter()
  const selfUserId = useAuthStore((s) => s.user?.id)

  const [presence, setPresence] = useState<PresenceUser[]>([])
  const [joinedId, setJoinedId] = useState<string | null>(null)

  const focusRef = useRef<{ focus: PresenceFocus | null; mode: PresenceMode }>({ focus: null, mode: 'viewing' })
  const sendPresenceRef = useRef<() => void>(() => {})
  const focusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const dragListenersRef = useRef(new Set<(ev: NodeDragEvent) => void>())

  useEffect(() => {
    if (!socket || !id) return
    let seqState: SeqState = {}
    let joinedOnce = false
    let joinedNow = false
    const coalescer = createCoalescer((scope) => resyncScopes(id, [scope]), RESYNC_COALESCE_MS)

    const sendPresence = () => {
      if (!socket.connected || !joinedNow) return
      const { focus, mode } = focusRef.current
      socket.emit(EV.presenceUpdate, { incident_id: id, focus, mode: focus ? mode : 'viewing' })
    }
    sendPresenceRef.current = sendPresence

    const join = () => socket.emit(EV.join, { incident_id: id })

    const onConnect = () => join()
    const onDisconnect = () => {
      joinedNow = false
      setJoinedId(null)
    }
    const onJoined = (raw: unknown) => {
      if (!isRecord(raw) || raw.incident_id !== id) return
      const ack = raw as unknown as JoinAck
      const { state, gaps } = gapsAfterJoin(seqState, { scopes: Array.isArray(ack.scopes) ? ack.scopes : [], seq: ack.seq }, joinedOnce)
      seqState = state
      joinedOnce = true
      joinedNow = true
      gaps.forEach((scope) => coalescer.request(scope))
      if (Array.isArray(ack.presence)) setPresence(ack.presence.filter(isPresenceUser))
      setJoinedId(id)
      // Re-announce focus after a reconnect.
      if (focusRef.current.focus) sendPresence()
    }
    const onChanged = (raw: unknown) => {
      if (!isEntityChange(raw) || raw.incident_id !== id) return
      const scope = raw.scope || scopeForEntity(raw.entity)
      if (scope) {
        const r = trackSeq(seqState, scope, raw.seq)
        seqState = r.state
        if (r.gap) coalescer.request(scope)
      }
      dispatchChange(raw)
      if (raw.entity === 'incident') applyIncidentChange(raw)
    }
    const onResync = (raw: unknown) => {
      if (!isRecord(raw) || raw.incident_id !== id) return
      const ev = raw as unknown as ResyncEvent
      if (!Array.isArray(ev.scopes)) return
      ev.scopes.forEach((s) => {
        if (typeof s === 'string') coalescer.request(s)
      })
    }
    const onAccessRevoked = (raw: unknown) => {
      if (!isRecord(raw) || raw.incident_id !== id) return
      const ev = raw as unknown as AccessRevokedEvent
      joinedNow = false
      coalescer.dispose()
      forget(`/incidents/${id}`)
      toast({
        title: 'Access to this incident ended',
        description: (ev.reason && ACCESS_REVOKED_COPY[ev.reason]) || 'You no longer have access to this incident.',
      })
      router.push('/dashboard/incidents')
    }
    const onPresenceState = (raw: unknown) => {
      if (!isRecord(raw) || raw.incident_id !== id) return
      const ev = raw as unknown as PresenceState
      if (Array.isArray(ev.users)) setPresence(ev.users.filter(isPresenceUser))
    }
    const onNodeDrag = (raw: unknown) => {
      if (!isRecord(raw) || raw.incident_id !== id) return
      const { node_id, x, y } = raw
      if (typeof node_id !== 'string' || typeof x !== 'number' || typeof y !== 'number') return
      if (!Number.isFinite(x) || !Number.isFinite(y)) return
      const ev = raw as unknown as NodeDragEvent
      dragListenersRef.current.forEach((fn) => fn(ev))
    }

    socket.on('connect', onConnect)
    socket.on('disconnect', onDisconnect)
    socket.on(EV.joined, onJoined)
    socket.on(EV.changed, onChanged)
    socket.on(EV.resync, onResync)
    socket.on(EV.accessRevoked, onAccessRevoked)
    socket.on(EV.presenceState, onPresenceState)
    socket.on(EV.nodeDrag, onNodeDrag)
    if (socket.connected) join()

    const heartbeat = setInterval(sendPresence, PRESENCE_HEARTBEAT_MS)

    return () => {
      clearInterval(heartbeat)
      coalescer.dispose()
      socket.off('connect', onConnect)
      socket.off('disconnect', onDisconnect)
      socket.off(EV.joined, onJoined)
      socket.off(EV.changed, onChanged)
      socket.off(EV.resync, onResync)
      socket.off(EV.accessRevoked, onAccessRevoked)
      socket.off(EV.presenceState, onPresenceState)
      socket.off(EV.nodeDrag, onNodeDrag)
      if (socket.connected && joinedNow) socket.emit(EV.leave, { incident_id: id })
      sendPresenceRef.current = () => {}
      setJoinedId(null)
      setPresence([])
    }
  }, [socket, id, router])

  useEffect(
    () => () => {
      if (focusTimerRef.current) clearTimeout(focusTimerRef.current)
    },
    []
  )

  const setFocus = useCallback((focus: PresenceFocus | null, mode: PresenceMode = 'viewing') => {
    const cur = focusRef.current
    const next = { focus, mode: focus ? mode : ('viewing' as PresenceMode) }
    if (cur.mode === next.mode && cur.focus?.entity === focus?.entity && cur.focus?.id === focus?.id) return
    focusRef.current = next
    if (focusTimerRef.current) clearTimeout(focusTimerRef.current)
    focusTimerRef.current = setTimeout(() => {
      focusTimerRef.current = null
      sendPresenceRef.current()
    }, PRESENCE_DEBOUNCE_MS)
  }, [])

  const sendNodeDrag = useCallback(
    (nodeId: string, x: number, y: number) => {
      if (!socket?.connected || !id || joinedId !== id) return
      if (!Number.isFinite(x) || !Number.isFinite(y)) return
      socket.emit(EV.nodeDrag, { incident_id: id, node_id: nodeId, x, y })
    },
    [socket, id, joinedId]
  )

  const onNodeDrag = useCallback((fn: (ev: NodeDragEvent) => void) => {
    const set = dragListenersRef.current
    set.add(fn)
    return () => {
      set.delete(fn)
    }
  }, [])

  const joined = !!id && joinedId === id
  const status: LiveStatus =
    socketStatus === 'connected' ? (joined ? 'live' : 'connecting') : socketStatus === 'connecting' ? 'connecting' : 'offline'

  return useMemo(
    () => ({ incidentId: id, status, presence, selfUserId, setFocus, sendNodeDrag, onNodeDrag }),
    [id, status, presence, selfUserId, setFocus, sendNodeDrag, onNodeDrag]
  )
}
