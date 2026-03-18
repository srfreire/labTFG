import type { AgentState, ChatMessage } from './types'
import { AgentPanel } from './components/AgentPanel'
import { ChatPanel } from './components/ChatPanel'
import { useWebSocket } from './hooks/useWebSocket'
import { useMockWebSocket } from './hooks/useMockWebSocket'

const isMock = new URLSearchParams(window.location.search).has('mock')

// Wrap in separate components to avoid conditional hook calls
function MockApp() {
  const { connected, agents, messages, thinking, send } = useMockWebSocket()
  return <AppShell connected={connected} agents={agents} messages={messages} thinking={thinking} send={send} />
}

function RealApp() {
  const { connected, agents, messages, thinking, send } = useWebSocket()
  return <AppShell connected={connected} agents={agents} messages={messages} thinking={thinking} send={send} />
}

export default function App() {
  return isMock ? <MockApp /> : <RealApp />
}

interface ShellProps {
  connected: boolean
  agents: AgentState[]
  messages: ChatMessage[]
  thinking: boolean
  send: (text: string) => void
}

function AppShell({ connected, agents, messages, thinking, send }: ShellProps) {
  return (
    <div className="flex flex-col h-screen bg-bg">
      {/* Header */}
      <div className="flex justify-between items-center px-6 py-3 border-b border-border bg-surface/80 backdrop-blur-xl">
        <div>
          <h1 className="text-[14px] font-bold uppercase tracking-[2px]">DecisionLab</h1>
          <p className="text-[11px] mt-0.5 text-text-dim">
            Laboratorio Virtual de Simulación
          </p>
        </div>
        <div className="flex items-center gap-3 text-[9px] text-text-faint">
          {isMock && (
            <span className="px-1.5 py-0.5 uppercase tracking-[1px] rounded-[var(--radius-sm)]" style={{ background: 'rgba(251,191,36,0.15)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.25)' }}>
              mock
            </span>
          )}
          <span>
            <span style={{ color: connected ? '#4ade80' : '#ef4444' }}>●</span>
            {' '}{connected ? 'conectado' : 'desconectado'}
          </span>
        </div>
      </div>

      {/* Main */}
      <div className="flex flex-1 overflow-hidden">
        <div className="hidden md:block w-[240px] flex-shrink-0">
          <AgentPanel agents={agents} />
        </div>
        <ChatPanel messages={messages} thinking={thinking} onSend={send} agents={agents} />
      </div>

      {/* Mobile agent bar */}
      <div className="md:hidden flex items-center gap-2 px-4 py-2 border-t border-border-subtle overflow-x-auto">
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
