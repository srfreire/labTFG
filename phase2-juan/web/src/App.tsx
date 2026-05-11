import { AgentPanel } from './components/AgentPanel'
import { ChatPanel } from './components/ChatPanel'
import { useWebSocket } from './hooks/useWebSocket'
import { useMockWebSocket } from './hooks/useMockWebSocket'

const isMock = new URLSearchParams(window.location.search).has('mock')

// Separate wrapper components are required: each calls exactly one hook,
// keeping the Rules of Hooks intact across mock/real socket variants.
function MockApp() {
  return <AppShell {...useMockWebSocket()} />
}

function RealApp() {
  return <AppShell {...useWebSocket()} />
}

export default function App() {
  return isMock ? <MockApp /> : <RealApp />
}

type ShellProps = ReturnType<typeof useWebSocket>

function AppShell({ connected, agents, messages, thinking, simAgents, send }: ShellProps) {
  return (
    <div className="h-screen p-10 flex gap-8 overflow-hidden">
      {/* Sidebar — floating panel, frosted glass */}
      <aside className="hidden md:flex w-[200px] flex-shrink-0 min-h-0 flex-col floating-panel">
        {/* Header — Phase 1 style */}
        <div className="px-5 py-4 border-b border-border-subtle shrink-0">
          <div className="text-[17px] font-semibold tracking-tight text-text">
            DecisionLab
          </div>
          <div className="flex items-center gap-1.5 mt-1">
            <span className="text-[13px] text-text-muted">Laboratorio</span>
            <span
              className="w-2 h-2 rounded-full inline-block shrink-0"
              style={{ background: connected ? 'var(--color-accent-green-light)' : 'var(--color-accent-red)' }}
            />
            {isMock && (
              <span className="text-[9px] px-1.5 py-0.5 uppercase tracking-[1px] rounded-[var(--radius-sm)] text-accent-amber" style={{ background: 'color-mix(in srgb, var(--color-accent-amber) 15%, transparent)', border: '1px solid color-mix(in srgb, var(--color-accent-amber) 25%, transparent)' }}>
                mock
              </span>
            )}
          </div>
        </div>
        <AgentPanel agents={agents} simAgents={simAgents} />
      </aside>

      {/* Main chat — floating panel */}
      <main className="flex-1 min-h-0 flex flex-col floating-panel">
        <ChatPanel messages={messages} thinking={thinking} onSend={send} agents={agents} />
      </main>

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
