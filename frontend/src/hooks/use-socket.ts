import { useEffect, useCallback, useRef } from 'react'
import { useSocketContext } from '@/components/providers/socket-provider'

/**
 * Access the raw Socket.IO instance and connection status.
 */
export function useSocket() {
  const { socket, status, isConnected } = useSocketContext()
  return { socket, status, isConnected }
}

/**
 * Subscribe to a Socket.IO event. Automatically handles
 * subscribe/unsubscribe on mount/unmount and dependency changes.
 *
 * @param event - The event name to listen for
 * @param handler - Callback invoked with the event payload
 */
export function useSocketEvent<T = unknown>(
  event: string,
  handler: (data: T) => void
) {
  const { socket } = useSocketContext()
  const handlerRef = useRef(handler)

  // Keep handler ref fresh without re-subscribing
  useEffect(() => {
    handlerRef.current = handler
  }, [handler])

  useEffect(() => {
    if (!socket) return

    const listener = (data: T) => handlerRef.current(data)
    socket.on(event, listener)

    return () => {
      socket.off(event, listener)
    }
  }, [socket, event])
}

/**
 * Emit a Socket.IO event. Returns a stable emit function.
 *
 * @param event - Default event name (can be overridden per-call)
 */
export function useSocketEmit(event?: string) {
  const { socket, isConnected } = useSocketContext()

  const emit = useCallback(
    (eventOrData?: string | Record<string, unknown>, data?: Record<string, unknown>) => {
      if (!socket || !isConnected) return

      if (typeof eventOrData === 'string') {
        socket.emit(eventOrData, data)
      } else if (event) {
        socket.emit(event, eventOrData)
      }
    },
    [socket, isConnected, event]
  )

  return emit
}

/**
 * Manage joining/leaving an incident room for real-time collaboration.
 *
 * @param incidentId - The incident UUID to join (null to skip)
 * @param userId - Current user's ID
 * @param userName - Current user's display name
 */
export function useIncidentRoom(
  incidentId: string | null,
  userId: string | undefined,
  userName: string | undefined
) {
  const { socket, isConnected } = useSocketContext()

  useEffect(() => {
    if (!socket || !isConnected || !incidentId || !userId) return

    socket.emit('join_incident', {
      incident_id: incidentId,
      user_id: userId,
      user_name: userName,
    })

    return () => {
      socket.emit('leave_incident', { incident_id: incidentId })
    }
  }, [socket, isConnected, incidentId, userId, userName])
}
