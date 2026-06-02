import { useState, useCallback, useRef, useEffect } from 'react'
import type { AgentState, ChatMessage, DataCard, ReplayData, ReportArtifact, SimAgent } from '../types'
import { AGENT_COLORS, INITIAL_AGENTS } from '../constants'

function isDataCard(value: unknown): value is DataCard {
  if (!value || typeof value !== 'object') return false
  const c = value as Partial<DataCard>
  return typeof c.title === 'string' && !!c.data && typeof c.data === 'object'
}

type WsMessage = {
  type?: unknown
  agents?: unknown
  simColors?: unknown
  agent?: unknown
  status?: unknown
  tool?: unknown
  from?: unknown
  text?: unknown
  card?: unknown
  tracker?: unknown
  analyst?: unknown
  replay?: unknown
  charts?: unknown
  reports?: unknown
  summary?: unknown
  compactedMessages?: unknown
  retainedMessages?: unknown
}

function isAgentStatus(value: unknown): value is AgentState['status'] {
  return value === 'idle' || value === 'working' || value === 'done'
}

function isAgentStateArray(value: unknown): value is AgentState[] {
  return Array.isArray(value) && value.every(item => {
    if (!item || typeof item !== 'object') return false
    const candidate = item as Record<string, unknown>
    return (
      typeof candidate.name === 'string' &&
      typeof candidate.color === 'string' &&
      isAgentStatus(candidate.status)
    )
  })
}

function isSender(value: unknown): value is ChatMessage['from'] {
  return (
    value === 'user' ||
    value === 'orchestrator' ||
    value === 'tracker' ||
    value === 'analyst' ||
    value === 'reporter'
  )
}

function hasReplayFrames(value: unknown): value is ReplayData {
  return (
    !!value &&
    typeof value === 'object' &&
    Array.isArray((value as ReplayData).frames)
  )
}

function isReportArray(value: unknown): value is ReportArtifact[] {
  return Array.isArray(value) && value.every(item => {
    if (!item || typeof item !== 'object') return false
    const candidate = item as Record<string, unknown>
    return typeof candidate.key === 'string' && typeof candidate.filename === 'string'
  })
}

