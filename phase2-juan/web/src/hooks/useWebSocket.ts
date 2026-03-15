import { useState, useCallback, useRef, useEffect } from 'react'
import type { AgentState, PipelineStep, ChatMessage } from '../types'

export function useWebSocket() {
  const [connected, setConnected] = useState(false)
  const [agents, setAgents] = useState<AgentState[]>([])
  const [pipeline, setPipeline] = useState<PipelineStep[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [thinking, setThinking] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const idRef = useRef(0)

  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.hostname}:8000/ws`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)

      switch (data.type) {
        case 'agents':
          setAgents(data.agents)
          if (data.pipeline) setPipeline(data.pipeline)
          break

        case 'agent_status':
          setAgents(prev => prev.map(a =>
            a.name === data.agent ? { ...a, status: data.status } : a
          ))
          break

        case 'status':
          setThinking(data.status === 'thinking')
          break

        case 'message':
          setThinking(false)
          setMessages(prev => [...prev, {
            id: String(++idRef.current),
            from: data.from || 'orchestrator',
            text: data.text,
            card: data.card,
            tracker: data.tracker,
            analyst: data.analyst,
          }])
          break

        case 'error':
          setThinking(false)
          setMessages(prev => [...prev, {
            id: String(++idRef.current),
            from: 'orchestrator',
            text: `Error: ${data.text}`,
          }])
          break
      }
    }

    return () => ws.close()
  }, [])

  const send = useCallback((text: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setMessages(prev => [...prev, {
      id: String(++idRef.current),
      from: 'user',
      text,
    }])
    wsRef.current.send(JSON.stringify({ message: text }))
    setThinking(true)
  }, [])

  return { connected, agents, pipeline, messages, thinking, send }
}
