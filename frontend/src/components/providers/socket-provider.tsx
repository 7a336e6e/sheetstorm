"use client"

import { createContext, useContext, useEffect, useRef, useState, ReactNode, useCallback } from 'react'
import { io, Socket } from 'socket.io-client'
import { useAuthStore } from '@/lib/store'

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'http://127.0.0.1:5000'

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
  const socketRef = useRef<Socket | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const { isAuthenticated } = useAuthStore()

  const getToken = useCallback(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('access_token')
    }
    return null
  }, [])

  useEffect(() => {
    if (!isAuthenticated) {
      // Disconnect if logged out
      if (socketRef.current) {
        socketRef.current.disconnect()
        socketRef.current = null
        setStatus('disconnected')
      }
      return
    }

    const token = getToken()
    if (!token) return

    setStatus('connecting')

    const socket = io(WS_URL, {
      query: { token },
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 10000,
      timeout: 10000,
    })

    socket.on('connect', () => {
      setStatus('connected')
    })

    socket.on('disconnect', () => {
      setStatus('disconnected')
    })

    socket.on('connect_error', () => {
      setStatus('error')
    })

    socket.on('connected', (data: { user_id?: string; anonymous?: boolean }) => {
      if (data.anonymous) {
        console.warn('[Socket] Connected anonymously — token may be invalid')
      }
    })

    socketRef.current = socket

    return () => {
      socket.disconnect()
      socketRef.current = null
      setStatus('disconnected')
    }
  }, [isAuthenticated, getToken])

  return (
    <SocketContext.Provider
      value={{
        socket: socketRef.current,
        status,
        isConnected: status === 'connected',
      }}
    >
      {children}
    </SocketContext.Provider>
  )
}
