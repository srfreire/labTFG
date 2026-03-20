import { useState, useCallback, useRef, useEffect } from 'react'
import type { AgentState, PipelineStep, ChatMessage, SimAgent } from '../types'

// Fallback colors — overridden by backend on first WS message
const DEFAULT_SIM_COLORS = ['#4ade80', '#fbbf24', '#a78bfa', '#f472b6', '#38bdf8', '#fb923c']

export function useWebSocket() {
  const [connected, setConnected] = useState(false)
  const [agents, setAgents] = useState<AgentState[]>([
    { name: 'Orchestrator', status: 'idle', color: '#94a3b8' },
    { name: 'Architect', status: 'idle', color: '#4ade80' },
    { name: 'Tracker', status: 'idle', color: '#fbbf24' },
    { name: 'Analyst', status: 'idle', color: '#a78bfa' },
    { name: 'Reporter', status: 'idle', color: '#f472b6' },
  ])
  const [pipeline, setPipeline] = useState<PipelineStep[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [thinking, setThinking] = useState(false)
  const [simAgents, setSimAgents] = useState<SimAgent[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const idRef = useRef(0)
  const simColorsRef = useRef<string[]>(DEFAULT_SIM_COLORS)

  useEffect(() => {
    let stopped = false
    let retryTimeout: ReturnType<typeof setTimeout>

    function connect() {
      if (stopped) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws`)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!stopped) retryTimeout = setTimeout(connect, 1500)
      }

      ws.onmessage = (event) => {
        let data: Record<string, unknown>
        try {
          data = JSON.parse(event.data)
        } catch {
          console.error('[ws] invalid JSON frame:', event.data)
          return
        }

        switch (data.type) {
          case 'agents':
            // Merge backend agents with local Orchestrator state
            setAgents(prev => {
              const orch = prev.find(a => a.name === 'Orchestrator') || { name: 'Orchestrator', status: 'idle' as const, color: '#94a3b8' }
              return [orch, ...data.agents]
            })
            if (data.pipeline) setPipeline(data.pipeline)
            // Backend sends the color palette once on connect
            if (Array.isArray(data.simColors)) simColorsRef.current = data.simColors
            break

          case 'agent_status':
            setAgents(prev => prev.map(a =>
              a.name === data.agent
                ? { ...a, status: data.status, activeTool: data.status === 'working' ? a.activeTool : undefined }
                : a
            ))
            break

          case 'agent_tool':
            setAgents(prev => prev.map(a =>
              a.name === data.agent ? { ...a, activeTool: data.tool } : a
            ))
            break

          case 'status': {
            const isThinking = data.status === 'thinking'
            setThinking(isThinking)
            setAgents(prev => prev.map(a =>
              a.name === 'Orchestrator'
                ? { ...a, status: isThinking ? 'working' : 'done', activeTool: isThinking ? a.activeTool : undefined }
                : a
            ))
            break
          }

          case 'message': {
            setThinking(false)
            const msg = {
              id: String(++idRef.current),
              from: data.from || 'orchestrator',
              text: data.text,
              card: data.card,
              tracker: data.tracker,
              analyst: data.analyst,
              replay: data.replay,
            }
            setMessages(prev => [...prev, msg])
            // Extract simulation agents from replay
            if (data.replay?.frames?.[0]?.agents) {
              const colors = simColorsRef.current
              const ids = data.replay.frames[0].agents.map((a: { id: string }) => a.id)
              setSimAgents(ids.map((id: string, i: number) => ({
                id,
                color: colors[i % colors.length],
              })))
            }
            break
          }

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
    }

    connect()
    return () => { stopped = true; clearTimeout(retryTimeout); wsRef.current?.close() }
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

  return { connected, agents, pipeline, messages, thinking, simAgents, send }
}