export function useWebSocket() {
  const [connected, setConnected] = useState(false)
  const [agents, setAgents] = useState<AgentState[]>(INITIAL_AGENTS)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [thinking, setThinking] = useState(false)
  const [simAgents, setSimAgents] = useState<SimAgent[]>([])
  const [envCard, setEnvCard] = useState<DataCard | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const idRef = useRef(0)
  const simColorsRef = useRef<string[]>([...AGENT_COLORS])
  const pendingSendsRef = useRef<string[]>([])

  useEffect(() => {
    let stopped = false
    let retryTimeout: ReturnType<typeof setTimeout>

    function connect() {
      if (stopped) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws`)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        const pending = pendingSendsRef.current.splice(0)
        for (const text of pending) {
          ws.send(JSON.stringify({ message: text }))
        }
      }
      ws.onclose = () => {
        setConnected(false)
        // The per-connection Orchestrator on the backend dies with this socket,
        // so any in-flight chat() is gone. If we don't clear `thinking` and the
        // Orchestrator's "working" state here, the merger in the `agents` case
        // preserves them across reconnect and the input stays disabled forever.
        setThinking(false)
        // envCard reflects the live (post-sim) state of the dead Orchestrator;
        // dropping it lets AppShell fall back to the chat-derived env card
        // until the new session emits its own env_card_update.
        setEnvCard(null)
        setAgents(prev => prev.map(a =>
          a.name === 'Orchestrator'
            ? { ...a, status: 'idle', activeTool: undefined }
            : a
        ))
        if (!stopped) retryTimeout = setTimeout(connect, 1500)
      }

      ws.onmessage = (event) => {
        let data: WsMessage
        try {
          data = JSON.parse(event.data)
        } catch {
          console.error('[ws] invalid JSON frame:', event.data)
          return
        }

        switch (data.type) {
          case 'agents':
            // Merge backend agents with local Orchestrator state
            if (!isAgentStateArray(data.agents)) break
            {
              const backendAgents = data.agents
              setAgents(prev => {
                const orch = prev.find(a => a.name === 'Orchestrator') || { name: 'Orchestrator', status: 'idle' as const, color: '#94a3b8' }
                return [orch, ...backendAgents]
              })
            }
            // Backend sends the color palette once on connect
            if (Array.isArray(data.simColors) && data.simColors.every(c => typeof c === 'string')) {
              simColorsRef.current = data.simColors
            }
            break

          case 'agent_status':
            if (typeof data.agent !== 'string' || !isAgentStatus(data.status)) break
            {
              const agentName = data.agent
              const status = data.status
              setAgents(prev => prev.map(a =>
                a.name === agentName
                  ? { ...a, status, activeTool: status === 'working' ? a.activeTool : undefined }
                  : a
              ))
            }
            break

          case 'agent_tool':
            if (typeof data.agent !== 'string' || typeof data.tool !== 'string') break
            {
              const agentName = data.agent
              const tool = data.tool
              setAgents(prev => prev.map(a =>
                a.name === agentName ? { ...a, activeTool: tool } : a
              ))
            }
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
              from: isSender(data.from) ? data.from : 'orchestrator',
              text: typeof data.text === 'string' ? data.text : '',
              card: data.card as ChatMessage['card'],
              tracker: data.tracker as ChatMessage['tracker'],
              analyst: data.analyst as ChatMessage['analyst'],
              replay: hasReplayFrames(data.replay) ? data.replay : undefined,
              charts: Array.isArray(data.charts) ? data.charts as ChatMessage['charts'] : undefined,
              reports: isReportArray(data.reports) ? data.reports : undefined,
            } satisfies ChatMessage
            setMessages(prev => [...prev, msg])
            // A fresh Environment Spec chat card means a new env was created;
            // drop the live envCard (which carries the prior env's Seed/Pasos)
            // so AppShell falls back to envCardFromMsgs until the next sim
            // emits a new env_card_update. Without this the sidebar sticks to
            // the old env's post-sim card while the chat already moved on.
            if (msg.card?.title === 'Environment Spec') {
              setEnvCard(null)
            }
            // Extract simulation agents from replay
            if (msg.replay?.frames?.[0]?.agents) {
              const colors = simColorsRef.current
              const ids = msg.replay.frames[0].agents.map(a => a.id)
              setSimAgents(ids.map((id: string, i: number) => ({
                id,
                color: colors[i % colors.length],
              })))
            }
            break
          }

          case 'context_compacted': {
            setMessages(prev => [...prev, {
              id: String(++idRef.current),
              from: 'orchestrator',
              text: typeof data.text === 'string' ? data.text : 'Contexto compactado.',
              contextSummary: {
                summary: typeof data.summary === 'string' ? data.summary : '',
                compactedMessages: typeof data.compactedMessages === 'number' ? data.compactedMessages : 0,
                retainedMessages: typeof data.retainedMessages === 'number' ? data.retainedMessages : 0,
              },
            }])
            break
          }

          case 'env_card_update':
            // Silent sidebar refresh — backend re-emits the env card with
            // post-run fields (seed, Pasos ejecutados) without injecting a
            // new chat message. The chat already showed the env card once
            // at create_environment time.
            if (isDataCard(data.card)) setEnvCard(data.card)
            break

          case 'error':
            setThinking(false)
            setMessages(prev => [...prev, {
              id: String(++idRef.current),
              from: 'orchestrator',
              text: `Error: ${typeof data.text === 'string' ? data.text : 'unknown error'}`,
            }])
            break
        }
      }
    }

    connect()
    return () => { stopped = true; clearTimeout(retryTimeout); wsRef.current?.close() }
  }, [])

  const send = useCallback((text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    const ws = wsRef.current
    setMessages(prev => [...prev, {
      id: String(++idRef.current),
      from: 'user',
      text: trimmed,
    }])
    setThinking(true)
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      pendingSendsRef.current.push(trimmed)
      return
    }
    ws.send(JSON.stringify({ message: trimmed }))
  }, [])

  return { connected, agents, messages, thinking, simAgents, envCard, send }
}
