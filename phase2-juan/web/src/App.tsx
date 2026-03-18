import type { AgentState, ChatMessage, SimAgent } from './types'
import { AgentPanel } from './components/AgentPanel'
import { ChatPanel } from './components/ChatPanel'
import { useWebSocket } from './hooks/useWebSocket'
import { useMockWebSocket } from './hooks/useMockWebSocket'

const isMock = new URLSearchParams(window.location.search).has('mock')

// Wrap in separate components to avoid conditional hook calls
function MockApp() {
  const { connected, agents, messages, thinking, simAgents, send } = useMockWebSocket()
  return <AppShell connected={connected} agents={agents} messages={messages} thinking={thinking} simAgents={simAgents} send={send} />
}

function RealApp() {
  const { connected, agents, messages, thinking, simAgents, send } = useWebSocket()
  return <AppShell connected={connected} agents={agents} messages={messages} thinking={thinking} simAgents={simAgents} send={send} />
}

export default function App() {
  return isMock ? <MockApp /> : <RealApp />
}

interface ShellProps {
  connected: boolean
  agents: AgentState[]
  messages: ChatMessage[]
  thinking: boolean
  simAgents: SimAgent[]
  send: (text: string) => void
}

function AppShell({ connected, agents, messages, thinking, simAgents, send }: ShellProps) {
  return (
    <div className="h-screen bg-bg p-4 flex gap-4 overflow-hidden">
      {/* Sidebar — floating panel */}
      <div className="hidden md:flex w-[200px] flex-shrink-0 min-h-0 flex-col floating-panel">
        {/* Sidebar header */}
        <div className="flex justify-between items-center px-5 py-4 border-b border-border-subtle">
          <div>
            <h1 className="text-[13px] font-bold uppercase tracking-[2px]">DecisionLab</h1>
            <p className="text-[10px] mt-0.5 text-text-dim">Laboratorio Virtual</p>
          </div>
        </div>
        <AgentPanel agents={agents} simAgents={simAgents} />
        {/* Connection status at bottom */}
        <div className="px-5 py-3 border-t border-border-subtle flex items-center gap-2 text-[9px] text-text-faint">
          {isMock && (
            <span className="px-1.5 py-0.5 uppercase tracking-[1px] rounded-[var(--radius-sm)] text-accent-amber" style={{ background: 'color-mix(in srgb, var(--color-accent-amber) 15%, transparent)', border: '1px solid color-mix(in srgb, var(--color-accent-amber) 25%, transparent)' }}>
              mock
            </span>
          )}
          <span>
            <span style={{ color: connected ? 'var(--color-accent-green-light)' : 'var(--color-accent-red)' }}>●</span>
            {' '}{connected ? 'conectado' : 'desconectado'}
          </span>
        </div>
      </div>

      {/* Main chat — floating panel */}
      <div className="flex-1 min-h-0 flex flex-col floating-panel">
        <ChatPanel messages={messages} thinking={thinking} onSend={send} agents={agents} />
      </div>

      {/* Mobile agent bar — bottom floating */}
      <div className="md:hidden fixed bottom-4 left-4 right-4 flex items-center gap-2 px-4 py-2.5 floating-panel overflow-x-auto z-30">
        {agents.map(a => (
          <div key={a.name} className="flex items-center gap-1 flex-shrink-0">
            <div className="w-1.5 h-1.5 rounded-full" style={{
              background: a.color,
              opacity: a.status === 'idle' ? 0.3 : 1,
            }} />
            <span className="text-[8px] uppercase text-text-dim">{a.name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
