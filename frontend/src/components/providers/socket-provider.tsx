"use client"

import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { io, Socket } from 'socket.io-client'
import { useAuthStore } from '@/lib/store'

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || ''

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

interface SocketContextType {
  socket: Socket | null
  status: ConnectionStatus
  isConnected: boolean
}

const SocketContext = createContext<SocketContextType>({
  socket: null,
  status: 'disconnected',
  isConnected: false,
})

export function useSocketContext() {
  return useContext(SocketContext)
}

export function SocketProvider({ children }: { children: ReactNode }) {
  const [socket, setSocket] = useState<Socket | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const { isAuthenticated } = useAuthStore()

  useEffect(() => {
    // Logged out: nothing to do — the previous effect's cleanup (below)
    // already disconnected any socket when isAuthenticated flipped.
    if (!isAuthenticated) return

    setStatus('connecting')

    const s = io(WS_URL || undefined, {
      // Auth rides the httpOnly access cookie on the handshake. No token is
      // sent from JS (none is held there) and never in the query string.
      withCredentials: true,
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 10000,
      timeout: 10000,
    })

    s.on('connect', () => {
      setStatus('connected')
    })

    // permissions_changed: the user's roles/permissions changed. Refetch
    // /auth/me so nav, route guards and gates update; the server then drops
    // this socket so rooms are recomputed, and we reconnect right away (a
    // server-side disconnect is otherwise final in socket.io).
    let reconnectAfterServerDisconnect = false
    s.on('permissions_changed', () => {
      reconnectAfterServerDisconnect = true
      void useAuthStore.getState().refreshUser()
    })

    s.on('disconnect', (reason: string) => {
      setStatus('disconnected')
      if (reason === 'io server disconnect' && reconnectAfterServerDisconnect) {
        reconnectAfterServerDisconnect = false
        s.connect()
      }
    })

    s.on('connect_error', () => {
      setStatus('error')
    })

    s.on('connected', (data: { user_id?: string; anonymous?: boolean }) => {
      if (data.anonymous) {
        console.warn('[Socket] Connected anonymously — token may be invalid')
      }
    })

    setSocket(s)

    return () => {
      s.disconnect()
      setSocket(null)
      setStatus('disconnected')
    }
  }, [isAuthenticated])

  return (
    <SocketContext.Provider
      value={{
        socket,
        status,
        isConnected: status === 'connected',
      }}
    >
      {children}
    </SocketContext.Provider>
  )
}
