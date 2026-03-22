/**
 * useWebSocket — real-time cluster metrics via WebSocket
 * Automatically reconnects on disconnect with exponential backoff.
 *
 * NOTE: Next.js rewrites cannot proxy ws:// connections.
 * The WebSocket connects directly to the backend URL derived from
 * NEXT_PUBLIC_API_URL (http→ws / https→wss conversion happens here).
 */
import { useEffect, useRef, useCallback, useState } from 'react'

/**
 * Derive the WebSocket base URL from the HTTP API URL.
 * http://host:8000  → ws://host:8000
 * https://host      → wss://host
 */
function getWsBase(): string {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  return apiUrl.replace(/^https:\/\//, 'wss://').replace(/^http:\/\//, 'ws://')
}

type Status = 'connecting' | 'connected' | 'disconnected' | 'error'

interface UseWebSocketOptions {
  onMessage?: (data: any) => void
  enabled?: boolean
  reconnectDelay?: number   // ms base delay (default 2000)
  maxDelay?: number         // ms max delay  (default 30000)
}

export function useClusterWebSocket(
  clusterId: string,
  options: UseWebSocketOptions = {}
) {
  const { onMessage, enabled = true, reconnectDelay = 2000, maxDelay = 30000 } = options
  const [status, setStatus] = useState<Status>('disconnected')
  const [lastMessage, setLastMessage] = useState<any>(null)
  const ws = useRef<WebSocket | null>(null)
  const retries = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const mountedRef = useRef(true)
  // Stable ref so connect() callback doesn't re-create on onMessage change
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const connect = useCallback(() => {
    if (!enabled || !clusterId || !mountedRef.current) return
    if (ws.current?.readyState === WebSocket.OPEN) return

    setStatus('connecting')

    try {
      const wsUrl = `${getWsBase()}/ws/metrics/${clusterId}`
      const socket = new WebSocket(wsUrl)
      ws.current = socket

      socket.onopen = () => {
        if (!mountedRef.current) { socket.close(); return }
        setStatus('connected')
        retries.current = 0
      }

      socket.onmessage = (event) => {
        if (!mountedRef.current) return
        try {
          const data = JSON.parse(event.data)
          setLastMessage(data)
          onMessageRef.current?.(data)
        } catch { /* ignore non-JSON frames */ }
      }

      socket.onerror = () => {
        if (!mountedRef.current) return
        setStatus('error')
      }

      socket.onclose = () => {
        if (!mountedRef.current) return
        setStatus('disconnected')
        // Exponential backoff
        const delay = Math.min(reconnectDelay * Math.pow(1.5, retries.current), maxDelay)
        retries.current += 1
        reconnectTimer.current = setTimeout(connect, delay)
      }
    } catch {
      setStatus('error')
    }
  }, [clusterId, enabled, reconnectDelay, maxDelay])   // onMessage intentionally excluded

  const disconnect = useCallback(() => {
    clearTimeout(reconnectTimer.current)
    ws.current?.close()
    ws.current = null
    setStatus('disconnected')
  }, [])

  useEffect(() => {
    mountedRef.current = true
    if (enabled) connect()
    return () => {
      mountedRef.current = false
      clearTimeout(reconnectTimer.current)
      ws.current?.close()
    }
  }, [connect, enabled])

  return { status, lastMessage, disconnect, reconnect: connect }
}
